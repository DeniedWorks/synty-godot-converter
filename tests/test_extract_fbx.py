"""Tests for extracting FBX straight out of a .unitypackage.

A pack whose meshes were never imported into Unity has no --source-files to
point at, even though its FBX are sitting inside the .unitypackage. Extracting
them makes such a pack convertible without Unity in the loop at all.
"""

import io
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unity_package import extract_fbx_to_directory  # noqa: E402

GUID_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
GUID_B = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
GUID_C = "cccccccccccccccccccccccccccccccc"


def _package(tmp_path, entries, name="pack.unitypackage"):
    """Build a .unitypackage: a gzipped tar of GUID folders.

    Args:
        entries: GUID to (pathname, asset bytes or None) - None omits the
            asset file, as Unity does for folder entries.
    """
    path = tmp_path / name
    with tarfile.open(path, "w:gz") as tar:
        for guid, (pathname, payload) in entries.items():
            for filename, data in (
                ("pathname", pathname.encode("utf-8")),
                ("asset", payload),
            ):
                if data is None:
                    continue
                info = tarfile.TarInfo(f"{guid}/{filename}")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    return path


class TestExtractFbxToDirectory:
    def test_writes_fbx_at_its_project_path(self, tmp_path):
        package = _package(tmp_path, {
            GUID_A: ("Assets/Synty/Meshes/SK_HEAD_01.fbx", b"fbx-bytes"),
        })
        out = tmp_path / "out"
        assert extract_fbx_to_directory(package, out) == 1
        written = out / "Assets/Synty/Meshes/SK_HEAD_01.fbx"
        assert written.read_bytes() == b"fbx-bytes"

    def test_ignores_non_fbx_assets(self, tmp_path):
        package = _package(tmp_path, {
            GUID_A: ("Assets/M.mat", b"mat"),
            GUID_B: ("Assets/T.png", b"png"),
            GUID_C: ("Assets/Meshes/A.fbx", b"fbx"),
        })
        out = tmp_path / "out"
        assert extract_fbx_to_directory(package, out) == 1
        assert [p.name for p in out.rglob("*") if p.is_file()] == ["A.fbx"]

    def test_matches_extension_case_insensitively(self, tmp_path):
        package = _package(tmp_path, {GUID_A: ("Assets/A.FBX", b"fbx")})
        out = tmp_path / "out"
        assert extract_fbx_to_directory(package, out) == 1

    def test_skips_entry_with_no_asset_payload(self, tmp_path):
        """Folder entries carry a pathname but no asset."""
        package = _package(tmp_path, {GUID_A: ("Assets/Meshes/A.fbx", None)})
        assert extract_fbx_to_directory(package, tmp_path / "out") == 0

    def test_empty_package_writes_nothing(self, tmp_path):
        package = _package(tmp_path, {})
        out = tmp_path / "out"
        assert extract_fbx_to_directory(package, out) == 0

    def test_creates_output_directory(self, tmp_path):
        package = _package(tmp_path, {GUID_A: ("Assets/A.fbx", b"fbx")})
        out = tmp_path / "deep" / "nested"
        extract_fbx_to_directory(package, out)
        assert out.is_dir()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
