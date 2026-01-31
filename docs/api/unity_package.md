# Unity Package Module API

The `unity_package` module handles extraction of Unity `.unitypackage` files and builds GUID mappings for materials and textures.

> **For detailed implementation:** See [Step 3: Extract Unity Package](../steps/03-extract-unity-package.md)

## Module Location

```
synty-converter/unity_package.py
```

## Usage

```python
from unity_package import extract_unitypackage, get_material_guids, get_material_name
from pathlib import Path

# Extract the package
guid_map = extract_unitypackage(Path("package.unitypackage"))

# Get all material GUIDs
material_guids = get_material_guids(guid_map)

# Get material name by GUID
for guid in material_guids:
    name = get_material_name(guid_map, guid)
    print(f"{name}: {guid}")
```

---

## Unity Package Structure

A `.unitypackage` file is a **gzip-compressed tar archive** where each asset is stored in a folder named with its GUID.

```
package.unitypackage (tar.gz)
    <guid1>/
        asset          # The actual file content (e.g., .mat, .png)
        pathname       # Text file with Unity asset path
        asset.meta     # Unity metadata file
    <guid2>/
        asset
        pathname
        asset.meta
    ...
```

### Example Entry

For a material at `Assets/Materials/Crystal.mat`:

```
a1b2c3d4e5f6789012345678901234ab/
    asset          # YAML content of Crystal.mat
    pathname       # Contains: "Assets/Materials/Crystal.mat"
    asset.meta     # Unity metadata (not used by converter)
```

### GUID Format

Unity GUIDs are 32-character hexadecimal strings:
- Example: `a1b2c3d4e5f6789012345678901234ab`
- Used internally to reference assets without relying on file paths

---

## Classes

### GuidMap

Container for GUID mappings extracted from a Unity package.

```python
@dataclass
class GuidMap:
    guid_to_pathname: dict[str, str] = field(default_factory=dict)
    guid_to_content: dict[str, bytes] = field(default_factory=dict)
    texture_guid_to_name: dict[str, str] = field(default_factory=dict)
    texture_guid_to_path: dict[str, Path] = field(default_factory=dict)
```

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `guid_to_pathname` | `dict[str, str]` | Maps GUID to Unity asset path (e.g., `"Assets/Materials/Crystal.mat"`) |
| `guid_to_content` | `dict[str, bytes]` | Maps GUID to raw file content (bytes) for `.mat` files only |
| `texture_guid_to_name` | `dict[str, str]` | Maps texture GUID to texture filename (with extension) |
| `texture_guid_to_path` | `dict[str, Path]` | Maps texture GUID to temp file Path (for texture extraction from package) |

#### Methods

##### `__repr__`

Returns a summary string of the GuidMap contents.

```python
>>> guid_map = extract_unitypackage(Path("package.unitypackage"))
>>> print(guid_map)
GuidMap(pathnames=1523, contents=245, textures=89, texture_paths=89)
```

#### Example Usage

```python
from unity_package import extract_unitypackage
from pathlib import Path

guid_map = extract_unitypackage(Path("package.unitypackage"))

# Access pathname for a GUID
pathname = guid_map.guid_to_pathname.get("a1b2c3d4...")
# Returns: "Assets/Materials/Crystal.mat"

# Access raw .mat file content
content = guid_map.guid_to_content.get("a1b2c3d4...")
# Returns: bytes (YAML content of the .mat file)

# Resolve a texture GUID to filename
texture_name = guid_map.texture_guid_to_name.get("b2c3d4e5...")
# Returns: "Crystal_Albedo.png"
```

---

## Functions

### extract_unitypackage

Extract a Unity package and build GUID mappings. This is the main entry point for Unity package extraction.

```python
def extract_unitypackage(package_path: Path) -> GuidMap
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `package_path` | `Path` | Path to the `.unitypackage` file |

#### Returns

`GuidMap` containing all extracted GUID mappings.

#### Raises

| Exception | Condition |
|-----------|-----------|
| `FileNotFoundError` | If the package file doesn't exist |
| `tarfile.ReadError` | If the file is not a valid tar/gzip archive |

#### Example

```python
from unity_package import extract_unitypackage
from pathlib import Path

try:
    guid_map = extract_unitypackage(Path("Nature.unitypackage"))
    print(f"Extracted {len(guid_map.guid_to_pathname)} assets")
    print(f"Found {len(guid_map.guid_to_content)} materials")
    print(f"Found {len(guid_map.texture_guid_to_name)} textures")
except FileNotFoundError:
    print("Package not found!")
except tarfile.ReadError:
    print("Invalid package format!")
```

---

### get_material_guids

Get all GUIDs that correspond to `.mat` files.

```python
def get_material_guids(guid_map: GuidMap) -> list[str]
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `guid_map` | `GuidMap` | GuidMap instance from `extract_unitypackage()` |

#### Returns

