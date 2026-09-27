"""Tests for building a Polygon BoneMap and putting it where Godot reads it.

The side-resolution tests carry real measured coordinates. Synty names both
hands' finger bones identically and Godot's FBX importer dedups the second with
a suffix whose number differs per file - `Thumb_01_2` in the character FBX,
`Thumb_01_1` in the clips - so anything that infers side from the suffix binds
left-hand tracks to the right hand.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retarget import (  # noqa: E402
    POLYGON_BONE_MAP,
    inject_subresources,
    render_bone_map,
    render_subresources,
    resolve_bone_map,
)


def _bones(**overrides):
    """A minimal Polygon rig: the sided pair that calibrates, plus whatever else."""
    bones = {
        "Root": (0.0, 0.0, 0.0),
        "Hips": (0.0, 0.876, 0.0),
        "Spine_01": (0.0, 1.0, 0.0),
        "Hand_L": (0.7996, 1.3609, -0.0342),
        "Hand_R": (-0.7996, 1.3609, -0.0342),
    }
    bones.update(overrides)
    return bones


class TestSideResolution:
    def test_suffixed_duplicate_resolves_to_the_right_hand(self):
        """The character FBX suffixes the right hand `_2`. Measured values."""
        bones = _bones(**{"Thumb_01": (0.8348, 1.3492, 0.0109),
                          "Thumb_01_2": (-0.8348, 1.3492, 0.0109)})
        resolved, _ = resolve_bone_map(bones)
        assert resolved["LeftThumbMetacarpal"] == "Thumb_01"
        assert resolved["RightThumbMetacarpal"] == "Thumb_01_2"

    def test_a_different_suffix_number_resolves_the_same_way(self):
        """The clip FBX suffixes the same bone `_1`. Suffix order is not a signal."""
        bones = _bones(**{"Thumb_01": (0.2420, 0.7345, 0.3486),
                          "Thumb_01_1": (-0.3667, 0.8054, -0.2616)})
        resolved, _ = resolve_bone_map(bones)
        assert resolved["LeftThumbMetacarpal"] == "Thumb_01"
        assert resolved["RightThumbMetacarpal"] == "Thumb_01_1"

    def test_side_follows_position_even_when_the_suffix_is_on_the_left(self):
        """Guard against re-introducing an encounter-order assumption."""
        bones = _bones(**{"Thumb_01": (-0.8348, 1.3492, 0.0109),
                          "Thumb_01_2": (0.8348, 1.3492, 0.0109)})
        resolved, _ = resolve_bone_map(bones)
        assert resolved["LeftThumbMetacarpal"] == "Thumb_01_2"
        assert resolved["RightThumbMetacarpal"] == "Thumb_01"

    def test_a_rig_whose_left_is_negative_x_still_resolves(self):
        """Calibration comes from the file, not from an assumption about +X."""
        bones = {
            "Hand_L": (-0.8, 1.36, 0.0),
            "Hand_R": (0.8, 1.36, 0.0),
            "Thumb_01": (-0.83, 1.35, 0.0),
            "Thumb_01_1": (0.83, 1.35, 0.0),
        }
        resolved, _ = resolve_bone_map(bones)
        assert resolved["LeftThumbMetacarpal"] == "Thumb_01"
        assert resolved["RightThumbMetacarpal"] == "Thumb_01_1"


class TestUnresolved:
    def test_absent_structural_bones_are_reported_not_guessed(self):
        resolved, unresolved = resolve_bone_map(_bones())
        assert "LeftUpperArm" in unresolved
        assert "LeftUpperArm" not in resolved

    def test_absent_finger_bones_are_left_unmapped_without_refusing(self):
        """Fingers are optional; their absence must not disqualify a humanoid."""
        resolved, unresolved = resolve_bone_map(_bones())
        assert "RightThumbMetacarpal" not in resolved
        assert "RightThumbMetacarpal" not in unresolved

    def test_plain_bones_map_straight_through(self):
        resolved, _ = resolve_bone_map(_bones())
        assert resolved["Hips"] == "Hips"
        assert resolved["Spine"] == "Spine_01"

    def test_profile_bones_with_no_polygon_equivalent_are_left_empty(self):
        """Synty rigs have no ring or little finger; those stay deliberately blank."""
        assert POLYGON_BONE_MAP["LeftRingProximal"] == ""

    def test_deliberately_unmapped_bones_are_not_reported_as_missing(self):
        _, unresolved = resolve_bone_map(_bones())
        assert "LeftRingProximal" not in unresolved
        assert "Jaw" not in unresolved

    def test_calibration_pair_missing_means_no_side_resolution(self):
        """Without Hand_L/Hand_R there is no way to learn which side is which."""
        bones = {"Hips": (0.0, 0.876, 0.0),
                 "Thumb_01": (0.83, 1.34, 0.0), "Thumb_01_2": (-0.83, 1.34, 0.0)}
        resolved, _ = resolve_bone_map(bones)
        assert "LeftThumbMetacarpal" not in resolved
        assert "RightThumbMetacarpal" not in resolved

    def test_a_non_humanoid_rig_resolves_almost_nothing(self):
        """Fantasy Kingdom's 3-bone fairy is the case that must keep being refused."""
        resolved, unresolved = resolve_bone_map(
            {"Root": (0, 0, 0), "Bone": (0, 1, 0), "Bone_001": (0, 2, 0)})
        assert resolved == {"Root": "Root"}
        # Every structural bone but Root is missing, which is what refuses it.
        assert len(unresolved) > 20


