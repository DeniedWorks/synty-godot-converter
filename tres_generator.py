"""
TRES Generator Module for Synty Material Conversion.

This module generates Godot .tres ShaderMaterial files from converted materials.
It takes MappedMaterial objects and produces properly formatted .tres files
that can be directly imported by Godot.

Key Features:
    - Generates valid Godot .tres format with proper resource structure
    - Handles textures, floats, bools, and colors
    - Auto-enables features based on textures present
    - Proper number formatting (strips trailing zeros)

Example Usage:
    >>> from shader_mapping import MappedMaterial
    >>> from tres_generator import generate_tres, generate_and_write_tres
    >>>
    >>> # Generate .tres content as string
    >>> content = generate_tres(mapped_material, "res://shaders", "res://textures")
    >>> print(content)
    [gd_resource type="ShaderMaterial" load_steps=3 format=3]
    ...
    >>>
    >>> # Or generate and write directly to file
    >>> output_path = generate_and_write_tres(
    ...     material=mapped_material,
    ...     output_dir=Path("output/materials"),
    ...     shader_base="res://shaders",
    ...     texture_base="res://textures"
    ... )

Module Structure:
    - AUTO_ENABLE_RULES: Automatic feature enable rules based on texture presence
    - format_float(), format_color(): Number formatting for .tres output
    - sanitize_filename(): Make material names safe for filenames
    - generate_tres(): Main entry point for .tres content generation
    - write_tres_file(): Write content to disk
    - generate_and_write_tres(): Convenience function combining both
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shader_mapping import MappedMaterial

logger = logging.getLogger(__name__)

# =============================================================================
# AUTO-ENABLE FEATURE RULES
# =============================================================================

# Auto-enable rules: When certain textures are present, automatically
# enable the corresponding shader feature. This ensures that when a texture
# is assigned, the shader knows to use it.
#
# The keys are texture parameter names, the values are the corresponding
# boolean enable parameters in the shader.
#
# Example: If "leaf_normal" texture is set, "enable_leaf_normal" = true
#
# How it works:
#   1. During .tres generation, we scan all assigned textures
#   2. For each texture that matches a key in AUTO_ENABLE_RULES,
#      we automatically set the corresponding bool parameter to true
#   3. This saves users from manually enabling features after assigning textures
AUTO_ENABLE_RULES: dict[str, str] = {
    "leaf_normal": "enable_leaf_normal",        # Foliage leaf normal maps
    "trunk_normal": "enable_trunk_normal",      # Foliage trunk normal maps
    "normal_texture": "enable_normal_texture",  # General normal mapping
    "emission_texture": "enable_emission_texture",  # Emission/glow effects
    "ao_texture": "enable_ambient_occlusion",   # Ambient occlusion maps
}

# Prefix patterns that enable triplanar projection.
# If any texture parameter starts with these prefixes, triplanar is enabled.
# Triplanar projection maps textures based on world normals rather than UVs,
# useful for terrain and rock meshes that lack proper UV mapping.
TRIPLANAR_PREFIXES: tuple[str, ...] = ("triplanar_texture_",)


# =============================================================================
# NUMBER FORMATTING
# =============================================================================

def format_float(value: float) -> str:
    """
    Format a float value for .tres output.

    Uses up to 6 decimal places and strips trailing zeros for cleaner output.
    Always includes at least one decimal place for consistency with Godot's
    resource format.

    Args:
        value: Float value to format.

    Returns:
        Formatted string with minimal decimal places.

    Examples:
        >>> format_float(0.5)
        '0.5'
        >>> format_float(0.123456789)
        '0.123457'
        >>> format_float(1.0)
        '1.0'
        >>> format_float(0.0)
        '0.0'
        >>> format_float(0.500000)
        '0.5'
    """
    # Format with 6 decimal places, then strip trailing zeros
    formatted = f"{value:.6f}".rstrip("0").rstrip(".")

    # Ensure we have at least one digit after decimal for consistency
    if "." not in formatted:
        formatted = f"{formatted}.0"

    return formatted


def format_color(r: float, g: float, b: float, a: float) -> str:
    """
    Format an RGBA color for .tres output.

    Produces Godot Color() constructor syntax with minimal decimal precision.
    Maintains at least one decimal place for each component.

    Args:
        r: Red component (0.0-1.0).
        g: Green component (0.0-1.0).
        b: Blue component (0.0-1.0).
        a: Alpha component (0.0-1.0).

    Returns:
        Formatted color string in Godot syntax.

    Examples:
        >>> format_color(1.0, 0.5, 0.25, 1.0)
        'Color(1.0, 0.5, 0.25, 1.0)'
        >>> format_color(0.0, 0.0, 0.0, 1.0)
        'Color(0.0, 0.0, 0.0, 1.0)'
        >>> format_color(0.333333, 0.666666, 1.0, 0.5)
        'Color(0.333333, 0.666666, 1.0, 0.5)'
    """
    # Format each component with 3 decimal places minimum
    def fmt(v: float) -> str:
        formatted = f"{v:.6f}".rstrip("0")
        # Ensure at least 3 decimal places for precision
        if "." in formatted:
            integer, decimal = formatted.split(".")
            if len(decimal) < 1:
                decimal = decimal.ljust(1, "0")
            return f"{integer}.{decimal}"
        return f"{formatted}.0"

    return f"Color({fmt(r)}, {fmt(g)}, {fmt(b)}, {fmt(a)})"


# =============================================================================
# FILENAME UTILITIES
# =============================================================================

def sanitize_filename(name: str) -> str:
    """
    Make a material name safe for use as a filename.

    Removes or replaces characters that are invalid in filenames across
    Windows, macOS, and Linux. Also normalizes multiple underscores and
    trims leading/trailing whitespace.

    Args:
        name: Material name to sanitize.

    Returns:
        Sanitized filename-safe string. Returns "unnamed_material" if the
        input results in an empty string after sanitization.

    Examples:
        >>> sanitize_filename('Normal_Mat')
        'Normal_Mat'
        >>> sanitize_filename('Mat:With/Bad<Chars>')
        'Mat_With_Bad_Chars'
        >>> sanitize_filename('Material "Special"')
        'Material_Special'
        >>> sanitize_filename('  __spaced__  ')
        'spaced'
        >>> sanitize_filename('path\\to\\material')
        'path_to_material'
        >>> sanitize_filename('')
        'unnamed_material'
        >>> sanitize_filename('???')
        'unnamed_material'

    Invalid characters replaced:
        < > : " / \\ | ? * and control characters (0x00-0x1f)
    """
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


# =============================================================================
# AUTO-ENABLE FEATURE DETECTION
# =============================================================================

def _auto_enable_features(material: "MappedMaterial") -> dict[str, bool]:
    """
    Determine additional bool parameters to enable based on textures present.

    Scans the material's texture assignments and automatically enables
    corresponding shader features using AUTO_ENABLE_RULES and TRIPLANAR_PREFIXES.

    Args:
        material: The mapped material to analyze.

    Returns:
        Dictionary of auto-enabled bool parameters. Keys are shader parameter
        names, values are always True (features to enable).

    Example:
        If material has textures={'leaf_normal': 'Leaf_Normal.png'},
        returns {'enable_leaf_normal': True}
    """
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


# =============================================================================
# RESOURCE BUILDING
# =============================================================================

def _build_ext_resources(
    shader_path: str,
    textures: dict[str, str],
    texture_base: str
) -> tuple[list[str], dict[str, str]]:
    """
    Build [ext_resource] lines for the .tres file.

    Creates external resource references for the shader and all textures.
    The shader is always assigned ID "1", textures get sequential IDs starting at "2".

    Args:
        shader_path: Full resource path to the shader file (e.g., "res://shaders/polygon.gdshader").
        textures: Mapping of godot_param -> texture_filename.
        texture_base: Base resource path for textures (e.g., "res://textures").

    Returns:
        Tuple of (resource_lines, param_to_id_map) where:
        - resource_lines: List of [ext_resource ...] lines ready for .tres file
        - param_to_id_map: Maps godot_param names to their resource IDs

    Example:
        >>> lines, id_map = _build_ext_resources(
        ...     "res://shaders/polygon.gdshader",
        ...     {"albedo_texture": "Ground_01.png"},
        ...     "res://textures"
        ... )
        >>> print(lines[0])
        [ext_resource type="Shader" path="res://shaders/polygon.gdshader" id="1"]
        >>> print(lines[1])
        [ext_resource type="Texture2D" path="res://textures/Ground_01.png" id="2"]
        >>> print(id_map)
        {'albedo_texture': '2'}
    """
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


def _build_shader_parameters(
    material: "MappedMaterial",
    texture_id_map: dict[str, str]
) -> list[str]:
    """
    Build shader_parameter/xxx = yyy lines for the .tres file.

    Creates shader parameter assignments for textures, bools, floats, and colors.
    Automatically enables features based on texture presence.

    Args:
        material: The mapped material containing parameter values.
        texture_id_map: Maps godot_param to resource ID for textures.

    Returns:
        List of shader_parameter lines ready for .tres file.

    Example output lines:
        shader_parameter/albedo_texture = ExtResource("2")
        shader_parameter/enable_normal_texture = true
        shader_parameter/metallic = 0.5
        shader_parameter/albedo_color = Color(1.0, 0.9, 0.8, 1.0)
    """
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


# =============================================================================
# MAIN GENERATION FUNCTION
# =============================================================================

def generate_tres(
    material: "MappedMaterial",
    shader_base: str = "res://shaders",
    texture_base: str = "res://textures"
) -> str:
    """Generate Godot .tres ShaderMaterial resource content.

    Creates a complete .tres file as a string, ready to be written to disk.
    This is the main entry point for .tres generation.

    The generated file includes:
        - Resource header with type and load_steps
        - External resource references (shader and textures)
        - Resource section with shader assignment and all parameters

    Args:
        material: MappedMaterial with shader and property data.
        shader_base: Base path for shader references (default: "res://shaders").
        texture_base: Base path for texture references (default: "res://textures").

    Returns:
        Complete .tres file content as string.

    Example:
        >>> content = generate_tres(mapped_material)
        >>> print(content[:200])
        [gd_resource type="ShaderMaterial" load_steps=3 format=3]

        [ext_resource type="Shader" path="res://shaders/polygon.gdshader" id="1"]
        [ext_resource type="Texture2D" path="res://textures/Ground_01.png" id="2"]
        ...

    Full example output:
        [gd_resource type="ShaderMaterial" load_steps=3 format=3]

        [ext_resource type="Shader" path="res://shaders/foliage.gdshader" id="1"]
        [ext_resource type="Texture2D" path="res://textures/Fern_1.tga" id="2"]

        [resource]
        shader = ExtResource("1")
        shader_parameter/leaf_color = ExtResource("2")
        shader_parameter/enable_breeze = true
        shader_parameter/alpha_clip_threshold = 0.5
        shader_parameter/leaf_base_color = Color(1.0, 0.9, 0.8, 1.0)
    """
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

    logger.info(
        "Generated .tres for material %s (shader=%s, textures=%d, params=%d)",
        material.name, material.shader_file,
        len(material.textures), len(shader_params)
    )

    return content


# =============================================================================
# FILE WRITING
# =============================================================================

def write_tres_file(content: str, output_path: Path) -> None:
    """
    Write .tres content to a file, creating directories as needed.

    Args:
        content: The .tres file content to write.
        output_path: Path where the file should be written.

    Raises:
        OSError: If the directory cannot be created or file cannot be written.

    Example:
        >>> content = generate_tres(mapped_material)
        >>> write_tres_file(content, Path("output/materials/Crystal_Mat_01.tres"))
    """
    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write the file
    output_path.write_text(content, encoding="utf-8")

    logger.info("Wrote .tres file: %s", output_path)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def generate_and_write_tres(
    material: "MappedMaterial",
    output_dir: Path,
    shader_base: str = "res://shaders",
    texture_base: str = "res://textures"
) -> Path:
    """
    Generate and write a .tres file for a material.

    Convenience function that combines generation and writing. Automatically
    sanitizes the material name for use as a filename.

    Args:
        material: The mapped material to convert.
        output_dir: Directory to write the .tres file to.
        shader_base: Resource path base for shaders.
        texture_base: Resource path base for textures.

    Returns:
        Path to the written .tres file.

    Raises:
        OSError: If the directory cannot be created or file cannot be written.

    Example:
        >>> from pathlib import Path
        >>> output = generate_and_write_tres(
        ...     material=mapped_material,
        ...     output_dir=Path("output/materials"),
        ...     shader_base="res://shaders",
        ...     texture_base="res://textures"
        ... )
        >>> print(output)
        output/materials/Crystal_Mat_01.tres
    """
    # Generate content
    content = generate_tres(material, shader_base, texture_base)

    # Build output path
    safe_name = sanitize_filename(material.name)
    output_path = output_dir / f"{safe_name}.tres"

    # Write file
    write_tres_file(content, output_path)

    return output_path


# =============================================================================
# CLI ENTRY POINT (FOR TESTING)
# =============================================================================

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

    print("=" * 60)
    print("TRES Generator Test")
    print("=" * 60)
    print()

    # Generate .tres content
    content = generate_tres(
        test_material,  # type: ignore
        shader_base="res://shaders",
        texture_base="res://textures"
    )

    print("Generated .tres content:")
    print("-" * 60)
    print(content)
    print("-" * 60)

    # Test formatting functions
    print()
    print("Format tests:")
    print(f"  format_float(0.5) = {format_float(0.5)}")
    print(f"  format_float(0.123456789) = {format_float(0.123456789)}")
    print(f"  format_float(1.0) = {format_float(1.0)}")
    print(f"  format_float(0.0) = {format_float(0.0)}")
    print(f"  format_color(1.0, 0.5, 0.25, 1.0) = {format_color(1.0, 0.5, 0.25, 1.0)}")

    print()
    print("Sanitize filename tests:")
    print(f"  'Normal_Mat' = '{sanitize_filename('Normal_Mat')}'")
    print(f"  'Mat:With/Bad<Chars>' = '{sanitize_filename('Mat:With/Bad<Chars>')}'")
    print(f"  '  __spaced__  ' = '{sanitize_filename('  __spaced__  ')}'")
    print(f"  '' = '{sanitize_filename('')}'")

    print()
    print("Test complete.")
