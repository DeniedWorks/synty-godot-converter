# Synty Converter - Session Handoff Document

**Last Updated:** 2026-01-30
**Project:** `C:\Godot\Projects\synty-converter\`
**Purpose:** Convert Unity Synty asset packs to Godot 4.6 projects with proper materials, shaders, and scene files.

---

## What Was Done This Session (2026-01-30)

### 1. Shader Property Validation (COMMITTED: 14243a7)

**Location:** `shader_mapping.py`

**THE PROBLEM:**
Old Synty packs (like PolygonNature) mark materials as "Uses custom shader" in MaterialList.txt, so our name-based detection correctly identifies them as foliage/water/etc. However, the Unity `.mat` files in these older packs only have generic properties like `_MainTex` and `_BumpMap` - they do NOT have shader-specific properties like `_Leaf_Texture` or `_Trunk_Texture`.

This caused a silent failure: we assigned `foliage.gdshader` to these materials (correct shader choice), but the texture mapping failed because `foliage.gdshader` expects a `leaf_color` uniform, while the material only had data for `base_texture` (from `_MainTex`). Result: textures did not display even though the shader was correct.

**THE SOLUTION:**
Before applying a specialized shader, we now validate that the material actually HAS any shader-specific properties. If the material only has generic Unity properties (`_MainTex`, `_BumpMap`, `_Color`), we fall back to `polygon.gdshader` which correctly handles those generic properties.

**Implementation:**
- Added `SHADER_SPECIFIC_PROPERTIES` dict defining unique properties per shader:
  - `foliage`: `_Leaf_Texture`, `_Trunk_Texture`, `_Leaf_Color`, etc.
  - `crystal`: `_Crystal_Color`, `_Fresnel_*`, `_Refraction_*`, etc.
  - `water`: `_Water_Color`, `_Shallow_Color`, `_Depth_*`, etc.
  - `particles`: `_Soft_Factor`, `_Camera_Fade_*`, etc.
  - `skydome`: `_Sky_Color_*`, `_Sun_*`, `_Cloud_*`, etc.
  - `clouds`: `_Cloud_*`, `_Edge_*`, etc.

- Added `validate_shader_properties()` function to check if materials have shader-specific properties
- Materials detected as specialized shaders via name patterns now validate they have proper properties
- If no shader-specific properties found, falls back to `polygon.gdshader`

### 2. Transparency/Alpha Fix (COMMITTED: 2bbac05)

**Location:** `shader_mapping.py`

**THE PROBLEM:**
The converter had an "alpha fix" that changed `alpha=0` to `alpha=1.0` for all color values. This was originally intended to fix a Unity quirk where opaque materials store colors with `alpha=0` even though they should be fully opaque.

However, glass and transparent materials INTENTIONALLY have low alpha values (e.g., 0.23-0.47) for transparency. The blanket fix was overwriting these intentional alpha values, making glass materials appear opaque instead of transparent.

**THE SOLUTION:**
Unity's `_Mode` property tells us the intended rendering mode:
- `0` = Opaque (alpha fix needed - Unity stores with alpha=0)
- `1` = Cutout (transparent, preserve alpha)
- `2` = Fade (transparent, preserve alpha)
- `3` = Transparent (transparent, preserve alpha)

If `_Mode >= 1`, we skip the alpha fix and preserve the original alpha value. This allows glass, windows, and other transparent materials to render correctly while still fixing the alpha=0 issue for opaque materials.

**Implementation:**
- Check `_Mode` property before applying alpha fix
- Only apply "alpha=0 -> alpha=1.0" fix when `_Mode == 0` (Opaque) or `_Mode` is not set
- Materials with `_Mode >= 1` now preserve original alpha values
- This fixes glass, windows, cutout leaves, and fade particles appearing opaque

### 3. Material Name Fallback (IN PROGRESS - needs commit)

**Location:** `godot_converter.gd`

**THE PROBLEM:**
Synty has inconsistent naming between MaterialList.txt and their Unity `.mat` files:

| Source | Example Name |
|--------|--------------|
| MaterialList.txt references | `PolygonFantasyKingdom_Mat_Castle_Wall_01` |
| Unity `.mat` file `m_Name` | `Castle_Wall_01` |

The Python converter generates `.tres` files using the short name from the `.mat` file (e.g., `Castle_Wall_01.tres`). But when the GDScript tries to apply materials to meshes, it looks for the long name from MaterialList.txt. Result: material files exist but are not found because of the name mismatch.

**THE SOLUTION:**
Added a fallback chain in `godot_converter.gd` that tries multiple name variations:

1. **Exact name match** - Try the name as-is from MaterialList.txt
2. **Strip prefix** - Remove `Polygon*_Mat_` or `Polygon*_` prefix patterns
3. **Add suffix** - Try with `_01` suffix if not already present (some materials reference base name without variant number)

**Secondary fix:** Changed `FileAccess.file_exists()` to `ResourceLoader.exists()` because `FileAccess` does not work with `res://` paths when running Godot in headless/CLI mode. `ResourceLoader.exists()` is the correct API for checking if resources exist at `res://` paths.

