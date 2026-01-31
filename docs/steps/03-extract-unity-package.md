# Step 3: Extract Unity Package

This document provides comprehensive documentation for the `unity_package.py` module, which handles extraction of Unity `.unitypackage` files and builds GUID mappings for materials and textures.

**Module Location:** `synty-converter/unity_package.py` (566 lines)

**Related Documentation:**
- [Architecture](../architecture.md) - Overall pipeline context
- [Unity Reference](../unity-reference.md) - Unity shader GUIDs and formats
- [API: unity_package](../api/unity_package.md) - API reference (condensed)

---

## Table of Contents

- [Overview](#overview)
- [Unity Package Format](#unity-package-format)
  - [Archive Structure](#archive-structure)
  - [GUID Folder Layout](#guid-folder-layout)
  - [GUID Format Specification](#guid-format-specification)
- [Module Constants](#module-constants)
- [GuidMap Class](#guidmap-class)
  - [Attributes](#attributes)
  - [Methods](#methods)
  - [Usage Examples](#usage-examples)
- [Main Entry Point: extract_unitypackage()](#main-entry-point-extract_unitypackage)
  - [Function Signature](#function-signature)
  - [Parameters](#parameters)
  - [Return Value](#return-value)
  - [Exceptions](#exceptions)
  - [Extraction Process](#extraction-process)
  - [Example Usage](#example-usage)
- [Internal Functions](#internal-functions)
  - [_parse_tar_structure()](#_parse_tar_structure)
  - [_is_valid_guid()](#_is_valid_guid)
  - [_build_guid_to_pathname()](#_build_guid_to_pathname)
  - [_build_texture_guid_map()](#_build_texture_guid_map)
  - [_extract_material_contents()](#_extract_material_contents)
  - [_extract_textures_to_temp()](#_extract_textures_to_temp)
- [Public Helper Functions](#public-helper-functions)
  - [get_material_guids()](#get_material_guids)
  - [get_material_name()](#get_material_name)
  - [resolve_texture_guid()](#resolve_texture_guid)
  - [print_guid_map_summary()](#print_guid_map_summary)
- [CLI Usage](#cli-usage)
- [Integration with Pipeline](#integration-with-pipeline)
- [Error Handling](#error-handling)
- [Performance Considerations](#performance-considerations)
- [Notes for Doc Cleanup](#notes-for-doc-cleanup)

---

## Overview

The `unity_package.py` module is responsible for **Step 3** of the 12-step conversion pipeline. It extracts Unity package archives and builds the GUID mappings required for subsequent material parsing.

**Core Responsibilities:**

1. Open and decompress `.unitypackage` files (gzip-compressed tar archives)
2. Parse the internal GUID-based folder structure
3. Build three primary mappings:
   - GUID to Unity asset pathname (all assets)
   - GUID to raw content bytes (`.mat` files only)
   - Texture GUID to filename (PNG, TGA, JPG files only)
4. Extract textures to temporary files for later processing

**Dependencies:**

```python
from __future__ import annotations  # PEP 604 union syntax support

import logging        # Logging infrastructure
import tarfile        # Tar archive handling
import tempfile       # Temporary directory creation
from dataclasses import dataclass, field  # GuidMap dataclass
from pathlib import Path, PurePosixPath   # Cross-platform path handling
```

All dependencies are Python standard library - no external packages required.

---

## Unity Package Format

### Archive Structure

A `.unitypackage` file is a **gzip-compressed tar archive** (`tar.gz`). This format was chosen by Unity for portability across platforms.

The archive can be opened with standard tools:

```bash
# View contents
tar -tzf MyPackage.unitypackage | head -20

# Extract (not recommended - use the module instead)
tar -xzf MyPackage.unitypackage -C output_dir/
```

However, the module uses Python's `tarfile` library for programmatic access:

```python
with tarfile.open(package_path, "r:gz") as tar:
    # Access tar members
    for member in tar.getmembers():
        print(member.name)
```

The `"r:gz"` mode specifies:
- `r` = read mode
- `gz` = gzip compression

### GUID Folder Layout

Inside the archive, each Unity asset is stored in a folder named with its 32-character GUID:

```
package.unitypackage (tar.gz)
    0730dae39bc73f34796280af9875ce14/
        asset          # The actual file content (e.g., .mat YAML)
        pathname       # Text file: "Assets/Materials/Crystal.mat"
        asset.meta     # Unity metadata (guid, importer settings)

    9b98a126c8d4d7a4baeb81b16e4f7b97/
        asset          # Texture binary data
        pathname       # Text file: "Assets/Textures/Ground_01.png"
        asset.meta     # Texture import settings

    a1b2c3d4e5f6789012345678901234ab/
        asset          # FBX binary data
        pathname       # Text file: "Assets/Models/SM_Prop_Tree_01.fbx"
        asset.meta     # FBX import settings
    ...
```

**Files within each GUID folder:**

| File | Purpose | Used by Converter |
|------|---------|-------------------|
| `asset` | The actual file content (binary or text) | Yes - for materials and textures |
| `pathname` | Unity project path as UTF-8 text | Yes - for all assets |
| `asset.meta` | Unity importer settings (YAML) | No - not needed |

### GUID Format Specification

Unity GUIDs are 32-character lowercase hexadecimal strings:

```
Example: 0730dae39bc73f34796280af9875ce14

Format:  [0-9a-f]{32}
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
         32 hex characters (128 bits)
```

The GUID is deterministically generated by Unity based on the asset's content and import settings. Key properties:

- **Stable**: Same asset always has the same GUID
- **Unique**: No two assets share a GUID within a project
- **Portable**: GUIDs persist across Unity versions and platforms

The module validates GUIDs with the `_is_valid_guid()` function:

```python
def _is_valid_guid(guid: str) -> bool:
    if len(guid) != 32:
        return False
    try:
        int(guid, 16)  # Try parsing as hexadecimal
        return True
    except ValueError:
        return False
```

---

## Module Constants

### TEXTURE_EXTENSIONS

```python
TEXTURE_EXTENSIONS = frozenset({".png", ".tga", ".jpg", ".jpeg"})
```

This constant defines the supported texture file formats. It's a `frozenset` for:
- O(1) membership testing
- Immutability (cannot be accidentally modified)
- Hashability (can be used in sets/dicts)

**Why these formats?**

Based on analysis of 29 Synty packs (~3,300 materials):

| Format | Usage | Notes |
|--------|-------|-------|
| PNG | 76% | Primary format, lossless |
| TGA | 23% | Secondary format, supports alpha |
| JPG/JPEG | <1% | Rare, lossy compression |

The module does not support PSD, EXR, DDS, or other formats because Synty packs don't use them for textures.

---

## GuidMap Class

The `GuidMap` dataclass is the primary output of the extraction process. It holds four GUID mappings needed for material conversion.

### Attributes

```python
@dataclass
class GuidMap:
    guid_to_pathname: dict[str, str] = field(default_factory=dict)
    guid_to_content: dict[str, bytes] = field(default_factory=dict)
    texture_guid_to_name: dict[str, str] = field(default_factory=dict)
    texture_guid_to_path: dict[str, Path] = field(default_factory=dict)
```

#### guid_to_pathname

**Type:** `dict[str, str]`

Maps every asset's GUID to its Unity project path.

```python
# Example entries:
{
    "0730dae39bc73f34796280af9875ce14": "Assets/Materials/Crystal.mat",
    "9b98a126c8d4d7a4baeb81b16e4f7b97": "Assets/Textures/Ground_01.png",
    "a1b2c3d4e5f6789012345678901234ab": "Assets/Models/SM_Prop_Tree.fbx",
}
```

**Purpose:**
- Identify asset type by file extension
- Get human-readable names for logging
- Determine material names from pathname

**Populated by:** `_build_guid_to_pathname()`

#### guid_to_content

**Type:** `dict[str, bytes]`

Maps material GUIDs to their raw `.mat` file content as bytes.

```python
# Example entry:
{
    "0730dae39bc73f34796280af9875ce14": b"%YAML 1.1\n%TAG !u! tag:unity3d...",
}
```

**Purpose:**
- Provide raw material YAML for parsing by `unity_parser.py`
- Only stores `.mat` files (not textures, models, etc.)

**Populated by:** `_extract_material_contents()`

#### texture_guid_to_name

**Type:** `dict[str, str]`

Maps texture GUIDs to their filename with extension.

```python
# Example entries:
{
    "9b98a126c8d4d7a4baeb81b16e4f7b97": "Ground_01.png",
    "abc123def456789012345678901234ab": "Leaf_Texture_01.tga",
}
```

**Purpose:**
- Resolve texture references in materials (materials store texture GUIDs, not filenames)
- Match texture names to SourceFiles for copying

**Populated by:** `_build_texture_guid_map()`

#### texture_guid_to_path

**Type:** `dict[str, Path]`

Maps texture GUIDs to temporary file paths where the actual texture content is extracted.

```python
# Example entries:
{
    "9b98a126c8d4d7a4baeb81b16e4f7b97": Path("/tmp/synty_textures_abc123/9b98a126...png"),
    "abc123def456789012345678901234ab": Path("/tmp/synty_textures_abc123/abc123de...tga"),
}
```

**Purpose:**
- Allow direct use of textures from the Unity package
- Fallback when textures aren't in SourceFiles

**Populated by:** `_extract_textures_to_temp()`

### Methods

#### __repr__

Returns a concise summary of the GuidMap contents:

```python
def __repr__(self) -> str:
    return (
        f"GuidMap(pathnames={len(self.guid_to_pathname)}, "
        f"contents={len(self.guid_to_content)}, "
        f"textures={len(self.texture_guid_to_name)}, "
        f"texture_paths={len(self.texture_guid_to_path)})"
    )
```

**Example output:**
```python
>>> guid_map = extract_unitypackage(Path("Nature.unitypackage"))
>>> print(guid_map)
GuidMap(pathnames=1523, contents=42, textures=156, texture_paths=156)
```

### Usage Examples

```python
from unity_package import extract_unitypackage
from pathlib import Path

# Extract the package
guid_map = extract_unitypackage(Path("PolygonNature.unitypackage"))

# Count assets by type
print(f"Total assets: {len(guid_map.guid_to_pathname)}")
print(f"Materials: {len(guid_map.guid_to_content)}")
print(f"Textures: {len(guid_map.texture_guid_to_name)}")

# Look up a specific material
material_guid = "0730dae39bc73f34796280af9875ce14"
pathname = guid_map.guid_to_pathname.get(material_guid)
content = guid_map.guid_to_content.get(material_guid)
print(f"Material path: {pathname}")
print(f"Content length: {len(content)} bytes")

# Resolve a texture reference from a material
texture_guid = "9b98a126c8d4d7a4baeb81b16e4f7b97"
texture_name = guid_map.texture_guid_to_name.get(texture_guid)
print(f"Texture: {texture_name}")  # e.g., "Ground_01.png"
```

---

## Main Entry Point: extract_unitypackage()

This is the primary function for extracting Unity packages. It orchestrates all the internal functions to build a complete `GuidMap`.

### Function Signature

```python
def extract_unitypackage(package_path: Path) -> GuidMap:
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `package_path` | `Path` | Path to the `.unitypackage` file |

### Return Value

Returns a `GuidMap` instance containing all four mappings (pathnames, contents, texture names, texture paths).

### Exceptions

| Exception | Condition |
|-----------|-----------|
| `FileNotFoundError` | Package file does not exist |
| `tarfile.ReadError` | File is not a valid tar archive or is corrupted |
| `tarfile.CompressionError` | Gzip decompression fails |

### Extraction Process

The function follows this sequence:

```
1. Validate package exists
   └─> FileNotFoundError if missing

2. Open tar.gz archive
   └─> tarfile.open(package_path, "r:gz")

3. Parse tar structure
   └─> _parse_tar_structure(tar)
   └─> Returns: {guid: {filename: content_bytes}}

4. Build GUID-to-pathname mapping
   └─> _build_guid_to_pathname(guid_data)
   └─> Returns: {guid: "Assets/Materials/Name.mat"}

5. Build texture GUID-to-name mapping
   └─> _build_texture_guid_map(guid_to_pathname)
   └─> Returns: {guid: "Texture_01.png"}

6. Extract material file contents
   └─> _extract_material_contents(guid_data, guid_to_pathname)
   └─> Returns: {guid: b"YAML content..."}

7. Extract textures to temp directory
   └─> _extract_textures_to_temp(guid_data, guid_to_pathname, temp_dir)
   └─> Returns: {guid: Path("/tmp/.../guid.png")}

8. Return GuidMap with all mappings
```

**Detailed code walkthrough:**

```python
def extract_unitypackage(package_path: Path) -> GuidMap:
    # Step 1: Validate package exists
    if not package_path.exists():
        raise FileNotFoundError(f"Unity package not found: {package_path}")

    logger.info("Extracting Unity package: %s", package_path.name)

    # Step 2-3: Open archive and parse structure
    with tarfile.open(package_path, "r:gz") as tar:
        guid_data = _parse_tar_structure(tar)

    logger.debug("Parsed %d GUID entries from package", len(guid_data))

    # Step 4: Build pathname mapping (all assets)
    guid_to_pathname = _build_guid_to_pathname(guid_data)
    logger.debug("Built pathname mapping for %d assets", len(guid_to_pathname))

    # Step 5: Build texture name mapping (textures only)
    texture_guid_to_name = _build_texture_guid_map(guid_to_pathname)
    logger.debug("Found %d texture assets", len(texture_guid_to_name))

    # Step 6: Extract raw .mat file contents
    guid_to_content = _extract_material_contents(guid_data, guid_to_pathname)
    logger.debug("Extracted content for %d material files", len(guid_to_content))

    # Step 7: Extract textures to temp files
    temp_dir = Path(tempfile.mkdtemp(prefix="synty_textures_"))
    texture_guid_to_path = _extract_textures_to_temp(
        guid_data, guid_to_pathname, temp_dir
    )
    logger.debug(
        "Extracted %d textures to temp directory: %s",
        len(texture_guid_to_path),
        temp_dir,
    )

    # Step 8: Return complete GuidMap
    return GuidMap(
        guid_to_pathname=guid_to_pathname,
        guid_to_content=guid_to_content,
        texture_guid_to_name=texture_guid_to_name,
        texture_guid_to_path=texture_guid_to_path,
    )
```

### Example Usage

```python
from pathlib import Path
from unity_package import extract_unitypackage, get_material_guids

# Basic extraction
package_path = Path("C:/SyntyComplete/PolygonNature/Nature.unitypackage")
guid_map = extract_unitypackage(package_path)

print(f"Extracted {len(guid_map.guid_to_pathname)} assets")
print(f"Found {len(guid_map.guid_to_content)} materials")
print(f"Found {len(guid_map.texture_guid_to_name)} textures")

# Iterate over materials
for guid in get_material_guids(guid_map):
    pathname = guid_map.guid_to_pathname[guid]
    content = guid_map.guid_to_content[guid]
    print(f"Material: {pathname} ({len(content)} bytes)")
```

---

## Internal Functions

These functions are prefixed with `_` to indicate they are internal implementation details. They are not part of the public API but are documented here for completeness.

### _parse_tar_structure()

```python
def _parse_tar_structure(tar: tarfile.TarFile) -> dict[str, dict[str, bytes]]:
```

**Purpose:** Parse the tar archive into a structured dictionary organizing files by GUID.

**Input:** Open `TarFile` object

**Output:** Nested dictionary: `{guid: {filename: content_bytes}}`

**Algorithm:**

```
For each member in tar:
    1. Skip if not a file (directories, symlinks)

    2. Parse path into parts
       - Expected format: "<guid>/<filename>"
       - Example: "0730dae39bc73f34796280af9875ce14/asset"

    3. Validate GUID format (32 hex chars)
       - Skip if invalid with debug log

    4. Extract file content from archive
       - Read all bytes into memory
       - Handle extraction errors gracefully

    5. Store in nested dictionary
       - guid_data[guid][filename] = content
```

**Code walkthrough:**

```python
def _parse_tar_structure(tar: tarfile.TarFile) -> dict[str, dict[str, bytes]]:
    guid_data: dict[str, dict[str, bytes]] = {}

    for member in tar.getmembers():
        # Skip directories
        if not member.isfile():
            continue

        # Parse path: expected format is "<guid>/<filename>"
        path = PurePosixPath(member.name)
        parts = path.parts

        if len(parts) < 2:
            logger.debug("Skipping malformed entry (too few parts): %s", member.name)
            continue

        # The first part is the GUID, second is the filename
        guid = parts[0]
        filename = parts[1]

        # Validate GUID format (should be 32 hex characters)
        if not _is_valid_guid(guid):
            logger.debug("Skipping entry with invalid GUID format: %s", guid)
            continue

        # Extract file content
        try:
            file_obj = tar.extractfile(member)
            if file_obj is None:
                logger.warning("Could not extract file: %s", member.name)
                continue

            content = file_obj.read()

            # Initialize dict for this GUID if needed
            if guid not in guid_data:
                guid_data[guid] = {}

            guid_data[guid][filename] = content

        except Exception as e:
            logger.warning("Error extracting %s: %s", member.name, e)
            continue

    return guid_data
```

**Why PurePosixPath?**

Unity packages always use forward slashes (`/`) regardless of the OS that created them. `PurePosixPath` correctly handles this:

```python
path = PurePosixPath("0730dae39bc73f34796280af9875ce14/asset")
path.parts  # ('0730dae39bc73f34796280af9875ce14', 'asset')
```

Using `Path` or `PureWindowsPath` could incorrectly handle paths on different platforms.

### _is_valid_guid()

```python
def _is_valid_guid(guid: str) -> bool:
```

**Purpose:** Validate that a string is a valid Unity GUID (32 hexadecimal characters).

**Input:** String to validate

**Output:** `True` if valid, `False` otherwise

**Algorithm:**

```
1. Check length is exactly 32
2. Try parsing as hexadecimal integer
3. Return True if both pass, False otherwise
```

**Code:**

```python
def _is_valid_guid(guid: str) -> bool:
    if len(guid) != 32:
        return False

    try:
        int(guid, 16)  # Parse as base-16 (hexadecimal)
        return True
    except ValueError:
        return False
```

**Examples:**

```python
_is_valid_guid("0730dae39bc73f34796280af9875ce14")  # True - valid
_is_valid_guid("invalid")                           # False - not hex
_is_valid_guid("0730dae39bc73f34")                  # False - too short
_is_valid_guid("0730dae39bc73f34796280af9875ce1g")  # False - 'g' not hex
```

### _build_guid_to_pathname()

```python
def _build_guid_to_pathname(
    guid_data: dict[str, dict[str, bytes]]
) -> dict[str, str]:
```

**Purpose:** Build mapping from GUID to Unity asset pathname by reading `pathname` files.

**Input:** Parsed tar structure from `_parse_tar_structure()`

**Output:** Dictionary mapping GUID to Unity path string

**Algorithm:**

```
For each GUID in parsed data:
    1. Check if "pathname" file exists
       - Skip if missing (with debug log)

    2. Decode pathname content as UTF-8
       - Handle decoding errors gracefully

    3. Clean the pathname
       - Strip whitespace
       - Remove null bytes (rare but possible)

    4. Add to mapping if non-empty
```

**Code:**

```python
def _build_guid_to_pathname(guid_data: dict[str, dict[str, bytes]]) -> dict[str, str]:
    guid_to_pathname: dict[str, str] = {}

    for guid, files in guid_data.items():
        if "pathname" not in files:
            logger.debug("GUID %s has no pathname file", guid)
            continue

        try:
            # Pathname file contains UTF-8 text
            pathname = files["pathname"].decode("utf-8").strip()

            # Remove any null bytes or unusual characters
            pathname = pathname.replace("\x00", "")

            if pathname:
                guid_to_pathname[guid] = pathname
            else:
                logger.debug("GUID %s has empty pathname", guid)

        except UnicodeDecodeError as e:
            logger.warning("Failed to decode pathname for GUID %s: %s", guid, e)
            continue

    return guid_to_pathname
```

**Example output:**

```python
{
    "0730dae39bc73f34796280af9875ce14": "Assets/Materials/Crystal.mat",
    "9b98a126c8d4d7a4baeb81b16e4f7b97": "Assets/Textures/Ground_01.png",
    "a1b2c3d4e5f6789012345678901234ab": "Assets/Models/SM_Prop_Tree.fbx",
    "b2c3d4e5f6789012345678901234abcd": "Assets/Prefabs/SM_Prop_Rock.prefab",
}
```

### _build_texture_guid_map()

```python
def _build_texture_guid_map(guid_to_pathname: dict[str, str]) -> dict[str, str]:
```

**Purpose:** Filter the GUID-to-pathname mapping to include only texture files, extracting just the filename.

**Input:** Complete GUID-to-pathname mapping

**Output:** Dictionary mapping texture GUID to filename (with extension)

**Algorithm:**

```
For each (guid, pathname) pair:
    1. Extract file extension (case-insensitive)
    2. Check if extension is in TEXTURE_EXTENSIONS
    3. If yes, extract filename and add to mapping
```

**Code:**

```python
def _build_texture_guid_map(guid_to_pathname: dict[str, str]) -> dict[str, str]:
    texture_guid_to_name: dict[str, str] = {}

    for guid, pathname in guid_to_pathname.items():
        # Get the extension (case-insensitive)
        path = PurePosixPath(pathname)
        ext = path.suffix.lower()

        if ext in TEXTURE_EXTENSIONS:
            # Store the full filename with extension
            texture_guid_to_name[guid] = path.name

    return texture_guid_to_name
```

**Why PurePosixPath.name?**

The `.name` property returns just the filename portion:

```python
path = PurePosixPath("Assets/Textures/Ground_01.png")
path.name    # "Ground_01.png" - filename with extension
path.stem    # "Ground_01" - filename without extension
path.suffix  # ".png" - extension with dot
```

**Example output:**

```python
{
    "9b98a126c8d4d7a4baeb81b16e4f7b97": "Ground_01.png",
    "abc123def456789012345678901234ab": "Leaf_Texture_01.tga",
    "def456789012345678901234abcdef01": "Sky_Background.jpg",
}
```

### _extract_material_contents()

```python
def _extract_material_contents(
    guid_data: dict[str, dict[str, bytes]],
    guid_to_pathname: dict[str, str],
) -> dict[str, bytes]:
```

**Purpose:** Extract raw content for `.mat` files only, for later parsing by `unity_parser.py`.

**Input:**
- Parsed tar structure
- GUID-to-pathname mapping (to identify `.mat` files)

**Output:** Dictionary mapping material GUID to raw bytes

**Algorithm:**

```
For each (guid, pathname) pair:
    1. Check if pathname ends with ".mat" (case-insensitive)
    2. If yes, get the files for this GUID
    3. Check if "asset" file exists
       - Warn and skip if missing
    4. Add raw content to mapping
```

**Code:**

```python
def _extract_material_contents(
    guid_data: dict[str, dict[str, bytes]], guid_to_pathname: dict[str, str]
) -> dict[str, bytes]:
    guid_to_content: dict[str, bytes] = {}

    for guid, pathname in guid_to_pathname.items():
        # Check if this is a .mat file
        if not pathname.lower().endswith(".mat"):
            continue

        # Get the files for this GUID
        files = guid_data.get(guid, {})

        if "asset" not in files:
            logger.warning("Material %s (GUID: %s) has no asset file", pathname, guid)
            continue

        guid_to_content[guid] = files["asset"]

    return guid_to_content
```

**Example content (bytes decoded for display):**

```yaml
%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!21 &2100000
Material:
  m_Name: Crystal_Mat_01
  m_Shader: {fileID: 4800000, guid: 5808064c5204e554c89f589a7059c558, type: 3}
  m_TexEnvs:
    - _Base_Albedo:
        m_Texture: {fileID: 2800000, guid: 9b98a126c8d4d7a4baeb81b16e4f7b97, type: 3}
  m_Floats:
    - _Opacity: 0.7
  m_Colors:
    - _Base_Color: {r: 0.5, g: 0.8, b: 1.0, a: 1}
```

### _extract_textures_to_temp()

```python
def _extract_textures_to_temp(
    guid_data: dict[str, dict[str, bytes]],
    guid_to_pathname: dict[str, str],
    temp_dir: Path,
) -> dict[str, Path]:
```

**Purpose:** Extract texture asset content to temporary files for direct use.

**Input:**
- Parsed tar structure
- GUID-to-pathname mapping
- Temporary directory path

**Output:** Dictionary mapping texture GUID to temp file path

**Algorithm:**

```
For each (guid, pathname) pair:
    1. Check if file extension is in TEXTURE_EXTENSIONS
    2. If yes, get the files for this GUID
    3. Check if "asset" file exists
    4. Write content to temp file: {temp_dir}/{guid}{ext}
    5. Add temp file path to mapping
```

**Code:**

```python
def _extract_textures_to_temp(
    guid_data: dict[str, dict[str, bytes]],
    guid_to_pathname: dict[str, str],
    temp_dir: Path,
) -> dict[str, Path]:
    texture_guid_to_path: dict[str, Path] = {}

    for guid, pathname in guid_to_pathname.items():
        ext = PurePosixPath(pathname).suffix.lower()
        if ext not in TEXTURE_EXTENSIONS:
            continue

        files = guid_data.get(guid, {})
        if "asset" not in files:
            continue

        # Write to temp file with original extension
        temp_file = temp_dir / f"{guid}{ext}"
        temp_file.write_bytes(files["asset"])
        texture_guid_to_path[guid] = temp_file

    return texture_guid_to_path
```

**Temp file naming:**

The temp file is named `{guid}{extension}` to ensure uniqueness:

```
/tmp/synty_textures_abc123/
    0730dae39bc73f34796280af9875ce14.png
    9b98a126c8d4d7a4baeb81b16e4f7b97.tga
    a1b2c3d4e5f6789012345678901234ab.jpg
```

**Note:** The temp directory is created with `tempfile.mkdtemp()` and is NOT automatically cleaned up. The calling code is responsible for cleanup if needed.

---

## Public Helper Functions

These functions provide convenient access to the `GuidMap` data.

### get_material_guids()

```python
def get_material_guids(guid_map: GuidMap) -> list[str]:
```

**Purpose:** Get all GUIDs that correspond to `.mat` files.

**Input:** `GuidMap` instance

**Output:** List of material GUIDs

**Code:**

```python
def get_material_guids(guid_map: GuidMap) -> list[str]:
    material_guids: list[str] = []

    for guid, pathname in guid_map.guid_to_pathname.items():
        if pathname.lower().endswith(".mat"):
            material_guids.append(guid)

    return material_guids
```

**Example usage:**

```python
guid_map = extract_unitypackage(Path("Nature.unitypackage"))
material_guids = get_material_guids(guid_map)

print(f"Found {len(material_guids)} materials")
for guid in material_guids:
    print(f"  {guid}: {guid_map.guid_to_pathname[guid]}")
```

**Why not just use guid_to_content.keys()?**

Both approaches work, but `get_material_guids()`:
- Is more explicit about intent
- Works even if content extraction failed for some materials
- Matches the pathname-based approach used elsewhere

### get_material_name()

```python
def get_material_name(guid_map: GuidMap, guid: str) -> str | None:
```

**Purpose:** Get the material name (filename without path or extension) for a given GUID.

**Input:**
- `GuidMap` instance
- Material GUID

**Output:** Material name or `None` if GUID not found

**Code:**

```python
def get_material_name(guid_map: GuidMap, guid: str) -> str | None:
    pathname = guid_map.guid_to_pathname.get(guid)
    if pathname is None:
        return None

    return PurePosixPath(pathname).stem
```

**Example:**

```python
# For pathname "Assets/Materials/PolygonNature_Ground_01.mat"
name = get_material_name(guid_map, "abc123...")
print(name)  # "PolygonNature_Ground_01"
```

### resolve_texture_guid()

```python
def resolve_texture_guid(guid_map: GuidMap, texture_guid: str) -> str | None:
```

**Purpose:** Resolve a texture GUID to its filename.

**Input:**
- `GuidMap` instance
- Texture GUID

**Output:** Texture filename with extension or `None` if not found

**Code:**

```python
def resolve_texture_guid(guid_map: GuidMap, texture_guid: str) -> str | None:
    return guid_map.texture_guid_to_name.get(texture_guid)
```

**Use case:** When parsing materials, texture references are stored as GUIDs:

```yaml
m_TexEnvs:
  - _Base_Albedo:
      m_Texture: {fileID: 2800000, guid: 9b98a126c8d4d7a4baeb81b16e4f7b97, type: 3}
```

To find the actual texture file:

```python
texture_guid = "9b98a126c8d4d7a4baeb81b16e4f7b97"
filename = resolve_texture_guid(guid_map, texture_guid)
print(filename)  # "Ground_01.png"
```

### print_guid_map_summary()

```python
def print_guid_map_summary(guid_map: GuidMap) -> None:
```

**Purpose:** Print a detailed summary of the GuidMap contents for debugging.

**Code:**

```python
def print_guid_map_summary(guid_map: GuidMap) -> None:
    print(f"\n{'='*60}")
    print("GUID Map Summary")
    print(f"{'='*60}")
    print(f"Total assets:     {len(guid_map.guid_to_pathname)}")
    print(f"Material files:   {len(guid_map.guid_to_content)}")
    print(f"Texture files:    {len(guid_map.texture_guid_to_name)}")
    print(f"Texture temps:    {len(guid_map.texture_guid_to_path)}")

    # Count by extension
    extensions: dict[str, int] = {}
    for pathname in guid_map.guid_to_pathname.values():
        ext = PurePosixPath(pathname).suffix.lower()
        extensions[ext] = extensions.get(ext, 0) + 1

    print(f"\nAssets by type:")
    for ext, count in sorted(extensions.items(), key=lambda x: -x[1]):
        print(f"  {ext or '(no ext)'}: {count}")

    print(f"{'='*60}\n")
```

**Example output:**

```
============================================================
GUID Map Summary
============================================================
Total assets:     1523
Material files:   245
Texture files:    89
Texture temps:    89

Assets by type:
  .prefab: 432
  .mat: 245
  .fbx: 156
  .png: 67
  .tga: 22
  .asset: 15
  .controller: 8
  ...
============================================================
```

---

## CLI Usage

The module can be run directly for testing and exploration:

```bash
python unity_package.py path/to/package.unitypackage
```

**CLI code (at module bottom):**

```python
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        print("Usage: python unity_package.py <path_to_unitypackage>")
        sys.exit(1)

    package_path = Path(sys.argv[1])

    try:
        guid_map = extract_unitypackage(package_path)
        print_guid_map_summary(guid_map)

        # Print first few materials
        material_guids = get_material_guids(guid_map)
        print(f"Found {len(material_guids)} materials:")
        for guid in material_guids[:10]:
            name = get_material_name(guid_map, guid)
            print(f"  - {name} ({guid})")

        if len(material_guids) > 10:
            print(f"  ... and {len(material_guids) - 10} more")

    except Exception as e:
        logger.error("Failed to extract package: %s", e)
        sys.exit(1)
```

**Example CLI session:**

```bash
$ python unity_package.py C:/SyntyComplete/PolygonNature/Nature.unitypackage

INFO: Extracting Unity package: Nature.unitypackage

============================================================
GUID Map Summary
============================================================
Total assets:     1523
Material files:   78
Texture files:    45
Texture temps:    45

Assets by type:
  .prefab: 523
  .fbx: 312
  .mat: 78
  .png: 34
  .tga: 11
  ...
============================================================

Found 78 materials:
  - PolygonNature_Ground_01 (0730dae39bc73f34796280af9875ce14)
  - PolygonNature_Tree_Bark (9b98a126c8d4d7a4baeb81b16e4f7b97)
  - PolygonNature_Leaf_01 (a1b2c3d4e5f6789012345678901234ab)
  ...
  ... and 68 more
```

---

## Integration with Pipeline

### Input from Previous Step

Step 2 (Create Output Directories) creates the output folder structure. Step 3 receives:
- Path to the `.unitypackage` file (validated in Step 1)

### Output to Next Step

Step 4 (Parse Unity Materials) uses the `GuidMap` to:
- Iterate over material GUIDs: `get_material_guids(guid_map)`
- Get material content: `guid_map.guid_to_content[guid]`
- Resolve texture references: `guid_map.texture_guid_to_name[texture_guid]`

**Integration in converter.py:**

```python
# Step 3: Extract Unity Package
from unity_package import extract_unitypackage, get_material_guids, get_material_name

guid_map = extract_unitypackage(package_path)
logger.info("Extracted %d assets from Unity package", len(guid_map.guid_to_pathname))

# Step 4: Parse Unity Materials
from unity_parser import parse_material_bytes

for guid in get_material_guids(guid_map):
    name = get_material_name(guid_map, guid)
    content = guid_map.guid_to_content[guid]

    unity_material = parse_material_bytes(content, guid_map)
    # ... continue with shader mapping
```

### Data Flow Diagram

```
                    ┌─────────────────────────┐
                    │    .unitypackage        │
                    │    (tar.gz archive)     │
                    └───────────┬─────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │ extract_unitypackage()│
                    └───────────┬───────────┘
                                │
            ┌───────────────────┼───────────────────┐
            ▼                   ▼                   ▼
    ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
    │guid_to_pathname│   │guid_to_content│   │texture_guid   │
    │               │   │               │   │_to_name       │
    │ All assets    │   │ .mat bytes    │   │ Texture names │
    └───────┬───────┘   └───────┬───────┘   └───────┬───────┘
            │                   │                   │
            ▼                   ▼                   ▼
    ┌─────────────────────────────────────────────────────┐
    │                     GuidMap                         │
    └─────────────────────────────────────────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │   Step 4: Parse       │
                    │   Unity Materials     │
                    └───────────────────────┘
```

---

## Error Handling

### FileNotFoundError

Raised when the package file doesn't exist:

```python
if not package_path.exists():
    raise FileNotFoundError(f"Unity package not found: {package_path}")
```

**Handling in caller:**

```python
try:
    guid_map = extract_unitypackage(package_path)
except FileNotFoundError as e:
    logger.error("Package not found: %s", e)
    sys.exit(1)
```

### tarfile.ReadError

Raised for invalid or corrupted archives:

```python
try:
    with tarfile.open(package_path, "r:gz") as tar:
        # ...
except tarfile.ReadError as e:
    logger.error("Invalid tar archive: %s", e)
```

### Graceful Degradation

The module handles non-fatal errors gracefully:

| Situation | Behavior |
|-----------|----------|
| GUID folder missing `pathname` file | Debug log, skip GUID |
| GUID folder missing `asset` file | Warning log, skip asset |
| Invalid GUID format | Debug log, skip entry |
| UTF-8 decode error in pathname | Warning log, skip GUID |
| Extraction error | Warning log, skip file |

This ensures that one corrupted asset doesn't break the entire extraction.

---

## Performance Considerations

### Memory Usage

The module loads all content into memory:
- `guid_to_content` holds all `.mat` file bytes (~1-10 KB each)
- `guid_data` temporarily holds all file content during parsing

For a large pack with 200+ materials, this is typically under 10 MB.

### Temp File Cleanup

The `_extract_textures_to_temp()` function creates a temp directory that persists:

```python
temp_dir = Path(tempfile.mkdtemp(prefix="synty_textures_"))
```

The converter should clean up this directory after processing is complete:

```python
import shutil

# After conversion completes
if guid_map.texture_guid_to_path:
    temp_dir = list(guid_map.texture_guid_to_path.values())[0].parent
    shutil.rmtree(temp_dir, ignore_errors=True)
```

### Streaming Alternative

For very large packages, a streaming approach could reduce memory:

```python
# Not implemented - for reference only
def stream_extract(package_path: Path) -> Iterator[tuple[str, bytes]]:
    with tarfile.open(package_path, "r:gz") as tar:
        for member in tar.getmembers():
            if member.isfile() and member.name.endswith("/asset"):
                yield guid, tar.extractfile(member).read()
```

Currently, Synty packages are small enough that memory isn't a concern.

---

## Notes for Doc Cleanup

After reviewing existing documentation, here are observations for future consolidation:

### Redundant Information

1. **`docs/api/unity_package.md`**: Contains overlapping information with this doc:
   - Unity package structure description (lines 31-65)
   - GuidMap class documentation (lines 69-120)
   - Function signatures and examples (lines 122-402)

   **Recommendation:** Keep `api/unity_package.md` as a quick reference with function signatures only. Move detailed explanations to this step doc.

2. **`docs/unity-reference.md`**: Contains Unity material structure info (lines 61-93) that overlaps with this doc's archive structure section.

   **Recommendation:** Keep material YAML format in `unity-reference.md`, archive format in this step doc.

### Outdated Information

1. **`docs/api/unity_package.md`** line 79:
   ```python
   texture_guid_to_name: dict[str, str] = field(default_factory=dict)
   ```
   Missing the `texture_guid_to_path` attribute added in the current version.

   **Fix:** Add `texture_guid_to_path` attribute to the API doc.

2. **`docs/api/unity_package.md`** line 99:
   ```python
   GuidMap(pathnames=1523, contents=245, textures=89)
   ```
   Should show `texture_paths` count too.

   **Fix:** Update `__repr__` example output.

3. **`docs/architecture.md`** line 121:
   ```python
   GuidMap = dict[str, str]        # guid -> pathname
   ```
   This is incorrect - `GuidMap` is a dataclass, not a dict.

   **Fix:** Update to show dataclass structure.

### Information to Incorporate

1. **From `docs/unity-reference.md`**: The texture handling section (lines 633-680) has useful context about texture discovery flow that could be referenced from here.

2. **From `docs/architecture.md`**: The "Why Regex Over YAML Parser" section (lines 292-320) explains why the converter uses regex instead of YAML parsing - this context is useful for understanding `unity_parser.py` but is also relevant here for understanding why we just read raw bytes.

### Missing Cross-References

Add links from:
- `docs/api/unity_package.md` -> this step doc for detailed explanations
- `docs/architecture.md` Step 3 section -> this step doc
- `docs/troubleshooting.md` -> this step doc for extraction errors

---

*Last Updated: 2026-01-31*
