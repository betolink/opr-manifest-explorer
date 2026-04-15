# Manifest Explorer

Interactive visualization of VirtualiZarr chunk manifests for any HDF5 file (HDF5, MATLAB v7.3 `.mat`, NetCDF4, ICESat-2, etc.).

This dashboard displays the internal structure of HDF5 files without downloading them, using pre-generated manifest metadata.

## Features

- **Variables Overview**: Browse all variables with their shapes, chunk sizes, and storage info
- **ByteMap**: Visualize how chunks are laid out in the source file(s)
- **ChunkMap**: See the chunk grid structure for selected variables
- **Summary Statistics**: File-level and manifest-level metrics

## Local Development

```bash
# Install dependencies
uv sync

# Run with a specific manifest
uv run python app.py path/to/manifest.json

# Or via panel serve with an env var
MANIFEST_PATH=path/to/manifest.json uv run panel serve app.py --show

# Or via URL query param
uv run panel serve app.py --show
# then open http://localhost:5006/app?manifest=path/to/manifest.json
```

If no manifest is specified, falls back to `data/xopr_manifest.json`.

## Generating Manifests

### 1. Discover the file structure

```bash
uv run scripts/generate_manifest_generic.py /path/to/file.h5 ./data --dry-run
```

This prints the full group/variable tree and suggests valid `--group` paths.

### 2. Generate a manifest

```bash
# Entire root group
uv run scripts/generate_manifest_generic.py /path/to/file.h5 ./data

# A specific HDF5 group
uv run scripts/generate_manifest_generic.py /path/to/file.h5 ./data --group=/gt1l/freeboard_segment

# MATLAB .mat file
uv run scripts/generate_manifest_generic.py /path/to/file.mat ./data --matlab

# From a directory
uv run scripts/generate_manifest_generic.py /path/to/directory ./data --pattern "*.h5"

# From a URL
uv run scripts/generate_manifest_generic.py https://example.com/file.h5 ./data

# Drop specific variables
uv run scripts/generate_manifest_generic.py /path/to/file.h5 ./data --drop var1 --drop var2
```

**Options:**
- `--dry-run`: List groups and variables without writing output
- `--group, -g`: HDF5 group path to virtualize (e.g. `/gt1l/freeboard_segment`)
- `--drop, -d`: Drop specific variables (can be used multiple times)
- `--matlab, -m`: Use MATLAB v7.3 HDF5 preset
- `--pattern, -p`: File pattern for directory mode (default: `*`)

See [MANIFEST_GENERATOR_USAGE.md](MANIFEST_GENERATOR_USAGE.md) for complete documentation.

### Legacy Script

The original `scripts/generate_manifest.py` generates a manifest from a hardcoded CReSIS `.mat` file:

```bash
uv run scripts/generate_manifest.py
```

## Findings

See [FINDINGS.md](FINDINGS.md) for observations about MATLAB v7.3 HDF5 compatibility with VirtualiZarr's HDFParser, including required workarounds and implications for full-archive virtualization.

## About

Built with [vzviz](https://github.com/virtual-zarr/vzviz) and [VirtualiZarr](https://github.com/zarr-developers/VirtualiZarr).
