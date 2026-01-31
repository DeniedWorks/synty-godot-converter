# Shader Mapping API Reference

The `shader_mapping` module is the **core** of the Synty Shader Converter. It detects Unity shader types and maps Unity material properties to their Godot equivalents.

> **For detailed implementation:** See [Step 6: Shader Detection](../steps/06-shader-detection.md)

## Module Location

```
synty-converter/shader_mapping.py
```

## Overview

This module provides:
- **Shader Detection**: 3-tier algorithm to identify the correct Godot shader from Unity materials
- **Property Mapping**: Converts Unity property names to Godot parameter names
- **Quirk Handling**: Fixes common Unity material issues (alpha=0 colors, boolean-as-float)
- **Default Values**: Applies sensible defaults when Unity values are missing

The module contains extensive mapping data derived from analysis of **29 Synty Unity packages** (~3,300 materials).

---

## Classes

### MappedMaterial

Represents a material converted for use in Godot.

```python
@dataclass
class MappedMaterial:
    name: str
    shader_file: str
    textures: dict[str, str] = field(default_factory=dict)
    floats: dict[str, float] = field(default_factory=dict)
    bools: dict[str, bool] = field(default_factory=dict)
    colors: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)
```

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Material name (from Unity) |
| `shader_file` | `str` | Godot shader filename (e.g., `"foliage.gdshader"`) |
| `textures` | `dict[str, str]` | Godot parameter name -> texture filename mapping |
| `floats` | `dict[str, float]` | Godot parameter name -> float value mapping |
| `bools` | `dict[str, bool]` | Godot parameter name -> boolean value mapping |
| `colors` | `dict[str, tuple]` | Godot parameter name -> RGBA tuple `(r, g, b, a)` |

#### Example

```python
mapped = MappedMaterial(
    name="Tree_Leaves_Mat",
    shader_file="foliage.gdshader",
    textures={
        "leaf_color": "Tree_Leaves_Albedo.png",
        "leaf_normal": "Tree_Leaves_Normal.png",
    },
    floats={
        "leaf_smoothness": 0.1,
        "alpha_clip_threshold": 0.5,
    },
    bools={
        "enable_breeze": True,
    },
    colors={
        "leaf_base_color": (0.2, 0.5, 0.2, 1.0),
    }
)
```

---

### Color

RGBA color representation (also defined in this module for internal use).

```python
@dataclass
class Color:
    r: float = 0.0
    g: float = 0.0
    b: float = 0.0
    a: float = 1.0
```

#### Methods

- `as_tuple() -> tuple[float, float, float, float]` - Returns `(r, g, b, a)` tuple
- `has_rgb() -> bool` - Returns `True` if any RGB component is non-zero

---

### UnityMaterial

Represents a parsed Unity material (internal representation).

```python
@dataclass
class UnityMaterial:
    name: str
    shader_guid: str
    textures: dict[str, str] = field(default_factory=dict)
    floats: dict[str, float] = field(default_factory=dict)
    colors: dict[str, Color] = field(default_factory=dict)
```

---

## Core Functions

### detect_shader_type

Detect the appropriate Godot shader for a Unity material.

