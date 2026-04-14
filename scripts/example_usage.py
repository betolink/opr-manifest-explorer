#!/usr/bin/env python3
"""
Example: Generate manifests from generic HDF5 files.

This script demonstrates using the manifest generator with various HDF5 file types.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from manifest_generator import ManifestGenerator


def example_generic_hdf5():
    """Example: Generate manifest from a generic HDF5 file."""
    generator = ManifestGenerator(drop_variables=None)

    print("Example: Generic HDF5 file")
    print("=" * 60)
    print("\nUsage:")
    print("  generator = ManifestGenerator(drop_variables=None)")
    print("  manifest_store = generator.generate(")
    print("      path='/path/to/file.h5',")
    print("      output_path=Path('output/manifest.json'),")
    print("      metadata={'source': 'HDF5 data'}")
    print("  )")
    print("\nThis will process all variables in the HDF5 file.")


def example_matlab_file():
    """Example: Generate manifest from a MATLAB .mat file."""
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

    print("\nExample: MATLAB .mat file")
    print("=" * 60)
    print("\nUsage:")
    print("  generator = ManifestGenerator(")
    print("      drop_variables=['#refs#', '#subsystem#', 'param_*', ...]")
    print("  )")
    print("  manifest_store = generator.generate(")
    print("      path='/path/to/file.mat',")
    print("      output_path=Path('output/manifest.json')")
    print("  )")
    print("\nThis will skip MATLAB-specific internal groups.")


def example_netcdf4_file():
    """Example: Generate manifest from a NetCDF4 file."""
    generator = ManifestGenerator(drop_variables=None)

    print("\nExample: NetCDF4 file")
    print("=" * 60)
    print("\nUsage:")
    print("  generator = ManifestGenerator(drop_variables=None)")
    print("  manifest_store = generator.generate(")
    print("      path='/path/to/file.nc',")
    print("      output_path=Path('output/manifest.json')")
    print("  )")
    print("\nNetCDF4 files are HDF5-based and can be processed directly.")


def example_with_error_handling():
    """Example: Handle exceptions during generation."""
    print("\nExample: Exception handling")
    print("=" * 60)
    print("\nUsage:")
    print("  from manifest_generator import ManifestGenerationError")
    print("\n  try:")
    print("      manifest_store = generator.generate(")
    print("          path='/path/to/file.h5',")
    print("          output_path=Path('output/manifest.json')")
    print("      )")
    print("  except ManifestGenerationError as e:")
    print("      print(f'Failed variables: {len(e.errors)}')")
    print("      for var, error in e.errors:")
    print("          print(f'  {var}: {error}')")


def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("Manifest Generator Examples")
    print("=" * 60)

    example_generic_hdf5()
    example_matlab_file()
    example_netcdf4_file()
    example_with_error_handling()

    print("\n" + "=" * 60)
    print("Command Line Examples")
    print("=" * 60)
    print("\n# Generic HDF5 file")
    print("uv run scripts/generate_manifest_generic.py file.h5 ./data")
    print("\n# MATLAB file with preset")
    print("uv run scripts/generate_manifest_generic.py file.mat ./data --matlab")
    print("\n# NetCDF4 file")
    print("uv run scripts/generate_manifest_generic.py file.nc ./data")
    print("\n# Directory with pattern")
    print(
        "uv run scripts/generate_manifest_generic.py /path/to/files ./data --pattern '*.h5'"
    )
    print("\n# Drop specific variables")
    print(
        "uv run scripts/generate_manifest_generic.py file.h5 ./data --drop var1 --drop var2"
    )

    print("\n" + "=" * 60)
    print("For complete documentation, see:")
    print("  MANIFEST_GENERATOR_USAGE.md")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
