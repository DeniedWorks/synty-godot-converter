# Step 8: Copy Textures

This document provides comprehensive documentation for the texture copying step of the synty-converter pipeline. Texture copying is implemented in `converter.py` and involves discovering required textures from mapped materials and copying them to the output directory.

**Module Location:** `synty-converter/converter.py`

**Related Documentation:**
- [Architecture](../architecture.md) - Overall pipeline context
- [API: converter](../api/converter.md) - Quick API reference
- [API: unity_package](../api/unity_package.md) - GuidMap and texture extraction
- [Troubleshooting](../troubleshooting.md) - Missing texture issues

---

## Table of Contents

- [Overview](#overview)
- [Texture Discovery Process](#texture-discovery-process)
  - [Building the Required Textures Set](#building-the-required-textures-set)
  - [How Textures Are Referenced](#how-textures-are-referenced)
- [Texture Source Priority](#texture-source-priority)
  - [Primary Source: Unity Package Temp Files](#primary-source-unity-package-temp-files)
  - [Fallback Source: SourceFiles Directory](#fallback-source-sourcefiles-directory)
- [Core Functions](#core-functions)
  - [copy_textures()](#copy_textures)
  - [find_texture_file()](#find_texture_file)
  - [find_fallback_texture()](#find_fallback_texture)
  - [generate_texture_import_file()](#generate_texture_import_file)
- [Constants](#constants)
  - [TEXTURE_EXTENSIONS](#texture_extensions)
  - [FALLBACK_TEXTURE_PATTERNS](#fallback_texture_patterns)
  - [TEXTURE_IMPORT_TEMPLATE](#texture_import_template)
- [Path Resolution and Naming](#path-resolution-and-naming)
  - [Synty Naming Inconsistencies](#synty-naming-inconsistencies)
  - [Name Variation Handling](#name-variation-handling)
- [Optimization Strategy](#optimization-strategy)
- [Import File Generation](#import-file-generation)
- [Error Handling](#error-handling)
- [Pipeline Integration](#pipeline-integration)
- [Code Examples](#code-examples)
- [Notes for Doc Cleanup](#notes-for-doc-cleanup)

---

## Overview

Step 8 copies texture files that are actually referenced by the generated materials. This is an optimization step that avoids copying unused textures from the asset pack.

### Key Responsibilities

1. **Build required texture set** - Collect texture names from all mapped materials
2. **Smart texture filtering** - When using `--filter`, only include textures needed by filtered FBX files
3. **Resolve texture sources** - Find textures in .unitypackage or SourceFiles
4. **Copy with correct naming** - Handle Synty naming inconsistencies
5. **Generate .import files** - Create Godot import sidecar files with VRAM compression (or BPTC when `--high-quality-textures` is used)
6. **Handle missing textures** - Log warnings, optionally use fallback

### Pipeline Position

```
Step 7: Copy Shaders
        |
        v
Step 8: Copy Textures  <-- You are here
        |
        v
Step 9: Copy FBX Files
```

---

## Texture Discovery Process

### Building the Required Textures Set

Textures are discovered during material mapping (Step 5) and collected into a set before copying:

```python
# From converter.py lines 1836-1848
mapped_materials: list[MappedMaterial] = []
required_textures: set[str] = set()

for guid, unity_mat in unity_materials:
    try:
        # Use cached shader decision if available
        cached_shader = shader_cache.get(unity_mat.name)
        mapped = map_material(unity_mat, guid_map.texture_guid_to_name, override_shader=cached_shader)
        mapped_materials.append(mapped)

        # Collect required textures
        for texture_name in mapped.textures.values():
            required_textures.add(texture_name)

    except Exception as e:
        warning_msg = f"Failed to map material '{unity_mat.name}': {e}"
        logger.debug(warning_msg)
        stats.warnings.append(warning_msg)
```

The `mapped.textures` dictionary contains Godot parameter names mapped to texture filenames:

```python
# Example mapped.textures content:
{
    "base_texture": "PolygonNature_Texture_01_A.png",
    "normal_texture": "PolygonNature_Texture_01_N.png",
    "emission_texture": "PolygonNature_Texture_01_E.png"
}
```

### How Textures Are Referenced

The texture reference chain is:

1. **Unity material** - References textures by GUID in `m_TexEnvs` section
2. **GuidMap** - Maps texture GUID to filename (from `unity_package.py`)
3. **map_material()** - Resolves GUID to filename during property mapping
4. **MappedMaterial.textures** - Contains final filename for each texture slot
5. **required_textures set** - Aggregates all unique texture filenames

```
Unity .mat file               GuidMap                      MappedMaterial
+--------------------------+  +------------------------+  +------------------+
| m_TexEnvs:               |  | texture_guid_to_name:  |  | textures: {      |
|   - _Albedo_Map:         |  |   "abc123..." ->       |  |   "base_texture" |
|       m_Texture: {       |->|     "Texture_01.png"   |->|     -> "Tex..."  |
|         guid: abc123...  |  |   "def456..." ->       |  |   ...            |
|       }                  |  |     "Texture_01_N.png" |  | }                |
+--------------------------+  +------------------------+  +------------------+
```

---

## Texture Source Priority

The texture copying system uses a two-tier source priority:

### Primary Source: Unity Package Temp Files

Textures extracted from the `.unitypackage` are the preferred source because:
- They are the exact textures referenced by the materials
- GUID-based lookup ensures correct file
- No naming inconsistency issues

The GuidMap contains:
- `texture_guid_to_name`: Maps GUID to texture filename
- `texture_guid_to_path`: Maps GUID to temp file path (extracted during package processing)

```python
# From converter.py lines 1918-1919
# Build reverse lookup: texture_name -> GUID
texture_name_to_guid = {name: guid for guid, name in guid_map.texture_guid_to_name.items()}
```

### Fallback Source: SourceFiles Directory

When a texture is not found in the .unitypackage temp files, the system searches the SourceFiles directory:

```python
# From converter.py lines 1903-1915
texture_dirs = [config.source_files / "Textures"]
if not texture_dirs[0].exists():
    texture_dirs = [d for d in config.source_files.rglob("Textures") if d.is_dir()]
    if texture_dirs:
        logger.debug("Found %d Textures directories as fallback sources", len(texture_dirs))
    else:
        logger.debug("No SourceFiles/Textures found - using .unitypackage textures only")

source_textures = texture_dirs[0] if texture_dirs else config.source_files / "Textures"
additional_texture_dirs = texture_dirs[1:] if len(texture_dirs) > 1 else None
```

This handles complex nested pack structures like POLYGON Dwarven Dungeon which has multiple Textures directories.

---

## Core Functions

### copy_textures()

The main texture copying function. Defined at lines 752-919 in `converter.py`.

**Signature:**

```python
def copy_textures(
    source_textures: Path,
    output_textures: Path,
    required: set[str],
    dry_run: bool,
    fallback_texture: Path | None = None,
    texture_guid_to_path: dict[str, Path] | None = None,
    texture_name_to_guid: dict[str, str] | None = None,
    additional_texture_dirs: list[Path] | None = None,
) -> tuple[int, int, int]:
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `source_textures` | `Path` | Primary SourceFiles/Textures directory |
| `output_textures` | `Path` | Destination textures directory |
| `required` | `set[str]` | Set of texture names to copy (with or without extensions) |
| `dry_run` | `bool` | If True, only log what would be copied |
| `fallback_texture` | `Path \| None` | Optional fallback texture for missing files |
| `texture_guid_to_path` | `dict[str, Path] \| None` | GUID to temp file path mapping |
| `texture_name_to_guid` | `dict[str, str] \| None` | Texture name to GUID reverse mapping |
| `additional_texture_dirs` | `list[Path] \| None` | Additional directories to search |

**Returns:**

Tuple of `(textures_copied, textures_fallback, textures_missing)`.

**Implementation Flow:**

```python
for texture_name in required:
    # 1. Try temp files from .unitypackage first
    temp_path = None
    if texture_guid_to_path and texture_name_to_guid:
        guid = texture_name_to_guid.get(texture_name)
        if guid:
            temp_path = texture_guid_to_path.get(guid)

    if temp_path and temp_path.exists():
        # Copy from temp file
        dest_path = output_textures / texture_name
        shutil.copy2(temp_path, dest_path)
        generate_texture_import_file(dest_path)
        copied += 1
        from_temp += 1
        continue

    # 2. Fall back to SourceFiles search
    source_path = find_texture_file(source_textures, texture_name, additional_texture_dirs)

    if source_path is None:
        # 3. Handle missing texture (try fallback or log warning)
        if fallback_texture is not None and fallback_texture.exists():
            # Copy fallback with missing texture's name
            shutil.copy2(fallback_texture, dest_path)
            generate_texture_import_file(dest_path)
            fallback_count += 1
        else:
            logger.warning("Texture not found in package or SourceFiles: %s", texture_name)
            missing += 1
        continue

    # 4. Copy from SourceFiles with correct naming
    dest_name = base_name + source_path.suffix
    dest_path = output_textures / dest_name
    shutil.copy2(source_path, dest_path)
    generate_texture_import_file(dest_path)
    copied += 1
    from_source += 1
```

---

### find_texture_file()

Searches for a texture by name across directories. Defined at lines 626-703.

**Signature:**

```python
def find_texture_file(
    textures_dir: Path,
    texture_name: str,
    additional_texture_dirs: list[Path] | None = None,
) -> Path | None:
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `textures_dir` | `Path` | Primary directory to search |
| `texture_name` | `str` | Texture name (with or without extension) |
| `additional_texture_dirs` | `list[Path] \| None` | Additional directories to search |

**Returns:**

`Path` to the texture file if found, `None` otherwise.

**Implementation Details:**

1. **Strip extension** - Extracts base name from texture_name
2. **Build name variations** - Creates alternative names to try (see [Name Variation Handling](#name-variation-handling))
3. **Search root directories first** - Checks all directories' roots with each extension
4. **Recursive search fallback** - Uses `rglob` if not found in root

```python
# Step 1: Strip known extension
base_name = texture_name
for ext in TEXTURE_EXTENSIONS:
    if texture_name.lower().endswith(ext.lower()):
        base_name = texture_name[:-len(ext)]
        break

# Step 2: Build name variations
name_variations = [base_name]
match = re.match(r'^(.+?)(_\d+_[A-Za-z]+(?:_\w+)?)$', base_name)
if match:
    prefix, suffix = match.groups()
    name_variations.append(f"{prefix}_Texture{suffix}")

# Step 3: Search all directories
all_texture_dirs = [textures_dir]
if additional_texture_dirs:
    all_texture_dirs.extend(additional_texture_dirs)

for search_dir in all_texture_dirs:
    for name in name_variations:
        for ext in TEXTURE_EXTENSIONS:
            texture_path = search_dir / f"{name}{ext}"
            if texture_path.exists():
                return texture_path

# Step 4: Recursive fallback
for search_dir in all_texture_dirs:
    for name in name_variations:
        for ext in TEXTURE_EXTENSIONS:
            for texture_path in search_dir.rglob(f"{name}{ext}"):
                return texture_path

return None
```

---

### find_fallback_texture()

Finds the pack's main texture atlas for use as a fallback. Defined at lines 601-623.

**Signature:**

```python
def find_fallback_texture(textures_dir: Path) -> Path | None:
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `textures_dir` | `Path` | SourceFiles/Textures directory |

**Returns:**

`Path` to fallback texture if found, `None` otherwise.

**Implementation:**

```python
for pattern in FALLBACK_TEXTURE_PATTERNS:
    # Only search in root directory, not subdirectories
    matches = list(textures_dir.glob(pattern))
    if matches:
        # Return first match (prefer shorter names)
        matches.sort(key=lambda p: len(p.name))
        logger.debug("Found fallback texture: %s", matches[0].name)
        return matches[0]

return None
```

**Note:** The current pipeline passes `fallback_texture=None` to `copy_textures()`, so fallback textures are not currently used. Missing textures are logged as warnings instead.

---

### generate_texture_import_file()

Creates a Godot `.import` sidecar file for a texture. Defined at lines 706-749.

**Signature:**

```python
def generate_texture_import_file(texture_path: Path) -> None:
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `texture_path` | `Path` | Absolute path to the copied texture file |

**Purpose:**

The `.import` file configures Godot to:
- Use VRAM compression (CompressedTexture2D)
- Apply high quality compression settings
- Generate mipmaps
- Fix alpha borders

**Implementation:**

```python
# Calculate res:// path
filename = texture_path.name
res_path = f"res://textures/{filename}"

# Generate unique identifiers
hash_input = f"{filename}{random.randint(0, 999999999)}"
file_hash = hashlib.md5(hash_input.encode()).hexdigest()[:12]
uid_chars = "abcdefghijklmnopqrstuvwxyz0123456789"
uid = "".join(random.choice(uid_chars) for _ in range(5 + random.randint(0, 8)))

# Format and write the import file
import_content = TEXTURE_IMPORT_TEMPLATE.format(
    uid=uid,
    filename=filename,
    hash=file_hash,
    res_path=res_path,
)

import_path = texture_path.parent / f"{filename}.import"
import_path.write_text(import_content, encoding="utf-8")
```

---

## Constants

### TEXTURE_EXTENSIONS

Supported texture file extensions. Defined at line 140.

```python
TEXTURE_EXTENSIONS = [".png", ".tga", ".jpg", ".jpeg", ".PNG", ".TGA", ".JPG", ".JPEG"]
```

Both lowercase and uppercase variants are included for case-insensitive matching on case-sensitive filesystems.

### FALLBACK_TEXTURE_PATTERNS

Patterns for finding the pack's main texture atlas. Defined at lines 144-150.

```python
FALLBACK_TEXTURE_PATTERNS = [
    "Polygon*_Texture_01.png",     # Most common: PolygonNature_Texture_01.png
    "Polygon*_Texture_01_A.png",   # Some packs use _A suffix
    "POLYGON*_Texture_01.png",     # Uppercase variant
    "*_Texture_01_A.png",          # Fallback: any pack with _A suffix
    "Texture_01.png",              # Simple naming
]
```

**Order matters** - first matching pattern wins. Patterns are searched in order to prefer more specific matches.

### TEXTURE_IMPORT_TEMPLATE

Template for Godot `.import` sidecar files. Defined at lines 154-195.

```python
TEXTURE_IMPORT_TEMPLATE = """[remap]

importer="texture"
type="CompressedTexture2D"
uid="uid://{uid}"
path="res://.godot/imported/{filename}-{hash}.ctex"
metadata={{
"vram_texture": true
}}

[deps]

source_file="{res_path}"
dest_files=["res://.godot/imported/{filename}-{hash}.ctex"]

[params]

compress/mode=2
compress/high_quality=true
compress/lossy_quality=0.7
compress/hdr_compression=1
compress/normal_map=0
compress/channel_pack=0
mipmaps/generate=true
mipmaps/limit=-1
roughness/mode=0
roughness/src_normal=""
process/fix_alpha_border=true
process/premult_alpha=false
process/normal_map_invert_y=false
process/hdr_as_srgb=false
process/hdr_clamp_exposure=false
process/size_limit=0
detect_3d/compress_to=1
"""
```

**Key settings:**

| Setting | Value | Purpose |
|---------|-------|---------|
| `compress/mode` | 2 | VRAM compression (GPU-optimized) |
| `compress/high_quality` | true | Better visual quality |
| `compress/bptc_ldr` | 0 or 1 | BPTC compression mode (1 when `--high-quality-textures` is used) |
| `mipmaps/generate` | true | Enable mipmapping |
| `process/fix_alpha_border` | true | Prevent alpha edge artifacts |

### High Quality Texture Compression

When the `--high-quality-textures` flag is enabled, the import files are generated with BPTC (BC7) compression enabled:

```ini
compress/bptc_ldr=1
```

BPTC compression provides:
- Higher visual quality, especially for gradients and transparency
- Better preservation of color accuracy
- Larger compressed file sizes compared to default S3TC/DXT compression

This is recommended for:
- Hero assets that players see up close
- Textures with subtle gradients or transparency
- When visual fidelity is prioritized over file size

---

## Path Resolution and Naming

### Synty Naming Inconsistencies

Synty asset packs have naming inconsistencies between Unity materials and SourceFiles:

| Unity Material Reference | SourceFiles Actual Name |
|-------------------------|-------------------------|
| `PolygonSamuraiEmpire_01_A` | `PolygonSamuraiEmpire_Texture_01_A` |
| `PolygonNature_01_A` | `PolygonNature_Texture_01_A` |

The Unity package references textures without `_Texture` in the name, but the SourceFiles directory contains textures WITH `_Texture`.

### Name Variation Handling

The `find_texture_file()` function handles this by building name variations:

```python
# Build list of name variations to try
name_variations = [base_name]

# Try inserting "_Texture" before numbered suffixes like "_01_A", "_02_B", etc.
match = re.match(r'^(.+?)(_\d+_[A-Za-z]+(?:_\w+)?)$', base_name)
if match:
    prefix, suffix = match.groups()
    name_variations.append(f"{prefix}_Texture{suffix}")

# Also try just appending "_Texture" variations
if "_Texture" not in base_name:
    name_variations.append(base_name.replace("_01", "_Texture_01"))
    name_variations.append(base_name.replace("_02", "_Texture_02"))
    name_variations.append(base_name.replace("_03", "_Texture_03"))
    name_variations.append(base_name.replace("_04", "_Texture_04"))
```

**Example transformations:**

| Input | Generated Variations |
|-------|---------------------|
| `PolygonSamurai_01_A` | `PolygonSamurai_01_A`, `PolygonSamurai_Texture_01_A` |
| `Ground_02` | `Ground_02`, `Ground_Texture_02` |
| `Tree_Bark_Normal` | `Tree_Bark_Normal` (no number suffix to modify) |

### Destination Naming

When copying, the **requested texture name** is preserved (what materials expect), but the **source extension** is used:

```python
# From copy_textures() lines 881-890
# Use the requested texture name (what materials expect), but with source's extension
base_name = texture_name
for ext in TEXTURE_EXTENSIONS:
    if texture_name.lower().endswith(ext.lower()):
        base_name = texture_name[:-len(ext)]
        break
dest_name = base_name + source_path.suffix
dest_path = output_textures / dest_name
```

This ensures materials reference the correct filename while preserving the actual file format.

---

## Optimization Strategy

The texture copying step is optimized to avoid unnecessary work:

### 1. Only Copy Referenced Textures

Instead of copying all textures from the asset pack, only textures that are actually referenced by materials are copied:

```python
# Before copying
logger.info("Step 8: Copying %d textures...", len(required_textures))
```

This can dramatically reduce the output size. A pack with 500+ textures might only need 50-100 for the specific materials being used.

### 1a. Smart Texture Filtering

When using the `--filter` option to convert only specific FBX files, the converter also intelligently filters textures. Instead of copying all textures referenced by all materials in the pack, it only copies textures that are actually used by the filtered FBX files.

This is accomplished by:
1. Parsing `MaterialList.txt` to identify which materials each FBX file uses
2. Filtering the material list to only include materials used by filtered FBX files
3. Building the required texture set from this filtered material list

**Example**: Using `--filter Chest` on POLYGON Samurai Empire:
- Full pack: 234 textures
- With filter: 8 textures
- Reduction: 97%

This makes it practical to extract small subsets of assets from large packs without including unnecessary textures.

### 2. Prefer Package Textures

Textures from the `.unitypackage` are preferred over SourceFiles because:
- Exact GUID match guarantees correct file
- Already extracted to temp directory
- Avoids name resolution complexity

### 3. Efficient Search Order

The search order is optimized:
1. Check temp files (O(1) dictionary lookup)
2. Check root directory of each texture dir
3. Only fall back to recursive search (`rglob`) if needed

```python
# Fast path: root directory check
for search_dir in all_texture_dirs:
    for name in name_variations:
        for ext in TEXTURE_EXTENSIONS:
            texture_path = search_dir / f"{name}{ext}"
            if texture_path.exists():
                return texture_path

# Slow path: recursive search (only if not found above)
for search_dir in all_texture_dirs:
    for name in name_variations:
        for ext in TEXTURE_EXTENSIONS:
            for texture_path in search_dir.rglob(f"{name}{ext}"):
                return texture_path
```

### 4. Statistics Tracking

The copy function tracks where textures came from for debugging:

```python
from_temp = 0
from_source = 0

# ... copying logic ...

logger.debug(
    "Copied %d textures (%d from package, %d from SourceFiles), %d fallback, %d missing",
    copied, from_temp, from_source, fallback_count, missing
)
```

---

## Import File Generation

Every copied texture gets a corresponding `.import` sidecar file. This pre-configures Godot's import settings.

### Why Pre-Generate Import Files?

1. **Consistent settings** - All textures use VRAM compression
2. **Faster first import** - Godot doesn't need to analyze each texture
3. **Prevent yellow textures** - VRAM mode prevents common import issues

### Generated File Structure

For a texture `Ground_01.png`, creates `Ground_01.png.import`:

```ini
[remap]

importer="texture"
type="CompressedTexture2D"
uid="uid://abc123xyz"
path="res://.godot/imported/Ground_01.png-1a2b3c4d5e6f.ctex"
metadata={
"vram_texture": true
}

[deps]

source_file="res://textures/Ground_01.png"
dest_files=["res://.godot/imported/Ground_01.png-1a2b3c4d5e6f.ctex"]

[params]

compress/mode=2
compress/high_quality=true
...
```

---

## Error Handling

The texture copying system uses graceful degradation:

| Scenario | Behavior |
|----------|----------|
| Texture not in temp files | Falls back to SourceFiles search |
| Texture not in SourceFiles | Logs warning, increments `missing` count |
| Fallback texture provided | Copies fallback with missing texture's name |
| Extension mismatch | Uses source file's actual extension |
| Search directory missing | Skips that directory, continues |
| Dry run mode | Logs what would happen, no actual copies |

### Warning Messages

Missing textures generate warning logs:

```python
logger.warning("Texture not found in package or SourceFiles: %s", texture_name)
```

These appear in the conversion output as:
```
WARNING: Texture not found in package or SourceFiles: Generic_Rock_01.png
```

### Return Value Interpretation

```python
copied, fallback_count, missing = copy_textures(...)

if missing > 0:
    logger.warning("%d textures could not be found", missing)
if fallback_count > 0:
    logger.info("%d textures used fallback atlas", fallback_count)
```

---

## Pipeline Integration

### Input Requirements

Before Step 8, the following must be available:

1. **GuidMap** - From Step 3 (extract_unitypackage)
   - `texture_guid_to_name`: GUID -> filename mapping
   - `texture_guid_to_path`: GUID -> temp file path mapping

2. **MappedMaterials** - From Step 5 (map_material)
   - Each material's `textures` dict contains required texture names

3. **Output Directory** - From Step 2
   - `output/textures/` directory must exist

### Invocation

From `run_conversion()` at lines 1899-1932:

```python
# Step 8: Copy required textures
logger.info("Step 8: Copying %d textures...", len(required_textures))

# Build reverse lookup: texture_name -> GUID
texture_name_to_guid = {name: guid for guid, name in guid_map.texture_guid_to_name.items()}

# Copy required textures
stats.textures_copied, stats.textures_fallback, stats.textures_missing = copy_textures(
    source_textures,
    output_textures,
    required_textures,
    config.dry_run,
    fallback_texture=None,  # No fallback - let missing textures fail
    texture_guid_to_path=guid_map.texture_guid_to_path,
    texture_name_to_guid=texture_name_to_guid,
    additional_texture_dirs=additional_texture_dirs,
)
```

### Statistics Updated

The following `ConversionStats` fields are updated:

| Field | Description |
|-------|-------------|
| `textures_copied` | Total textures successfully copied |
| `textures_fallback` | Textures using fallback atlas |
| `textures_missing` | Textures that could not be found |

---

## Code Examples

### Basic Texture Copy

```python
from pathlib import Path
from converter import copy_textures

# Simple case: copy specific textures
required = {"Ground_01.png", "Trees_02.png", "Rocks_03.png"}

copied, fallback, missing = copy_textures(
    source_textures=Path("C:/Synty/SourceFiles/Textures"),
    output_textures=Path("C:/Output/textures"),
    required=required,
    dry_run=False
)

print(f"Copied: {copied}, Fallback: {fallback}, Missing: {missing}")
```

### With GUID Mapping

```python
from pathlib import Path
from unity_package import extract_unitypackage
from converter import copy_textures

# Extract package to get GUID mappings
guid_map = extract_unitypackage(Path("Package.unitypackage"))

# Build reverse lookup
texture_name_to_guid = {name: guid for guid, name in guid_map.texture_guid_to_name.items()}

# Copy textures (prefers package textures)
copied, fallback, missing = copy_textures(
    source_textures=Path("SourceFiles/Textures"),
    output_textures=Path("output/textures"),
    required={"Texture_01_A.png", "Texture_01_N.png"},
    dry_run=False,
    texture_guid_to_path=guid_map.texture_guid_to_path,
    texture_name_to_guid=texture_name_to_guid,
)
```

### Finding Textures Manually

```python
from pathlib import Path
from converter import find_texture_file

# Search for a texture with name variations
texture_path = find_texture_file(
    textures_dir=Path("C:/Synty/SourceFiles/Textures"),
    texture_name="PolygonSamurai_01_A",  # Will also try PolygonSamurai_Texture_01_A
    additional_texture_dirs=[
        Path("C:/Synty/SourceFiles/Generic/Textures"),
        Path("C:/Synty/SourceFiles/Expansion/Textures"),
    ]
)

if texture_path:
    print(f"Found: {texture_path}")
else:
    print("Texture not found")
```

### Dry Run Mode

```python
from pathlib import Path
from converter import copy_textures

# Preview what would be copied without making changes
copied, fallback, missing = copy_textures(
    source_textures=Path("SourceFiles/Textures"),
    output_textures=Path("output/textures"),
    required={"Texture_01.png", "Missing_Texture.png"},
    dry_run=True  # No files will be copied
)

# Output shows what WOULD happen:
# DEBUG: [DRY RUN] Would copy texture from temp: Texture_01.png
# WARNING: Texture not found in package or SourceFiles: Missing_Texture.png
```

---

## Notes for Doc Cleanup

After reviewing the existing documentation, here are findings for consolidation:

### Redundant Information

1. **`docs/api/converter.md` Section "copy_textures"** (lines 294-319):
   - Shows simplified function signature without all parameters
   - Missing `texture_guid_to_path`, `texture_name_to_guid`, `additional_texture_dirs` parameters
   - **Recommendation:** Update API doc to reflect current signature or link to this step doc

2. **`docs/architecture.md` Section "Step 8: Copy Textures"** (lines 221-228):
   - Brief 4-line description that this document expands significantly
   - **Recommendation:** Keep brief, add link to this document

3. **`docs/troubleshooting.md` Section "Missing Textures"** (lines 190-223):
   - Covers symptoms and solutions for missing texture issues
   - **Recommendation:** Keep as-is, this is user-facing troubleshooting

### Outdated Information

1. **`docs/api/converter.md` line 304-305** - Shows return as `tuple[int, int]`:
   ```python
   def copy_textures(...) -> tuple[int, int]
   ```
   Should be:
   ```python
   def copy_textures(...) -> tuple[int, int, int]
   ```
   (Returns copied, fallback, missing - three values)

2. **`docs/api/converter.md` line 318** - Returns description is outdated:
   ```
   Tuple of `(textures_copied, textures_missing)`.
   ```
   Should be:
   ```
   Tuple of `(textures_copied, textures_fallback, textures_missing)`.
   ```

3. **`docs/api/unity_package.md` line 77-79** - GuidMap class definition missing `texture_guid_to_path`:
   ```python
   @dataclass
   class GuidMap:
       guid_to_pathname: dict[str, str] = field(default_factory=dict)
       guid_to_content: dict[str, bytes] = field(default_factory=dict)
       texture_guid_to_name: dict[str, str] = field(default_factory=dict)
   ```
   Should include:
   ```python
       texture_guid_to_path: dict[str, Path] = field(default_factory=dict)
   ```

### Information to Incorporate

1. **Package texture extraction** from `unity_package.py`:
   - The `_extract_textures_to_temp()` function (lines 387-423) extracts textures to temp files
   - This is how `texture_guid_to_path` gets populated
   - Relevant context for understanding the primary texture source

### Suggested Cross-References

Add to the following docs:

1. **`docs/architecture.md`** Step 8 section:
   - Add: "See [Step 8: Copy Textures](steps/08-copy-textures.md) for detailed implementation."

2. **`docs/api/converter.md`** copy_textures section:
   - Add at top: "For detailed implementation documentation, see [Step 8: Copy Textures](../steps/08-copy-textures.md)."
   - Update function signature and return type

3. **`docs/troubleshooting.md`** Missing Textures section:
   - Add: "See [Step 8: Copy Textures](steps/08-copy-textures.md) for how textures are discovered and copied."

4. **`docs/api/unity_package.md`** GuidMap section:
   - Add `texture_guid_to_path` attribute
   - Add explanation of temp file extraction

---

*Last Updated: 2026-01-31*
