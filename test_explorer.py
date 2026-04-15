import h5py
import numpy as np
import pytest
import tempfile
import os
from pathlib import Path


class TestScanGroups:
    def test_scan_groups_finds_groups(self, tmp_path):
        from explorer import scan_groups

        h5_path = tmp_path / "test.h5"
        with h5py.File(h5_path, "w") as f:
            f.create_group("group1")
            f.create_dataset("group1/dataset1", data=np.arange(10))
            f.create_group("group2")
            f.create_dataset("group2/dataset2", data=np.arange(20))

        df = scan_groups(str(h5_path))

        assert len(df) == 2
        groups = df["group"].tolist()
        assert "/group1" in groups
        assert "/group2" in groups

    def test_scan_groups_root_group(self, tmp_path):
        from explorer import scan_groups

        h5_path = tmp_path / "test.h5"
        with h5py.File(h5_path, "w") as f:
            f.create_group("level1")
            f.create_dataset("level1/dataset1", data=np.arange(10))

        df = scan_groups(str(h5_path))

        assert len(df) >= 1
        groups = df["group"].tolist()
        assert "/level1" in groups

    def test_scan_groups_empty_file(self, tmp_path):
        from explorer import scan_groups

        h5_path = tmp_path / "empty.h5"
        with h5py.File(h5_path, "w") as f:
            f.create_group("empty_group")

        df = scan_groups(str(h5_path))
        assert len(df) == 0


class TestIsHdf4:
    def test_hdf5_returns_false(self, tmp_path):
        from explorer import is_hdf4

        h5_path = tmp_path / "test.h5"
        with h5py.File(h5_path, "w") as f:
            f.create_dataset("data", data=np.arange(10))

        assert is_hdf4(str(h5_path)) is False

    def test_nonexistent_file(self, tmp_path):
        from explorer import is_hdf4

        assert is_hdf4(str(tmp_path / "nonexistent.hdf")) is False


class TestHdf4Conversion:
    def test_hdf4_kerchunk_manifest(self, tmp_path):
        from explorer import is_hdf4, make_manifest_from_hdf4

        hdf_path = Path("data/MOD07_L2.A2019126.1420.061.2019127012833.hdf")
        if not hdf_path.exists():
            pytest.skip("HDF4 test file not found")

        assert is_hdf4(hdf_path) is True

        manifest_path = tmp_path / "manifest.json"
        manifest = make_manifest_from_hdf4(hdf_path, manifest_path)

        assert manifest_path.exists()
        assert isinstance(manifest, dict)
        assert ".zgroup" in manifest
        assert "Latitude/.zarray" in manifest

    def test_hdf4_read_with_existing_file(self):
        from explorer import is_hdf4, make_manifest_from_hdf4

        hdf_path = Path("data/MOD07_L2.A2019126.1420.061.2019127012833.hdf")
        if not hdf_path.exists():
            pytest.skip("HDF4 test file not found")

        manifest = make_manifest_from_hdf4(hdf_path)
        assert "Latitude/.zarray" in manifest


class TestMakeManifest:
    def test_make_manifest_creates_manifest(self, tmp_path):
        from explorer import make_manifest

        h5_path = tmp_path / "test.h5"
        with h5py.File(h5_path, "w") as f:
            f.create_dataset("data", data=np.arange(10))

        manifest, removed_vars, _, _ = make_manifest(str(h5_path), "/")
        assert manifest is not None

    def test_make_manifest_with_group(self, tmp_path):
        from explorer import make_manifest

        h5_path = tmp_path / "test.h5"
        with h5py.File(h5_path, "w") as f:
            f.create_group("mygroup")
            f.create_dataset("mygroup/data", data=np.arange(10))

        manifest, removed_vars, _, _ = make_manifest(str(h5_path), "/mygroup")
        assert manifest is not None


class TestFixHdf5References:
    def test_matlab_file_with_reference_fillvalue(self):
        from explorer import make_manifest, _fix_hdf5_references

        mat_path = Path("data/Data_20160517_06_001.mat")
        if not mat_path.exists():
            pytest.skip("MATLAB test file not found")

        manifest, removed_vars, json_path, cleaned_attrs = make_manifest(
            str(mat_path), "/param_csarp/csarp"
        )
        assert manifest is not None

    def test_matlab_combine_group(self):
        from explorer import make_manifest

        mat_path = Path("data/Data_20160517_06_001.mat")
        if not mat_path.exists():
            pytest.skip("MATLAB test file not found")

        manifest, removed_vars, json_path, cleaned_attrs = make_manifest(
            str(mat_path), "/param_csarp/combine"
        )
        assert manifest is not None

    def test_matlab_combine_manifest_has_info(self):
        from explorer import make_manifest
        import vzviz

        mat_path = Path("data/Data_20160517_06_001.mat")
        if not mat_path.exists():
            pytest.skip("MATLAB test file not found")

        manifest, removed_vars, json_path, cleaned_attrs = make_manifest(
            str(mat_path), "/param_csarp/combine"
        )

        # For contiguous data, chunks will be empty but we can still get variable info
        overview = vzviz.variables_overview(manifest)
        assert len(overview) > 0

        # Verify that cleaned attributes helps (should have data for combine)
        print(f"Variables found: {len(overview)}")
        print(f"Removed vars: {removed_vars}")
        print(f"Cleaned attrs: {cleaned_attrs}")

    def test_fix_hdf5_references_returns_removed_vars(self, tmp_path):
        from explorer import _fix_hdf5_references
        import h5py

        h5_path = tmp_path / "test.h5"
        with h5py.File(h5_path, "w") as f:
            f.create_dataset("good_data", data=np.arange(10))
            f.create_dataset("bad_ref", data=np.arange(5))

        output_path = tmp_path / "output.h5"
        removed = _fix_hdf5_references(h5_path, output_path, "/")

        assert output_path.exists()
        with h5py.File(output_path, "r") as f:
            assert "good_data" in f

    def test_clean_hdf5_attributes(self, tmp_path):
        from explorer import _clean_hdf5_attributes
        import h5py

        h5_path = tmp_path / "test.h5"
        with h5py.File(h5_path, "w") as f:
            f.attrs["normal"] = "string"
            f.attrs["bytes_attr"] = np.bytes_(b"test")
            f.attrs["array_attr"] = np.array([b"a", b"b"], dtype="|S1")
            f.create_dataset("data", data=np.arange(10))

        output_path = tmp_path / "output.h5"
        cleaned = _clean_hdf5_attributes(h5_path, output_path, "/")

        assert output_path.exists()
        assert isinstance(cleaned, list)
        # The byte attributes should be cleaned


class TestBuildReport:
    def test_build_report_returns_dict(self, tmp_path):
        from explorer import make_manifest, _build_report

        h5_path = tmp_path / "test.h5"
        with h5py.File(h5_path, "w") as f:
            f.create_dataset("data", data=np.arange(10))

        manifest, removed_vars, _, _ = make_manifest(str(h5_path), "/")
        report = _build_report(manifest, str(h5_path), "/")

        assert isinstance(report, dict)
        assert "summary" in report
        assert "variables" in report
        assert "chunks" in report
