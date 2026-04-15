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
import requests

import h5py
import json
import numpy as np
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

        root_ds = [k for k in f if isinstance(f[k], h5py.Dataset)]
        if root_ds:
            rows.append(
                {
                    "group": "/",
                    "n_vars": len(root_ds),
                    "variables": ", ".join(root_ds),
                }
            )
    return pd.DataFrame(rows)


def _fix_hdf5_references(input_path, output_path, group_path):
    """Create a patched HDF5 file with Reference fillvalues fixed.

    Some HDF5 files (especially MATLAB v7.3 .mat) have datasets with
    h5py.h5r.Reference as fillvalue, which virtualizarr can't handle.
    This function creates a copy with those datasets removed or fixed.

    Returns:
        list of problematic variable names that were removed
    """
    import h5py
    import shutil
    import numpy as np

    # Find problematic variables first
    problematic = []
    with h5py.File(input_path, "r") as src:
        group_obj = src[group_path] if group_path != "/" else src

        def find_refs(name, obj):
            if isinstance(obj, h5py.Dataset):
                try:
                    fv = obj.fillvalue
                    if isinstance(fv, h5py.h5r.Reference):
                        problematic.append(name)
                except Exception:
                    pass

        group_obj.visititems(find_refs)

    if not problematic:
        shutil.copy(input_path, output_path)
        return problematic

    # Copy file, then delete problematic datasets
    shutil.copy(input_path, output_path)

    with h5py.File(output_path, "r+") as dst:
        group_obj = dst[group_path] if group_path != "/" else dst
        for name in problematic:
            if name in group_obj:
                del group_obj[name]

    return problematic


def _clean_hdf5_attributes(input_path, output_path, group_path):
    """Create a patched HDF5 file with non-serializable attributes removed.

    Some HDF5 files (especially MATLAB v7.3 .mat) have attributes with
    numpy byte arrays that can't be JSON serialized. This function creates
    a copy with those attributes removed or converted.

    Returns:
        list of attribute keys that were removed/cleaned
    """
    import h5py
    import shutil
    import numpy as np

    cleaned = []

    with h5py.File(input_path, "r") as src:
        group_obj = src[group_path] if group_path != "/" else src
        attrs = dict(group_obj.attrs)

    # Check which attributes are problematic
    problematic_keys = []
    for key, value in attrs.items():
        try:
            import ujson

            ujson.dumps(value)
        except (TypeError, OverflowError):
            problematic_keys.append(key)

    if not problematic_keys:
        shutil.copy(input_path, output_path)
        return cleaned

    # Copy file and clean attributes
    shutil.copy(input_path, output_path)

    with h5py.File(output_path, "r+") as dst:
        group_obj = dst[group_path] if group_path != "/" else dst
        for key in problematic_keys:
            original_value = attrs[key]
            cleaned.append(key)

            # Try to convert byte strings to regular strings
            if isinstance(original_value, np.bytes_):
                try:
                    group_obj.attrs[key] = original_value.decode("utf-8")
                except:
                    del group_obj.attrs[key]
            elif isinstance(original_value, np.ndarray):
                # Try to convert byte arrays
                try:
                    if original_value.dtype.kind == "S":
                        group_obj.attrs[key] = original_value.astype(str).tolist()
                    else:
                        del group_obj.attrs[key]
                except:
                    del group_obj.attrs[key]
            else:
                # Delete the attribute
                try:
                    del group_obj.attrs[key]
                except:
                    pass

    return cleaned