```python
def detect_shader_type(
    shader_guid: str,
    material_name: str,
    floats: dict[str, float] | None = None,
    colors: dict[str, tuple[float, float, float, float]] | None = None,
) -> str
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `shader_guid` | `str` | Unity shader GUID from `m_Shader.guid` |
| `material_name` | `str` | Material name for fallback pattern matching |
| `floats` | `dict[str, float]` | Optional float properties for property-based detection |
| `colors` | `dict[str, tuple]` | Optional color properties for property-based detection |

#### Returns

Godot shader filename (e.g., `"foliage.gdshader"`).

#### Detection Algorithm

The function uses a **3-tier detection strategy**:

```
                    +------------------+
                    |   Shader GUID    |
                    +--------+---------+
                             |
           +-----------------+-----------------+
           |                                   |
           v                                   v
    +------+-------+                   +-------+------+
    | GUID found   |                   | GUID unknown |
    | (specific)   |                   | or polygon   |
    +------+-------+                   +-------+------+
           |                                   |
           v                                   v
    Return shader                    +---------+---------+
    immediately                      |  Scoring System   |
                                     +---------+---------+
                                               |
                           +-------------------+-------------------+
                           |                                       |
                           v                                       v
                    +------+-------+                       +-------+------+
                    | Name Pattern |                       | Property     |
                    | Scoring      |                       | Scoring      |
                    +------+-------+                       +-------+------+
                           |                                       |
                           +-------------------+-------------------+
                                               |
                                               v
                                     +---------+---------+
                                     | Sum all scores    |
                                     | Highest wins      |
                                     | (if >= 20 points) |
                                     +---------+---------+
                                               |
                           +-------------------+-------------------+
                           |                                       |
                           v                                       v
                    Score >= 20                              Score < 20
                    Return winner                            Return DEFAULT
                                                             (polygon.gdshader)
```

#### Tier 1: GUID Lookup (Highest Priority)

If the shader GUID matches a known Synty shader and maps to a **specific** shader (not polygon), use it immediately:

```python
# Known GUID for Synty Foliage shader -> immediately return "foliage.gdshader"
shader_guid = "9b98a126c8d4d7a4baeb81b16e4f7b97"
result = detect_shader_type(shader_guid, "AnyName")  # -> "foliage.gdshader"
```

#### Tier 2: Scoring-Based Detection

If GUID is unknown or maps to polygon (generic), the function calculates scores:

**Name Pattern Scoring:**
- Each matching pattern adds points based on specificity
- High scores (50+): Technical terms like "triplanar", "caustics", "fresnel"
- Medium scores (30-49): Clear material types like "crystal", "water", "particle"
- Low scores (10-29): Generic terms like "leaf", "bark", "effect"

**Property-Based Scoring:**
- Each matching property adds 10 points to the associated shader
- Water properties: `_Enable_Caustics`, `_Water_Depth`, etc.
- Foliage properties: `_Enable_Breeze`, `_Leaf_Smoothness`, etc.
- Crystal properties: `_Enable_Fresnel`, `_Fresnel_Power`, etc.

**Example - Compound Name Resolution:**
```python
# Material name: "Dirt_Leaves_Triplanar"
# - "triplanar" adds 60 points to polygon.gdshader
# - "leaves" adds 20 points to foliage.gdshader
# Result: polygon.gdshader wins (60 > 20)

shader = detect_shader_type("unknown", "Dirt_Leaves_Triplanar")
# Returns "polygon.gdshader"
```

#### Tier 3: Default Fallback

If no detection method yields a strong result (score < 20), defaults to `polygon.gdshader`.

#### Complete Example

```python
from shader_mapping import detect_shader_type

# Tier 1: GUID lookup
shader = detect_shader_type(
    shader_guid="9b98a126c8d4d7a4baeb81b16e4f7b97",  # Known foliage GUID
    material_name="Tree_Mat"
)
# Returns: "foliage.gdshader" (from GUID)

# Tier 2: Name pattern + property scoring
shader = detect_shader_type(
    shader_guid="unknown_guid_12345678901234567890",
    material_name="SomeMaterial",
    floats={
        "_Enable_Fresnel": 1.0,
        "_Fresnel_Power": 2.5,
        "_Opacity": 0.7,
    },
    colors={
        "_Deep_Color": (0.1, 0.2, 0.5, 1.0),
    }
)
# Returns: "crystal.gdshader" (4 crystal properties * 10 = 40 points)

