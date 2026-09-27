# Synty Library API Reference

> **For the user-facing walkthrough:** See the README's [Getting started](../../README.md) section

## Overview

`converter.py` converts one pack and has to be told where that pack's meshes live. Across a library that becomes three mechanical decisions per pack:

- **Which packs are left?** A pack whose folder already exists under the output has been converted, so a re-run resumes rather than starting over.
- **Where are its meshes?** Either an already-imported Unity folder, or the `.unitypackage` itself.
- **What kind of pack is it?** Meshes, UI sprites, or animation clips - each takes a different route.

The `synty_library` module makes those decisions from the contents of each package and runs the whole library in one command. Conversion happens **in-process**, not by spawning `converter.py`, so the frozen PyInstaller build works the same as a source checkout.

**Module Location:** `synty_library.py`
**CLI:** `python synty_library.py --packages ... --godot ... --output ...`

---

## CLI Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--packages` | yes | Directory holding your `.unitypackage` files |
| `--godot` | yes | Path to the Godot console executable (`_console.exe` on Windows) |
| `--output` | yes | Godot project directory to build |
| `--unity-assets` | no | A Unity project's `Assets/Synty`, used as the mesh source for packs already imported there, and where `Side_Kick_Data.db` is found |
| `--work-dir` | no | Where to stage FBX extracted from packages. Must sit outside the Godot project, or Godot imports every mesh twice |
| `--no-retarget` | no | Skip rig retargeting |
| `--godot-timeout` | no | Per-pack Godot timeout in seconds (default 3600) |
| `--force` | no | Re-convert packs whose output folder already exists |
| `--only` | no | Comma-separated substrings; convert only matching packages |
| `--dry-run` | no | List what would be converted, by which route, and stop |

---

## Functions

### convert_library(args, report=print) -> int

Converts every package in a folder into one Godot project. Returns a process exit code: `1` if any pack failed, else `0`.

| Parameter | Type | Description |
|-----------|------|-------------|
| `args` | `argparse.Namespace` | Parsed CLI arguments (see above) |
| `report` | `Callable[[str], None]` | Where progress lines go. The GUI passes a queue writer instead of `print` |

Each pack is converted inside its own `try/except`, so one failure does not end the run. Output for a pack goes to a per-pack log file.

---

### process(package, args, log_dir) -> dict

Converts one package by whichever route its contents call for. Returns a result record with `pack`, `status` (`ok` / `partial` / `failed` / `skipped`), `detail`, and `seconds`.

### convert_mesh_pack(package, pack_name, source, args, log_path) -> tuple[bool, str]

Converts one mesh pack in this process, redirecting logging and stdout to `log_path`.

### convert_ui_pack(package, pack_name, output) -> tuple[bool, str]

Writes a UI pack's sprites where Godot imports them as textures unaided.

### install_addon(output, report=print) -> int

Copies the Sidekick runtime addon into the converted project. Returns the number of files copied.

### collect_warnings(output, results) -> list[str]

Names the degradations a user would otherwise discover by accident - a missing Sidekick database, a pack converted without its source meshes.

---

## Classification Helpers

| Function | Description |
|----------|-------------|
| `normalise(name)` | Reduces a pack or folder name to a form both naming conventions share |
| `find_unity_source(pack_name, unity_assets)` | Locates a pack's already-imported Unity folder, if it has a usable one |
| `has_meshes(counts)` | True when a pack has meshes for the converter to work on |
| `has_sprites(counts)` | True when a pack's images are a UI sprite set, not mesh textures |
| `is_animation_pack(counts)` | True for a pack that is mostly animation clips rather than assets |
| `resolve_work_dir(output, work_dir)` | Decides where FBX extracted from packages are staged |

---

## Constants

| Constant | Description |
|----------|-------------|
| `REPO_ROOT` | Resolved from `__file__`, so it works inside a PyInstaller bundle |
| `ADDON_SOURCE` | `addon/synty_sidekick`, the runtime addon installed into the output project |
| `SKIP_PREFIXES` | `("ParrelSync",)` - package name prefixes that are never converted |
| `MIN_UNITY_SOURCE_FBX` | `2` - fewest FBX a Unity folder must hold to count as a usable mesh source |
| `SPRITE_DOMINANCE` | `10` - a pack takes the UI route when it has more than this many PNGs per FBX |