def make_manifest(file_path, group):
    p = Path(file_path).resolve()

    # Pre-check for Reference fillvalues in .mat files
    patched_path = None
    removed_vars = []

    if p.suffix.lower() == ".mat":
        with h5py.File(p, "r") as f:
            group_obj = f[group] if group != "/" else f

            def find_refs(name, obj):
                if isinstance(obj, h5py.Dataset):
                    try:
                        fv = obj.fillvalue
                        if isinstance(fv, h5py.h5r.Reference):
                            removed_vars.append(name)
                    except Exception:
                        pass

            group_obj.visititems(find_refs)

        if removed_vars:
            # Create patched HDF5 file
            patched_path = Path(_tmpdir) / f"{p.stem}_patched.h5"
            removed_vars = _fix_hdf5_references(p, patched_path, group)

    # Check for non-serializable attributes in .mat files
    cleaned_attrs = []
    if p.suffix.lower() == ".mat":
        # Create a second patched file with cleaned attributes for JSON export
        clean_attrs_path = Path(_tmpdir) / f"{p.stem}_clean_attrs.h5"
        cleaned_attrs = _clean_hdf5_attributes(p, clean_attrs_path, group)

        # Use the cleaned file for JSON export
        json_export_path = clean_attrs_path if cleaned_attrs else None
    else:
        json_export_path = None

    # Set up registry based on whether we have a patched file
    if patched_path:
        registry = ObjectStoreRegistry(
            {"file://": _FileStore(str(patched_path.parent))}
        )
        file_path = patched_path
    else:
        registry = ObjectStoreRegistry({"file://": _FileStore(str(p.parent))})

    drop_variables = None
    if p.suffix.lower() == ".mat":
        drop_variables = [
            "#refs#",
            "#subsystem#",
            "param_array",
            "param_records",
            "param_sar",
            "file_type",
            "file_version",
            "radiometric_corr_dB",
        ] + removed_vars

    try:
        manifest = vz.parsers.HDFParser(group=group, drop_variables=drop_variables)(
            f"file://{Path(file_path).resolve()}", registry=registry
        )
        return manifest, removed_vars, json_export_path, cleaned_attrs
    except AttributeError as e:
        if "'h5py.h5r.Reference' object has no attribute 'item'" in str(e):
            raise RuntimeError(
                f"Failed to handle Reference fillvalues. Removed vars: {removed_vars}"
            ) from e
        raise


def hdf4_to_hdf5(hdf4_path, hdf5_path):
    """Convert HDF4 file to intermediate HDF5.

    Args:
        hdf4_path: Path to the HDF4 file
        hdf5_path: Path for the output HDF5 file

    Returns:
        Path to the converted HDF5 file
    """
    from pyhdf.HDF import HDF
    from pyhdf.SD import SD

    h4 = SD(str(hdf4_path))

    with h5py.File(str(hdf5_path), "w") as h5:
        for name in h4.datasets():
            sds = h4.select(name)
            data = sds[:]
            h5.create_dataset(name, data=data)

            for attr in sds.attributes():
                try:
                    h5[name].attrs[attr] = sds.getattr(attr)
                except Exception:
                    pass

        for attr in h4.attributes():
            try:
                h5.attrs[attr] = h4.getattr(attr)
            except Exception:
                pass

    h4.end()
    return hdf5_path


def is_hdf4(path):
    """Check if a file is HDF4 format."""
    try:
        from pyhdf.HDF import HDF, HC

        h = HDF(str(path), HC.READ)
        h.close()
        return True
    except Exception:
        return False


