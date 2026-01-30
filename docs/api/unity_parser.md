# Unity Parser API Reference

The `unity_parser` module extracts material data from Unity `.mat` files using regex-based parsing.

## Module Location

```
synty-converter-BLUE/unity_parser.py
```

## Overview

Unity `.mat` files are YAML 1.1 documents containing material definitions. This module parses these files to extract shader references, texture assignments, float parameters, and color values needed for Godot conversion.

### Why Regex Instead of YAML?

Unity uses **non-standard YAML** with custom `!u!` tags that break standard YAML parsers:

```yaml
%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!21 &2100000
Material:
  m_Name: MyMaterial
  m_Shader: {fileID: 4800000, guid: abc123..., type: 3}
```

The `!u!21` tag identifies the document type (21 = Material class ID in Unity), but this syntax is invalid in standard YAML parsers. Rather than preprocessing the file or using a custom YAML loader, this module uses carefully crafted regex patterns to extract the required data directly.

**Benefits of the regex approach:**
- No YAML library dependencies with Unity-specific workarounds
- Faster parsing for large packages (no full document tree construction)
- More resilient to Unity version variations
- Handles multi-document files (some `.mat` files contain multiple `---` sections)

---

## Classes

### TextureRef

Reference to a texture assigned to a material property.

```python
@dataclass
class TextureRef:
    guid: str
    scale: tuple[float, float] = (1.0, 1.0)
    offset: tuple[float, float] = (0.0, 0.0)
```

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `guid` | `str` | required | Unity GUID of the texture asset (32 hex characters) |
| `scale` | `tuple[float, float]` | `(1.0, 1.0)` | Texture tiling scale as (x, y) |
| `offset` | `tuple[float, float]` | `(0.0, 0.0)` | Texture UV offset as (x, y) |

#### Example

```python
tex_ref = TextureRef(
    guid="abc123def456789012345678abcdef01",
    scale=(2.0, 2.0),  # Tile 2x2
    offset=(0.5, 0.0)  # Offset half in U direction
)
```

---

### Color

RGBA color value from a material property.

```python
@dataclass
class Color:
    r: float
    g: float
    b: float
    a: float
```

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `r` | `float` | Red component (typically 0.0 to 1.0, can exceed for HDR) |
| `g` | `float` | Green component |
| `b` | `float` | Blue component |
| `a` | `float` | Alpha component |

#### Methods

##### as_tuple()

```python
def as_tuple(self) -> tuple[float, float, float, float]
```

Returns the color as an `(r, g, b, a)` tuple.

**Example:**
```python
color = Color(r=1.0, g=0.5, b=0.25, a=1.0)
rgba = color.as_tuple()  # (1.0, 0.5, 0.25, 1.0)
```

##### has_rgb()

```python
def has_rgb(self) -> bool
```

Returns `True` if any RGB component is non-zero. Used for detecting the Unity alpha=0 quirk where colors have visible RGB but alpha stored as 0.

**Example:**
```python
color = Color(r=0.5, g=0.5, b=0.5, a=0.0)
color.has_rgb()  # True - has RGB despite alpha=0
```

---

### UnityMaterial

Complete parsed material data from a Unity `.mat` file.

```python
@dataclass
class UnityMaterial:
    name: str
    shader_guid: str
    tex_envs: dict[str, TextureRef] = field(default_factory=dict)
    floats: dict[str, float] = field(default_factory=dict)
    colors: dict[str, Color] = field(default_factory=dict)
```

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Material name from `m_Name` field |
| `shader_guid` | `str` | GUID of the shader used (32 hex characters, lowercase) |
| `tex_envs` | `dict[str, TextureRef]` | Texture references keyed by Unity property name (e.g., `"_Albedo_Map"`) |
| `floats` | `dict[str, float]` | Float properties keyed by Unity property name (e.g., `"_Smoothness"`) |
| `colors` | `dict[str, Color]` | Color properties keyed by Unity property name (e.g., `"_Color"`) |

#### Example

```python
material = UnityMaterial(
    name="Tree_Leaves_Mat",
    shader_guid="9b98a126c8d4d7a4baeb81b16e4f7b97",
    tex_envs={
        "_Leaf_Texture": TextureRef(guid="abc123..."),
        "_Leaf_Normal": TextureRef(guid="def456..."),
    },
    floats={
        "_Smoothness": 0.1,
        "_Alpha_Clip_Threshold": 0.5,
    },
    colors={
        "_Color": Color(r=1.0, g=1.0, b=1.0, a=1.0),
    }
)
```

