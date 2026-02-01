# Synty Unity-to-Godot Converter

Convert Synty Studios Unity asset packs (`.unitypackage` files) to Godot 4.6 with full shader support, automatic material conversion, and FBX mesh processing.

## Features

- **Full material conversion** - Parses Unity `.mat` files and generates Godot `ShaderMaterial` `.tres` files
- **3-tier shader detection** - GUID lookup (56 known shaders), name pattern matching, property-based analysis
- **7 Godot shaders** - Polygon, Foliage, Crystal, Water, Clouds, Particles, Skydome
- **FBX mesh conversion** - Imports FBX models via Godot CLI with materials pre-assigned
- **Texture handling** - Extracts textures from `.unitypackage` with fallback to SourceFiles
- **Modern GUI** - CustomTkinter interface with real-time logging and progress display
- **Global shader uniforms** - Generates `project.godot` with wind, sky, and water parameters
- **Recursive folder discovery** - Finds FBX files in nested pack structures automatically
- **Project merging** - Merges `project.godot` settings for multi-pack workflows
- **LOD inheritance** - Consistent shader detection across LOD levels
- **Smart texture filtering** - When using `--filter`, only copies textures needed by filtered FBX files
- **High quality texture compression** - Optional BPTC compression for improved texture quality

## Quick Start

```bash
# CLI (no dependencies required)
# Note: --source-files supports recursive discovery, so you can point to
# the top-level SourceFiles folder even if FBX files are in subdirectories.
python converter.py \
    --unity-package "C:\SyntyComplete\POLYGON_Fantasy\Fantasy.unitypackage" \
    --source-files "C:\SyntyComplete\POLYGON_Fantasy\SourceFiles" \
    --output "C:\Godot\Projects\fantasy-assets" \
    --godot "C:\Godot\Godot_v4.6-stable_mono_win64\Godot_v4.6-stable_mono_win64.exe"

# GUI (requires additional dependencies)
pip install -r requirements-gui.txt
python gui.py
```

## Installation

**Requirements:**
- Python 3.10+
- Godot 4.6 (mono or standard)

**GUI dependencies** (optional):
```bash
pip install -r requirements-gui.txt
```

This installs CustomTkinter for the graphical interface.

## CLI Options

| Flag | Required | Description |
|------|----------|-------------|
| `--unity-package` | Yes | Path to `.unitypackage` file |
| `--source-files` | Yes | Path to SourceFiles folder containing FBX/ (recursive search, Textures/ optional) |
| `--output` | Yes | Output directory for Godot project |
| `--godot` | Yes | Path to Godot 4.6 executable |
| `--dry-run` | No | Preview without writing files |
| `--verbose` | No | Enable debug logging |
| `--skip-fbx-copy` | No | Skip copying FBX files |
| `--skip-godot-cli` | No | Skip Godot CLI (materials only) |
| `--skip-godot-import` | No | Skip Godot import phase (converter script still runs) |
| `--godot-timeout` | No | Godot CLI timeout in seconds (default: 600) |
| `--keep-meshes-together` | No | Keep all meshes from one FBX in a single scene |
| `--mesh-format` | No | Output format: `tscn` (default) or `res` |
| `--filter` | No | Filter pattern for FBX filenames (also filters textures) |
| `--high-quality-textures` | No | Use BPTC compression for higher quality textures |

## Output Structure

```
output/
  project.godot              # Godot project with global shader uniforms
  shaders/                   # 7 community drop-in shaders
    mesh_material_mapping.json  # Shared mesh-to-material mappings
  PackName/
    textures/                # Extracted textures
    materials/               # Generated .tres ShaderMaterials
    models/                  # Copied FBX files (structure preserved)
    meshes/                  # Individual mesh .tscn/.res files
    conversion_log.txt
```

## Pipeline Overview

The converter runs a 12-step pipeline:

| Step | Description |
|------|-------------|
| 1 | Validate inputs (package, source files, Godot exe) |
| 2 | Create output directory structure |
| 3 | Extract `.unitypackage` and build GUID maps |
| 4 | Parse Unity `.mat` files |
| 5 | Parse `MaterialList.txt` for mesh-material mappings |
| 6 | Detect shaders via 3-tier system |
| 7 | Generate Godot `.tres` ShaderMaterial files |
| 8 | Copy community shader files |
| 9 | Copy textures with fallback resolution |
| 10 | Copy FBX models |
| 11 | Generate `mesh_material_mapping.json` |
| 12 | Run Godot CLI for mesh-to-scene conversion |

See [docs/steps/](docs/steps/README.md) for comprehensive step-by-step documentation.

## Supported Shaders

| Shader | Description |
|--------|-------------|
| Polygon | Standard Synty materials (characters, props, buildings) |
| Foliage | Trees, bushes, grass with wind animation |
| Crystal | Transparent/refractive materials |
| Water | Animated water surfaces |
| Clouds | Volumetric cloud rendering |
| Particles | Unlit particle effects |
| Skydome | Sky gradient and sun rendering |

These use community shaders from [GodotShaders.com](https://godotshaders.com) as drop-in replacements.

## Documentation

| Document | Description |
|----------|-------------|
| [Pipeline Steps](docs/steps/README.md) | Comprehensive 12-step pipeline documentation |
| [GUI Documentation](docs/steps/gui.md) | CustomTkinter GUI wrapper |
| [Architecture](docs/architecture.md) | Technical architecture |
| [Shader Reference](docs/shader-reference.md) | Godot shader parameters |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and solutions |
| [API Reference](docs/api/index.md) | Module API documentation |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## License

This converter tool is provided for use with legally purchased Synty Studios assets. The shaders are licensed under their respective GodotShaders.com licenses.