EMPTY_IMPORT = '''[remap]

importer="scene"
type="PackedScene"

[params]

nodes/root_type=""
_subresources={}
gltf/naming_version=1
'''


class TestRenderBoneMap:
    def test_renders_a_loadable_resource_header(self):
        text = render_bone_map({"Hips": "Hips"})
        assert text.startswith('[gd_resource type="BoneMap" format=3]')
        assert "SkeletonProfileHumanoid" in text
        assert 'bone_map/Hips = &"Hips"' in text

    def test_unresolved_profile_bones_are_written_empty_not_omitted(self):
        """Godot expects every profile bone present; a missing key is an error."""
        text = render_bone_map({"Hips": "Hips"})
        assert 'bone_map/LeftRingProximal = &""' in text

    def test_covers_every_profile_bone_exactly_once(self):
        text = render_bone_map({})
        assert text.count("bone_map/") == 56


class TestRenderSubresources:
    def test_make_unique_is_false(self):
        """True rewrites tracks to %GeneralSkeleton and they resolve to nothing."""
        assert ('"retarget/bone_renamer/unique_node/make_unique": false'
                in render_subresources("res://bonemap.tres"))

    def test_keys_the_block_by_the_skeleton_node_path(self):
        assert '"PATH:Skeleton3D"' in render_subresources("res://bonemap.tres")

    def test_references_the_given_bone_map(self):
        assert ('Resource("res://packs/x.bonemap.tres")'
                in render_subresources("res://packs/x.bonemap.tres"))


class TestInjectSubresources:
    def test_replaces_the_empty_block_godot_writes(self, tmp_path):
        """Appending instead of replacing leaves the empty block winning."""
        f = tmp_path / "x.fbx.import"
        f.write_text(EMPTY_IMPORT, encoding="utf8")
        assert inject_subresources(f, "res://bonemap.tres") is True
        text = f.read_text(encoding="utf8")
        assert "_subresources={}" not in text
        assert text.count("_subresources=") == 1
        assert 'Resource("res://bonemap.tres")' in text

    def test_leaves_the_rest_of_the_import_intact(self, tmp_path):
        f = tmp_path / "x.fbx.import"
        f.write_text(EMPTY_IMPORT, encoding="utf8")
        inject_subresources(f, "res://bonemap.tres")
        text = f.read_text(encoding="utf8")
        assert 'importer="scene"' in text
        assert "gltf/naming_version=1" in text

    def test_refuses_a_file_that_already_carries_a_block(self, tmp_path):
        f = tmp_path / "x.fbx.import"
        f.write_text(EMPTY_IMPORT.replace('_subresources={}',
                                          '_subresources={"nodes": {}}'), encoding="utf8")
        assert inject_subresources(f, "res://bonemap.tres") is False
        assert '"nodes": {}' in f.read_text(encoding="utf8")

    def test_missing_block_entirely_is_an_error_not_a_silent_skip(self, tmp_path):
        f = tmp_path / "x.fbx.import"
        f.write_text('[params]\nnodes/root_type=""\n', encoding="utf8")
        with pytest.raises(ValueError, match="_subresources"):
            inject_subresources(f, "res://bonemap.tres")


