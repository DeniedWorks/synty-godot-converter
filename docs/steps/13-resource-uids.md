# Step 13: Resource UIDs

This document covers the final pipeline step, which gives every generated scene and material a stable `uid://` address.

**Related Files:**
- `tres_generator.py` - Contains `uid_for_path()` and `stamp_resource_uids()`
- `converter.py` - Runs the stamping pass as Step 13
- `godot_converter.gd` - Saves the scenes that this step then stamps

**Related Documentation:**
- [API: tres_generator](../api/tres_generator.md) - Function reference
- [Step 7: TRES Generation](07-tres-generation.md) - Where material UIDs are written inline
- [Step 12: Godot Conversion](12-godot-conversion.md) - Where scenes are produced

---

## Overview

Godot 4 addresses resources two ways: by path (`res://Pack/materials/M.tres`) and by UID (`uid://dtw1bypimep`). The UID is what survives a file being moved or renamed, and it is what the editor writes into new references.

**Godot assigns a UID only when the editor saves a resource.** It never assigns one on import, and `ResourceSaver.save()` assigns none. A generated project therefore ends up with every resource unaddressable by UID - and the editor never backfills them. Running `--headless --editor --quit` over a full project and re-checking confirms this: 0 of 42 resources gained a UID.

The symptom users hit: generated materials and scenes do not resolve through `uid://`, and references to them break on any move instead of following the file.

## Two Writing Points

A UID is written where the resource is created, when the Python side creates it, and stamped afterwards when Godot creates it.

| Resource | Created by | UID written |
|----------|-----------|-------------|
| `.tres` materials | `tres_generator.generate_tres()` | Inline, from the `res_path` argument (Step 7) |
| `.tscn` scenes | `godot_converter.gd` via `ResourceSaver` | Stamped in this step |
| `.res` binary resources | `godot_converter.gd` | Not stamped - the header is not text to patch |

The Godot side saves scenes from a dozen call sites, so stamping them in one pass afterwards is simpler and less error-prone than threading a UID through each of them.

## Derivation

`uid_for_path()` derives the UID from the resource's `res://` path rather than at random:

```python
value = int(hashlib.md5(res_path.encode("utf8")).hexdigest()[:15], 16)
return "uid://" + _encode_uid(value)
```

- **Path-derived, so stable.** Re-converting a pack produces the same UIDs, so references into it survive a re-run. A random UID would invalidate them every time.
- **60 bits**, comfortably inside the positive range Godot masks ids into, and far enough from a birthday collision for a library of any size.
- **Base 34**, matching `ResourceUID::id_to_text`: `a`-`z` map to 0-25 and `0`-`9` map to 25-34. Note the overlap - `z` and `0` both decode to 25, and Godot's own encoder never emits `z` or `9`.

## The Stamping Pass

```python
stamped = stamp_resource_uids(pack_output_dir, project_dir)
```

- Walks `.tscn` and `.tres` files recursively under the pack's output folder
- Skips anything under `.godot`, which Godot regenerates and must not be edited
- Only touches a first line that is a `[gd_scene ...]` or `[gd_resource ...]` tag
- Leaves a header that already has `uid=` alone, so re-runs are idempotent

**Why `project_root` is a separate argument:** the scan covers one pack's folder, but `res://` paths are relative to the Godot project root. Deriving a UID from a pack-relative path would give the same UID to same-named materials in two different packs. Passing the real project root keeps them distinct.

## Dry Run Handling

Skipped entirely under `--dry-run`, along with the conversion log - there is nothing on disk to stamp.

## Verification

After a conversion, all resources in a pack should be registered, resolve to their own path, and load through `uid://`. A reconverted pack was checked in the editor: 56 of 56 resources resolved.

Unit coverage lives in `tests/test_resource_uid.py` (15 tests), including a reference decoder that reverses Godot's `id_to_text` and collision tests across packs.

## Known Gap

Texture `.import` files still carry the random UIDs Godot generates at import time. Nothing references textures by UID - materials reference them by path - so this is a wart rather than a bug.
