# Retarget API Reference

> **For the pipeline context:** See [Step 12: Godot Conversion](../steps/12-godot-conversion.md)

## Overview

The `retarget` module makes Synty animation packs bind to Synty character rigs.

An animation clip poses only the rig whose rest orientations it was authored against, because almost every track is an **absolute local rotation** rather than a delta from rest - only about four bones carry position tracks at all. Synty's character rigs and clip rigs disagree, so binding one to the other collapses the character.

Godot's scene importer can rewrite both onto a common profile (`SkeletonProfileHumanoid`) given a `BoneMap`. This module builds that map from a file's real bones and writes it into the FBX's `.import` file, where the importer reads it as `_subresources`.

**Module Location:** `retarget.py`

---

## Functions

### resolve_bone_map(bones) -> tuple[dict[str, str], list[str]]

Resolves the Polygon template against one file's actual bones.

| Parameter | Type | Description |
|-----------|------|-------------|
| `bones` | `dict[str, Vector]` | Bone name to rest position, read from the FBX |

**Returns:** `(resolved, missing)` - the profile-bone to rig-bone mapping that this file can actually satisfy, and the profile bones it cannot.

---

### render_bone_map(resolved) -> str

Renders a resolved mapping as `BoneMap` `.tres` content.

### render_subresources(bone_map_res) -> str

Builds the `retarget/` option block, keyed by the skeleton's node path.

### inject_subresources(import_path, bone_map_res) -> bool

Writes the retarget options into an FBX's `.import` file. Returns `True` when the file was modified.

| Parameter | Type | Description |
|-----------|------|-------------|
| `import_path` | `Path` | The FBX's `.import` file |
| `bone_map_res` | `str` | `res://` path of the `BoneMap` resource |

---

## POLYGON_BONE_MAP

Maps each `SkeletonProfileHumanoid` bone to its Polygon rig equivalent. An empty string means the profile bone has no equivalent in a Synty rig and is deliberately left unmapped - Godot keeps such bones under their original names. Synty rigs have no ring or little finger, and no separate eye or jaw bones.

---

## Notes

- **Rest agreement** (the dot product of corresponding rest directions) gates whether a retargeted clip binds cleanly. It does not distinguish Sidekick libraries from one another: they all sit around 0.97-0.98.
- **`_Additive_` clips are deltas for an `AnimationTree`**, not playable poses. Playing one directly folds a character up and looks exactly like a broken rig. This is the most common false alarm when checking retargeting by eye.
- `converter.py` retargets only with `--retarget`; `synty_library.py` retargets by default and takes `--no-retarget` to skip it. Without retargeting characters still convert, but clips will not bind to them.
