# Synty Converter v2 Architecture

This document describes the modular architecture of the Synty Converter v2 tool, which converts Unity Synty asset packs to Godot-compatible formats.

## Overview

The converter follows a pipeline architecture with distinct modules for each stage of the conversion process:

```
Unity Package (.unitypackage)
         |
         v
    +-------------------+
    |    Extractors     |  <- Parse .mat YAML, FBX .meta files (PRIMARY source
    +-------------------+     for FBX material names), extract assets
         |
         v
    +-------------------+
    |  FBX Analysis     |  <- OPTIONAL Blender fallback (only when .meta
    +-------------------+     files unavailable)
         |
         v
    +-------------------+
    |    Matchers       |  <- GUID matching from .meta + fuzzy name fallback
    +-------------------+
         |
         v
    +-------------------+
    |   Classifiers     |  <- Detect material types (FOLIAGE, GLASS, etc.)
    +-------------------+
         |
         v
    +-------------------+
    |   Generators      |  <- Create .tres materials, .fbx.import files
    +-------------------+
         |
         v
    +-------------------+
    |     Copiers       |  <- Copy textures with fuzzy matching
    +-------------------+
         |
         v
    Godot Project Assets
```

### Detailed Conversion Flow

1. **Extract Unity Package** - Parse `.unitypackage` archive, extract all assets
2. **Parse FBX Meta Files (PRIMARY)** - Extract FBX material names AND Unity material GUIDs from `externalObjects` section in FBX `.meta` files. This is the primary source for FBX material names - no Blender needed.
3. **Analyze FBX with Blender (OPTIONAL FALLBACK)** - Only used when `.meta` files are unavailable (e.g., converting from extracted directories)
4. **Match Materials** - Primary: GUID matching from `.meta` files (100% accurate), Fallback: Fuzzy name matching
5. **Classify Materials** - Determine shader type for each material
6. **Generate Materials** - Create Godot `.tres` ShaderMaterial files with FBX material names
7. **Configure Imports** - Generate `.fbx.import` files with proper FBX/ufbx parameters
8. **Copy Assets** - Copy textures and FBX files to Godot project

## Directory Structure

```
synty_converter_v2/
|-- __init__.py
|-- __main__.py           # CLI entry point (python -m synty_converter_v2)
|-- main.py               # CLI argument parsing and orchestration
|-- config.py             # Configuration classes and constants
|-- converter.py          # Main SyntyConverter orchestrator class
|-- gui.py                # CustomTkinter GUI application
|
|-- extractors/
|   |-- __init__.py
|   |-- unity_package.py  # Parse .unitypackage, .mat YAML, FBX .meta files
|   |-- fbx_extractor.py  # Blender-based FBX material extraction
|
|-- matchers/
|   |-- __init__.py
|   |-- material_matcher.py  # Two-phase material matching (GUID + fuzzy)
|
|-- classifiers/
|   |-- __init__.py
|   |-- material_classifier.py  # Classify materials by type
|
|-- generators/
|   |-- __init__.py
|   |-- material_generator.py    # Generate .tres ShaderMaterial files
|   |-- import_file_generator.py # Generate .fbx.import files
|   |-- global_uniforms.py       # Generate global shader uniforms script
|
|-- copiers/
|   |-- __init__.py
|   |-- texture_copier.py  # Copy and match textures
|
|-- shaders/
|   |-- __init__.py
|   |-- shader_installer.py     # Download shaders from godotshaders.com
|   |-- polygon_shader.gdshader
|   |-- foliage.gdshader
|   |-- water.gdshader
|   |-- refractive_transparent.gdshader
|   |-- clouds.gdshader
|   |-- sky_dome.gdshader
|   |-- particles_unlit.gdshader
|   |-- biomes_tree.gdshader

build_exe.py              # PyInstaller build script for standalone exe
```

## Module Details

### extractors/unity_package.py

**Purpose:** Parse Unity .unitypackage files, extract material metadata from .mat YAML files, and parse FBX .meta files for GUID-based material mappings.

