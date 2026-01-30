# Synty Converter - Session Handoff Document

**Date:** 2026-01-30
**Project:** `C:\Godot\Projects\synty-converter\`
**Purpose:** Convert Unity Synty asset packs to Godot 4.6 projects with proper materials, shaders, and scene files.

---

## What Was Accomplished (P0 - Critical Fixes)

### 1. Output Structure Change - DONE

**Location:** `converter.py` - `run_conversion()` function (lines 1157-1164)

Changed output from flat `output/` to `output/{PACKNAME}/`:
- Pack name extracted from `source_files.parent.name`
- Example: `C:\SyntyComplete\PolygonNature\SourceFiles` produces `output/PolygonNature/`
- Pack name is sanitized via `sanitize_filename()` to remove invalid filesystem characters

```python
# Extract pack name from source_files parent directory
raw_pack_name = config.source_files.parent.name
pack_name = sanitize_filename(raw_pack_name)
pack_output_dir = config.output_dir / pack_name
```

### 2. Texture Extraction from .unitypackage - DONE

**Location:** `unity_package.py` - `GuidMap` class and `extract_unitypackage()` function

Added `texture_guid_to_path` field to `GuidMap` dataclass (line 75):
```python
texture_guid_to_path: dict[str, Path] = field(default_factory=dict)
```

New function `_extract_textures_to_temp()` (lines 387-423):
- Extracts texture bytes from .unitypackage during parsing
- Writes to temp files with GUID-based names
- Returns mapping: texture GUID -> temp file Path

**Location:** `converter.py` - `copy_textures()` function (lines 506-666)

Enhanced to try temp files first, fall back to SourceFiles:
- Added `texture_guid_to_path` and `texture_name_to_guid` parameters
- First checks if texture exists in temp files from package
- Falls back to `find_texture_file()` searching SourceFiles
- Added try/finally cleanup for temp directory (lines 1437-1441)

### 3. Shader Detection Overhaul - DONE

**Location:** `shader_mapping.py` - New functions at bottom of file (lines 1830-2012)

New detection flow:
1. **MaterialList check:** If `uses_custom_shader=False` -> `polygon.gdshader` immediately
2. **Name patterns:** If `uses_custom_shader=True` -> score-based pattern matching
3. **Default:** If no pattern match, use `polygon.gdshader` but flag as unmatched for logging

New functions:
- `detect_shader_from_name(material_name)` - Name-only pattern matching (lines 1838-1881)
- `determine_shader(material_name, uses_custom_shader)` - Main entry point for new flow (lines 1884-1931)

**Location:** `converter.py` - `build_shader_cache()` function (lines 1057-1112)

LOD inheritance implemented:
- First mesh (LOD0) determines shader for all LODs by slot index
- Shader decisions cached by material name
- Returns tuple: `(shader_cache, unmatched_materials)`

```python
# LOD inheritance: LOD0's slot 0 shader -> all LODs' slot 0
if is_lod0:
    shader, matched = determine_shader(mat_name, slot.uses_custom_shader)
    prefab_slot_shaders[slot_idx] = shader
else:
    # Inherit from LOD0's slot
    if slot_idx in prefab_slot_shaders:
        shader_cache[mat_name] = prefab_slot_shaders[slot_idx]
