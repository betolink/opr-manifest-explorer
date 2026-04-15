"""
HDF5 Manifest Explorer

Usage:
    panel serve explorer.py --show
    voila explorer.ipynb
"""

import atexit
import shutil
import tempfile
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple, Sequence
from collections.abc import AsyncIterator, Iterator
from urllib.request import urlretrieve

import h5py
import json
import pandas as pd
import panel as pn
import virtualizarr as vz
import virtualizarr.manifests as vzm
import vzviz

from obspec import GetResult, GetResultAsync, ObjectMeta
from obspec_utils.registry import ObjectStoreRegistry
from obspec_utils.protocols import ReadableStore

pn.extension("tabulator", sizing_mode="stretch_width")

_tmpdir = tempfile.mkdtemp(prefix="manifest_explorer_")
atexit.register(shutil.rmtree, _tmpdir, ignore_errors=True)


# ── FileStore ──
@dataclass
class _R(GetResult):
    _data: bytes
    _meta: ObjectMeta
    _attributes: Dict = field(default_factory=dict)
    _range: Tuple[int, int] = (0, 0)

    def __post_init__(self):
        if self._range == (0, 0):
            self._range = (0, len(self._data))

    @property
    def attributes(self):
        return self._attributes

    def buffer(self):
        return self._data

    @property
    def meta(self):
        return self._meta

    @property
    def range(self):
        return self._range

    def __iter__(self):
        yield self._data


@dataclass
class _RA(GetResultAsync):
    _data: bytes
    _meta: ObjectMeta
    _attributes: Dict = field(default_factory=dict)
    _range: Tuple[int, int] = (0, 0)

    def __post_init__(self):
        if self._range == (0, 0):
            self._range = (0, len(self._data))

    @property
    def attributes(self):
        return self._attributes

    async def buffer_async(self):
        return self._data

    @property
    def meta(self):
        return self._meta

    @property
    def range(self):
        return self._range

    async def __aiter__(self):
        yield self._data


class _FileStore(ReadableStore):
    def __init__(self, base_path):
        self.base_path = Path(base_path.replace("file://", "")).resolve()

    def _resolve(self, path):
        path = path.replace("file://", "")
        p = Path(path)
        if p.is_absolute():
            return p.resolve()
        if str(path).startswith(str(self.base_path).lstrip("/")):
            return Path(f"/{path}").resolve()
        return (self.base_path / path).resolve()

    def get(self, path, *, options=None):
        fp = self._resolve(path)
        s = fp.stat()
        return _R(
            _data=fp.read_bytes(),
            _meta={
                "path": path,
                "last_modified": datetime.fromtimestamp(s.st_mtime, tz=timezone.utc),
                "size": s.st_size,
                "e_tag": None,
                "version": None,
            },
        )

    async def get_async(self, path, *, options=None):
        r = self.get(path, options=options)
        return _RA(
            _data=r._data, _meta=r._meta, _attributes=r._attributes, _range=r._range
        )

    def get_range(self, path, *, start, end=None, length=None):
        if end is None:
            end = start + length
        fp = self._resolve(path)
        with open(fp, "rb") as f:
            f.seek(start)
            return f.read(end - start)

    async def get_range_async(self, path, **kw):
        return self.get_range(path, **kw)

    def get_ranges(self, path, *, starts, ends=None, lengths=None):
        if ends is None:
            ends = [s + l for s, l in zip(starts, lengths)]
        return [self.get_range(path, start=s, end=e) for s, e in zip(starts, ends)]

    async def get_ranges_async(self, path, **kw):
        return self.get_ranges(path, **kw)

    def head(self, path):
        fp = self._resolve(path)
        s = fp.stat()
        return {
            "path": path,
            "last_modified": datetime.fromtimestamp(s.st_mtime, tz=timezone.utc),
            "size": s.st_size,
            "e_tag": None,
            "version": None,
        }

    async def head_async(self, path):
        return self.head(path)


