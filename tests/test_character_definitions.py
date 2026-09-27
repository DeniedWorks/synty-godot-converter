"""Tests for deriving character definitions from Unity prefabs."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prefab_parser import (  # noqa: E402
    MIN_CHARACTER_BONES,
    CharacterDefinition,
    build_character_definitions,
)


def _prefab(body: str) -> bytes:
    return ("%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n" + body).encode("utf-8")


def _bones(count: int, *, indent: str = "  ", start: int = 9000) -> str:
    """An m_Bones block with `count` entries, as Unity serialises it.

    `start` picks which bones of a shared skeleton the block names, so two
    blocks can overlap the way a modular character's parts do.
    """
    lines = [f"{indent}m_Bones:"]
    lines += [f"{indent}- {{fileID: {start + i}}}" for i in range(count)]
    return "\n".join(lines)


# A rig comfortably above the cloth/FX cutoff. Real Synty character rigs are
# 49-52 bones; cloth is 5 and FX is 2.
CHARACTER_BONES = 50


# One active skinned character plus one active bone-attached item, and one
# disabled sibling character - the shape every Synty character prefab has.
WARCHIEF = _prefab(
    f"""--- !u!1 &100
GameObject:
  m_Name: Character_Goblin_WarChief
  m_IsActive: 1
--- !u!137 &101
SkinnedMeshRenderer:
  m_GameObject: {{fileID: 100}}
  m_Materials:
  - {{fileID: 2100000, guid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, type: 2}}
{_bones(CHARACTER_BONES)}
  m_Mesh: {{fileID: 4300072, guid: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb, type: 3}}
--- !u!1 &200
GameObject:
  m_Name: SM_Item_Goblin_WarBanner
  m_IsActive: 1
--- !u!23 &201
MeshRenderer:
  m_GameObject: {{fileID: 200}}
  m_Materials:
  - {{fileID: 2100000, guid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, type: 2}}
  m_StaticBatchInfo:
    firstSubMesh: 0
--- !u!1 &300
GameObject:
  m_Name: Character_Skeleton_Knight
  m_IsActive: 0
--- !u!137 &301
SkinnedMeshRenderer:
  m_GameObject: {{fileID: 300}}
  m_Materials:
  - {{fileID: 2100000, guid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, type: 2}}
{_bones(CHARACTER_BONES)}
  m_Mesh: {{fileID: 4300050, guid: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb, type: 3}}
"""
)

# A plain prop: MeshRenderer only, no skinning.
BARREL = _prefab(
    """--- !u!1 &1
GameObject:
  m_Name: SM_Prop_Barrel_01
  m_IsActive: 1
--- !u!23 &2
MeshRenderer:
  m_GameObject: {fileID: 1}
  m_Materials:
  - {fileID: 2100000, guid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, type: 2}
  m_StaticBatchInfo:
    firstSubMesh: 0
"""
)

PATHNAMES = {
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": "Assets/P/Materials/Dungeon_Material_01.mat",
    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb": "Assets/P/Models/Characters.fbx",
    "pw": "Assets/P/Prefabs/Characters/Character_Goblin_WarChief.prefab",
    "pb": "Assets/P/Prefabs/Props/SM_Prop_Barrel_01.prefab",
    "pm": "Assets/P/Prefabs/Characters/Character_Mystery.prefab",
    "cccccccccccccccccccccccccccccccc": "Assets/P/Models/FixedScale/Characters.fbx",
    "pf": "Assets/P/Prefabs/Characters/Character_Goblin_WarChief_FixedScale.prefab",
    "dddddddddddddddddddddddddddddddd": "Assets/P/Characters/FantasyKnights_01/Meshes/FantasyKnights_01.asset",
    "psk": "Assets/P/Characters/FantasyKnights_01/FantasyKnights_01.prefab",
}


class _FakeGuidMap:
    def __init__(self, pathnames, prefab_content):
        self.guid_to_pathname = pathnames
        self.guid_to_prefab_content = prefab_content
        self.guid_to_content = {}
        self.texture_guid_to_name = {}
        self.texture_guid_to_path = {}


def _guid_map(prefabs):
    return _FakeGuidMap(PATHNAMES, prefabs)


class TestBuildCharacterDefinitions:
    def test_finds_character_prefab(self):
        defs = build_character_definitions(_guid_map({"pw": WARCHIEF}))
        assert list(defs) == ["Character_Goblin_WarChief"]

    def test_includes_only_active_skinned_mesh(self):
        defs = build_character_definitions(_guid_map({"pw": WARCHIEF}))
        assert defs["Character_Goblin_WarChief"].skinned == [
            "Character_Goblin_WarChief"
        ]

    def test_includes_active_attachment(self):
        defs = build_character_definitions(_guid_map({"pw": WARCHIEF}))
        assert defs["Character_Goblin_WarChief"].attachments == [
            "SM_Item_Goblin_WarBanner"
        ]

    def test_resolves_source_fbx_from_mesh_guid(self):
        defs = build_character_definitions(_guid_map({"pw": WARCHIEF}))
        assert defs["Character_Goblin_WarChief"].source_fbx == "Characters"

    def test_ignores_prefab_with_no_skinned_renderer(self):
        assert build_character_definitions(_guid_map({"pb": BARREL})) == {}

    def test_ignores_prefab_whose_only_skinned_mesh_is_disabled(self):
        """Bones are present and plentiful - being disabled is the reason."""
        data = _prefab(
            f"""--- !u!1 &300
