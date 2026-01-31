# TRES Generator API Reference

> **For detailed implementation:** See [Step 7: TRES Generation](../steps/07-tres-generation.md)

## Overview

The `tres_generator` module generates Godot `.tres` ShaderMaterial resource files from converted materials. It takes `MappedMaterial` objects (produced by the shader mapping system) and outputs properly formatted `.tres` files that can be directly imported by Godot 4.x.

**Key Features:**
- Generates valid Godot `.tres` format with proper resource structure
- Handles textures, floats, bools, and colors
- Auto-enables shader features based on textures present (28 rules)
- Proper number formatting (strips trailing zeros for clean output)
- Sanitizes material names for filesystem safety

**Module Location:** `tres_generator.py`

---

## .tres File Format

Godot's `.tres` format is a text-based resource format. ShaderMaterial files consist of:

1. **Header** - Declares resource type and load steps
2. **External Resources** - References to shader and texture files
3. **Resource Section** - Shader assignment and parameter values

### Example Output

```tres
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
```

### Format Details

- **load_steps**: Number of external resources + 1 (for the resource itself)
- **format=3**: Godot 4.x resource format version
- **ExtResource("id")**: References to external resources by their ID
- Parameters are sorted alphabetically within each type for consistent output

---

## Functions

### generate_tres(material, shader_base, texture_base) -> str

Main entry point for `.tres` generation. Converts a `MappedMaterial` into complete `.tres` file content.

**Arguments:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `material` | `MappedMaterial` | The mapped material to convert |
| `shader_base` | `str` | Resource path base for shaders (e.g., `"res://shaders"`) |
| `texture_base` | `str` | Resource path base for textures (e.g., `"res://textures"`) |

**Returns:** `str` - Complete `.tres` file content as a string

**Example:**

```python
from tres_generator import generate_tres
from shader_mapping import MappedMaterial

material = MappedMaterial(
    name="Grass_01",
    shader_file="foliage.gdshader",
    textures={"leaf_color": "Grass_01.tga"},
    floats={"alpha_clip_threshold": 0.5},
    bools={"enable_breeze": True},
    colors={}
)

content = generate_tres(
    material,
    shader_base="res://shaders",
    texture_base="res://textures"
)
```

---

### write_tres_file(content, output_path) -> None

Writes `.tres` content to a file, creating parent directories as needed.

**Arguments:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `content` | `str` | The `.tres` file content to write |
| `output_path` | `Path` | Path where the file should be written |

**Returns:** `None`

**Side Effects:**
- Creates parent directories if they don't exist
- Writes file with UTF-8 encoding
- Logs the output path

**Example:**

```python
from pathlib import Path
from tres_generator import write_tres_file

write_tres_file(content, Path("output/materials/Grass_01.tres"))
```

---

### generate_and_write_tres(material, output_dir, shader_base, texture_base) -> Path

Convenience function that combines generation and writing in a single call.

**Arguments:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `material` | `MappedMaterial` | - | The mapped material to convert |
| `output_dir` | `Path` | - | Directory to write the `.tres` file to |
| `shader_base` | `str` | `"res://shaders"` | Resource path base for shaders |
| `texture_base` | `str` | `"res://textures"` | Resource path base for textures |

**Returns:** `Path` - Path to the written `.tres` file

**Example:**

```python
from pathlib import Path
from tres_generator import generate_and_write_tres

output_path = generate_and_write_tres(
    material,
    output_dir=Path("output/materials"),
    shader_base="res://shaders",
    texture_base="res://textures"
)
print(f"Written to: {output_path}")
```

---

### sanitize_filename(name) -> str

Makes a material name safe for use as a filename by removing or replacing invalid characters.

**Arguments:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Material name to sanitize |

**Returns:** `str` - Sanitized filename-safe string

**Behavior:**
- Replaces invalid filename characters (`< > : " / \ | ? *` and control characters) with underscores
- Collapses multiple consecutive underscores into a single underscore
- Strips leading/trailing underscores and whitespace
- Returns `"unnamed_material"` if result would be empty

**Examples:**

```python
from tres_generator import sanitize_filename

sanitize_filename("Normal_Mat")           # -> "Normal_Mat"
sanitize_filename("Mat:With/Bad<Chars>")  # -> "Mat_With_Bad_Chars"
sanitize_filename("  __spaced__  ")       # -> "spaced"
sanitize_filename("")                     # -> "unnamed_material"
```

---

### format_float(value) -> str

Formats a float value for `.tres` output with clean representation.

**Arguments:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `value` | `float` | Float value to format |

**Returns:** `str` - Formatted string (e.g., `"0.5"` not `"0.500000"`)

