# Step 4: Parse Materials

This document provides comprehensive documentation for the `unity_parser.py` module, which parses Unity `.mat` files to extract material data for Godot conversion.

**Module Location:** `synty-converter/unity_parser.py` (659 lines)

**Related Documentation:**
- [Architecture](../architecture.md) - Overall pipeline context
- [Unity Reference](../unity-reference.md) - Unity material structure and property mappings
- [API: unity_parser](../api/unity_parser.md) - Quick API reference

---

## Table of Contents

- [Overview](#overview)
- [Unity .mat File Format](#unity-mat-file-format)
  - [YAML 1.1 with Custom Tags](#yaml-11-with-custom-tags)
  - [Document Structure](#document-structure)
  - [Why Regex Instead of YAML Parsing](#why-regex-instead-of-yaml-parsing)
- [Data Classes](#data-classes)
  - [TextureRef](#textureref)
  - [Color](#color)
  - [UnityMaterial](#unitymaterial)
- [Regex Patterns](#regex-patterns)
  - [_NAME_PATTERN](#_name_pattern)
  - [_SHADER_GUID_PATTERN](#_shader_guid_pattern)
  - [_FLOAT_PATTERN](#_float_pattern)
  - [_COLOR_PATTERN](#_color_pattern)
  - [_TEX_PROPERTY_PATTERN](#_tex_property_pattern)
  - [_TEX_GUID_PATTERN](#_tex_guid_pattern)
  - [_TEX_SCALE_PATTERN](#_tex_scale_pattern)
  - [_TEX_OFFSET_PATTERN](#_tex_offset_pattern)
- [Internal Helper Functions](#internal-helper-functions)
  - [_extract_material_section()](#_extract_material_section)
  - [_extract_material_name()](#_extract_material_name)
  - [_extract_shader_guid()](#_extract_shader_guid)
  - [_parse_floats()](#_parse_floats)
  - [_parse_colors()](#_parse_colors)
  - [_parse_tex_envs()](#_parse_tex_envs)
- [Public API Functions](#public-api-functions)
  - [parse_material()](#parse_material)
  - [parse_material_bytes()](#parse_material_bytes)
- [CLI Testing Interface](#cli-testing-interface)
- [Error Handling](#error-handling)
- [Unity YAML Quirks Handled](#unity-yaml-quirks-handled)
- [Complete Parsing Flow](#complete-parsing-flow)
- [Code Examples](#code-examples)
- [Notes for Doc Cleanup](#notes-for-doc-cleanup)

---

## Overview

The `unity_parser.py` module is Step 4 in the 12-step conversion pipeline. It receives raw bytes of Unity `.mat` files (extracted in Step 3 by `unity_package.py`) and produces structured `UnityMaterial` objects that Step 5 (`shader_mapping.py`) uses to detect shaders and map properties.

### Key Responsibilities

1. **Decode Unity YAML** - Handle the non-standard YAML 1.1 format with `!u!` tags
2. **Extract material name** - Parse `m_Name` field
3. **Extract shader reference** - Parse `m_Shader.guid` for shader detection
4. **Extract texture references** - Parse `m_TexEnvs` section with GUIDs, scale, and offset
5. **Extract float properties** - Parse `m_Floats` section (smoothness, metallic, cutoff, etc.)
6. **Extract color properties** - Parse `m_Colors` section with HDR support

### Module Dependencies

```
unity_parser.py
    └── Standard library only:
        ├── re (regex patterns)
        ├── logging (debug/warning output)
        └── dataclasses (data structures)
```

No external packages required. This is intentional for portability and to avoid dependency conflicts.

---

## Unity .mat File Format

### YAML 1.1 with Custom Tags

Unity material files use YAML 1.1 with Unity-specific custom tags that are **not valid standard YAML**:

```yaml
%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!21 &2100000
Material:
  serializedVersion: 8
  m_Name: PolygonNature_Ground_01
  m_Shader: {fileID: 4800000, guid: 0730dae39bc73f34796280af9875ce14, type: 3}
  ...
```

**Line-by-line breakdown:**

| Line | Meaning |
|------|---------|
| `%YAML 1.1` | YAML version declaration |
| `%TAG !u! tag:unity3d.com,2011:` | Custom tag shorthand declaration - `!u!` is shorthand for Unity's tag namespace |
| `--- !u!21 &2100000` | Document separator with tag. `21` is Unity's class ID for Material. `&2100000` is the local file ID anchor |
| `Material:` | Root mapping key |

### Document Structure

A complete Unity material file has this structure:

```yaml
%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!21 &2100000
Material:
  serializedVersion: 8
  m_Name: MaterialName
  m_Shader: {fileID: 4800000, guid: <32-char-hex>, type: 3}
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
    - _PropertyName:
        m_Texture: {fileID: 2800000, guid: <32-char-hex>, type: 3}
        m_Scale: {x: 1, y: 1}
        m_Offset: {x: 0, y: 0}
    m_Ints: []
    m_Floats:
    - _PropertyName: 0.5
    m_Colors:
    - _PropertyName: {r: 1, g: 0.5, b: 0.25, a: 1}
```

**Key sections for parsing:**

| Section | Purpose | Parsed By |
|---------|---------|-----------|
| `m_Name` | Material name | `_extract_material_name()` |
| `m_Shader` | Shader reference with GUID | `_extract_shader_guid()` |
| `m_TexEnvs` | Texture assignments | `_parse_tex_envs()` |
| `m_Floats` | Float properties | `_parse_floats()` |
| `m_Colors` | Color properties | `_parse_colors()` |

### Why Regex Instead of YAML Parsing

Standard YAML parsers (PyYAML, ruamel.yaml) fail on Unity's custom `!u!` tags:

```python
# This fails:
import yaml
yaml.safe_load(unity_mat_content)
# Error: could not determine a constructor for the tag '!u!21'
```

**Options considered:**

| Approach | Pros | Cons |
|----------|------|------|
| Register custom tag handlers | Clean YAML parsing | Requires external library, complex setup |
| Preprocess to remove tags | Uses standard YAML | Risk of breaking edge cases, slower |
| **Regex extraction** | Fast, no dependencies, precise | More code, must handle variations |

**Benefits of regex approach (chosen):**

1. **No external dependencies** - Pure Python standard library
2. **~10x faster** - No full document tree construction
3. **Resilient** - Handles Unity version variations gracefully
4. **Precise** - Extracts exactly what we need, ignores rest
5. **Handles multi-document files** - Some `.mat` files have multiple `---` sections

---

## Data Classes

The module defines three dataclasses for structured material data.

### TextureRef

**Purpose:** Represents a texture assignment in Unity's `m_TexEnvs` section.

**Definition (lines 53-79):**

```python
@dataclass
class TextureRef:
    """Reference to a texture in Unity's m_TexEnvs section."""
    guid: str
    scale: tuple[float, float] = (1.0, 1.0)
    offset: tuple[float, float] = (0.0, 0.0)
```

**Attributes:**

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `guid` | `str` | (required) | Unity GUID of the texture asset. 32 lowercase hex characters. Used to look up texture filename via GuidMap. |
| `scale` | `tuple[float, float]` | `(1.0, 1.0)` | UV tiling scale as (x, y). Values > 1.0 tile the texture, values < 1.0 stretch it. |
| `offset` | `tuple[float, float]` | `(0.0, 0.0)` | UV offset as (x, y). Shifts texture position in UV space. |

**Unity YAML source:**

```yaml
- _Albedo_Map:
    m_Texture: {fileID: 2800000, guid: 0730dae39bc73f34796280af9875ce14, type: 3}
    m_Scale: {x: 2, y: 2}
    m_Offset: {x: 0.5, y: 0}
```

**Example usage:**

```python
tex_ref = TextureRef(
    guid="0730dae39bc73f34796280af9875ce14",
    scale=(2.0, 2.0),  # Tile 2x2
    offset=(0.5, 0.0)  # Shift right by half
)
print(tex_ref.guid)    # 0730dae39bc73f34796280af9875ce14
print(tex_ref.scale)   # (2.0, 2.0)
print(tex_ref.offset)  # (0.5, 0.0)
```

---

### Color

**Purpose:** Represents an RGBA color from Unity's `m_Colors` section with HDR support.

**Definition (lines 82-129):**

```python
@dataclass
class Color:
    """RGBA color from Unity's m_Colors section."""
    r: float
    g: float
    b: float
    a: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        """Return color as (r, g, b, a) tuple."""
        return (self.r, self.g, self.b, self.a)

    def has_rgb(self) -> bool:
        """Check if color has any non-zero RGB values."""
        return self.r != 0.0 or self.g != 0.0 or self.b != 0.0
```

**Attributes:**

| Attribute | Type | Range | Description |
|-----------|------|-------|-------------|
| `r` | `float` | Typically 0.0-1.0, can exceed for HDR | Red component |
| `g` | `float` | Typically 0.0-1.0, can exceed for HDR | Green component |
| `b` | `float` | Typically 0.0-1.0, can exceed for HDR | Blue component |
| `a` | `float` | 0.0 (transparent) to 1.0 (opaque) | Alpha component |

**Methods:**

| Method | Returns | Purpose |
|--------|---------|---------|
| `as_tuple()` | `tuple[float, float, float, float]` | Convert to (r, g, b, a) tuple for Godot |
| `has_rgb()` | `bool` | Check if any RGB is non-zero (for alpha=0 quirk detection) |

**HDR Support:**

Unity stores HDR colors (for emission, glow effects) with values exceeding 1.0:

```yaml
- _EmissionColor: {r: 2.5, g: 1.0, b: 0, a: 1}
```

The `Color` class preserves these values without clamping.

**Unity Alpha=0 Quirk:**

Unity often stores visible colors with `alpha=0`. The `has_rgb()` method helps detect this:

```python
color = Color(r=0.5, g=0.5, b=0.5, a=0.0)
if color.has_rgb() and color.a == 0.0:
    # This is the alpha=0 quirk - color should be visible
    color.a = 1.0
```

**Example usage:**

```python
# Standard color
color = Color(r=1.0, g=0.5, b=0.25, a=1.0)
print(color.as_tuple())  # (1.0, 0.5, 0.25, 1.0)

# HDR emission
emission = Color(r=2.5, g=1.0, b=0.0, a=1.0)
print(emission.has_rgb())  # True
print(emission.r)          # 2.5 (preserved)

# Alpha=0 quirk detection
quirky = Color(r=0.8, g=0.6, b=0.4, a=0.0)
print(quirky.has_rgb())  # True - has RGB despite alpha=0
```

---

### UnityMaterial

**Purpose:** Complete parsed material data - the main output of this module.

**Definition (lines 132-169):**

```python
@dataclass
class UnityMaterial:
    """Parsed Unity material data."""
    name: str
    shader_guid: str
    tex_envs: dict[str, TextureRef] = field(default_factory=dict)
    floats: dict[str, float] = field(default_factory=dict)
    colors: dict[str, Color] = field(default_factory=dict)
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Material name from `m_Name` field. Used for output filename and logging. |
| `shader_guid` | `str` | GUID of the Unity shader (32 hex chars, lowercase). Used by `shader_mapping.py` to detect shader type. |
| `tex_envs` | `dict[str, TextureRef]` | Texture references keyed by Unity property name (e.g., `"_Albedo_Map"`). |
| `floats` | `dict[str, float]` | Float properties keyed by Unity property name (e.g., `"_Smoothness"`). |
| `colors` | `dict[str, Color]` | Color properties keyed by Unity property name (e.g., `"_Color"`). |

**Common property keys:**

| Category | Common Keys |
|----------|-------------|
| Textures | `_Albedo_Map`, `_Normal_Map`, `_Emission_Map`, `_Leaf_Texture`, `_Trunk_Texture` |
| Floats | `_Smoothness`, `_Metallic`, `_Cutoff`, `_Alpha_Clip_Threshold`, `_NormalStrength` |
| Colors | `_Color`, `_EmissionColor`, `_TintColor`, `_Deep_Color`, `_Shallow_Color` |

**Example usage:**

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

# Accessing data
print(material.name)                           # Tree_Leaves_Mat
print(material.shader_guid)                    # 9b98a126c8d4d7a4baeb81b16e4f7b97
print(len(material.tex_envs))                  # 2
print(material.floats.get("_Smoothness", 0.5)) # 0.1
if "_Leaf_Texture" in material.tex_envs:
    print(material.tex_envs["_Leaf_Texture"].guid)  # abc123...
```

---

## Regex Patterns

The module defines 8 compiled regex patterns (lines 172-254) for extracting data from Unity YAML.

### _NAME_PATTERN

**Purpose:** Extract material name from `m_Name` field.

**Definition (lines 178-182):**

```python
_NAME_PATTERN = re.compile(r"m_Name:\s*(.+?)\s*(?:\n|$)")
```

**Pattern breakdown:**

| Component | Meaning |
|-----------|---------|
| `m_Name:` | Literal match for field name |
| `\s*` | Optional whitespace after colon |
| `(.+?)` | **Capture group 1**: Material name (non-greedy) |
| `\s*` | Optional trailing whitespace |
| `(?:\n\|$)` | Non-capturing: newline or end of string |

**Matches:**

```yaml
m_Name: PolygonNature_Ground_01
```

**Captures:** `PolygonNature_Ground_01`

**Why non-greedy `(.+?)`:** Prevents capturing trailing whitespace or content after the name.

---

### _SHADER_GUID_PATTERN

**Purpose:** Extract shader GUID from `m_Shader` reference field.

**Definition (lines 184-191):**

```python
_SHADER_GUID_PATTERN = re.compile(
    r"m_Shader:\s*\{[^}]*guid:\s*([a-f0-9]+)",
    re.IGNORECASE,
)
```

**Pattern breakdown:**

| Component | Meaning |
|-----------|---------|
| `m_Shader:` | Literal field name |
| `\s*` | Optional whitespace |
| `\{` | Opening brace of inline YAML mapping |
| `[^}]*` | Any characters except closing brace (skips `fileID: 4800000, `) |
| `guid:\s*` | The guid key |
| `([a-f0-9]+)` | **Capture group 1**: Hex GUID string |

**Flags:**

- `re.IGNORECASE` - Handles uppercase hex digits (rare but possible)

**Matches:**

```yaml
m_Shader: {fileID: 4800000, guid: 0730dae39bc73f34796280af9875ce14, type: 3}
```

**Captures:** `0730dae39bc73f34796280af9875ce14`

**Why `[^}]*`:** Robustly skips any fields before `guid:` without hardcoding field order.

---

### _FLOAT_PATTERN

**Purpose:** Extract float properties from `m_Floats` section.

**Definition (lines 193-203):**

```python
_FLOAT_PATTERN = re.compile(
    r"^\s*-\s+(_\w+):\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*$",
    re.MULTILINE,
)
```

**Pattern breakdown:**

| Component | Meaning |
|-----------|---------|
| `^` | Start of line (with MULTILINE) |
| `\s*` | Optional leading whitespace |
| `-\s+` | YAML list item marker and required space |
| `(_\w+)` | **Capture group 1**: Property name (starts with underscore) |
| `:\s*` | Colon and optional whitespace |
| `([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)` | **Capture group 2**: Float value with scientific notation |
| `\s*$` | Optional trailing whitespace, end of line |

**Float value pattern explained:**

```
[-+]?           # Optional sign
\d*             # Optional digits before decimal
\.?             # Optional decimal point
\d+             # Required digits
(?:[eE][-+]?\d+)?  # Optional scientific notation (e.g., 1.5e-05)
```

**Flags:**

- `re.MULTILINE` - `^` and `$` match line boundaries, not just string boundaries

**Matches:**

```yaml
- _Smoothness: 0.5
- _Metallic: 0
- _AlphaThreshold: 1.5e-05
- _NegativeValue: -0.25
```

**Why property names start with `_`:** Unity shader properties conventionally use underscore prefix. This filters out non-property lines.

---

### _COLOR_PATTERN

**Purpose:** Extract RGBA color properties from `m_Colors` section.

**Definition (lines 205-217):**

```python
_COLOR_PATTERN = re.compile(
    r"^\s*-\s+(_\w+):\s*\{r:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?),\s*"
    r"g:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?),\s*"
    r"b:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?),\s*"
    r"a:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*\}",
    re.MULTILINE,
)
```

**Pattern breakdown:**

| Component | Meaning |
|-----------|---------|
| `^\s*-\s+(_\w+):\s*` | Same list item format as floats |
| `\{r:\s*(...),` | RGBA inline mapping with r component |
| `g:\s*(...),` | g component |
| `b:\s*(...),` | b component |
| `a:\s*(...)\s*\}` | a component and closing brace |

**Capture groups:**

1. Property name (e.g., `_Color`)
2. Red value
3. Green value
4. Blue value
5. Alpha value

**Matches:**

```yaml
- _Color: {r: 1, g: 0.5, b: 0.25, a: 1}
- _EmissionColor: {r: 2.5, g: 1.2, b: 0, a: 1}
```

**Captures:** `_Color`, `1`, `0.5`, `0.25`, `1`

---

### _TEX_PROPERTY_PATTERN

**Purpose:** Identify texture property entry start in `m_TexEnvs` section.

**Definition (lines 219-226):**

```python
_TEX_PROPERTY_PATTERN = re.compile(r"^\s*-\s+(_\w+):\s*$", re.MULTILINE)
```

**Pattern breakdown:**

| Component | Meaning |
|-----------|---------|
| `^\s*-\s+` | List item marker |
| `(_\w+)` | **Capture group 1**: Property name |
| `:\s*$` | Colon followed by nothing else on line |

**Key insight:** Texture entries have the property name on its own line (with colon), followed by indented `m_Texture`, `m_Scale`, `m_Offset` on subsequent lines.

**Matches:**

```yaml
- _Albedo_Map:
- _Normal_Map:
- _Emission_Map:
```

**Captures:** `_Albedo_Map`

**Why `:\s*$`:** Ensures we only match texture properties (which have nested content), not float properties (which have values on the same line).

---

### _TEX_GUID_PATTERN

**Purpose:** Extract texture GUID from `m_Texture` field within a texture entry.

**Definition (lines 228-236):**

```python
_TEX_GUID_PATTERN = re.compile(
    r"m_Texture:\s*\{[^}]*guid:\s*([a-f0-9]+)",
    re.IGNORECASE,
)
```

**Pattern:** Same structure as `_SHADER_GUID_PATTERN`.

**Matches:**

```yaml
m_Texture: {fileID: 2800000, guid: abc123def456789012345678abcdef01, type: 3}
```

**Captures:** `abc123def456789012345678abcdef01`

**Note on `fileID: 0`:** When no texture is assigned, Unity writes:

```yaml
m_Texture: {fileID: 0}
```

This has no `guid:` field, so the pattern correctly doesn't match (entry is skipped).

---

### _TEX_SCALE_PATTERN

**Purpose:** Extract UV scale from `m_Scale` field.

**Definition (lines 238-245):**

```python
_TEX_SCALE_PATTERN = re.compile(
    r"m_Scale:\s*\{x:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?),\s*"
    r"y:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*\}",
)
```

**Capture groups:**

1. X scale value
2. Y scale value

**Matches:**

```yaml
m_Scale: {x: 2, y: 2}
m_Scale: {x: 1.5, y: 0.75}
```

**Captures:** `2`, `2`

---

### _TEX_OFFSET_PATTERN

**Purpose:** Extract UV offset from `m_Offset` field.

**Definition (lines 247-254):**

```python
_TEX_OFFSET_PATTERN = re.compile(
    r"m_Offset:\s*\{x:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?),\s*"
    r"y:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*\}",
)
```

**Capture groups:**

1. X offset value
2. Y offset value

**Matches:**

```yaml
m_Offset: {x: 0.5, y: 0}
m_Offset: {x: -0.25, y: 0.1}
```

**Captures:** `0.5`, `0`

---

## Internal Helper Functions

### _extract_material_section()

**Purpose:** Extract the Material document from multi-document YAML.

**Definition (lines 257-295):**

```python
def _extract_material_section(content: str) -> str:
    """Extract the Material document from multi-document YAML."""
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `content` | `str` | Full `.mat` file content |

**Returns:** Material section string, or original content if no document markers found.

**Implementation:**

```python
material_match = re.search(
    r"---\s*!u!21[^\n]*\n((?:.*\n)*?)(?=---|\Z)",
    content,
    re.MULTILINE,
)
if material_match:
    return material_match.group(0)
return content
```

**Pattern breakdown:**

| Component | Meaning |
|-----------|---------|
| `---\s*!u!21` | Document separator with Material class ID (21) |
| `[^\n]*\n` | Rest of separator line |
| `((?:.*\n)*?)` | Content lines (non-greedy) |
| `(?=---\|\Z)` | Lookahead: next separator or end of string |

**Why needed:** Some Unity packages have multiple documents in one file. This ensures we parse the Material document, not metadata.

---

### _extract_material_name()

**Purpose:** Extract material name from `m_Name` field.

**Definition (lines 298-316):**

```python
def _extract_material_name(content: str) -> str:
    """Extract material name from m_Name field."""
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `content` | `str` | Material section content |

**Returns:** Material name (stripped of whitespace), or `"Unknown"` if not found.

**Implementation:**

```python
match = _NAME_PATTERN.search(content)
if match:
    return match.group(1).strip()
logger.warning("Could not extract material name from content")
return "Unknown"
```

**Logging:** Logs warning if name extraction fails (should be rare).

---

### _extract_shader_guid()

**Purpose:** Extract shader GUID from `m_Shader` field.

**Definition (lines 319-343):**

```python
def _extract_shader_guid(content: str) -> str:
    """Extract shader GUID from m_Shader field."""
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `content` | `str` | Material section content |

**Returns:** Shader GUID as lowercase 32-char hex string, or empty string if not found.

**Implementation:**

```python
match = _SHADER_GUID_PATTERN.search(content)
if match:
    return match.group(1).lower()
logger.warning("Could not extract shader GUID from content")
return ""
```

**Normalization:** Converts to lowercase for consistent lookups in shader GUID maps.

---

### _parse_floats()

**Purpose:** Parse all float properties from `m_Floats` section.

**Definition (lines 346-375):**

```python
def _parse_floats(content: str) -> dict[str, float]:
    """Parse float properties from m_Floats section."""
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `content` | `str` | Material section content |

**Returns:** Dictionary mapping property names to float values.

**Implementation:**

```python
floats: dict[str, float] = {}
for match in _FLOAT_PATTERN.finditer(content):
    prop_name = match.group(1)
    try:
        value = float(match.group(2))
        floats[prop_name] = value
    except ValueError as e:
        logger.warning("Failed to parse float '%s': %s", match.group(2), e)
return floats
```

**Error handling:** Logs warning on parse failure, continues processing other floats.

**Handles:**
- Integer values: `0`, `1`, `100`
- Decimal values: `0.5`, `0.123`
- Scientific notation: `1.5e-05`, `2.0E+10`
- Negative values: `-0.5`, `-1`

---

### _parse_colors()

**Purpose:** Parse all color properties from `m_Colors` section.

**Definition (lines 378-410):**

```python
def _parse_colors(content: str) -> dict[str, Color]:
    """Parse color properties from m_Colors section."""
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `content` | `str` | Material section content |

**Returns:** Dictionary mapping property names to `Color` objects.

**Implementation:**

```python
colors: dict[str, Color] = {}
for match in _COLOR_PATTERN.finditer(content):
    prop_name = match.group(1)
    try:
        r = float(match.group(2))
        g = float(match.group(3))
        b = float(match.group(4))
        a = float(match.group(5))
        colors[prop_name] = Color(r=r, g=g, b=b, a=a)
    except ValueError as e:
        logger.warning("Failed to parse color '%s': %s", prop_name, e)
return colors
```

**Preserves HDR values:** Does not clamp to 0.0-1.0 range.

---

### _parse_tex_envs()

**Purpose:** Parse texture references from `m_TexEnvs` section.

**Definition (lines 413-502):**

```python
def _parse_tex_envs(content: str) -> dict[str, TextureRef]:
    """Parse texture references from m_TexEnvs section."""
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `content` | `str` | Material section content |

**Returns:** Dictionary mapping property names to `TextureRef` objects.

**Implementation (multi-step):**

**Step 1: Find the m_TexEnvs section**

```python
tex_envs_match = re.search(
    r"m_TexEnvs:\s*\n((?:\s+-.*\n|\s+\w.*\n)*)",
    content,
)
if not tex_envs_match:
    return tex_envs
tex_section = tex_envs_match.group(0)
```

**Step 2: Find all texture property entries**

```python
for prop_match in _TEX_PROPERTY_PATTERN.finditer(tex_section):
    prop_name = prop_match.group(1)
    prop_start = prop_match.end()

    # Find boundary of this property's block
    next_prop = _TEX_PROPERTY_PATTERN.search(tex_section, prop_start)
    prop_end = next_prop.start() if next_prop else len(tex_section)
    prop_block = tex_section[prop_start:prop_end]
```

**Step 3: Extract GUID (skip if missing)**

```python
guid_match = _TEX_GUID_PATTERN.search(prop_block)
if not guid_match:
    continue  # No texture assigned
guid = guid_match.group(1).lower()

# Skip invalid GUIDs
if len(guid) < 32 or guid == "0" * 32:
    continue
```

**Step 4: Extract scale and offset**

```python
scale = (1.0, 1.0)
scale_match = _TEX_SCALE_PATTERN.search(prop_block)
if scale_match:
    try:
        scale = (float(scale_match.group(1)), float(scale_match.group(2)))
    except ValueError:
        pass  # Keep default

offset = (0.0, 0.0)
offset_match = _TEX_OFFSET_PATTERN.search(prop_block)
if offset_match:
    try:
        offset = (float(offset_match.group(1)), float(offset_match.group(2)))
    except ValueError:
        pass  # Keep default
```

**Step 5: Build TextureRef**

```python
tex_envs[prop_name] = TextureRef(guid=guid, scale=scale, offset=offset)
```

**Key behaviors:**
- Skips entries with `fileID: 0` (no texture assigned)
- Skips entries with all-zero or short GUIDs
- Uses defaults for scale/offset on parse failure
- Only returns textures that are actually assigned

---

## Public API Functions

### parse_material()

**Purpose:** Main entry point for parsing Unity materials.

**Definition (lines 505-569):**

```python
def parse_material(content: str) -> UnityMaterial:
    """Parse a Unity .mat file into structured data."""
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `content` | `str` | Full content of a `.mat` file as UTF-8 string |

**Returns:** `UnityMaterial` with all extracted properties.

**Implementation:**

```python
# Step 1: Extract Material document from multi-document YAML
material_section = _extract_material_section(content)

# Step 2: Parse each component
name = _extract_material_name(material_section)
shader_guid = _extract_shader_guid(material_section)
tex_envs = _parse_tex_envs(material_section)
floats = _parse_floats(material_section)
colors = _parse_colors(material_section)

# Step 3: Log summary
logger.debug(
    "Parsed material '%s': shader=%s, textures=%d, floats=%d, colors=%d",
    name,
    shader_guid[:8] + "..." if shader_guid else "none",
    len(tex_envs),
    len(floats),
    len(colors),
)

# Step 4: Return structured data
return UnityMaterial(
    name=name,
    shader_guid=shader_guid,
    tex_envs=tex_envs,
    floats=floats,
    colors=colors,
)
```

**Example:**

```python
from unity_parser import parse_material

with open("PolygonNature_Ground_01.mat", "r", encoding="utf-8") as f:
    content = f.read()

material = parse_material(content)
print(f"Material: {material.name}")           # PolygonNature_Ground_01
print(f"Shader GUID: {material.shader_guid}") # 0730dae39bc73f34796280af9875ce14
print(f"Textures: {len(material.tex_envs)}")  # 3
print(f"Floats: {material.floats}")           # {'_Smoothness': 0.7, ...}
```

---

### parse_material_bytes()

**Purpose:** Convenience wrapper for parsing from raw bytes.

**Definition (lines 572-600):**

```python
def parse_material_bytes(content: bytes, encoding: str = "utf-8") -> UnityMaterial:
    """Parse a Unity .mat file from raw bytes."""
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `content` | `bytes` | (required) | Raw bytes of the `.mat` file |
| `encoding` | `str` | `"utf-8"` | Text encoding for decoding |

**Returns:** `UnityMaterial` with all extracted properties.

**Raises:** `UnicodeDecodeError` if content cannot be decoded.

**Implementation:**

```python
text = content.decode(encoding)
return parse_material(text)
```

**Usage context:** The `unity_package.py` module provides raw bytes from tar extraction. This function handles the decode step.

**Example:**

```python
from unity_parser import parse_material_bytes
from unity_package import extract_unitypackage

guid_map = extract_unitypackage(Path("Package.unitypackage"))
for guid in get_material_guids(guid_map):
    content_bytes = guid_map.guid_to_content[guid]
    material = parse_material_bytes(content_bytes)
    print(f"Parsed: {material.name}")
```

---

## CLI Testing Interface

The module includes a CLI for testing (lines 603-659).

**Usage:**

```bash
python unity_parser.py path/to/material.mat
```

**Implementation:**

```python
if __name__ == "__main__":
    import argparse
    import sys
    from pathlib import Path

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Parse a Unity .mat file and display its contents."
    )
    parser.add_argument("mat_file", type=Path, help="Path to .mat file")
    args = parser.parse_args()

    if not args.mat_file.exists():
        print(f"Error: File not found: {args.mat_file}", file=sys.stderr)
        sys.exit(1)

    try:
        content = args.mat_file.read_text(encoding="utf-8")
        material = parse_material(content)

        print(f"\n{'='*60}")
        print(f"Material: {material.name}")
        print(f"{'='*60}")
        print(f"Shader GUID: {material.shader_guid or 'Not found'}")

        if material.tex_envs:
            print(f"\nTextures ({len(material.tex_envs)}):")
            for prop, tex in sorted(material.tex_envs.items()):
                print(f"  {prop}:")
                print(f"    GUID: {tex.guid}")
                print(f"    Scale: {tex.scale}")
                print(f"    Offset: {tex.offset}")

        if material.floats:
            print(f"\nFloats ({len(material.floats)}):")
            for prop, value in sorted(material.floats.items()):
                print(f"  {prop}: {value}")

        if material.colors:
            print(f"\nColors ({len(material.colors)}):")
            for prop, color in sorted(material.colors.items()):
                print(f"  {prop}: r={color.r:.3f}, g={color.g:.3f}, b={color.b:.3f}, a={color.a:.3f}")

        print(f"{'='*60}\n")

    except Exception as e:
        logger.error("Failed to parse material: %s", e)
        sys.exit(1)
```

**Example output:**

```
============================================================
Material: Tree_Bark
============================================================
Shader GUID: 9b98a126c8d4d7a4baeb81b16e4f7b97

Textures (2):
  _Trunk_Normal:
    GUID: def456789012345678abcdef01234567
    Scale: (1.0, 1.0)
    Offset: (0.0, 0.0)
  _Trunk_Texture:
    GUID: abc123def456789012345678abcdef01
    Scale: (1.0, 1.0)
    Offset: (0.0, 0.0)

Floats (3):
  _Alpha_Clip_Threshold: 0.5
  _Metallic: 0.0
  _Smoothness: 0.15

Colors (2):
  _Color: r=1.000, g=1.000, b=1.000, a=1.000
  _Trunk_Base_Color: r=0.800, g=0.600, b=0.400, a=1.000
============================================================
```

---

## Error Handling

The module uses graceful degradation:

| Scenario | Behavior |
|----------|----------|
| Missing `m_Name` | Logs warning, returns `"Unknown"` |
| Missing `m_Shader` | Logs warning, returns empty string |
| Invalid float value | Logs warning, skips that float |
| Invalid color value | Logs warning, skips that color |
| Texture with `fileID: 0` | Silently skips (expected case) |
| Invalid texture GUID | Silently skips |
| Scale/offset parse failure | Uses defaults `(1.0, 1.0)` / `(0.0, 0.0)` |
| Encoding error | Raises `UnicodeDecodeError` (in `parse_material_bytes`) |

**No exceptions are raised for missing data** - the module always returns a valid `UnityMaterial` object, even if mostly empty. This allows batch processing to continue when individual materials have issues.

---

## Unity YAML Quirks Handled

| Quirk | How Handled |
|-------|-------------|
| `!u!` custom tags | Regex ignores YAML parsing entirely |
| Multi-document files | `_extract_material_section()` extracts correct document |
| `fileID: 0` for empty textures | Pattern doesn't match (no guid), skips gracefully |
| Scientific notation | Float regex includes `(?:[eE][-+]?\d+)?` |
| All-zero GUIDs | Explicitly filtered: `guid == "0" * 32` |
| Short/invalid GUIDs | Filtered: `len(guid) < 32` |
| Varying whitespace | All patterns use `\s*` for flexibility |
| HDR color values | No clamping applied |
| Alpha=0 colors | Preserved as-is (fixed in shader_mapping.py) |

---

## Complete Parsing Flow

```
Input: .mat file bytes
          |
          v
   parse_material_bytes()
          | (decode UTF-8)
          v
   parse_material()
          |
          +---> _extract_material_section()
          |           | (find --- !u!21 block)
          |           v
          |     Material section string
          |
          +---> _extract_material_name()
          |           | (regex match m_Name)
          |           v
          |     name: str
          |
          +---> _extract_shader_guid()
          |           | (regex match m_Shader)
          |           v
          |     shader_guid: str
          |
          +---> _parse_tex_envs()
          |           | (multi-step texture parsing)
          |           v
          |     tex_envs: dict[str, TextureRef]
          |
          +---> _parse_floats()
          |           | (regex finditer m_Floats)
          |           v
          |     floats: dict[str, float]
          |
          +---> _parse_colors()
                      | (regex finditer m_Colors)
                      v
                colors: dict[str, Color]
          |
          v
   UnityMaterial(
       name=...,
       shader_guid=...,
       tex_envs=...,
       floats=...,
       colors=...
   )
          |
          v
Output: UnityMaterial dataclass
```

---

## Code Examples

### Basic Usage

```python
from pathlib import Path
from unity_parser import parse_material

# Read and parse a .mat file
mat_path = Path("C:/SyntyAssets/Materials/PolygonNature_Ground_01.mat")
content = mat_path.read_text(encoding="utf-8")
material = parse_material(content)

# Access basic info
print(f"Name: {material.name}")
print(f"Shader: {material.shader_guid}")

# Check for specific textures
if "_Albedo_Map" in material.tex_envs:
    albedo = material.tex_envs["_Albedo_Map"]
    print(f"Albedo texture GUID: {albedo.guid}")
    print(f"Albedo scale: {albedo.scale}")

# Get float with default
smoothness = material.floats.get("_Smoothness", 0.5)
print(f"Smoothness: {smoothness}")

# Check for HDR emission
if "_EmissionColor" in material.colors:
    emission = material.colors["_EmissionColor"]
    if emission.has_rgb():
        print(f"Has emission: r={emission.r}, g={emission.g}, b={emission.b}")
```

### Batch Processing from Unity Package

```python
from pathlib import Path
from unity_parser import parse_material_bytes
from unity_package import extract_unitypackage, get_material_guids

# Extract Unity package
package_path = Path("C:/Downloads/POLYGON_NatureBiomes.unitypackage")
guid_map = extract_unitypackage(package_path)

# Parse all materials
materials = []
for guid in get_material_guids(guid_map):
    content_bytes = guid_map.guid_to_content[guid]
    material = parse_material_bytes(content_bytes)
    materials.append(material)
    print(f"Parsed: {material.name}")

print(f"\nTotal materials: {len(materials)}")

# Group by shader
from collections import defaultdict
by_shader = defaultdict(list)
for mat in materials:
    by_shader[mat.shader_guid[:8] if mat.shader_guid else "unknown"].append(mat.name)

print("\nMaterials by shader:")
for shader, names in sorted(by_shader.items()):
    print(f"  {shader}...: {len(names)} materials")
```

### Detecting Texture Usage

```python
from unity_parser import parse_material

content = Path("MyMaterial.mat").read_text(encoding="utf-8")
material = parse_material(content)

# Check which texture slots are used
texture_slots = {
    "albedo": ["_Albedo_Map", "_BaseMap", "_MainTex", "_Base_Texture"],
    "normal": ["_Normal_Map", "_BumpMap", "_Normal_Texture"],
    "emission": ["_Emission_Map", "_EmissionMap"],
    "ao": ["_AO_Texture", "_OcclusionMap"],
}

used_textures = {}
for slot_name, property_names in texture_slots.items():
    for prop in property_names:
        if prop in material.tex_envs:
            used_textures[slot_name] = material.tex_envs[prop]
            break

print(f"Material '{material.name}' uses:")
for slot, tex in used_textures.items():
    print(f"  {slot}: {tex.guid[:8]}... (scale={tex.scale})")
```

---

## Notes for Doc Cleanup

After reviewing the existing documentation, here are findings for consolidation:

### Redundant Information

1. **`docs/api/unity_parser.md`** - This is a quick API reference that duplicates much of what's now in this step documentation:
   - Dataclass definitions (repeated verbatim)
   - Regex pattern documentation (repeated)
   - Complete example at the end (similar)
   - **Recommendation:** Keep as concise API reference, link to this step doc for detailed explanations

2. **`docs/unity-reference.md` Section "Unity Material Structure"** (lines 61-94):
   - Shows the same YAML structure documented here
   - **Recommendation:** Keep in unity-reference.md for quick reference, add cross-link

3. **`docs/unity-reference.md` Section "Unity Parsing Quirks"** (lines 601-630):
   - Brief overview that this document expands on
   - **Recommendation:** Keep brief overview, link here for regex details

4. **`docs/architecture.md` Section "Step 4: Parse Unity Materials"** (lines 165-175):
   - High-level description of this step
   - **Recommendation:** Keep as-is, add link to this document

### Outdated Information

1. **`docs/architecture.md` line 105-108** - Shows old dataclass structure:
   ```python
   textures: dict[str, str]    # property_name -> texture_guid
   ```
   Should be:
   ```python
   tex_envs: dict[str, TextureRef]  # property_name -> TextureRef
   ```

2. **`docs/api/unity_parser.md` line 8** - References `synty-converter-BLUE/unity_parser.py` instead of just `synty-converter/unity_parser.py`

### Information to Incorporate

1. **Property name alternatives** from `docs/unity-reference.md` lines 562-577 should be mentioned here as context for why multiple property names exist (though the actual handling is in shader_mapping.py)

2. **Legacy property names** from `docs/unity-reference.md` lines 578-597 are relevant context for what the parser might encounter

### Suggested Cross-References

Add to the following docs:

1. **`docs/architecture.md`** Step 4 section:
   - Add: "See [Step 4: Parse Materials](steps/04-parse-materials.md) for detailed implementation."

2. **`docs/api/unity_parser.md`**:
   - Add at top: "For detailed implementation documentation, see [Step 4: Parse Materials](../steps/04-parse-materials.md)."

3. **`docs/unity-reference.md`**:
   - In "Unity Parsing Quirks" section, add: "See [Step 4: Parse Materials](steps/04-parse-materials.md) for regex implementation details."

---

*Last Updated: 2026-01-31*
*Based on unity_parser.py (659 lines)*
