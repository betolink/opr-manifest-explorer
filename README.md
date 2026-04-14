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

### Generic Manifest Generator

Generate manifests from **any HDF5 file** (HDF5, MATLAB v7.3 .mat, NetCDF4, etc.) with automatic exception handling:

```bash
# From a generic HDF5 file
uv run scripts/generate_manifest_generic.py /path/to/file.h5 ./data

# From a MATLAB .mat file (with preset)
uv run scripts/generate_manifest_generic.py /path/to/file.mat ./data --matlab

# From a directory (processes all files matching pattern)
uv run scripts/generate_manifest_generic.py /path/to/directory ./data --pattern "*.h5"

# From a URL
uv run scripts/generate_manifest_generic.py https://example.com/file.h5 ./data
```

The generic script automatically collects and reports parsing exceptions for variables that cannot be virtualized, allowing manifest generation to continue even when some variables fail.

**Options:**
- `--drop, -d`: Drop specific variables (can be used multiple times)
- `--matlab, -m`: Use MATLAB v7.3 HDF5 preset (drops #refs#, #subsystem#, param_*, etc.)
- `--pattern, -p`: File pattern to match when processing directories (default: *)

See [MANIFEST_GENERATOR_USAGE.md](MANIFEST_GENERATOR_USAGE.md) for complete documentation.

### Legacy Script

The original `scripts/generate_manifest.py` script generates a manifest from a hardcoded CReSIS `.mat` file (no authentication required):

```bash
uv run scripts/generate_manifest.py
```

The default target is a single frame from the `2022_Antarctica_BaslerMKB` collection (`CSARP_standard` product).

## Findings

See [FINDINGS.md](FINDINGS.md) for observations about MATLAB v7.3 HDF5 compatibility with VirtualiZarr's HDFParser, including required workarounds and implications for full-archive virtualization.

## About

Built with [vzviz](https://github.com/virtual-zarr/vzviz) and [VirtualiZarr](https://github.com/zarr-developers/VirtualiZarr). Part of the [XOPR](https://github.com/englacial/xopr) ecosystem.
