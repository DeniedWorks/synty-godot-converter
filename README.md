# Synty Asset Converter v2

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Godot](https://img.shields.io/badge/Godot-4.x-478CBF?logo=godot-engine&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![GUI](https://img.shields.io/badge/GUI-CustomTkinter-blue)
![Blender](https://img.shields.io/badge/Blender-Optional-orange)

A Python tool for converting [Synty Studios](https://www.syntystudios.com/) Unity asset packs to Godot 4.x format with proper shader material handling.

---

## Overview

Synty Asset Converter v2 automates the process of migrating Synty's popular low-poly asset packs from Unity to Godot Engine. It handles the complete pipeline: extracting assets from `.unitypackage` files, classifying materials by type, generating Godot-compatible ShaderMaterial resources, and configuring FBX imports with proper mesh extraction.

**New in v2.1:** Modern GUI with dark theme, standalone executable builds, Blender-based FBX analysis, and exact GUID-based material matching from FBX `.meta` files for 100% accurate material assignments.

---

## Features

### Core Features
- **Unity Package Extraction** - Parse `.unitypackage` files to extract FBX models, textures, and material metadata directly
- **Smart Material Classification** - Automatically detect material types (standard, foliage, water, glass, emissive, sky, clouds, particles) from Unity metadata and naming conventions
- **Shader Material Generation** - Create properly configured Godot `.tres` ShaderMaterial files for each material type
- **Import Configuration** - Generate `.fbx.import` files with correct FBX/ufbx import parameters and material mappings
- **Mesh Extraction** - Configure Godot to extract meshes to separate `.res` files for reuse
- **Texture Management** - Copy and map textures with intelligent fuzzy matching
- **Dry Run Mode** - Preview all changes before writing any files

### GUI Features
- **Modern Dark Theme** - Beautiful CustomTkinter-based GUI with dark mode
- **Standalone Executable** - Build `SyntyConverter.exe` that runs without Python installed
- **Real-time Progress** - Live output log showing conversion progress
- **Easy Configuration** - File/folder browsers for selecting packages and projects

### Advanced Material Matching (v2.1)
- **FBX Meta File Parsing (Primary)** - Parse Unity FBX `.meta` files for exact GUID-based material mappings with FBX material names from `externalObjects` section
- **Blender FBX Analysis (Optional Fallback)** - Optional headless Blender integration only when `.meta` files are unavailable
- **Two-Phase Matching** - GUID matching from `.meta` files (100% accurate) with fuzzy name matching fallback
- **Works Without Blender** - Full functionality using `.meta` file data; Blender is completely optional

---

## Installation

```bash
# Clone or download the converter
git clone https://github.com/DeniedWorks/synty-godot-converter.git
cd synty-godot-converter

# Install in development mode (recommended)
pip install -e .

# Or run directly without installing
python -m synty_converter_v2 --help
```

### Requirements

- Python 3.10 or higher
- Godot 4.x project

### Optional: Blender Integration

**Blender is optional.** The converter works perfectly without it by extracting FBX material names directly from Unity `.meta` files included in `.unitypackage` archives.

When converting `.unitypackage` files:
1. The `externalObjects` section in FBX `.meta` files contains the exact FBX material names
2. These names are matched against Unity material GUIDs for 100% accurate assignments
3. **No Blender required** for typical Unity package conversions

**When Blender is useful:**
- Converting from extracted directories (without `.meta` files)
- Working with FBX files that lack corresponding `.meta` files
- Blender handles `.001`, `.002` suffix duplicates automatically

To install Blender for these edge cases:
```bash
# Check if Blender is available
blender --version
```

---

## Quick Start

### Convert a Unity Package

```bash
python -m synty_converter_v2 \
    --pack POLYGON_Samurai_Empire \
    --unity "C:/Downloads/SamuraiEmpire.unitypackage" \
    --project "C:/Godot/Projects/MyGame"
```

### Convert from Extracted Directories

```bash
python -m synty_converter_v2 \
    --pack POLYGON_Fantasy \
    --fbx-dir "./Extracted/Models" \
    --textures-dir "./Extracted/Textures" \
    --project "C:/Godot/Projects/MyGame"
```

### Preview Mode (Dry Run)

```bash
python -m synty_converter_v2 \
    --pack POLYGON_Samurai_Empire \
    --unity SamuraiEmpire.unitypackage \
    --dry-run
```

### CLI Options

| Option | Description |
|--------|-------------|
| `--pack`, `-p` | Pack name (required, e.g., `POLYGON_Samurai_Empire`) |
| `--project` | Path to Godot project root (default: current directory) |
| `--unity`, `-u` | Path to `.unitypackage` file |
| `--fbx-dir` | Path to directory containing FBX files |
| `--textures-dir` | Path to directory containing texture files |
| `--dry-run`, `-n` | Preview changes without writing files |
| `--verbose`, `-v` | Enable verbose output |
| `--no-meshes` | Disable mesh extraction to separate `.res` files |

---

## GUI Usage

The converter includes a modern graphical user interface with a dark theme.

### Running the GUI

```bash
# Using the installed command
synty-convert-gui

# Or run directly with Python
python -m synty_converter_v2.gui
```

The GUI provides:
- File browser for selecting Unity packages (.unitypackage)
- Folder browser for selecting Godot project directory
- Dry Run option to preview changes without writing files
- Extract Meshes toggle for mesh extraction configuration
- Real-time output log showing conversion progress

### Building Standalone Executable

To create a standalone `.exe` file that can run without Python installed:

```bash
# Install dev dependencies (includes PyInstaller)
pip install -e ".[dev]"

# Run the build script
python build_exe.py
```

This creates `dist/SyntyConverter.exe` - a single portable executable with no external dependencies.

---

## Output Directory Structure

```
assets/synty/{PACK_NAME}/
├── Materials/          # .tres ShaderMaterial files
│   ├── Mat_Building_01.tres
│   ├── Mat_Foliage_Tree.tres
│   └── ...
├── Textures/           # Copied PNG/TGA textures
│   ├── PolygonSamurai_Texture_01_A.png
│   └── ...
├── Models/             # FBX files + .fbx.import configs
│   ├── Buildings/
│   ├── Characters/
│   ├── Environment/
│   ├── Props/
│   └── Vehicles/
└── Meshes/             # Extracted .res mesh files (generated by Godot)
```

---

## Material Classification

Materials are automatically classified based on Unity `.mat` file metadata and naming conventions:

| Type | Shader | Detection Method |
|------|--------|------------------|
| **STANDARD** | `polygon_shader` | Default - standard PBR material |
| **FOLIAGE** | `foliage` | Has `_Leaf_Texture`, `_Trunk_Texture`, or wind properties |
| **EMISSIVE** | `refractive_transparent` | Has `_Enable_Emission: 1` with emission texture/color |
| **GLASS** | `refractive_transparent` | `RenderType == "Transparent"` or name contains Glass/Window/Crystal/Ice |
| **WATER** | `water` | Name contains Water/Ocean/River/Lake/Sea |
| **SKY** | `sky_dome` | Name contains Sky/Skydome/Skybox |
| **CLOUDS** | `clouds` | Name contains Cloud/Fog/Mist/Smoke |
| **PARTICLES** | `particles_unlit` | Name contains Particle/FX_/Effect/Spark |

---

## Required Shaders

This converter generates materials that require specific shaders. Download them from [godotshaders.com](https://godotshaders.com) and place in `assets/shaders/synty/` in your Godot project:

| Shader File | Material Type | Source |
|-------------|---------------|--------|
| `polygon_shader.gdshader` | Standard PBR | [Synty Polygon Drop-in Replacement](https://godotshaders.com/shader/synty-polygon-drop-in-replacement-for-polygonshader/) |
| `foliage.gdshader` | Foliage/Trees | [Synty Core Foliage Shader](https://godotshaders.com/shader/synty-core-drop-in-foliage-shader/) |
| `water.gdshader` | Water/Ocean | [Synty Core Water Shader](https://godotshaders.com/shader/synty-core-drop-in-water-shader/) |
| `refractive_transparent.gdshader` | Glass/Crystal/Emissive | [Synty Refractive/Crystal Shader](https://godotshaders.com/shader/synty-refractive_transparent-crystal-shader/) |
| `clouds.gdshader` | Clouds/Fog | [Synty Core Clouds Shader](https://godotshaders.com/shader/synty-core-drop-in-clouds-shader/) |
| `sky_dome.gdshader` | Sky/Skybox | [Synty SkyDome Drop-in Replacement](https://godotshaders.com/shader/synty-polygon-drop-in-replacement-for-skydome-shader/) |
| `particles_unlit.gdshader` | Particles/Effects | [Synty Particles Shader](https://godotshaders.com/shader/synty-core-drop-in-particles-shader-generic_particlesunlit/) |
| `biomes_tree.gdshader` | Biomes Trees | [Synty Biomes Tree Shader](https://godotshaders.com/shader/synty-biomes-tree-compatible-shader/) |

---

## Global Shader Uniforms

Some shaders require global uniforms for features like wind animation and water effects. Add the following to your Godot project settings or create an autoload script:

### Project Settings Method

In Godot, go to **Project > Project Settings > Globals** and add:

| Name | Type | Default |
|------|------|---------|
| `WindDirection` | Vector3 | `(1.0, 0.0, 0.5)` |
| `WindIntensity` | float | `1.0` |
| `GaleStrength` | float | `0.0` |
| `OceanWavesGradient` | GradientTexture1D | (create gradient) |

### Autoload Script Method

Create `GlobalShaderUniforms.gd` and add as an autoload:

```gdscript
extends Node

func _ready() -> void:
    # Wind parameters for foliage
    RenderingServer.global_shader_parameter_set("WindDirection", Vector3(1.0, 0.0, 0.5))
    RenderingServer.global_shader_parameter_set("WindIntensity", 1.0)
    RenderingServer.global_shader_parameter_set("GaleStrength", 0.0)

    # Water parameters
    var gradient = GradientTexture1D.new()
    gradient.gradient = Gradient.new()
    RenderingServer.global_shader_parameter_set("OceanWavesGradient", gradient)

func _process(delta: float) -> void:
    # Optional: Animate wind
    var time = Time.get_ticks_msec() / 1000.0
    var wind_dir = Vector3(sin(time * 0.5), 0.0, cos(time * 0.3)).normalized()
    RenderingServer.global_shader_parameter_set("WindDirection", wind_dir)
```

---

## API Usage

Use the converter programmatically in your Python scripts:

```python
from synty_converter_v2.converter import convert_pack, SyntyConverter
from synty_converter_v2.config import ConversionConfig
from pathlib import Path

# Simple conversion using helper function
summary = convert_pack(
    pack_name="POLYGON_Samurai_Empire",
    godot_project=Path("C:/Godot/Projects/MyGame"),
    unity_package=Path("C:/Downloads/SamuraiEmpire.unitypackage")
)

print(f"Converted {summary['materials']['total']} materials")
print(f"Processed {summary['models']} models")
print(f"Extracted {summary['meshes']} meshes")

# Material breakdown by type
for mat_type, count in summary['materials']['by_type'].items():
    print(f"  - {mat_type}: {count}")
```

### Advanced Configuration

```python
from synty_converter_v2.config import ConversionConfig
from synty_converter_v2.converter import SyntyConverter

config = ConversionConfig(
    pack_name="POLYGON_Fantasy",
    godot_project_path=Path("C:/Godot/Projects/MyGame"),
    unity_package_path=Path("C:/Downloads/Fantasy.unitypackage"),
    dry_run=False,           # Set True to preview without writing
    verbose=True,            # Enable detailed logging
    extract_meshes=True,     # Extract meshes to .res files
)

converter = SyntyConverter(config)
summary = converter.convert()
```

---

## Workflow

1. **Download** your Synty asset pack from the Unity Asset Store
2. **Run** the converter with your `.unitypackage` file (CLI or GUI)
3. **Download** the required shaders from godotshaders.com
4. **Place** shaders in `assets/shaders/synty/` in your Godot project
5. **Open** Godot to trigger asset reimport
6. **Configure** global shader uniforms if using foliage/water shaders
7. **Use** the converted materials and meshes in your scenes

### Material Matching Workflow

The converter uses a sophisticated material matching system where **`.meta` files are the primary source**:

1. **Primary: Meta File Extraction** (100% accurate, no Blender needed)
   - Parses FBX `.meta` files from the Unity package
   - Extracts `externalObjects` section containing both FBX material names AND Unity material GUIDs
   - Provides complete material mappings directly - Blender is unnecessary

2. **Fallback: Blender Analysis** (only when `.meta` files unavailable)
   - Used when converting from extracted directories without `.meta` files
   - Extracts actual material names from FBX files via headless Blender
   - Cleans Blender's `.001` suffixes from duplicate materials

3. **Final Fallback: Fuzzy Name Matching**
   - Intelligent name pattern matching when neither source is available

See [FBX_MATERIAL_MATCHING.md](docs/FBX_MATERIAL_MATCHING.md) for detailed documentation.

---

## Troubleshooting

### Materials appear pink/missing shader
Ensure all required shaders are downloaded and placed in `assets/shaders/synty/`.

### Textures not found
The converter uses fuzzy matching for texture names. Check that texture files exist in the output `Textures/` directory.

### Meshes not extracted
Mesh extraction happens on Godot reimport. Open the project in Godot and wait for import to complete.

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## Credits

- **Shader Authors**: All Godot shaders are created by [Giancarlo Niccolai](https://godotshaders.com/author/jonnygc/) and available on [godotshaders.com](https://godotshaders.com)
- **Synty Studios**: Original asset packs - [syntystudios.com](https://www.syntystudios.com/)

---

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

---

*This tool is not affiliated with or endorsed by Synty Studios or Unity Technologies.*