---

## Functions

### parse_material

Parse a Unity `.mat` file from string content.

```python
def parse_material(content: str) -> UnityMaterial
```

This is the **main entry point** for parsing Unity materials.

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `content` | `str` | Full content of a `.mat` file as a string |

#### Returns

`UnityMaterial` with all extracted properties.

#### Example

```python
from unity_parser import parse_material

with open("MyMaterial.mat", "r", encoding="utf-8") as f:
    content = f.read()

material = parse_material(content)

print(f"Material: {material.name}")
print(f"Shader GUID: {material.shader_guid}")
print(f"Textures: {len(material.tex_envs)}")
print(f"Floats: {material.floats}")
```

---

### parse_material_bytes

Parse a Unity `.mat` file from raw bytes.

```python
def parse_material_bytes(content: bytes, encoding: str = "utf-8") -> UnityMaterial
```

Convenience wrapper for parsing material data extracted from Unity packages (which provide raw bytes).

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `content` | `bytes` | required | Raw bytes of the `.mat` file |
| `encoding` | `str` | `"utf-8"` | Text encoding to use for decoding |

#### Returns

`UnityMaterial` with all extracted properties.

#### Raises

- `UnicodeDecodeError` - If content cannot be decoded with the given encoding

#### Example

```python
from unity_parser import parse_material_bytes
from unity_package import extract_unitypackage

# Extract package and get material content
guid_map = extract_unitypackage(Path("package.unitypackage"))
material_content = guid_map.guid_to_content["abc123..."]

# Parse from bytes
material = parse_material_bytes(material_content)
print(f"Parsed: {material.name}")
```

---

## Regex Patterns

The module uses these compiled regex patterns to extract data from Unity YAML:

### _NAME_PATTERN

Extracts the material name from `m_Name` field.

```python
_NAME_PATTERN = re.compile(r"m_Name:\s*(.+?)\s*(?:\n|$)")
```

**Matches:**
```yaml
m_Name: Tree_Bark_Material
```
**Captures:** `Tree_Bark_Material`

---

### _SHADER_GUID_PATTERN

Extracts the shader GUID from `m_Shader` field.

```python
_SHADER_GUID_PATTERN = re.compile(
    r"m_Shader:\s*\{[^}]*guid:\s*([a-f0-9]+)",
    re.IGNORECASE,
)
```

**Matches:**
```yaml
m_Shader: {fileID: 4800000, guid: 9b98a126c8d4d7a4baeb81b16e4f7b97, type: 3}
```
**Captures:** `9b98a126c8d4d7a4baeb81b16e4f7b97`

---

### _FLOAT_PATTERN

Extracts float properties from `m_Floats` section.

```python
_FLOAT_PATTERN = re.compile(
    r"^\s*-\s+(_\w+):\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*$",
    re.MULTILINE,
)
```

**Matches:**
```yaml
- _Smoothness: 0.5
- _Metallic: 0
- _AlphaThreshold: 1.5e-05
```
**Captures:** Property name and value (handles scientific notation)

---

### _COLOR_PATTERN

Extracts color properties from `m_Colors` section.

```python
_COLOR_PATTERN = re.compile(
    r"^\s*-\s+(_\w+):\s*\{r:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?),\s*"
    r"g:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?),\s*"
    r"b:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?),\s*"
    r"a:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*\}",
    re.MULTILINE,
)
```

**Matches:**
```yaml
- _Color: {r: 1, g: 0.5, b: 0.25, a: 1}
- _EmissionColor: {r: 2.5, g: 1.2, b: 0, a: 1}
```
**Captures:** Property name and all four RGBA components

---

### _TEX_PROPERTY_PATTERN

Identifies texture property entries in `m_TexEnvs` section.

```python
_TEX_PROPERTY_PATTERN = re.compile(r"^\s*-\s+(_\w+):\s*$", re.MULTILINE)
```

**Matches:**
```yaml
- _Albedo_Map:
```
**Captures:** Property name (`_Albedo_Map`)

---

### _TEX_GUID_PATTERN

Extracts texture GUID from `m_Texture` field.

```python
_TEX_GUID_PATTERN = re.compile(
    r"m_Texture:\s*\{[^}]*guid:\s*([a-f0-9]+)",
    re.IGNORECASE,
)
```

**Matches:**
```yaml
m_Texture: {fileID: 2800000, guid: abc123def456789012345678abcdef01, type: 3}
```
**Captures:** `abc123def456789012345678abcdef01`

---