**Key Classes:**
- `UnityPackageExtractor` - Main extractor class
- `MaterialInfo` - Dataclass holding parsed material properties
- `TextureInfo` - Dataclass holding texture asset information
- `FBXMaterialMapping` - Dataclass for FBX material name to Unity material GUID mappings

**Key Features:**
- Extracts gzipped tar archive (.unitypackage format)
- Parses GUID-based folder structure
- Extracts material properties from YAML:
  - `m_TexEnvs` - Texture references with GUIDs
  - `m_Floats` - Float properties like `_Enable_Emission`
  - `m_Colors` - Color properties like `_Emission_Color`
  - `stringTagMap` - Tags like `RenderType`
- **Parses FBX .meta files** for `externalObjects` section:
  - Maps FBX material names to Unity material GUIDs
  - Enables 100% accurate material matching
- Resolves texture GUIDs to actual filenames
- Provides `materials_by_guid` dict for GUID-based lookups
- Provides `fbx_material_mappings` dict for FBX-to-Unity material mappings

**Example Usage:**
```python
extractor = UnityPackageExtractor(Path("pack.unitypackage"))
extractor.extract()

# Access materials by name
for name, mat_info in extractor.materials.items():
    print(f"{name}: {mat_info.has_foliage_properties}")

# Access materials by GUID (for FBX matching)
for guid, mat_info in extractor.materials_by_guid.items():
    print(f"GUID {guid}: {mat_info.name}")

# Access FBX material mappings
for fbx_path, mappings in extractor.fbx_material_mappings.items():
    for mapping in mappings:
        print(f"{fbx_path}: {mapping.fbx_material_name} -> {mapping.unity_material_guid}")
```

### extractors/fbx_extractor.py

**Purpose:** Extract material names from FBX files using Blender's headless mode. **This is an optional fallback** - the primary source for FBX material names is the `.meta` file parser in `unity_package.py`.

**When Used:**
- Converting from extracted directories without `.meta` files
- FBX files that lack corresponding `.meta` files
- NOT needed for typical `.unitypackage` conversions (`.meta` files provide all needed data)

**Key Features:**
- Runs Blender in background mode (no GUI)
- Extracts actual material names from FBX mesh objects
- Handles Blender's automatic `.001`, `.002` suffix additions
- Provides `clean_material_name()` function to strip suffixes
- Returns deduplicated list of material names per FBX file
- Gracefully falls back if Blender is not available

**Example Usage:**
```python
from synty_converter_v2.extractors.fbx_extractor import FBXExtractor

extractor = FBXExtractor()
if extractor.blender_available:
    materials = extractor.extract_materials(Path("model.fbx"))
    # Returns: ["Material_01", "Material_02", ...]
```

### matchers/material_matcher.py

**Purpose:** Two-phase material matching system that maps FBX material names to Unity materials.

**Key Classes:**
- `MaterialMatcher` - Main matcher class with GUID and fuzzy matching

**Matching Phases:**

1. **Primary: Meta File GUID Matching (100% confidence, no Blender needed)**
   - Uses `FBXMaterialMapping` data from FBX `.meta` files
   - The `.meta` file contains both FBX material names AND Unity material GUIDs
   - Looks up Unity material by GUID using `materials_by_guid`
   - Returns exact match - this is the primary and preferred method

2. **Fallback: Blender + Fuzzy Name Matching**
   - Only used when `.meta` files are unavailable
   - If Blender available: extracts FBX material names from file
   - Cleans Blender suffixes (`.001`, `.002`) from material names
   - Tries exact name match, then normalized comparison
   - Uses similarity scoring for best match

**Key Features:**
- Detailed logging of match statistics (GUID vs fuzzy matches)
- Handles materials not found in either phase
- Cleans Blender-added duplicate suffixes

**Example Usage:**
```python
from synty_converter_v2.matchers import MaterialMatcher

matcher = MaterialMatcher(
    materials=extractor.materials,
    materials_by_guid=extractor.materials_by_guid,
    fbx_material_mappings=extractor.fbx_material_mappings
)

# Match a single FBX material
unity_material = matcher.match(fbx_path, fbx_material_name)

# Match all materials for an FBX file
matches = matcher.match_all(fbx_path, fbx_material_names)
```

