"""Tests for prefab_parser.py - deriving mesh/material mappings from Unity prefabs.

Fixtures mirror the real structure found in Synty packs (old-style Unity
prefabs using ``m_PrefabParentObject`` / ``!u!1001 Prefab``), trimmed to the
fields the parser actually reads.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prefab_parser import (  # noqa: E402
    _is_game_object_active,
    build_fbx_material_fallback,
    build_prefabs_from_package,
    parse_prefab_bytes,
)

# GUID -> material name, as resolved from GuidMap.guid_to_pathname
GUIDS = {
    "42b64fdb315e3054ea757d8d1c4bcfa7": "Dungeons_Texture_01_Mat",
    "1a64cf0a23f83924f9debcb452685f6f": "Ghost_Mat",
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": "Trim_Mat",
}


def _prefab(body: str) -> bytes:
    return ("%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n" + body).encode("utf-8")


SINGLE_MESH = _prefab(
    """--- !u!1 &123292
GameObject:
  m_Name: SM_Prop_Barrel_01
  m_IsActive: 1
--- !u!23 &2325676
MeshRenderer:
  m_GameObject: {fileID: 123292}
  m_Materials:
  - {fileID: 2100000, guid: 42b64fdb315e3054ea757d8d1c4bcfa7, type: 2}
  m_StaticBatchInfo:
    firstSubMesh: 0
--- !u!33 &3366390
MeshFilter:
  m_GameObject: {fileID: 123292}
  m_Mesh: {fileID: 4300000, guid: 83695bf29d2022e4d9a5dcba65dedb60, type: 3}
"""
)


class TestSingleMesh:
    def test_extracts_mesh_name_from_linked_gameobject(self):
        prefab = parse_prefab_bytes(SINGLE_MESH, "SM_Prop_Barrel_01", GUIDS)
        assert prefab is not None
        assert prefab.prefab_name == "SM_Prop_Barrel_01"
        assert [m.mesh_name for m in prefab.meshes] == ["SM_Prop_Barrel_01"]

    def test_resolves_material_guid_to_name(self):
        prefab = parse_prefab_bytes(SINGLE_MESH, "SM_Prop_Barrel_01", GUIDS)
        assert [s.material_name for s in prefab.meshes[0].slots] == [
            "Dungeons_Texture_01_Mat"
        ]

    def test_marks_slots_as_custom_shader(self):
        """build_shader_cache() short-circuits to polygon when this is False.

        Prefabs carry no such flag, so slots must opt into real shader
        detection (GUID lookup, then name patterns) rather than defaulting
        every material in every pack to polygon.gdshader.
        """
        prefab = parse_prefab_bytes(SINGLE_MESH, "SM_Prop_Barrel_01", GUIDS)
        assert all(s.uses_custom_shader for s in prefab.meshes[0].slots)


class TestMaterialSlots:
    def test_preserves_slot_order(self):
        """Slot index maps to Godot surface index - order is load-bearing."""
        data = _prefab(
            """--- !u!1 &1
GameObject:
  m_Name: SM_Env_Rock_01
--- !u!23 &2
MeshRenderer:
  m_GameObject: {fileID: 1}
  m_Materials:
  - {fileID: 2100000, guid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, type: 2}
  - {fileID: 2100000, guid: 42b64fdb315e3054ea757d8d1c4bcfa7, type: 2}
  m_StaticBatchInfo:
    firstSubMesh: 0
"""
        )
        prefab = parse_prefab_bytes(data, "SM_Env_Rock_01", GUIDS)
        assert [s.material_name for s in prefab.meshes[0].slots] == [
            "Trim_Mat",
            "Dungeons_Texture_01_Mat",
        ]

    def test_skips_null_material_reference(self):
        data = _prefab(
            """--- !u!1 &1
GameObject:
  m_Name: SM_Prop_Empty
--- !u!23 &2
MeshRenderer:
  m_GameObject: {fileID: 1}
  m_Materials:
  - {fileID: 0}
  m_StaticBatchInfo:
    firstSubMesh: 0
"""
        )
        assert parse_prefab_bytes(data, "SM_Prop_Empty", GUIDS) is None

    def test_skips_unresolvable_guid_but_keeps_siblings(self):
        data = _prefab(
            """--- !u!1 &1
