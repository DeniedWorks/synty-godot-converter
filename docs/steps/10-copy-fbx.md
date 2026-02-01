# Step 10: Copy FBX Files

This document provides comprehensive documentation for the FBX file copying step of the synty-converter pipeline. FBX copying is implemented in `converter.py` and involves discovering FBX model files from SourceFiles directories and copying them to the output directory.

**Module Location:** `synty-converter/converter.py`

**Related Documentation:**
- [Architecture](../architecture.md) - Overall pipeline context
- [API: converter](../api/converter.md) - Quick API reference
- [User Guide](../user-guide.md) - CLI options and usage
- [Troubleshooting](../troubleshooting.md) - Common FBX issues

---

## Table of Contents

- [Overview](#overview)
- [FBX Discovery Process](#fbx-discovery-process)
  - [Simplified Discovery with rglob](#simplified-discovery-with-rglob)
  - [Common Prefix Stripping](#common-prefix-stripping)
  - [Path Structure Preservation](#path-structure-preservation)
  - [Case-Insensitive File Finding](#case-insensitive-file-finding)
  - [Duplicate Removal](#duplicate-removal)
- [Core Function](#core-function)
  - [copy_fbx_files()](#copy_fbx_files)
  - [Parameters](#parameters)
  - [Return Value](#return-value)
- [Copy Logic Analysis](#copy-logic-analysis)
  - [File Iteration](#file-iteration)
  - [Path Preservation](#path-preservation)
  - [Skip Logic](#skip-logic)
  - [Dry Run Mode](#dry-run-mode)
- [Filter Pattern Support](#filter-pattern-support)
- [Directory Structure Preservation](#directory-structure-preservation)
- [Pipeline Integration](#pipeline-integration)
  - [Invocation Context](#invocation-context)
  - [Pre-Copy FBX Count](#pre-copy-fbx-count)
  - [Statistics Updated](#statistics-updated)
- [Configuration Options](#configuration-options)
  - [CLI Arguments](#cli-arguments)
  - [ConversionConfig Fields](#conversionconfig-fields)
- [Error Handling](#error-handling)
- [Code Examples](#code-examples)
- [Notes for Doc Cleanup](#notes-for-doc-cleanup)

---

## Overview

Step 10 copies FBX model files from the SourceFiles directory to the output directory. This step prepares the raw 3D models for subsequent Godot import and conversion.

### Key Responsibilities

1. **Discover FBX files** - Use `rglob("*.fbx")` to find all FBX files recursively
2. **Strip common prefixes** - Remove `SourceFiles/`, `FBX/`, `Models/` from paths
3. **Preserve remaining structure** - Maintain remaining subdirectory hierarchy (Props/, Environment/, Characters/)
4. **Avoid redundant copies** - Skip files that already exist with matching size
5. **Support filtering** - Copy only FBX files matching an optional pattern

### Pipeline Position

```
Step 9: Copy Textures
        |
        v
Step 10: Copy FBX Files  <-- You are here
        |
        v
Step 11: Generate mesh_material_mapping.json
        |
        v
Step 12: Generate project.godot
        |
        v
Step 13: Run Godot CLI
```


---

## FBX Discovery Process

### Simplified Discovery with rglob

The converter now uses a simplified discovery approach using `rglob("*.fbx")`:

```python
# Find all FBX files recursively in SourceFiles
fbx_files = list(config.source_files.rglob("*.fbx"))
fbx_files.extend(config.source_files.rglob("*.FBX"))  # Case-insensitive
```

This approach:
- **No directory hunting** - Finds FBX files regardless of folder structure
- **Works with any pack layout** - Standard `FBX/`, nested structures, or `Models/` folders
- **Simpler code** - Single glob operation instead of directory search logic

### Common Prefix Stripping

When copying FBX files, common Synty prefixes are stripped from paths:

```python
COMMON_PREFIXES = ["SourceFiles", "FBX", "Models"]

def strip_common_prefixes(path: Path) -> Path:
    """Strip common Synty prefixes from a path."""
    parts = list(path.parts)
    while parts and parts[0] in COMMON_PREFIXES:
        parts.pop(0)
    return Path(*parts) if parts else path
```

**Examples:**

| Source Path | After Stripping |
|------------|-----------------|
| `SourceFiles/FBX/Props/SM_Barrel.fbx` | `Props/SM_Barrel.fbx` |
| `SourceFiles/FBX/SM_Tree.fbx` | `SM_Tree.fbx` |
| `SourceFiles/Models/Environment/SM_Rock.fbx` | `Environment/SM_Rock.fbx` |
| `FBX/Characters/SK_Character.fbx` | `Characters/SK_Character.fbx` |

### Path Structure Preservation

The remaining path structure is preserved after prefix stripping:

```
SourceFiles/
  FBX/
    Props/                    # Preserved as Props/
      SM_Prop_Barrel.fbx
    Environment/              # Preserved as Environment/
      SM_Env_Tree.fbx
    Characters/               # Preserved as Characters/
      SK_Character.fbx
```

After copying to output:

```
output/
  models/
    Props/
      SM_Prop_Barrel.fbx
    Environment/
      SM_Env_Tree.fbx
    Characters/
      SK_Character.fbx
```

### Case-Insensitive File Finding

FBX files are found using case-insensitive matching to handle Windows/macOS differences:

```python
# Find all FBX files recursively (case-insensitive)
fbx_files = list(source_files.rglob("*.fbx"))
fbx_files.extend(source_files.rglob("*.FBX"))
```

Both `.fbx` and `.FBX` patterns are searched to catch files regardless of extension case.

### Duplicate Removal

Because Windows filesystems are case-insensitive, the same file could be found by both patterns. The converter removes duplicates:

```python
# Remove duplicates (Windows is case-insensitive)
seen_paths: set[Path] = set()
unique_fbx_files: list[Path] = []
for source_path in fbx_files:
    resolved = source_path.resolve()
    if resolved not in seen_paths:
        seen_paths.add(resolved)
        unique_fbx_files.append(source_path)
fbx_files = unique_fbx_files
```

The `resolve()` call normalizes paths to their canonical form, ensuring the same file is not processed twice even if discovered via different glob patterns.

---

## Core Function

### copy_fbx_files()

The main FBX copying function. Defined at lines 922-1039 in `converter.py`.

**Signature:**

```python
def copy_fbx_files(
    source_fbx_dir: Path,
    output_models_dir: Path,
    dry_run: bool,
    filter_pattern: str | None = None,
    additional_fbx_dirs: list[Path] | None = None,
) -> tuple[int, int]:
```

**Docstring:**

```python
"""Copy FBX files from FBX directories to output/models/, preserving structure.

Recursively finds all .fbx files (case-insensitive) in the source directory
(and any additional directories) and copies them to the output, preserving
the subdirectory structure. Files that already exist with the same size are
skipped.
"""
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `source_fbx_dir` | `Path` | Yes | Primary FBX directory containing FBX models |
| `output_models_dir` | `Path` | Yes | Path to output/models directory. Subdirectories will be created as needed |
| `dry_run` | `bool` | Yes | If True, only log what would be copied without actually copying files |
| `filter_pattern` | `str \| None` | No | Optional filter pattern for FBX filenames. If specified, only FBX files containing this pattern (case-insensitive) are copied |
| `additional_fbx_dirs` | `list[Path] \| None` | No | Optional list of additional FBX directories to search (for complex nested structures) |

### Return Value

Returns a tuple of `(fbx_copied, fbx_skipped)` where:

| Return Value | Description |
|--------------|-------------|
| `fbx_copied` | Number of FBX files copied (or would be copied in dry_run mode) |
| `fbx_skipped` | Number of FBX files skipped due to already existing at destination with matching file size |

**Example return values:**

```python
# All files copied, none existed
(150, 0)

# Re-running conversion, all files already exist
(0, 150)

# Partial copy (some new files, some existing)
(45, 105)
```

---

## Copy Logic Analysis

### File Iteration

The function iterates over all discovered FBX files as tuples of `(source_path, base_dir)`:

```python
# From converter.py lines 1017-1038
for source_path, base_dir in fbx_files:
    # Calculate relative path to preserve subdirectory structure
    # Use the base_dir this file came from to compute relative path
    relative_path = source_path.relative_to(base_dir)
    dest_path = output_models_dir / relative_path

    # Skip if destination already exists and is same size
    if dest_path.exists():
        if dest_path.stat().st_size == source_path.stat().st_size:
            logger.debug("Skipping existing FBX: %s", relative_path)
            skipped += 1
            continue

    if dry_run:
        logger.debug("[DRY RUN] Would copy FBX: %s", relative_path)
        copied += 1
    else:
        # Ensure parent directory exists
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, dest_path)
        logger.debug("Copied FBX: %s", relative_path)
        copied += 1
```

### Path Preservation

The key to structure preservation is stripping common prefixes and keeping the rest:

```python
relative_path = strip_common_prefixes(source_path.relative_to(source_files))
dest_path = output_models_dir / relative_path
```

**Example path mapping:**

| Source Path | After Prefix Strip | Destination |
|------------|-------------------|-------------|
| `SourceFiles/FBX/Props/SM_Prop_Barrel.fbx` | `Props/SM_Prop_Barrel.fbx` | `output/models/Props/SM_Prop_Barrel.fbx` |
| `SourceFiles/FBX/Characters/SK_Character.fbx` | `Characters/SK_Character.fbx` | `output/models/Characters/SK_Character.fbx` |
| `SourceFiles/FBX/SM_Env_Tree.fbx` | `SM_Env_Tree.fbx` | `output/models/SM_Env_Tree.fbx` |
| `SourceFiles/Models/Environment/SM_Rock.fbx` | `Environment/SM_Rock.fbx` | `output/models/Environment/SM_Rock.fbx` |

This ensures subdirectory structures like `Props/`, `Environment/`, `Characters/` are maintained while removing the `SourceFiles/FBX/` or `SourceFiles/Models/` wrapper directories.

### Skip Logic

Files are skipped when they already exist at the destination with the same file size:

```python
# From converter.py lines 1023-1028
if dest_path.exists():
    if dest_path.stat().st_size == source_path.stat().st_size:
        logger.debug("Skipping existing FBX: %s", relative_path)
        skipped += 1
        continue
```

**Skip conditions:**
1. Destination file must exist (`dest_path.exists()`)
2. File size must match (`dest_path.stat().st_size == source_path.stat().st_size`)

**Why size-based comparison?**
- Fast comparison (no need to read file contents)
- Reliable for FBX files (binary format, size changes indicate content changes)
- Allows partial re-runs to skip already-copied files

**Note:** If a source file is modified but happens to have the same size, it will be skipped. This is acceptable because FBX files typically change size when modified.

### Dry Run Mode

In dry run mode, no files are actually copied:

```python
# From converter.py lines 1030-1032
if dry_run:
    logger.debug("[DRY RUN] Would copy FBX: %s", relative_path)
    copied += 1
```

The `copied` counter is still incremented to show what *would* be copied, allowing accurate preview statistics.

---

## Filter Pattern Support

An optional filter pattern allows copying only specific FBX files:

```python
# From converter.py lines 1000-1013
# Apply filter pattern if specified
if filter_pattern:
    pattern_lower = filter_pattern.lower()
    original_count = len(fbx_files)
    fbx_files = [(f, d) for f, d in fbx_files if pattern_lower in f.stem.lower()]
    logger.debug(
        "Filter '%s' matched %d of %d FBX files",
        filter_pattern, len(fbx_files), original_count
    )

if not fbx_files:
    dirs_str = ", ".join(str(d) for d in all_fbx_dirs)
    logger.warning("No FBX files found after filtering in: %s", dirs_str)
    return 0, 0
```

**Filter behavior:**
- Case-insensitive matching (`pattern_lower` and `f.stem.lower()`)
- Matches against the file stem (name without extension)
- Partial matching (pattern can appear anywhere in the name)

**Filter examples:**

| Filter | Matches | Does Not Match |
|--------|---------|----------------|
| `Tree` | `SM_Env_Tree_01.fbx`, `Tree_Pine.fbx` | `SM_Prop_Barrel.fbx` |
| `character` | `SK_Character_Female.fbx` | `SM_Prop_Chair.fbx` |
| `SM_Prop` | `SM_Prop_Barrel.fbx`, `SM_Prop_Chair.fbx` | `SM_Env_Rock.fbx` |

---

## Directory Structure Preservation

### Standard Pack Structure

Most Synty packs have this FBX structure:

```
SourceFiles/
  FBX/
    Characters/
      SK_Character_01.fbx
      SK_Character_02.fbx
    Environment/
      SM_Env_Rock_01.fbx
      SM_Env_Tree_01.fbx
    Props/
      SM_Prop_Barrel_01.fbx
      SM_Prop_Chest_01.fbx
```

After copying (with `SourceFiles/FBX/` stripped):

```
output/
  models/
    Characters/
      SK_Character_01.fbx
      SK_Character_02.fbx
    Environment/
      SM_Env_Rock_01.fbx
      SM_Env_Tree_01.fbx
    Props/
      SM_Prop_Barrel_01.fbx
      SM_Prop_Chest_01.fbx
```

### Complex Nested Structure

Some packs have multiple FBX or Models directories. The `rglob` approach handles these seamlessly:

```
SourceFiles/
  DungeonA/
    FBX/
      SM_DungeonA_Door.fbx
    Models/
      SM_DungeonA_Wall.fbx
  DungeonB/
    FBX/
      SM_DungeonB_Door.fbx
```

After copying (with common prefixes stripped):

```
output/
  models/
    DungeonA/
      SM_DungeonA_Door.fbx     # SourceFiles/DungeonA/FBX/ stripped
      SM_DungeonA_Wall.fbx     # SourceFiles/DungeonA/Models/ stripped
    DungeonB/
      SM_DungeonB_Door.fbx     # SourceFiles/DungeonB/FBX/ stripped
```

The structure after `SourceFiles/` is preserved, with only the common `FBX/` or `Models/` directories stripped when they appear directly under a pack subfolder.

### Parent Directory Creation

The function ensures parent directories exist before copying:

```python
# From converter.py line 1035
dest_path.parent.mkdir(parents=True, exist_ok=True)
```

This creates any missing intermediate directories (e.g., `Props/`, `Characters/`) as needed.

---

## Pipeline Integration

### Invocation Context

The `copy_fbx_files()` function is called from `run_conversion()` at lines 1934-1976:

```python
# From converter.py lines 1934-1976
# Step 9: Copy FBX files
if not config.skip_fbx_copy:
    # Find all FBX directories recursively for complex nested structures
    # Also check for "Models" directories which some packs use (e.g., Generic folder)
    fbx_dirs = [config.source_files / "FBX"]
    if not fbx_dirs[0].exists():
        # Search for both FBX and Models directories
        fbx_dirs = [d for d in config.source_files.rglob("FBX") if d.is_dir()]
        models_dirs = [d for d in config.source_files.rglob("Models") if d.is_dir()]
        fbx_dirs.extend(models_dirs)
        if fbx_dirs:
            logger.debug("Found %d FBX/Models directories in nested structure", len(fbx_dirs))
            for fd in fbx_dirs:
                logger.debug("  FBX/Models dir: %s", fd)
    source_fbx = fbx_dirs[0] if fbx_dirs else config.source_files / "FBX"
    additional_fbx_dirs = fbx_dirs[1:] if len(fbx_dirs) > 1 else None
    output_models = pack_output_dir / "models"

    # Count FBX files before copying for step message
    all_fbx_dirs = [source_fbx]
    if additional_fbx_dirs:
        all_fbx_dirs.extend(additional_fbx_dirs)
    fbx_count = 0
    for fbx_dir in all_fbx_dirs:
        if fbx_dir.exists():
            fbx_count += len(list(fbx_dir.rglob("*.fbx"))) + len(list(fbx_dir.rglob("*.FBX")))
    logger.info("Step 9: Copying %d FBX files...", fbx_count)

    stats.fbx_copied, stats.fbx_skipped = copy_fbx_files(
        source_fbx,
        output_models,
        config.dry_run,
        config.filter_pattern,
        additional_fbx_dirs=additional_fbx_dirs,
    )

    if stats.fbx_copied == 0 and stats.fbx_skipped == 0:
        dirs_str = ", ".join(str(d) for d in fbx_dirs) if fbx_dirs else str(source_fbx)
        warning_msg = f"No FBX files found in {dirs_str}"
        stats.warnings.append(warning_msg)
else:
    logger.info("Step 9: Skipping FBX copy...")
```

### Pre-Copy FBX Count

Before calling `copy_fbx_files()`, the converter counts FBX files to display in the step message:

```python
# From converter.py lines 1952-1960
fbx_count = 0
for fbx_dir in all_fbx_dirs:
    if fbx_dir.exists():
        fbx_count += len(list(fbx_dir.rglob("*.fbx"))) + len(list(fbx_dir.rglob("*.FBX")))
logger.info("Step 9: Copying %d FBX files...", fbx_count)
```

This provides user feedback about the expected scope of the copy operation.

### Statistics Updated

The following `ConversionStats` fields are updated:

| Field | Type | Description |
|-------|------|-------------|
| `fbx_copied` | `int` | Number of FBX files successfully copied |
| `fbx_skipped` | `int` | Number of FBX files skipped (already existed) |

Statistics appear in the final conversion summary:

```python
# From converter.py lines 1551-1552
f"  FBX Files Copied: {stats.fbx_copied}",
f"  FBX Files Skipped: {stats.fbx_skipped}",
```

---

## Configuration Options

### CLI Arguments

The FBX copy step is controlled by these CLI arguments:

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--skip-fbx-copy` | flag | Off | Skip copying FBX files entirely |
| `--filter` | string | None | Filter pattern for FBX filenames (case-insensitive) |

**Examples:**

```bash
# Skip FBX copy (models already exist)
python converter.py ... --skip-fbx-copy

# Only copy tree-related FBX files
python converter.py ... --filter Tree

# Only copy character FBX files
python converter.py ... --filter Character
```

### ConversionConfig Fields

```python
# From converter.py lines 291, 297
skip_fbx_copy: bool = False
filter_pattern: str | None = None
```

The `skip_fbx_copy` field is defined at line 255 in the docstring:

```python
skip_fbx_copy: If True, skip copying FBX files from SourceFiles/FBX.
    Use this if the models/ directory is already populated.
```

---

## Error Handling

### Missing FBX Directory

If no FBX directories are found:

```python
# From converter.py lines 992-998
if not fbx_files:
    dirs_checked = ", ".join(str(d) for d in all_fbx_dirs if d.exists())
    if dirs_checked:
        logger.warning("No FBX files found in: %s", dirs_checked)
    else:
        logger.warning("No FBX directories found")
    return 0, 0
```

### Empty Filter Results

If the filter pattern matches no files:

```python
# From converter.py lines 1010-1013
if not fbx_files:
    dirs_str = ", ".join(str(d) for d in all_fbx_dirs)
    logger.warning("No FBX files found after filtering in: %s", dirs_str)
    return 0, 0
```

### No Files Copied Warning

After copying, if no files were processed:

```python
# From converter.py lines 1970-1973
if stats.fbx_copied == 0 and stats.fbx_skipped == 0:
    dirs_str = ", ".join(str(d) for d in fbx_dirs) if fbx_dirs else str(source_fbx)
    warning_msg = f"No FBX files found in {dirs_str}"
    stats.warnings.append(warning_msg)
```

This warning is added to `ConversionStats.warnings` for the final summary.

### Non-Existent Directories

Individual directories that don't exist are logged and skipped:

```python
# From converter.py lines 974-976
if not fbx_dir.exists():
    logger.debug("FBX directory not found, skipping: %s", fbx_dir)
    continue
```

---

## Code Examples

### Basic FBX Copy

```python
from pathlib import Path
from converter import copy_fbx_files

# Copy all FBX files from SourceFiles/FBX to output/models
copied, skipped = copy_fbx_files(
    source_fbx_dir=Path("C:/Synty/SourceFiles/FBX"),
    output_models_dir=Path("C:/Output/models"),
    dry_run=False
)

print(f"Copied: {copied}, Skipped: {skipped}")
```

### With Filter Pattern

```python
from pathlib import Path
from converter import copy_fbx_files

# Only copy FBX files containing "Tree" in the name
copied, skipped = copy_fbx_files(
    source_fbx_dir=Path("SourceFiles/FBX"),
    output_models_dir=Path("output/models"),
    dry_run=False,
    filter_pattern="Tree"
)

print(f"Copied {copied} tree-related FBX files")
```

### With Additional Directories

```python
from pathlib import Path
from converter import copy_fbx_files

# Handle complex nested pack structure
primary_dir = Path("SourceFiles/DungeonA/FBX")
additional = [
    Path("SourceFiles/DungeonB/FBX"),
    Path("SourceFiles/Generic/Models"),
]

copied, skipped = copy_fbx_files(
    source_fbx_dir=primary_dir,
    output_models_dir=Path("output/models"),
    dry_run=False,
    additional_fbx_dirs=additional
)
```

### Dry Run Preview

```python
from pathlib import Path
from converter import copy_fbx_files

# Preview what would be copied without making changes
copied, skipped = copy_fbx_files(
    source_fbx_dir=Path("SourceFiles/FBX"),
    output_models_dir=Path("output/models"),
    dry_run=True  # No files will be copied
)

# Output shows what WOULD happen:
# DEBUG: [DRY RUN] Would copy FBX: Props/SM_Prop_Barrel.fbx
# DEBUG: [DRY RUN] Would copy FBX: Environment/SM_Env_Tree.fbx
print(f"Would copy {copied} files, skip {skipped}")
```

### Re-Running Conversion

```python
from pathlib import Path
from converter import copy_fbx_files

# Re-run conversion - existing files will be skipped
copied, skipped = copy_fbx_files(
    source_fbx_dir=Path("SourceFiles/FBX"),
    output_models_dir=Path("output/models"),
    dry_run=False
)

if copied == 0 and skipped > 0:
    print(f"All {skipped} FBX files already exist, nothing to copy")
elif copied > 0:
    print(f"Copied {copied} new files, skipped {skipped} existing")
```

---

## Notes for Doc Cleanup

After reviewing the existing documentation, here are findings for consolidation:

### Redundant Information

1. **`docs/api/converter.md` Section "copy_fbx_files"** (lines 322-344):
   - Shows simplified function signature missing `filter_pattern` and `additional_fbx_dirs` parameters
   - Current signature at lines 322-331:
     ```python
     def copy_fbx_files(
         source_fbx_dir: Path,
         output_models_dir: Path,
         dry_run: bool
     ) -> tuple[int, int]
     ```
   - **Should be:**
     ```python
     def copy_fbx_files(
         source_fbx_dir: Path,
         output_models_dir: Path,
         dry_run: bool,
         filter_pattern: str | None = None,
         additional_fbx_dirs: list[Path] | None = None,
     ) -> tuple[int, int]
     ```
   - **Recommendation:** Update API doc to reflect current signature or add link to this step doc

2. **`docs/architecture.md` Section "Step 9: Copy FBX Files"** (lines 230-237):
   - Brief 4-line description that this document expands significantly
   - Content is accurate but minimal
   - **Recommendation:** Keep brief, add link to this document

3. **`docs/user-guide.md` multiple sections** reference FBX copying:
   - Line 152: `--skip-fbx-copy` option description
   - Line 155: `--keep-meshes-together` mentions FBX
   - Line 157: `--filter` option for FBX filtering
   - Lines 185, 207: Output structure showing models/ directory
   - Lines 255-257: Skip FBX Copy usage example
   - Lines 275-283: Keep Meshes Together usage
   - Lines 306-319: Filter pattern usage
   - **Recommendation:** Keep user-facing documentation, ensure it matches implementation

### Outdated Information

1. **`docs/api/converter.md` lines 322-331** - Function signature is incomplete:
   - Missing `filter_pattern` parameter
   - Missing `additional_fbx_dirs` parameter
   - **Action required:** Update to match current signature

2. **`docs/api/converter.md` line 344** - Returns description is correct but doesn't mention skip reason:
   - Current: "Files are skipped if they already exist with the same size."
   - This is accurate, no change needed

3. **`docs/architecture.md` line 231** - Step number mismatch:
   - Architecture doc says "Step 9: Copy FBX Files"
   - This document calls it "Step 10"
   - The code uses "Step 9" internally
   - **Recommendation:** Standardize step numbering across all docs or add note about renumbering

### Information to Incorporate

1. **Nested directory support** is not documented elsewhere:
   - The ability to handle `FBX/` and `Models/` directories from complex pack structures
   - Should be mentioned in user-guide.md for users with problematic packs

2. **Case-insensitive file finding** behavior:
   - Both `.fbx` and `.FBX` extensions are searched
   - Windows duplicate removal logic
   - Worth adding to troubleshooting.md

### Suggested Cross-References

Add to the following docs:

1. **`docs/architecture.md`** Step 9 section (line 230):
   - Add: "See [Step 10: Copy FBX Files](steps/10-copy-fbx.md) for detailed implementation."

2. **`docs/api/converter.md`** copy_fbx_files section (line 322):
   - Add at top: "For detailed implementation documentation, see [Step 10: Copy FBX Files](../steps/10-copy-fbx.md)."
   - Update function signature to include all parameters

3. **`docs/user-guide.md`** Section "Skip FBX Copy" (line 255):
   - Add: "See [Step 10: Copy FBX Files](steps/10-copy-fbx.md) for technical details on how FBX files are discovered and copied."

4. **`docs/troubleshooting.md`**:
   - Add section for FBX-related issues (missing FBX directory, no files found after filter)

### ConversionConfig Documentation Gap

The `ConversionConfig` class documentation in `docs/api/converter.md` (lines 51-61) is missing:
- `keep_meshes_together: bool = False`
- `mesh_format: str = "tscn"`
- `filter_pattern: str | None = None`

These fields exist in the actual code (lines 295-297) but are not in the API doc.

---

*Last Updated: 2026-02-01*
