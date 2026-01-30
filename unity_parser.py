"""Parse Unity .mat files using regex.

Unity .mat files use YAML 1.1 with custom `!u!` tags that break standard YAML parsers.
This module extracts material data using regex patterns instead of a YAML library.

The module provides:
- TextureRef: Dataclass for texture references with GUID, scale, and offset
- Color: Dataclass for RGBA colors (supports HDR values)
- UnityMaterial: Dataclass containing all parsed material data
- parse_material(): Main entry point for parsing .mat file content
- parse_material_bytes(): Convenience wrapper for raw bytes

Unity Material YAML Structure:
    %YAML 1.1
    %TAG !u! tag:unity3d.com,2011:
    --- !u!21 &2100000
    Material:
      m_Name: MaterialName
      m_Shader: {fileID: 4800000, guid: <shader_guid_hex>, type: 3}
      m_TexEnvs:
        - _Albedo_Map:
            m_Texture: {fileID: 2800000, guid: <texture_guid_hex>, type: 3}
            m_Scale: {x: 1, y: 1}
            m_Offset: {x: 0, y: 0}
      m_Floats:
        - _Smoothness: 0.5
        - _Metallic: 0.0
      m_Colors:
        - _Color: {r: 1, g: 0.5, b: 0.25, a: 1}
        - _EmissionColor: {r: 0, g: 0, b: 0, a: 1}

Example:
    >>> from unity_parser import parse_material
    >>> content = Path("MyMaterial.mat").read_text()
    >>> material = parse_material(content)
    >>> print(material.name)
    'MyMaterial'
    >>> print(material.shader_guid)
    '0730dae39bc73f34796280af9875ce14'
    >>> print(material.floats.get("_Smoothness"))
    0.5
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TextureRef:
    """Reference to a texture in Unity's m_TexEnvs section.

    Represents a texture assignment in a Unity material, including the
    texture's GUID and UV transform parameters.

    Attributes:
        guid: Unity GUID of the texture asset (32 lowercase hex characters).
            This GUID is used to look up the actual texture filename via
            the GuidMap.texture_guid_to_name mapping.
        scale: Texture tiling scale as (x, y) tuple. Values > 1.0 tile the
            texture, values < 1.0 stretch it. Default is (1.0, 1.0).
        offset: Texture UV offset as (x, y) tuple. Shifts the texture in
            UV space. Default is (0.0, 0.0).

    Example:
        >>> tex_ref = TextureRef(
        ...     guid="0730dae39bc73f34796280af9875ce14",
        ...     scale=(2.0, 2.0),  # Tile 2x2
        ...     offset=(0.5, 0.0)  # Shift right by half
        ... )
    """

    guid: str
    scale: tuple[float, float] = (1.0, 1.0)
    offset: tuple[float, float] = (0.0, 0.0)


@dataclass
class Color:
    """RGBA color from Unity's m_Colors section.

    Represents a color property in a Unity material. All components are
    floats, typically in the 0.0 to 1.0 range, but can exceed this for
    HDR colors (emission, glow effects, etc.).

    Attributes:
        r: Red component. Range typically 0.0-1.0, but can be higher for HDR.
        g: Green component. Range typically 0.0-1.0, but can be higher for HDR.
        b: Blue component. Range typically 0.0-1.0, but can be higher for HDR.
        a: Alpha component. Range 0.0 (transparent) to 1.0 (opaque).

    Example:
        >>> color = Color(r=1.0, g=0.5, b=0.25, a=1.0)  # Orange, opaque
        >>> print(color.as_tuple())
        (1.0, 0.5, 0.25, 1.0)

        >>> # HDR emission color (values > 1.0)
        >>> emission = Color(r=2.5, g=1.0, b=0.0, a=1.0)
        >>> print(emission.has_rgb())
        True
    """

    r: float
    g: float
    b: float
    a: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        """Return color as (r, g, b, a) tuple.

        Returns:
            Tuple of (red, green, blue, alpha) float values.
        """
        return (self.r, self.g, self.b, self.a)

    def has_rgb(self) -> bool:
        """Check if color has any non-zero RGB values.

        Useful for detecting if a color property (like emission) is
        actually being used.

        Returns:
            True if any of r, g, b is non-zero, False if all are 0.0.
        """
        return self.r != 0.0 or self.g != 0.0 or self.b != 0.0


@dataclass
class UnityMaterial:
    """Parsed Unity material data.

    Contains all extracted data from a Unity .mat file needed for
    Godot material conversion. This is the output of parse_material().

    Attributes:
        name: Material name from m_Name field (e.g., "PolygonNature_Ground_01").
        shader_guid: GUID of the shader used by this material (32 hex chars).
            Used by shader_mapping to detect which Synty shader type this is.
        tex_envs: Texture references keyed by Unity property name.
            Common keys: "_Albedo_Map", "_Normal_Map", "_Emission_Map".
            Values are TextureRef instances with GUID and UV transform.
        floats: Float properties keyed by Unity property name.
            Common keys: "_Smoothness", "_Metallic", "_Cutoff", "_NormalStrength".
        colors: Color properties keyed by Unity property name.
            Common keys: "_Color", "_EmissionColor", "_TintColor".

    Example:
        >>> mat = parse_material(content)
        >>> print(mat.name)
        'PolygonNature_Ground_01'
        >>> print(mat.shader_guid)
        '0730dae39bc73f34796280af9875ce14'
        >>> print(len(mat.tex_envs))
        3
        >>> print(mat.floats.get("_Smoothness", 0.5))
        0.7
        >>> if "_Albedo_Map" in mat.tex_envs:
        ...     albedo_guid = mat.tex_envs["_Albedo_Map"].guid
    """

    name: str
    shader_guid: str
    tex_envs: dict[str, TextureRef] = field(default_factory=dict)
    floats: dict[str, float] = field(default_factory=dict)
    colors: dict[str, Color] = field(default_factory=dict)


# =============================================================================
# Regex Patterns for Unity Material Parsing
# =============================================================================
# Unity .mat files use YAML with custom tags that break standard parsers.
# These patterns extract the specific fields we need for Godot conversion.

# Matches the material name field
# Format: m_Name: MaterialName
# Example: "m_Name: PolygonNature_Ground_01"
# Captures: group(1) = "PolygonNature_Ground_01"
_NAME_PATTERN = re.compile(r"m_Name:\s*(.+?)\s*(?:\n|$)")

# Matches the shader GUID in the m_Shader reference
# Format: m_Shader: {fileID: 4800000, guid: <32-char-hex>, type: 3}
# Example: "m_Shader: {fileID: 4800000, guid: 0730dae39bc73f34796280af9875ce14, type: 3}"
# Captures: group(1) = "0730dae39bc73f34796280af9875ce14"
_SHADER_GUID_PATTERN = re.compile(
    r"m_Shader:\s*\{[^}]*guid:\s*([a-f0-9]+)",
    re.IGNORECASE,
)

# Matches float property entries in m_Floats section
# Format: - _PropertyName: <float_value>
# Examples:
#   "- _Smoothness: 0.5"
#   "- _Cutoff: 0.25"
#   "- _NormalStrength: 1.5e-05" (scientific notation)
# Captures: group(1) = property name, group(2) = float value
_FLOAT_PATTERN = re.compile(
    r"^\s*-\s+(_\w+):\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*$",
    re.MULTILINE,
)

# Matches color property entries in m_Colors section
# Format: - _PropertyName: {r: <float>, g: <float>, b: <float>, a: <float>}
# Examples:
#   "- _Color: {r: 1, g: 0.5, b: 0.25, a: 1}"
#   "- _EmissionColor: {r: 2.5, g: 1.0, b: 0, a: 1}" (HDR values > 1.0)
# Captures: group(1) = name, groups(2-5) = r, g, b, a values
_COLOR_PATTERN = re.compile(
    r"^\s*-\s+(_\w+):\s*\{r:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?),\s*"
    r"g:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?),\s*"
    r"b:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?),\s*"
    r"a:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*\}",
    re.MULTILINE,
)

# Matches texture property name line (start of texture entry in m_TexEnvs)
# Format: - _PropertyName:
# Examples:
#   "- _Albedo_Map:"
#   "- _Normal_Map:"
#   "- _Emission_Map:"
# Captures: group(1) = property name (e.g., "_Albedo_Map")
_TEX_PROPERTY_PATTERN = re.compile(r"^\s*-\s+(_\w+):\s*$", re.MULTILINE)

# Matches the texture GUID within a texture entry
# Format: m_Texture: {fileID: 2800000, guid: <32-char-hex>, type: 3}
# Example: "m_Texture: {fileID: 2800000, guid: abc123def456..., type: 3}"
# Captures: group(1) = texture GUID
# Note: Entries with fileID: 0 have no guid and mean "no texture assigned"
_TEX_GUID_PATTERN = re.compile(
    r"m_Texture:\s*\{[^}]*guid:\s*([a-f0-9]+)",
    re.IGNORECASE,
)

# Matches texture UV scale within a texture entry
# Format: m_Scale: {x: <float>, y: <float>}
# Example: "m_Scale: {x: 2, y: 2}" (tiles texture 2x2)
# Captures: group(1) = x scale, group(2) = y scale
_TEX_SCALE_PATTERN = re.compile(
    r"m_Scale:\s*\{x:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?),\s*"
    r"y:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*\}",
)

# Matches texture UV offset within a texture entry
# Format: m_Offset: {x: <float>, y: <float>}
# Example: "m_Offset: {x: 0.5, y: 0}" (shifts texture right by half)
# Captures: group(1) = x offset, group(2) = y offset
_TEX_OFFSET_PATTERN = re.compile(
    r"m_Offset:\s*\{x:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?),\s*"
    r"y:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*\}",
)


def _extract_material_section(content: str) -> str:
    """Extract the Material document from multi-document YAML.

    Unity .mat files may contain multiple YAML documents separated by `---`.
    Each document starts with a tag like `--- !u!21 &2100000` where:
    - `21` is the Unity class ID for Material
    - `2100000` is the local file ID

    This function extracts just the Material document for parsing.

    Args:
        content: Full .mat file content as a string.

    Returns:
        The Material section content starting from `--- !u!21`, or the
        original content if no document markers are found.

    Example:
        >>> content = '''%YAML 1.1
        ... --- !u!21 &2100000
        ... Material:
        ...   m_Name: MyMaterial'''
        >>> section = _extract_material_section(content)
        >>> "Material:" in section
        True
    """
    # Look for the !u!21 marker (Material class ID)
    # Pattern: --- !u!21 followed by the Material block
    material_match = re.search(
        r"---\s*!u!21[^\n]*\n((?:.*\n)*?)(?=---|\Z)",
        content,
        re.MULTILINE,
    )

    if material_match:
        return material_match.group(0)

    # Fallback: return entire content if no document markers
    return content


def _extract_material_name(content: str) -> str:
    """Extract material name from m_Name field.

    Args:
        content: Material section content from _extract_material_section.

    Returns:
        Material name with whitespace stripped, or "Unknown" if not found.

    Example:
        >>> _extract_material_name("m_Name: PolygonNature_Ground_01\\n")
        'PolygonNature_Ground_01'
    """
    match = _NAME_PATTERN.search(content)
    if match:
        return match.group(1).strip()

    logger.warning("Could not extract material name from content")
    return "Unknown"


def _extract_shader_guid(content: str) -> str:
    """Extract shader GUID from m_Shader field.

    The shader GUID identifies which Unity shader this material uses.
    This is used by shader_mapping.detect_shader_type() to determine
    the appropriate Godot shader.

    Args:
        content: Material section content from _extract_material_section.

    Returns:
        Shader GUID as lowercase 32-character hex string, or empty string
        if not found.

    Example:
        >>> content = "m_Shader: {fileID: 4800000, guid: abc123..., type: 3}"
        >>> _extract_shader_guid(content)
        'abc123...'
    """
    match = _SHADER_GUID_PATTERN.search(content)
    if match:
        return match.group(1).lower()

    logger.warning("Could not extract shader GUID from content")
    return ""


def _parse_floats(content: str) -> dict[str, float]:
    """Parse float properties from m_Floats section.

    Extracts all float properties like _Smoothness, _Metallic, _Cutoff, etc.
    Handles scientific notation (e.g., 1.5e-05) and negative values.

    Args:
        content: Material section content from _extract_material_section.

    Returns:
        Dictionary mapping property names (with underscore prefix) to float values.

    Example:
        >>> floats = _parse_floats("- _Smoothness: 0.7\\n- _Metallic: 0.0")
        >>> floats["_Smoothness"]
        0.7
        >>> floats["_Metallic"]
        0.0
    """
    floats: dict[str, float] = {}

    for match in _FLOAT_PATTERN.finditer(content):
        prop_name = match.group(1)
        try:
            value = float(match.group(2))
            floats[prop_name] = value
        except ValueError as e:
            logger.warning("Failed to parse float '%s': %s", match.group(2), e)

    return floats


def _parse_colors(content: str) -> dict[str, Color]:
    """Parse color properties from m_Colors section.

    Extracts all color properties like _Color, _EmissionColor, _TintColor, etc.
    Handles scientific notation and HDR values (components > 1.0).

    Args:
        content: Material section content from _extract_material_section.

    Returns:
        Dictionary mapping property names to Color objects.

    Example:
        >>> colors = _parse_colors("- _Color: {r: 1, g: 0.5, b: 0.25, a: 1}")
        >>> colors["_Color"].r
        1.0
        >>> colors["_Color"].as_tuple()
        (1.0, 0.5, 0.25, 1.0)
    """
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


def _parse_tex_envs(content: str) -> dict[str, TextureRef]:
    """Parse texture references from m_TexEnvs section.

    Extracts texture assignments with their GUIDs and UV transform settings.
    Each texture entry has this YAML structure:

        m_TexEnvs:
          - _Albedo_Map:
              m_Texture: {fileID: 2800000, guid: <32-char-hex>, type: 3}
              m_Scale: {x: 1, y: 1}
              m_Offset: {x: 0, y: 0}

    Entries with fileID: 0 or missing guid are skipped - these represent
    texture slots with no texture assigned.

    Args:
        content: Material section content from _extract_material_section.

    Returns:
        Dictionary mapping property names to TextureRef objects.
        Only includes textures that are actually assigned (have valid GUIDs).

    Example:
        >>> tex_envs = _parse_tex_envs(content)
        >>> if "_Albedo_Map" in tex_envs:
        ...     albedo = tex_envs["_Albedo_Map"]
        ...     print(albedo.guid)
        ...     print(albedo.scale)
        'abc123def456...'
        (1.0, 1.0)
    """
    tex_envs: dict[str, TextureRef] = {}

    # Find the m_TexEnvs section
    tex_envs_match = re.search(
        r"m_TexEnvs:\s*\n((?:\s+-.*\n|\s+\w.*\n)*)",
        content,
    )

    if not tex_envs_match:
        return tex_envs

    tex_section = tex_envs_match.group(0)

    # Find all texture property entries
    # Each entry starts with "- _PropertyName:" on its own line
    for prop_match in _TEX_PROPERTY_PATTERN.finditer(tex_section):
        prop_name = prop_match.group(1)
        prop_start = prop_match.end()

        # Find the next property or end of section
        next_prop = _TEX_PROPERTY_PATTERN.search(tex_section, prop_start)
        prop_end = next_prop.start() if next_prop else len(tex_section)

        # Extract the block for this property
        prop_block = tex_section[prop_start:prop_end]

        # Extract GUID
        guid_match = _TEX_GUID_PATTERN.search(prop_block)
        if not guid_match:
            # No texture assigned or fileID: 0
            continue

        guid = guid_match.group(1).lower()

        # Skip empty/invalid GUIDs (all zeros or very short)
        if len(guid) < 32 or guid == "0" * 32:
            continue

        # Extract scale (default 1, 1)
        scale = (1.0, 1.0)
        scale_match = _TEX_SCALE_PATTERN.search(prop_block)
        if scale_match:
            try:
                scale = (float(scale_match.group(1)), float(scale_match.group(2)))
            except ValueError:
                pass

        # Extract offset (default 0, 0)
        offset = (0.0, 0.0)
        offset_match = _TEX_OFFSET_PATTERN.search(prop_block)
        if offset_match:
            try:
                offset = (float(offset_match.group(1)), float(offset_match.group(2)))
            except ValueError:
                pass

        tex_envs[prop_name] = TextureRef(guid=guid, scale=scale, offset=offset)

    return tex_envs


def parse_material(content: str) -> UnityMaterial:
    """Parse a Unity .mat file into structured data.

    This is the main entry point for parsing Unity materials. It extracts
    the material name, shader reference, texture assignments, float
    properties, and color properties from the Unity YAML format.

    The parsing process:
    1. Extract the Material document from multi-document YAML
    2. Parse the m_Name field for the material name
    3. Parse the m_Shader field for the shader GUID
    4. Parse the m_TexEnvs section for texture references
    5. Parse the m_Floats section for float properties
    6. Parse the m_Colors section for color properties

    Args:
        content: Full content of a .mat file as a string (UTF-8).

    Returns:
        UnityMaterial with all extracted properties. Missing fields will
        have appropriate defaults (empty string for name/guid, empty dicts
        for properties).

    Example:
        >>> with open("PolygonNature_Ground_01.mat", "r", encoding="utf-8") as f:
        ...     content = f.read()
        >>> material = parse_material(content)
        >>> print(material.name)
        'PolygonNature_Ground_01'
        >>> print(material.shader_guid)
        '0730dae39bc73f34796280af9875ce14'
        >>> print(len(material.tex_envs))
        3
        >>> print(material.floats.get("_Smoothness", 0.5))
        0.7
        >>> if "_Albedo_Map" in material.tex_envs:
        ...     print(material.tex_envs["_Albedo_Map"].guid[:8] + "...")
        'abc123de...'
    """
    # Extract just the Material document if multiple documents exist
    material_section = _extract_material_section(content)

    # Parse each component
    name = _extract_material_name(material_section)
    shader_guid = _extract_shader_guid(material_section)
    tex_envs = _parse_tex_envs(material_section)
    floats = _parse_floats(material_section)
    colors = _parse_colors(material_section)

    logger.debug(
        "Parsed material '%s': shader=%s, textures=%d, floats=%d, colors=%d",
        name,
        shader_guid[:8] + "..." if shader_guid else "none",
        len(tex_envs),
        len(floats),
        len(colors),
    )

    return UnityMaterial(
        name=name,
        shader_guid=shader_guid,
        tex_envs=tex_envs,
        floats=floats,
        colors=colors,
    )


def parse_material_bytes(content: bytes, encoding: str = "utf-8") -> UnityMaterial:
    """Parse a Unity .mat file from raw bytes.

    Convenience wrapper for parsing material data extracted from a Unity
    package. The unity_package module provides raw bytes; this function
    handles the decoding before calling parse_material().

    Args:
        content: Raw bytes of the .mat file content.
        encoding: Text encoding to use for decoding. Default is "utf-8",
            which is standard for Unity YAML files.

    Returns:
        UnityMaterial with all extracted properties.

    Raises:
        UnicodeDecodeError: If content cannot be decoded with the given
            encoding. This is rare for valid Unity files.

    Example:
        >>> # Typical usage with unity_package
        >>> guid_map = extract_unitypackage(Path("Package.unitypackage"))
        >>> for guid in get_material_guids(guid_map):
        ...     content_bytes = guid_map.guid_to_content[guid]
        ...     material = parse_material_bytes(content_bytes)
        ...     print(f"Parsed: {material.name}")
    """
    text = content.decode(encoding)
    return parse_material(text)


# CLI for testing
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
    parser.add_argument(
        "mat_file",
        type=Path,
        help="Path to .mat file",
    )
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