### _TEX_SCALE_PATTERN

Extracts texture scale from `m_Scale` field.

```python
_TEX_SCALE_PATTERN = re.compile(
    r"m_Scale:\s*\{x:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?),\s*"
    r"y:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*\}",
)
```

**Matches:**
```yaml
m_Scale: {x: 2, y: 2}
```
**Captures:** x and y scale values

---

### _TEX_OFFSET_PATTERN

Extracts texture offset from `m_Offset` field.

```python
_TEX_OFFSET_PATTERN = re.compile(
    r"m_Offset:\s*\{x:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?),\s*"
    r"y:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*\}",
)
```

**Matches:**
```yaml
m_Offset: {x: 0.5, y: 0}
```
**Captures:** x and y offset values

---

## Unity Material Structure

For reference, here is the structure of a Unity `.mat` file:

```yaml
%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!21 &2100000
Material:
  serializedVersion: 8
  m_Name: Tree_Bark_Material
  m_Shader: {fileID: 4800000, guid: 9b98a126c8d4d7a4baeb81b16e4f7b97, type: 3}
  m_Parent: {fileID: 0}
  m_ModifiedSerializedProperties: 0
  m_ValidKeywords: []
  m_InvalidKeywords: []
  m_LightmapFlags: 4
  m_EnableInstancingVariants: 0
  m_DoubleSidedGI: 0
  m_CustomRenderQueue: -1
  stringTagMap: {}
  disabledShaderPasses: []
  m_LockedProperties:
  m_SavedProperties:
    serializedVersion: 3
    m_TexEnvs:
    - _Trunk_Texture:
        m_Texture: {fileID: 2800000, guid: abc123..., type: 3}
        m_Scale: {x: 1, y: 1}
        m_Offset: {x: 0, y: 0}
    - _Trunk_Normal:
        m_Texture: {fileID: 2800000, guid: def456..., type: 3}
        m_Scale: {x: 1, y: 1}
        m_Offset: {x: 0, y: 0}
    m_Ints: []
    m_Floats:
    - _Smoothness: 0.15
    - _Metallic: 0
    - _Alpha_Clip_Threshold: 0.5
    m_Colors:
    - _Color: {r: 1, g: 1, b: 1, a: 1}
    - _Trunk_Base_Color: {r: 0.8, g: 0.6, b: 0.4, a: 1}
```

---

## Complete Example

```python
#!/usr/bin/env python3
"""Example: Parse a Unity material file and display its contents."""

from pathlib import Path
from unity_parser import parse_material

# Read the .mat file
mat_path = Path("C:/SyntyAssets/Materials/Tree_Bark.mat")
content = mat_path.read_text(encoding="utf-8")

# Parse it
material = parse_material(content)

# Display results
print(f"Material: {material.name}")
print(f"Shader GUID: {material.shader_guid}")

print(f"\nTextures ({len(material.tex_envs)}):")
for prop_name, tex_ref in material.tex_envs.items():
    print(f"  {prop_name}:")
    print(f"    GUID: {tex_ref.guid}")
    print(f"    Scale: {tex_ref.scale}")
    print(f"    Offset: {tex_ref.offset}")

print(f"\nFloats ({len(material.floats)}):")
for prop_name, value in material.floats.items():
    print(f"  {prop_name}: {value}")

print(f"\nColors ({len(material.colors)}):")
for prop_name, color in material.colors.items():
    print(f"  {prop_name}: r={color.r:.3f}, g={color.g:.3f}, b={color.b:.3f}, a={color.a:.3f}")
```

**Output:**
```
Material: Tree_Bark
Shader GUID: 9b98a126c8d4d7a4baeb81b16e4f7b97

Textures (2):
  _Trunk_Texture:
    GUID: abc123def456789012345678abcdef01
    Scale: (1.0, 1.0)
    Offset: (0.0, 0.0)
  _Trunk_Normal:
    GUID: def456789012345678abcdef01234567
    Scale: (1.0, 1.0)
    Offset: (0.0, 0.0)

Floats (3):
  _Smoothness: 0.15
  _Metallic: 0.0
  _Alpha_Clip_Threshold: 0.5

Colors (2):
  _Color: r=1.000, g=1.000, b=1.000, a=1.000
  _Trunk_Base_Color: r=0.800, g=0.600, b=0.400, a=1.000
```

---

## CLI Usage

The module includes a CLI for testing:

```bash
python unity_parser.py path/to/material.mat
```

This displays parsed material data in a formatted output, useful for debugging and verification.