class TestFingersAreOptional:
    """Retargeting eligibility is about being a humanoid, not about completeness.

    Two of Sword Combat's clips have no left index finger. Refusing the whole
    file over a fingertip would lose an otherwise ordinary humanoid rig; Godot
    keeps an unmapped bone under its own name. Whether the retargeted pair can
    actually pose each other is settled later by rest agreement and a render.
    """

    def _hands_and_thumbs(self):
        return {
            "Root": (0, 0, 0), "Hips": (0, 0.9, 0), "Spine_01": (0, 1.0, 0),
            "Spine_02": (0, 1.1, 0), "Spine_03": (0, 1.2, 0),
            "Neck": (0, 1.4, 0), "Head": (0, 1.5, 0),
            "Clavicle_L": (0.1, 1.3, 0), "Shoulder_L": (0.3, 1.3, 0),
            "Elbow_L": (0.5, 1.3, 0), "Hand_L": (0.8, 1.3, 0),
            "Clavicle_R": (-0.1, 1.3, 0), "Shoulder_R": (-0.3, 1.3, 0),
            "Elbow_R": (-0.5, 1.3, 0), "Hand_R": (-0.8, 1.3, 0),
            "UpperLeg_L": (0.1, 0.8, 0), "LowerLeg_L": (0.1, 0.4, 0),
            "Ankle_L": (0.1, 0.1, 0), "Ball_L": (0.1, 0.0, 0.1),
            "UpperLeg_R": (-0.1, 0.8, 0), "LowerLeg_R": (-0.1, 0.4, 0),
            "Ankle_R": (-0.1, 0.1, 0), "Ball_R": (-0.1, 0.0, 0.1),
            "Thumb_01": (0.85, 1.3, 0), "Thumb_01_1": (-0.85, 1.3, 0),
            "Thumb_02": (0.88, 1.3, 0), "Thumb_02_1": (-0.88, 1.3, 0),
            "Thumb_03": (0.91, 1.3, 0), "Thumb_03_1": (-0.91, 1.3, 0),
            "IndexFinger_01": (0.86, 1.32, 0), "IndexFinger_01_1": (-0.86, 1.32, 0),
            "Finger_01": (0.86, 1.28, 0), "Finger_01_1": (-0.86, 1.28, 0),
        }

    def test_a_humanoid_missing_finger_bones_still_retargets(self):
        resolved, unresolved = resolve_bone_map(self._hands_and_thumbs())
        assert unresolved == []
        assert resolved["LeftThumbDistal"] == "Thumb_03"
        assert resolved["RightThumbDistal"] == "Thumb_03_1"
        assert "LeftIndexDistal" not in resolved

    def test_a_missing_structural_bone_still_refuses(self):
        bones = self._hands_and_thumbs()
        del bones["Spine_01"]
        _, unresolved = resolve_bone_map(bones)
        assert "Spine" in unresolved

    def test_chain_root_vote_survives_one_misleading_chain(self):
        """A sword grip puts both hands together; one chain must not flip a hand."""
        bones = self._hands_and_thumbs()
        # Left middle-finger root sitting nearer the right hand, as a clasped pose.
        bones["Finger_01"] = (-0.84, 1.28, 0)
        bones["Finger_01_1"] = (0.84, 1.28, 0)
        resolved, unresolved = resolve_bone_map(bones)
        assert unresolved == []
        assert resolved["LeftThumbMetacarpal"] == "Thumb_01"
        assert resolved["RightThumbMetacarpal"] == "Thumb_01_1"
