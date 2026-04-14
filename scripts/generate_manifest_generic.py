#!/usr/bin/env python3
"""
Generate Kerchunk JSON manifests from HDF5 files with proper exception handling.

This script makes manifest generation generic by:
- Accepting a path (local directory, file, or URL) as input
- Wrapping parser exceptions to collect and report them
- Continuing manifest generation even when some variables fail to parse
- Supporting any HDF5 file format (MATLAB .mat, NetCDF4, etc.)

Usage:
    uv run scripts/generate_manifest_generic.py <path> [output_dir] [options]

Examples:
    # Generic HDF5 file
    uv run scripts/generate_manifest_generic.py /path/to/file.h5 ./data

    # MATLAB .mat file with preset
    uv run scripts/generate_manifest_generic.py /path/to/file.mat ./data --matlab

    # Process directory with custom pattern
    uv run scripts/generate_manifest_generic.py /path/to/files ./data --pattern "*.h5"

    # Drop specific variables
    uv run scripts/generate_manifest_generic.py /path/to/file.nc ./data --drop var1 --drop var2

    # HTTP URL
    uv run scripts/generate_manifest_generic.py https://example.com/file.h5 ./data
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
import traceback

import virtualizarr as vz
import virtualizarr.manifests as vzm
import vzviz

from obspec_utils.registry import ObjectStoreRegistry
from obspec_utils.stores import AiohttpStore


class ManifestGenerationError(Exception):
    """Raised when manifest generation encounters issues."""

    def __init__(
        self, errors: List[Tuple[str, str]], total_attempted: int, total_success: int
    ):
        self.errors = errors
        self.total_attempted = total_attempted
        self.total_success = total_success
        super().__init__(
            f"Failed to parse {len(errors)}/{total_attempted} variables "
            f"({total_success} successful)"
        )


class ManifestGenerator:
    """Generic manifest generator with exception collection."""

    def __init__(
        self,
        drop_variables: Optional[List[str]] = None,
        base_url: Optional[str] = None,
    ):
        self.drop_variables = drop_variables or []
        self.base_url = base_url
        self.parser = vz.parsers.HDFParser(drop_variables=self.drop_variables)
        self.errors: List[Tuple[str, str]] = []

    def generate_from_url(
        self,
        url: str,
        output_path: Optional[Path] = None,
        metadata: Optional[Dict] = None,
    ) -> vzm.ManifestStore:
        """Generate manifest from a single URL with error collection."""
        registry = self._create_registry(url)
        manifest_store, errors = self._parse_with_error_collection(url, registry)

        if errors:
            error_msg = "\n".join([f"  - {var}: {err}" for var, err in errors])
            raise ManifestGenerationError(
                errors,
                len(manifest_store._group.arrays) + len(errors),
                len(manifest_store._group.arrays),
            )

        if output_path:
            self._save_manifest(manifest_store, output_path, metadata or {})

        return manifest_store

    def generate_from_directory(
        self,
        directory: Path,
        output_dir: Path,
        pattern: str = "*.mat",
        metadata_template: Optional[Dict] = None,
    ) -> Dict[str, vzm.ManifestStore]:
        """Generate manifests from all files in a directory."""
        directory = Path(directory)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        files = sorted(directory.glob(pattern))
        if not files:
            raise ValueError(f"No files found matching '{pattern}' in {directory}")

        manifests = {}
        total_errors = 0

        for file_path in files:
            print(f"\nProcessing {file_path.name}...")
            try:
                output_file = output_dir / f"{file_path.stem}_manifest.json"
                metadata = self._generate_metadata(file_path, metadata_template)

                manifest_store, errors = self._parse_with_error_collection(
                    str(file_path), None
                )

                if errors:
                    total_errors += len(errors)
                    print(f"  ⚠ {len(errors)} variable(s) failed to parse")
                    for var, err in errors[:3]:
                        print(f"    - {var}: {err}")
                    if len(errors) > 3:
                        print(f"    ... and {len(errors) - 3} more")

                self._save_manifest(manifest_store, output_file, metadata)
                manifests[file_path.name] = manifest_store

                print(
                    f"  ✓ Generated manifest with {len(manifest_store._group.arrays)} variables"
                )

            except Exception as e:
                total_errors += 1
                print(f"  ✗ Failed: {e}")

        print(f"\n{'=' * 60}")
        print(f"Complete! Generated {len(manifests)}/{len(files)} manifests")
        if total_errors > 0:
            print(f"Total errors: {total_errors}")
        print(f"{'=' * 60}")

        return manifests

    def _create_registry(self, url: str) -> ObjectStoreRegistry:
        """Create appropriate registry based on URL scheme."""
        if url.startswith(("http://", "https://")):
            base_url = self.base_url or self._extract_base_url(url)
            store = AiohttpStore(base_url)
            return ObjectStoreRegistry({base_url: store})
        return None

    def _parse_with_error_collection(
        self,
        path: str,
        registry: Optional[ObjectStoreRegistry],
    ) -> Tuple[vzm.ManifestStore, List[Tuple[str, str]]]:
        """Parse file and collect exceptions for each variable."""
        errors: List[Tuple[str, str]] = []

        try:
            manifest_store = self.parser(path, registry=registry)

            arrays = manifest_store._group.arrays
            print(f"  Variables found: {list(arrays.keys())}")
            for name, array in arrays.items():
                try:
                    print(
                        f"    {name}: shape={array.shape}, dtype={array.dtype}, chunks={array.chunks}"
                    )
                except Exception as e:
                    errors.append((name, str(e)))

            return manifest_store, errors

        except Exception as e:
            tb = traceback.format_exc()
            errors.append(("MANIFEST_GENERATION", f"{e}\n{tb}"))
            raise

    def _save_manifest(
        self,
        manifest_store: vzm.ManifestStore,
        output_path: Path,
        metadata: Dict,
    ):
        """Save manifest to JSON file."""
        vzviz.save_manifest_to_json(manifest_store, output_path, metadata)
        print(f"  Saved to {output_path}")

    def _generate_metadata(
        self,
        file_path: Path,
        template: Optional[Dict],
    ) -> Dict:
        """Generate metadata for the manifest."""
        metadata = template.copy() if template else {}
        metadata.update(
            {
                "source_path": str(file_path),
                "filename": file_path.name,
            }
        )
        return metadata

    @staticmethod
    def _extract_base_url(url: str) -> str:
        """Extract base URL from full path."""
        from urllib.parse import urlparse

        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"


def main():
    import sys
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate Kerchunk JSON manifests from HDF5 files with exception handling"
    )
    parser.add_argument(
        "path", help="Path to file, directory, or URL to generate manifest(s) from"
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        default="data",
        help="Output directory for manifest files (default: data)",
    )
    parser.add_argument(
        "--drop",
        "-d",
        action="append",
        help="Variable names to drop (can be used multiple times)",
    )
    parser.add_argument(
        "--matlab",
        "-m",
        action="store_true",
        help="Use MATLAB v7.3 HDF5 preset (drops #refs#, #subsystem#, param_*, etc.)",
    )
    parser.add_argument(
        "--pattern",
        "-p",
        default="*",
        help="File pattern to match when processing directories (default: *)",
    )

    args = parser.parse_args()

    input_path = args.path
    output_dir = Path(args.output_dir)

    drop_variables = None
    if args.matlab:
        drop_variables = [
            "#refs#",
            "#subsystem#",
            "param_array",
            "param_records",
            "param_sar",
            "file_type",
            "file_version",
            "radiometric_corr_dB",
        ]
    elif args.drop:
        drop_variables = args.drop

    generator = ManifestGenerator(drop_variables=drop_variables)

    if input_path.startswith(("http://", "https://")):
        print(f"Generating manifest from URL: {input_path}")
        metadata = {
            "source_url": input_path,
            "collection": Path(input_path).parent.name,
        }
        try:
            generator.generate_from_url(
                input_path,
                output_dir / f"{Path(input_path).stem}_manifest.json",
                metadata,
            )
            print("✓ Manifest generated successfully!")
        except ManifestGenerationError as e:
            print(f"\n⚠ Manifest generated with errors:")
            print(f"  {e}")
            print(f"\nError details:")
            for var, err in e.errors:
                print(f"  - {var}: {err}")
        except Exception as e:
            print(f"✗ Failed to generate manifest: {e}")
            import traceback

            traceback.print_exc()

    else:
        path = Path(input_path)
        if not path.exists():
            print(f"✗ Path does not exist: {input_path}")
            sys.exit(1)

        if path.is_file():
            print(f"Generating manifest from file: {input_path}")
            metadata = {"source_path": str(path.absolute())}
            try:
                generator.generate_from_url(
                    str(path.absolute()),
                    output_dir / f"{path.stem}_manifest.json",
                    metadata,
                )
                print("✓ Manifest generated successfully!")
            except ManifestGenerationError as e:
                print(f"\n⚠ Manifest generated with errors:")
                print(f"  {e}")
                print(f"\nError details:")
                for var, err in e.errors:
                    print(f"  - {var}: {err}")
            except Exception as e:
                print(f"✗ Failed to generate manifest: {e}")
                import traceback

                traceback.print_exc()

        elif path.is_dir():
            print(f"Generating manifests from directory: {input_path}")
            generator.generate_from_directory(
                path,
                output_dir,
                pattern=args.pattern,
                metadata_template={"source_directory": str(path.absolute())},
            )


if __name__ == "__main__":
    main()