See [FBX_MATERIAL_MATCHING.md](FBX_MATERIAL_MATCHING.md) for detailed documentation.

---

### classifiers/material_classifier.py

**Purpose:** Classify materials into shader types based on Unity metadata and naming conventions.

**Key Classes:**
- `MaterialClassifier` - Main classification logic

**Classification Priority:**
1. **FOLIAGE** - Has `_Leaf_Texture`, `_Trunk_Texture`, or wind properties
2. **EMISSIVE** - Has `_Enable_Emission: 1` with emission texture/color
3. **GLASS** - `RenderType == "Transparent"` or name contains Glass/Window
4. **WATER** - Name contains Water/Ocean/River
5. **STANDARD** - Default fallback

**Name Pattern Detection:**
Uses regex patterns for fallback classification when metadata unavailable:
- `FOLIAGE_PATTERNS`: leaf, tree, plant, grass, bush, hedge, vine, etc.
- `WATER_PATTERNS`: water, ocean, river, lake, pond, sea, wave
- `GLASS_PATTERNS`: glass, window, crystal, ice, transparent, mirror
- `EMISSIVE_PATTERNS`: lantern, lamp, light, glow, torch, fire, flame
- `SKY_PATTERNS`: sky, skydome, skybox
- `CLOUD_PATTERNS`: cloud, fog, mist, smoke
- `PARTICLE_PATTERNS`: particle, fx_, effect, spark, dust

See [MATERIAL_CLASSIFICATION.md](MATERIAL_CLASSIFICATION.md) for detailed classification logic.

### generators/material_generator.py

**Purpose:** Generate Godot ShaderMaterial .tres resource files.

**Key Classes:**
- `MaterialGenerator` - Generates .tres file content

**Generated Output:**
- `[gd_resource type="ShaderMaterial"]` format
- External resource references for shader and textures
- Shader parameters matching each shader's uniforms

**Material Type Generators:**
- `_generate_standard()` - polygon_shader.gdshader
- `_generate_foliage()` - foliage.gdshader with wind parameters
- `_generate_water()` - water.gdshader with wave settings
- `_generate_glass()` - refractive_transparent.gdshader
- `_generate_emissive()` - polygon_shader with emission enabled
- `_generate_sky()` - sky_dome.gdshader
- `_generate_clouds()` - clouds.gdshader
- `_generate_particles()` - particles_unlit.gdshader

**Example Output:**
```tres
[gd_resource type="ShaderMaterial" load_steps=3 format=3]

[ext_resource type="Shader" path="res://assets/shaders/synty/polygon_shader.gdshader" id="1"]
[ext_resource type="Texture2D" path="res://assets/synty/MyPack/Textures/Albedo.png" id="2"]

[resource]
shader = ExtResource("1")
shader_parameter/enable_base_texture = true
shader_parameter/base_texture = ExtResource("2")
shader_parameter/color_tint = Color(1, 1, 1, 1)
shader_parameter/metallic = 0.0
shader_parameter/smoothness = 0.5
```

### generators/import_file_generator.py

**Purpose:** Generate `.fbx.import` configuration files for Godot's import system.

**Key Classes:**
- `ImportFileGenerator` - Creates import configuration

**Generated Settings:**
- Scene importer configuration
- Material remapping to external .tres files
- Mesh extraction settings (optional)
- LOD and shadow mesh generation
- Animation import settings

**FBX Categorization:**
Automatically categorizes models based on naming conventions:
- `Buildings/` - Bld_, Building_, House_, Castle_, Temple_
- `Characters/` - Char_, Character_, NPC_, Player_
- `Environment/` - Env_, Tree_, Rock_, Grass_, Plant_
- `Props/` - Prop_, Item_, Weapon_, Tool_, Furniture_
- `Vehicles/` - Veh_, Vehicle_, Cart_, Boat_, Ship_
- `FX/` - FX_, Particle_, Effect_

### generators/global_uniforms.py

**Purpose:** Generate a GDScript autoload for global shader uniforms.

