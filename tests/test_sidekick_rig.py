"""Tests for Sidekick's blend-shape-driven joint adjustments.

Changing a character's proportions reshapes the body mesh, but the attachment
joints - where pouches, shoulder pads and back items hang - do not follow on
their own. Synty stores per-joint offsets in its tool database and applies them
as body size changes. Without them, gear floats off a heavy character or sinks
into a skinny one.
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sidekick import (  # noqa: E402
    SIDEKICK_DATABASE_NAME,
    find_sidekick_database,
    load_rig_adjustments,
    write_sidekick_rig_adjustments_json,
)

# part_type 27/28 are AttachmentHipsLeft/Right, blend_type 1 is Heavy.
ROWS = [
    (27, 1, 0.0, 0.0, 0.130, 0.0, 0.0, 0.0),
    (28, 1, 0.0, 0.0, -0.130, 0.0, 0.0, 0.0),
    (24, 3, -0.04, 0.04, 0.0, 356.0, 0.0, 0.0),
    (99, 0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0),
]


def _database(tmp_path, rows=ROWS, name=SIDEKICK_DATABASE_NAME):
    path = tmp_path / "Database" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE sk_blend_shape_rig_movement ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, part_type INTEGER, "
        "blend_type INTEGER, max_offset_x REAL, max_offset_y REAL, "
        "max_offset_z REAL, max_rotation_x REAL, max_rotation_y REAL, "
        "max_rotation_z REAL, max_scale_x REAL, max_scale_y REAL, "
        "max_scale_z REAL)"
    )
    connection.executemany(
        "INSERT INTO sk_blend_shape_rig_movement (part_type, blend_type, "
        "max_offset_x, max_offset_y, max_offset_z, max_rotation_x, "
        "max_rotation_y, max_rotation_z) VALUES (?,?,?,?,?,?,?,?)",
        rows,
    )
    connection.commit()
    connection.close()
    return path


class TestFindSidekickDatabase:
    def test_finds_database_under_source_dir(self, tmp_path):
        expected = _database(tmp_path)
        assert find_sidekick_database([tmp_path]) == expected

    def test_returns_none_when_absent(self, tmp_path):
        assert find_sidekick_database([tmp_path]) is None

    def test_ignores_missing_directory(self, tmp_path):
        assert find_sidekick_database([tmp_path / "nope"]) is None

    def test_searches_every_source_dir(self, tmp_path):
        (tmp_path / "empty").mkdir()
        expected = _database(tmp_path / "real")
        assert find_sidekick_database([tmp_path / "empty", tmp_path / "real"]) == expected


class TestLoadRigAdjustments:
    def test_maps_part_type_to_joint_and_blend_name(self, tmp_path):
        adjustments = load_rig_adjustments(_database(tmp_path))
        assert adjustments["hipAttach_l"]["heavy"]["offset"] == [0.0, 0.0, 0.130]
        assert adjustments["hipAttach_r"]["heavy"]["offset"] == [0.0, 0.0, -0.130]

    def test_normalises_angles_to_signed_range(self, tmp_path):
        """356 degrees is -4, and a quaternion must not take the long way."""
        adjustments = load_rig_adjustments(_database(tmp_path))
        assert adjustments["backAttach"]["bulk"]["rotation"] == [-4.0, 0.0, 0.0]

    def test_keeps_offsets_alongside_rotation(self, tmp_path):
        adjustments = load_rig_adjustments(_database(tmp_path))
        assert adjustments["backAttach"]["bulk"]["offset"] == [-0.04, 0.04, 0.0]

    def test_ignores_unknown_part_types(self, tmp_path):
        """Only the 11 attachment joints are adjusted; anything else is noise."""
        adjustments = load_rig_adjustments(_database(tmp_path))
        assert all(not key.startswith("99") for key in adjustments)
        assert set(adjustments) == {"hipAttach_l", "hipAttach_r", "backAttach"}

    def test_missing_table_yields_nothing(self, tmp_path):
        path = tmp_path / "empty.db"
        sqlite3.connect(path).close()
        assert load_rig_adjustments(path) == {}

    def test_unreadable_file_yields_nothing(self, tmp_path):
        path = tmp_path / "not.db"
        path.write_text("definitely not sqlite", encoding="utf-8")
        assert load_rig_adjustments(path) == {}

    def test_zero_rows_only_for_joints_present(self, tmp_path):
        """A joint with no row must be absent rather than zero-filled."""
        adjustments = load_rig_adjustments(_database(tmp_path))
        assert "kneeAttach_l" not in adjustments
        assert set(adjustments["hipAttach_l"]) == {"heavy"}


class TestWriteRigAdjustmentsJson:
    def test_writes_expected_shape(self, tmp_path):
        adjustments = load_rig_adjustments(_database(tmp_path))
        out = tmp_path / "sidekick_rig_adjustments.json"
        write_sidekick_rig_adjustments_json(adjustments, out)
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["hipAttach_r"]["heavy"] == {
            "offset": [0.0, 0.0, -0.130],
            "rotation": [0.0, 0.0, 0.0],
        }

    def test_creates_parent_directory(self, tmp_path):
        out = tmp_path / "deep" / "sidekick_rig_adjustments.json"
        write_sidekick_rig_adjustments_json({}, out)
        assert out.exists()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