GameObject:
  m_Name: SM_Prop_Mixed
--- !u!23 &2
MeshRenderer:
  m_GameObject: {fileID: 1}
  m_Materials:
  - {fileID: 2100000, guid: ffffffffffffffffffffffffffffffff, type: 2}
  - {fileID: 2100000, guid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, type: 2}
  m_StaticBatchInfo:
    firstSubMesh: 0
"""
        )
        prefab = parse_prefab_bytes(data, "SM_Prop_Mixed", GUIDS)
        assert [s.material_name for s in prefab.meshes[0].slots] == ["Trim_Mat"]

    def test_does_not_read_past_materials_list(self):
        """m_Materials must stop at the next key, not swallow later GUIDs."""
        data = _prefab(
            """--- !u!1 &1
GameObject:
  m_Name: SM_Prop_Barrel_01
--- !u!23 &2
MeshRenderer:
  m_GameObject: {fileID: 1}
  m_Materials:
  - {fileID: 2100000, guid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, type: 2}
  m_StaticBatchInfo:
    firstSubMesh: 0
  m_LightmapParameters: {fileID: 2100000, guid: 42b64fdb315e3054ea757d8d1c4bcfa7, type: 2}
"""
        )
        prefab = parse_prefab_bytes(data, "SM_Prop_Barrel_01", GUIDS)
        assert [s.material_name for s in prefab.meshes[0].slots] == ["Trim_Mat"]


class TestRendererTypes:
    def test_reads_skinned_mesh_renderer(self):
        data = _prefab(
            """--- !u!1 &103632
GameObject:
  m_Name: Ghost_Body
--- !u!137 &13726810
SkinnedMeshRenderer:
  m_GameObject: {fileID: 103632}
  m_Materials:
  - {fileID: 2100000, guid: 1a64cf0a23f83924f9debcb452685f6f, type: 2}
  m_Mesh: {fileID: 4300072, guid: b69174d668ba02d44b14a084b217670a, type: 3}
"""
        )
        prefab = parse_prefab_bytes(data, "Character_Ghost_01", GUIDS)
        assert prefab.meshes[0].mesh_name == "Ghost_Body"
        assert prefab.meshes[0].slots[0].material_name == "Ghost_Mat"

    def test_ignores_mesh_collider(self):
        """MeshCollider references a mesh but is not a renderer."""
        data = _prefab(
            """--- !u!1 &1
GameObject:
  m_Name: SM_Prop_Barrel_01
--- !u!64 &64295123690121964
MeshCollider:
  m_GameObject: {fileID: 1}
  m_Material: {fileID: 0}
  m_Mesh: {fileID: 43966164966285454, guid: f88585dab8d7f5f40a1210f243674231, type: 2}
"""
        )
        assert parse_prefab_bytes(data, "SM_Prop_Barrel_01", GUIDS) is None


class TestLodOrdering:
    def test_lod0_sorts_first_regardless_of_document_order(self):
        """build_shader_cache() treats meshes[0] as LOD0 and propagates its
        shader to every other LOD, so LOD0 must lead."""
        data = _prefab(
            """--- !u!1 &3
GameObject:
  m_Name: SM_Env_Tree_01_LOD2
--- !u!23 &30
MeshRenderer:
  m_GameObject: {fileID: 3}
  m_Materials:
  - {fileID: 2100000, guid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, type: 2}
  m_StaticBatchInfo:
    firstSubMesh: 0
--- !u!1 &1
GameObject:
  m_Name: SM_Env_Tree_01_LOD0
--- !u!23 &10
MeshRenderer:
  m_GameObject: {fileID: 1}
  m_Materials:
  - {fileID: 2100000, guid: 42b64fdb315e3054ea757d8d1c4bcfa7, type: 2}
  m_StaticBatchInfo:
    firstSubMesh: 0
"""
        )
        prefab = parse_prefab_bytes(data, "SM_Env_Tree_01", GUIDS)
        assert [m.mesh_name for m in prefab.meshes] == [
            "SM_Env_Tree_01_LOD0",
            "SM_Env_Tree_01_LOD2",
        ]

    def test_non_lod_meshes_keep_document_order(self):
        data = _prefab(
            """--- !u!1 &1