```

### 4. Auto-Enable Rules Expansion - DONE

**Location:** `tres_generator.py` - `AUTO_ENABLE_RULES` dict (lines 71-114)

Expanded from 6 to 23 rules:

| Texture Parameter | Enables |
|------------------|---------|
| `normal_texture` | `enable_normal_texture` |
| `emission_texture` | `enable_emission_texture` |
| `ao_texture` | `enable_ambient_occlusion` |
| `overlay_texture` | `enable_overlay_texture` |
| `triplanar_normal_top/side/bottom` | `enable_triplanar_normals` |
| `triplanar_emission_texture` | `enable_triplanar_emission` |
| `leaf_normal` | `enable_leaf_normal` |
| `trunk_normal` | `enable_trunk_normal` |
| `emissive_mask` | `enable_emission` |
| `emissive_2_mask` | `enable_emission` |
| `trunk_emissive_mask` | `enable_emission` |
| `emissive_pulse_mask` | `enable_pulse` |
| `top_albedo` | `enable_top_projection` |
| `top_normal` | `enable_top_projection` |
| `refraction_texture` | `enable_refraction` |
| `water_normal_texture` | `enable_normals` |
| `shore_foam_noise_texture` | `enable_shore_foam` |
| `foam_noise_texture` | `enable_global_foam` |
| `noise_texture` | `enable_global_foam` |
| `scrolling_texture` | `enable_top_scrolling_texture` |
| `caustics_flipbook` | `enable_caustics` |

**Location:** `shader_mapping.py` - Texture mappings (lines 369-508)

Added mappings for texture properties that trigger auto-enable:
- Foliage: `_Emissive_Mask`, `_Emissive_2_Mask`, `_Emissive_Pulse_Map`, `_Trunk_Emissive_Mask`
- Polygon: `_Overlay_Texture`, `_Triplanar_Normal_Texture_*`, `_Triplanar_Emission_Texture`
- Crystal: `_Top_Albedo`, `_Top_Normal`
- Water: `_Foam_Texture`, `_Noise_Texture`, `_Shore_Foam_Noise_Texture`

---

## What Still Needs To Be Done

### P1 - Verify ALL Unity Properties (NOT DONE)

**Task:** Extract and verify ALL texture/float/color properties from ALL .unitypackage files

**Why:** Current mappings may be incomplete. Need to ensure no Unity properties are being silently dropped.

**Scope:** 40+ .unitypackage files in `C:\SyntyComplete\`

**Process:**
1. Open each .unitypackage (tar.gz format)
2. Find `/asset` files where `/pathname` ends in `.mat`
3. Parse YAML content for:
   - `m_TexEnvs` section: texture properties (format: `- _Property_Name:`)
   - `m_Floats` section: float properties (format: `- _Property_Name: value`)
   - `m_Colors` section: color properties (format: `- _Property_Name: {r:...}`)
4. Collect unique property names across all packs
5. Compare against `TEXTURE_MAP_*`, `FLOAT_MAP_*`, `COLOR_MAP_*` in `shader_mapping.py`
6. Add any missing mappings

**Script idea:**
```python
import tarfile
from pathlib import Path

def extract_unity_properties(package_path):
    """Extract all unique property names from a .unitypackage"""
    textures, floats, colors = set(), set(), set()

    with tarfile.open(package_path, "r:gz") as tar:
        for member in tar.getmembers():
            # Find .mat files and parse for properties
            pass

    return textures, floats, colors
```

### P2 - Polish Items (NOT DONE)

1. **High-quality texture imports**
   - Generate `.import` files for each texture with `filter=false` for pixel art look
   - Or set project-wide import defaults in `project.godot`

2. **Dynamic project name**
   - Change `PROJECT_GODOT_TEMPLATE` (line 87) to use pack name
   - Currently hardcoded as `"Synty Converted Assets"`

3. **Track missing material warnings in stats**
   - Add count of missing materials to `ConversionStats`
   - Currently logs warnings but doesn't track in stats

### P3 - Testing (NOT DONE)

1. Run converter on actual packs to verify:
   - Textures render correctly (not pink/gray)
   - Shader detection works (foliage animates, crystals refract)
   - LOD inheritance works
   - Auto-enable rules trigger correctly

2. Test packs to prioritize:
   - `PolygonNature` - has foliage, water, triplanar terrain
   - `PolygonFantasyKingdom` - has crystals
   - `PolygonSciFi` - has emission, holograms

---

## Key Files Modified This Session

| File | Changes |
|------|---------|
| `converter.py` | Pack-based output structure, shader cache with LOD inheritance, temp file cleanup |
| `unity_package.py` | Added `texture_guid_to_path` field, `_extract_textures_to_temp()` function |
| `shader_mapping.py` | New `determine_shader()`, `detect_shader_from_name()` functions, expanded texture mappings |
| `tres_generator.py` | Expanded `AUTO_ENABLE_RULES` from 6 to 23 rules |

---

## Key Architectural Decisions

### 1. Texture Resolution Strategy
**Decision:** Extract textures from .unitypackage to temp files, SourceFiles as fallback

**Rationale:**
- GUID-to-filename resolution fails when package internal names don't match SourceFiles names
- Package textures are the exact files referenced by materials
- SourceFiles fallback handles cases where textures are excluded from package

### 2. Shader Detection Hierarchy
**Decision:** MaterialList `uses_custom_shader` flag is primary, name patterns secondary

**Rationale:**
- GUID-based detection has coverage gaps (only ~50 GUIDs mapped)
- Property-based detection adds complexity without reliability
- MaterialList explicitly marks custom shader usage
- Name patterns handle remaining ambiguity

**Flow:**
```
MaterialList.uses_custom_shader == False?
    -> polygon.gdshader (immediate)