def make_manifest_from_hdf4(hdf4_path, output_path=None):
    """Generate kerchunk manifest from HDF4 file using kerchunk HDF4ToZarr.

    Args:
        hdf4_path: Path to the HDF4 file
        output_path: Optional path to save the manifest JSON

    Returns:
        The kerchunk manifest dict
    """
    from kerchunk.hdf4 import HDF4ToZarr
    import json

    h = HDF4ToZarr(str(hdf4_path))
    result = h.translate()

    if output_path:

        class BytesEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, bytes):
                    return {"__bytes__": True, "data": obj.hex()}
                return super().default(obj)

        with open(output_path, "w") as f:
            json.dump(result, f, cls=BytesEncoder)

    return result


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
    status = pn.pane.Markdown(
        "Enter a local path or remote URL, then click **Load**.<br>"
        "Note: Remote files are downloaded to a temp directory before scanning."
    )
    status_css = pn.pane.HTML(
        "<style>.bk-status { padding: 10px; margin: 10px 0; }</style>",
        sizing_mode="stretch_width",
    )
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

                if is_hdf4(p):
                    status.object = (
                        f"Generating kerchunk manifest for HDF4 file `{p.name}`..."
                    )
                    manifest_path = Path(_tmpdir) / f"{p.stem}_manifest.json"
                    manifest = make_manifest_from_hdf4(p, manifest_path)
                    current_file[0] = str(manifest_path)
                    status.object = (
                        "HDF4 manifest generated. Select group to visualize."
                    )
            elif url_str:
                suffix = Path(url_str.split("/")[-1].split("?")[0]).suffix or ".h5"
                tmp = Path(_tmpdir) / f"downloaded{suffix}"
                status.object = "Connecting to remote..."
                try:
                    import requests

                    with requests.get(url_str, timeout=300, stream=True) as response:
                        response.raise_for_status()
                        total_size = int(response.headers.get("content-length", 0))
                        downloaded = 0
                        with open(tmp, "wb") as f:
                            for chunk in response.iter_content(chunk_size=1024 * 1024):
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    if total_size > 0:
                                        percent = int(100 * downloaded / total_size)
                                        status.object = f"Downloading: {percent}%"
                except ImportError:
                    from urllib.request import urlretrieve

                    urlretrieve(url_str, tmp)
                except Exception as e:
                    status.object = f"Error: {str(e)}"
                    progress.active = False
                    return
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

            manifest, removed_vars, json_export_path, cleaned_attrs = make_manifest(
                current_file[0], group_path
            )
            dashboard = vzviz.manifest_dashboard(manifest)

            # Save kerchunk manifest JSON - try with cleaned attributes file first
            manifest_json_path = (
                Path(_tmpdir)
                / f"{src_name}_{group_path.replace('/', '_')}_manifest.json"
            )
            try:
                # If we have a cleaned attributes file, generate new manifest from it
                if json_export_path and json_export_path.exists():
                    # Create new manifest from cleaned file
                    clean_registry = ObjectStoreRegistry(
                        {"file://": _FileStore(str(json_export_path.parent))}
                    )
                    clean_manifest = vz.parsers.HDFParser(group=group_path)(
                        f"file://{json_export_path}", registry=clean_registry
                    )

                    vzviz.save_manifest_to_json(
                        clean_manifest,
                        manifest_json_path,
                        metadata={
                            "source": current_file[0],
                            "group": group_path,
                            "skipped_variables": removed_vars,
                            "cleaned_attributes": cleaned_attrs,
                        },
                    )
                else:
                    vzviz.save_manifest_to_json(
                        manifest,
                        manifest_json_path,
                        metadata={
                            "source": current_file[0],
                            "group": group_path,
                            "skipped_variables": removed_vars,
                        },
                    )
            except (TypeError, AttributeError) as e:
                manifest_json_path = None

            # Build chunk stats report
            report = _build_report(manifest, current_file[0], group_path)
            report_json_path = (
                Path(_tmpdir) / f"{src_name}_{group_path.replace('/', '_')}_report.json"
            )
            with open(report_json_path, "w") as f:
                json.dump(report, f, indent=2, default=str)

            # Create download buttons (skip manifest if not saved)
            manifest_saved = manifest_json_path and manifest_json_path.exists()
            if manifest_saved:
                dl_manifest_btn = pn.widgets.FileDownload(
                    file=str(manifest_json_path),
                    label="Download Kerchunk Manifest",
                    filename=manifest_json_path.name,
                    button_type="primary",
                )
            elif json_export_path and json_export_path.exists():
                dl_manifest_btn = pn.widgets.FileDownload(
                    file=str(json_export_path),
                    label="Download Cleaned HDF5 (for kerchunk)",
                    filename=json_export_path.name,
                    button_type="primary",
                )
            else:
                dl_manifest_btn = pn.pane.Markdown("*Manifest JSON not available*")

            dl_report_btn = pn.widgets.FileDownload(
                file=str(report_json_path),
                label="Download Chunk Report",
                filename=report_json_path.name,
                button_type="warning",
            )

            viz_area.clear()
            viz_area.append(pn.Row(dl_manifest_btn, dl_report_btn))

            if removed_vars:
                viz_area.append(
                    pn.pane.Markdown(
                        f"⚠️ **Skipped {len(removed_vars)} variables** (unsupported fill values):\n"
                        + ", ".join(removed_vars),
                        sizing_mode="stretch_width",
                    )
                )

            if cleaned_attrs:
                viz_area.append(
                    pn.pane.Markdown(
                        f"ℹ️ **Cleaned {len(cleaned_attrs)} attributes** (non-serializable):\n"
                        + ", ".join(cleaned_attrs),
                        sizing_mode="stretch_width",
                    )
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
            if removed_vars:
                status.object = (
                    f"Ready for `{group_path}` (skipped {len(removed_vars)} variables)"
                )
            else:
                status.object = f"Ready for `{group_path}`"
        except (AttributeError, TypeError) as e:
            if "'h5py.h5r.Reference' object has no attribute 'item'" in str(e):
                progress.bar_color = "warning"
                status.object = (
                    f"Error: Some datasets in this file have unsupported fill values (HDF5 references). "
                    f"This is a known issue with MATLAB v7.3 files in virtualizarr. "
                    f"The group was loaded but some variables may not display correctly.\n\n"
                    f"Details: {str(e)[:200]}..."
                )
            elif "not JSON serializable" in str(e):
                progress.bar_color = "warning"
                status.object = (
                    f"Error: Some HDF5 attributes contain non-serializable data (byte strings). "
                    f"The manifest was generated but some metadata may be missing.\n\n"
                    f"Details: {str(e)[:200]}..."
                )
            else:
                raise
        except Exception as e:
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