# Tier 3: Default fallback
shader = detect_shader_type(
    shader_guid="unknown_guid_12345678901234567890",
    material_name="GenericMaterial"
)
# Returns: "polygon.gdshader" (no strong matches)
```

---

### map_material

Convert a Unity material to Godot format.

```python
def map_material(
    material: UnityMaterial,
    texture_guid_map: dict[str, str]
) -> MappedMaterial
```

This is the **main entry point** for material conversion.

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `material` | `UnityMaterial` | Parsed Unity material from `unity_parser` |
| `texture_guid_map` | `dict[str, str]` | Mapping from texture GUID to texture filename |

#### Returns

`MappedMaterial` ready for `.tres` generation.

#### Conversion Process

1. **Detect shader type** - Uses `detect_shader_type()` with all available context
2. **Get property maps** - Retrieves texture, float, and color mappings for the shader
3. **Map textures** - Converts Unity property names to Godot names, resolves GUIDs to filenames
4. **Map floats** - Converts names, splits out boolean-as-float properties
5. **Map colors** - Converts names, fixes alpha=0 quirk
6. **Apply defaults** - Adds shader-specific default values for missing properties

#### Example

```python
from unity_parser import parse_material_bytes
from shader_mapping import map_material

# Parse Unity material
unity_mat = parse_material_bytes(mat_content)

# Map to Godot format
texture_guid_map = {
    "abc123...": "Tree_Bark_Albedo.png",
    "def456...": "Tree_Bark_Normal.png",
}

mapped = map_material(unity_mat, texture_guid_map)

print(f"Shader: {mapped.shader_file}")
print(f"Textures: {mapped.textures}")
print(f"Floats: {mapped.floats}")
print(f"Bools: {mapped.bools}")
print(f"Colors: {mapped.colors}")
```

---

### create_placeholder_material

Create a placeholder material for missing references.

```python
def create_placeholder_material(material_name: str) -> MappedMaterial
```

Used when a material is referenced in `mesh_material_mapping.json` but doesn't exist in the Unity package (e.g., shared materials from other packs).

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `material_name` | `str` | Name of the missing material |

#### Returns

`MappedMaterial` with appropriate shader (detected from name) and default values.

#### Example

```python
from shader_mapping import create_placeholder_material

# Referenced but missing material
placeholder = create_placeholder_material("Crystal_Mat_01")

# Returns MappedMaterial with:
#   shader_file: "crystal.gdshader" (detected from name)
#   floats: {"opacity": 0.7}
#   bools: {"enable_fresnel": True}
#   colors: {"base_color": (0.5, 0.7, 1.0, 1.0)}  # Light blue
```

---

## Helper Functions

### _fix_alpha_zero

Fix Unity's alpha=0 quirk for color properties.

```python
def _fix_alpha_zero(color: Color, property_name: str) -> Color
```

Unity often stores colors with `alpha=0` even when the color is visible. If the property is in `ALPHA_FIX_PROPERTIES` and has non-zero RGB with zero alpha, this function sets alpha to 1.0.

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `color` | `Color` | Original color |
| `property_name` | `str` | Unity property name |

#### Returns

`Color` with potentially fixed alpha.

#### Example

```python
# Unity stored: _Deep_Color: {r: 0.1, g: 0.2, b: 0.5, a: 0}
color = Color(r=0.1, g=0.2, b=0.5, a=0.0)
fixed = _fix_alpha_zero(color, "_Deep_Color")
# Returns: Color(r=0.1, g=0.2, b=0.5, a=1.0)
```

---

### _convert_boolean_floats

Split boolean-as-float properties from regular floats.

```python
def _convert_boolean_floats(
    floats: dict[str, float],
    float_map: dict[str, str]
) -> tuple[dict[str, float], dict[str, bool]]
```

Unity stores many boolean toggles as floats (0.0 or 1.0). This function separates them.

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `floats` | `dict[str, float]` | Unity float properties |
| `float_map` | `dict[str, str]` | Mapping from Unity names to Godot names |

#### Returns

Tuple of `(remaining_floats, extracted_bools)` with Godot names.

#### Example

```python
floats = {
    "_Smoothness": 0.5,
    "_Enable_Breeze": 1.0,
    "_Enable_Wind": 0.0,
}
float_map = {"_Smoothness": "smoothness"}