MaterialList.uses_custom_shader == True?
    -> Name pattern matching (score >= 20)
        -> Matched shader
    -> No match
        -> polygon.gdshader (log for manual review)
```

### 3. LOD Inheritance
**Decision:** LOD0's shader applies to all LODs by slot index

**Rationale:**
- LOD meshes often have simplified names missing shader hints
- Same slot index across LODs should use same shader
- Maintains visual consistency across LOD levels

### 4. Auto-Enable Rules
**Decision:** Texture presence triggers enable flags

**Rationale:**
- When artists assign a texture, they expect the feature to work
- Manual enable after texture assignment is error-prone
- Safe: enabling without texture just means shader checks a null texture

---

## Reference: Deprecated Version

**Location:** `C:\Godot\Projects\DEPRECATED\synty-converter-RED\`

Contains analysis of 29 Unity packages (~3,300 materials). The current version has MORE mappings than deprecated, but deprecated version may have useful reference data for property verification task.

---

## How to Run the Converter

```bash
cd C:\Godot\Projects\synty-converter

python converter.py ^
    --unity-package "C:\SyntyComplete\PolygonNature\PolygonNature.unitypackage" ^
    --source-files "C:\SyntyComplete\PolygonNature\SourceFiles" ^
    --output "C:\Godot\Projects\output" ^
    --godot "C:\Godot\Godot_v4.6-stable_mono_win64\Godot_v4.6-stable_mono_win64.exe" ^
    --verbose
