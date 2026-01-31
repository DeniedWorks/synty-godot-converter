# Step 0: CLI & Orchestration

This document provides comprehensive documentation of the CLI interface and main orchestration logic in `converter.py`, which serves as the entry point and pipeline coordinator for the Synty Unity-to-Godot Converter.

## Table of Contents

- [Overview](#overview)
- [CLI Interface](#cli-interface)
  - [Argument Parser Setup](#argument-parser-setup)
  - [Required Arguments](#required-arguments)
  - [Optional Arguments](#optional-arguments)
  - [Argument Validation](#argument-validation)
- [Configuration Classes](#configuration-classes)
  - [ConversionConfig](#conversionconfig)
  - [ConversionStats](#conversionstats)
- [Main Entry Point](#main-entry-point)
  - [main() Function](#main-function)
  - [Exit Codes](#exit-codes)
- [Pipeline Orchestration](#pipeline-orchestration)
  - [run_conversion() Overview](#run_conversion-overview)
  - [12-Step Pipeline Details](#12-step-pipeline-details)
  - [Error Handling Strategy](#error-handling-strategy)
- [Helper Functions](#helper-functions)
  - [Path Resolution](#path-resolution)
  - [Output Directory Setup](#output-directory-setup)
  - [Project Generation](#project-generation)
  - [Logging and Summary](#logging-and-summary)
- [Constants and Templates](#constants-and-templates)
- [Code Examples](#code-examples)
- [Notes for Doc Cleanup](#notes-for-doc-cleanup)

---

## Overview

The `converter.py` module is the main CLI entry point and orchestrator for the Synty Shader Converter. It is responsible for:

1. **Parsing CLI arguments** - Accepting user input via argparse
2. **Validating inputs** - Ensuring all paths exist and are valid
3. **Orchestrating the pipeline** - Coordinating all conversion steps in sequence
4. **Error handling** - Capturing and reporting all warnings and errors
5. **Statistics collection** - Tracking metrics throughout the conversion
6. **Logging and output** - Providing user feedback and generating logs

The module follows a philosophy of **fail gracefully**: individual failures (missing textures, unparseable materials) are captured as warnings and do not halt the pipeline. Only critical failures (missing package, Godot executable not found) cause early termination.

---

## CLI Interface

### Argument Parser Setup

The CLI is built using Python's `argparse` module with a custom formatter and epilog examples:

```python
parser = argparse.ArgumentParser(
    description="Convert Synty Unity assets to Godot 4.6 format.",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="""
Examples:
    python converter.py \\
        --unity-package "C:/SyntyComplete/PolygonNature/Nature.unitypackage" \\
        --source-files "C:/SyntyComplete/PolygonNature/SourceFiles" \\
        --output "C:/Godot/Projects/converted_nature" \\
        --godot "C:/Godot/Godot_v4.6.exe"

    python converter.py \\
        --unity-package package.unitypackage \\
        --source-files ./SourceFiles \\
        --output ./output \\
        --godot godot.exe \\
        --dry-run --verbose
""",
)
```

### Required Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `--unity-package` | `Path` | Path to the Unity `.unitypackage` file. This file contains material definitions, shader GUIDs, texture references, and is the primary source for material data. |
| `--source-files` | `Path` | Path to the SourceFiles folder. Must contain FBX files (in FBX/ or Models/ subdirectory). Textures/ subdirectory is optional as textures are primarily extracted from the .unitypackage. |
| `--output` | `Path` | Output directory for the generated Godot project. Created if it does not exist. Assets are organized into PackName/ subfolder with shaders/ at the root. |
| `--godot` | `Path` | Path to the Godot 4.6 executable. Used for headless FBX import and mesh conversion. |

### Optional Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--dry-run` | `flag` | `False` | Preview what would be done without writing any files. All operations are logged but no filesystem changes occur. |
| `--verbose` | `flag` | `False` | Enable DEBUG-level logging. Shows shader detection decisions, property mappings, texture lookups, and Godot CLI output. |
| `--skip-fbx-copy` | `flag` | `False` | Skip copying FBX files to output/models/. Use when re-running conversion and models already exist. Saves time on large packs. |
| `--skip-godot-cli` | `flag` | `False` | Skip running Godot CLI entirely. Generates materials only, no .tscn scene files. Useful for debugging material issues. |
| `--skip-godot-import` | `flag` | `False` | Skip Godot's headless import step but still run the GDScript converter. Useful for large projects where import times out. You must open the project in Godot manually first to trigger import. |
| `--godot-timeout` | `int` | `600` | Timeout in seconds for each Godot CLI phase (import and convert). Each phase has this timeout applied separately. |
| `--keep-meshes-together` | `flag` | `False` | Keep all meshes from one FBX in a single scene file. Default behavior saves each mesh as a separate .tscn file. |
| `--mesh-format` | `choice` | `"tscn"` | Output format for mesh scenes. Options: `tscn` (text format, human-readable, diff-friendly) or `res` (binary compiled format, smaller, faster to load). |
| `--filter` | `str` | `None` | Filter pattern for FBX filenames (case-insensitive). Only FBX files containing this pattern are processed. Example: `--filter Tree` |

### Argument Validation

After parsing, the following validations occur in `parse_args()`:

1. **Unity package existence**: `args.unity_package.exists()` - Fatal error if missing
2. **Source files existence**: `args.source_files.exists()` - Fatal error if missing
3. **Source files resolution**: Calls `resolve_source_files_path()` to handle nested structures
4. **Textures directory check**: Informational only - textures primarily come from .unitypackage
5. **Godot executable existence**: `args.godot.exists()` - Fatal error if missing
6. **Path resolution**: All paths are converted to absolute paths via `.resolve()`

The `resolve_source_files_path()` function handles complex pack structures where source assets may be nested in subdirectories (like Dwarven Dungeon's `SourceFiles_v2/SourceFiles/` structure).

---

## Configuration Classes

### ConversionConfig

The `ConversionConfig` dataclass holds all configuration options for the conversion pipeline. It is populated from CLI arguments via `parse_args()`.

```python
@dataclass
class ConversionConfig:
    """Configuration dataclass for the conversion pipeline."""

    unity_package: Path      # Path to .unitypackage file (required)
    source_files: Path       # Path to SourceFiles directory (required)
    output_dir: Path         # Output directory for Godot assets (required)
    godot_exe: Path          # Path to Godot 4.6 executable (required)
    dry_run: bool = False    # Preview without writing files
    verbose: bool = False    # Enable DEBUG logging
    skip_fbx_copy: bool = False      # Skip FBX file copying
    skip_godot_cli: bool = False     # Skip Godot CLI entirely
    skip_godot_import: bool = False  # Skip import phase only
    godot_timeout: int = 600         # Timeout per phase in seconds
    keep_meshes_together: bool = False  # Single scene per FBX
    mesh_format: str = "tscn"        # Output format: "tscn" or "res"
    filter_pattern: str | None = None  # FBX filename filter
```

#### Field Details

| Field | Type | Description |
|-------|------|-------------|
| `unity_package` | `Path` | Absolute path to the .unitypackage file. Contains material definitions with shader GUIDs, texture references, and property values. |
| `source_files` | `Path` | Absolute path to SourceFiles directory. Contains FBX models and optionally high-quality textures as fallback. |
| `output_dir` | `Path` | Absolute path to output directory. The converter creates a PackName/ subfolder for pack-specific assets and shaders/ at the root for shared shaders. |
| `godot_exe` | `Path` | Absolute path to Godot 4.6 executable. Used for `--headless --import` and `--headless --script` operations. |
| `dry_run` | `bool` | When True, all operations are logged with "[DRY RUN]" prefix but no files are written. Useful for validation. |
| `verbose` | `bool` | When True, logging level is set to DEBUG. Shows detailed information about every operation. |
| `skip_fbx_copy` | `bool` | When True, Step 9 (FBX copying) is skipped. Use when models/ is already populated from a previous run. |
| `skip_godot_cli` | `bool` | When True, Step 12 (Godot CLI) is skipped entirely. Generates materials only without .tscn scenes. |
| `skip_godot_import` | `bool` | When True, only the import phase of Godot CLI is skipped. The GDScript converter still runs. Requires manual import in Godot first. |
| `godot_timeout` | `int` | Maximum seconds for each Godot CLI phase. Import and convert phases each get this timeout. Increase for very large packs. |
| `keep_meshes_together` | `bool` | When True, all meshes from one FBX file are saved together in a single scene. Default (False) saves each mesh as a separate scene. |
| `mesh_format` | `str` | Output format for scenes. "tscn" is human-readable text format. "res" is binary compiled format. |
| `filter_pattern` | `str | None` | When set, only FBX files whose names contain this pattern (case-insensitive) are processed. |

### ConversionStats

The `ConversionStats` dataclass tracks all metrics, warnings, and errors during conversion. It is populated by `run_conversion()` and used for the final summary and log file.

```python
@dataclass
class ConversionStats:
    """Statistics collected during the conversion pipeline."""

    # Material metrics
    materials_parsed: int = 0      # Unity .mat files parsed
    materials_generated: int = 0   # Godot .tres files generated
    materials_missing: int = 0     # Materials referenced but not found

    # Texture metrics
    textures_copied: int = 0       # Textures successfully copied
    textures_fallback: int = 0     # Textures using fallback atlas
    textures_missing: int = 0      # Textures not found

    # Asset metrics
    shaders_copied: int = 0        # Shader files copied
    fbx_copied: int = 0            # FBX files copied
    fbx_skipped: int = 0           # FBX files skipped (already exist)
    meshes_converted: int = 0      # .tscn scenes generated by Godot

    # Godot CLI status
    godot_import_success: bool = False    # Import phase completed
    godot_convert_success: bool = False   # Convert script completed
    godot_timeout_occurred: bool = False  # Either phase timed out

    # Issues
    warnings: list[str] = field(default_factory=list)  # Non-critical issues
    errors: list[str] = field(default_factory=list)    # Critical failures
```

#### Field Details

| Field | Type | When Incremented |
|-------|------|------------------|
| `materials_parsed` | `int` | Step 4: Each successful `parse_material_bytes()` call |
| `materials_generated` | `int` | Step 6: Each successful .tres file write |
| `materials_missing` | `int` | Step 10: Materials in MaterialList.txt not found in materials/ |
| `textures_copied` | `int` | Step 8: Each texture file successfully copied |
| `textures_fallback` | `int` | Step 8: Each missing texture substituted with fallback |
| `textures_missing` | `int` | Step 8: Each texture not found and no fallback available |
| `shaders_copied` | `int` | Step 7: Return value from `copy_shaders()` |
| `fbx_copied` | `int` | Step 9: Each FBX file copied |
| `fbx_skipped` | `int` | Step 9: Each FBX file skipped (same size at destination) |
| `meshes_converted` | `int` | Step 12: Count of files in meshes/ after Godot CLI |
| `godot_import_success` | `bool` | Step 12: Set True if import phase exit code is 0 |
| `godot_convert_success` | `bool` | Step 12: Set True if converter script exit code is 0 |
| `godot_timeout_occurred` | `bool` | Step 12: Set True if either phase exceeds timeout |
| `warnings` | `list[str]` | Various: Non-critical issues (missing textures, parse failures) |
| `errors` | `list[str]` | Various: Critical failures (package extraction, Godot failures) |

---

## Main Entry Point

### main() Function

The `main()` function is the CLI entry point, called when the script is run directly.

```python
def main() -> int:
    """CLI entry point.

    Returns:
        Exit code (0 for success, 1 for errors).
    """
    # Step 1: Parse arguments
    try:
        config = parse_args()
    except SystemExit:
        return 1

    # Step 2: Setup logging
    log_level = logging.DEBUG if config.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s: %(message)s",
    )

    # Step 3: Run conversion
    try:
        stats = run_conversion(config)
    except KeyboardInterrupt:
        print("\nConversion interrupted by user.")
        return 1
    except Exception as e:
        logger.exception("Unexpected error during conversion: %s", e)
        return 1

    # Step 4: Print summary
    print_summary(stats)

    # Step 5: Return exit code
    if stats.errors:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

#### Logic Flow

1. **Parse CLI arguments**: Calls `parse_args()` which validates inputs and returns `ConversionConfig`. If validation fails, `argparse` raises `SystemExit` which is caught and returns exit code 1.

2. **Configure logging**: Sets logging level based on `--verbose` flag. Uses simple format with level and message only.

3. **Run conversion**: Calls `run_conversion(config)` inside try/except block. Catches `KeyboardInterrupt` for clean Ctrl+C handling and generic `Exception` for unexpected errors.

4. **Print summary**: Calls `print_summary(stats)` to display final statistics to console.

5. **Determine exit code**: Returns 1 if any errors were captured in `stats.errors`, otherwise returns 0.

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success - conversion completed without critical errors |
| `1` | Failure - argument validation failed, conversion error, or user interrupt |

---

## Pipeline Orchestration

### run_conversion() Overview

The `run_conversion()` function is the main orchestrator that executes all pipeline steps in sequence.

```python
def run_conversion(config: ConversionConfig) -> ConversionStats:
    """Execute the full conversion pipeline.

    Args:
        config: ConversionConfig with all paths and options.

    Returns:
        ConversionStats with all metrics, warnings, and errors.

    Raises:
        No exceptions are raised to caller; all errors are captured in stats.
    """
```

#### Key Design Principles

1. **No exceptions escape**: All errors are captured in `stats.errors` and logged
2. **Graceful degradation**: Individual failures don't halt the pipeline
3. **Cleanup guaranteed**: Uses `try/finally` to ensure temp files are cleaned up
4. **Pack-aware structure**: Creates PackName/ subfolder with shaders/ at root

### 12-Step Pipeline Details

The pipeline executes these steps in order:

#### Step 1: Validate Inputs

```python
logger.info("Step 1: Validating inputs...")
logger.debug("  Pack Name: %s", pack_name)
logger.debug("  Unity Package: %s", config.unity_package)
logger.debug("  Source Files: %s", config.source_files)
logger.debug("  Pack Output: %s", pack_output_dir)
logger.debug("  Shaders Dir: %s", shaders_dir)
logger.debug("  Project Dir: %s", project_dir)
```

Extracts pack name from source_files parent directory (e.g., `C:\Synty\PolygonNature\SourceFiles` -> `PolygonNature`). Sanitizes the name for filesystem safety. Sets up output paths:
- `pack_output_dir = config.output_dir / pack_name`
- `shaders_dir = config.output_dir / "shaders"`
- `project_dir = config.output_dir`

#### Step 2: Create Output Directories

```python
logger.info("Step 2: Creating directories...")
setup_output_directories(pack_output_dir, config.dry_run)
```

Calls `setup_output_directories()` which creates:
- `pack_output_dir/` - Pack root
- `pack_output_dir/textures/` - Texture storage
- `pack_output_dir/materials/` - Generated .tres files
- `pack_output_dir/models/` - Copied FBX files
- `pack_output_dir/meshes/` - Godot-converted scenes

Note: `shaders/` is created by `copy_shaders()` at the project root, not here.

#### Step 3: Extract Unity Package

```python
logger.info("Step 3: Extracting Unity package...")
try:
    guid_map: GuidMap = extract_unitypackage(config.unity_package)
    logger.debug("Extracted %d assets from Unity package", len(guid_map.guid_to_pathname))
except Exception as e:
    error_msg = f"Failed to extract Unity package: {e}"
    logger.error(error_msg)
    stats.errors.append(error_msg)
    return stats  # Critical failure - cannot continue
```

Calls `extract_unitypackage()` from `unity_package.py`. Returns a `GuidMap` containing:
- `guid_to_pathname`: Maps GUIDs to Unity asset paths
- `guid_to_content`: Maps GUIDs to raw file bytes
- `texture_guid_to_path`: Maps texture GUIDs to extracted temp file paths
- `texture_guid_to_name`: Maps texture GUIDs to filenames

This is a **critical step** - failure causes immediate return.

#### Step 4: Parse Unity Materials

```python
material_guids = get_material_guids(guid_map)
logger.info("Step 4: Parsing %d materials...", len(material_guids))
unity_materials: list[tuple[str, UnityMaterial]] = []

for guid in material_guids:
    content = guid_map.guid_to_content.get(guid)
    if content is None:
        warning_msg = f"No content for material GUID: {guid}"
        stats.warnings.append(warning_msg)
        continue

    try:
        material = parse_material_bytes(content)
        unity_materials.append((guid, material))
        stats.materials_parsed += 1
    except Exception as e:
        warning_msg = f"Failed to parse material GUID {guid}: {e}"
        stats.warnings.append(warning_msg)
```

Iterates through all material GUIDs, parsing each with `parse_material_bytes()` from `unity_parser.py`. Failures are captured as warnings, not errors.

#### Step 4.5: Parse MaterialList.txt

```python
material_list_files = list(config.source_files.rglob("MaterialList*.txt"))
prefabs: list[PrefabMaterials] = []

if material_list_files:
    for material_list_path in material_list_files:
        try:
            file_prefabs = parse_material_list(material_list_path)
            prefabs.extend(file_prefabs)
        except Exception as e:
            logger.debug("Failed to parse %s: %s", material_list_path.name, e)
```

Recursively searches for `MaterialList*.txt` files and parses them to extract mesh-to-material mappings. This data is used for:
- Shader cache building (Step 4.6)
- Mesh-material mapping JSON (Step 10)

#### Step 4.6: Build Shader Cache

```python
logger.info("Step 5: Mapping shader properties...")
shader_cache, unmatched_materials = build_shader_cache(prefabs)
logger.debug("Shader cache: %d materials cached", len(shader_cache))
```

Calls `build_shader_cache()` which uses `determine_shader()` from `shader_mapping.py` to make shader decisions for each material. Implements LOD inheritance: LOD0's shader decision applies to all LODs of the same prefab.

#### Step 5: Map Material Properties

```python
logger.debug("Mapping materials to Godot format...")
mapped_materials: list[MappedMaterial] = []
required_textures: set[str] = set()

for guid, unity_mat in unity_materials:
    try:
        cached_shader = shader_cache.get(unity_mat.name)
        mapped = map_material(unity_mat, guid_map.texture_guid_to_name, override_shader=cached_shader)
        mapped_materials.append(mapped)

        for texture_name in mapped.textures.values():
            required_textures.add(texture_name)
    except Exception as e:
        warning_msg = f"Failed to map material '{unity_mat.name}': {e}"
        stats.warnings.append(warning_msg)
```

Calls `map_material()` from `shader_mapping.py` for each Unity material. Uses the shader cache to override shader selection. Collects all required texture names.

#### Step 6: Generate .tres Files

```python
logger.info("Step 6: Generating .tres files...")
materials_dir = pack_output_dir / "materials"
texture_base = f"res://{pack_name}/textures"

for mapped_mat in mapped_materials:
    try:
        tres_content = generate_tres(
            mapped_mat,
            shader_base="res://shaders",
            texture_base=texture_base
        )
        filename = sanitize_filename(mapped_mat.name) + ".tres"
        output_path = materials_dir / filename

        if config.dry_run:
            logger.debug("[DRY RUN] Would write material: %s", output_path)
        else:
            write_tres_file(tres_content, output_path)

        stats.materials_generated += 1
    except Exception as e:
        warning_msg = f"Failed to generate .tres for '{mapped_mat.name}': {e}"
        stats.warnings.append(warning_msg)
```

Calls `generate_tres()` and `write_tres_file()` from `tres_generator.py`. Texture paths are relative to pack folder (`res://PackName/textures/`). Shader paths are at project root (`res://shaders/`).

#### Step 7: Copy Shaders

```python
logger.info("Step 7: Copying shaders...")
stats.shaders_copied = copy_shaders(shaders_dir, config.dry_run)
```

Copies all shader files from the converter's `shaders/` directory to the output's `shaders/` directory. Skips shaders that already exist (for multi-pack conversions).

#### Step 8: Copy Textures

```python
logger.info("Step 8: Copying %d textures...", len(required_textures))

# Build texture lookups
texture_name_to_guid = {name: guid for guid, name in guid_map.texture_guid_to_name.items()}

stats.textures_copied, stats.textures_fallback, stats.textures_missing = copy_textures(
    source_textures,
    output_textures,
    required_textures,
    config.dry_run,
    fallback_texture=None,
    texture_guid_to_path=guid_map.texture_guid_to_path,
    texture_name_to_guid=texture_name_to_guid,
    additional_texture_dirs=additional_texture_dirs,
)
```

Copies only textures that are actually referenced by materials. Prefers textures from .unitypackage extraction over SourceFiles. Generates `.import` sidecar files for VRAM compression.

#### Step 9: Copy FBX Files

```python
if not config.skip_fbx_copy:
    logger.info("Step 9: Copying %d FBX files...", fbx_count)
    stats.fbx_copied, stats.fbx_skipped = copy_fbx_files(
        source_fbx,
        output_models,
        config.dry_run,
        config.filter_pattern,
        additional_fbx_dirs=additional_fbx_dirs,
    )
else:
    logger.info("Step 9: Skipping FBX copy...")
```

Copies FBX files from SourceFiles to output, preserving directory structure. Skips files that already exist with matching file size. Applies filter pattern if specified.

#### Step 10: Generate Mesh Material Mapping

```python
logger.info("Step 10: Generating mesh material mapping...")
if prefabs:
    mapping_output = shaders_dir / "mesh_material_mapping.json"
    if not config.dry_run:
        generate_mesh_material_mapping_json(prefabs, mapping_output)

    # Check for missing materials (warn only, no placeholders)
    existing_materials = {f.stem for f in materials_dir.glob("*.tres")}
    referenced_materials = set()
    for prefab in prefabs:
        for mesh in prefab.meshes:
            for slot in mesh.slots:
                if slot.material_name:
                    referenced_materials.add(slot.material_name)

    missing_materials = referenced_materials - existing_materials
    stats.materials_missing = len(missing_materials)
```

Generates `mesh_material_mapping.json` for the Godot converter script. Also checks for materials referenced by meshes but not generated.

#### Step 11: Generate project.godot

```python
logger.info("Step 11: Generating project.godot...")
generate_project_godot(project_dir, pack_name, config.dry_run)
```

Calls `generate_project_godot()` which either:
- Creates a new project.godot with global shader uniforms
- Merges missing shader uniforms into existing project.godot

#### Step 12: Run Godot CLI

```python
if not config.skip_godot_cli:
    logger.info("Step 12: Running Godot CLI...")

    (
        stats.godot_import_success,
        stats.godot_convert_success,
        stats.godot_timeout_occurred,
    ) = run_godot_cli(
        config.godot_exe,
        project_dir,
        config.godot_timeout,
        config.dry_run,
        skip_import=config.skip_godot_import,
        keep_meshes_together=config.keep_meshes_together,
        mesh_format=config.mesh_format,
        filter_pattern=config.filter_pattern,
    )

    # Count generated meshes
    meshes_dir = pack_output_dir / "meshes"
    stats.meshes_converted = count_mesh_files(meshes_dir, config.mesh_format)
else:
    logger.info("Step 12: Skipping Godot CLI...")
```

Runs Godot in two phases:
1. **Import**: `godot --headless --import --path <project>`
2. **Convert**: `godot --headless --script res://godot_converter.gd --path <project>`

### Error Handling Strategy

The converter uses a **multi-layer error handling** approach:

1. **Critical Errors** (cause immediate return):
   - Unity package extraction failure
   - Required path validation failures

2. **Non-Critical Errors** (captured as warnings, continue):
   - Individual material parse failures
   - Missing textures
   - Material mapping failures
   - .tres generation failures

3. **Godot CLI Errors** (captured as errors, continue):
   - Import phase failures
   - Converter script failures
   - Timeout occurrences

4. **Cleanup** (always runs via finally):
   - Temp texture files are always cleaned up

```python
try:
    # ... pipeline steps ...
    return stats
finally:
    # Cleanup temp texture files (always runs, even on error)
    if temp_dir_to_cleanup and temp_dir_to_cleanup.exists():
        shutil.rmtree(temp_dir_to_cleanup, ignore_errors=True)
```

---

## Helper Functions

### Path Resolution

#### has_source_assets_recursive()

```python
def has_source_assets_recursive(path: Path) -> bool:
    """Check if a path contains any MaterialList, FBX, or Models anywhere in tree."""
```

Validates that a directory contains usable assets by searching recursively for:
- `MaterialList*.txt` files
- `FBX/` directories
- `Models/` directories

Note: Textures directories are NOT required for validation since textures come from .unitypackage.

#### resolve_source_files_path()

```python
def resolve_source_files_path(source_files: Path) -> Path:
    """Validate and return the source files path."""
```

Handles complex nested structures where source assets may be in subdirectories. Returns the path as-is since file discovery is recursive.

### Output Directory Setup

#### setup_output_directories()

```python
def setup_output_directories(output_dir: Path, dry_run: bool) -> None:
    """Create the output directory structure for pack assets."""
```

Creates the standard directory structure:
```
output_dir/
    textures/
    materials/
    models/
    meshes/
```

Note: `shaders/` is created by `copy_shaders()` at project root level.

### Project Generation

#### generate_project_godot()

```python
def generate_project_godot(output_dir: Path, pack_name: str, dry_run: bool) -> None:
    """Write or update project.godot with global shader uniforms."""
```

If project.godot exists:
- Extracts existing [shader_globals] section
- Parses uniforms from both existing and template
- Merges missing uniforms from template
- Preserves all other project settings

If project.godot doesn't exist:
- Creates new file with pack name and all shader uniforms

#### Helper functions for project.godot:

- `_extract_shader_globals_section(content)` - Extracts [shader_globals] section
- `_parse_shader_globals(section)` - Parses uniforms into dict
- `_merge_shader_globals(existing, template)` - Merges missing uniforms

### Logging and Summary

#### write_conversion_log()

```python
def write_conversion_log(output_dir: Path, stats: ConversionStats, config: ConversionConfig) -> None:
    """Write a summary log file with all warnings and errors."""
```

Writes `conversion_log.txt` with:
- Timestamp
- Input/output paths
- All statistics
- Godot CLI status
- All warnings and errors

#### print_summary()

```python
def print_summary(stats: ConversionStats) -> None:
    """Print conversion summary to console."""
```

Displays:
- Materials generated
- Textures copied
- Meshes converted
- Missing materials/textures (if any)
- Godot CLI status (if failed)
- Warning count
- First 5 errors (if any)

---

## Constants and Templates

### SHADER_FILES

List of shader files to copy:
```python
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

### TEXTURE_EXTENSIONS

Supported texture file extensions (case-sensitive search):
```python
TEXTURE_EXTENSIONS = [".png", ".tga", ".jpg", ".jpeg", ".PNG", ".TGA", ".JPG", ".JPEG"]
```

### FALLBACK_TEXTURE_PATTERNS

Patterns for finding the pack's main texture atlas:
```python
FALLBACK_TEXTURE_PATTERNS = [
    "Polygon*_Texture_01.png",
    "Polygon*_Texture_01_A.png",
    "POLYGON*_Texture_01.png",
    "*_Texture_01_A.png",
    "Texture_01.png",
]
```

### TEXTURE_IMPORT_TEMPLATE

Template for Godot .import sidecar files:
- Configures VRAM compression (mode=2)
- Enables high quality compression
- Enables mipmap generation
- Enables fix_alpha_border

### PROJECT_GODOT_TEMPLATE

Template for project.godot with shader uniforms:
- WindDirection, WindIntensity, GaleStrength (foliage wind)
- MainLightDirection (lighting)
- SkyColor, EquatorColor, GroundColor (sky gradient)
- OceanWavesGradient (water waves)

---

## Code Examples

### Basic CLI Usage

```bash
python converter.py \
    --unity-package "C:/SyntyComplete/PolygonNature/Nature.unitypackage" \
    --source-files "C:/SyntyComplete/PolygonNature/SourceFiles" \
    --output "C:/Godot/Projects/converted" \
    --godot "C:/Godot/Godot_v4.6.exe"
```

### Dry Run with Verbose Output

```bash
python converter.py \
    --unity-package "package.unitypackage" \
    --source-files "SourceFiles" \
    --output "output" \
    --godot "godot.exe" \
    --dry-run \
    --verbose
```

### Converting Specific Assets

```bash
# Only tree-related assets
python converter.py ... --filter Tree

# Only character assets
python converter.py ... --filter Chr

# Skip FBX copy (already done)
python converter.py ... --skip-fbx-copy

# Materials only (no scenes)
python converter.py ... --skip-godot-cli
```

### Programmatic Usage

```python
from pathlib import Path
from converter import ConversionConfig, run_conversion

config = ConversionConfig(
    unity_package=Path("package.unitypackage"),
    source_files=Path("SourceFiles"),
    output_dir=Path("output"),
    godot_exe=Path("godot.exe"),
    verbose=True,
)

stats = run_conversion(config)

if stats.errors:
    print(f"Conversion failed with {len(stats.errors)} errors")
    for error in stats.errors:
        print(f"  - {error}")
else:
    print(f"Success! Generated {stats.materials_generated} materials")
```

---

## Notes for Doc Cleanup

After reviewing the existing documentation, the following observations were made:

### Redundant Information

1. **docs/api/converter.md** - Contains a complete API reference for converter.py. Much of this overlaps with what is documented here. Consider:
   - Keeping api/converter.md as a concise API reference only
   - Referring to this step doc for detailed explanations
   - Removing the narrative descriptions from api/converter.md

2. **docs/user-guide.md** - Command-Line Options section duplicates CLI argument documentation. Consider:
   - Keeping user-guide.md focused on user workflows
   - Linking to this doc for complete argument details
   - The user-guide version is more user-friendly, this doc is more technical

3. **docs/architecture.md** - Data Flow section duplicates pipeline steps. Consider:
   - Keeping architecture.md as high-level overview
   - Linking to this doc for implementation details
   - The architecture doc is good for understanding "why", this doc is for "how"

### Outdated Information

1. **docs/api/converter.md** - Pipeline steps are listed in wrong order:
   - Lists Step 9 as "Copy FBX files" then Step 10 as "Parse MaterialList*.txt"
   - Actual order: MaterialList is parsed in Step 4.5, FBX copy is Step 9, mapping is Step 10
   - Missing Step 4.5 and Step 4.6 (shader cache building)

2. **docs/api/converter.md** - ConversionConfig is missing newer fields:
   - Missing: `skip_godot_import`, `keep_meshes_together`, `mesh_format`, `filter_pattern`
   - `godot_timeout` default listed as 600 (correct)

3. **docs/api/converter.md** - ConversionStats is missing:
   - Missing: `textures_fallback` field
   - All other fields are accurate

4. **docs/api/converter.md** - copy_shaders() signature is wrong:
   - Shows: `copy_shaders(source_dir: Path, output_dir: Path, dry_run: bool)`
   - Actual: `copy_shaders(shaders_dest: Path, dry_run: bool)` - source is determined internally

5. **docs/architecture.md** - Step 10 says "Parse MaterialList.txt" but parsing now happens in Step 4.5:
   - MaterialList parsing was moved earlier to enable shader cache building
   - Step 10 now generates mesh_material_mapping.json from cached prefabs

6. **docs/user-guide.md** - "Textures directory not found" error:
   - This is now informational only, not an error
   - Textures primarily come from .unitypackage, SourceFiles/Textures is optional fallback

### Information to Incorporate

The following could be added to other docs:

1. **LOD inheritance** - The shader cache system uses LOD inheritance where LOD0's shader decision applies to all LODs. This is not documented in architecture.md.

2. **Texture extraction priority** - Textures are first extracted from .unitypackage temp files, then fall back to SourceFiles/Textures. This prioritization is not clearly documented.

3. **project.godot merging** - The converter now intelligently merges shader uniforms into existing project.godot files instead of overwriting. This supports multi-pack conversions to the same project.

4. **Nested structure support** - The converter handles complex nested pack structures (like Dwarven Dungeon) by searching recursively. The `has_source_assets_recursive()` and `resolve_source_files_path()` functions enable this.
