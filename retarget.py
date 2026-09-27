"""Retarget Synty rigs onto SkeletonProfileHumanoid at import time.

A clip poses only the rig whose rest orientations it was authored against, since
almost every track is an absolute local rotation rather than a delta from rest.
Synty's character rigs and clip rigs disagree, so binding one to the other
collapses the character.

Godot's scene importer can rewrite both onto a common profile, given a `BoneMap`.
This module builds that map from a file's real bones and puts it where the
importer will read it.
"""

from pathlib import Path

# Profile bone -> Polygon rig bone. "" means the profile bone has no equivalent
# in a Synty rig and is deliberately left unmapped; Godot keeps such bones under
# their original names. Synty rigs have no ring or little finger, no separate eye
# or jaw bones.
POLYGON_BONE_MAP: dict[str, str] = {
    "Root": "Root",
    "Hips": "Hips",
    "Spine": "Spine_01",
    "Chest": "Spine_02",
    "UpperChest": "Spine_03",
    "Neck": "Neck",
    "Head": "Head",
    "LeftEye": "",
    "RightEye": "",
    "Jaw": "",
    "LeftShoulder": "Clavicle_L",
    "LeftUpperArm": "Shoulder_L",
    "LeftLowerArm": "Elbow_L",
    "LeftHand": "Hand_L",
    "LeftRingProximal": "",
    "LeftRingIntermediate": "",
    "LeftRingDistal": "",
    "LeftLittleProximal": "",
    "LeftLittleIntermediate": "",
    "LeftLittleDistal": "",
    "RightShoulder": "Clavicle_R",
    "RightUpperArm": "Shoulder_R",
    "RightLowerArm": "Elbow_R",
    "RightHand": "Hand_R",
    "RightRingProximal": "",
    "RightRingIntermediate": "",
    "RightRingDistal": "",
    "RightLittleProximal": "",
    "RightLittleIntermediate": "",
    "RightLittleDistal": "",
    "LeftUpperLeg": "UpperLeg_L",
    "LeftLowerLeg": "LowerLeg_L",
    "LeftFoot": "Ankle_L",
    "LeftToes": "Ball_L",
    "RightUpperLeg": "UpperLeg_R",
    "RightLowerLeg": "LowerLeg_R",
    "RightFoot": "Ankle_R",
    "RightToes": "Ball_R",
}

# Profile bone -> (base rig name, side). Both hands' finger bones share names, so
# Godot's importer dedups one side with a suffix whose number differs per file.
# Side is therefore resolved by position, never by the suffix.
POLYGON_DUPLICATE_BONES: dict[str, tuple[str, str]] = {
    "LeftThumbMetacarpal": ("Thumb_01", "L"),
    "LeftThumbProximal": ("Thumb_02", "L"),
    "LeftThumbDistal": ("Thumb_03", "L"),
    "LeftIndexProximal": ("IndexFinger_01", "L"),
    "LeftIndexIntermediate": ("IndexFinger_02", "L"),
    "LeftIndexDistal": ("IndexFinger_03", "L"),
    "LeftMiddleProximal": ("Finger_01", "L"),
    "LeftMiddleIntermediate": ("Finger_02", "L"),
    "LeftMiddleDistal": ("Finger_03", "L"),
    "RightThumbMetacarpal": ("Thumb_01", "R"),
    "RightThumbProximal": ("Thumb_02", "R"),
    "RightThumbDistal": ("Thumb_03", "R"),
    "RightIndexProximal": ("IndexFinger_01", "R"),
    "RightIndexIntermediate": ("IndexFinger_02", "R"),
    "RightIndexDistal": ("IndexFinger_03", "R"),
    "RightMiddleProximal": ("Finger_01", "R"),
    "RightMiddleIntermediate": ("Finger_02", "R"),
    "RightMiddleDistal": ("Finger_03", "R"),
}

# The hands a finger chain is matched against.
_HANDS = {"L": "Hand_L", "R": "Hand_R"}

# The knuckle at the base of each finger chain. Side is decided from these and
# applied to the whole chain: a fingertip is not reliably nearest its own hand,
# since a two-handed grip puts both hands together.
_CHAIN_ROOTS = ("Thumb_01", "IndexFinger_01", "Finger_01")

Vector = tuple[float, float, float]


def _distance(a: Vector, b: Vector) -> float:
    """Straight-line distance between two rest origins."""
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _suffix_candidates(bones: dict[str, Vector], base: str) -> list[str]:
    """Every bone that is `base` or `base` plus Godot's dedup index."""
    return [
        name for name in sorted(bones)
        if name == base
        or (name.startswith(base + "_") and name[len(base) + 1:].isdigit())
    ]


def _hand_suffixes(bones: dict[str, Vector]) -> dict[str, str]:
    """Decides which dedup suffix belongs to which hand.

    The suffix differs per file, so it is learned rather than assumed: each chain
    root votes by proximity to its hand and the majority wins, so one contorted
    chain cannot mislabel a hand.

    Returns:
        {"L": suffix, "R": suffix}, empty when the two sides cannot be told
        apart. A suffix is "" for the undecorated name.
    """
    if not all(hand in bones for hand in _HANDS.values()):
        return {}

    votes: dict[str, dict[str, int]] = {"L": {}, "R": {}}
    for base in _CHAIN_ROOTS:
        candidates = _suffix_candidates(bones, base)
        if len(candidates) < 2:
            continue
        for side, hand in _HANDS.items():
            nearest = min(candidates, key=lambda n: _distance(bones[n], bones[hand]))
            suffix = nearest[len(base):]
            votes[side][suffix] = votes[side].get(suffix, 0) + 1

    if not votes["L"] or not votes["R"]:
        return {}
    chosen = {side: max(tally, key=tally.get) for side, tally in votes.items()}
    # Both hands resolving to the same suffix means they were not distinguished,
    # and guessing would put left-hand tracks on the right hand.
    if chosen["L"] == chosen["R"]:
        return {}
    return chosen