**Implementation:**
- Added `find_material_path()` function with the fallback chain
- Uses regex to strip pack-specific prefixes: `r"^Polygon[A-Za-z]+_(Mat_)?"`
- Result: Fantasy Kingdom improved from 511 meshes without materials to only 171 (edge cases)

### 4. Created analyze_multi_materials.py Utility Script

**Location:** `analyze_multi_materials.py` (new file)

- Analyzes MaterialList.txt files to find prefabs with 2+ materials
- Helps identify naming patterns for leaves vs trunk materials

---

## Current State

- synty-converter has uncommitted changes in `godot_converter.gd` (the material fallback fix)
- 4 packs converted and ready for testing:
  - `C:\Godot\Projects\PolygonNature` (working)
  - `C:\Godot\Projects\EnchantedForest` (working)
  - `C:\Godot\Projects\SciFiCity` (working, glass now transparent)
  - `C:\Godot\Projects\FantasyKingdom` (working, 171 meshes still need materials)

---

## What's Next / Remaining Issues

1. **Commit the godot_converter.gd changes**
2. **171 meshes without materials in Fantasy Kingdom are edge cases:**
   - `*_Static` variants (not in MaterialList)
   - FX/particle meshes
   - Some preset/composite meshes
3. **Older packs (PolygonNature) have static foliage** - could add name-based forcing for "Leaves" materials
4. **Could investigate why some materials still don't match**

---

## Previous Session: What Was Accomplished (P0 - Critical Fixes)

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

## Previous Session: What Was Accomplished (P1 - Property Verification) - DONE

### P1 - Verify ALL Unity Properties - COMPLETED 2026-01-30

**Task:** Extract and verify ALL texture/float/color properties from ALL .unitypackage files

**Result:** Analyzed 29 packages with 3,400+ material files.

**Script Created:** `extract_unity_properties.py`
- Opens .unitypackage as tar.gz
- Builds GUID -> pathname mapping
- Parses .mat files for m_TexEnvs, m_Floats, m_Colors sections
- Extracts property names using indentation-aware parsing

**Mappings Added:** 113 new property mappings including:

| Category | New Mappings |
|----------|-------------|
| **Snow System** | `_Snow_Normal_Texture`, `_Snow_Metallic_Smoothness_Texture`, `_Snow_Edge_Noise`, `_Snow_Transition`, `_Snow_Metallic`, `_Snow_Smoothness`, `_Snow_Normal_Intensity` |
| **Detail Maps** | `_DetailAlbedoMap`, `_DetailNormalMap`, `_DetailMask`, `_DetailNormalMapScale` |
| **Triplanar** | `_Triplanar_Fade`, `_Triplanar_Intensity`, `_Triplanar_Normal_Intensity_Top/Side/Bottom` |
| **Particles** | Alpha clip variants, emission, camera fade smoothness |
| **Water** | `_Shore_Wave_Foam_Noise_Texture`, `_Water_Noise_Texture`, depth properties, caustics intensity |
| **SciFi Cubemaps** | `_BackTex`, `_FrontTex`, `_LeftTex`, `_RightTex`, `_UpTex`, `_DownTex` |
| **Boolean Flags** | `_Wind_Enabled`, `_Enable_Detail_Map`, `_Enable_Parallax`, `_Enable_AO`, `_Enable_Shore_Waves`, `_Enable_Ocean_Wave` |