GameObject:
  m_Name: Zebra
--- !u!23 &10
MeshRenderer:
  m_GameObject: {fileID: 1}
  m_Materials:
  - {fileID: 2100000, guid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, type: 2}
  m_StaticBatchInfo:
    firstSubMesh: 0
--- !u!1 &2
GameObject:
  m_Name: Apple
--- !u!23 &20
MeshRenderer:
  m_GameObject: {fileID: 2}
  m_Materials:
  - {fileID: 2100000, guid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, type: 2}
  m_StaticBatchInfo:
    firstSubMesh: 0
"""
        )
        prefab = parse_prefab_bytes(data, "Multi", GUIDS)
        assert [m.mesh_name for m in prefab.meshes] == ["Zebra", "Apple"]


class TestDegenerateInput:
    def test_prefab_with_no_renderers_returns_none(self):
        data = _prefab(
            """--- !u!1 &1
GameObject:
  m_Name: EmptyThing
--- !u!4 &2
Transform:
  m_GameObject: {fileID: 1}
"""
        )
        assert parse_prefab_bytes(data, "EmptyThing", GUIDS) is None

    def test_renderer_pointing_at_missing_gameobject_is_skipped(self):
        data = _prefab(
            """--- !u!23 &2
MeshRenderer:
  m_GameObject: {fileID: 999999}
  m_Materials:
  - {fileID: 2100000, guid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, type: 2}
  m_StaticBatchInfo:
    firstSubMesh: 0
"""
        )
        assert parse_prefab_bytes(data, "Orphan", GUIDS) is None

    def test_garbage_input_does_not_raise(self):
        assert parse_prefab_bytes(b"\x00\x01\x02not yaml", "Junk", GUIDS) is None

    def test_empty_input_does_not_raise(self):
        assert parse_prefab_bytes(b"", "Empty", GUIDS) is None


# Prefab *variant*. It carries no renderer document at all: the material is a
# property modification on the source FBX. Shape taken verbatim from
# POLYGON_NatureBiomes_MeadowForest/SM_Prop_HandCart_01.prefab.
VARIANT = _prefab(
    """--- !u!1001 &6121675629342051127
PrefabInstance:
  m_ObjectHideFlags: 0
  serializedVersion: 2
  m_Modification:
    m_TransformParent: {fileID: 0}
    m_Modifications:
    - target: {fileID: -8679921383154817045, guid: fbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfb, type: 3}
      propertyPath: m_LocalPosition.x
      value: 0
      objectReference: {fileID: 0}
    - target: {fileID: -7511558181221131132, guid: fbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfb, type: 3}
      propertyPath: m_Materials.Array.data[0]
      value: 
      objectReference: {fileID: 2100000, guid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, type: 2}
    m_RemovedComponents: []
  m_SourcePrefab: {fileID: 100100000, guid: fbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfb, type: 3}
"""
)

# Unity wraps long mappings, so `target:` is not reliably on one line. 94 of
# POLYGON_Dwarven_Dungeon_Map's prefabs are written this way; a single-line
# regex silently under-matches them.
VARIANT_WRAPPED = _prefab(
    """--- !u!1001 &1
PrefabInstance:
  m_Modification:
    m_Modifications:
    - target: {fileID: -7511558181221131132, guid: fbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfb,
        type: 3}
      propertyPath: m_Materials.Array.data[0]
      value: 
      objectReference: {fileID: 2100000, guid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,
        type: 2}
  m_SourcePrefab: {fileID: 100100000, guid: fbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfb, type: 3}
"""
)

# Multi-slot variant: one FBX, two material slots. 17 per pack look like this,
# e.g. SM_Gen_Bld_Background_10 (Generic_01_A + Generic_Glass_Opaque).
VARIANT_MULTI_SLOT = _prefab(
    """--- !u!1001 &1