GameObject:
  m_Name: Character_Skeleton_Knight
  m_IsActive: 0
--- !u!137 &301
SkinnedMeshRenderer:
  m_GameObject: {{fileID: 300}}
{_bones(CHARACTER_BONES)}
  m_Mesh: {{fileID: 4300050, guid: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb, type: 3}}
"""
        )
        assert build_character_definitions(_guid_map({"pw": data})) == {}

    def test_returns_empty_when_no_prefabs(self):
        assert build_character_definitions(_guid_map({})) == {}

    def test_unresolvable_mesh_guid_yields_empty_source_fbx(self):
        data = _prefab(
            f"""--- !u!1 &1
GameObject:
  m_Name: Character_Mystery
  m_IsActive: 1
--- !u!137 &2
SkinnedMeshRenderer:
  m_GameObject: {{fileID: 1}}
{_bones(CHARACTER_BONES)}
  m_Mesh: {{fileID: 1, guid: ffffffffffffffffffffffffffffffff, type: 3}}
"""
        )
        defs = build_character_definitions(_guid_map({"pm": data}))
        assert defs["Character_Mystery"].source_fbx == ""

    def test_source_fbx_is_relative_to_models_root(self):
        """Basenames collide: this pack ships Models/Characters.fbx AND
        Models/FixedScale/Characters.fbx. If source_fbx were just the
        basename, every definition would match both files and characters
        would be built twice, half of them from the wrong FBX."""
        data = WARCHIEF.replace(
            b"guid: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            b"guid: cccccccccccccccccccccccccccccccc",
        )
        defs = build_character_definitions(_guid_map({"pf": data}))
        got = defs["Character_Goblin_WarChief_FixedScale"].source_fbx
        assert got == "FixedScale/Characters"

    def test_source_fbx_has_no_prefix_for_top_level_fbx(self):
        defs = build_character_definitions(_guid_map({"pw": WARCHIEF}))
        assert defs["Character_Goblin_WarChief"].source_fbx == "Characters"

    def test_records_bone_count(self):
        defs = build_character_definitions(_guid_map({"pw": WARCHIEF}))
        assert defs["Character_Goblin_WarChief"].bone_count == CHARACTER_BONES

    def test_ignores_skinned_cloth(self):
        """Synty skins tent covers and flag lines so they move in the wind.

        On POLYGON_Dungeon_Realms this over-match produced 33 bogus character
        definitions out of 52 - every one of which then failed in Godot.
        """
        data = _prefab(
            f"""--- !u!1 &1
GameObject:
  m_Name: SM_Bld_Camp_Tent_01
  m_IsActive: 1
--- !u!137 &2
SkinnedMeshRenderer:
  m_GameObject: {{fileID: 1}}
{_bones(5)}
  m_Mesh: {{fileID: 4300072, guid: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb, type: 3}}
"""
        )
        assert build_character_definitions(_guid_map({"pm": data})) == {}

    def test_modular_character_counts_bones_across_its_parts(self):
        """POLYGON_Modular_Fantasy_Hero assembles a character out of ~17 parts,
        each skinned only to the bones it needs - a forearm binds 12. Taking the
        largest single part rejected 117 of its 126 characters; the parts
        together cover 49-58 bones of one shared skeleton.
        """
        data = _prefab(
            f"""--- !u!1 &1
GameObject:
  m_Name: Chr_FantasyHero_Preset_99
  m_IsActive: 1
--- !u!137 &2
SkinnedMeshRenderer:
  m_GameObject: {{fileID: 1}}
{_bones(12, start=9000)}
  m_Mesh: {{fileID: 4300072, guid: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb, type: 3}}
--- !u!1 &3
GameObject:
  m_Name: Chr_FantasyHero_Preset_99_Legs
  m_IsActive: 1
--- !u!137 &4
SkinnedMeshRenderer:
  m_GameObject: {{fileID: 3}}
{_bones(12, start=9008)}
  m_Mesh: {{fileID: 4300072, guid: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb, type: 3}}