**Commits:**
- `8bce757` - Checkpoint before analysis
- `661155f` - Add extract script and 113 new mappings
- `8491a3a` - Fix mapping inconsistencies from code review
- `ea02e1e` - P2 polish items
- `a006e88` - Support existing Godot projects
- `0c126bc` - Simplify output structure
- `98e0f85` - Remove shaders/ from pack folder

**Packages Analyzed (29 total, 3,400+ materials):**

| # | Package Name | .mat Files |
|---|--------------|------------|
| 1 | POLYGON_Nature | 78 |
| 2 | POLYGON_Samurai_Empire | 226 |
| 3 | POLYGON_NatureBiomes_EnchantedForest | 109 |
| 4 | POLYGON_Fantasy_Kingdom | 92 |
| 5 | POLYGON_NatureBiomes_AlpineMountain | 139 |
| 6 | POLYGON_NatureBiomes_AridDesert | 108 |
| 7 | POLYGON_NatureBiomes_MeadowForest | 130 |
| 8 | POLYGON_NatureBiomes_SwampMarshland | 82 |
| 9 | POLYGON_NatureBiomes_TropicalJungle | 123 |
| 10 | POLYGON_Pirate | 21 |
| 11 | POLYGON_SciFi_City | 60 |
| 12 | POLYGON_SciFi_Worlds | 107 |
| 13 | POLYGON_CyberCity | 219 |
| 14 | POLYGON_Horror_Asylum | 127 |
| 15 | POLYGON_Horror_Carnival | 84 |
| 16 | POLYGON_Horror_Mansion | 181 |
| 17 | POLYGON_SciFi_Horror | 289 |
| 18 | POLYGON_Viking_Realm | 163 |
| 19 | POLYGON_Apocalypse | 111 |
| 20 | POLYGON_Nightclubs | 104 |
| 21 | POLYGON_Vikings | 15 |
| 22 | POLYGON_City | 67 |
| 23 | POLYGON_City_Zombies | 13 |
| 24 | POLYGON_Dark_Fantasy | 105 |
| 25 | POLYGON_Dark_Fortress | 153 |
| 26 | POLYGON_ElvenRealm | 127 |
| 27 | POLYGON_Pro_Racer | 230 |
| 28 | POLYGON_Military | 111 |
| 29 | POLYGON_Modular_Fantasy_Hero | 33 |
| 30 | POLYGON_Dungeon_Realms | 74 |
| 31 | POLYGON_Street_Racer | 116 |
| 32 | POLYGON_Kaiju | 49 |
| 33 | POLYGON_War | 57 |
| 34 | POLYGON_Mech | 35 |
| 35 | POLYGON_Casino | 96 |
| 36 | POLYGON_Gang_Warfare | 29 |
| 37 | POLYGON_SciFi_Space | 113 |
| 38 | POLYGON_Ancient_Egypt | 115 |
| 39 | POLYGON_Fantasy_Rivals | 26 |
| 40 | POLYGON_AncientEmpire | 131 |
| 41 | POLYGON_Kids | 20 |
| 42 | POLYGON_Goblin_War_Camp | 45 |
| 43 | POLYGON_Dungeon | 42 |
| 44 | POLYGON_Dwarven_Dungeon_Map | 56 |
| 45 | POLYGON_Dungeon_Map | 1 |

**To analyze additional packs:**
```bash
python extract_unity_properties.py "C:\SyntyComplete\YOUR_PACK.unitypackage"
```

---

## Key Files Modified This Session (2026-01-30)

