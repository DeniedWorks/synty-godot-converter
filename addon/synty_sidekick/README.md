# Synty Sidekick for Godot

Assemble Synty Sidekick characters at runtime and change their parts, gear,
proportions and colours while the game is running.

This addon is installed by `synty_library.py` when it converts a SIDEKICK pack.
It reads the parts library that conversion writes to your project root:
`sidekick_parts.json`, `sidekick_gear_sets.json` and `sidekick_colors.json`.

## Why parts are assembled rather than swapped

Synty gear is **body-mesh replacement, not attachment**. A knight's breastplate
*is* the torso mesh. Most gear sets span several body slots at once — the
largest covers 27 — so nothing can be equipped by parenting a prop to a bone,
and a wardrobe cannot be pre-baked as finished characters without producing one
scene per combination.

There is also no naked body underneath. `clear_slot()` therefore reverts to a
loadout you nominate with `set_base_loadout()`, not to some intrinsic bare mesh.

## Quick start

```gdscript
extends Node3D

const SidekickCharacter := preload("res://addons/synty_sidekick/sidekick_character.gd")

func _ready() -> void:
    var character: Node3D = SidekickCharacter.new()
    add_child(character)
    character.load_library("res://")

    # A skeleton to hang the parts on. Pass your own, or let it build the
    # modal rig from the library.
    character.set_base_skeleton(character.create_base_skeleton())

    # A complete character is one gear set from each of the three body regions.
    for set_id in ["<head set>", "<upper set>", "<lower set>"]:
        character.equip_set(set_id)
    character.set_base_loadout()

    character.set_proportions(0.0, 25.0, 60.0)   # body type, size, muscle
    character.load_animations()
    character.play("A_Base_Locomotion_Idle_Standing_Masc")
```

Run the included viewer to browse what your conversion produced and find real
set ids: open `addons/synty_sidekick/sidekick_viewer.tscn` and press play.

## API

| Call | Does |
|---|---|
| `load_library(root)` | Reads the parts index, gear sets and colour tables. Returns `false` if none are there. |
| `create_base_skeleton()` | Builds the rig most parts share. |
| `set_base_skeleton(skeleton)` | Use a skeleton you already have instead. |
| `equip_set(set_id)` | Wears every part of a gear set, across all the slots it covers. |
| `set_part(slot, part_id)` | Replaces one slot. |
| `clear_slot(slot)` | Reverts that slot to the base loadout. |
| `set_base_loadout()` | Records what is worn now as the fallback for `clear_slot()`. |
| `set_proportions(body_type, body_size, muscle)` | Blend-shape sliders, each −100..100. |
| `apply_color_preset(preset_id)` | Recolours from the master palette. |
| `recolour(slot_group, colour)` | Changes one colour group; skin and gear are separate, so armour never disturbs skin. |
| `load_animations()` / `play(clip)` | Binds the converted libraries and plays a clip. |
| `graft_missing_bones()` | Adds a part's own bones — capes and pouches carry their own. Called for you by `equip_set` and `set_part`. |

## Things that will bite you

**Assign `skin` after `add_child()`.** A part added to the tree without its skin
already assigned stays in bind pose while the skeleton animates. The addon does
this correctly; it matters if you assemble parts yourself.

**Zero is not neutral for proportions.** The defaults are 50/0/50 in Synty's
terms. Leaving the blend shapes unset renders every character fully masculine
and unmuscled, which looks like a bug and is not.

**Joint offsets are applied per frame, not baked into rests.** An animation
rewrites the attachment joints every frame, so an offset folded into the rest is
discarded the moment a clip plays and gear snaps back mid-swing. The node
re-applies them from `_process` with `process_priority = 100`, which puts it
after the AnimationPlayer.

**A part can render bright red under the wrong palette.** Each Synty character
ships a 32×32 `ColorMap`, and Synty fills the slots that character does not use
with pure red. A part whose UVs point at an unused slot renders red — the
texture loaded fine, it simply defines no colour there. Mixing parts across
characters needs each part rendered with the palette it was authored against, or
the master palette.

**An `_Additive_` clip is not playable on its own.** Synty's libraries ship
additive clips - `A_MOD_GBL_BodyLook_Additive_D_Neut` and the like - whose tracks
are deltas meant to be blended over a base pose in an `AnimationTree`. Hand one
to `play()` and it is applied as an absolute pose: the character folds up, head
and neck collapsing into the torso, looking exactly like a broken rig. It is not
broken. Filter `animation_clips()` on `_Additive_` before offering clips to a
player, or blend them properly.

**Without `Side_Kick_Data.db` there are no joint adjustments.** That database
ships with Synty's Sidekick Unity tool and never inside a `.unitypackage`. Three
things degrade without it, and all three look like bugs:

- Attachment joints do not follow body size, so a large character's backpack
  sits where a small one's would.
- There are no colour tables and no master palette, so `recolour()` and
  `apply_color_preset()` do nothing. Synty's **base body parts carry no colour
  of their own** - they exist to be painted by the palette - so a bare body
  renders plain white. That is the missing palette, not a missing texture.
- Gear sets fall back to what part names imply: whole characters rather than the
  database's three mix-and-match regions, and every set's `group` reads
  `unknown`. Measured on a databaseless conversion of SIDEKICK_Starter: 15 sets
  instead of the database's 532.

Characters still assemble, swap and animate.

## Updating

`synty_library.py` refreshes `addons/synty_sidekick/` on every run, so edits you
make inside this folder are overwritten. Subclass `sidekick_character.gd` or
copy it elsewhere in your project instead.
