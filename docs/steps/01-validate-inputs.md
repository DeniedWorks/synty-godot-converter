# Step 1: Validate Inputs

The input validation step is the gateway to the conversion pipeline. It ensures all required paths exist and are valid before any processing begins. This step is implemented primarily in `parse_args()` with support from `has_source_assets_recursive()` and `resolve_source_files_path()`.

## Table of Contents

- [Overview](#overview)
- [Validation Flow](#validation-flow)
- [Required Inputs](#required-inputs)
- [Validation Functions](#validation-functions)
  - [parse_args()](#parse_args)
  - [has_source_assets_recursive()](#has_source_assets_recursive)
  - [resolve_source_files_path()](#resolve_source_files_path)
- [CLI Arguments](#cli-arguments)
- [Error Messages](#error-messages)
- [ConversionConfig Dataclass](#conversionconfig-dataclass)
- [Validation Order](#validation-order)
- [Logic Flow Diagram](#logic-flow-diagram)
- [Code Examples](#code-examples)
- [Notes for Doc Cleanup](#notes-for-doc-cleanup)

---

## Overview

Input validation serves two purposes:

1. **Fail fast**: Catch missing files/directories immediately rather than mid-pipeline
2. **Clear errors**: Provide actionable error messages so users can fix problems quickly

The validation is performed in `parse_args()` which is called by `main()` before any conversion work begins. If validation fails, the program exits with code 1 via `parser.error()` which raises `SystemExit`.

**Key principle**: The validation is lenient about the Textures directory because textures are now primarily extracted from the `.unitypackage` file. The SourceFiles/Textures folder is an optional fallback only.

---

## Validation Flow

```
main()
  |
  v
parse_args()
  |
  +---> Parse CLI arguments (argparse)
  |
  +---> Validate unity_package exists
  |       |
  |       +---> If missing: parser.error() -> SystemExit
  |
  +---> Validate source_files exists
  |       |
  |       +---> If missing: parser.error() -> SystemExit
  |
  +---> resolve_source_files_path()
  |       |
  |       +---> has_source_assets_recursive()
  |       |       |
  |       |       +---> Check for MaterialList*.txt files
  |       |       +---> Check for FBX/ directories
  |       |       +---> Check for Models/ directories
  |       |
  |       +---> Returns source_files path (as-is)
  |
  +---> Log debug if Textures/ not found (informational only)
  |
  +---> Validate godot executable exists
  |       |
  |       +---> If missing: parser.error() -> SystemExit
  |
  +---> Create ConversionConfig with resolved paths
  |
  v
Return ConversionConfig
```

---

## Required Inputs

| Input | Flag | Purpose | Validated? |
|-------|------|---------|------------|
| Unity Package | `--unity-package` | Source of materials, textures, shader GUIDs | Must exist |
| Source Files | `--source-files` | Source of FBX models, MaterialList.txt | Must exist |
| Output Directory | `--output` | Destination for converted assets | Created if missing |
| Godot Executable | `--godot` | For FBX import and mesh conversion | Must exist |

### What IS validated:

- Unity package file exists (line 476-477)
- Source files directory exists (line 479-480)
- Godot executable exists (line 500-501)

### What is NOT validated:

- Output directory existence (created in Step 2)
- Textures directory existence (optional fallback)
- FBX directory existence (warning only, not fatal)
- Unity package format validity (deferred to Step 3)
- Godot version compatibility (not checked)

---

## Validation Functions

### parse_args()

**Location**: `converter.py`, lines 367-517

**Purpose**: Parse command-line arguments and validate that required input paths exist.

**Signature**:
```python
def parse_args() -> ConversionConfig:
    """Parse command-line arguments and validate inputs.

    Returns:
        ConversionConfig with validated paths.

    Raises:
        SystemExit: If required arguments are missing or invalid.
    """
```

**Implementation Details**:

1. **Argument Parser Setup** (lines 376-471):
   - Creates `argparse.ArgumentParser` with description and examples
   - Defines all CLI arguments with types, help text, and defaults
   - Uses `RawDescriptionHelpFormatter` to preserve epilog formatting

2. **Parse Arguments** (line 473):
   ```python
   args = parser.parse_args()
   ```

3. **Validate Unity Package** (lines 476-477):
   ```python
   if not args.unity_package.exists():
       parser.error(f"Unity package not found: {args.unity_package}")
   ```
   - Checks if the file exists using `Path.exists()`
   - Calls `parser.error()` which prints message and raises `SystemExit`

4. **Validate Source Files Directory** (lines 479-480):
   ```python
   if not args.source_files.exists():
       parser.error(f"Source files directory not found: {args.source_files}")
   ```

5. **Resolve Source Files Path** (lines 482-498):
   ```python
   resolved_source_files = resolve_source_files_path(args.source_files)
   ```
   - Handles nested SourceFiles folder structures
   - Logs debug message if no Textures directory found (informational only)

6. **Validate Godot Executable** (lines 500-501):
   ```python
   if not args.godot.exists():
       parser.error(f"Godot executable not found: {args.godot}")
   ```

7. **Create Config** (lines 503-517):
   ```python
   return ConversionConfig(
       unity_package=args.unity_package.resolve(),
       source_files=resolved_source_files.resolve(),
       output_dir=args.output.resolve(),
       godot_exe=args.godot.resolve(),
       dry_run=args.dry_run,
       verbose=args.verbose,
       skip_fbx_copy=args.skip_fbx_copy,
       skip_godot_cli=args.skip_godot_cli,
       skip_godot_import=args.skip_godot_import,
       godot_timeout=args.godot_timeout,
       keep_meshes_together=args.keep_meshes_together,
       mesh_format=args.mesh_format,
       filter_pattern=args.filter,
   )
   ```
   - All paths are resolved to absolute paths via `.resolve()`
   - This ensures consistent path handling throughout the pipeline

---

### has_source_assets_recursive()

**Location**: `converter.py`, lines 66-100

**Purpose**: Check if a directory tree contains usable Synty assets (MaterialList, FBX, or Models directories).

**Signature**:
```python
def has_source_assets_recursive(path: Path) -> bool:
    """Check if a path contains any MaterialList, FBX, or Models anywhere in tree.

    This is used to validate that the source_files path contains usable assets,
    even if they are nested in subdirectories (like Dwarven Dungeon structure).

    Note: Textures are primarily extracted from .unitypackage files, so Textures
    directories are not required for validation. SourceFiles/Textures is used
    as an optional fallback only.

    Args:
        path: Directory to search recursively.

    Returns:
        True if any MaterialList*.txt, FBX directory, or Models directory
        exists anywhere in the tree.
    """
```

**Implementation Details**:

```python
def has_source_assets_recursive(path: Path) -> bool:
    # Check for MaterialList files
    if list(path.rglob("MaterialList*.txt")):
        return True

    # Check for FBX directories
    for item in path.rglob("FBX"):
        if item.is_dir():
            return True

    # Check for Models directories (some packs use this instead of FBX)
    for item in path.rglob("Models"):
        if item.is_dir():
            return True

    # Note: Textures directories are NOT required - textures come from .unitypackage
    # SourceFiles/Textures is optional fallback only

    return False
```

**Search Order**:

1. **MaterialList*.txt files** (line 84):
   - Uses `rglob()` for recursive glob search
   - Pattern `MaterialList*.txt` matches:
     - `MaterialList.txt`
     - `MaterialList_Characters.txt`
     - `MaterialList_v2.txt`
   - Returns `True` immediately if any match found

2. **FBX directories** (lines 88-90):
   - Searches for any directory named exactly "FBX"
   - Uses `is_dir()` to filter out files
   - Most Synty packs use this structure

3. **Models directories** (lines 93-95):
   - Searches for any directory named exactly "Models"
   - Some packs use "Models" instead of "FBX"
   - This fallback ensures broader compatibility

**Why Textures is NOT checked**:

Lines 97-98 explicitly document this design decision:
```python
# Note: Textures directories are NOT required - textures come from .unitypackage
# SourceFiles/Textures is optional fallback only
```

Textures are now primarily extracted directly from the `.unitypackage` file, making the SourceFiles/Textures directory optional.

---

### resolve_source_files_path()

**Location**: `converter.py`, lines 103-125

**Purpose**: Validate and return the source files path. Handles complex nested structures found in some Synty packs.

**Signature**:
```python
def resolve_source_files_path(source_files: Path) -> Path:
    """Validate and return the source files path.

    Since all file discovery is now recursive, users can point to any folder
    containing Synty assets and the converter will find MaterialList*.txt,
    FBX/, and Textures/ folders anywhere in the tree.

    Args:
        source_files: Path provided by the user as --source-files argument.

    Returns:
        The source files path as-is. If the path does not exist or has no
        assets, it will fail validation later with a clear error message.
    """
```

**Implementation Details**:

```python
def resolve_source_files_path(source_files: Path) -> Path:
    if not source_files.exists():
        return source_files  # Will fail validation with clear error

    if has_source_assets_recursive(source_files):
        return source_files

    # Log debug if no assets found (will be reported later if it's a real problem)
    logger.debug("No MaterialList, FBX, or Models found in: %s", source_files)
    return source_files
```

**Behavior**:

1. If path doesn't exist: Returns it unchanged (validation fails later with clear error)
2. If path has assets: Returns it unchanged (valid)
3. If path has no assets: Logs debug message and returns unchanged

**Key design point**: This function does NOT raise errors. It defers error handling to `parse_args()` so that all validation errors come from the same place with consistent formatting.

---

## CLI Arguments

### Required Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `--unity-package` | `Path` | Path to Unity `.unitypackage` file |
| `--source-files` | `Path` | Path to SourceFiles folder containing FBX/ |
| `--output` | `Path` | Output directory for Godot project |
| `--godot` | `Path` | Path to Godot 4.6 executable |

### Optional Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--dry-run` | flag | `False` | Preview without writing files |
| `--verbose` | flag | `False` | Enable verbose logging |
| `--skip-fbx-copy` | flag | `False` | Skip copying FBX files |
| `--skip-godot-cli` | flag | `False` | Skip running Godot CLI (materials only) |
| `--skip-godot-import` | flag | `False` | Skip Godot's headless import step |
| `--godot-timeout` | `int` | `600` | Timeout for Godot CLI (seconds) |
| `--keep-meshes-together` | flag | `False` | Keep all meshes from one FBX together |
| `--mesh-format` | `str` | `"tscn"` | Output format: `tscn` or `res` |
| `--filter` | `str` | `None` | Filter pattern for FBX filenames |

---

## Error Messages

When validation fails, `parser.error()` prints a message to stderr and exits:

### Unity Package Not Found

```
usage: converter.py [-h] --unity-package UNITY_PACKAGE ...
converter.py: error: Unity package not found: C:\Invalid\Path\package.unitypackage
```

**Cause**: The file specified by `--unity-package` does not exist.

**Fix**: Verify the path is correct. Use absolute paths to avoid working directory issues.

### Source Files Directory Not Found

```
usage: converter.py [-h] --unity-package UNITY_PACKAGE ...
converter.py: error: Source files directory not found: C:\Invalid\Path\SourceFiles
```

**Cause**: The directory specified by `--source-files` does not exist.

**Fix**: Verify the path points to the SourceFiles folder, not the parent pack folder.

### Godot Executable Not Found

```
usage: converter.py [-h] --unity-package UNITY_PACKAGE ...
converter.py: error: Godot executable not found: C:\Invalid\Path\godot.exe
```

**Cause**: The file specified by `--godot` does not exist.

**Fix**: Verify the Godot path. On Windows, include the full `.exe` extension.

---

## ConversionConfig Dataclass

**Location**: `converter.py`, lines 236-297

The `ConversionConfig` dataclass holds all validated configuration for the pipeline:

```python
@dataclass
class ConversionConfig:
    """Configuration dataclass for the conversion pipeline."""

    unity_package: Path       # Must exist (validated)
    source_files: Path        # Must exist (validated)
    output_dir: Path          # Will be created
    godot_exe: Path           # Must exist (validated)
    dry_run: bool = False
    verbose: bool = False
    skip_fbx_copy: bool = False
    skip_godot_cli: bool = False
    skip_godot_import: bool = False
    godot_timeout: int = 600
    keep_meshes_together: bool = False
    mesh_format: str = "tscn"
    filter_pattern: str | None = None
```

All Path attributes are **resolved to absolute paths** via `.resolve()` during `parse_args()`, ensuring consistent path handling throughout the pipeline.

---

## Validation Order

The validation checks occur in this exact order:

1. **Parse all CLI arguments** (argparse)
2. **Check unity_package exists** (line 476)
3. **Check source_files exists** (line 479)
4. **Resolve source_files path** (line 483)
   - Check for MaterialList*.txt
   - Check for FBX/ directory
   - Check for Models/ directory
   - Log debug if no assets found
5. **Check for Textures directory** (informational, lines 487-498)
   - If not found in root, search recursively
   - Log debug message (not an error)
6. **Check godot executable exists** (line 500)
7. **Create ConversionConfig** (lines 503-517)

The order matters because:
- Unity package is needed for material/texture extraction
- Source files must exist before we check for subdirectories
- Godot is validated last since it's only needed for Step 12

---

## Logic Flow Diagram

```
                              main()
                                |
                                v
                           parse_args()
                                |
                    +-----------+-----------+
                    |           |           |
                    v           v           v
              unity_package  source_files  godot
                exists?       exists?     exists?
                    |           |           |
              +-----+-----+ +---+---+ +-----+-----+
              |           | |       | |           |
              v           v v       v v           v
            Yes          No Yes    No Yes        No
              |           |   |     |   |         |
              |    parser.error() parser.error() parser.error()
              |      exit(1)     exit(1)         exit(1)
              |
              v
     resolve_source_files_path()
              |
              v
     has_source_assets_recursive()
              |
              +---> MaterialList*.txt? --Yes--> return True
              |                  |
              |                  No
              |                  |
              +---> FBX/ dir? --------Yes--> return True
              |                  |
              |                  No
              |                  |
              +---> Models/ dir? -----Yes--> return True
              |                  |
              |                  No
              |                  |
              +---> return False (log debug)
              |
              v
     Check Textures/ (informational only)
              |
              v
     Create ConversionConfig
              |
              v
     Return to main()
```

---

## Code Examples

### Successful Validation

```python
# Command line:
# python converter.py \
#     --unity-package "C:\SyntyComplete\PolygonNature\Nature.unitypackage" \
#     --source-files "C:\SyntyComplete\PolygonNature\SourceFiles" \
#     --output "C:\Godot\Projects\converted" \
#     --godot "C:\Godot\Godot_v4.6.exe"

# parse_args() returns:
ConversionConfig(
    unity_package=Path("C:/SyntyComplete/PolygonNature/Nature.unitypackage"),
    source_files=Path("C:/SyntyComplete/PolygonNature/SourceFiles"),
    output_dir=Path("C:/Godot/Projects/converted"),
    godot_exe=Path("C:/Godot/Godot_v4.6.exe"),
    dry_run=False,
    verbose=False,
    skip_fbx_copy=False,
    skip_godot_cli=False,
    skip_godot_import=False,
    godot_timeout=600,
    keep_meshes_together=False,
    mesh_format="tscn",
    filter_pattern=None,
)
```

### Programmatic Usage

```python
from converter import ConversionConfig, run_conversion
from pathlib import Path

# ConversionConfig doesn't validate - you must ensure paths exist
config = ConversionConfig(
    unity_package=Path("C:/SyntyComplete/PolygonNature/Nature.unitypackage"),
    source_files=Path("C:/SyntyComplete/PolygonNature/SourceFiles"),
    output_dir=Path("C:/Godot/Projects/converted"),
    godot_exe=Path("C:/Godot/Godot_v4.6.exe"),
)

# Manual validation if not using parse_args()
if not config.unity_package.exists():
    raise FileNotFoundError(f"Unity package not found: {config.unity_package}")
if not config.source_files.exists():
    raise FileNotFoundError(f"Source files not found: {config.source_files}")
if not config.godot_exe.exists():
    raise FileNotFoundError(f"Godot not found: {config.godot_exe}")

# Run conversion
stats = run_conversion(config)
```

### Testing has_source_assets_recursive()

```python
from pathlib import Path
from converter import has_source_assets_recursive

# Test various directory structures
test_paths = [
    Path("C:/SyntyComplete/PolygonNature/SourceFiles"),
    Path("C:/SyntyComplete/DwarvenDungeon_SourceFiles_v2"),
    Path("C:/Empty/Directory"),
]

for p in test_paths:
    if p.exists():
        has_assets = has_source_assets_recursive(p)
        print(f"{p.name}: {'Has assets' if has_assets else 'No assets'}")
```

---

## Notes for Doc Cleanup

After reviewing the existing documentation, here are redundancies and issues found:

### Redundant Information

1. **docs/api/converter.md**:
   - Lines 212-241: `parse_args()` section duplicates the CLI arguments table
   - Lines 63-75: ConversionConfig attributes table is less complete than this doc
   - The `setup_output_directories` section says shaders/ is created here, but it's actually created by `copy_shaders()` (line 268 says "Creates: ... shaders/" but comment on line 530 says "Note: shaders/ is created at project root by copy_shaders()")

2. **docs/architecture.md**:
   - Lines 127-137: Step 1 section is very brief (7 lines) and mentions "SourceFiles/Textures subdirectory" as required - this is outdated since textures now come from .unitypackage primarily
   - The input sources table (line 33) says Textures come from "SourceFiles/ folder" which is now only a fallback

3. **docs/user-guide.md**:
   - Lines 141-144: Required arguments table says source-files "must contain Textures/" - outdated
   - Lines 68-84: "SourceFiles Folder" section says "Textures/ # High-resolution textures" implying required - misleading
   - Lines 477-487: Troubleshooting "Unity package not found" - accurate but brief

4. **docs/troubleshooting.md**:
   - Lines 89-123: "Textures directory missing" section describes this as a "Fatal error" - this is OUTDATED. The current code only logs a debug message if Textures is missing, not an error

### Outdated Information

1. **docs/troubleshooting.md lines 89-123**:
   ```
   ### "Textures directory missing"
   **Symptom**: Fatal error about SourceFiles/Textures not existing.
   ```
   This is **no longer true**. The current code (lines 487-498 in converter.py) only logs a debug message about Textures being optional.

2. **docs/architecture.md line 133**:
   ```
   - SourceFiles/Textures subdirectory
   ```
   Should be updated to note this is optional.

3. **docs/api/converter.md line 68**:
   ```
   | `source_files` | `Path` | required | Path to `SourceFiles` folder containing `Textures/` and `FBX/` |
   ```
   Should say "containing `FBX/`" only, or note Textures is optional.

### Information to Incorporate

1. **docs/HANDOFF.md** contains important context about WHY textures validation was relaxed:
   - "Textures are primarily extracted from .unitypackage files"
   - "SourceFiles/Textures is used as an optional fallback only"
   This should be reflected in user-facing docs.

2. The `has_source_assets_recursive()` function is not documented in any existing doc. It should be added to api/converter.md.

3. The `resolve_source_files_path()` function is not documented. It should be added to api/converter.md.

### Recommended Updates

1. **docs/troubleshooting.md**: Remove or update the "Textures directory missing" section to reflect current behavior
2. **docs/architecture.md**: Update Step 1 to remove Textures requirement
3. **docs/user-guide.md**: Update source-files description to note Textures is optional
4. **docs/api/converter.md**: Add `has_source_assets_recursive()` and `resolve_source_files_path()` function documentation

---

## Related Documentation

- [Architecture](../architecture.md) - Overall pipeline design
- [API: converter.md](../api/converter.md) - Function reference
- [User Guide](../user-guide.md) - CLI usage
- [Troubleshooting](../troubleshooting.md) - Common issues