PrefabInstance:
  m_Modification:
    m_Modifications:
    - target: {fileID: -7511558181221131132, guid: fbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfb, type: 3}
      propertyPath: m_Materials.Array.data[1]
      value: 
      objectReference: {fileID: 2100000, guid: 1a64cf0a23f83924f9debcb452685f6f, type: 2}
    - target: {fileID: -7511558181221131132, guid: fbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfb, type: 3}
      propertyPath: m_Materials.Array.data[0]
      value: 
      objectReference: {fileID: 2100000, guid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, type: 2}
  m_SourcePrefab: {fileID: 100100000, guid: fbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfb, type: 3}
"""
)

# One FBX, two renderers. Unity tells them apart by the target's fileID, not by
# its GUID - both name the same FBX. Shape taken from
# SM_Bld_Base_Wall_Window_Half_02, which ships in all three packs measured: the
# wall body carries three surfaces and the glass pane one.
VARIANT_TWO_RENDERERS = _prefab(
    """--- !u!1001 &1
PrefabInstance:
  m_Modification:
    m_Modifications:
    - target: {fileID: 111, guid: fbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfb, type: 3}
      propertyPath: m_Materials.Array.data[0]
      value:
      objectReference: {fileID: 2100000, guid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, type: 2}
    - target: {fileID: 111, guid: fbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfb, type: 3}
      propertyPath: m_Materials.Array.data[1]
      value:
      objectReference: {fileID: 2100000, guid: 42b64fdb315e3054ea757d8d1c4bcfa7, type: 2}
    - target: {fileID: 222, guid: fbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfb, type: 3}
      propertyPath: m_Materials.Array.data[0]
      value:
      objectReference: {fileID: 2100000, guid: 1a64cf0a23f83924f9debcb452685f6f, type: 2}
  m_SourcePrefab: {fileID: 100100000, guid: fbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfb, type: 3}
"""
)

# FBX GUID -> mesh name, as resolved from GuidMap.guid_to_pathname.
MESH_GUIDS = {"fbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfb": "SM_Prop_HandCart_01"}


class TestPrefabVariants:
    """Variants express materials as modifications, not renderer documents.

    Without this path hundreds of meshes per pack get no mapping and render
    with Godot's imported StandardMaterial3D - flat white - while the
    conversion still reports success.
    """

    def test_variant_yields_mesh_and_material(self):
        result = parse_prefab_bytes(VARIANT, "SM_Prop_HandCart_01", GUIDS, MESH_GUIDS)
        assert result is not None
        assert [m.mesh_name for m in result.meshes] == ["SM_Prop_HandCart_01"]
        assert [s.material_name for s in result.meshes[0].slots] == ["Trim_Mat"]

    def test_variant_slots_use_custom_shader(self):
        """Same reasoning as the renderer path: route through determine_shader."""
        result = parse_prefab_bytes(VARIANT, "X", GUIDS, MESH_GUIDS)
        assert result.meshes[0].slots[0].uses_custom_shader is True

    def test_wrapped_target_mapping_is_matched(self):
        result = parse_prefab_bytes(VARIANT_WRAPPED, "X", GUIDS, MESH_GUIDS)
        assert result is not None
        assert result.meshes[0].slots[0].material_name == "Trim_Mat"

    def test_multi_slot_variant_keeps_slots_in_index_order(self):
        result = parse_prefab_bytes(VARIANT_MULTI_SLOT, "X", GUIDS, MESH_GUIDS)
        assert [s.material_name for s in result.meshes[0].slots] == [
            "Trim_Mat",
            "Ghost_Mat",
        ]

    def test_unresolvable_mesh_guid_yields_none(self):
        assert parse_prefab_bytes(VARIANT, "X", GUIDS, {}) is None

    def test_unresolvable_material_guid_yields_none(self):
        assert parse_prefab_bytes(VARIANT, "X", {}, MESH_GUIDS) is None

    def test_renderer_form_still_parses(self):
        """Regression guard: the plain path must be untouched."""
        result = parse_prefab_bytes(SINGLE_MESH, "SM_Prop_Barrel_01", GUIDS, MESH_GUIDS)
        assert result.meshes[0].mesh_name == "SM_Prop_Barrel_01"
        assert result.meshes[0].slots[0].material_name == "Dungeons_Texture_01_Mat"

    def test_renderer_form_wins_over_modifications(self):
        """A prefab with real renderers must not also be read as a variant."""
        result = parse_prefab_bytes(SINGLE_MESH, "X", GUIDS, MESH_GUIDS)
        assert len(result.meshes) == 1

    def test_mesh_guid_map_is_optional(self):
        """Callers that pass no mesh map keep the old behaviour."""
        assert parse_prefab_bytes(VARIANT, "X", GUIDS) is None

    def test_two_renderers_do_not_merge_into_one_slot_list(self):
        """Grouping by GUID alone let the glass pane overwrite the wall body.

        Both renderers name the same FBX, so a GUID-keyed dict kept whichever
        was written last at slot 0 - shipping a wall whose first surface is
        glass.
        """
        result = parse_prefab_bytes(VARIANT_TWO_RENDERERS, "X", GUIDS, MESH_GUIDS)
        assert [s.material_name for s in result.meshes[0].slots] == [
            "Trim_Mat",
            "Dungeons_Texture_01_Mat",
        ]

    def test_largest_renderer_claims_the_fbx_name(self):
        """The mesh named after the FBX is its body, which carries the most
        surfaces. One entry only: mesh_material_mapping.json is keyed by name,
        so a second entry under the same name would just overwrite it."""
        result = parse_prefab_bytes(VARIANT_TWO_RENDERERS, "X", GUIDS, MESH_GUIDS)
        assert len(result.meshes) == 1
        assert result.meshes[0].mesh_name == "SM_Prop_HandCart_01"

    def test_modifications_without_materials_yield_none(self):
        data = _prefab(
            """--- !u!1001 &1
