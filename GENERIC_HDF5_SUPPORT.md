# Generic HDF5 Support

## Overview

Yes! The new manifest generator **handles generic HDF5 files**. It is designed to work with any HDF5-based file format, not just MATLAB files.

## Supported File Formats

The manifest generator uses `virtualizarr.parsers.HDFParser`, which is a generic HDF5 parser that supports:

- **HDF5 files** (`.h5`, `.hdf5`)
- **MATLAB v7.3 files** (`.mat`) - with optional preset
- **NetCDF4 files** (`.nc`, `.nc4`)
- **Any other HDF5-compatible format**

## Implementation Details

### Core Components

1. **`manifest_generator.py`** - Programmatic API (completely generic)
   - Uses `virtualizarr.parsers.HDFParser`
   - No file type assumptions
   - Works with any HDF5 file

2. **`scripts/generate_manifest_generic.py`** - CLI tool
   - Generic HDF5 support by default
   - Optional MATLAB preset via `--matlab` flag
   - Configurable file patterns and variable dropping

### Key Features

- **Generic by default**: No variables are dropped unless specified
- **Optional MATLAB support**: Use `--matlab` flag for MATLAB v7.3 files
- **Configurable filtering**: Drop specific variables with `--drop` option
- **Pattern matching**: Process files with custom patterns (`--pattern`)
- **Exception collection**: Collects errors without stopping generation

## Examples

### Generic HDF5 File

```bash
# No special options needed
uv run scripts/generate_manifest_generic.py file.h5 ./data
```

```python
from manifest_generator import ManifestGenerator
from pathlib import Path

generator = ManifestGenerator(drop_variables=None)
manifest_store = generator.generate(
    path="/path/to/file.h5",
    output_path=Path("output/manifest.json")
)
```

### NetCDF4 File

```bash
# NetCDF4 files are HDF5-based
uv run scripts/generate_manifest_generic.py file.nc ./data
```

### MATLAB File

```bash
# Use the MATLAB preset
uv run scripts/generate_manifest_generic.py file.mat ./data --matlab
```

```python
# Or drop specific MATLAB groups
generator = ManifestGenerator(
    drop_variables=["#refs#", "#subsystem#", "param_*"]
)
```

### Directory Processing

```bash
# Process all HDF5 files
uv run scripts/generate_manifest_generic.py /data/ ./output --pattern "*.h5"

# Process all NetCDF4 files
uv run scripts/generate_manifest_generic.py /data/ ./output --pattern "*.nc"
```

## Verification

Run the test script to verify generic HDF5 support:

```bash
uv run python scripts/test_generic_hdf5.py
```

Expected output:
```
✓ ManifestGenerator is completely generic
✓ Works with any HDF5 file format (.h5, .mat, .nc, etc.)
✓ MATLAB support is optional via drop_variables parameter
✓ No hardcoded assumptions about file types
```

## Comparison with Legacy Script

| Feature | Legacy Script | Generic Script |
|---------|---------------|----------------|
| File types | MATLAB only | Any HDF5 format |
| Variable dropping | Hardcoded | Configurable |
| Directory support | No | Yes |
| Exception handling | Basic | Advanced |
| Pattern matching | No | Yes |

## Summary

The manifest generator is **completely generic** and works with any HDF5 file format. MATLAB support is provided as an optional convenience feature, not a requirement. The core implementation uses the standard HDFParser from virtualizarr, which is designed to handle all HDF5-based formats.
