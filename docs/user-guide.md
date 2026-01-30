# User Guide

Comprehensive guide to using the Synty Unity-to-Godot Converter.

## Table of Contents

- [Installation](#installation)
- [Understanding Synty Asset Structure](#understanding-synty-asset-structure)
- [Basic Usage](#basic-usage)
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

   The converter uses only Python standard library modules - no pip packages required.

2. **Godot 4.6**

   Download from [godotengine.org](https://godotengine.org). Either the standard or Mono version works.

   Verify Godot is accessible:
   ```bash
   "C:\Godot\Godot_v4.6-stable_mono_win64\Godot_v4.6-stable_mono_win64.exe" --version
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
  FBX/                 # 3D models ready for import
    Characters/
    Environment/
    Props/
    ...
  Textures/            # High-resolution textures (PNG, TGA)
    Atlas textures
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

## Command-Line Options

### Required Arguments

| Flag | Description | Example |
|------|-------------|---------|
| `--unity-package` | Path to the .unitypackage file from the Synty pack | `"C:\Synty\Fantasy\Fantasy.unitypackage"` |
| `--source-files` | Path to the SourceFiles folder (must contain Textures/) | `"C:\Synty\Fantasy\SourceFiles"` |
| `--output` | Output directory for the generated Godot project | `"C:\Godot\Projects\fantasy"` |
| `--godot` | Path to Godot 4.6 executable | `"C:\Godot\Godot_v4.6.exe"` |

### Optional Arguments

| Flag | Default | Description |
|------|---------|-------------|
| `--dry-run` | Off | Preview what would be done without writing any files. Useful for validation. |
| `--verbose` | Off | Enable debug-level logging. Shows detailed shader detection, property mapping, and file operations. |
| `--skip-fbx-copy` | Off | Skip copying FBX files to output/models/. Use when re-running conversion and models already exist. |
| `--skip-godot-cli` | Off | Skip running Godot CLI. Generates materials only, no mesh .res files. Useful for debugging material issues. |
| `--godot-timeout` | 600 | Maximum seconds for Godot CLI operations. Increase for very large packs. |

---

## Output Structure

After conversion, your output directory contains:

```
output/
  project.godot              # Godot project file with global shader uniforms
  shaders/                   # Community drop-in shaders (7 files)
    polygon.gdshader         # Static props, buildings, terrain
    foliage.gdshader         # Trees, ferns, grass, vegetation
    crystal.gdshader         # Crystals, gems, glass, ice
    water.gdshader           # Rivers, lakes, oceans, ponds
    clouds.gdshader          # Volumetric clouds, sky effects
    particles.gdshader       # Particles, fog, distant effects
    skydome.gdshader         # Gradient sky domes
  textures/                  # Textures referenced by materials
    PolygonFantasy_Texture_01.png
    PolygonFantasy_Texture_02.png
    ...
  materials/                 # Generated ShaderMaterial .tres files
    PolygonFantasy_Mat_01_A.tres
    Crystal_Mat_01.tres
    Water_River_Mat.tres
    ...
  models/                    # Copied FBX files (preserves subdirectory structure)
    Characters/
    Environment/
    Props/
    ...
  meshes/                    # Converted mesh .res files (ready to use!)
    Characters/
      SM_Chr_Knight_01.res
    Environment/
      SM_Env_Tree_Pine_01_LOD0.res
      SM_Env_Tree_Pine_01_LOD1.res
    ...
  mesh_material_mapping.json # Mesh-to-material assignments (intermediate file)
  conversion_log.txt         # Warnings, errors, statistics
```

### Understanding the Output

**meshes/** - This is what you use in your Godot project. Each .res file is a standalone Mesh resource with materials already baked into surfaces. Drag these directly into your scenes.

**materials/** - ShaderMaterial .tres files. These are automatically assigned to meshes, but you can also use them manually.

**models/** - Raw FBX files. These are used by Godot during import but aren't needed at runtime.

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

The `meshes/` folder contains ready-to-use Mesh resources:

**Method 1: Drag and Drop**
1. Open the FileSystem panel in Godot
2. Navigate to `meshes/`
3. Drag a `.res` file into your 3D scene

**Method 2: MeshInstance3D**
1. Create a MeshInstance3D node
2. In the Inspector, click the Mesh property
3. Select "Load" and choose a `.res` file

**Method 3: Script**
```gdscript
var mesh = load("res://meshes/Props/SM_Prop_Chest_01.res")
var instance = MeshInstance3D.new()
instance.mesh = mesh
add_child(instance)
```

### 4. Working with LOD Variants

Meshes with LOD levels are saved as separate files:
```
SM_Env_Tree_Pine_01_LOD0.res  # Highest detail
SM_Env_Tree_Pine_01_LOD1.res  # Medium detail
SM_Env_Tree_Pine_01_LOD2.res  # Lowest detail
```

Use Godot's LOD system or manually switch based on distance.

---

## Troubleshooting

### Common Issues

**"Unity package not found"**
- Verify the path to .unitypackage is correct
- Use absolute paths to avoid working directory issues

**"Textures directory not found"**
- The SourceFiles folder must contain a `Textures/` subdirectory
- Some older packs may have a different structure

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

After each conversion, check `conversion_log.txt`:

```
============================================================
Synty Shader Converter - Conversion Log
============================================================
Date: 2024-01-15T10:30:00
Unity Package: C:\Synty\Fantasy\Fantasy.unitypackage
Source Files: C:\Synty\Fantasy\SourceFiles
Output Directory: C:\Godot\Projects\Fantasy

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

============================================================
```

### Getting Help

If you encounter issues:

1. Run with `--verbose` to get detailed logs
2. Check `conversion_log.txt` for warnings and errors
3. Review the [Architecture](architecture.md) for technical details
4. Verify your Synty pack structure matches expected format
