"""Godot resource UIDs for generated .tres files.

Without a uid in its header a generated resource has no UID at all: Godot does
not assign one on import, only when the editor re-saves the file. Anything
addressing resources by uid:// - the editor's quick-open among them - cannot
see them.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tres_generator import generate_tres, uid_for_path  # noqa: E402


def godot_text_to_id(text: str) -> int:
    """Godot's own ResourceUID::text_to_id, to check what we emit decodes back.

    Base 34, with 'a'-'z' as 0-25 and '0'-'9' continuing from 25 - so 'z' and
    '0' both decode to 25. Derived from the engine rather than assumed.
    """
    assert text.startswith("uid://")
    value = 0
    for char in text[len("uid://"):]:
        value *= 34
        if "a" <= char <= "z":
            value += ord(char) - ord("a")
        elif "0" <= char <= "9":
            value += ord(char) - ord("0") + 25
        else:
            raise AssertionError(f"invalid UID character {char!r}")
    return value


class TestUidForPath:
    def test_is_deterministic_so_rerunning_keeps_references_valid(self):
        first = uid_for_path("res://POLYGON_Dungeon/materials/Dungeon_01.tres")
        second = uid_for_path("res://POLYGON_Dungeon/materials/Dungeon_01.tres")
        assert first == second

    def test_different_paths_get_different_uids(self):
        paths = [
            "res://POLYGON_Dungeon/materials/Dungeon_01.tres",
            "res://POLYGON_Dungeon/materials/Dungeon_02.tres",
            "res://POLYGON_Vikings/materials/Dungeon_01.tres",
        ]
        assert len({uid_for_path(p) for p in paths}) == len(paths)

    def test_a_whole_library_of_paths_stays_collision_free(self):
        """A real conversion writes tens of thousands of resources."""
        paths = [
            f"res://PACK_{pack}/materials/Material_{index}.tres"
            for pack in range(40)
            for index in range(500)
        ]
        assert len({uid_for_path(p) for p in paths}) == len(paths)

    def test_godot_can_decode_what_we_emit(self):
        text = uid_for_path("res://POLYGON_Dungeon/materials/Dungeon_01.tres")
        assert text.startswith("uid://")
        # Round-trips, and stays inside the positive range Godot masks to.
        value = godot_text_to_id(text)
        assert 0 < value < 2 ** 63

    def test_uses_only_characters_godot_accepts(self):
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789")
        for index in range(200):
            text = uid_for_path(f"res://pack/materials/M_{index}.tres")
            assert set(text[len("uid://"):]) <= allowed


class TestHeader:
    @pytest.fixture
    def material(self):
        from shader_mapping import MappedMaterial

        return MappedMaterial(
            name="Dungeon_01",
            shader_file="polygon.gdshader",
            textures={},
            floats={},
            bools={},
            colors={},
        )

    def test_header_carries_the_uid_when_a_path_is_given(self, material):
        content = generate_tres(
            material, res_path="res://POLYGON_Dungeon/materials/Dungeon_01.tres"
        )
        header = content.split("\n")[0]
        expected = uid_for_path("res://POLYGON_Dungeon/materials/Dungeon_01.tres")
        assert f'uid="{expected}"' in header
        assert header.startswith("[gd_resource ") and header.endswith("]")

    def test_no_path_means_no_uid_rather_than_a_broken_one(self, material):
        """Callers that do not know where the file will land must not get a UID
        derived from nothing."""
        header = generate_tres(material).split("\n")[0]
        assert "uid=" not in header


class TestStamping:
    """Scenes are written by the Godot side across ten call sites, so they are
    stamped once afterwards rather than at each of them."""

    def _project(self, tmp_path):
        pack = tmp_path / "POLYGON_Dungeon" / "meshes"
        pack.mkdir(parents=True)
        return pack

    def test_a_scene_without_a_uid_gets_one(self, tmp_path):
        from tres_generator import stamp_resource_uids

        scene = self._project(tmp_path) / "SM_Prop_Barrel.tscn"
        scene.write_text("[gd_scene format=4]\n\n[node name=\"a\" type=\"Node3D\"]\n",
                         encoding="utf8")
        assert stamp_resource_uids(tmp_path) == 1
        header = scene.read_text(encoding="utf8").split("\n")[0]
        expected = uid_for_path("res://POLYGON_Dungeon/meshes/SM_Prop_Barrel.tscn")
        assert header == f'[gd_scene format=4 uid="{expected}"]'

    def test_load_steps_are_preserved(self, tmp_path):
        from tres_generator import stamp_resource_uids

        scene = self._project(tmp_path) / "SM_Prop_Crate.tscn"
        scene.write_text('[gd_scene load_steps=3 format=3]\n', encoding="utf8")
        stamp_resource_uids(tmp_path)
        assert scene.read_text(encoding="utf8").startswith(
            '[gd_scene load_steps=3 format=3 uid="uid://'
        )

    def test_a_file_that_already_has_one_is_left_alone(self, tmp_path):
        from tres_generator import stamp_resource_uids

        scene = self._project(tmp_path) / "SM_Prop_Keep.tscn"
        original = '[gd_scene format=4 uid="uid://bqqqqqqqqqqqq"]\n'
        scene.write_text(original, encoding="utf8")
        assert stamp_resource_uids(tmp_path) == 0
        assert scene.read_text(encoding="utf8") == original

    def test_binary_resources_are_not_touched(self, tmp_path):
        from tres_generator import stamp_resource_uids

        binary = self._project(tmp_path) / "SM_Prop_Binary.res"
        binary.write_bytes(b"RSRC\x00\x01binary")
        assert stamp_resource_uids(tmp_path) == 0
        assert binary.read_bytes() == b"RSRC\x00\x01binary"

    def test_the_godot_cache_is_skipped(self, tmp_path):
        from tres_generator import stamp_resource_uids

        cache = tmp_path / ".godot" / "imported"
        cache.mkdir(parents=True)
        (cache / "x.tscn").write_text("[gd_scene format=4]\n", encoding="utf8")
        assert stamp_resource_uids(tmp_path) == 0

    def test_a_file_that_is_not_a_resource_is_left_alone(self, tmp_path):
        from tres_generator import stamp_resource_uids

        odd = self._project(tmp_path) / "notes.tres"
        odd.write_text("this is not a resource header\n", encoding="utf8")
        assert stamp_resource_uids(tmp_path) == 0

    def test_stamping_twice_changes_nothing(self, tmp_path):
        from tres_generator import stamp_resource_uids

        scene = self._project(tmp_path) / "SM_Prop_Idem.tscn"
        scene.write_text("[gd_scene format=4]\n", encoding="utf8")
        stamp_resource_uids(tmp_path)
        once = scene.read_text(encoding="utf8")
        assert stamp_resource_uids(tmp_path) == 0
        assert scene.read_text(encoding="utf8") == once

    def test_uids_follow_the_project_path_not_the_scanned_folder(self, tmp_path):
        """Stamping runs per pack, but a UID must encode the resource's address
        in the project - or two packs' same-named materials collide."""
        from tres_generator import stamp_resource_uids

        uids = []
        for pack in ("POLYGON_Dungeon", "POLYGON_Vikings"):
            materials = tmp_path / pack / "materials"
            materials.mkdir(parents=True)
            scene = materials / "Ground_01.tres"
            scene.write_text('[gd_resource type="ShaderMaterial" format=3]\n',
                             encoding="utf8")
            stamp_resource_uids(tmp_path / pack, project_root=tmp_path)
            uids.append(scene.read_text(encoding="utf8").split('uid="')[1].split('"')[0])

        assert uids[0] != uids[1]
        assert uids[0] == uid_for_path("res://POLYGON_Dungeon/materials/Ground_01.tres")
