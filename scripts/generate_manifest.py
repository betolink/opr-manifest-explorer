#!/usr/bin/env python3
"""
Generate a Kerchunk JSON manifest from an XOPR (Open Polar Radar) .mat file.

No authentication required -- CReSIS data is publicly accessible.

Usage:
    uv run scripts/generate_manifest.py
"""

from pathlib import Path

import virtualizarr as vz
import vzviz

from obspec_utils.registry import ObjectStoreRegistry
from obspec_utils.stores import AiohttpStore

# Target: one frame from 2022_Antarctica_BaslerMKB, CSARP_standard product
BASE_URL = "https://data.cresis.ku.edu"
MAT_PATH = "/data/rds/2022_Antarctica_BaslerMKB/CSARP_standard/20230109_01/Data_20230109_01_001.mat"
FULL_URL = BASE_URL + MAT_PATH


def main():
    output_dir = Path(__file__).parent.parent / "data"
    output_file = output_dir / "xopr_manifest.json"

    print(f"Target: {FULL_URL}")

    # Create HTTP store -- no auth needed for CReSIS
    store = AiohttpStore(BASE_URL)
    registry = ObjectStoreRegistry({BASE_URL: store})

    print("Parsing .mat file with HDFParser...")
    # MATLAB v7.3 HDF5 files contain several groups that VirtualiZarr cannot
    # handle: `#refs#` and `#subsystem#` store MATLAB object references
    # (dtype=object, fillvalue=HDF5 Reference), which cause HDFParser to crash
    # on `dataset.fillvalue.item()`. The `param_*` groups also contain
    # MATLAB cell arrays stored as object-type datasets with reference fill
    # values. Drop them all -- they hold processing metadata, not radar data.
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
    parser = vz.parsers.HDFParser(drop_variables=MATLAB_INTERNAL_GROUPS)
    manifest_store = parser(FULL_URL, registry=registry)
    print("ManifestStore created!")

    # Print summary of what was found
    arrays = manifest_store._group.arrays
    print(f"\nVariables found: {list(arrays.keys())}")
    for name, array in arrays.items():
        print(
            f"  {name}: shape={array.shape}, dtype={array.dtype}, chunks={array.chunks}"
        )

    # Save manifest and metadata
    print(f"\nSaving manifest to {output_file}...")
    vzviz.save_manifest_to_json(
        manifest_store,
        output_file,
        metadata={
            "source_url": FULL_URL,
            "collection": "2022_Antarctica_BaslerMKB",
            "product": "CSARP_standard",
            "flight_id": "20230109_01",
            "frame": "001",
        },
    )

    print(f"Done! Manifest saved to {output_file}")


if __name__ == "__main__":
    main()