"""
        )
        defs = build_character_definitions(_guid_map({"pm": data}))
        # 9000-9011 and 9008-9019: 20 distinct bones, not 12.
        # The definition is keyed by the prefab path, not the GameObject.
        assert defs["Character_Mystery"].bone_count == 20

    def test_cloth_stays_rejected_when_several_pieces_share_a_prefab(self):
        """The union must not rescue cloth: a tent's covers are skinned to the
        same handful of bones, so together they still name only those bones."""
        data = _prefab(
            f"""--- !u!1 &1
GameObject:
  m_Name: SM_Bld_Camp_Tent_01
  m_IsActive: 1
--- !u!137 &2
SkinnedMeshRenderer:
  m_GameObject: {{fileID: 1}}
{_bones(5)}
  m_Mesh: {{fileID: 4300072, guid: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb, type: 3}}
--- !u!1 &3
GameObject:
  m_Name: SM_Bld_Camp_Tent_Cover_01
  m_IsActive: 1
--- !u!137 &4
SkinnedMeshRenderer:
  m_GameObject: {{fileID: 3}}
{_bones(5)}
  m_Mesh: {{fileID: 4300072, guid: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb, type: 3}}
"""
        )
        assert build_character_definitions(_guid_map({"pm": data})) == {}

    def test_ignores_skinned_renderer_with_no_bone_list(self):
        data = _prefab(
            """--- !u!1 &1
GameObject:
  m_Name: Character_Mystery
  m_IsActive: 1
--- !u!137 &2
SkinnedMeshRenderer:
  m_GameObject: {fileID: 1}
  m_Mesh: {fileID: 4300072, guid: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb, type: 3}
"""
        )
        assert build_character_definitions(_guid_map({"pm": data})) == {}

    def test_bone_count_threshold_is_inclusive(self):
        data = _prefab(
            f"""--- !u!1 &1
GameObject:
  m_Name: Character_Mystery
  m_IsActive: 1
--- !u!137 &2
SkinnedMeshRenderer:
  m_GameObject: {{fileID: 1}}
{_bones(MIN_CHARACTER_BONES)}
  m_Mesh: {{fileID: 4300072, guid: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb, type: 3}}
"""
        )
        defs = build_character_definitions(_guid_map({"pm": data}))
        assert defs["Character_Mystery"].bone_count == MIN_CHARACTER_BONES

    def test_one_bone_below_threshold_is_rejected(self):
        data = _prefab(
            f"""--- !u!1 &1
GameObject:
  m_Name: Character_Mystery
  m_IsActive: 1
--- !u!137 &2
SkinnedMeshRenderer:
  m_GameObject: {{fileID: 1}}
{_bones(MIN_CHARACTER_BONES - 1)}
  m_Mesh: {{fileID: 4300072, guid: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb, type: 3}}
"""
        )
        assert build_character_definitions(_guid_map({"pm": data})) == {}

    def test_definition_is_a_dataclass_with_expected_fields(self):
        d = CharacterDefinition(
            name="X", source_fbx="F", skinned=["a"], attachments=["b"]
        )
        assert (d.name, d.source_fbx, d.skinned, d.attachments) == (
            "X",
            "F",
            ["a"],
            ["b"],
        )


    def test_ignores_prefab_whose_mesh_is_not_an_fbx(self):
        """Sidekick prefabs point at a Unity-baked .asset mesh.

        Godot cannot import .asset, so such a definition could never match a
        file and produced a silent zero-character conversion. Sidekick
        characters are built from .sk recipes instead.
        """
        data = _prefab(
            f"""--- !u!1 &1
GameObject:
  m_Name: FantasyKnights_01
  m_IsActive: 1
--- !u!137 &2
SkinnedMeshRenderer:
  m_GameObject: {{fileID: 1}}
{_bones(CHARACTER_BONES)}
  m_Mesh: {{fileID: 1, guid: dddddddddddddddddddddddddddddddd, type: 3}}
"""
        )
        assert build_character_definitions(_guid_map({"psk": data})) == {}

class TestWriteCharacterDefinitionsJson:
    def test_writes_expected_json_shape(self, tmp_path):
        from prefab_parser import write_character_definitions_json

        defs = build_character_definitions(_guid_map({"pw": WARCHIEF}))
        out = tmp_path / "character_definitions.json"
        write_character_definitions_json(defs, out)

        import json

        assert json.loads(out.read_text(encoding="utf-8")) == {
            "Character_Goblin_WarChief": {
                "source_fbx": "Characters",
                "skinned": ["Character_Goblin_WarChief"],
                "attachments": ["SM_Item_Goblin_WarBanner"],
                "bone_count": CHARACTER_BONES,
            }
        }

    def test_creates_parent_directory(self, tmp_path):
        from prefab_parser import write_character_definitions_json

        out = tmp_path / "nested" / "character_definitions.json"
        write_character_definitions_json({}, out)
        assert out.exists()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
