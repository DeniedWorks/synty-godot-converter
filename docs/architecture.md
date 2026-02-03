# Architecture

Technical architecture documentation for the Synty Unity-to-Godot Converter.

## Table of Contents

- [System Overview](#system-overview)
- [Module Dependency Graph](#module-dependency-graph)
- [Module Responsibilities](#module-responsibilities)
- [Data Flow (12-Step Pipeline)](#data-flow-12-step-pipeline)
- [Key Design Decisions](#key-design-decisions)
- [Extension Points](#extension-points)
- [Step Documentation Reference](#step-documentation-reference)

---

## System Overview

The Synty Converter follows a single core philosophy: **shaders do the heavy lifting**.

The converter's job is straightforward - wire Unity materials to the correct Godot shader with correct textures and parameters. All the visual complexity (wind animation, water caustics, crystal refraction) lives in the 7 community drop-in shaders from GodotShaders.com.

This approach has several advantages:

1. **Maintainability**: Shader behavior changes require zero converter code changes
2. **Accuracy**: Community shaders are already tested to match Unity's Synty shaders
3. **Simplicity**: The converter is purely a data transformation pipeline
4. **Upgradability**: Shaders can be updated independently of the converter

### Input Sources

| Source | Purpose | Location |
|--------|---------|----------|
| Unity Package | Material definitions, shader GUIDs, texture references | `.unitypackage` file |
| SourceFiles | FBX models, high-quality textures | `SourceFiles/` folder |
| MaterialList.txt | Mesh-to-material mappings | `SourceFiles/MaterialList.txt` |

### Output Artifacts

| Artifact | Purpose |
|----------|---------|
| `.tres` files | Godot ShaderMaterial definitions (per-pack in `PACK_NAME/materials/`) |
| `.gdshader` files | 7 drop-in replacement shaders (shared in `shaders/`) |
| `.tscn` files | Individual mesh scene files (per-pack in `PACK_NAME/meshes/`) |
| `project.godot` | Godot project with global shader uniforms |
| `PACK_NAME/mesh_material_mapping.json` | Mesh-to-material mapping for Godot CLI (per-pack) |
| `converter_config.json` | Runtime configuration for the GDScript converter (pack_name, mesh_scale, output_subfolder, flatten_output) |
| `conversion_log.txt` | Conversion summaries (appends for each pack) |

---

## Module Dependency Graph

```
converter.py ──┬── unity_package.py
               │      └── (tarfile, gzip - stdlib)
               │
               ├── unity_parser.py
               │      └── (re - stdlib)
               │
               ├── shader_mapping.py
               │      └── unity_parser.py (UnityMaterial type)
               │
               ├── tres_generator.py
               │      └── shader_mapping.py (MappedMaterial type)
               │
               └── material_list.py
                      └── (json - stdlib)

gui.py ────────┬── converter.py (ConversionConfig, run_conversion)
               ├── customtkinter (external dependency)
               └── settings.json (persisted to %APPDATA%\SyntyConverter\)

godot_converter.gd ── (runs inside Godot headless)
               └── reads converter_config.json, mesh_material_mapping.json

External Dependencies:
- Godot 4.6 CLI (headless mode for FBX import and mesh extraction)
- Python 3.10+ (standard library only - no pip packages required for CLI)
- CustomTkinter (optional, required only for GUI: pip install customtkinter)
```

### Import Flow

```python
# converter.py imports:
from unity_package import extract_unitypackage, GuidMap, get_material_guids, get_material_name
from unity_parser import parse_material_bytes, UnityMaterial
from shader_mapping import map_material, detect_shader_type, determine_shader, MappedMaterial
from tres_generator import generate_tres, write_tres_file, sanitize_filename
from material_list import parse_material_list, generate_mesh_material_mapping_json
```

---

## Module Responsibilities

| Module | Input | Output | Responsibility |
|--------|-------|--------|----------------|
| `converter.py` | CLI arguments | Converted Godot project | Main orchestrator - runs 12-step pipeline, handles errors, writes logs |
| `gui.py` | User input | Converted Godot project | Optional CustomTkinter GUI wrapper for converter.py |
| `unity_package.py` | `.unitypackage` file | `GuidMap` dataclass | Extract tar/gzip archive, build GUID mappings, extract textures to temp |
| `unity_parser.py` | `.mat` file bytes | `UnityMaterial` dataclass | Parse Unity YAML using regex, extract textures/floats/colors |
| `shader_mapping.py` | `UnityMaterial` | `MappedMaterial` dataclass | 3-tier shader detection, property name translation, Unity quirk fixes |
| `tres_generator.py` | `MappedMaterial` | `.tres` file content | Generate Godot ShaderMaterial resource format |
| `material_list.py` | `MaterialList.txt` | mesh-to-material dict | Parse Unity material list, generate JSON for Godot CLI |
| `godot_converter.gd` | FBX files + config JSON | `.tscn` scene files | GDScript for Godot CLI - extract meshes, assign materials |

### Data Structures

```python
# unity_parser.py
@dataclass
class TextureRef:
    guid: str                          # 32-char hex GUID
    scale: tuple[float, float] = (1.0, 1.0)
    offset: tuple[float, float] = (0.0, 0.0)

@dataclass
class Color:
    r: float
    g: float
    b: float
    a: float

@dataclass
class UnityMaterial:
    name: str
    shader_guid: str
    tex_envs: dict[str, TextureRef]    # property_name -> TextureRef
    floats: dict[str, float]           # property_name -> value
    colors: dict[str, Color]           # property_name -> Color

# shader_mapping.py
@dataclass
class MappedMaterial:
    name: str
    shader_file: str                   # e.g., "foliage.gdshader"
    textures: dict[str, str]           # godot_param -> texture_filename
    floats: dict[str, float]           # godot_param -> value
    bools: dict[str, bool]             # godot_param -> value
    colors: dict[str, tuple]           # godot_param -> (r, g, b, a)

# unity_package.py
@dataclass
class GuidMap:
    guid_to_pathname: dict[str, str]       # guid -> Unity asset path
    guid_to_content: dict[str, bytes]      # guid -> raw .mat file bytes
    texture_guid_to_name: dict[str, str]   # guid -> texture filename
    texture_guid_to_path: dict[str, Path]  # guid -> temp file path
```

---

## Data Flow (12-Step Pipeline)

### Step 1: Validate Inputs

```
Check existence of:
  - Unity package (.unitypackage file)
  - SourceFiles directory
  - SourceFiles/Textures subdirectory
  - Godot executable

Fatal error if any missing.
```

### Step 2: Create Output Directories

```
output/
  shaders/      # Drop-in .gdshader files
  textures/     # Copied from SourceFiles/Textures
  materials/    # Generated .tres ShaderMaterials
  models/       # Copied FBX files (structure preserved)
  meshes/       # Mesh output organized by configuration
    tscn_separate/   # --mesh-format tscn (default)
    tscn_combined/   # --mesh-format tscn --keep-meshes-together
    res_separate/    # --mesh-format res
    res_combined/    # --mesh-format res --keep-meshes-together
```

### Step 3: Extract Unity Package

The `.unitypackage` format is a gzip-compressed tar archive. Each asset is stored as:

```
<guid>/
  asset           # The actual file content
  asset.meta      # Unity metadata
  pathname        # Plain text path within Unity project
```

**Output**: `GuidMap` dictionary mapping GUIDs to Unity asset paths.

### Step 4: Parse Unity Materials

For each `.mat` file found in the package:

1. Read raw bytes from tar archive
2. Decode as UTF-8 (Unity YAML format)
3. Extract using regex (not YAML parser - see [Design Decisions](#why-regex-over-yaml-parser))
4. Build `UnityMaterial` with:
   - Material name (`m_Name`)
   - Shader GUID (`m_Shader.guid`)
   - Texture references (`m_TexEnvs` with GUIDs)
   - Float properties (`m_Floats`)
   - Color properties (`m_Colors`)

### Step 5: Detect Shaders and Map Properties

**Three-tier shader detection**:

1. **GUID Lookup** (primary): Check `SHADER_GUID_MAP` for 56 known Unity shader GUIDs
2. **Name Pattern Scoring**: Match material name against weighted patterns
3. **Property-Based Detection**: Analyze material properties for shader hints

**Property mapping**:
- Translate Unity property names to Godot parameter names
- Apply Unity quirk fixes (alpha=0 colors, boolean-as-float)
- Apply shader-specific defaults for missing properties

**Output**: `MappedMaterial` with Godot-compatible property names.

#### LOD Inheritance for Shader Detection

The converter implements LOD inheritance to ensure visual consistency across all LOD levels of a mesh. This is handled by the `build_shader_cache()` function in `converter.py`:

1. **LOD0 is authoritative**: The shader decision made for LOD0 applies to all LODs of the same prefab
2. **Consistent appearance**: This ensures LOD1, LOD2, LOD3 all use the same shader as LOD0
3. **Cache built early**: The shader cache is populated before material mapping begins

**Example**: If `SM_Prop_Chair_01_LOD0` uses the polygon shader, then `SM_Prop_Chair_01_LOD1`, `SM_Prop_Chair_01_LOD2`, and `SM_Prop_Chair_01_LOD3` will also use the polygon shader, regardless of what their material properties might otherwise suggest.

The shader cache maps prefab base names to their determined shader:

```python
# shader_cache populated by build_shader_cache()
shader_cache = {
    "SM_Prop_Chair_01": "polygon.gdshader",
    "SM_Env_Tree_01": "foliage.gdshader",
    "SM_Prop_Crystal_01": "crystal.gdshader",
}
```

This prevents jarring visual discontinuities when meshes transition between LOD levels at different distances from the camera.

### Step 6: Resolve Shader Paths

Before generating materials, the converter searches the entire project for existing shader files:

1. **Search**: Look for each shader file (e.g., `polygon.gdshader`) anywhere in the project
2. **Reuse**: If found, use that path (e.g., `res://my_custom_location/polygon.gdshader`)
3. **Copy**: If not found, copy to `shaders/` and use `res://shaders/polygon.gdshader`

This prevents duplicate shaders when converting multiple packs or when users relocate shaders.

### Step 7: Generate .tres Files

For each `MappedMaterial`, generate a Godot ShaderMaterial resource.

**Smart Material Filtering**: When using `--filter`, materials are only generated if they are used by matching FBX files. This is determined by cross-referencing MaterialList.txt with the filter pattern.

```ini
[gd_resource type="ShaderMaterial" load_steps=3 format=3]

[ext_resource type="Shader" path="res://shaders/foliage.gdshader" id="1"]
[ext_resource type="Texture2D" path="res://textures/Leaf_01.png" id="2"]

[resource]
shader = ExtResource("1")
shader_parameter/leaf_color = ExtResource("2")
shader_parameter/leaf_smoothness = 0.1
shader_parameter/enable_breeze = true
```

### Step 8: Copy Textures

Copy only textures that are actually referenced by generated materials:

1. Build set of required texture names from all materials
2. **Smart filtering**: When using `--filter`, cross-reference with filtered materials to only include textures needed by matching FBX files (can reduce texture count by 90%+)
3. Search `.unitypackage` extracted textures first (primary source)
4. Search `SourceFiles/Textures` as fallback
5. Copy to `output/PACK_NAME/textures/`
6. Generate `.import` files with compression settings:
   - **Default**: Lossless compression (mode=0) for faster Godot import times
   - **High quality**: BPTC compression (mode=2) when `--high-quality-textures` is used
7. Log warnings for missing textures

### Step 9: Copy FBX Files

Copy FBX models from `SourceFiles/FBX` to `output/models/`:

- Preserve directory structure (Props/, Environment/, Characters/, etc.)
- Skip non-FBX files
- Can be skipped with `--skip-fbx-copy` flag

### Step 10: Generate Mesh Material Mapping

**Note:** MaterialList.txt parsing now happens in Step 4.5 to enable shader cache building for LOD inheritance. Step 10 generates the JSON file from the cached prefab data.

Generates `PACK_NAME/mesh_material_mapping.json` for the Godot CLI converter:

```json
{
  "SM_Prop_Crystal_01": ["Crystal_Mat_01", "PolygonNature_Mat_01"],
  "SM_Env_Tree_01_LOD0": ["Tree_Trunk_Mat", "Tree_Leaves_Mat"]
}
```

**Per-pack mapping**: Each pack has its own mapping file in its folder. This enables incremental multi-pack workflows where converting Pack B doesn't need to re-read Pack A's mapping.

Also checks for materials referenced by meshes but not generated (adds to warnings).

### Step 11: Generate project.godot

Write Godot project file with global shader uniforms required by drop-in shaders:

| Uniform | Type | Purpose |
|---------|------|---------|
| `WindDirection` | vec3 | Direction for foliage wind animation |
| `WindIntensity` | float | Strength of wind effect |
| `GaleStrength` | float | Storm/gust intensity |
| `MainLightDirection` | vec3 | Sun direction for clouds/sky |
| `SkyColor` | color | Sky gradient top |
| `EquatorColor` | color | Sky gradient middle |
| `GroundColor` | color | Sky gradient bottom |
| `OceanWavesGradient` | sampler2D | Wave displacement texture |

### Step 12: Run Godot CLI

Two-phase Godot headless execution:

**Phase 1: Import**
```bash
godot --headless --import --path <project_dir>
```
- Godot processes all FBX files
- Generates `.import` metadata files
- Can timeout on large packs (configurable with `--godot-timeout`)

**Phase 2: Convert**
```bash
godot --headless --script res://godot_converter.gd --path <project_dir>
```
- Reads `converter_config.json` for runtime options:
  - `pack_name`: Specific pack folder to process (enables incremental conversion)
  - `mesh_format`: Output format (tscn or res)
  - `filter_pattern`: FBX filename filter
  - `mesh_scale`: Scale factor for mesh vertices (e.g., 100 for undersized packs)
  - `keep_meshes_together`: Whether to combine meshes per FBX
- Reads `PACK_NAME/mesh_material_mapping.json` for material assignments
- Loads each FBX as PackedScene, finds all MeshInstance3D nodes
- Applies mesh_scale to vertex positions if not 1.0
- Applies materials as surface overrides with fallback logic
- Handles collision meshes with green wireframe debug material
- Saves as individual `.tscn` files or combined scenes (configurable)

See [Step 12: Godot Conversion](steps/12-godot-conversion.md) for detailed implementation.

---

## Multi-Pack Architecture

The converter supports incremental multi-pack conversion to a single Godot project.

### Pack Isolation

Each pack is converted to its own subfolder:
```
project/
  POLYGON_Fantasy/
    textures/
    materials/
    meshes/
      tscn_separate/          # Mesh subfolders by configuration
      res_combined/           # Multiple configs can coexist
    models/
    mesh_material_mapping.json
  POLYGON_Nature/
    textures/
    materials/
    meshes/
      tscn_separate/
    models/
    mesh_material_mapping.json
  shaders/                    # Shared across all packs
  project.godot
  conversion_log.txt          # Appends for each conversion
```

### Existing Pack Detection

When re-running on a pack that already has `materials/`, `textures/`, `models/`, and `mesh_material_mapping.json`, the converter detects this and skips phases 3-10. Only mesh generation runs, outputting to the appropriate `meshes/{format}_{mode}/` subfolder. This enables quick iteration on mesh format/mode options without re-processing textures and materials.

### Smart Shader Discovery

The `get_shader_paths()` function implements dynamic shader discovery:

1. **Search**: For each required shader, search the entire project tree
2. **Reuse**: If found (even if relocated by user), use that path in material references
3. **Copy**: If not found, copy to `shaders/` directory

This prevents shader duplication when:
- Converting a second pack to the same project
- Users have moved shaders to custom locations

### Incremental Processing

The `converter_config.json` includes a `pack_name` field:

```json
{
  "pack_name": "POLYGON_Nature",
  "keep_meshes_together": false,
  "mesh_format": "tscn",
  "filter_pattern": null,
  "mesh_scale": 1.0
}
```

When `pack_name` is set, `godot_converter.gd` only processes that specific pack folder, leaving other packs untouched.

### Append-Mode Logging

`write_conversion_log()` appends to `conversion_log.txt` rather than overwriting, accumulating summaries across multiple pack conversions with timestamps for each entry.

---

## Key Design Decisions

### Why Regex Over YAML Parser

Unity `.mat` files use non-standard YAML 1.1 with custom tags:

```yaml
%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!21 &2100000
Material:
  m_Name: MyMaterial
  m_Shader: {fileID: 4800000, guid: abc123, type: 3}
```

Standard YAML parsers (PyYAML, ruamel) fail on the `!u!21` tags. Rather than preprocessing or using Unity-specific libraries, we use targeted regex extraction:

```python
# Extract shader GUID
shader_match = re.search(r'm_Shader:.*?guid:\s*([a-f0-9]{32})', content)

# Extract textures section
texenvs_match = re.search(r'm_TexEnvs:(.*?)(?=m_Ints:|m_Floats:|m_Colors:|$)', content, re.DOTALL)
```

**Benefits**:
- No external dependencies (pure stdlib)
- Handles Unity's non-standard YAML
- Extracts exactly what we need
- ~10x faster than full YAML parsing

### Why GUID-First Shader Detection

Unity shader GUIDs are stable identifiers that persist across Unity versions and asset updates. Using GUIDs as the primary detection method:

1. **Accuracy**: Direct mapping to exact Unity shader
2. **Reliability**: GUIDs don't change when materials are renamed
3. **Completeness**: Handles shaders with non-descriptive names
4. **Performance**: O(1) dictionary lookup vs O(n) pattern matching

The `SHADER_GUID_MAP` currently contains 56 known GUIDs covering:
- Core Synty shaders (PolygonLit, Foliage, Particles)
- Pack-specific shaders (SciFi, Horror, Viking, Racing)
- Legacy shaders (Amplify-based from 2021)

### Why Scoring System for Name Patterns

Material names often contain multiple keywords that could match different shaders:

```
"Dirt_Leaves_Triplanar_01"
  - "Leaves" suggests foliage
  - "Triplanar" suggests polygon (triplanar mode)
  - "Dirt" suggests polygon
```

A simple first-match approach would incorrectly assign foliage shader. The scoring system:

1. Assigns weighted scores to each pattern:
   - High specificity: "triplanar" = 60, "crystal" = 45
   - Medium specificity: "tree" = 30, "fern" = 30
   - Low specificity: "leaves" = 20, "moss" = 15

2. Sums scores per shader type

3. Selects highest-scoring shader (minimum threshold of 20)

**Result**: "Dirt_Leaves_Triplanar_01" scores polygon=75, foliage=20, correctly choosing polygon.

### Why TSCN with External Material References

Early versions embedded materials directly into mesh resources. The current approach uses `.tscn` scene files with external material references:

```ini
[ext_resource type="ShaderMaterial" path="res://materials/Crystal_Mat_01.tres" id="1"]
```

**Benefits**:
- Materials can be edited without re-converting meshes
- Shared materials across multiple meshes (memory efficient)
- Clear separation of concerns
- Easier debugging (human-readable material files)

---

## Extension Points

### Adding New Shader Types

1. **Add shader file**: Place new `.gdshader` in `shaders/` directory

2. **Register GUIDs**: Add Unity shader GUIDs to `SHADER_GUID_MAP` in `shader_mapping.py`:
   ```python
   SHADER_GUID_MAP = {
       "abc123...": "new_shader.gdshader",
       # ...
   }
   ```

3. **Add name patterns**: Add patterns to `SHADER_NAME_PATTERNS` with scoring:
   ```python
   "new_shader": [
       (r"keyword1", 45),  # High specificity
       (r"keyword2", 30),  # Medium specificity
   ],
   ```

4. **Add property detection**: Add to `SHADER_PROPERTY_SIGNATURES`:
   ```python
   "new_shader": [
       "_Unique_Property_1",
       "_Unique_Property_2",
   ],
   ```

5. **Add property mapping**: Create mapping table in `PROPERTY_MAPS`:
   ```python
   "new_shader": {
       "_Unity_Prop": "godot_param",
       # ...
   },
   ```

6. **Update converter.py**: Add filename to `SHADER_FILES` list

### Adding New Property Mappings

1. **Identify Unity property name**: Check `.mat` file in Unity package

2. **Identify Godot parameter name**: Check shader file uniform declarations

3. **Add to appropriate map** in `shader_mapping.py`:
   ```python
   PROPERTY_MAPS["foliage"]["_New_Unity_Prop"] = "new_godot_param"
   ```

4. **Handle type conversion** if needed (boolean-as-float, alpha fix)

### Customizing Defaults

Default values for missing properties are defined per shader in `SHADER_DEFAULTS`:

```python
SHADER_DEFAULTS = {
    "crystal.gdshader": {
        "opacity": 0.7,
        "metallic": 0.0,
        "smoothness": 0.85,
    },
    "foliage.gdshader": {
        "leaf_smoothness": 0.1,
        "trunk_smoothness": 0.15,
        "leaf_metallic": 0.0,
        "trunk_metallic": 0.0,
    },
    # ...
}
```

To customize:
1. Edit the defaults dictionary
2. Values apply when Unity material lacks the property

### Adding Unity Quirk Fixes

For new color properties that suffer from alpha=0:

```python
ALPHA_FIX_PROPERTIES = [
    "_New_Color_Property",
    # ...
]
```

For new boolean-as-float properties:

```python
BOOL_PROPERTIES = [
    "_New_Enable_Feature",
    # ...
]
```

---

## Step Documentation Reference

For detailed implementation documentation of each pipeline step, see the step docs:

| Step | Documentation | Module |
|------|---------------|--------|
| Step 0 | [CLI & Orchestration](steps/00-cli-orchestration.md) | `converter.py` |
| Step 1 | [Validate Inputs](steps/01-validate-inputs.md) | `converter.py` |
| Step 2 | [Create Directories](steps/02-create-directories.md) | `converter.py` |
| Step 3 | [Extract Unity Package](steps/03-extract-unity-package.md) | `unity_package.py` |
| Step 4 | [Parse Materials](steps/04-parse-materials.md) | `unity_parser.py` |
| Step 4.5 | [Parse MaterialList](steps/05-parse-material-list.md) | `material_list.py` |
| Step 5 | [Shader Detection](steps/06-shader-detection.md) | `shader_mapping.py` |
| Step 6 | Resolve Shader Paths | `converter.py` |
| Step 7 | [TRES Generation](steps/07-tres-generation.md) | `tres_generator.py` |
| Step 8 | [Copy Textures](steps/09-copy-textures.md) | `converter.py` |
| Step 9 | [Copy FBX](steps/10-copy-fbx.md) | `converter.py` |
| Step 10 | [Generate Mapping](steps/11-generate-mapping.md) | `converter.py` |
| Step 11 | Generate project.godot | `converter.py` |
| Step 12 | [Godot Conversion](steps/12-godot-conversion.md) | `godot_converter.gd` |
| GUI | [GUI Application](steps/gui.md) | `gui.py` |

**Note:** Step numbering changed in v2.1 - shader copying is now part of Step 6 (Resolve Shader Paths).

---

## Related Documentation

- [Unity Reference](unity-reference.md) - Unity shader GUIDs and property tables
- [Shader Reference](shader-reference.md) - Godot shader parameters
- [Troubleshooting Guide](troubleshooting.md) - Common issues and solutions
- [User Guide](user-guide.md) - Installation and usage instructions
