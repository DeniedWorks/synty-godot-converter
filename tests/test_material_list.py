"""Tests for material_list.py's flattening of prefab data to a mesh->materials map."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from material_list import (  # noqa: E402
    MaterialSlot,
    MeshMaterials,
    PrefabMaterials,
    get_mesh_to_materials_map,
)


def _prefab(prefab_name: str, mesh_name: str, *material_names: str) -> PrefabMaterials:
    return PrefabMaterials(
        prefab_name=prefab_name,
        meshes=[
            MeshMaterials(
                mesh_name=mesh_name,
                slots=[
                    MaterialSlot(
                        material_name=name, texture_name=None, uses_custom_shader=True
                    )
                    for name in material_names
                ],
            )
        ],
    )


class TestDuplicateMeshNames:
    """A Synty character prefab lists every sibling character it can swap to.

    The mesh's own prefab gives it every surface; the prefabs where it appears
    only as a spare give it one. Taking whichever came last dropped the extra
    surfaces whenever the fuller entry was not last - six characters in
    POLYGON_Dungeon_Realms shipped with their body geometry left on Godot's
    imported material, which reads as flat white.
    """

    def test_fuller_entry_survives_a_later_shorter_one(self):
        prefabs = [
            _prefab("Chr_BR_Dwarf_King_01", "Chr_Dwarf_King_01", "Realms_04_A", "Realms_04_A"),
            _prefab("Chr_BR_Dwarf_Miner_01", "Chr_Dwarf_King_01", "Realms_01_A"),
        ]
        assert get_mesh_to_materials_map(prefabs)["Chr_Dwarf_King_01"] == [
            "Realms_04_A",
            "Realms_04_A",
        ]

    def test_fuller_entry_wins_when_it_comes_last(self):
        prefabs = [
            _prefab("Chr_BR_Dwarf_Miner_01", "Chr_Dwarf_King_01", "Realms_01_A"),
            _prefab("Chr_BR_Dwarf_King_01", "Chr_Dwarf_King_01", "Realms_04_A", "Realms_04_A"),
        ]
        assert get_mesh_to_materials_map(prefabs)["Chr_Dwarf_King_01"] == [
            "Realms_04_A",
            "Realms_04_A",
        ]

    def test_equal_length_entries_keep_the_last(self):
        """794 duplicates across the library are same-length but name different
        materials - colour variants of one mesh. Which of those is authoritative
        is a separate question, so this leaves the existing behaviour alone."""
        prefabs = [
            _prefab("A", "SM_Env_Water_Plane_01", "Water_Stream"),
            _prefab("B", "SM_Env_Water_Plane_01", "Water_Mat_Basic"),
        ]
        assert get_mesh_to_materials_map(prefabs)["SM_Env_Water_Plane_01"] == [
            "Water_Mat_Basic"
        ]

    def test_unique_mesh_names_are_unaffected(self):
        prefabs = [
            _prefab("A", "SM_Prop_Barrel_01", "Barrel_Mat"),
            _prefab("B", "SM_Prop_Crate_01", "Crate_Mat", "Metal_Mat"),
        ]
        assert get_mesh_to_materials_map(prefabs) == {
            "SM_Prop_Barrel_01": ["Barrel_Mat"],
            "SM_Prop_Crate_01": ["Crate_Mat", "Metal_Mat"],
        }

    def test_empty_input_is_empty(self):
        assert get_mesh_to_materials_map([]) == {}


class TestDuplicateLogging:
    def test_says_which_entry_won(self, caplog):
        """This was invisible at DEBUG: the log said a duplicate was found but
        not that slots were being dropped."""
        import logging

        prefabs = [
            _prefab("Own", "Chr_Dwarf_King_01", "Realms_04_A", "Realms_04_A"),
            _prefab("Spare", "Chr_Dwarf_King_01", "Realms_01_A"),
        ]
        with caplog.at_level(logging.DEBUG, logger="material_list"):
            get_mesh_to_materials_map(prefabs)

        assert any(
            "Chr_Dwarf_King_01" in record.message and "keeping" in record.message.lower()
            for record in caplog.records
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