remaining, bools = _convert_boolean_floats(floats, float_map)
# remaining = {"smoothness": 0.5}
# bools = {"enable_breeze": True, "enable_wind": False}
```

---

### _unity_to_godot_name

Convert a Unity property name to Godot style.

```python
def _unity_to_godot_name(unity_name: str) -> str
```

Removes leading underscore and converts to snake_case.

#### Example

```python
_unity_to_godot_name("_Enable_Breeze")  # -> "enable_breeze"
_unity_to_godot_name("_AlphaClip")       # -> "alpha_clip"
```

---

### _apply_defaults

Apply shader-specific default values for missing properties.

```python
def _apply_defaults(material: MappedMaterial) -> MappedMaterial
```

Applies defaults from `SHADER_DEFAULTS` when values are missing.

---

## Utility Functions

### get_all_shader_guids

```python
def get_all_shader_guids() -> set[str]
```

Returns all known shader GUIDs (56 total).

---

### get_shader_for_guid

```python
def get_shader_for_guid(guid: str) -> str | None
```

Get the Godot shader filename for a Unity shader GUID, or `None` if unknown.

---

### get_texture_property_mapping

```python
def get_texture_property_mapping(shader_file: str) -> dict[str, str]
```

Get the texture property mapping for a specific shader.

**Example:**
```python
mapping = get_texture_property_mapping("foliage.gdshader")
# Returns: {"_Leaf_Texture": "leaf_color", "_Trunk_Texture": "trunk_color", ...}
```

---

### get_float_property_mapping

```python
def get_float_property_mapping(shader_file: str) -> dict[str, str]
```

Get the float property mapping for a specific shader.

---

### get_color_property_mapping

```python
def get_color_property_mapping(shader_file: str) -> dict[str, str]
```

Get the color property mapping for a specific shader.

---

### detect_shader_from_name

Detect shader type using only name pattern matching.

```python
def detect_shader_from_name(material_name: str) -> str | None
```

Used when `uses_custom_shader=True` in MaterialList. Returns shader filename or `None` if no match (signals logging needed).

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `material_name` | `str` | The material name to analyze |

#### Returns

Shader filename if a strong match is found (score >= 20), `None` if no strong match (caller should log for manual review).

#### Example

```python
>>> detect_shader_from_name("Crystal_Mat_01")
'crystal.gdshader'
>>> detect_shader_from_name("Water_River_01")
'water.gdshader'
>>> detect_shader_from_name("SomeUnknownMaterial")
None
```

---

### determine_shader

Determine shader for a material using the simplified MaterialList-based flow.

```python
def determine_shader(
    material_name: str,
    uses_custom_shader: bool,
) -> tuple[str, bool]
```

This is the main entry point for the new detection system. The logic is:
1. If not a custom shader (`uses_custom_shader=False`), always use polygon
2. If custom shader, try name pattern matching
3. If no match, default to polygon but signal for logging

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `material_name` | `str` | The material name |
| `uses_custom_shader` | `bool` | From MaterialList.txt - True if marked "(Uses custom shader)" |

#### Returns

Tuple of `(shader_filename, matched)` where:
- `shader_filename`: The Godot shader to use
- `matched`: `False` if the material should be logged for manual review (used to track unmatched custom shader materials)

#### Example

```python
>>> determine_shader("Ground_Mat", uses_custom_shader=False)
('polygon.gdshader', True)
>>> determine_shader("Crystal_Mat_01", uses_custom_shader=True)
('crystal.gdshader', True)
>>> determine_shader("UnknownMat", uses_custom_shader=True)
('polygon.gdshader', False)  # Needs manual review
```

---

## Constants Overview

The module contains extensive mapping data. Here is a summary:

### SHADER_GUID_MAP

Maps 44 Unity shader GUIDs to Godot shaders. See [constants.md](constants.md) for the full list.

| Shader Type | Count | Examples |
|-------------|-------|----------|
| `polygon.gdshader` | 45 | PolygonLit, Triplanar, Hologram, Ghost, Grunge |
| `foliage.gdshader` | 8 | Synty Foliage, Leaf Card, SciFiPlant, Wind Animation |
| `water.gdshader` | 5 | Synty Water, Waterfall, Water (Amplify) |
| `particles.gdshader` | 5 | Synty Particles, ParticlesLit, ParticlesUnlit |
| `crystal.gdshader` | 2 | Synty Crystal, Synty Glass |
| `skydome.gdshader` | 5 | Synty Skydome, Skybox_Generic, Aurora |
| `clouds.gdshader` | 1 | Synty Clouds |

### SHADER_NAME_PATTERNS_SCORED

30+ regex patterns with scores for name-based detection:

| Score Range | Pattern Examples |
|-------------|------------------|
| 50-60 | `triplanar`, `caustics`, `fresnel`, `skydome` |
| 40-49 | `crystal`, `water`, `particle`, `cloud` |
| 30-39 | `glass`, `ice`, `pond`, `smoke`, `aurora` |
| 20-29 | `tree`, `grass`, `vine`, `branch` |
| 10-19 | `moss`, `dirt`, `effect` |

### TEXTURE_MAPS

Per-shader texture property mappings:

```python
# Example: foliage.gdshader texture map
TEXTURE_MAP_FOLIAGE = {
    "_Leaf_Texture": "leaf_color",
    "_Leaf_Normal": "leaf_normal",
    "_Trunk_Texture": "trunk_color",
    "_Trunk_Normal": "trunk_normal",
    "_Leaf_Ambient_Occlusion": "leaf_ao",
    "_Trunk_Ambient_Occlusion": "trunk_ao",
    # Legacy names
    "_Leaves_NoiseTexture": "leaf_color",
    "_Tree_NoiseTexture": "trunk_color",
}
```

### FLOAT_MAPS

Per-shader float property mappings (77+ total properties across all shaders).

### COLOR_MAPS

Per-shader color property mappings (50+ total properties across all shaders).

### ALPHA_FIX_PROPERTIES

Set of 87 color property names that may have the alpha=0 quirk.

### BOOLEAN_FLOAT_PROPERTIES

Set of 55 property names that are booleans stored as floats.

### SHADER_DEFAULTS

Default values per shader type:

```python
SHADER_DEFAULTS = {
    "crystal.gdshader": {
        "opacity": 0.7,  # Crystals should be translucent
    },
    "foliage.gdshader": {
        "leaf_smoothness": 0.1,   # Matte leaves
        "trunk_smoothness": 0.15,  # Slightly rough bark
    },
    "water.gdshader": {
        "smoothness": 0.95,  # Very smooth water surface
    },
    "polygon.gdshader": {
        "smoothness": 0.5,
        "metallic": 0.0,
    },
}
```

---

## Adding New Shader Support

To add support for a new Synty shader:

### Step 1: Find the Shader GUID

Extract a Unity package that uses the shader and find the GUID in a `.mat` file:

```yaml
m_Shader: {fileID: 4800000, guid: <NEW_GUID_HERE>, type: 3}
```

### Step 2: Add to SHADER_GUID_MAP

```python
SHADER_GUID_MAP: dict[str, str] = {
    # ... existing entries ...
    "new_guid_here_32_hex_chars": "appropriate.gdshader",
}
```

### Step 3: Add Name Patterns (if applicable)

```python
SHADER_NAME_PATTERNS_SCORED.append(
    (re.compile(r"(?i)new_pattern"), "appropriate.gdshader", 45),
)
```

### Step 4: Add Property Mappings

Add Unity -> Godot property name mappings for textures, floats, and colors:

```python
TEXTURE_MAP_APPROPRIATE["_NewTexture"] = "new_texture"
FLOAT_MAP_APPROPRIATE["_NewFloat"] = "new_float"
COLOR_MAP_APPROPRIATE["_NewColor"] = "new_color"
```

### Step 5: Add to Quirk Handling (if needed)

```python
ALPHA_FIX_PROPERTIES.add("_NewColor")  # If alpha=0 quirk applies
BOOLEAN_FLOAT_PROPERTIES.add("_NewToggle")  # If it's a boolean
```

---

## Examples

### Example 1: Basic Material Conversion

```python
from unity_parser import parse_material
from shader_mapping import map_material