**Generated Script Features:**
- Registers global shader variables via `RenderingServer`
- Provides `trigger_gust()` for wind gust effects
- Provides `set_wind_from_angle()` for directional control
- Updates uniforms in `_process()` for real-time control

See [GLOBAL_UNIFORMS.md](GLOBAL_UNIFORMS.md) for setup instructions.

### copiers/texture_copier.py

**Purpose:** Copy texture files with intelligent fuzzy matching.

**Key Classes:**
- `TextureCopier` - Texture file operations

**Key Features:**
- Copies from directory or Unity package extraction
- Fuzzy matching for material-to-texture association
- Handles duplicate detection (compares file content)
- Supports multiple texture types: albedo, normal, emission, metallic, roughness, AO

**Texture Pattern Matching:**
```python
TEXTURE_PATTERNS = {
    "albedo": ["_Albedo", "_Color", "_Diffuse", "_BaseColor", "_D", "_01_A", "_A"],
    "normal": ["_Normal", "_N", "_Nrm", "_Bump"],
    "emission": ["_Emission", "_Emissive", "_E", "_Glow"],
    "metallic": ["_Metallic", "_M", "_Metal"],
    "roughness": ["_Roughness", "_R", "_Rough"],
    "ao": ["_AO", "_Occlusion", "_AmbientOcclusion"],
}
```

**Fuzzy Matching Algorithm:**
1. Exact match on filename
2. Case-insensitive match
3. Base name containment (with prefix/suffix removal)
4. Character similarity scoring (>70% threshold)

### shaders/

**Purpose:** Godot shader files that replicate Unity Synty shaders.

**Included Shaders (8 total):**

