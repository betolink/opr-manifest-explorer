# Manifest Generator Usage Guide

## Overview

The manifest generator creates Kerchunk JSON manifests from **any HDF5 file** with automatic exception handling. When variables cannot be virtualized, exceptions are collected and reported rather than stopping the entire process.

**Supported formats:**
- HDF5 files (`.h5`, `.hdf5`)
- MATLAB v7.3 files (`.mat`)
- NetCDF4 files (`.nc`, `.nc4`)
- Any other HDF5-compatible format

## Command Line Usage

### Generate from a single HDF5 file

```bash
# Generic HDF5 file
uv run scripts/generate_manifest_generic.py /path/to/file.h5 ./data

# MATLAB .mat file (with preset)
uv run scripts/generate_manifest_generic.py /path/to/file.mat ./data --matlab

# NetCDF4 file
uv run scripts/generate_manifest_generic.py /path/to/file.nc ./data
```

### Generate from a directory

```bash
# Process all HDF5 files
uv run scripts/generate_manifest_generic.py /path/to/directory ./data --pattern "*.h5"

# Process all MATLAB files with preset
uv run scripts/generate_manifest_generic.py /path/to/directory ./data --matlab --pattern "*.mat"
```

### Generate from a URL

```bash
uv run scripts/generate_manifest_generic.py https://example.com/file.h5 ./data
```

### Command Line Options

```bash
usage: generate_manifest_generic.py [-h] [--drop DROP] [--matlab] [--pattern PATTERN]
                                    path [output_dir]

positional arguments:
  path                  Path to file, directory, or URL to generate manifest(s) from
  output_dir            Output directory for manifest files (default: data)

options:
  --drop, -d DROP       Variable names to drop (can be used multiple times)
  --matlab, -m          Use MATLAB v7.3 HDF5 preset (drops #refs#, #subsystem#, param_*, etc.)
  --pattern, -p PATTERN File pattern to match when processing directories (default: *)
```

### Examples with Options

```bash
# Drop specific variables
uv run scripts/generate_manifest_generic.py file.h5 ./data --drop var1 --drop var2

# Use MATLAB preset
uv run scripts/generate_manifest_generic.py file.mat ./data --matlab

# Process directory with custom pattern
uv run scripts/generate_manifest_generic.py /data/ ./output --pattern "*.nc4"
```

## Programmatic Usage

### Basic usage with any HDF5 file

```python
from manifest_generator import ManifestGenerator
from pathlib import Path

generator = ManifestGenerator()

# Generic HDF5 file
manifest_store = generator.generate(
    path="/path/to/file.h5",
    output_path=Path("output/manifest.json"),
    metadata={"source": "HDF5 data"}
)

# MATLAB file
manifest_store = generator.generate(
    path="/path/to/file.mat",
    output_path=Path("output/manifest.json"),
    metadata={"source": "MATLAB data"}
)

# NetCDF4 file
manifest_store = generator.generate(
    path="/path/to/file.nc",
    output_path=Path("output/manifest.json"),
    metadata={"source": "NetCDF4 data"}
)
```

### With custom variable filtering

```python
# Drop specific variables
generator = ManifestGenerator(
    drop_variables=["variable1", "variable2"]
)

manifest_store = generator.generate(
    path="/path/to/file.h5",
    output_path=Path("output/manifest.json")
)

# Use MATLAB preset
generator = ManifestGenerator(
    drop_variables=["#refs#", "#subsystem#", "param_*", "file_type", "file_version"]
)

manifest_store = generator.generate(
    path="/path/to/file.mat",
    output_path=Path("output/manifest.json")
)

# No variable filtering (process all variables)
generator = ManifestGenerator(drop_variables=None)

manifest_store = generator.generate(
    path="/path/to/file.h5",
    output_path=Path("output/manifest.json")
)
```

### Error handling

```python
from manifest_generator import ManifestGenerationError

try:
    manifest_store = generator.generate(
        path="/path/to/file.mat",
        output_path=Path("output/manifest.json")
    )
except ManifestGenerationError as e:
    print(f"Some variables failed: {e}")
    print(f"Successfully parsed {e.total_success} variables")
    for var, error in e.errors:
        print(f"  {var}: {error}")
```

## Exception Collection

The manifest generator automatically collects exceptions that occur during variable parsing. This allows the generation process to continue even when some variables cannot be virtualized.

When exceptions occur, you will see output like:

```
⚠ 3 variable(s) failed to parse
  - variable1: dtype not supported
  - variable2: fillvalue.item() failed
  - variable3: invalid chunk size
```

## Output

Each manifest is saved as a JSON file with:
- Chunk layout information
- Variable metadata
- Custom metadata provided via the `metadata` parameter

Example output:
```
output/
  ├── file1_manifest.json
  ├── file2_manifest.json
  └── file3_manifest.json
```
