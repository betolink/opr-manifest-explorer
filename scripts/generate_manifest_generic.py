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
from typing import Dict, List, Optional, Tuple, Sequence
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import traceback

import virtualizarr as vz
import virtualizarr.manifests as vzm
import vzviz

from obspec import GetResult, GetResultAsync, ObjectMeta
from obspec_utils.registry import ObjectStoreRegistry
from obspec_utils.stores import AiohttpStore
from obspec_utils.protocols import ReadableStore


@dataclass
class FileStoreGetResult(GetResult):
    _data: bytes
    _meta: ObjectMeta
    _attributes: Dict = field(default_factory=dict)
    _range: Tuple[int, int] = (0, 0)

    def __post_init__(self):
        if self._range == (0, 0):
            self._range = (0, len(self._data))

    @property
    def attributes(self) -> Dict:
        return self._attributes

    def buffer(self) -> bytes:
        return self._data

    @property
    def meta(self) -> ObjectMeta:
        return self._meta

    @property
    def range(self) -> Tuple[int, int]:
        return self._range

    def __iter__(self) -> Iterator[bytes]:
        yield self._data


@dataclass
class FileStoreGetResultAsync(GetResultAsync):
    _data: bytes
    _meta: ObjectMeta
    _attributes: Dict = field(default_factory=dict)
    _range: Tuple[int, int] = (0, 0)

    def __post_init__(self):
        if self._range == (0, 0):
            self._range = (0, len(self._data))

    @property
    def attributes(self) -> Dict:
        return self._attributes

    async def buffer_async(self) -> bytes:
        return self._data

    @property
    def meta(self) -> ObjectMeta:
        return self._meta

    @property
    def range(self) -> Tuple[int, int]:
        return self._range

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._data


