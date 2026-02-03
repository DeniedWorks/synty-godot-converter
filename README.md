# Synty Unity-to-Godot Converter

Convert Synty Studios Unity asset packs (`.unitypackage` files) to Godot 4.6 with full shader support, automatic material conversion, and FBX mesh processing.

**Version 2.4** - Output subfolder organization, retain source directory structure.

## Features

- **Full material conversion** - Parses Unity `.mat` files and generates Godot `ShaderMaterial` `.tres` files
- **3-tier shader detection** - GUID lookup (56 known shaders), name pattern matching, property-based analysis
- **7 Godot shaders** - Polygon, Foliage, Crystal, Water, Clouds, Particles, Skydome
- **FBX mesh conversion** - Imports FBX models via Godot CLI with materials pre-assigned
- **Texture handling** - Extracts textures from `.unitypackage` with fallback to SourceFiles
- **Modern GUI** - CustomTkinter interface with real-time logging, progress display, and settings persistence
- **Global shader uniforms** - Generates `project.godot` with wind, sky, and water parameters
- **Recursive folder discovery** - Finds FBX files in nested pack structures automatically
- **Project merging** - Merges `project.godot` settings for multi-pack workflows
- **LOD inheritance** - Consistent shader detection across LOD levels
- **Smart filtering** - When using `--filter`, only copies textures and materials needed by filtered FBX files
- **High quality texture compression** - Optional BPTC compression for improved texture quality
- **Per-pack isolation** - Each pack gets its own folder with `mesh_material_mapping.json` for targeted processing
- **Dynamic shader discovery** - Finds existing shaders in your project before copying duplicates
- **Clean FBX paths** - Strips `SourceFiles/FBX/Models` prefixes for cleaner output structure
- **Comprehensive fallback matching** - Name variations, prefix swaps, and fuzzy matching (Levenshtein) for materials
- **Output subfolder organization** - Organize converted packs into custom subfolders with `--output-subfolder`
- **Retain source structure** - Preserve `Source_Files/FBX/` subdirectory structure in mesh output with `--retain-subfolders`

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
| `--filter` | No | Filter pattern for FBX filenames (also filters textures and materials) |
| `--high-quality-textures` | No | Use BPTC compression for higher quality textures |
| `--mesh-scale` | No | Scale factor for mesh output (e.g., `100` for undersized packs) |
| `--output-subfolder` | No | Subfolder path prepended to pack folder names |
| `--retain-subfolders` | No | Preserve Source_Files/FBX/ subdirectory structure in mesh output |

## Output Structure

```
output/
  project.godot              # Godot project with global shader uniforms
  shaders/                   # 7 community drop-in shaders
  conversion_log.txt         # Append-mode log for all pack conversions
  PackName/
    textures/                # Extracted textures
    materials/               # Generated .tres ShaderMaterials
    models/                  # Copied FBX files (clean paths, structure preserved)
    meshes/                  # Mesh output organized by configuration
      tscn_separate/         # --mesh-format tscn (default, one file per mesh)
      tscn_combined/         # --mesh-format tscn --keep-meshes-together
      res_separate/          # --mesh-format res (one file per mesh)
      res_combined/          # --mesh-format res --keep-meshes-together
    mesh_material_mapping.json  # Per-pack mesh-to-material mappings
```

**Mesh subfolder naming**: Output goes to `meshes/{format}_{mode}/` based on your options. This allows multiple output configurations to coexist without overwriting each other.

**Multi-pack workflow**: Each pack folder is self-contained with its own `mesh_material_mapping.json`. The `conversion_log.txt` at the project root appends entries from each conversion, making it easy to track multiple pack imports.

**Incremental conversion**: When re-running on a pack that already has `materials/`, `textures/`, `models/`, and `mesh_material_mapping.json`, the converter skips phases 3-10 and only regenerates meshes. This is useful for trying different mesh format/mode combinations without re-processing textures and materials.

## Pipeline Overview

The converter runs a 12-step pipeline:

| Step | Description |
|------|-------------|
| 1 | Validate inputs (package, source files, Godot exe) |
| 2 | Create output directory structure |
| 3 | Extract `.unitypackage` and build GUID maps |
| 4 | Parse Unity `.mat` files |
| 5 | Parse `MaterialList.txt` for mesh-material mappings |
| 6 | Detect shaders via 3-tier system (GUID, name patterns, property analysis) |
| 7 | Generate Godot `.tres` ShaderMaterial files |
| 8 | Copy community shader files (with dynamic path discovery) |
| 9 | Copy textures with smart filtering and fallback resolution |
| 10 | Copy FBX models (clean paths, optional scale) |
| 11 | Generate per-pack `mesh_material_mapping.json` |
| 12 | Run Godot CLI for mesh-to-scene conversion (with fallback matching) |

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

## Material Matching

The converter uses a comprehensive fallback system to match meshes to materials:

1. **Exact match** - Direct mesh name lookup in `mesh_material_mapping.json`
2. **SK_/SM_ prefix swap** - Tries both prefixes when one fails
3. **Suffix stripping** - Removes `_LOD0`, `_LOD1`, `_Low`, `_High`, etc.
4. **Prefix removal** - Strips `PolygonPack_Mat_` prefixes
5. **Name variations** - Generates all combinations of above transformations
6. **Fuzzy matching** - Levenshtein distance <= 2 as last resort

This handles naming inconsistencies between Unity prefabs and Godot mesh imports.

## GUI Features

The GUI (`gui.py`) provides:
- Real-time conversion progress with percentage and ETA
- Detailed logging with warning/error highlighting
- **Settings persistence** - Paths and options are saved between sessions
- Dry-run mode for previewing conversions

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
