# User Guide

Comprehensive guide to using the Synty Unity-to-Godot Converter.

## Table of Contents

- [Installation](#installation)
- [Understanding Synty Asset Structure](#understanding-synty-asset-structure)
- [Basic Usage](#basic-usage)
- [GUI Application](#gui-application)
- [Command-Line Options](#command-line-options)
- [Output Structure](#output-structure)
- [Advanced Usage](#advanced-usage)
- [Batch Processing](#batch-processing)
- [Post-Conversion Steps](#post-conversion-steps)
- [Troubleshooting](#troubleshooting)

---

## Installation

### Prerequisites

1. **Python 3.10 or higher**

   Verify your Python version:
   ```bash
   python --version
   ```

   The CLI converter uses only Python standard library modules - no pip packages required.

2. **Godot 4.6**

   Download from [godotengine.org](https://godotengine.org). Either the standard or Mono version works.

   Verify Godot is accessible:
   ```bash
   "C:\Godot\Godot_v4.6-stable_mono_win64\Godot_v4.6-stable_mono_win64.exe" --version
   ```

3. **CustomTkinter (Optional - for GUI only)**

   If you want to use the graphical interface instead of the command line:
   ```bash
   pip install customtkinter
   ```

### Download the Converter

Clone or download the converter to a local directory:

```bash
git clone <repository-url> synty-converter
cd synty-converter
```

No installation step is required - run directly with Python.

---

## Understanding Synty Asset Structure

Synty asset packs contain three key components the converter uses:

### 1. Unity Package (.unitypackage)

A gzip-compressed tar archive containing:
- **Material definitions** (.mat files in YAML format)
- **Texture references** (GUIDs pointing to texture assets)
- **Shader assignments** (which shader each material uses)

This is the primary source for material data, especially for custom shaders like Foliage, Crystal, and Water.

### 2. SourceFiles Folder

Contains high-quality source assets:

```
SourceFiles/
  FBX/                 # 3D models ready for import (REQUIRED)
    Characters/
    Environment/
    Props/
    ...
  Textures/            # High-resolution textures (OPTIONAL - fallback only)
    Atlas textures     # Textures are primarily extracted from .unitypackage
    Detail textures
    Normal maps
    ...
  MaterialList.txt     # Documents mesh-to-material assignments
```

### 3. MaterialList.txt

Documents which materials each mesh uses:

```
Prefab Name: SM_Prop_Crystal_01
    Mesh Name: SM_Prop_Crystal_01
        Slot: Crystal_Mat_01 (Uses custom shader)
        Slot: PolygonFantasy_Mat_01_A (PolygonFantasy_Texture_01)
```

The converter uses this to assign materials to mesh surfaces automatically.

---

## Basic Usage

### Minimum Required Arguments

```bash
python converter.py \
    --unity-package "path/to/.unitypackage" \
    --source-files "path/to/SourceFiles" \
    --output "path/to/output" \
    --godot "path/to/Godot.exe"
```

### Example with Real Paths

**Windows:**
```bash
python converter.py ^
    --unity-package "C:\SyntyComplete\POLYGON_NatureBiomes\PolygonNatureBiomes.unitypackage" ^
    --source-files "C:\SyntyComplete\POLYGON_NatureBiomes\SourceFiles" ^
    --output "C:\Godot\Projects\nature-biomes-assets" ^
    --godot "C:\Godot\Godot_v4.6-stable_mono_win64\Godot_v4.6-stable_mono_win64.exe"
```

**Linux/macOS:**
```bash
python converter.py \
    --unity-package "/home/user/SyntyAssets/POLYGON_NatureBiomes/PolygonNatureBiomes.unitypackage" \
    --source-files "/home/user/SyntyAssets/POLYGON_NatureBiomes/SourceFiles" \
    --output "/home/user/GodotProjects/nature-biomes-assets" \
    --godot "/usr/local/bin/godot"
```

---

## GUI Application

The converter includes an optional graphical interface for users who prefer not to use the command line.

### Running the GUI

```bash
python gui.py
```

### GUI Features

- **Dark mode interface** with dark-blue color theme
- **All CLI options** exposed as widgets (path inputs, checkboxes, sliders)
- **Browse dialogs** for selecting files and directories
- **Real-time log output** during conversion
- **Progress indication** with status updates
- **Help popup** with documentation

### GUI Field Layout

The GUI displays input fields in the following order from top to bottom:

1. **Unity Package** - Path to the .unitypackage file (with Browse button)
2. **Source Files** - Path to the SourceFiles folder (with Browse button)
3. **Output Directory** - Base output directory for converted assets (with Browse button)
4. **Output Subfolder** - Optional subfolder path prepended to pack folder names (text input with "Optional" placeholder). Creates packs at `output/subfolder/POLYGON_PackName/` instead of `output/POLYGON_PackName/`
5. **Godot Executable** - Path to the Godot 4.6 executable (with Browse button)

### Settings Persistence

The GUI automatically saves your settings to `%APPDATA%\SyntyConverter\settings.json`:
- All path fields (Unity package, source files, output, output subfolder, Godot executable)
- All options (output format, mesh mode, filter, timeout, checkboxes)
- Settings are restored when you reopen the application

For detailed GUI documentation, see [GUI Application](steps/gui.md).

---

## Command-Line Options

### Required Arguments

| Flag | Description | Example |
|------|-------------|---------|
| `--unity-package` | Path to the .unitypackage file from the Synty pack | `"C:\Synty\Fantasy\Fantasy.unitypackage"` |
| `--source-files` | Path to the SourceFiles folder containing FBX/ (Textures/ optional - textures come from .unitypackage) | `"C:\Synty\Fantasy\SourceFiles"` |
| `--output` | Output directory for the generated Godot project | `"C:\Godot\Projects\fantasy"` |
| `--godot` | Path to Godot 4.6 executable | `"C:\Godot\Godot_v4.6.exe"` |

### Optional Arguments

| Flag | Default | Description |
|------|---------|-------------|
| `--dry-run` | Off | Preview what would be done without writing any files. Useful for validation. |
| `--verbose` | Off | Enable debug-level logging. Shows detailed shader detection, property mapping, and file operations. |
| `--skip-fbx-copy` | Off | Skip copying FBX files to output/models/. Use when re-running conversion and models already exist. |
| `--skip-godot-cli` | Off | Skip running Godot CLI. Generates materials only, no mesh .res files. Useful for debugging material issues. |
| `--skip-godot-import` | Off | Skip Godot's headless import step. The GDScript converter still runs. Useful for large projects that timeout - open project manually in Godot first. |
| `--godot-timeout` | 600 | Maximum seconds for Godot CLI operations. Increase for very large packs. |
| `--keep-meshes-together` | Off | Keep all meshes from one FBX together in a single scene file. Default behavior is to save each mesh as a separate file. |
| `--mesh-format` | `tscn` | Output format for mesh scenes: `tscn` (text, human-readable) or `res` (binary, more compact). |
| `--filter` | None | Filter pattern for FBX filenames (case-insensitive). Only FBX files containing the pattern are processed. Also filters textures AND materials to only include those needed by filtered FBX files. Example: `--filter Tree` |
| `--high-quality-textures` | Off | Use BPTC compression for higher quality textures. Produces larger files but better visual quality. Default uses lossless compression for faster Godot import times. |
| `--mesh-scale` | 1.0 | Scale factor for mesh vertices. Use when packs are undersized (e.g., `--mesh-scale 100` for packs that are 100x too small). |
| `--output-subfolder` | None | Subfolder path prepended to pack folder names. Example: `--output-subfolder synty/` creates packs at `output/synty/POLYGON_PackName/` instead of `output/POLYGON_PackName/`. Useful for organizing multiple packs. |
| `--retain-subfolders` | Off | Preserve Source_Files/FBX/ subdirectory structure in mesh output. By default, paths are flattened and all meshes go directly to `meshes/tscn_separate/`. |

---

## Output Structure

After conversion, your output directory contains:

```
output/
  project.godot              # Godot project file with global shader uniforms
  conversion_log.txt         # Warnings, errors, statistics (appends for multi-pack)
  converter_config.json      # Runtime config for Godot converter (intermediate file)
  shaders/                   # Community drop-in shaders (7 files, shared across packs)
    polygon.gdshader         # Static props, buildings, terrain
    foliage.gdshader         # Trees, ferns, grass, vegetation
    crystal.gdshader         # Crystals, gems, glass, ice
    water.gdshader           # Rivers, lakes, oceans, ponds
    clouds.gdshader          # Volumetric clouds, sky effects
    particles.gdshader       # Particles, fog, distant effects
    skydome.gdshader         # Gradient sky domes
  POLYGON_PackName/          # Each pack gets its own folder
    textures/                # Textures referenced by this pack's materials
      PolygonFantasy_Texture_01.png
      ...
    materials/               # Generated ShaderMaterial .tres files
      PolygonFantasy_Mat_01_A.tres
      Crystal_Mat_01.tres
      ...
    models/                  # Copied FBX files (preserves subdirectory structure)
      Characters/
      Environment/
      Props/
      ...
    meshes/                  # Mesh output organized by configuration
      tscn_separate/         # Default: --mesh-format tscn (one file per mesh)
        Characters/
          SM_Chr_Knight_01.tscn
        Environment/
          SM_Env_Tree_Pine_01_LOD0.tscn
          SM_Env_Tree_Pine_01_LOD1.tscn
        ...
      tscn_combined/         # --mesh-format tscn --keep-meshes-together
      res_separate/          # --mesh-format res (one file per mesh)
      res_combined/          # --mesh-format res --keep-meshes-together
    mesh_material_mapping.json  # Mesh-to-material assignments (per-pack)
```

### Understanding the Output

**meshes/{format}_{mode}/** - Mesh output is organized into subfolders based on your conversion options:
- `tscn_separate/` - Text format, one file per mesh (default)
- `tscn_combined/` - Text format, one file per FBX (with `--keep-meshes-together`)
- `res_separate/` - Binary format, one file per mesh
- `res_combined/` - Binary format, one file per FBX

This allows you to try different configurations without overwriting previous output. Each .tscn/.res file is a standalone scene with a MeshInstance3D root node and materials assigned as surface overrides. Drag these directly into your scenes.

**materials/** - ShaderMaterial .tres files. These are automatically assigned to meshes via external resource references.

**models/** - Raw FBX files. These are used by Godot during import but aren't needed at runtime.

**shaders/** - Contains the drop-in replacement shaders. Shaders are only copied if they don't already exist elsewhere in the project, preventing duplicates when converting multiple packs.

**mesh_material_mapping.json** - Each pack has its own mapping file in its folder. This enables incremental multi-pack workflows where converting Pack B doesn't re-process Pack A.

### Incremental Conversion (Existing Pack Detection)

When re-running the converter on a pack that already has `materials/`, `textures/`, `models/`, and `mesh_material_mapping.json`, the converter detects this as an existing pack and skips phases 3-10 (extraction, parsing, material generation, texture/FBX copying). Only the mesh generation phase runs.

This is useful for:
- Trying different `--mesh-format` options (tscn vs res)
- Trying different `--keep-meshes-together` settings
- Regenerating meshes after updating Godot or the converter

The GUI displays "Existing pack detected - mesh regeneration only" when this mode is active, and shows the target mesh subfolder (e.g., "Mesh output: meshes/tscn_separate/").

---

## Advanced Usage

### Dry-Run Mode

Preview the conversion without writing any files:

```bash
python converter.py \
    --unity-package "Fantasy.unitypackage" \
    --source-files "SourceFiles" \
    --output "output" \
    --godot "godot.exe" \
    --dry-run
```

Output shows what would be created:
```
[DRY RUN] Would create directory: output/shaders
[DRY RUN] Would write material: PolygonFantasy_Mat_01_A.tres
[DRY RUN] Would copy texture: PolygonFantasy_Texture_01.png
...
```

### Verbose Mode

Enable detailed logging for debugging:

```bash
python converter.py \
    --unity-package "Fantasy.unitypackage" \
    --source-files "SourceFiles" \
    --output "output" \
    --godot "godot.exe" \
    --verbose
```

Verbose output includes:
- Shader detection decisions (GUID lookup, pattern matching, property detection)
- Property mappings (Unity parameter -> Godot parameter)
- Texture resolution attempts
- Godot CLI stdout/stderr

### Skip Options

**Skip FBX Copy** - Re-run conversion without re-copying large FBX files:
```bash
python converter.py ... --skip-fbx-copy
```

**Skip Godot CLI** - Generate only materials (useful for debugging):
```bash
python converter.py ... --skip-godot-cli
```

### Timeout Configuration

For very large packs, increase the Godot CLI timeout:

```bash
python converter.py ... --godot-timeout 1200  # 20 minutes
```

### Mesh Grouping Options

**Keep Meshes Together** - Save all meshes from one FBX as a single scene:

```bash
python converter.py ... --keep-meshes-together
```

This is useful when:
- You want to preserve the original FBX hierarchy
- A single FBX contains multiple related meshes (e.g., a building with doors and windows)
- You prefer fewer scene files to manage

Default behavior (without this flag) saves each mesh as a separate scene file, which is better for:
- Modular asset usage (placing individual props)
- Memory efficiency (loading only needed meshes)
- Instancing many copies of individual meshes

### Output Format Options

**Binary Format** - Use compiled .res format instead of text .tscn:

```bash
python converter.py ... --mesh-format res
```

| Format | Extension | Pros | Cons |
|--------|-----------|------|------|
| `tscn` | .tscn | Human-readable, diff-friendly, editable | Larger file size |
| `res` | .res | Smaller, faster to load | Binary, not editable |

### Filter Option

**Convert Only Specific Files** - Process only FBX files matching a pattern:

```bash
# Only convert tree-related assets
python converter.py ... --filter Tree

# Only convert vehicle assets
python converter.py ... --filter Veh

# Only convert character assets
python converter.py ... --filter Chr
```

The filter is case-insensitive and matches anywhere in the FBX filename. This is useful for:
- Testing conversion with a subset of assets
- Converting only specific categories (trees, props, characters)
- Faster iteration when debugging specific assets

**Smart Filtering**: When using `--filter`, the converter automatically identifies which materials AND textures are needed by the filtered FBX files and only processes those. This dramatically reduces output size and conversion time when converting a subset of assets.

Example: Using `--filter Chest` on POLYGON Samurai Empire reduces textures from 234 to just 8 files (97% reduction), and similarly reduces the number of generated material files.

### High Quality Textures

**Use BPTC compression** for improved texture quality at the cost of larger file sizes:

```bash
python converter.py ... --high-quality-textures
```

This option enables BPTC (BC7) texture compression in Godot's import settings:
- Higher visual quality, especially for gradients and transparency
- Larger compressed texture files
- Slower Godot import times
- Recommended for hero assets or when visual fidelity is critical

The default uses lossless compression (mode=0) for faster Godot import times.

### Mesh Scale

**Scale undersized meshes** when packs import at incorrect sizes:

```bash
python converter.py ... --mesh-scale 100
```

Some Synty packs may import at 1/100th scale. Use this option to fix the scale during conversion rather than manually rescaling in Godot. The scale factor is applied to all mesh vertices during the Godot conversion step.

### Output Subfolder

**Organize packs into a subfolder** within the output directory:

```bash
python converter.py ... --output-subfolder synty/
```

This option prepends a subfolder path to pack folder names. Without it, packs go directly into the output directory. With it, packs are nested under the specified subfolder:

| Command | Output Location |
|---------|-----------------|
| `--output "C:/Project"` | `C:/Project/POLYGON_Fantasy/` |
| `--output "C:/Project" --output-subfolder synty/` | `C:/Project/synty/POLYGON_Fantasy/` |
| `--output "C:/Project" --output-subfolder assets/synty/` | `C:/Project/assets/synty/POLYGON_Fantasy/` |

This is useful for:
- Organizing multiple packs under a common folder
- Keeping Synty assets separate from other project assets
- Matching existing project structure conventions

### Retain Subfolders

**Preserve source directory structure** in mesh output:

```bash
python converter.py ... --retain-subfolders
```

By default, the converter flattens output and all meshes go directly into `meshes/tscn_separate/` without subdirectories. With `--retain-subfolders`, the subdirectory structure from the FBX source files is preserved (e.g., `meshes/tscn_separate/Props/` or `meshes/tscn_separate/Environment/`).

| Mode | Output Structure |
|------|------------------|
| Default (flattened) | `meshes/tscn_separate/SM_Prop_Barrel.tscn` |
| `--retain-subfolders` | `meshes/tscn_separate/Props/SM_Prop_Barrel.tscn` |

Flattening (the default) is useful when:
- You prefer a flat file structure
- Your source FBX paths have unwanted nesting (e.g., `Source_Files/FBX/...`)
- You're filtering to a small subset of assets and don't need subdirectories

**Note:** The converter automatically strips common Synty path prefixes (`sourcefiles`, `source_files`, `fbx`, `models`, `bonusfbx`) from FBX paths when copying, regardless of whether flatten output is enabled. This prevents deeply nested output structures.

---

## Multi-Pack Workflow

The converter is designed for incremental multi-pack workflows:

### Per-Pack Isolation

Each pack is converted to its own subfolder:
```
output/
  POLYGON_Fantasy/
    textures/
    materials/
    models/
    meshes/
    mesh_material_mapping.json
  POLYGON_Nature/
    textures/
    materials/
    models/
    meshes/
    mesh_material_mapping.json
  shaders/                    # Shared across all packs
  project.godot
  conversion_log.txt          # Appends entries for each pack
```

### Smart Shader Discovery

When converting a second pack to the same project:
1. The converter searches the entire project for existing shaders
2. If shaders are found (even if moved to a different location), those paths are used
3. New shaders are only copied if they don't exist anywhere in the project

This prevents duplicate shader files when converting multiple packs.

### Incremental Conversion

Converting Pack B after Pack A:
- Pack A's files are untouched
- Only Pack B's folder is created/updated
- The Godot converter script only processes Pack B (via `pack_name` in converter_config.json)
- `conversion_log.txt` appends Pack B's summary

---

## Batch Processing

Convert multiple Synty packs in sequence using a shell script.

### Windows Batch Script

Create `convert_all.bat`:

```batch
@echo off
setlocal

set GODOT="C:\Godot\Godot_v4.6-stable_mono_win64\Godot_v4.6-stable_mono_win64.exe"
set SYNTY="C:\SyntyComplete"
set OUTPUT="C:\Godot\Projects\SyntyAssets"
set CONVERTER="C:\Godot\Projects\synty-converter\converter.py"

:: Fantasy Pack
python %CONVERTER% ^
    --unity-package "%SYNTY%\POLYGON_Fantasy\Fantasy.unitypackage" ^
    --source-files "%SYNTY%\POLYGON_Fantasy\SourceFiles" ^
    --output "%OUTPUT%\Fantasy" ^
    --godot %GODOT%

:: Nature Biomes Pack
python %CONVERTER% ^
    --unity-package "%SYNTY%\POLYGON_NatureBiomes\NatureBiomes.unitypackage" ^
    --source-files "%SYNTY%\POLYGON_NatureBiomes\SourceFiles" ^
    --output "%OUTPUT%\NatureBiomes" ^
    --godot %GODOT%

:: SciFi Pack
python %CONVERTER% ^
    --unity-package "%SYNTY%\POLYGON_SciFi\SciFi.unitypackage" ^
    --source-files "%SYNTY%\POLYGON_SciFi\SourceFiles" ^
    --output "%OUTPUT%\SciFi" ^
    --godot %GODOT%

echo All packs converted!
pause
```

### Linux/macOS Shell Script

Create `convert_all.sh`:

```bash
#!/bin/bash

GODOT="/usr/local/bin/godot"
SYNTY="$HOME/SyntyAssets"
OUTPUT="$HOME/GodotProjects/SyntyAssets"
CONVERTER="$HOME/tools/synty-converter/converter.py"

PACKS=(
    "POLYGON_Fantasy"
    "POLYGON_NatureBiomes"
    "POLYGON_SciFi"
    "POLYGON_City"
)

for pack in "${PACKS[@]}"; do
    echo "Converting $pack..."

    # Find the .unitypackage file (name varies by pack)
    PACKAGE=$(find "$SYNTY/$pack" -name "*.unitypackage" | head -1)

    python "$CONVERTER" \
        --unity-package "$PACKAGE" \
        --source-files "$SYNTY/$pack/SourceFiles" \
        --output "$OUTPUT/$pack" \
        --godot "$GODOT"

    echo "$pack complete!"
    echo "---"
done

echo "All packs converted!"
```

Make executable: `chmod +x convert_all.sh`

---

## Post-Conversion Steps

### 1. Opening in Godot

1. Launch Godot 4.6
2. Click "Import" and navigate to the output directory
3. Select the `project.godot` file
4. Godot will import all resources (may take a few minutes for large packs)

### 2. Setting Up Global Shader Uniforms

The converter generates `project.godot` with sensible defaults for global shader uniforms. To customize:

1. Open **Project > Project Settings > Globals > Shader Globals**
2. Adjust these parameters:

| Uniform | Type | Purpose | Default |
|---------|------|---------|---------|
| WindDirection | vec3 | Direction wind blows (foliage) | (1, 0, 0) |
| WindIntensity | float | Strength of wind animation | 0.5 |
| GaleStrength | float | Intensity of gale gusts | 0.0 |
| MainLightDirection | vec3 | Sun/moon direction (sky/clouds) | (0.5, -0.5, 0) |
| SkyColor | color | Top of sky gradient | Light blue |
| EquatorColor | color | Horizon color | Warm white |
| GroundColor | color | Bottom of sky gradient | Brown/gray |
| OceanWavesGradient | sampler2D | Wave texture for water | Empty |

### 3. Using Converted Meshes

The `meshes/` folder contains ready-to-use scene files:

**Method 1: Drag and Drop**
1. Open the FileSystem panel in Godot
2. Navigate to `meshes/`
3. Drag a `.tscn` file into your 3D scene

**Method 2: Instantiate Scene**
1. Right-click in the Scene panel
2. Select "Instance Child Scene..."
3. Navigate to the mesh `.tscn` file

**Method 3: Script**
```gdscript
var mesh_scene = load("res://meshes/Props/SM_Prop_Chest_01.tscn")
var instance = mesh_scene.instantiate()
add_child(instance)
```

### 4. Working with LOD Variants

Meshes with LOD levels are saved as separate files:
```
SM_Env_Tree_Pine_01_LOD0.tscn  # Highest detail
SM_Env_Tree_Pine_01_LOD1.tscn  # Medium detail
SM_Env_Tree_Pine_01_LOD2.tscn  # Lowest detail
```

Use Godot's LOD system or manually switch based on distance.

**Note:** When using `--keep-meshes-together`, all LOD meshes from one FBX are saved together in a single combined scene.

---

## Troubleshooting

### Common Issues

**"Unity package not found"**
- Verify the path to .unitypackage is correct
- Use absolute paths to avoid working directory issues

**"Textures directory not found" (informational)**
- This is now just a warning, not an error
- Textures are primarily extracted from the .unitypackage file
- The SourceFiles/Textures directory is used as a fallback source
- Some packs may not include a separate Textures directory

**"Godot executable not found"**
- Verify the Godot path is correct
- On Windows, include the full `.exe` extension

**"Godot CLI timed out"**
- Increase timeout: `--godot-timeout 1200`
- Large packs with 1000+ FBX files may take 10-20 minutes

**Materials appear wrong/missing textures**
- Check `conversion_log.txt` for texture warnings
- Verify textures exist in SourceFiles/Textures
- Some textures may use different naming conventions

**Meshes have no materials**
- Check if MaterialList.txt exists in SourceFiles
- Run with `--verbose` to see material assignment details

### Reading the Conversion Log

After each conversion, check `conversion_log.txt` in the project root. The log appends entries for each pack conversion:

```
================================================================================
Conversion: POLYGON_Fantasy
Date: 2024-01-15 10:30:00
================================================================================
Unity Package: C:\Synty\Fantasy\Fantasy.unitypackage
Source Files: C:\Synty\Fantasy\SourceFiles
Output Directory: C:\Godot\Projects\Assets

Statistics:
  Materials Parsed: 145
  Materials Generated: 145
  Textures Copied: 23
  Textures Missing: 2
  Shaders Copied: 7
  FBX Files Copied: 342
  Meshes Converted: 856

Warnings (2):
  - Texture not found: PolygonFantasy_Texture_Special
  - Failed to parse material GUID abc123: Invalid YAML

================================================================================

================================================================================
Conversion: POLYGON_Nature
Date: 2024-01-15 10:45:00
================================================================================
...
```

### Getting Help

If you encounter issues:

1. Run with `--verbose` to get detailed logs
2. Check `conversion_log.txt` for warnings and errors
3. Review the [Architecture](architecture.md) for technical details
4. Verify your Synty pack structure matches expected format
