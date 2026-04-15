"""
Manifest Explorer

Interactive visualization of VirtualiZarr chunk manifests.
Loads from a pre-generated Kerchunk JSON -- no authentication required.

Usage:
    # Direct with argument:
    uv run python app.py path/to/manifest.json

    # Via panel serve with env var:
    MANIFEST_PATH=path/to/manifest.json uv run panel serve app.py --show

    # Via panel serve with URL query param:
    uv run panel serve app.py --show -- app-manifest=path/to/manifest.json
"""

import os
import sys
import warnings
from pathlib import Path

import holoviews as hv
import panel as pn

import vzviz

warnings.filterwarnings(
    "ignore",
    message="Numcodecs codecs are not in the Zarr version 3 specification",
    category=UserWarning,
)

hv.extension("bokeh")
pn.extension("tabulator", sizing_mode="stretch_width")


def _resolve_manifest_path() -> Path:
    default = Path(__file__).parent / "data" / "xopr_manifest.json"

    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        return Path(sys.argv[1])

    env = os.environ.get("MANIFEST_PATH")
    if env:
        return Path(env)

    if pn.state.location and pn.state.location.query_params:
        p = pn.state.location.query_params.get("manifest")
        if p:
            return Path(p)

    return default


def create_app(manifest_path: Path):
    if not manifest_path.exists():
        return pn.Column(
            pn.pane.Markdown("# Manifest Not Found"),
            pn.pane.Markdown(
                f"Expected manifest at: `{manifest_path}`\n\n"
                "Generate one with:\n"
                "```\n"
                "uv run scripts/generate_manifest_generic.py <file.h5> ./data --dry-run\n"
                "uv run scripts/generate_manifest_generic.py <file.h5> ./data --group=/some/group\n"
                "```"
            ),
        )

    try:
        manifest_store = vzviz.load_manifest_from_json(manifest_path)
        return vzviz.manifest_dashboard(manifest_store)
    except Exception:
        import traceback

        return pn.Column(
            pn.pane.Markdown("# Error Loading Manifest"),
            pn.pane.Markdown(f"```\n{traceback.format_exc()}\n```"),
        )


manifest_path = _resolve_manifest_path()
app = create_app(manifest_path)
app.servable(title="Manifest Explorer")

if __name__ == "__main__":
    app.show(title="Manifest Explorer")
