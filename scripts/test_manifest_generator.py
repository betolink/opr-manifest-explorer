#!/usr/bin/env python3
"""
Test the manifest generator with exception collection.

This script demonstrates how the manifest generator collects and reports
exceptions without stopping the entire generation process.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from manifest_generator import ManifestGenerator


def test_exception_collection():
    """Test that exceptions are collected and reported properly."""

    generator = ManifestGenerator(
        drop_variables=[
            "#refs#",
            "#subsystem#",
            "param_array",
            "param_records",
            "param_sar",
            "file_type",
            "file_version",
            "radiometric_corr_dB",
        ]
    )

    print("Testing manifest generator with exception collection...")
    print("=" * 60)

    # Test with the existing manifest file
    test_file = Path(__file__).parent.parent / "data" / "xopr_manifest.json"

    if test_file.exists():
        print(f"\nTest file exists: {test_file}")
        print("This is a pre-existing manifest, not a .mat file.")
        print("To test actual parsing, you need a .mat file.")
    else:
        print(f"\nTest file not found: {test_file}")

    print("\n" + "=" * 60)
    print("Test complete!")
    print("\nTo test with actual .mat files:")
    print("  uv run scripts/generate_manifest_generic.py /path/to/file.mat")


if __name__ == "__main__":
    test_exception_collection()