def scan_groups(file_path):
    rows = []
    with h5py.File(file_path, "r") as f:

        def visitor(name, obj):
            if isinstance(obj, h5py.Group):
                ds = [k for k in obj if isinstance(obj[k], h5py.Dataset)]
                if ds:
                    rows.append(
                        {
                            "group": f"/{name}" if name else "/",
                            "n_vars": len(ds),
                            "variables": ", ".join(ds),
                        }
                    )

        f.visititems(visitor)
    return pd.DataFrame(rows)


def make_manifest(file_path, group):
    p = Path(file_path).resolve()
    registry = ObjectStoreRegistry({"file://": _FileStore(str(p.parent))})
    return vz.parsers.HDFParser(group=group)(f"file://{p}", registry=registry)


def _build_report(manifest_store, source_file, group_path):
    from vzviz.utils import format_bytes

    chunks_df = vzviz.manifest_to_dataframe(manifest_store)
    overview_df = vzviz.variables_overview(manifest_store)
    summary_df = vzviz.manifest_summary(manifest_store)
    file_df = vzviz.file_summary(manifest_store)

    report = {
        "source_file": str(source_file),
        "group": group_path,
        "summary": summary_df.to_dict(orient="records")[0] if len(summary_df) else {},
        "variables": overview_df.to_dict(orient="records"),
        "file_stats": file_df.to_dict(orient="records"),
        "chunks": chunks_df.to_dict(orient="records"),
    }

    for var in report["variables"]:
        for k, v in var.items():
            if hasattr(v, "item"):
                var[k] = v.item()

    for key in ["summary"]:
        for k, v in report[key].items():
            if hasattr(v, "item"):
                report[key][k] = v.item()

    return report