**Behavior:**
- Uses up to 6 decimal places for precision
- Strips trailing zeros
- Ensures at least one digit after decimal point (e.g., `"1.0"` not `"1"`)

**Examples:**

```python
from tres_generator import format_float

format_float(0.5)          # -> "0.5"
format_float(0.123456789)  # -> "0.123457" (rounded to 6 places)
format_float(1.0)          # -> "1.0"
format_float(0.0)          # -> "0.0"
format_float(0.100000)     # -> "0.1"
```

---

### format_color(r, g, b, a) -> str

Formats an RGBA color for `.tres` output in Godot's Color format.

**Arguments:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `r` | `float` | Red component (0.0-1.0) |
| `g` | `float` | Green component (0.0-1.0) |
| `b` | `float` | Blue component (0.0-1.0) |
| `a` | `float` | Alpha component (0.0-1.0) |

**Returns:** `str` - Formatted color string (e.g., `"Color(1.0, 0.9, 0.8, 1.0)"`)

**Behavior:**
- Formats each component with up to 6 decimal places
- Ensures at least 1 decimal place for readability

**Example:**

```python
from tres_generator import format_color

format_color(1.0, 0.5, 0.25, 1.0)  # -> "Color(1.0, 0.5, 0.25, 1.0)"
format_color(0.0, 0.0, 0.0, 1.0)   # -> "Color(0.0, 0.0, 0.0, 1.0)"
```

---

## Auto-Enable Rules

The generator automatically enables certain shader features when corresponding textures are present. This ensures proper rendering without requiring manual configuration.

> **Full rule list:** See [Step 7: TRES Generation](../steps/07-tres-generation.md#auto-enable-rules) for all 28 auto-enable rules.

### Common Texture-to-Feature Mappings

| Texture Parameter | Auto-Enabled Feature |
|------------------|---------------------|
| `leaf_normal` | `enable_leaf_normal` |
| `trunk_normal` | `enable_trunk_normal` |
| `normal_texture` | `enable_normal_texture` |
| `emission_texture` | `enable_emission_texture` |
| `ao_texture` | `enable_ambient_occlusion` |
| `overlay_texture` | `enable_overlay_texture` |
| `emissive_2_mask`, `trunk_emissive_mask` | `enable_emission` |
| `emissive_pulse_mask` | `enable_pulse` |

### Triplanar Texture Detection

Any texture parameter starting with these prefixes automatically enables the corresponding feature:

```python
TRIPLANAR_PREFIXES: tuple[str, ...] = (
    "triplanar_texture_",   # -> enable_triplanar_texture
    "triplanar_normal_",    # -> enable_triplanar_normals
    "triplanar_emission_",  # -> enable_triplanar_emission
)
```

### Rule Application

Auto-enabled features are merged with explicitly defined boolean parameters. **Explicit values take precedence** over auto-enabled values, allowing override when needed.

---

## Complete Example

This example demonstrates converting a `MappedMaterial` to a `.tres` file.

### Input: MappedMaterial

```python
from dataclasses import dataclass, field

@dataclass
class MappedMaterial:
    name: str = "Fern_01"
    shader_file: str = "foliage.gdshader"
    textures: dict = field(default_factory=lambda: {
        "leaf_color": "Fern_1.tga",
        "leaf_normal": "Fern_1_Normal.png",
    })
    floats: dict = field(default_factory=lambda: {
        "breeze_strength": 0.2,
        "alpha_clip_threshold": 0.5,
        "metallic": 0.0,
        "leaf_smoothness": 0.1,
    })
    bools: dict = field(default_factory=lambda: {
        "enable_breeze": True,
    })
    colors: dict = field(default_factory=lambda: {
        "leaf_base_color": (1.0, 0.9, 0.8, 1.0),
        "color_tint": (0.95, 1.0, 0.9, 1.0),
    })
```

### Output: .tres Content

```tres
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
```

**Note:** The `enable_leaf_normal` parameter was auto-enabled because `leaf_normal` texture is present.

---

## Internal Functions

These functions are used internally and are prefixed with underscore.

### _auto_enable_features(material) -> dict[str, bool]

Determines additional bool parameters to enable based on textures present.

### _build_ext_resources(shader_path, textures, texture_base) -> tuple[list[str], dict[str, str]]

Builds `[ext_resource]` lines for the `.tres` file. Returns both the lines and a mapping of parameter names to resource IDs.

### _build_shader_parameters(material, texture_id_map) -> list[str]

Builds `shader_parameter/xxx = yyy` lines for the `.tres` file. Handles textures, bools, floats, and colors.

---

## Logging

The module uses Python's standard logging module. Enable debug logging to see detailed information about generation:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Log messages include:
- Auto-enabled features for each material
- Generated file paths and parameter counts
- Written file locations
