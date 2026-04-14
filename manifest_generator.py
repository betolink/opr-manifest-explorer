"""
Generic manifest generator with exception handling.

This module provides a programmatic interface for generating manifests
from files with automatic error collection and reporting.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
        """
        Initialize the manifest generator.

        Args:
            drop_variables: List of variable names to skip during parsing
            base_url: Base URL for HTTP stores (auto-detected if not provided)
        """
        self.drop_variables = drop_variables or []
        self.base_url = base_url
        self.parser = vz.parsers.HDFParser(drop_variables=self.drop_variables)

    def generate(
        self,
        path: str,
        output_path: Optional[Path] = None,
        metadata: Optional[Dict] = None,
    ) -> vzm.ManifestStore:
        """
        Generate manifest from a file path or URL.

        Args:
            path: File path or URL to parse
            output_path: Optional path to save the manifest JSON
            metadata: Optional metadata dict to include in the manifest

        Returns:
            ManifestStore containing the parsed variables

        Raises:
            ManifestGenerationError: If any variables fail to parse
        """
        registry = self._create_registry(path)
        manifest_store = self.parser(path, registry=registry)

        if output_path:
            self._save_manifest(manifest_store, output_path, metadata or {})

        return manifest_store

    def _create_registry(self, url: str) -> Optional[ObjectStoreRegistry]:
        """Create appropriate registry based on URL scheme."""
        if url.startswith(("http://", "https://")):
            base_url = self.base_url or self._extract_base_url(url)
            store = AiohttpStore(base_url)
            return ObjectStoreRegistry({base_url: store})
        return None

    def _save_manifest(
        self,
        manifest_store: vzm.ManifestStore,
        output_path: Path,
        metadata: Dict,
    ):
        """Save manifest to JSON file."""
        vzviz.save_manifest_to_json(manifest_store, output_path, metadata)

    @staticmethod
    def _extract_base_url(url: str) -> str:
        """Extract base URL from full path."""
        from urllib.parse import urlparse

        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