List of GUIDs for material files.

#### Example

```python
from unity_package import extract_unitypackage, get_material_guids

guid_map = extract_unitypackage(Path("package.unitypackage"))
material_guids = get_material_guids(guid_map)

print(f"Found {len(material_guids)} materials:")
for guid in material_guids[:5]:
    pathname = guid_map.guid_to_pathname[guid]
    print(f"  {guid}: {pathname}")
```

---

### get_material_name

Get the material name (without path or extension) for a given GUID.

```python
def get_material_name(guid_map: GuidMap, guid: str) -> str | None
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `guid_map` | `GuidMap` | GuidMap instance |
| `guid` | `str` | Material GUID |

#### Returns

Material name (stem only) or `None` if GUID not found.

#### Example

```python
from unity_package import extract_unitypackage, get_material_guids, get_material_name

guid_map = extract_unitypackage(Path("package.unitypackage"))

for guid in get_material_guids(guid_map):
    name = get_material_name(guid_map, guid)
    print(f"Material: {name}")
    # Output: "Material: Crystal" (not "Assets/Materials/Crystal.mat")
```

---

### resolve_texture_guid

Resolve a texture GUID to its filename.

```python
def resolve_texture_guid(guid_map: GuidMap, texture_guid: str) -> str | None
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `guid_map` | `GuidMap` | GuidMap instance |
| `texture_guid` | `str` | GUID of the texture |

#### Returns

Texture filename (with extension) or `None` if not found.

#### Example

```python
from unity_package import extract_unitypackage, resolve_texture_guid

guid_map = extract_unitypackage(Path("package.unitypackage"))

# In a .mat file, textures are referenced by GUID
texture_guid = "b2c3d4e5f6789012345678901234abcd"
filename = resolve_texture_guid(guid_map, texture_guid)
print(f"Texture: {filename}")
# Output: "Texture: Crystal_Albedo.png"
```

---

### print_guid_map_summary

Print a summary of the GUID map contents. Useful for debugging.

```python
def print_guid_map_summary(guid_map: GuidMap) -> None
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `guid_map` | `GuidMap` | GuidMap instance |

#### Output Example

```
============================================================
GUID Map Summary
============================================================
Total assets:     1523
Material files:   245
Texture files:    89

Assets by type:
  .mat: 245
  .png: 67
  .tga: 22
  .fbx: 156
  .prefab: 432
  ...
============================================================
```

---

## Constants

### TEXTURE_EXTENSIONS

Supported texture file extensions (case-insensitive).

```python
TEXTURE_EXTENSIONS = frozenset({".png", ".tga", ".jpg", ".jpeg"})
```

Used to identify which assets in the package are textures when building the `texture_guid_to_name` mapping.

---

## Internal Functions

These functions are used internally by `extract_unitypackage()` but are not part of the public API.

| Function | Purpose |
|----------|---------|
| `_parse_tar_structure()` | Parse tar archive into `{guid: {filename: content}}` |
| `_is_valid_guid()` | Validate GUID format (32 hex characters) |
| `_build_guid_to_pathname()` | Build GUID to pathname mapping from parsed tar |
| `_build_texture_guid_map()` | Filter for texture files and build texture mapping |
| `_extract_material_contents()` | Extract raw content for `.mat` files |

---

## Complete Example

```python
#!/usr/bin/env python3
"""Example: Explore contents of a Unity package."""

import logging
from pathlib import Path
from unity_package import (
    extract_unitypackage,
    get_material_guids,
    get_material_name,
    resolve_texture_guid,
    print_guid_map_summary
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Extract the package
package_path = Path("C:/SyntyComplete/PolygonNature/Nature.unitypackage")
guid_map = extract_unitypackage(package_path)

# Print summary
print_guid_map_summary(guid_map)

# List all materials
print("\nMaterials found:")
material_guids = get_material_guids(guid_map)
for guid in material_guids[:10]:
    name = get_material_name(guid_map, guid)
    pathname = guid_map.guid_to_pathname[guid]
    print(f"  {name}: {pathname}")

if len(material_guids) > 10:
    print(f"  ... and {len(material_guids) - 10} more")

# List all textures
print("\nTextures found:")
for guid, filename in list(guid_map.texture_guid_to_name.items())[:10]:
    print(f"  {guid[:8]}...: {filename}")

if len(guid_map.texture_guid_to_name) > 10:
    print(f"  ... and {len(guid_map.texture_guid_to_name) - 10} more")

# Access raw material content
print("\nFirst material content (first 200 bytes):")
first_guid = material_guids[0]
content = guid_map.guid_to_content[first_guid]
print(content[:200].decode('utf-8', errors='replace'))
```

---

## CLI Usage

The module can be run directly for testing:

```bash
python unity_package.py path/to/package.unitypackage
```

This will:
1. Extract the package
2. Print a summary of contents
3. List the first 10 materials found