```

**Flags:**
- `--dry-run` - Preview without writing files
- `--skip-fbx-copy` - Use if models/ already populated
- `--skip-godot-cli` - Generate materials only, no .tscn files
- `--godot-timeout 600` - Timeout for Godot CLI operations (seconds)

---

## Pipeline Overview (12 Steps)

| Step | Name | Function | File |
|------|------|----------|------|
| 1 | Validate Inputs | `parse_args()` | converter.py |
| 2 | Create Output Directories | `setup_output_directories()` | converter.py |
| 3 | Extract Unity Package | `extract_unitypackage()` | unity_package.py |
| 4 | Parse Unity Materials | `parse_material_bytes()` | unity_parser.py |
| 4.5 | Parse MaterialList (early) | `parse_material_list()` | material_list.py |
| 4.6 | Build Shader Cache | `build_shader_cache()` | converter.py |
| 5 | Map Material Properties | `map_material()` | shader_mapping.py |
| 6 | Generate .tres Files | `generate_tres()` | tres_generator.py |
| 7 | Copy Shaders | `copy_shaders()` | converter.py |
| 8 | Copy Textures | `copy_textures()` | converter.py |
| 8.5 | Copy FBX Files | `copy_fbx_files()` | converter.py |
| 9 | Generate mesh_material_mapping.json | `generate_mesh_material_mapping_json()` | material_list.py |
| 10 | Check Missing Materials | (inline) | converter.py |
| 11 | Generate project.godot | `generate_project_godot()` | converter.py |
| 12 | Run Godot CLI | `run_godot_cli()` | converter.py |

---

## Critical File Paths

**Python Pipeline:**
- `C:\Godot\Projects\synty-converter\converter.py` - Main orchestration (1484 lines)
- `C:\Godot\Projects\synty-converter\unity_package.py` - .unitypackage extraction (567 lines)
- `C:\Godot\Projects\synty-converter\unity_parser.py` - .mat file parsing
- `C:\Godot\Projects\synty-converter\shader_mapping.py` - Shader detection & property mapping (2072 lines)
- `C:\Godot\Projects\synty-converter\tres_generator.py` - .tres generation (690 lines)
- `C:\Godot\Projects\synty-converter\material_list.py` - MaterialList.txt parsing

**Godot Shaders:**
- `C:\Godot\Projects\synty-converter\shaders\polygon.gdshader` - Default (most materials)
- `C:\Godot\Projects\synty-converter\shaders\foliage.gdshader` - Wind animation
- `C:\Godot\Projects\synty-converter\shaders\crystal.gdshader` - Refractive
- `C:\Godot\Projects\synty-converter\shaders\water.gdshader` - Depth-based water
- `C:\Godot\Projects\synty-converter\shaders\particles.gdshader` - Soft particles
- `C:\Godot\Projects\synty-converter\shaders\skydome.gdshader` - Procedural sky
- `C:\Godot\Projects\synty-converter\shaders\clouds.gdshader` - Volumetric clouds

**GDScript:**
- `C:\Godot\Projects\synty-converter\godot_converter.gd` - Mesh-to-scene conversion

**Documentation:**
- `C:\Godot\Projects\synty-converter\docs\architecture.md`
- `C:\Godot\Projects\synty-converter\docs\shader-reference.md`
- `C:\Godot\Projects\synty-converter\docs\user-guide.md`
- `C:\Godot\Projects\synty-converter\docs\api\*.md` - API reference for each module

---

## Items to Revisit Later

- [ ] Review water/skydome/clouds/particles shaders (edge cases)
- [ ] Investigate `OceanWavesGradient` global uniform (empty but water shader expects texture)
- [ ] Consider placeholder materials for missing references (currently just warns)
- [ ] Review `godot_converter.gd` collision mesh handling
- [ ] Add GUID mappings for packs not yet analyzed

---

## Next Session Prompt

Copy and paste this to start the next session:

```
I'm continuing work on the synty-converter project at C:\Godot\Projects\synty-converter\

Please read the handoff document at C:\Godot\Projects\synty-converter\docs\SESSION_HANDOFF.md for full context.

The main task remaining is to verify ALL Unity properties from ALL .unitypackage files in C:\SyntyComplete\ and ensure the shader_mapping.py has complete coverage.
```

---

## Quick Reference: Key Code Locations

### Shader Detection Flow
```
converter.py:build_shader_cache()
    -> shader_mapping.py:determine_shader()
        -> If uses_custom_shader=False: return "polygon.gdshader"
        -> If uses_custom_shader=True: shader_mapping.py:detect_shader_from_name()
            -> Pattern matching with scoring
            -> Return matched shader or "polygon.gdshader" (unmatched)
```

### Texture Copy Flow
```
converter.py:copy_textures()
    -> Check texture_guid_to_path (from .unitypackage temp files)
    -> If found: copy from temp file
    -> If not found: converter.py:find_texture_file() (search SourceFiles)
    -> If still not found: log warning
```

### Material Generation Flow
```
converter.py:run_conversion()
    -> shader_mapping.py:map_material() (with override_shader from cache)
        -> Property mapping using TEXTURE_MAP_*, FLOAT_MAP_*, COLOR_MAP_*
        -> Boolean conversion for toggle floats
        -> Alpha=0 fix for colors
        -> Default value application
    -> tres_generator.py:generate_tres()
        -> Auto-enable rules check
        -> Build ext_resources (shader + textures)
        -> Build shader_parameters
        -> Format as .tres file
```

---

**End of Session Handoff Document**
