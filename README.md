# XOPR Manifest Explorer

Interactive visualization of VirtualiZarr chunk manifests for [Open Polar Radar](https://openradar.earth) (OPR) data.

This dashboard displays the HDF5 structure of CReSIS ice-penetrating radar `.mat` files without downloading them, using pre-generated manifest metadata.

## Features

- **Variables Overview**: Browse all variables with their shapes, chunk sizes, and storage info
- **ByteMap**: Visualize how chunks are laid out in the source file(s)
- **ChunkMap**: See the chunk grid structure for selected variables
- **Summary Statistics**: File-level and manifest-level metrics

## Local Development

```bash
# Install dependencies
uv sync

# Run the app
uv run panel serve app.py --show
```

## Regenerating the Manifest

To regenerate the manifest from a CReSIS `.mat` file (no authentication required):

```bash
uv run scripts/generate_manifest.py
```

The default target is a single frame from the `2022_Antarctica_BaslerMKB` collection (`CSARP_standard` product).

## Findings

See [FINDINGS.md](FINDINGS.md) for observations about MATLAB v7.3 HDF5 compatibility with VirtualiZarr's HDFParser, including required workarounds and implications for full-archive virtualization.

## About

Built with [vzviz](https://github.com/virtual-zarr/vzviz) and [VirtualiZarr](https://github.com/zarr-developers/VirtualiZarr). Part of the [XOPR](https://github.com/englacial/xopr) ecosystem.