PrefabInstance:
  m_Modification:
    m_Modifications:
    - target: {fileID: -1, guid: fbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfb, type: 3}
      propertyPath: m_LocalPosition.x
      value: 0
      objectReference: {fileID: 0}
"""
        )
        assert parse_prefab_bytes(data, "X", GUIDS, MESH_GUIDS) is None


class TestFbxMaterialFallback:
    """Sub-meshes of a multi-mesh FBX have no mapping of their own.

    A variant names its mesh by the source FBX, so only the mesh sharing that
    name gets a material - a hand cart is painted while its two wheels stay
    untextured. Godot knows which FBX each mesh came from, so it can fall back
    to the FBX's own materials; this is the table it falls back to.
    """

    def _guid_map(self, prefabs):
        return _FakeGuidMap(
            pathnames={
                "fbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfb": "Assets/P/Models/SM_Prop_HandCart_01.fbx",
                "42b64fdb315e3054ea757d8d1c4bcfa7": "Assets/P/Materials/Dungeons_Texture_01_Mat.mat",
                "1a64cf0a23f83924f9debcb452685f6f": "Assets/P/Materials/Ghost_Mat.mat",
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": "Assets/P/Materials/Trim_Mat.mat",
                "p1": "Assets/P/Prefabs/Variant.prefab",
            },
            prefab_content=prefabs,
        )

    def test_single_renderer_yields_one_entry(self):
        fallback = build_fbx_material_fallback(self._guid_map({"p1": VARIANT}))
        assert fallback == {"SM_Prop_HandCart_01": [["Trim_Mat"]]}

    def test_every_renderer_is_kept(self):
        fallback = build_fbx_material_fallback(
            self._guid_map({"p1": VARIANT_TWO_RENDERERS})
        )
        assert fallback == {
            "SM_Prop_HandCart_01": [
                ["Trim_Mat", "Dungeons_Texture_01_Mat"],
                ["Ghost_Mat"],
            ]
        }

    def test_renderers_are_ordered_largest_first(self):
        """Godot picks by surface count, and falls back to the first entry when
        nothing matches - which should be the body, not a one-surface pane."""
        fallback = build_fbx_material_fallback(
            self._guid_map({"p1": VARIANT_TWO_RENDERERS})
        )
        sizes = [len(slots) for slots in fallback["SM_Prop_HandCart_01"]]
        assert sizes == sorted(sizes, reverse=True)

    def test_prefabs_with_renderers_contribute_nothing(self):
        """Plain prefabs name their meshes directly, so they need no fallback."""
        assert build_fbx_material_fallback(self._guid_map({"p1": SINGLE_MESH})) == {}

    def test_package_without_prefabs_is_empty(self):
        assert build_fbx_material_fallback(_FakeGuidMap({}, {})) == {}


class _FakeGuidMap:
    """Minimal stand-in for unity_package.GuidMap."""

    def __init__(self, pathnames, prefab_content):
        self.guid_to_pathname = pathnames
        self.guid_to_prefab_content = prefab_content
        self.guid_to_content = {}
        self.texture_guid_to_name = {}
        self.texture_guid_to_path = {}


class TestBuildFromPackage:
    def test_builds_prefabs_and_resolves_material_names(self):
        guid_map = _FakeGuidMap(
            pathnames={
                "42b64fdb315e3054ea757d8d1c4bcfa7": "Assets/PolygonDungeon/Materials/Dungeons_Texture_01_Mat.mat",
                "p1": "Assets/PolygonDungeon/Prefabs/Props/SM_Prop_Barrel_01.prefab",
            },
            prefab_content={"p1": SINGLE_MESH},
        )
        prefabs = build_prefabs_from_package(guid_map)
        assert len(prefabs) == 1
        assert prefabs[0].prefab_name == "SM_Prop_Barrel_01"
        assert prefabs[0].meshes[0].slots[0].material_name == "Dungeons_Texture_01_Mat"

    def test_skips_prefabs_with_no_renderers(self):
        guid_map = _FakeGuidMap(
            pathnames={"p1": "Assets/Pack/Prefabs/Empty.prefab"},
            prefab_content={
                "p1": _prefab("--- !u!1 &1\nGameObject:\n  m_Name: Empty\n")
            },
        )
        assert build_prefabs_from_package(guid_map) == []

    def test_returns_empty_when_package_has_no_prefabs(self):
        assert build_prefabs_from_package(_FakeGuidMap({}, {})) == []


class TestIntegrationWithMaterialList:
    """The output must satisfy every downstream consumer unchanged."""

    def test_feeds_mesh_material_mapping_json(self, tmp_path):
        from material_list import generate_mesh_material_mapping_json

        guid_map = _FakeGuidMap(
            pathnames={
                "42b64fdb315e3054ea757d8d1c4bcfa7": "Assets/P/Materials/Dungeons_Texture_01_Mat.mat",
                "p1": "Assets/P/Prefabs/SM_Prop_Barrel_01.prefab",
            },
            prefab_content={"p1": SINGLE_MESH},
        )
        prefabs = build_prefabs_from_package(guid_map)
        out = tmp_path / "mesh_material_mapping.json"
        generate_mesh_material_mapping_json(prefabs, out)

        import json

        assert json.loads(out.read_text()) == {
            "SM_Prop_Barrel_01": ["Dungeons_Texture_01_Mat"]
        }

    def test_feeds_build_shader_cache(self):
        from converter import build_shader_cache

        guid_map = _FakeGuidMap(
            pathnames={
                "42b64fdb315e3054ea757d8d1c4bcfa7": "Assets/P/Materials/Dungeons_Texture_01_Mat.mat",
                "p1": "Assets/P/Prefabs/SM_Prop_Barrel_01.prefab",
            },
            prefab_content={"p1": SINGLE_MESH},
        )
        prefabs = build_prefabs_from_package(guid_map)
        shader_cache, _unmatched = build_shader_cache(prefabs)
        assert shader_cache["Dungeons_Texture_01_Mat"].endswith(".gdshader")


class TestIsGameObjectActive:
    def test_active_flag_one_is_active(self):
        assert _is_game_object_active("  m_Name: Foo\n  m_IsActive: 1\n") is True

    def test_active_flag_zero_is_inactive(self):
        assert _is_game_object_active("  m_Name: Foo\n  m_IsActive: 0\n") is False

    def test_absent_flag_defaults_to_active(self):
        """Older prefabs omit the field; treat them as visible rather than
        silently dropping every mesh in the file."""
        assert _is_game_object_active("  m_Name: Foo\n") is True

    def test_malformed_flag_defaults_to_active(self):
        assert _is_game_object_active("  m_IsActive: yes\n") is True

    def test_reads_own_field_not_a_later_one(self):
        body = "  m_Name: Foo\n  m_IsActive: 0\n  m_SomethingElse: 1\n"
        assert _is_game_object_active(body) is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
