"""Tests for the per-pack metadata stamp that drives incremental re-runs.

An existing pack skips straight to mesh generation, which is what makes
re-running cheap. The cost is that metadata the converter learned to emit
later - new fields, new files - never appears for packs converted by an
earlier version. The stamp records which schema a pack's metadata was
written against so a stale pack refreshes itself.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from converter import (  # noqa: E402
    PACK_METADATA_FILENAME,
    PACK_METADATA_VERSION,
    detect_existing_pack,
    pack_metadata_is_current,
    write_pack_metadata,
)


def _populated_pack(tmp_path):
    """A pack folder carrying every asset prerequisite."""
    (tmp_path / "materials").mkdir()
    (tmp_path / "materials" / "M.tres").write_text("x", encoding="utf-8")
    (tmp_path / "textures").mkdir()
    (tmp_path / "textures" / "T.png").write_bytes(b"x")
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "A.fbx").write_bytes(b"x")
    (tmp_path / "mesh_material_mapping.json").write_text("{}", encoding="utf-8")
    return tmp_path


class TestWritePackMetadata:
    def test_writes_current_version(self, tmp_path):
        write_pack_metadata(tmp_path)
        payload = json.loads(
            (tmp_path / PACK_METADATA_FILENAME).read_text(encoding="utf-8")
        )
        assert payload["schema_version"] == PACK_METADATA_VERSION

    def test_round_trips_as_current(self, tmp_path):
        write_pack_metadata(tmp_path)
        assert pack_metadata_is_current(tmp_path) is True


class TestPackMetadataIsCurrent:
    def test_absent_file_is_stale(self, tmp_path):
        """Packs converted before the stamp existed must refresh once."""
        assert pack_metadata_is_current(tmp_path) is False

    def test_older_version_is_stale(self, tmp_path):
        (tmp_path / PACK_METADATA_FILENAME).write_text(
            json.dumps({"schema_version": PACK_METADATA_VERSION - 1}),
            encoding="utf-8",
        )
        assert pack_metadata_is_current(tmp_path) is False

    def test_newer_version_is_not_stale(self, tmp_path):
        """A pack written by a newer converter is left alone."""
        (tmp_path / PACK_METADATA_FILENAME).write_text(
            json.dumps({"schema_version": PACK_METADATA_VERSION + 1}),
            encoding="utf-8",
        )
        assert pack_metadata_is_current(tmp_path) is True

    def test_corrupt_file_is_stale(self, tmp_path):
        (tmp_path / PACK_METADATA_FILENAME).write_text("not json", encoding="utf-8")
        assert pack_metadata_is_current(tmp_path) is False

    def test_missing_version_key_is_stale(self, tmp_path):
        (tmp_path / PACK_METADATA_FILENAME).write_text("{}", encoding="utf-8")
        assert pack_metadata_is_current(tmp_path) is False


class TestDetectExistingPack:
    def test_reports_metadata_state(self, tmp_path):
        pack = _populated_pack(tmp_path)
        assert detect_existing_pack(pack)["has_current_metadata"] is False
        write_pack_metadata(pack)
        assert detect_existing_pack(pack)["has_current_metadata"] is True

    def test_stamped_pack_skips_everything(self, tmp_path):
        pack = _populated_pack(tmp_path)
        write_pack_metadata(pack)
        assert all(detect_existing_pack(pack).values())

    def test_unstamped_pack_does_not_skip(self, tmp_path):
        """Assets are all present, but the stamp is stale - so step 10 re-runs."""
        state = detect_existing_pack(_populated_pack(tmp_path))
        assert not all(state.values())
        assert state["has_materials"] and state["has_models"]

    def test_empty_pack_reports_nothing_present(self, tmp_path):
        assert not any(detect_existing_pack(tmp_path).values())


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