| Shader | Purpose | Source |
|--------|---------|--------|
| polygon_shader.gdshader | Standard Synty materials with triplanar | [godotshaders.com](https://godotshaders.com/shader/synty-polygon-drop-in-replacement-for-polygonshader/) |
| foliage.gdshader | Trees, plants with wind animation | [godotshaders.com](https://godotshaders.com/shader/synty-core-drop-in-foliage-shader/) |
| water.gdshader | Water with waves, foam, caustics | [godotshaders.com](https://godotshaders.com/shader/synty-core-drop-in-water-shader/) |
| refractive_transparent.gdshader | Glass, crystals, ice | [godotshaders.com](https://godotshaders.com/shader/synty-refractive_transparent-crystal-shader/) |
| clouds.gdshader | Animated cloud meshes | [godotshaders.com](https://godotshaders.com/shader/synty-core-drop-in-clouds-shader/) |
| sky_dome.gdshader | Sky dome/skybox | [godotshaders.com](https://godotshaders.com/shader/synty-polygon-drop-in-replacement-for-skydome-shader/) |
| particles_unlit.gdshader | Particle effects | [godotshaders.com](https://godotshaders.com/shader/synty-core-drop-in-particles-shader-generic_particlesunlit/) |
| biomes_tree.gdshader | Biomes pack tree shader | [godotshaders.com](https://godotshaders.com/shader/synty-biomes-tree-compatible-shader/) |

See [SHADERS.md](SHADERS.md) for detailed shader documentation.

## Main Orchestrator

### converter.py - SyntyConverter

The main orchestrator class that runs the full conversion pipeline:

```python
class SyntyConverter:
    def convert(self) -> dict:
        # Step 1: Create output directories
        self._create_directories()

        # Step 2: Extract Unity package if provided
        self._extract_unity_package()
        # - Also parses FBX .meta files for GUID mappings
        # - Populates materials_by_guid and fbx_material_mappings

        # Step 3: Analyze FBX files with Blender (optional)
        self._analyze_fbx_materials()
        # - Extracts actual material names from FBX files
        # - Cleans Blender .001/.002 suffixes

        # Step 4: Match FBX materials to Unity materials
        self._match_materials()
        # - Phase 1: GUID matching from .meta files
        # - Phase 2: Fuzzy name matching fallback

        # Step 5: Copy textures
        self._copy_textures()

        # Step 6: Collect and classify materials
        self._classify_materials()

        # Step 7: Generate material files
        self._generate_materials()
        # - Uses matched FBX material names for accurate assignments

        # Step 8: Copy FBX files and generate import configs
        self._process_models()
        # - Generates .fbx.import with FBX/ufbx parameters

        # Step 9: Install shaders if needed
        self._ensure_shaders()
```

### gui.py - GUI Application

Modern graphical interface built with CustomTkinter:

**Features:**
- Dark theme with modern styling
- File browser for `.unitypackage` selection
- Folder browser for Godot project selection
- Pack name auto-detection from filename
- Dry Run toggle for preview mode
- Extract Meshes toggle
- Real-time output log with scrolling
- Progress indication during conversion

**Building Standalone Executable:**
```bash
# Install dev dependencies
pip install -e ".[dev]"

# Build exe using PyInstaller
python build_exe.py

# Output: dist/SyntyConverter.exe
```

## Configuration

### config.py

**MaterialType Enum:**
```python
class MaterialType(Enum):
    STANDARD = auto()
    FOLIAGE = auto()
    EMISSIVE = auto()
    GLASS = auto()
    WATER = auto()
    SKY = auto()
    CLOUDS = auto()
    PARTICLES = auto()
```

**ConversionConfig Dataclass:**
```python
@dataclass
class ConversionConfig:
    pack_name: str
    unity_package_path: Optional[Path] = None
    source_fbx_dir: Optional[Path] = None
    source_textures_dir: Optional[Path] = None
    godot_project_path: Path = Path.cwd()
    dry_run: bool = False
    verbose: bool = False
    extract_meshes: bool = True
```

**Output Directory Structure:**
```
{godot_project}/
|-- assets/
    |-- synty/
    |   |-- {pack_name}/
    |       |-- Materials/     # Generated .tres files
    |       |-- Textures/      # Copied texture files
    |       |-- Models/        # FBX files by category
    |       |   |-- Buildings/
    |       |   |-- Characters/
    |       |   |-- Environment/
    |       |   |-- Props/
    |       |   |-- Vehicles/
    |       |   |-- FX/
    |       |-- Meshes/        # Extracted .res mesh files
    |
    |-- shaders/
        |-- synty/             # Shader files
```

## CLI Usage

```bash
# Basic conversion with Unity package
python -m synty_converter_v2 \
    --pack POLYGON_Samurai_Empire \
    --unity SamuraiEmpire.unitypackage \
    --project C:\Godot\MyGame

# From extracted directories
python -m synty_converter_v2 \
    --pack POLYGON_Fantasy \
    --fbx-dir ./Models \
    --textures-dir ./Textures \
    --project C:\Godot\MyGame

# Preview without writing
python -m synty_converter_v2 \
    --pack MyPack \
    --unity pkg.unitypackage \
    --dry-run

# Verbose output
python -m synty_converter_v2 \
    --pack MyPack \
    --unity pkg.unitypackage \
    --project ./game \
    -v
```

## Extending the Converter

### Adding a New Material Type

1. Add to `MaterialType` enum in `config.py`
2. Add shader file mapping in `SHADER_FILES`
3. Add classification logic in `MaterialClassifier._classify_from_metadata()`
4. Add name patterns in `MaterialClassifier` if needed
5. Add generator method in `MaterialGenerator`

### Adding a New Shader

1. Add shader file to `shaders/` directory
2. Add URL to `SHADER_URLS` in both `config.py` and `shader_installer.py`
3. Add shader file mapping in `SHADER_FILES`
4. Create generator method in `MaterialGenerator`

## Dependencies

### Required
- Python 3.10+
- customtkinter >= 5.2.0 (for GUI)

### Optional
- **Blender** - Fallback for FBX material extraction (any recent version)
  - **Not needed for `.unitypackage` conversions** - `.meta` files provide FBX material names
  - Only useful when converting from extracted directories without `.meta` files
  - Must be in system PATH if used
  - Used in headless mode (no GUI required)
  - Falls back gracefully if not available

### Development
- pytest >= 7.0
- pytest-cov >= 4.0
- black >= 23.0
- ruff >= 0.1.0
- pyinstaller >= 6.0 (for building standalone exe)
