# Synty Converter - Session Handoff Prompt

**Copy everything below this line and paste into a new Claude Code session:**

---

## Project: synty-converter

I need you to continue work on the **synty-converter** project. Here's the complete context from our previous session.

### Project Location & Purpose

**Location:** `C:\Godot\Projects\synty-converter\`

**What it does:** A 12-step Python pipeline that converts Unity Synty asset packs (from `C:\SyntyComplete\`) into fully-functional Godot 4.6 projects with proper materials, shaders, and mesh-to-scene conversion.

**Godot Version:** 4.6 (executable at `C:\Godot\Godot_v4.6-stable_mono_win64\Godot_v4.6-stable_mono_win64.exe`)

---

### Pipeline Overview (12 Steps)

| Step | Name | File | Function |
|------|------|------|----------|
| 1 | Validate Inputs | converter.py | `parse_args()` |
| 2 | Create Output Directories | converter.py | `setup_output_directories()` |
| 3 | Extract Unity Package | unity_package.py | `extract_unitypackage()` |
| 4 | Parse Unity Materials | unity_parser.py | `parse_material_bytes()` |
| 5 | Detect Shaders & Map Properties | shader_mapping.py | `detect_shader_type()`, `map_material()` |
| 6 | Generate .tres Files | tres_generator.py | `generate_tres()` |
| 7 | Copy Shaders | converter.py | `copy_shaders()` |
| 8 | Copy Textures | converter.py | `copy_textures()` |
| 8.5 | Copy FBX Files | converter.py | `copy_fbx_files()` |
| 9 | Parse MaterialList.txt | material_list.py | `parse_material_list()` |
| 10 | Generate mesh_material_mapping.json | material_list.py | `generate_mesh_material_mapping_json()` |
| 10.5 | Check Missing Materials | converter.py | (inline) |
| 11 | Generate project.godot | converter.py | `generate_project_godot()` |
| 12 | Run Godot CLI | converter.py + godot_converter.gd | `run_godot_cli()` |

---

### What We Learned This Session

#### Texture Resolution Problem (CRITICAL)
- **Issue:** Materials render pink/gray because textures are missing
- **Root Cause:** GUID-to-filename resolution fails when .unitypackage internal names don't match SourceFiles folder names
- **Current flow:** `.unitypackage -> GUID -> filename -> search SourceFiles -> copy file`
- **Solution:** Extract texture bytes directly from .unitypackage, write to output from memory

#### Shader Detection Problem
- **Issue:** Foliage doesn't animate, crystals aren't refractive (wrong shader assigned)
- **Finding:** Code does NOT stop early at polygon GUID (as initially thought)
- **Real problems:**
  - Too few GUIDs for foliage (only 5) and crystal (only 2)
  - Threshold too high (20 points requires 2+ matches)
  - MaterialList has `uses_custom_shader` flag that's parsed but **never used**

#### Auto-Enable Rules Incomplete
- **Current rules:** Only 5 texture-based + 1 triplanar prefix
- **Total `enable_*` uniforms across all shaders:** 34
- **Missing coverage:** polygon overlays, snow, triplanar variants, foliage emission/wind, crystal effects, water normals/foam/caustics

#### Parameter Mapping Issues
- Many Unity params map to non-existent Godot uniforms (hologram, ghost, neon, CRT effects, interior mapping)
- Global uniform OceanWavesGradient is empty but water shader expects a texture

#### The 3 Shaders That Matter Most
1. **polygon.gdshader** - Default shader for most materials (basic PBR)
2. **foliage.gdshader** - Wind animation for trees/plants
3. **crystal.gdshader** - Refractive effects for gems/ores

---

### Key Decisions Made

| Decision | Rationale |
|----------|-----------|
| Extract textures from .unitypackage (not SourceFiles) | Guarantees GUID-to-bytes resolution; eliminates name-matching failures |
| Use MaterialList `uses_custom_shader` as PRIMARY shader signal | `False` = polygon immediately; `True` = continue detection |
| Output to `output/PACKNAME/` structure | Pack name from source_files parent folder; isolates each pack |
| Keep all 7 shaders as-is | Already configured and working |
| Keep property mappings as-is | Unity-to-Godot name translations are necessary |

---

### Prioritized Changes

#### P0 - Critical (Fix broken functionality)

1. **Extract textures from .unitypackage**
   - Modify Step 3 (`unity_package.py`) to extract texture bytes, not just GUID-to-filename
   - Modify Step 8 (`converter.py`) to write extracted bytes to output instead of copying from SourceFiles
   - Result: `GuidMap.guid_to_content` includes texture data

2. **Use MaterialList for shader detection**
   - Parse MaterialList BEFORE shader detection (currently after in Step 9)
   - In `shader_mapping.py`: if `uses_custom_shader == False`, return polygon immediately
   - If `True`, continue to GUID/name/property scoring

3. **Change output structure**
   - Output to `output/{PACKNAME}/` where PACKNAME = parent folder of `--source-files`
   - Example: `C:\SyntyComplete\PolygonNature\SourceFiles` produces `output/PolygonNature/`

#### P1 - Important (Improve accuracy)

4. **Improve shader detection scoring**
   - Add more foliage/crystal GUIDs to `SHADER_GUID_MAP`
   - Add name patterns: `Fol_`, `Canopy_`, `Ore_`, `Mineral_`, `Gem_`
   - Lower threshold from 20 to 15 when GUID is unknown
   - Add texture-based detection: presence of `_Leaf_*` textures suggests foliage

5. **Expand auto-enable rules**
   - Map all 34 `enable_*` uniforms to their trigger conditions

#### P2 - Polish (Quality improvements)

6. **High-quality texture imports** - Generate `.import` files or set project-wide defaults
7. **Dynamic project name** - Use pack name instead of "Synty Converted Assets"
8. **Track missing material warnings** - Add to `stats.warnings`

#### P3 - Consider (Low priority)

9. **Remove input validation** - Errors will surface naturally

---

### Critical File Paths

**Python Pipeline:**
- `C:\Godot\Projects\synty-converter\converter.py` - Main orchestration
- `C:\Godot\Projects\synty-converter\unity_package.py` - .unitypackage extraction
- `C:\Godot\Projects\synty-converter\unity_parser.py` - .mat file parsing
- `C:\Godot\Projects\synty-converter\shader_mapping.py` - Shader detection & property mapping
- `C:\Godot\Projects\synty-converter\tres_generator.py` - .tres generation
- `C:\Godot\Projects\synty-converter\material_list.py` - MaterialList.txt parsing

**Godot Shaders:**
- `C:\Godot\Projects\synty-converter\shaders\polygon.gdshader` - Default (most materials)
- `C:\Godot\Projects\synty-converter\shaders\foliage.gdshader` - Wind animation
- `C:\Godot\Projects\synty-converter\shaders\crystal.gdshader` - Refractive

**GDScript:**
- `C:\Godot\Projects\synty-converter\godot_converter.gd` - Mesh-to-scene conversion

**Documentation:**
- `C:\Godot\Projects\synty-converter\docs\architecture.md`
- `C:\Godot\Projects\synty-converter\docs\shader-reference.md`
- `C:\Godot\Projects\synty-converter\docs\user-guide.md`

---

### Detailed Plan File

Full plan with implementation notes: `C:\Users\alexg\.claude\plans\abundant-orbiting-walrus.md`

---

### Items to Revisit Later

- [ ] Review water/skydome/clouds/particles shaders (edge cases)
- [ ] Investigate OceanWavesGradient global uniform (empty but expected)
- [ ] Consider placeholder materials for missing references
- [ ] Review godot_converter.gd collision mesh handling

---

### How to Run the Converter

```bash
cd C:\Godot\Projects\synty-converter
python converter.py --package "C:\SyntyComplete\PolygonNature\PolygonNature.unitypackage" --source-files "C:\SyntyComplete\PolygonNature\SourceFiles"
```

---

**What would you like me to work on?** The P0 items are the most critical - they fix broken texture resolution and shader detection.