def resolve_bone_map(bones: dict[str, Vector]) -> tuple[dict[str, str], list[str]]:
    """Resolves the Polygon template against one file's actual bones.

    Args:
        bones: Bone name -> global rest origin, as reported by the Godot side.

    Returns:
        (profile bone -> rig bone name, *required* profile bones that could not
        be resolved). A non-empty second element means the rig is not a humanoid
        and must not be retargeted.

        Only structural bones are required; a missing finger is left unmapped and
        Godot keeps it under its own name. This decides eligibility, not
        correctness - whether a retargeted pair can pose each other is settled
        afterwards by rest agreement.
    """
    resolved: dict[str, str] = {}
    unresolved: list[str] = []

    for profile_bone, rig_bone in POLYGON_BONE_MAP.items():
        if not rig_bone:
            continue
        if rig_bone in bones:
            resolved[profile_bone] = rig_bone
        else:
            unresolved.append(profile_bone)

    suffixes = _hand_suffixes(bones)
    for profile_bone, (base, side) in POLYGON_DUPLICATE_BONES.items():
        if not suffixes:
            continue
        name = base + suffixes[side]
        if name in bones:
            resolved[profile_bone] = name

    return resolved, sorted(unresolved)


# Every profile bone Godot expects in a humanoid BoneMap. Order is irrelevant to
# the parser - the keys are properties - but every one must be present.
PROFILE_BONES: list[str] = list(POLYGON_BONE_MAP) + [
    bone for bone in POLYGON_DUPLICATE_BONES if bone not in POLYGON_BONE_MAP
]


def render_bone_map(resolved: dict[str, str]) -> str:
    """Renders a BoneMap .tres.

    Unresolved bones are written empty rather than omitted: Godot expects every
    profile bone to be present, and a missing key is an error rather than an
    unmapped bone.
    """
    lines = [
        '[gd_resource type="BoneMap" format=3]',
        "",
        '[sub_resource type="SkeletonProfileHumanoid" id="SkeletonProfileHumanoid_syn"]',
        "",
        "[resource]",
        'profile = SubResource("SkeletonProfileHumanoid_syn")',
    ]
    for profile_bone in PROFILE_BONES:
        lines.append('bone_map/%s = &"%s"' % (profile_bone, resolved.get(profile_bone, "")))
    return "\n".join(lines) + "\n"


def render_subresources(bone_map_res: str) -> str:
    """The retarget option block, keyed by the skeleton's node path.

    These are per-node subresource settings. Written under `[params]` they look
    like they work, and Godot drops them on the next import.
    """
    return (
        "_subresources={\n"
        '"nodes": {\n'
        '"PATH:Skeleton3D": {\n'
        '"retarget/bone_map": Resource("%s"),\n'
        '"retarget/bone_renamer/rename_bones": true,\n'
        # True rewrites tracks to %GeneralSkeleton:<bone>, which our
        # Skeleton3D-named characters never resolve - and Godot skips
        # unresolvable tracks silently, so the character binds and never moves.
        '"retarget/bone_renamer/unique_node/make_unique": false,\n'
        '"retarget/rest_fixer/apply_node_transforms": true,\n'
        '"retarget/rest_fixer/fix_silhouette/enable": true,\n'
        '"retarget/rest_fixer/fix_silhouette/filter": [],\n'
        '"retarget/rest_fixer/fix_silhouette/threshold": 15.0,\n'
        '"retarget/rest_fixer/keep_global_rest_on_leftovers": true,\n'
        '"retarget/rest_fixer/normalize_position_tracks": true,\n'
        '"retarget/rest_fixer/reset_all_bone_poses_after_import": true\n'
        "}\n"
        "}\n"
        "}"
    ) % bone_map_res


def inject_subresources(import_path: Path, bone_map_res: str) -> bool:
    """Puts the retarget options into an FBX's .import.

    Godot writes an empty `_subresources={}` into every scene .import, so this
    replaces that key. Appending a second one leaves the empty block winning and
    the options are silently ignored.

    Args:
        import_path: The FBX's `.import` sidecar, after a first import pass.
        bone_map_res: `res://` path of the BoneMap the options should reference.

    Returns:
        True when written. False when the file already carries a non-empty block,
        which is left untouched rather than clobbered.

    Raises:
        ValueError: The file has no `_subresources` key at all, so it is not a
            scene .import and anything written would be rewritten away.
    """
    text = import_path.read_text(encoding="utf8")
    if "_subresources=" not in text:
        raise ValueError("no _subresources key in %s" % import_path.name)
    if "_subresources={}" not in text:
        return False
    import_path.write_text(
        text.replace("_subresources={}", render_subresources(bone_map_res), 1),
        encoding="utf8",
    )
    return True