class FileStore(ReadableStore):
    def __init__(self, base_path: str):
        self.base_path = Path(base_path.replace("file://", "")).resolve()

    def _resolve_path(self, path: str) -> Path:
        path = path.replace("file://", "")
        p = Path(path)
        if p.is_absolute():
            return p.resolve()
        # Registry may have stripped leading / from path
        if str(path).startswith(str(self.base_path).lstrip("/")):
            return Path(f"/{path}").resolve()
        return (self.base_path / path).resolve()

    def get(self, path: str, *, options=None) -> FileStoreGetResult:
        full_path = self._resolve_path(path)
        stat = full_path.stat()
        meta = {
            "path": path,
            "last_modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            "size": stat.st_size,
            "e_tag": None,
            "version": None,
        }
        return FileStoreGetResult(_data=full_path.read_bytes(), _meta=meta)

    async def get_async(self, path: str, *, options=None) -> FileStoreGetResultAsync:
        result = self.get(path, options=options)
        return FileStoreGetResultAsync(
            _data=result._data,
            _meta=result._meta,
            _attributes=result._attributes,
            _range=result._range,
        )

    def get_range(
        self,
        path: str,
        *,
        start: int,
        end: Optional[int] = None,
        length: Optional[int] = None,
    ) -> bytes:
        if end is None and length is None:
            raise ValueError("Either 'end' or 'length' must be provided")
        if end is None:
            end = start + length
        full_path = self._resolve_path(path)
        with open(full_path, "rb") as f:
            f.seek(start)
            return f.read(end - start)

    async def get_range_async(
        self,
        path: str,
        *,
        start: int,
        end: Optional[int] = None,
        length: Optional[int] = None,
    ) -> bytes:
        return self.get_range(path, start=start, end=end, length=length)

    def get_ranges(
        self,
        path: str,
        *,
        starts: Sequence[int],
        ends: Optional[Sequence[int]] = None,
        lengths: Optional[Sequence[int]] = None,
    ) -> Sequence[bytes]:
        if ends is None and lengths is None:
            raise ValueError("Either 'ends' or 'lengths' must be provided")
        if ends is None:
            ends = [s + ln for s, ln in zip(starts, lengths)]
        return [self.get_range(path, start=s, end=e) for s, e in zip(starts, ends)]

    async def get_ranges_async(
        self,
        path: str,
        *,
        starts: Sequence[int],
        ends: Optional[Sequence[int]] = None,
        lengths: Optional[Sequence[int]] = None,
    ) -> Sequence[bytes]:
        return self.get_ranges(path, starts=starts, ends=ends, lengths=lengths)

    def head(self, path: str) -> ObjectMeta:
        full_path = self._resolve_path(path)
        stat = full_path.stat()
        return {
            "path": path,
            "last_modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            "size": stat.st_size,
            "e_tag": None,
            "version": None,
        }

    async def head_async(self, path: str) -> ObjectMeta:
        return self.head(path)

    async def head_async(self, path: str) -> ObjectMeta:
        return self._get_meta(path)

    async def head_async(self, path: str) -> ObjectMeta:
        return self._get_meta(path)


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
        group: Optional[str] = None,
    ):
        self.drop_variables = drop_variables or []
        self.base_url = base_url
        self.group = group
        self.parser = vz.parsers.HDFParser(
            group=self.group, drop_variables=self.drop_variables
        )
        self.errors: List[Tuple[str, str]] = []

    def generate_from_url(
        self,
        url: str,
        output_path: Optional[Path] = None,
        metadata: Optional[Dict] = None,
    ) -> vzm.ManifestStore:
        """Generate manifest from a single URL with error collection."""
        registry, file_url = self._create_registry(url)
        manifest_store, errors = self._parse_with_error_collection(file_url, registry)

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

                registry, file_url = self._create_registry(str(file_path))
                manifest_store, errors = self._parse_with_error_collection(
                    file_url, registry
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

    def _create_registry(self, url: str) -> Tuple[ObjectStoreRegistry, str]:
        if url.startswith(("http://", "https://")):
            base_url = self.base_url or self._extract_base_url(url)
            store = AiohttpStore(base_url)
            return ObjectStoreRegistry({base_url: store}), url
        p = Path(url).resolve()
        base_path = str(p.parent)
        file_url = f"file://{p}"
        return ObjectStoreRegistry({"file://": FileStore(base_path)}), file_url

    def _parse_with_error_collection(
        self,
        path: str,
        registry: ObjectStoreRegistry,
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
    def dry_run(file_path: str) -> None:
        """Print groups and variables in an HDF5 file without writing output."""
        import h5py

        def _print_group(group: h5py.Group, prefix: str = ""):
            items = sorted(
                group.items(), key=lambda x: (not isinstance(x[1], h5py.Group), x[0])
            )
            for i, (name, obj) in enumerate(items):
                last = i == len(items) - 1
                connector = "└── " if last else "├── "
                if isinstance(obj, h5py.Group):
                    ds_count = sum(1 for k in obj if isinstance(obj[k], h5py.Dataset))
                    sub_count = sum(1 for k in obj if isinstance(obj[k], h5py.Group))
                    label = name + "/"
                    if ds_count:
                        label += f"  ({ds_count} vars"
                        if sub_count:
                            label += f", {sub_count} subgroups"
                        label += ")"
                    elif sub_count:
                        label += f"  ({sub_count} subgroups)"
                    print(f"{prefix}{connector}{label}")
                    extension = "    " if last else "│   "
                    _print_group(obj, prefix + extension)
                else:
                    print(
                        f"{prefix}{connector}{name}: shape={obj.shape}, dtype={obj.dtype}"
                    )

        with h5py.File(file_path, "r") as f:
            root_items = sorted(
                f.items(), key=lambda x: (not isinstance(x[1], h5py.Group), x[0])
            )
            for name, obj in root_items:
                if isinstance(obj, h5py.Group):
                    ds_count = sum(1 for k in obj if isinstance(obj[k], h5py.Dataset))
                    sub_count = sum(1 for k in obj if isinstance(obj[k], h5py.Group))
                    label = f"/{name}"
                    if ds_count:
                        label += f"  ({ds_count} vars"
                        if sub_count:
                            label += f", {sub_count} subgroups"
                        label += ")"
                    elif sub_count:
                        label += f"  ({sub_count} subgroups)"
                    print(label)
                    _print_group(obj, "")
                else:
                    print(f"/{name}: shape={obj.shape}, dtype={obj.dtype}")

            print("\n--- Suggested --group values ---")
            suggested = []

            def _collect(name, obj):
                if isinstance(obj, h5py.Group):
                    if any(isinstance(obj[k], h5py.Dataset) for k in obj):
                        suggested.append(name)

            f.visititems(_collect)
            for s in sorted(suggested):
                print(f"  --group=/{s}")

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
    parser.add_argument(
        "--group",
        "-g",
        default=None,
        help="HDF5 group path to open (e.g. /gt1l/freeboard_segment). Use --dry-run to discover groups.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List groups and variables in the file without generating a manifest.",
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

    generator = ManifestGenerator(drop_variables=drop_variables, group=args.group)

    if args.dry_run:
        if input_path.startswith(("http://", "https://")):
            print("--dry-run is not supported for URLs")
            sys.exit(1)
        path = Path(input_path)
        if not path.is_file():
            print(f"--dry-run requires a single file, got: {input_path}")
            sys.exit(1)
        ManifestGenerator.dry_run(str(path))
        sys.exit(0)

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