| File | Changes |
|------|---------|
| `shader_mapping.py` | Added `SHADER_SPECIFIC_PROPERTIES` dict, `validate_shader_properties()` function, fixed alpha handling for transparent materials |
| `godot_converter.gd` | Added `find_material_path()` fallback function, fixed `ResourceLoader.exists()` usage |
| `analyze_multi_materials.py` | New utility script for analyzing multi-material prefabs |

---

## What Still Needs To Be Done

### Immediate (Next Session)

1. **Commit godot_converter.gd changes** - Material name fallback fix is uncommitted
2. **Address remaining 171 meshes in Fantasy Kingdom** - Edge cases like `*_Static` variants

### P2 - Polish Items - DONE (Previous Session)

1. **High-quality texture imports** - DONE
   - Generate `.import` files for each texture with VRAM compressed + high_quality
   - Textures now import with optimal settings for 3D assets

2. **Dynamic project name** - DONE
   - `project.godot` now uses pack name dynamically
   - Example: `PolygonNature` produces project named "PolygonNature"

3. **Track missing material warnings in stats** - DONE
   - Added `materials_missing: int = 0` field to `ConversionStats`
   - Counter incremented in Step 9.5 after calculating missing materials

### P2.5 - Output Structure Simplification - DONE (Previous Session)

Simplified output to one consistent structure:

```
output/
├── project.godot          # At project root (merged if existing)
├── shaders/               # At project root
│   ├── polygon.gdshader
│   ├── foliage.gdshader
│   └── ...
└── PackName/              # Pack assets in subfolder
    ├── materials/
    ├── models/
    ├── textures/
    └── scenes/
```

**Key changes:**
- `project.godot` and `shaders/` always at project root
- Pack assets organized in subfolder named after pack
- Supports existing Godot projects - shader uniforms merge into existing `project.godot`
- Multiple packs can coexist in same project

**Commits:**
- `a006e88` - Support existing Godot projects
- `0c126bc` - Simplify output structure
- `98e0f85` - Remove shaders/ from pack folder

### P3 - Testing - PARTIALLY DONE

**Tested packs:**
- `PolygonNature` - working
- `EnchantedForest` - working
- `SciFiCity` - working, glass now transparent
- `FantasyKingdom` - working, 171 meshes still need materials

**Previous bugs fixed:**
- **Shader Texture Mapping Gaps (2026-01-30):**
  - SM_Plant materials were getting correct shader (foliage.gdshader) but textures didn't display
  - Root cause: Common Unity properties (`_MainTex`, `_BaseMap`, `_BumpMap`) weren't mapped for shader-specific uniforms
  - **Fixes applied to `shader_mapping.py`:**
    - FOLIAGE: Added `_MainTex`→`leaf_color`, `_BaseMap`→`leaf_color`, `_BumpMap`→`leaf_normal`, `_EmissionMap`→`emissive_mask`
    - CRYSTAL: Added `_BaseMap`→`base_albedo`
    - WATER: Fixed 11 mappings using wrong uniform names (`water_normal_texture`→`normal_texture`, `foam_noise_texture`→`noise_texture`)
    - PARTICLES: Removed invalid `_EmissionMap` mapping, added `_BaseMap`→`albedo_map`
    - SKYDOME: Cleared to empty dict (shader is procedural, no texture uniforms)

---

## Key Files Modified Previous Sessions

| File | Changes |
|------|---------|
| `converter.py` | Pack-based output structure, shader cache with LOD inheritance, temp file cleanup |
| `unity_package.py` | Added `texture_guid_to_path` field, `_extract_textures_to_temp()` function |
| `shader_mapping.py` | New `determine_shader()`, `detect_shader_from_name()` functions, expanded texture mappings, fixed shader-specific TEXTURE_MAP_* dictionaries |
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

Immediate tasks:
1. Commit the uncommitted changes in godot_converter.gd (material name fallback fix)
2. Address the remaining 171 meshes without materials in Fantasy Kingdom (edge cases like *_Static variants)
3. Consider adding name-based forcing for "Leaves" materials in older packs like PolygonNature
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
