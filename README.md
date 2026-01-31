# Synty Unity-to-Godot Converter

Convert Synty Studios Unity asset packs to Godot 4.6 with full shader support.

## Features

- **Modern GUI** - User-friendly CustomTkinter interface with drag & drop support
- **Automatic shader detection** - Identifies Polygon, Foliage, Crystal, Water, Clouds, Particles, and Skydome materials
- **3-tier shader detection** - GUID lookup (50+ known shaders), name pattern matching, property-based analysis
- **Full material conversion** - Parses Unity .mat files and generates Godot ShaderMaterial .tres files
- **Texture handling** - Copies only required textures, supports PNG/TGA/JPG
- **FBX mesh conversion** - Imports FBX models via Godot CLI with materials pre-assigned
- **Global shader uniforms** - Generates project.godot with wind, sky, and water parameters
- **Pack browser** - Scan directories to discover and batch-convert Synty packs
- **Real-time logging** - Live conversion progress with detailed output

## Requirements

- **Python 3.10+**
- **Godot 4.6** (mono or standard)

### GUI Requirements (optional)

For the graphical interface, install additional dependencies:

```bash
pip install -r requirements-gui.txt
```

## Quick Start

### GUI Mode

Launch the graphical interface:

```bash
python gui.py
```

The GUI provides:
- Pack browser to discover Synty packs in a directory
- Drag & drop support for .unitypackage files
- All CLI options as easy-to-use widgets
- Real-time conversion log output
- Statistics display for materials, textures, and meshes

### Command Line

```bash
python converter.py \
    --unity-package "C:\SyntyComplete\POLYGON_Fantasy\Fantasy.unitypackage" \
    --source-files "C:\SyntyComplete\POLYGON_Fantasy\SourceFiles" \
    --output "C:\Godot\Projects\fantasy-assets" \
    --godot "C:\Godot\Godot_v4.6-stable_mono_win64\Godot_v4.6-stable_mono_win64.exe"
```

## Output Structure

```
output/
  project.godot              # Godot project with global shader uniforms
  shaders/                   # 7 community drop-in shaders
  textures/                  # Only textures referenced by materials
  materials/                 # Generated .tres ShaderMaterials
  models/                    # Copied FBX files (structure preserved)
  meshes/                    # Individual mesh .res files (ready to use)
  mesh_material_mapping.json # Mesh-to-material assignments
  conversion_log.txt         # Warnings, errors, summary
```

## Supported Synty Packs

The converter supports all Synty POLYGON packs. Detection is based on shader GUIDs and material properties, not pack-specific logic.

| Pack Category | Examples | Status |
|--------------|----------|--------|
| Fantasy/Medieval | POLYGON_Fantasy, POLYGON_Knights, POLYGON_Dungeons | Fully supported |
| Nature/Environment | POLYGON_NatureBiomes, POLYGON_EnchantedForest | Fully supported |
| Sci-Fi | POLYGON_SciFi, POLYGON_SciFiCity, POLYGON_CyberPunk | Fully supported |
| Modern/Urban | POLYGON_City, POLYGON_Town, POLYGON_StreetRacer | Fully supported |
| Horror | POLYGON_Horror, POLYGON_Samurai | Fully supported |
| Characters | POLYGON_Modular_Fantasy_Hero, POLYGON_Vikings | Fully supported |

## Documentation

- [User Guide](docs/user-guide.md) - Comprehensive usage documentation
- [Architecture](docs/architecture.md) - Technical architecture and implementation details
- [Unity Reference](docs/unity-reference.md) - Unity material parsing details
- [Shader Reference](docs/shader-reference.md) - Godot shader parameters and mappings
- [Troubleshooting](docs/troubleshooting.md) - Common issues and solutions
- [API Reference](docs/api/index.md) - Full API documentation

## Command-Line Options

| Flag | Required | Description |
|------|----------|-------------|
| `--unity-package` | Yes | Path to .unitypackage file |
| `--source-files` | Yes | Path to SourceFiles folder (must contain Textures/) |
| `--output` | Yes | Output directory for Godot project |
| `--godot` | Yes | Path to Godot 4.6 executable |
| `--dry-run` | No | Preview without writing files |
| `--verbose` | No | Enable debug logging |
| `--skip-fbx-copy` | No | Skip copying FBX files |
| `--skip-godot-cli` | No | Skip Godot CLI (materials only) |
| `--godot-timeout` | No | Godot CLI timeout in seconds (default: 600) |

## Shader Credits

This project uses community shaders from [GodotShaders.com](https://godotshaders.com) that replicate Synty's Unity shader behavior:

| Shader | Author | URL |
|--------|--------|-----|
| Polygon | Community | [godotshaders.com/shader/synty-polygon-drop-in-replacement-for-polygonshader](https://godotshaders.com/shader/synty-polygon-drop-in-replacement-for-polygonshader/) |
| Foliage | Community | [godotshaders.com/shader/synty-core-drop-in-foliage-shader](https://godotshaders.com/shader/synty-core-drop-in-foliage-shader/) |
| Crystal | Community | [godotshaders.com/shader/synty-refractive_transparent-crystal-shader](https://godotshaders.com/shader/synty-refractive_transparent-crystal-shader/) |
| Water | Community | [godotshaders.com/shader/synty-core-drop-in-water-shader](https://godotshaders.com/shader/synty-core-drop-in-water-shader/) |
| Clouds | Community | [godotshaders.com/shader/synty-core-drop-in-clouds-shader](https://godotshaders.com/shader/synty-core-drop-in-clouds-shader/) |
| Particles | Community | [godotshaders.com/shader/synty-core-drop-in-particles-shader-generic_particlesunlit](https://godotshaders.com/shader/synty-core-drop-in-particles-shader-generic_particlesunlit/) |
| Skydome | Community | [godotshaders.com/shader/synty-polygon-drop-in-replacement-for-skydome-shader](https://godotshaders.com/shader/synty-polygon-drop-in-replacement-for-skydome-shader/) |

These shaders are downloaded unmodified and used as drop-in replacements for the Unity equivalents.

## License

This converter tool is provided for use with legally purchased Synty Studios assets. The shaders are licensed under their respective GodotShaders.com licenses.
