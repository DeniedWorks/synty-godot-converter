# Step 2: Create Output Directories

This document provides a comprehensive analysis of Step 2 in the Synty Converter pipeline: creating the output directory structure for converted assets.

## Table of Contents

- [Overview](#overview)
- [Directory Structure](#directory-structure)
- [Function Analysis](#function-analysis)
  - [setup_output_directories()](#setup_output_directories)
  - [copy_shaders()](#copy_shaders)
- [Path Handling](#path-handling)
- [Error Handling](#error-handling)
- [Dry Run Mode](#dry-run-mode)
- [Code Flow Integration](#code-flow-integration)
- [Code Examples](#code-examples)
- [Related Documentation](#related-documentation)
- [Notes for Doc Cleanup](#notes-for-doc-cleanup)

---

## Overview

Step 2 creates the directory structure required for output assets. This step runs early in the pipeline (immediately after input validation) because all subsequent steps depend on these directories existing.

The converter uses a two-tier directory structure:
1. **Project-level directories** at `output_dir/` - Contains `project.godot`, `shaders/` (shared across packs)
2. **Pack-level directories** at `output_dir/PackName/` - Contains pack-specific assets (`textures/`, `materials/`, `models/`, `meshes/`)

This design supports converting multiple Synty packs into a single Godot project while sharing shader resources.

---

## Directory Structure

### Complete Output Layout

```
output_dir/                      # User-specified output directory
  project.godot                  # Godot project file (created in Step 10)
  converter_config.json          # Config for GDScript converter
  shaders/                       # SHARED across all packs
    polygon.gdshader             # Static props, buildings, terrain
    foliage.gdshader             # Trees, ferns, grass, vegetation
    crystal.gdshader             # Crystals, gems, glass, ice
    water.gdshader               # Rivers, lakes, oceans
    clouds.gdshader              # Volumetric clouds
    particles.gdshader           # Soft particles, fog effects
    skydome.gdshader             # Gradient sky domes
    mesh_material_mapping.json   # Mesh-to-material assignments
  PackName/                      # Pack-specific subdirectory
    textures/                    # Copied texture files
    materials/                   # Generated .tres material files
    models/                      # Copied FBX source files
    meshes/                      # Converted .tscn scene files
```

### Directory Purposes

| Directory | Purpose | Created By | Contents |
|-----------|---------|------------|----------|
| `output_dir/` | Project root | `setup_output_directories()` | `project.godot`, `shaders/`, pack folders |
| `shaders/` | Shared shader resources | `copy_shaders()` | 7 `.gdshader` files, `mesh_material_mapping.json` |
| `textures/` | Pack texture assets | `setup_output_directories()` | PNG, TGA files with `.import` sidecars |
| `materials/` | Generated Godot materials | `setup_output_directories()` | `.tres` ShaderMaterial resources |
| `models/` | FBX source files | `setup_output_directories()` | FBX files (preserves subdirectory structure) |
| `meshes/` | Final converted scenes | `setup_output_directories()` | `.tscn` scene files ready for use |

### Key Design Decisions

1. **Shaders at project root**: The `shaders/` directory is created at `output_dir/shaders/`, not inside the pack folder. This allows multiple packs to share the same shader files without duplication.

2. **Pack subfolder isolation**: Each pack gets its own subdirectory (`output_dir/PackName/`) to avoid asset name collisions between packs.

3. **Structure preservation**: The `models/` directory preserves the original FBX subdirectory structure (Props/, Environment/, Characters/, etc.) from the source files.

---

## Function Analysis

### setup_output_directories()

**Location:** `converter.py`, lines 520-549

**Purpose:** Creates the pack-specific directory structure for assets.

```python
def setup_output_directories(output_dir: Path, dry_run: bool) -> None:
    """Create the output directory structure for pack assets.

    Creates:
        output_dir/
            textures/
            materials/
            models/
            meshes/

    Note: shaders/ is created at project root by copy_shaders(), not here.

    Args:
        output_dir: Pack output directory.
        dry_run: If True, only log what would be created.
    """
    directories = [
        output_dir,
        output_dir / "textures",
        output_dir / "materials",
        output_dir / "models",
        output_dir / "meshes",
    ]

    for directory in directories:
        if dry_run:
            logger.debug("[DRY RUN] Would create directory: %s", directory)
        else:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug("Created directory: %s", directory)
```

#### Line-by-Line Analysis

| Line | Code | Explanation |
|------|------|-------------|
| 536-542 | `directories = [...]` | Builds a list of all directories to create. Includes the root `output_dir` plus four subdirectories. |
| 537 | `output_dir,` | The pack's root directory (e.g., `C:/output/PolygonNature/`) |
| 538 | `output_dir / "textures",` | Uses Path's `/` operator for cross-platform path joining |
| 544 | `for directory in directories:` | Iterates through each directory to create |
| 545-546 | `if dry_run:` | Dry run mode only logs, doesn't create |
| 548 | `directory.mkdir(parents=True, exist_ok=True)` | Creates directory with all parents; no error if exists |
| 549 | `logger.debug("Created directory: %s", directory)` | Logs at DEBUG level (only visible with `--verbose`) |

#### mkdir() Parameters Explained

- **`parents=True`**: Creates any missing parent directories. For example, if `output_dir` doesn't exist, it will be created automatically when creating `output_dir/textures/`.
- **`exist_ok=True`**: Does not raise an error if the directory already exists. This makes the operation idempotent, allowing safe re-runs of the converter.

#### Important Notes

1. **Does NOT create `shaders/`**: The docstring explicitly notes that `shaders/` is created by `copy_shaders()` at the project root, not inside the pack folder.

2. **Pack-scoped**: This function receives `pack_output_dir` (e.g., `output_dir/PackName/`), not the bare `output_dir`. The pack name is determined in `run_conversion()`.

3. **No return value**: Returns `None`; directories are created as a side effect.

---

### copy_shaders()

**Location:** `converter.py`, lines 552-598

**Purpose:** Copies shader files from the converter project to the output project's `shaders/` directory.

```python
def copy_shaders(shaders_dest: Path, dry_run: bool) -> int:
    """Copy .gdshader files from project's shaders/ to destination.

    Args:
        shaders_dest: Destination directory for shader files.
        dry_run: If True, only log what would be copied.

    Returns:
        Number of shader files copied (or would be copied in dry run).
    """
    # Source shaders are relative to where this script is located
    script_dir = Path(__file__).parent
    shaders_source = script_dir / "shaders"

    # Ensure destination directory exists
    if not dry_run:
        shaders_dest.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    for shader_file in SHADER_FILES:
        source_path = shaders_source / shader_file
        dest_path = shaders_dest / shader_file

        if not source_path.exists():
            logger.warning("Shader file not found: %s", source_path)
            continue

        # Skip if shader already exists (shared shaders persist across packs)
        if dest_path.exists():
            logger.debug("Shader already exists, skipping: %s", shader_file)
            skipped += 1
            continue

        if dry_run:
            logger.debug("[DRY RUN] Would copy shader: %s -> %s", source_path, dest_path)
        else:
            shutil.copy2(source_path, dest_path)
            logger.debug("Copied shader: %s", shader_file)

        copied += 1

    if skipped > 0:
        logger.debug("Copied %d shader files (%d already existed)", copied, skipped)
    else:
        logger.debug("Copied %d shader files", copied)
    return copied
```

#### Line-by-Line Analysis

| Line | Code | Explanation |
|------|------|-------------|
| 562-564 | `script_dir = Path(__file__).parent` | Gets the directory containing `converter.py` |
| 564 | `shaders_source = script_dir / "shaders"` | Source shaders are in `synty-converter/shaders/` |
| 567-568 | `shaders_dest.mkdir(...)` | Creates `shaders/` directory at destination (only if not dry run) |
| 572 | `for shader_file in SHADER_FILES:` | Iterates through the predefined list of shader filenames |
| 576-578 | `if not source_path.exists():` | Warns if a shader file is missing from the converter project |
| 581-584 | `if dest_path.exists():` | Skips copy if shader already exists (supports multi-pack conversion) |
| 589 | `shutil.copy2(...)` | Copies file with metadata (timestamps, permissions) |

#### SHADER_FILES Constant

**Location:** `converter.py`, lines 128-137

```python
# Shader files to copy from project's shaders/ directory
SHADER_FILES = [
    "clouds.gdshader",
    "crystal.gdshader",
    "foliage.gdshader",
    "particles.gdshader",
    "polygon.gdshader",
    "skydome.gdshader",
    "water.gdshader",
]
```

These 7 shaders are community drop-in replacements for Unity's Synty shaders, sourced from GodotShaders.com.

#### Skip Logic for Multi-Pack Support

The function includes logic to skip copying if shaders already exist:

```python
if dest_path.exists():
    logger.debug("Shader already exists, skipping: %s", shader_file)
    skipped += 1
    continue
```

This is critical for multi-pack workflows where multiple Synty packs are converted into the same Godot project. The shaders only need to be copied once; subsequent pack conversions reuse the existing shaders.

---

## Path Handling

### Library Used

The converter uses Python's `pathlib.Path` for all path operations, not the older `os.path` module. This provides:

1. **Cross-platform compatibility**: Path separators are handled automatically
2. **Object-oriented API**: Cleaner syntax with `/` operator for path joining
3. **Built-in methods**: `.mkdir()`, `.exists()`, `.parent`, etc.

### Key Path Operations Used

| Operation | Example | Purpose |
|-----------|---------|---------|
| `Path(__file__).parent` | Gets script directory | Locate bundled shaders |
| `path / "subdir"` | `output_dir / "textures"` | Join paths safely |
| `path.mkdir(parents=True, exist_ok=True)` | Create directory tree | Safe directory creation |
| `path.exists()` | Check before operations | Skip existing files |
| `path.resolve()` | Get absolute path | Normalize paths |

### Pack Name Extraction

**Location:** `converter.py`, lines 1722-1728

```python
# Extract pack name from source_files parent directory
# e.g., C:\SyntyComplete\PolygonNature\SourceFiles -> pack_name = "PolygonNature"
raw_pack_name = config.source_files.parent.name
# Sanitize to remove invalid filesystem characters
pack_name = sanitize_filename(raw_pack_name)
if pack_name != raw_pack_name:
    logger.warning("Pack name sanitized: '%s' -> '%s'", raw_pack_name, pack_name)
```

The pack name is derived from the parent directory of `SourceFiles/`, then sanitized to remove any filesystem-invalid characters.

### Output Path Construction

**Location:** `converter.py`, lines 1730-1736

```python
# Consistent output structure:
# - project.godot at output_dir root (create new or merge uniforms)
# - shaders/ at output_dir root (shared across all packs)
# - PackName/ subfolder for pack-specific assets
pack_output_dir = config.output_dir / pack_name
shaders_dir = config.output_dir / "shaders"
project_dir = config.output_dir
```

---

## Error Handling

### Directory Creation

The `mkdir(parents=True, exist_ok=True)` call handles all common error cases:

| Scenario | Behavior |
|----------|----------|
| Directory doesn't exist | Creates it (and all parents) |
| Directory already exists | No error, continues silently |
| Parent doesn't exist | Creates all parents automatically |
| Permission denied | Raises `PermissionError` (not caught) |
| Invalid path characters | Raises `OSError` (not caught) |

### Missing Shader Files

```python
if not source_path.exists():
    logger.warning("Shader file not found: %s", source_path)
    continue
```

If a shader file is missing from the converter's `shaders/` directory:
- A warning is logged
- The file is skipped
- Conversion continues (non-fatal error)

### No Explicit Try/Except

Neither `setup_output_directories()` nor `copy_shaders()` have try/except blocks. Exceptions propagate to the caller (`run_conversion()`), which has broad exception handling:

```python
# In run_conversion() - Step 3 example shows the pattern
try:
    guid_map = extract_unitypackage(config.unity_package)
except Exception as e:
    error_msg = f"Failed to extract Unity package: {e}"
    logger.error(error_msg)
    stats.errors.append(error_msg)
    return stats
```

However, Step 2 (directory creation) does not have this wrapper because directory creation failures are treated as immediately fatal - there's no point continuing if we can't create output directories.

---

## Dry Run Mode

Both functions support dry run mode for previewing operations without making changes.

### setup_output_directories() in Dry Run

```python
if dry_run:
    logger.debug("[DRY RUN] Would create directory: %s", directory)
else:
    directory.mkdir(parents=True, exist_ok=True)
    logger.debug("Created directory: %s", directory)
```

Output (with `--verbose --dry-run`):
```
DEBUG: [DRY RUN] Would create directory: C:\output\PolygonNature
DEBUG: [DRY RUN] Would create directory: C:\output\PolygonNature\textures
DEBUG: [DRY RUN] Would create directory: C:\output\PolygonNature\materials
DEBUG: [DRY RUN] Would create directory: C:\output\PolygonNature\models
DEBUG: [DRY RUN] Would create directory: C:\output\PolygonNature\meshes
```

### copy_shaders() in Dry Run

```python
# Ensure destination directory exists
if not dry_run:
    shaders_dest.mkdir(parents=True, exist_ok=True)
```

Note: The `shaders/` directory creation is skipped entirely in dry run (not just logged). This prevents side effects.

---

## Code Flow Integration

### Where Step 2 Fits in the Pipeline

**Location:** `converter.py`, lines 1752-1754

```python
# Step 2: Create output directory structure
logger.info("Step 2: Creating directories...")
setup_output_directories(pack_output_dir, config.dry_run)
```

### Complete Pipeline Context

```
Step 1: Validate inputs (parse_args)
    |
    v
Step 2: Create output directories  <-- THIS STEP
    |-- setup_output_directories(pack_output_dir)
    |       Creates: textures/, materials/, models/, meshes/
    |
    v
Step 3: Extract Unity package
    |
    v
Step 4-6: Parse materials, detect shaders, generate .tres
    |       Writes to: materials/
    |
    v
Step 7: Copy shaders
    |-- copy_shaders(shaders_dir)
    |       Creates: shaders/
    |       Copies: 7 .gdshader files
    |
    v
Step 8: Copy textures
    |       Writes to: textures/
    |
    v
Step 8.5: Copy FBX files
    |       Writes to: models/
    |
    v
Step 9-11: Generate mapping, project.godot, run Godot CLI
    |       Writes to: meshes/
```

### Additional Directory Creation

Some later functions create subdirectories within the established structure:

```python
# copy_fbx_files() creates subdirectories in models/
dest_path.parent.mkdir(parents=True, exist_ok=True)  # Line 1035
```

This handles FBX files in subdirectories like `Props/`, `Environment/`, etc.

---

## Code Examples

### Basic Usage

```python
from pathlib import Path
from converter import setup_output_directories, copy_shaders

# Create pack directories
pack_output = Path("C:/Godot/Projects/output/PolygonNature")
setup_output_directories(pack_output, dry_run=False)
# Creates:
#   C:/Godot/Projects/output/PolygonNature/
#   C:/Godot/Projects/output/PolygonNature/textures/
#   C:/Godot/Projects/output/PolygonNature/materials/
#   C:/Godot/Projects/output/PolygonNature/models/
#   C:/Godot/Projects/output/PolygonNature/meshes/

# Copy shaders to project root
shaders_dir = Path("C:/Godot/Projects/output/shaders")
copied = copy_shaders(shaders_dir, dry_run=False)
print(f"Copied {copied} shader files")
# Creates:
#   C:/Godot/Projects/output/shaders/
#   C:/Godot/Projects/output/shaders/polygon.gdshader
#   C:/Godot/Projects/output/shaders/foliage.gdshader
#   ... (5 more)
```

### Dry Run Preview

```python
from pathlib import Path
from converter import setup_output_directories

# Preview without creating
pack_output = Path("C:/Godot/Projects/output/PolygonNature")
setup_output_directories(pack_output, dry_run=True)
# Output (with verbose logging):
#   [DRY RUN] Would create directory: C:/Godot/Projects/output/PolygonNature
#   [DRY RUN] Would create directory: C:/Godot/Projects/output/PolygonNature/textures
#   [DRY RUN] Would create directory: C:/Godot/Projects/output/PolygonNature/materials
#   [DRY RUN] Would create directory: C:/Godot/Projects/output/PolygonNature/models
#   [DRY RUN] Would create directory: C:/Godot/Projects/output/PolygonNature/meshes
```

### Multi-Pack Conversion

```python
from pathlib import Path
from converter import setup_output_directories, copy_shaders

output_root = Path("C:/Godot/Projects/SyntyAssets")
shaders_dir = output_root / "shaders"

# First pack
setup_output_directories(output_root / "PolygonNature", dry_run=False)
copied = copy_shaders(shaders_dir, dry_run=False)
print(f"Pack 1: Copied {copied} shaders")  # 7 shaders

# Second pack
setup_output_directories(output_root / "PolygonFantasy", dry_run=False)
copied = copy_shaders(shaders_dir, dry_run=False)
print(f"Pack 2: Copied {copied} shaders")  # 0 shaders (already exist)

# Result:
#   C:/Godot/Projects/SyntyAssets/
#     shaders/                    <- Shared
#     PolygonNature/              <- Pack 1
#       textures/, materials/, models/, meshes/
#     PolygonFantasy/             <- Pack 2
#       textures/, materials/, models/, meshes/
```

---

## Related Documentation

- [Architecture Overview](../architecture.md) - Pipeline design and data flow
- [User Guide - Output Structure](../user-guide.md#output-structure) - End-user view of output
- [API Reference - converter.py](../api/converter.md) - Full API documentation
- [Step 1: Validate Inputs](01-validate-inputs.md) - Previous step in pipeline
- [Step 3: Extract Unity Package](03-extract-package.md) - Next step in pipeline

---

## Notes for Doc Cleanup

After reviewing the existing documentation, here are observations about directory creation information:

### Redundant Information

1. **`docs/architecture.md` (lines 139-148)**: Contains a brief "Step 2: Create Output Directories" section with the same directory structure. This is appropriate as a summary but could link to this detailed doc.

2. **`docs/user-guide.md` (lines 161-207)**: Contains "Output Structure" section with directory descriptions. This is user-facing and appropriate, but:
   - Lists `shaders/` inside the pack folder structure, but shaders are actually at project root
   - Should clarify multi-pack structure

3. **`docs/api/converter.md` (lines 244-268)**: Documents `setup_output_directories()` function. The "Created Directories" section incorrectly shows `shaders/` as being created by this function - it's actually created by `copy_shaders()`.

### Outdated Information

1. **`docs/api/converter.md` (lines 261-268)**: Shows this structure:
   ```
   output_dir/
       shaders/
       textures/
       materials/
       models/
       meshes/
   ```
   This is incorrect - `shaders/` is at project root (`output_dir/shaders/`), not pack root (`output_dir/PackName/shaders/`).

2. **`docs/api/converter.md` (lines 277-286)**: The `copy_shaders()` function signature shows `source_dir` parameter, but the actual function takes `shaders_dest` as the only path parameter (source is derived from `__file__`).

### Information to Incorporate

1. The multi-pack sharing design (shaders at project root, pack assets in subfolders) is not documented anywhere except in code comments.

2. The `sanitize_filename()` call for pack names is not documented.

3. The fact that `copy_shaders()` creates its own directory (line 568) while `setup_output_directories()` does not create `shaders/` is confusing and should be clarified.

### Recommended Actions

1. Update `docs/api/converter.md`:
   - Fix `setup_output_directories()` to not list `shaders/`
   - Fix `copy_shaders()` function signature
   - Clarify project-root vs pack-root directory placement

2. Update `docs/user-guide.md`:
   - Clarify that `shaders/` is at project root, shared across packs
   - Add multi-pack example showing shared shaders

3. Add cross-references from `docs/architecture.md` Step 2 to this detailed document.
