# XOPR Manifest Explorer Findings

## File Tested

- URL: `https://data.cresis.ku.edu/data/rds/2022_Antarctica_BaslerMKB/CSARP_standard/20230109_01/Data_20230109_01_001.mat`
- Collection: 2022_Antarctica_BaslerMKB
- Product: CSARP_standard

## HDFParser Compatibility

- Did HDFParser parse the file successfully? YES, with workarounds
- Errors encountered: `AttributeError: 'h5py.h5r.Reference' object has no attribute 'item'` at `virtualizarr/parsers/hdf/hdf.py:80` (`fill_value = dataset.fillvalue.item()`). MATLAB internal groups use `dtype=object` datasets whose fill value is an HDF5 `Reference` object, not a numeric scalar.
- Workarounds needed: Pass `drop_variables` to `HDFParser()` to skip MATLAB internal groups: `#refs#`, `#subsystem#`, `param_array`, `param_records`, `param_sar`, `file_type`, `file_version`, `radiometric_corr_dB`.

## Variables Discovered

| Variable | Shape | Dtype | Chunks | Notes |
|----------|-------|-------|--------|-------|
| Data | (1820, 3115) | float32 | (1820, 8) | Radar echogram, 390 chunks |
| Bottom | (1820, 1) | float64 | (1820, 1) | Bottom layer TWTT |
| Surface | (1820, 1) | float64 | (1820, 1) | Surface layer TWTT |
| Time | (1, 3115) | float64 | (1, 3115) | Fast-time axis (TWTT in seconds) |
| Latitude | (1820, 1) | float64 | (1820, 1) | Flight path latitude |
| Longitude | (1820, 1) | float64 | (1820, 1) | Flight path longitude |
| Elevation | (1820, 1) | float64 | (1820, 1) | Aircraft elevation |
| GPS_time | (1820, 1) | float64 | (1820, 1) | GPS timestamps |
| Heading | (1820, 1) | float64 | (1820, 1) | Aircraft heading |
| Pitch | (1820, 1) | float64 | (1820, 1) | Aircraft pitch |
| Roll | (1820, 1) | float64 | (1820, 1) | Aircraft roll |

Total: 424 chunk references, 65 KB manifest.

## MATLAB HDF5 Observations

- `#refs#` group present? YES, contains ~180+ datasets with dtype=object and HDF5 Reference fill values
- `#subsystem#` group present? YES, MATLAB MCOS class system metadata
- MATLAB class attributes? Yes, `MATLAB_class` attributes on datasets (e.g., `double`, `single`)
- Dimension ordering: MATLAB stores in column-major (Fortran) order. Shapes appear transposed compared to xopr's xarray representation (xopr shows Data as (twtt, slow_time) but HDF5 has (slow_time, twtt) = (1820, 3115))
- Dimension names: All dimensions are `phony_dim_0`/`phony_dim_1`, MATLAB does not embed NetCDF-style dimension names
- Coordinate variables (Latitude, Longitude, etc.) are shape (1820, 1) rather than (1820,), they're stored as 2D column vectors

## Chunk Layout

- `Data` variable is chunked: (1820, 8) chunks across 3115 columns = 390 chunks
- Coordinate variables (Latitude, Longitude, etc.) are single-chunk contiguous: (1820, 1)
- `Time` is single-chunk contiguous: (1, 3115)
- Total byte ranges across all variables: 424 refs

## Cross-File Consistency

Tested 5 files across 2 segments (20230109_01 frames 001-003, 20230127_01 frames 001-002).

**Consistent across all files:**
- Variable set: always the same 11 variables
- Dtypes: `Data` always float32, everything else float64
- `Time` (fast-time axis): always (1, 3115), single chunk
- Dim 1 (twtt/range bins): always 3115

**Varies per frame:**
- Dim 0 (slow_time): 1818, 1819, or 1820 traces per frame
- `Data` chunk shape varies accordingly: (1820, 8), (1819, 9), (1818, 9)
- Coordinate variables follow the same dim 0 variation

## Implications for Phase 1

- Can we use HDFParser as-is for bulk virtualization? YES, with `drop_variables` workaround
- The `drop_variables` list for MATLAB internal groups should be standardized and reused across all .mat files
- Concatenation along slow_time (dim 0) produces rectilinear chunks (variable chunk sizes per frame: 1818, 1819, 1820). This is supported by the upcoming zarr-python release.
- Keep singleton dimensions (N, 1) in the virtual store for simplicity. xopr already calls `ds.squeeze()` at read time, so it can continue to do that.
- `Time` is identical across frames (shared fast-time axis). Load eagerly and store once rather than virtualizing per frame.
- All other variables (Data, coordinates) are virtualized and concatenated along dim 0.
- Dimension renaming (`phony_dim_0` -> `slow_time`, `phony_dim_1` -> `twtt`) happens at write time to Icechunk.
- Issues to address:
  1. Standardize MATLAB `drop_variables` list
  2. Handle dimension renaming from phony_dim to meaningful names
  3. Enumerate all .mat file URLs in a collection (via STAC catalog or directory listing)
  4. Consider whether `Data` dtype varies across collections (float32 here, but xopr expects complex64 for some products)
