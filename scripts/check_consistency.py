#!/usr/bin/env python3
"""
Check structural consistency across multiple .mat files in a collection.

Probes several frames from 2022_Antarctica_BaslerMKB to verify that
shapes, dtypes, chunk layouts, and variable sets are consistent.

Usage:
    uv run scripts/check_consistency.py
"""

import virtualizarr as vz

from obspec_utils.registry import ObjectStoreRegistry
from obspec_utils.stores import AiohttpStore

BASE_URL = "https://data.cresis.ku.edu"

# Sample files from different segments and frames
URLS = [
    # Segment 20230109_01, frames 001-003
    "/data/rds/2022_Antarctica_BaslerMKB/CSARP_standard/20230109_01/Data_20230109_01_001.mat",
    "/data/rds/2022_Antarctica_BaslerMKB/CSARP_standard/20230109_01/Data_20230109_01_002.mat",
    "/data/rds/2022_Antarctica_BaslerMKB/CSARP_standard/20230109_01/Data_20230109_01_003.mat",
    # Different segment (20230127_01)
    "/data/rds/2022_Antarctica_BaslerMKB/CSARP_standard/20230127_01/Data_20230127_01_001.mat",
    "/data/rds/2022_Antarctica_BaslerMKB/CSARP_standard/20230127_01/Data_20230127_01_002.mat",
]

MATLAB_INTERNAL_GROUPS = [
    "#refs#",
    "#subsystem#",
    "param_array",
    "param_records",
    "param_sar",
    "file_type",
    "file_version",
    "radiometric_corr_dB",
]


def describe_arrays(manifest_store):
    """Extract array metadata as a comparable dict."""
    arrays = manifest_store._group.arrays
    return {
        name: {
            "shape": arr.shape,
            "dtype": str(arr.dtype),
            "chunks": arr.chunks,
        }
        for name, arr in arrays.items()
    }


def main():
    store = AiohttpStore(BASE_URL)
    registry = ObjectStoreRegistry({BASE_URL: store})
    parser = vz.parsers.HDFParser(drop_variables=MATLAB_INTERNAL_GROUPS)

    results = []
    for path in URLS:
        url = BASE_URL + path
        name = path.split("/")[-1]
        print(f"Parsing {name}...")
        try:
            ms = parser(url, registry=registry)
            info = describe_arrays(ms)
            results.append((name, info, None))
        except Exception as e:
            results.append((name, None, str(e)))
            print(f"  FAILED: {e}")

    # Report
    print("\n" + "=" * 80)
    print("CONSISTENCY REPORT")
    print("=" * 80)

    # Check for failures
    failures = [(name, err) for name, _, err in results if err]
    if failures:
        print(f"\n{len(failures)} file(s) failed to parse:")
        for name, err in failures:
            print(f"  {name}: {err}")

    successful = [(name, info) for name, info, err in results if info]
    if not successful:
        print("No files parsed successfully.")
        return

    # Variable names
    var_sets = {name: set(info.keys()) for name, info in successful}
    all_vars = set().union(*var_sets.values())
    common_vars = set.intersection(*var_sets.values())
    if all_vars != common_vars:
        print("\nVariable sets DIFFER:")
        for name, vs in var_sets.items():
            extra = vs - common_vars
            notes = []
            if extra:
                notes.append(f"extra: {extra}")
            if all_vars - vs:
                notes.append(f"missing: {all_vars - vs}")
            if notes:
                print(f"  {name}: {', '.join(notes)}")
    else:
        print(
            f"\nVariable sets: CONSISTENT ({len(common_vars)} variables in all files)"
        )

    # Per-variable comparison
    print("\nPer-variable details:")
    for var in sorted(common_vars):
        shapes = {name: info[var]["shape"] for name, info in successful}
        dtypes = {name: info[var]["dtype"] for name, info in successful}
        chunks = {name: info[var]["chunks"] for name, info in successful}

        unique_dtypes = set(dtypes.values())
        unique_chunks = set(str(c) for c in chunks.values())

        print(f"\n  {var}:")
        print(f"    dtype: {unique_dtypes}")
        print(f"    chunks: {unique_chunks}")
        print("    shapes:")
        for name, shape in shapes.items():
            print(f"      {name}: {shape}")


if __name__ == "__main__":
    main()
