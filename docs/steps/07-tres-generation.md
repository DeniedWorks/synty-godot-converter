# Step 7: TRES ShaderMaterial Generation

This document provides comprehensive documentation for the `tres_generator.py` module, which generates Godot `.tres` ShaderMaterial resource files from converted materials.

**Module Location:** `synty-converter/tres_generator.py`

**Related Documentation:**
- [Architecture](../architecture.md) - Overall pipeline context
- [Shader Reference](../shader-reference.md) - Target shader details
- [API: tres_generator](../api/tres_generator.md) - Quick API reference

---

## Table of Contents

- [Overview](#overview)
- [Godot .tres File Format](#godot-tres-file-format)
  - [Format Structure](#format-structure)
  - [Header Section](#header-section)
  - [External Resources Section](#external-resources-section)
  - [Resource Section](#resource-section)
  - [Parameter Types](#parameter-types)
- [Module Constants](#module-constants)
  - [AUTO_ENABLE_RULES](#auto_enable_rules)
  - [TRIPLANAR_PREFIXES](#triplanar_prefixes)
- [Number Formatting Functions](#number-formatting-functions)
  - [format_float()](#format_float)
  - [format_color()](#format_color)
- [Filename Utilities](#filename-utilities)
  - [sanitize_filename()](#sanitize_filename)
- [Internal Helper Functions](#internal-helper-functions)
  - [_auto_enable_features()](#_auto_enable_features)
  - [_build_ext_resources()](#_build_ext_resources)
  - [_build_shader_parameters()](#_build_shader_parameters)
- [Public API Functions](#public-api-functions)
  - [generate_tres()](#generate_tres)
  - [write_tres_file()](#write_tres_file)
  - [generate_and_write_tres()](#generate_and_write_tres)
- [CLI Testing Interface](#cli-testing-interface)
- [Complete Generation Flow](#complete-generation-flow)
- [Code Examples](#code-examples)
- [Notes for Doc Cleanup](#notes-for-doc-cleanup)

---

## Overview

The `tres_generator.py` module is Step 7 in the 12-step conversion pipeline. It receives `MappedMaterial` objects (produced by `shader_mapping.py` in Step 6) and produces Godot `.tres` ShaderMaterial resource files that can be directly imported by Godot 4.x.

### Key Responsibilities

1. **Generate valid .tres format** - Produce text-based Godot resource files with correct structure
2. **Build external resource references** - Create shader and texture references with proper IDs
3. **Format shader parameters** - Convert textures, floats, bools, and colors to Godot syntax
4. **Auto-enable features** - Automatically enable shader features when textures are present
5. **Sanitize filenames** - Make material names safe for cross-platform filesystem use
6. **Write files** - Create output files with proper directory structure

### Module Dependencies

```
tres_generator.py
    └── Standard library only:
        ├── re (regex for filename sanitization)
        ├── logging (debug/warning output)
        ├── pathlib (file path handling)
        └── TYPE_CHECKING (type hints only)
    └── Project imports (type checking only):
        └── shader_mapping.MappedMaterial
```

No external packages required. This is intentional for portability.

---

## Godot .tres File Format

Godot's `.tres` (text resource) format is a human-readable serialization format for resources. ShaderMaterial files follow a specific structure that this module generates.

### Format Structure

A complete `.tres` ShaderMaterial file consists of three sections:

```tres
[gd_resource type="ShaderMaterial" load_steps=N format=3]

[ext_resource type="Shader" path="res://..." id="1"]
[ext_resource type="Texture2D" path="res://..." id="2"]
...

[resource]
shader = ExtResource("1")
shader_parameter/param_name = value
...
```

### Header Section

**Definition (line 502):**

```tres
[gd_resource type="ShaderMaterial" load_steps=N format=3]
```

**Components:**

| Component | Value | Description |
|-----------|-------|-------------|
| `type` | `"ShaderMaterial"` | Godot resource type - indicates this is a ShaderMaterial |
| `load_steps` | Integer | Number of external resources + 1 (for the resource itself) |
| `format` | `3` | Godot 4.x resource format version |

**Example:**

```tres
[gd_resource type="ShaderMaterial" load_steps=4 format=3]
```

This indicates:
- 4 total load steps
- 3 external resources (1 shader + 2 textures)
- 1 for the resource itself

### External Resources Section

External resources are references to other files (shaders, textures) that this material depends on.

**Shader Reference (always ID "1"):**

```tres
[ext_resource type="Shader" path="res://shaders/foliage.gdshader" id="1"]
```

**Texture References (IDs "2" and onwards):**

```tres
[ext_resource type="Texture2D" path="res://textures/Fern_1.tga" id="2"]
[ext_resource type="Texture2D" path="res://textures/Fern_1_Normal.png" id="3"]
```

**Key points:**
- Shader is always assigned ID `"1"`
- Textures are sorted alphabetically by parameter name for consistent output
- Texture IDs start at `"2"` and increment sequentially
- The `path` uses Godot's `res://` resource path syntax

### Resource Section

The resource section contains the actual material configuration.

**Structure:**

```tres
[resource]
shader = ExtResource("1")
shader_parameter/leaf_color = ExtResource("2")
shader_parameter/enable_breeze = true
shader_parameter/alpha_clip_threshold = 0.5
shader_parameter/leaf_base_color = Color(1.0, 0.9, 0.8, 1.0)
```

**Components:**

| Line | Purpose |
|------|---------|
| `[resource]` | Section marker |
| `shader = ExtResource("1")` | Links to the shader external resource |
| `shader_parameter/...` | Individual shader uniform values |

### Parameter Types

The module handles four types of shader parameters:

#### Texture Parameters

**Format:** `ExtResource("id")`

```tres
shader_parameter/albedo_texture = ExtResource("2")
shader_parameter/normal_texture = ExtResource("3")
```

Textures reference external resources by their ID.

#### Boolean Parameters

**Format:** `true` or `false` (lowercase)

```tres
shader_parameter/enable_breeze = true
shader_parameter/enable_normal_texture = false
```

Boolean values use lowercase Godot/GDScript syntax.

#### Float Parameters

**Format:** Decimal number with at least one decimal place

```tres
shader_parameter/metallic = 0.5
shader_parameter/roughness = 1.0
shader_parameter/alpha_clip_threshold = 0.25
```

Trailing zeros are stripped, but at least one decimal place is preserved.

#### Color Parameters

**Format:** `Color(r, g, b, a)` constructor syntax

```tres
shader_parameter/albedo_color = Color(1.0, 0.9, 0.8, 1.0)
shader_parameter/emission_color = Color(2.5, 1.0, 0.0, 1.0)
```

HDR values (exceeding 1.0) are preserved for emission effects.

---

## Module Constants

### AUTO_ENABLE_RULES

**Purpose:** Automatically enable shader features when corresponding textures are present.

**Definition (lines 71-114):**

There are 21 auto-enable rules organized by shader:

```python
AUTO_ENABLE_RULES: dict[str, str] = {
    # Polygon Shader (8 rules)
    "normal_texture": "enable_normal_texture",
    "emission_texture": "enable_emission_texture",
    "ao_texture": "enable_ambient_occlusion",
    "overlay_texture": "enable_overlay_texture",
    "triplanar_normal_top": "enable_triplanar_normals",
    "triplanar_normal_side": "enable_triplanar_normals",
    "triplanar_normal_bottom": "enable_triplanar_normals",
    "triplanar_emission_texture": "enable_triplanar_emission",

    # Foliage Shader (6 rules)
    "leaf_normal": "enable_leaf_normal",
    "trunk_normal": "enable_trunk_normal",
    "emissive_mask": "enable_emission",
    "emissive_2_mask": "enable_emission",
    "trunk_emissive_mask": "enable_emission",
    "emissive_pulse_mask": "enable_pulse",

    # Crystal Shader (3 rules)
    "top_albedo": "enable_top_projection",
    "top_normal": "enable_top_projection",
    "refraction_texture": "enable_refraction",

    # Water Shader (6 rules)
    "water_normal_texture": "enable_normals",
    "shore_foam_noise_texture": "enable_shore_foam",
    "foam_noise_texture": "enable_global_foam",
    "noise_texture": "enable_global_foam",
    "scrolling_texture": "enable_top_scrolling_texture",
    "caustics_flipbook": "enable_caustics",
}
```

**How it works:**

1. During `.tres` generation, the module scans all assigned textures
2. For each texture parameter that matches a key in `AUTO_ENABLE_RULES`, the corresponding boolean parameter is set to `true`
3. This saves users from manually enabling features after assigning textures

**Rule breakdown by shader:**

#### Polygon Shader Rules

| Texture Parameter | Enables | Purpose |
|------------------|---------|---------|
| `normal_texture` | `enable_normal_texture` | General normal mapping |
| `emission_texture` | `enable_emission_texture` | Emission/glow effects |
| `ao_texture` | `enable_ambient_occlusion` | Ambient occlusion maps |
| `overlay_texture` | `enable_overlay_texture` | Overlay texture blending |
| `triplanar_normal_top` | `enable_triplanar_normals` | Top normal in triplanar |
| `triplanar_normal_side` | `enable_triplanar_normals` | Side normal in triplanar |
| `triplanar_normal_bottom` | `enable_triplanar_normals` | Bottom normal in triplanar |
| `triplanar_emission_texture` | `enable_triplanar_emission` | Triplanar emission |

#### Foliage Shader Rules

| Texture Parameter | Enables | Purpose |
|------------------|---------|---------|
| `leaf_normal` | `enable_leaf_normal` | Foliage leaf normal maps |
| `trunk_normal` | `enable_trunk_normal` | Foliage trunk normal maps |
| `emissive_mask` | `enable_emission` | Emission mask texture |
| `emissive_2_mask` | `enable_emission` | Secondary emission mask |
| `trunk_emissive_mask` | `enable_emission` | Trunk emission mask |
| `emissive_pulse_mask` | `enable_pulse` | Pulsing emission effect |

#### Crystal Shader Rules

| Texture Parameter | Enables | Purpose |
|------------------|---------|---------|
| `top_albedo` | `enable_top_projection` | Top projection albedo |
| `top_normal` | `enable_top_projection` | Top projection normal |
| `refraction_texture` | `enable_refraction` | Crystal refraction effect |

#### Water Shader Rules

| Texture Parameter | Enables | Purpose |
|------------------|---------|---------|
| `water_normal_texture` | `enable_normals` | Water normal mapping |
| `shore_foam_noise_texture` | `enable_shore_foam` | Shore foam effect |
| `foam_noise_texture` | `enable_global_foam` | Global foam effect |
| `noise_texture` | `enable_global_foam` | Global foam (alt name) |
| `scrolling_texture` | `enable_top_scrolling_texture` | Scrolling surface texture |
| `caustics_flipbook` | `enable_caustics` | Underwater caustics |

### TRIPLANAR_PREFIXES

**Purpose:** Enable triplanar texture projection when textures with certain prefixes are present.

**Definition (lines 124-128):**

```python
TRIPLANAR_PREFIXES: tuple[str, ...] = (
    "triplanar_texture_",      # Base triplanar textures (albedo, etc.)
    "triplanar_normal_",       # Triplanar normal maps
    "triplanar_emission_",     # Triplanar emission textures
)
```

**How it works:**

If any texture parameter starts with one of these prefixes, `enable_triplanar_texture` is automatically set to `true`.

**Example:**

```python
# If material has:
textures = {
    "triplanar_texture_top": "Rock_Top.png",
    "triplanar_texture_side": "Rock_Side.png"
}
# Then auto_enabled includes:
{"enable_triplanar_texture": True}
```

**Note:** Specific triplanar normal/emission textures (like `triplanar_normal_top`) are also handled by `AUTO_ENABLE_RULES` above, enabling more specific features like `enable_triplanar_normals`.

---

## Number Formatting Functions

### format_float()

**Purpose:** Format a float value for `.tres` output with clean representation.

**Definition (lines 135-168):**

```python
def format_float(value: float) -> str:
    """Format a float value for .tres output."""
    # Format with 6 decimal places, then strip trailing zeros
    formatted = f"{value:.6f}".rstrip("0").rstrip(".")

    # Ensure we have at least one digit after decimal for consistency
    if "." not in formatted:
        formatted = f"{formatted}.0"

    return formatted
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `value` | `float` | Float value to format |

**Returns:** `str` - Formatted string with minimal decimal places.

**Behavior:**

1. Format with 6 decimal places for precision
2. Strip trailing zeros
3. Strip trailing decimal point (if all zeros removed)
4. Add `.0` if no decimal point remains (for Godot consistency)

**Examples:**

| Input | Output | Explanation |
|-------|--------|-------------|
| `0.5` | `"0.5"` | Clean representation |
| `0.123456789` | `"0.123457"` | Rounded to 6 decimal places |
| `1.0` | `"1.0"` | Preserves at least one decimal |
| `0.0` | `"0.0"` | Zero with decimal |
| `0.500000` | `"0.5"` | Trailing zeros stripped |
| `100.0` | `"100.0"` | Large numbers preserved |
| `0.000001` | `"0.000001"` | Small values preserved |

**Why 6 decimal places?**

- Matches Godot's default precision
- Sufficient for most shader parameters
- Avoids floating-point representation artifacts

### format_color()

**Purpose:** Format an RGBA color for `.tres` output in Godot's Color format.

**Definition (lines 171-206):**

```python
def format_color(r: float, g: float, b: float, a: float) -> str:
    """Format an RGBA color for .tres output."""
    def fmt(v: float) -> str:
        formatted = f"{v:.6f}".rstrip("0")
        # Ensure at least 1 decimal place for readability
        if "." in formatted:
            integer, decimal = formatted.split(".")
            if len(decimal) < 1:
                decimal = decimal.ljust(1, "0")
            return f"{integer}.{decimal}"
        return f"{formatted}.0"

    return f"Color({fmt(r)}, {fmt(g)}, {fmt(b)}, {fmt(a)})"
```

**Parameters:**

| Parameter | Type | Range | Description |
|-----------|------|-------|-------------|
| `r` | `float` | 0.0-1.0+ | Red component (can exceed 1.0 for HDR) |
| `g` | `float` | 0.0-1.0+ | Green component (can exceed 1.0 for HDR) |
| `b` | `float` | 0.0-1.0+ | Blue component (can exceed 1.0 for HDR) |
| `a` | `float` | 0.0-1.0 | Alpha component |

**Returns:** `str` - Formatted color string (e.g., `"Color(1.0, 0.9, 0.8, 1.0)"`).

**Behavior:**

1. Format each component using the inner `fmt()` function
2. Strip trailing zeros from each component
3. Ensure at least 1 decimal place for readability
4. Wrap in `Color(...)` constructor syntax

**Examples:**

| Input | Output |
|-------|--------|
| `(1.0, 0.5, 0.25, 1.0)` | `"Color(1.0, 0.5, 0.25, 1.0)"` |
| `(0.0, 0.0, 0.0, 1.0)` | `"Color(0.0, 0.0, 0.0, 1.0)"` |
| `(0.333333, 0.666666, 1.0, 0.5)` | `"Color(0.333333, 0.666666, 1.0, 0.5)"` |
| `(2.5, 1.0, 0.0, 1.0)` | `"Color(2.5, 1.0, 0.0, 1.0)"` (HDR preserved) |

**HDR Support:**

The function does not clamp values to 0.0-1.0. This preserves HDR emission colors where components may exceed 1.0 for glow intensity.

---

## Filename Utilities

### sanitize_filename()

**Purpose:** Make a material name safe for use as a filename across all platforms.

**Definition (lines 213-261):**

```python
def sanitize_filename(name: str) -> str:
    """Make a material name safe for use as a filename."""
    # Replace invalid filename characters with underscores
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    sanitized = re.sub(invalid_chars, "_", name)

    # Replace multiple underscores with single underscore
    sanitized = re.sub(r"_+", "_", sanitized)

    # Remove leading/trailing underscores and whitespace
    sanitized = sanitized.strip("_ \t\n")

    # Ensure we have a valid name
    if not sanitized:
        sanitized = "unnamed_material"

    return sanitized
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Material name to sanitize |

**Returns:** `str` - Sanitized filename-safe string.

**Invalid Characters Replaced:**

| Character | Platform Issue |
|-----------|----------------|
| `<` `>` | Windows reserved |
| `:` | Windows drive separator |
| `"` | Windows reserved |
| `/` `\` | Path separators |
| `|` | Windows pipe |
| `?` `*` | Wildcards |
| `\x00-\x1f` | Control characters |

**Processing Steps:**

1. **Replace invalid characters** - Convert to underscores
2. **Collapse multiple underscores** - `___` becomes `_`
3. **Strip leading/trailing** - Remove `_`, space, tab, newline
4. **Fallback** - Return `"unnamed_material"` if empty

**Examples:**

| Input | Output | Explanation |
|-------|--------|-------------|
| `"Normal_Mat"` | `"Normal_Mat"` | Already valid |
| `"Mat:With/Bad<Chars>"` | `"Mat_With_Bad_Chars"` | Characters replaced |
| `"Material \"Special\""` | `"Material_Special"` | Quotes replaced |
| `"  __spaced__  "` | `"spaced"` | Stripped and collapsed |
| `"path\\to\\material"` | `"path_to_material"` | Backslashes replaced |
| `""` | `"unnamed_material"` | Fallback for empty |
| `"???"` | `"unnamed_material"` | All invalid, fallback |

---

## Internal Helper Functions

### _auto_enable_features()

**Purpose:** Determine additional bool parameters to enable based on textures present.

**Definition (lines 268-311):**

```python
def _auto_enable_features(material: "MappedMaterial") -> dict[str, bool]:
    """Determine additional bool parameters to enable based on textures present."""
    auto_enabled: dict[str, bool] = {}

    # Check direct texture mappings
    for texture_param, enable_param in AUTO_ENABLE_RULES.items():
        if texture_param in material.textures:
            auto_enabled[enable_param] = True
            logger.debug(
                "Auto-enabled %s for material %s (texture %s present)",
                enable_param, material.name, texture_param
            )

    # Check for triplanar textures
    for texture_param in material.textures:
        for prefix in TRIPLANAR_PREFIXES:
            if texture_param.startswith(prefix):
                auto_enabled["enable_triplanar_texture"] = True
                logger.debug(
                    "Auto-enabled enable_triplanar_texture for material %s",
                    material.name
                )
                break
        else:
            continue
        break

    return auto_enabled
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `material` | `MappedMaterial` | The mapped material to analyze |

**Returns:** `dict[str, bool]` - Auto-enabled bool parameters (keys are param names, values are always `True`).

**Algorithm:**

1. **Check AUTO_ENABLE_RULES** - For each rule, if the texture exists, enable the feature
2. **Check TRIPLANAR_PREFIXES** - If any texture starts with a triplanar prefix, enable triplanar

**Example:**

```python
# Input material with textures:
material.textures = {
    "leaf_normal": "Leaf_Normal.png",
    "emission_texture": "Leaf_Glow.png"
}

# Returns:
{
    "enable_leaf_normal": True,
    "enable_emission_texture": True
}
```

**Logging:**

Debug messages are logged for each auto-enabled feature, useful for troubleshooting.

### _build_ext_resources()

**Purpose:** Build `[ext_resource]` lines for the `.tres` file.

**Definition (lines 318-375):**

```python
def _build_ext_resources(
    shader_path: str,
    textures: dict[str, str],
    texture_base: str
) -> tuple[list[str], dict[str, str]]:
    """Build [ext_resource] lines for the .tres file."""
    lines: list[str] = []
    param_to_id: dict[str, str] = {}

    # Shader is always ID "1"
    lines.append(
        f'[ext_resource type="Shader" path="{shader_path}" id="1"]'
    )

    # Textures get IDs starting at "2"
    next_id = 2

    # Sort textures for consistent output
    for param in sorted(textures.keys()):
        texture_name = textures[param]
        texture_path = f"{texture_base}/{texture_name}"
        resource_id = str(next_id)

        lines.append(
            f'[ext_resource type="Texture2D" path="{texture_path}" id="{resource_id}"]'
        )
        param_to_id[param] = resource_id
        next_id += 1

    return lines, param_to_id
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `shader_path` | `str` | Full resource path to shader (e.g., `"res://shaders/polygon.gdshader"`) |
| `textures` | `dict[str, str]` | Mapping of godot_param to texture_filename |
| `texture_base` | `str` | Base resource path for textures (e.g., `"res://textures"`) |

**Returns:** `tuple[list[str], dict[str, str]]`
- `list[str]` - Resource lines ready for `.tres` file
- `dict[str, str]` - Maps godot_param names to their resource IDs

**ID Assignment:**

| Resource | ID |
|----------|-----|
| Shader | `"1"` (always) |
| First texture (alphabetically) | `"2"` |
| Second texture | `"3"` |
| ... | increments |

**Example:**

```python
lines, id_map = _build_ext_resources(
    "res://shaders/foliage.gdshader",
    {"leaf_color": "Fern.tga", "leaf_normal": "Fern_Normal.png"},
    "res://textures"
)

# lines:
# [ext_resource type="Shader" path="res://shaders/foliage.gdshader" id="1"]
# [ext_resource type="Texture2D" path="res://textures/Fern.tga" id="2"]
# [ext_resource type="Texture2D" path="res://textures/Fern_Normal.png" id="3"]

# id_map:
# {"leaf_color": "2", "leaf_normal": "3"}
```

**Why sorted?**

Textures are sorted alphabetically by parameter name to ensure deterministic, consistent output across runs.

### _build_shader_parameters()

**Purpose:** Build `shader_parameter/xxx = yyy` lines for the `.tres` file.

**Definition (lines 378-430):**

```python
def _build_shader_parameters(
    material: "MappedMaterial",
    texture_id_map: dict[str, str]
) -> list[str]:
    """Build shader_parameter/xxx = yyy lines for the .tres file."""
    lines: list[str] = []

    # Get auto-enabled features
    auto_enabled = _auto_enable_features(material)

    # Merge auto-enabled with explicit bools (explicit takes precedence)
    all_bools = {**auto_enabled, **material.bools}

    # Texture parameters (sorted for consistency)
    for param in sorted(texture_id_map.keys()):
        resource_id = texture_id_map[param]
        lines.append(f'shader_parameter/{param} = ExtResource("{resource_id}")')

    # Bool parameters (sorted for consistency)
    for param in sorted(all_bools.keys()):
        value = "true" if all_bools[param] else "false"
        lines.append(f"shader_parameter/{param} = {value}")

    # Float parameters (sorted for consistency)
    for param in sorted(material.floats.keys()):
        value = format_float(material.floats[param])
        lines.append(f"shader_parameter/{param} = {value}")

    # Color parameters (sorted for consistency)
    for param in sorted(material.colors.keys()):
        r, g, b, a = material.colors[param]
        value = format_color(r, g, b, a)
        lines.append(f"shader_parameter/{param} = {value}")

    return lines
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `material` | `MappedMaterial` | The mapped material containing parameter values |
| `texture_id_map` | `dict[str, str]` | Maps godot_param to resource ID for textures |

**Returns:** `list[str]` - Shader parameter lines ready for `.tres` file.

**Processing Order:**

1. **Auto-enable features** - Call `_auto_enable_features()` to detect features
2. **Merge bools** - Combine auto-enabled with explicit bools (explicit wins)
3. **Write textures** - Sorted alphabetically
4. **Write bools** - Sorted alphabetically
5. **Write floats** - Sorted alphabetically
6. **Write colors** - Sorted alphabetically

**Explicit Override Example:**

```python
# Auto-enabled:
auto_enabled = {"enable_leaf_normal": True}

# Explicit bool in material:
material.bools = {"enable_leaf_normal": False}  # User wants it off

# Result (explicit wins):
all_bools = {"enable_leaf_normal": False}
```

---

## Public API Functions

### generate_tres()

**Purpose:** Main entry point for `.tres` generation. Converts a `MappedMaterial` into complete `.tres` file content.

**Definition (lines 437-529):**

```python
def generate_tres(
    material: "MappedMaterial",
    shader_base: str = "res://shaders",
    texture_base: str = "res://textures"
) -> str:
    """Generate Godot .tres ShaderMaterial resource content."""
    # Build shader path
    shader_path = f"{shader_base}/{material.shader_file}"

    # Build external resources
    ext_resources, texture_id_map = _build_ext_resources(
        shader_path,
        material.textures,
        texture_base
    )

    # Calculate load_steps (1 for resource + number of ext_resources)
    load_steps = len(ext_resources) + 1

    # Build shader parameters
    shader_params = _build_shader_parameters(material, texture_id_map)

    # Assemble the .tres file
    lines: list[str] = []

    # Header
    lines.append(f'[gd_resource type="ShaderMaterial" load_steps={load_steps} format=3]')
    lines.append("")

    # External resources
    for ext_res in ext_resources:
        lines.append(ext_res)

    lines.append("")

    # Resource section
    lines.append("[resource]")
    lines.append('shader = ExtResource("1")')

    for param_line in shader_params:
        lines.append(param_line)

    # Final newline
    lines.append("")

    content = "\n".join(lines)

    logger.debug(
        "Generated .tres for material %s (shader=%s, textures=%d, params=%d)",
        material.name, material.shader_file,
        len(material.textures), len(shader_params)
    )

    return content
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `material` | `MappedMaterial` | (required) | The mapped material to convert |
| `shader_base` | `str` | `"res://shaders"` | Resource path base for shaders |
| `texture_base` | `str` | `"res://textures"` | Resource path base for textures |

**Returns:** `str` - Complete `.tres` file content as string.

**Assembly Steps:**

1. **Build shader path** - Combine `shader_base` + `material.shader_file`
2. **Build external resources** - Shader and all texture references
3. **Calculate load_steps** - External resources + 1
4. **Build shader parameters** - All parameter assignments
5. **Assemble lines** - Header, blank, ext_resources, blank, resource section
6. **Join with newlines** - Create final content string

**Example Usage:**

```python
from tres_generator import generate_tres
from shader_mapping import MappedMaterial

material = MappedMaterial(
    name="Grass_01",
    shader_file="foliage.gdshader",
    textures={"leaf_color": "Grass_01.tga"},
    floats={"alpha_clip_threshold": 0.5},
    bools={"enable_breeze": True},
    colors={"leaf_base_color": (0.9, 1.0, 0.8, 1.0)}
)

content = generate_tres(
    material,
    shader_base="res://shaders/synty",
    texture_base="res://textures/synty"
)
```

**Example Output:**

```tres
[gd_resource type="ShaderMaterial" load_steps=3 format=3]

[ext_resource type="Shader" path="res://shaders/synty/foliage.gdshader" id="1"]
[ext_resource type="Texture2D" path="res://textures/synty/Grass_01.tga" id="2"]

[resource]
shader = ExtResource("1")
shader_parameter/leaf_color = ExtResource("2")
shader_parameter/enable_breeze = true
shader_parameter/alpha_clip_threshold = 0.5
shader_parameter/leaf_base_color = Color(0.9, 1.0, 0.8, 1.0)
```

### write_tres_file()

**Purpose:** Write `.tres` content to a file, creating parent directories as needed.

**Definition (lines 536-557):**

```python
def write_tres_file(content: str, output_path: Path) -> None:
    """Write .tres content to a file, creating directories as needed."""
    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write the file
    output_path.write_text(content, encoding="utf-8")

    logger.debug("Wrote .tres file: %s", output_path)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `content` | `str` | The `.tres` file content to write |
| `output_path` | `Path` | Path where the file should be written |

**Returns:** `None`

**Raises:** `OSError` if directory cannot be created or file cannot be written.

**Behavior:**

1. Create parent directories if they don't exist (`parents=True, exist_ok=True`)
2. Write file with UTF-8 encoding
3. Log the output path at debug level

**Example:**

```python
from pathlib import Path
from tres_generator import generate_tres, write_tres_file

content = generate_tres(material)
write_tres_file(content, Path("C:/output/materials/Grass_01.tres"))
```

### generate_and_write_tres()

**Purpose:** Convenience function that combines generation and writing in a single call.

**Definition (lines 564-609):**

```python
def generate_and_write_tres(
    material: "MappedMaterial",
    output_dir: Path,
    shader_base: str = "res://shaders",
    texture_base: str = "res://textures"
) -> Path:
    """Generate and write a .tres file for a material."""
    # Generate content
    content = generate_tres(material, shader_base, texture_base)

    # Build output path
    safe_name = sanitize_filename(material.name)
    output_path = output_dir / f"{safe_name}.tres"

    # Write file
    write_tres_file(content, output_path)

    return output_path
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `material` | `MappedMaterial` | (required) | The mapped material to convert |
| `output_dir` | `Path` | (required) | Directory to write the `.tres` file to |
| `shader_base` | `str` | `"res://shaders"` | Resource path base for shaders |
| `texture_base` | `str` | `"res://textures"` | Resource path base for textures |

**Returns:** `Path` - Path to the written `.tres` file.

**Raises:** `OSError` if directory cannot be created or file cannot be written.

**Workflow:**

1. Generate `.tres` content using `generate_tres()`
2. Sanitize material name for filename
3. Build output path: `output_dir / "{safe_name}.tres"`
4. Write file using `write_tres_file()`
5. Return the output path

**Example:**

```python
from pathlib import Path
from tres_generator import generate_and_write_tres

output_path = generate_and_write_tres(
    material=mapped_material,
    output_dir=Path("C:/Godot/Project/materials"),
    shader_base="res://shaders/synty",
    texture_base="res://textures/synty"
)
print(f"Written to: {output_path}")
# Output: Written to: C:\Godot\Project\materials\Grass_01.tres
```

---

## CLI Testing Interface

The module includes a CLI for testing (lines 616-689).

**Usage:**

```bash
python tres_generator.py
```

**Implementation:**

```python
if __name__ == "__main__":
    import sys
    from dataclasses import dataclass, field

    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")

    # Create a test MappedMaterial (inline to avoid import issues)
    @dataclass
    class TestMappedMaterial:
        name: str
        shader_file: str
        textures: dict[str, str] = field(default_factory=dict)
        floats: dict[str, float] = field(default_factory=dict)
        bools: dict[str, bool] = field(default_factory=dict)
        colors: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)

    # Example foliage material
    test_material = TestMappedMaterial(
        name="Fern_01",
        shader_file="foliage.gdshader",
        textures={
            "leaf_color": "Fern_1.tga",
            "leaf_normal": "Fern_1_Normal.png",
        },
        floats={
            "breeze_strength": 0.2,
            "alpha_clip_threshold": 0.5,
            "metallic": 0.0,
            "leaf_smoothness": 0.1,
        },
        bools={
            "enable_breeze": True,
        },
        colors={
            "leaf_base_color": (1.0, 0.9, 0.8, 1.0),
            "color_tint": (0.95, 1.0, 0.9, 1.0),
        },
    )

    # Generate and print
    content = generate_tres(test_material)
    print("Generated .tres content:")
    print(content)

    # Test formatting functions
    print("Format tests:")
    print(f"  format_float(0.5) = {format_float(0.5)}")
    print(f"  format_float(0.123456789) = {format_float(0.123456789)}")
    print(f"  format_color(1.0, 0.5, 0.25, 1.0) = {format_color(1.0, 0.5, 0.25, 1.0)}")

    # Test sanitize
    print("Sanitize filename tests:")
    print(f"  'Normal_Mat' = '{sanitize_filename('Normal_Mat')}'")
    print(f"  'Mat:With/Bad<Chars>' = '{sanitize_filename('Mat:With/Bad<Chars>')}'")
```

**Example Output:**

```
============================================================
TRES Generator Test
============================================================

Generated .tres content:
------------------------------------------------------------
[gd_resource type="ShaderMaterial" load_steps=4 format=3]

[ext_resource type="Shader" path="res://shaders/foliage.gdshader" id="1"]
[ext_resource type="Texture2D" path="res://textures/Fern_1.tga" id="2"]
[ext_resource type="Texture2D" path="res://textures/Fern_1_Normal.png" id="3"]

[resource]
shader = ExtResource("1")
shader_parameter/leaf_color = ExtResource("2")
shader_parameter/leaf_normal = ExtResource("3")
shader_parameter/enable_breeze = true
shader_parameter/enable_leaf_normal = true
shader_parameter/alpha_clip_threshold = 0.5
shader_parameter/breeze_strength = 0.2
shader_parameter/leaf_smoothness = 0.1
shader_parameter/metallic = 0.0
shader_parameter/color_tint = Color(0.95, 1.0, 0.9, 1.0)
shader_parameter/leaf_base_color = Color(1.0, 0.9, 0.8, 1.0)
------------------------------------------------------------

Format tests:
  format_float(0.5) = 0.5
  format_float(0.123456789) = 0.123457
  format_float(1.0) = 1.0
  format_float(0.0) = 0.0
  format_color(1.0, 0.5, 0.25, 1.0) = Color(1.0, 0.5, 0.25, 1.0)

Sanitize filename tests:
  'Normal_Mat' = 'Normal_Mat'
  'Mat:With/Bad<Chars>' = 'Mat_With_Bad_Chars'
  '  __spaced__  ' = 'spaced'
  '' = 'unnamed_material'

Test complete.
```

**Note:** The test creates an inline `TestMappedMaterial` dataclass to avoid import dependency issues during standalone testing.

---

## Complete Generation Flow

```
Input: MappedMaterial
          |
          v
   generate_tres()
          |
          +---> Build shader_path
          |           | shader_base + "/" + shader_file
          |           v
          |     "res://shaders/foliage.gdshader"
          |
          +---> _build_ext_resources()
          |           | shader_path, textures, texture_base
          |           v
          |     ext_resource_lines, texture_id_map
          |
          +---> Calculate load_steps
          |           | len(ext_resources) + 1
          |           v
          |     load_steps: int
          |
          +---> _build_shader_parameters()
          |           |
          |           +---> _auto_enable_features()
          |           |           | Check AUTO_ENABLE_RULES
          |           |           | Check TRIPLANAR_PREFIXES
          |           |           v
          |           |     auto_enabled: dict[str, bool]
          |           |
          |           +---> Merge bools (explicit wins)
          |           |
          |           +---> Format textures as ExtResource()
          |           |
          |           +---> Format bools as true/false
          |           |
          |           +---> Format floats via format_float()
          |           |
          |           +---> Format colors via format_color()
          |           |
          |           v
          |     shader_param_lines: list[str]
          |
          +---> Assemble file content
                      | Header line
                      | Blank line
                      | External resources
                      | Blank line
                      | [resource] section
                      | Final blank line
                      v
                content: str
          |
          v
   write_tres_file() [optional]
          |
          | Create directories
          | Write UTF-8 content
          v
   output_path: Path

Output: .tres file on disk (or content string)
```

---

## Code Examples

### Basic Usage

```python
from pathlib import Path
from tres_generator import generate_tres, generate_and_write_tres

# Assuming MappedMaterial from shader_mapping
from shader_mapping import MappedMaterial

# Create a material
material = MappedMaterial(
    name="Rock_01",
    shader_file="polygon_shader.gdshader",
    textures={
        "albedo_texture": "Rock_01_Albedo.png",
        "normal_texture": "Rock_01_Normal.png",
    },
    floats={
        "metallic": 0.0,
        "roughness": 0.8,
    },
    bools={},  # enable_normal_texture will be auto-enabled
    colors={
        "albedo_color": (1.0, 1.0, 1.0, 1.0),
    }
)

# Generate content string
content = generate_tres(material)
print(content)

# Or generate and write directly
output_path = generate_and_write_tres(
    material=material,
    output_dir=Path("C:/Godot/Project/materials")
)
print(f"Written to: {output_path}")
```

### Custom Resource Paths

```python
# For Synty assets in a subdirectory
content = generate_tres(
    material,
    shader_base="res://addons/synty_shaders/shaders",
    texture_base="res://assets/synty/POLYGON_Nature/Textures"
)
```

### Batch Processing

```python
from pathlib import Path
from tres_generator import generate_and_write_tres

def convert_all_materials(materials, output_dir):
    """Convert a list of MappedMaterials to .tres files."""
    output_paths = []

    for material in materials:
        try:
            path = generate_and_write_tres(
                material=material,
                output_dir=output_dir,
                shader_base="res://shaders/synty",
                texture_base="res://textures/synty"
            )
            output_paths.append(path)
            print(f"Generated: {material.name}")
        except OSError as e:
            print(f"Failed to write {material.name}: {e}")

    return output_paths
```

### Manual Content Generation with Custom Path Handling

```python
from pathlib import Path
from tres_generator import generate_tres, write_tres_file, sanitize_filename

def generate_with_relative_paths(material, output_dir, shader_dir, texture_dir):
    """Generate .tres with paths relative to the output location."""
    # Calculate relative paths from output to shader/texture directories
    shader_rel = Path(shader_dir).relative_to(Path(output_dir).parent)
    texture_rel = Path(texture_dir).relative_to(Path(output_dir).parent)

    content = generate_tres(
        material,
        shader_base=f"res://{shader_rel.as_posix()}",
        texture_base=f"res://{texture_rel.as_posix()}"
    )

    safe_name = sanitize_filename(material.name)
    output_path = Path(output_dir) / f"{safe_name}.tres"
    write_tres_file(content, output_path)

    return output_path
```

---

## Notes for Doc Cleanup

After reviewing the existing documentation, here are findings for consolidation:

### Redundant Information

1. **`docs/api/tres_generator.md`** - This is a quick API reference that significantly overlaps with this step documentation:
   - Function signatures and descriptions (repeated)
   - `.tres` format explanation (repeated)
   - AUTO_ENABLE_RULES table (partial - only shows 5 rules instead of all 28)
   - Complete example at the end (similar)
   - **Recommendation:** Keep as concise API reference (signature + brief description + example), link to this step doc for detailed explanations. Remove the detailed format explanation.

2. **`docs/api/tres_generator.md` "Auto-Enable Rules" section (lines 251-283)**:
   - Shows only partial rules (missing Crystal, Water, most Foliage rules)
   - Shows outdated `TRIPLANAR_PREFIXES` (only `"triplanar_texture_"` instead of all 3 prefixes)
   - **Recommendation:** Update to either show all rules or just link to this document

### Outdated Information

1. **`docs/api/tres_generator.md` line 283-284** - Shows incomplete TRIPLANAR_PREFIXES:
   ```python
   TRIPLANAR_PREFIXES: tuple[str, ...] = ("triplanar_texture_",)
   ```
   Should be:
   ```python
   TRIPLANAR_PREFIXES: tuple[str, ...] = (
       "triplanar_texture_",
       "triplanar_normal_",
       "triplanar_emission_",
   )
   ```

2. **`docs/api/tres_generator.md` AUTO_ENABLE_RULES** - Missing the following rules that exist in code:
   - `overlay_texture` -> `enable_overlay_texture`
   - `triplanar_normal_top/side/bottom` -> `enable_triplanar_normals`
   - `triplanar_emission_texture` -> `enable_triplanar_emission`
   - `emissive_2_mask` -> `enable_emission`
   - `trunk_emissive_mask` -> `enable_emission`
   - `emissive_pulse_mask` -> `enable_pulse`
   - All Crystal shader rules
   - All Water shader rules

### Information to Incorporate

1. **`docs/shader-reference.md`** - Has detailed shader parameter documentation that complements this module:
   - Links between texture parameters and enable flags should cross-reference this document

2. **`docs/architecture.md`** - Step 7 description should link to this document

### Suggested Cross-References

Add to the following docs:

1. **`docs/architecture.md`** Step 7 section:
   - Add: "See [Step 7: TRES Generation](steps/07-tres-generation.md) for detailed implementation."

2. **`docs/api/tres_generator.md`**:
   - Add at top: "For detailed implementation documentation, see [Step 7: TRES Generation](../steps/07-tres-generation.md)."
   - Update AUTO_ENABLE_RULES to link to step doc for full list

3. **`docs/shader-reference.md`**:
   - In each shader's parameters section, note which textures auto-enable features
   - Link to this document for the complete auto-enable logic

### Suggested File Consolidation

Consider moving the detailed AUTO_ENABLE_RULES documentation from this step doc to a shared location since:
- It relates to both shader_mapping.py (which defines the mappings) and tres_generator.py (which applies them)
- Other docs reference it

Options:
1. Keep in this doc (current approach) - most relevant to TRES generation
2. Create `docs/reference/auto-enable-rules.md` and link from both step docs
3. Add to `docs/shader-reference.md` since it describes shader behavior

---

*Last Updated: 2026-01-31*