# ── App ──
def create_app():
    file_path_input = pn.widgets.FileSelector(
        directory=str(Path.cwd() / "data"),
        only_files=True,
        sizing_mode="stretch_width",
        size=8,
        height=200,
        name="Local File Path",
        root_directory=str(Path.cwd()),
    )
    url_input = pn.widgets.TextInput(
        name="Remote URL",
        placeholder="https://example.com/file.h5",
        sizing_mode="stretch_width",
        description="HTTP(S) URL to an HDF5 file. It will be downloaded to a temp directory before scanning.",
    )
    load_btn = pn.widgets.Button(
        name="Load",
        button_type="primary",
        width=100,
        description="Scan the file for HDF5 groups and list them in the table below.",
    )
    status = pn.pane.Markdown("Enter a local path or remote URL, then click **Load**.")
    progress = pn.widgets.Progress(
        active=False, bar_color="primary", sizing_mode="stretch_width"
    )
    group_table = pn.widgets.Tabulator(
        page_size=20,
        selectable=True,
        height=400,
    )
    viz_btn = pn.widgets.Button(
        name="Visualize Selected Group",
        button_type="success",
        disabled=True,
        description="Generate a chunk manifest for the selected HDF5 group and display the interactive visualization.",
    )
    viz_area = pn.Column()
    current_file = [None]

    def on_load(event):
        print(
            f"DEBUG: on_load called! file_path_input.value={file_path_input.value}, url_input.value={url_input.value}",
            flush=True,
        )
        try:
            progress.active = True
            progress.bar_color = "primary"
            status.object = "Loading..."

            selected = file_path_input.value
            if selected:
                # selected is list of relative paths from file_path_input.directory
                selected_file = selected[0]
                path_str = str(Path(file_path_input.directory) / selected_file)
                path_str = path_str.replace("file://", "")
            else:
                path_str = ""
            url_str = url_input.value.strip() if url_input.value else ""

            if path_str:
                p = Path(path_str)
                if not p.exists():
                    status.object = f"File not found: `{p}`"
                    progress.active = False
                    return
                if p.is_dir():
                    status.object = f"Path is a directory, not a file: `{p}`"
                    progress.active = False
                    return
                current_file[0] = str(p)
                status.object = f"Scanning `{p.name}`..."
            elif url_str:
                suffix = Path(url_str.split("/")[-1].split("?")[0]).suffix or ".h5"
                tmp = Path(_tmpdir) / f"downloaded{suffix}"
                status.object = f"Downloading from `{url_str[:60]}...`"
                urlretrieve(url_str, tmp)
                current_file[0] = str(tmp)
                status.object = "Scanning..."
            else:
                status.object = "Enter a file path or URL."
                progress.active = False
                return

            df = scan_groups(current_file[0])
            if df.empty:
                status.object = "No groups with variables found."
                progress.bar_color = "warning"
            else:
                group_table.value = df
                viz_btn.disabled = True
                progress.bar_color = "success"
                status.object = (
                    f"Found **{len(df)}** groups. Select one and click Visualize."
                )
        except Exception:
            progress.bar_color = "danger"
            status.object = f"Error:\n```\n{traceback.format_exc()}\n```"
        finally:
            progress.active = False

    def on_select(event):
        viz_btn.disabled = not group_table.selection

    def on_viz(event):
        if not current_file[0] or not group_table.selection:
            return
        try:
            progress.active = True
            progress.bar_color = "primary"
            group_path = group_table.value.iloc[group_table.selection[0]]["group"]
            src_name = Path(current_file[0]).stem
            status.object = f"Generating manifest for `{group_path}`..."

            manifest = make_manifest(current_file[0], group_path)
            dashboard = vzviz.manifest_dashboard(manifest)

            # Save kerchunk manifest JSON
            manifest_json_path = (
                Path(_tmpdir)
                / f"{src_name}_{group_path.replace('/', '_')}_manifest.json"
            )
            vzviz.save_manifest_to_json(
                manifest,
                manifest_json_path,
                metadata={"source": current_file[0], "group": group_path},
            )

            # Build chunk stats report
            report = _build_report(manifest, current_file[0], group_path)
            report_json_path = (
                Path(_tmpdir) / f"{src_name}_{group_path.replace('/', '_')}_report.json"
            )
            with open(report_json_path, "w") as f:
                json.dump(report, f, indent=2, default=str)

            dl_manifest_btn = pn.widgets.FileDownload(
                file=str(manifest_json_path),
                label="Download Kerchunk Manifest",
                filename=manifest_json_path.name,
                button_type="primary",
            )
            dl_report_btn = pn.widgets.FileDownload(
                file=str(report_json_path),
                label="Download Chunk Report",
                filename=report_json_path.name,
                button_type="warning",
            )

            viz_area.clear()
            viz_area.append(
                pn.Row(dl_manifest_btn, dl_report_btn),
            )
            viz_area.append(
                pn.pane.Markdown(
                    "**Dashboard columns:**\n"
                    "- **chunk_count**: total number of chunks for this file\n"
                    "- **total_bytes_human**: sum of all chunk sizes (data referenced by this manifest, not the full file size)\n"
                    "- **byte_range**: offset range where chunks live in the source file\n"
                    "- **is_contiguous**: whether chunks are stored sequentially with no gaps\n"
                    "- **gap_bytes_human**: total wasted space between non-contiguous chunks",
                    sizing_mode="stretch_width",
                )
            )
            viz_area.append(dashboard)
            progress.bar_color = "success"
            status.object = f"Ready for `{group_path}`"
        except Exception:
            progress.bar_color = "danger"
            status.object = f"Error:\n```\n{traceback.format_exc()}\n```"
        finally:
            progress.active = False

    load_btn.on_click(on_load)
    group_table.param.watch(on_select, ["selection"])
    viz_btn.on_click(on_viz)

    return pn.Column(
        pn.pane.Markdown("# HDF5 Manifest Explorer"),
        pn.Card(
            pn.Column(
                pn.widgets.StaticText(
                    value="Browse for a local file (the server reads the file directly — no upload needed):"
                ),
                file_path_input,
                pn.widgets.StaticText(value="— or a remote URL:"),
                url_input,
                pn.Row(load_btn),
            ),
            title="1. Load File",
        ),
        progress,
        status,
        pn.Card(pn.Column(group_table, viz_btn), title="2. Select Group"),
        pn.Card(viz_area, title="3. Visualization", sizing_mode="stretch_width"),
        sizing_mode="stretch_width",
    )


app = create_app()
app.servable()
