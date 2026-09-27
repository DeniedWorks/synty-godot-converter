# Sidekick API Reference

> **For the runtime side:** See [addon/synty_sidekick/README.md](../../addon/synty_sidekick/README.md)

## Overview

The `sidekick` module reads Synty's SIDEKICK packs, which are a modular character creator rather than a set of finished characters. A character is not one FBX: it is a recipe naming one part mesh per body slot, with every part skinned to the same 88-bone rig.

That recipe ships with the pack as a plain-text `.sk` file. This module parses those recipes, resolves each part to a mesh in the pack's `models/` directory, and writes JSON that `godot_converter.gd` and the runtime addon consume.

Some Sidekick features live in `Side_Kick_Data.db`, a SQLite database that ships with Synty's Unity-side Sidekick **tool** rather than in any `.unitypackage`. Every function that reads it degrades cleanly when it is absent - see [Database-optional behaviour](#database-optional-behaviour).

**Module Location:** `sidekick.py`

---

## Data Classes

### SidekickBlendShapes

A character's body proportions, as three slider values in `-100..100` (`body_size`, `muscle`, `body_shape`).

### SidekickPart

One mesh filling one body slot of a Sidekick character: the part name, its slot, and the resolved mesh path.

### SidekickRecipe

One Sidekick character as described by its `.sk` file: name, species, parts, and blend shape values.

---

## Functions

### parse_sk_bytes(data) -> SidekickRecipe | None

Parses one `.sk` recipe from raw bytes. Returns `None` when the bytes are not a recipe.

| Parameter | Type | Description |
|-----------|------|-------------|
| `data` | `bytes` | Contents of a `.sk` file |

---

### build_sidekick_recipes(guid_map, source_dirs, models_dir) -> dict[str, SidekickRecipe]

Collects and resolves every Sidekick recipe available for a pack.

| Parameter | Type | Description |
|-----------|------|-------------|
| `guid_map` | `GuidMap` | Provides `guid_to_sk_content` and `texture_guid_to_name` |
| `source_dirs` | `list[Path]` | Directories searched recursively for `.sk` files |
| `models_dir` | `Path` | The pack's output `models/` directory, already populated |

Recipes come from the `.unitypackage` and from `--source-files`. The latter wins on a name collision: a recipe saved into the user's Unity project is a character they built with the Sidekick tool, which is the likelier edit.

---

### parse_part_name(part_name) -> dict[str, str] | None

Splits a Sidekick part name into its components (`species`, `family`, `set`, `slot`, ...). Returns `None` for a name that does not follow the convention.

### slot_for_part_name(part_name) -> str

Reads just the body slot out of a part name.

---

### find_sidekick_database(source_dirs) -> Path | None

Locates `Side_Kick_Data.db`. Searches the given directories recursively; pass a Unity project's `Assets/Synty` root rather than a pack folder, since the tool installs to `Assets/Synty/SidekickCharacters/Database/` and matches no pack name.

### load_rig_adjustments(db_path) -> dict[str, dict[str, dict]]

Reads per-joint offsets and rotations, so attachment joints follow body proportions.

### load_part_presets(db_path) -> dict[str, dict]

Reads Synty's curated gear sets, partitioned by `sk_part_preset.part_group`.

### load_color_tables(db_path) -> dict

Reads colour slots and palette presets used by the runtime palette baker.

### find_master_color_map(source_dirs) -> Path | None

Locates Synty's master 32x32 `ColorMap` texture.

---

### derive_gear_sets_from_names(part_names) -> dict[str, dict]

Groups parts into wearable sets using only the family and number in their names - the fallback when the database is absent.

Sets are partitioned by `SLOT_GROUPS`, which maps each of the 38 body slots to `head`, `upper`, or `lower` (14/13/11 slots). The partition is a property of the slot, not of the database, so mix-and-match wardrobes work with no database present.

---

### write_sidekick_characters_json(recipes, output_path, \*, indent=2) -> None
### write_sidekick_rig_adjustments_json(adjustments, output_path, \*, indent=2) -> None
### write_sidekick_gear_sets_json(sets, output_path, \*, indent=2) -> None
### write_sidekick_colors_json(tables, output_path, \*, indent=2) -> None

Serialise each table for `godot_converter.gd` and the runtime addon. All take an output `Path` and an optional JSON `indent`.

---

## Constants

| Constant | Description |
|----------|-------------|
| `SIDEKICK_DATABASE_NAME` | `"Side_Kick_Data.db"` |
| `SIDEKICK_PARTS_DIRNAME` | `"sidekick_parts"` - output directory for extracted part meshes |
| `SIDEKICK_SLOT_CODES` | Recipe slot code to slot name, e.g. `"01HEAD"` -> `"Head"` |
| `SLOT_GROUPS` | Each of the 38 body slots mapped to `head` / `upper` / `lower` |
| `COLOR_UNSET` | `"FF0000"` - the value a recipe uses for an unset colour slot |

---

## Database-optional behaviour

A user who owns a SIDEKICK pack but not Synty's Unity tool has no `Side_Kick_Data.db`. Three features degrade rather than fail:

| Feature | With the database | Without it |
|---------|-------------------|------------|
| Gear sets | Synty's curated presets via `load_part_presets()` | Derived from part names via `derive_gear_sets_from_names()` |
| Colour palettes | Named palette presets via `load_color_tables()` | Characters keep their baked recipe colours |
| Rig adjustments | Attachment joints follow body proportions | Joints stay at their rest positions |

Pass `--unity-assets` (CLI) or set `ConversionConfig.sidekick_database` to supply the database when it is available.