# Parse Unity material
content = '''
%YAML 1.1
--- !u!21 &2100000
Material:
  m_Name: Stone_Wall
  m_Shader: {fileID: 4800000, guid: 0730dae39bc73f34796280af9875ce14, type: 3}
  m_TexEnvs:
  - _Base_Texture:
      m_Texture: {fileID: 2800000, guid: abc123, type: 3}
  m_Floats:
  - _Smoothness: 0.3
  m_Colors:
  - _Color: {r: 1, g: 1, b: 1, a: 1}
'''

unity_mat = parse_material(content)
texture_map = {"abc123": "Stone_Wall_Albedo.png"}

mapped = map_material(unity_mat, texture_map)
# mapped.shader_file = "polygon.gdshader"
# mapped.textures = {"base_texture": "Stone_Wall_Albedo.png"}
# mapped.floats = {"smoothness": 0.3}
# mapped.colors = {"color_tint": (1.0, 1.0, 1.0, 1.0)}
```

### Example 2: Foliage with Wind Properties

```python
shader = detect_shader_type(
    shader_guid="9b98a126c8d4d7a4baeb81b16e4f7b97",  # Foliage GUID
    material_name="Tree_Leaves",
    floats={
        "_Enable_Breeze": 1.0,
        "_Breeze_Strength": 0.5,
        "_Smoothness": 0.1,
    }
)
# Returns: "foliage.gdshader"
```

### Example 3: Scoring-Based Detection

```python
# Material with competing patterns
shader = detect_shader_type(
    shader_guid="unknown",
    material_name="Water_Splash_Particles",
    floats={
        "_Soft_Power": 1.0,
        "_Enable_Soft_Particles": 1.0,
    }
)
# Name scoring:
#   "water" -> water.gdshader: +45
#   "particle" -> particles.gdshader: +45
# Property scoring:
#   "_Soft_Power" -> particles.gdshader: +10
#   "_Enable_Soft_Particles" -> particles.gdshader: +10
# Final scores:
#   water.gdshader: 45
#   particles.gdshader: 65
# Returns: "particles.gdshader" (highest score)
```

### Example 4: Crystal Property Detection

```python
shader = detect_shader_type(
    shader_guid="unknown",
    material_name="SomeMaterial",  # No helpful name
    floats={
        "_Enable_Fresnel": 1.0,
        "_Fresnel_Power": 2.5,
        "_Opacity": 0.7,
        "_Enable_Refraction": 1.0,
    },
    colors={
        "_Fresnel_Color": (0.5, 0.7, 1.0, 1.0),
    }
)
# Property scoring:
#   5 crystal properties * 10 = 50 points
# Returns: "crystal.gdshader"
```

---

## CLI Usage

The module includes a CLI for testing:

```bash
python shader_mapping.py
```

This prints:
- Summary statistics (GUID count, pattern count, etc.)
- Test cases demonstrating all detection tiers

---

## Troubleshooting

### Wrong Shader Detected

1. Check if the shader GUID is in `SHADER_GUID_MAP`
2. Enable debug logging to see scoring details:
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```
3. Add the GUID to the map if it's a known Synty shader

### Missing Properties

1. Check if the Unity property name is in the appropriate `*_MAP` dictionary
2. Add the mapping if missing

### Alpha=0 Colors Appearing Invisible

1. Check if the property name is in `ALPHA_FIX_PROPERTIES`
2. Add it if the color should have its alpha fixed

### Boolean Properties Not Converting

1. Check if the property name is in `BOOLEAN_FLOAT_PROPERTIES`
2. Add it if the property should be treated as a boolean
