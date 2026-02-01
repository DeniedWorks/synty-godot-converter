"""Parse Synty's MaterialList.txt to extract mesh-to-material mappings.

This module parses the MaterialList.txt file found in Synty SourceFiles folders,
extracting information about which materials are used by each mesh. The parsed
data can be converted to JSON for use by the Godot converter script.

MaterialList.txt Format Example:
    Prefab Name: SM_Prop_Crystal_01
        Mesh Name: SM_Prop_Crystal_01
            Slot: Crystal_Mat_01 (Uses custom shader)
            Slot: PolygonNatureBiomes_EnchantedForest_Mat_01_A (TexName)
        Mesh Name: SM_Prop_Crystal_01_LOD1
            Slot: Crystal_Mat_01 (Uses custom shader)

    Prefab Name: SM_Env_Tree_01
        Mesh Name: SM_Env_Tree_01
            Slot: Foliage_Mat (Uses custom shader)
            Slot: Trunk_Mat (Bark_01)

Structure:
    - Prefab Name: Top-level container (Unity prefab)
    - Mesh Name: Individual mesh within the prefab
    - Slot: Material assignment with either texture name in parens or "(Uses custom shader)"

Usage Example:
    >>> from pathlib import Path
    >>> from material_list import parse_material_list, generate_mesh_material_mapping_json
    >>>
    >>> # Parse the MaterialList.txt file
    >>> prefabs = parse_material_list(Path("SourceFiles/MaterialList.txt"))
    >>> print(f"Found {len(prefabs)} prefabs")
    Found 150 prefabs
    >>>
    >>> # Generate JSON for Godot converter
    >>> generate_mesh_material_mapping_json(prefabs, Path("mesh_material_mapping.json"))
    >>>
    >>> # Or get data structures for custom processing
    >>> from material_list import get_all_material_names, get_custom_shader_materials
    >>> all_mats = get_all_material_names(prefabs)
    >>> custom_mats = get_custom_shader_materials(prefabs)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class MaterialSlot:
    """Single material slot assignment.

    Represents one material applied to a mesh slot, as parsed from
    MaterialList.txt. Each mesh can have multiple material slots.

    Attributes:
        material_name: Name of the material (e.g., "Crystal_Mat_01").
            This is the text before the parentheses in the Slot: line.
        texture_name: Optional texture name hint from parenthetical note.
            None if the material uses a custom shader. For standard materials,
            this contains the texture name (e.g., "Bark_01").
        uses_custom_shader: True if marked "(Uses custom shader)" in the file.
            Custom shader materials require Unity package parsing to get
            full texture and property information.

    Example:
        >>> # Custom shader material (no texture info available)
        >>> slot = MaterialSlot("Crystal_Mat_01", None, True)
        >>> print(f"Material: {slot.material_name}, Custom: {slot.uses_custom_shader}")
        Material: Crystal_Mat_01, Custom: True
        >>>
        >>> # Standard material with texture hint
        >>> slot = MaterialSlot("Trunk_Mat", "Bark_01", False)
        >>> print(f"Material: {slot.material_name}, Texture: {slot.texture_name}")
        Material: Trunk_Mat, Texture: Bark_01
    """

    material_name: str
    texture_name: str | None = None
    uses_custom_shader: bool = False


@dataclass
class MeshMaterials:
    """Mesh with its material slot assignments.

    Represents a mesh and all materials assigned to its surface slots.
    Material order matters - slot indices must match surface indices.

    Attributes:
        mesh_name: Name of the mesh (e.g., "SM_Prop_Crystal_01_LOD0").
            This corresponds to the MeshInstance3D node name in Godot.
        slots: Ordered list of material slots. Index 0 = surface 0, etc.
            Empty list if no materials are assigned.

    Example:
        >>> mesh = MeshMaterials(
        ...     mesh_name="SM_Env_Rock_01",
        ...     slots=[
        ...         MaterialSlot("Rock_Mat", "Rock_01", False),
        ...         MaterialSlot("Moss_Mat", "Moss_01", False),
        ...     ]
        ... )
        >>> print(f"Mesh: {mesh.mesh_name}, Surfaces: {len(mesh.slots)}")
        Mesh: SM_Env_Rock_01, Surfaces: 2
    """

    mesh_name: str
    slots: list[MaterialSlot] = field(default_factory=list)


@dataclass
class PrefabMaterials:
    """Prefab container with all its meshes.

    Represents a Unity prefab and all meshes contained within it.
    A prefab may contain multiple meshes with different LOD levels.

    Attributes:
        prefab_name: Name of the prefab (e.g., "SM_Prop_Crystal_01").
            This is typically the asset name without LOD suffix.
        meshes: List of meshes in this prefab with their materials.

    Example:
        >>> prefab = PrefabMaterials(
        ...     prefab_name="SM_Prop_Crystal_01",
        ...     meshes=[
        ...         MeshMaterials("SM_Prop_Crystal_01", [...]),
        ...         MeshMaterials("SM_Prop_Crystal_01_LOD1", [...]),
        ...         MeshMaterials("SM_Prop_Crystal_01_LOD2", [...]),
        ...     ]
        ... )
        >>> print(f"Prefab: {prefab.prefab_name}, LOD levels: {len(prefab.meshes)}")
        Prefab: SM_Prop_Crystal_01, LOD levels: 3
    """

    prefab_name: str
    meshes: list[MeshMaterials] = field(default_factory=list)


# Regex patterns for parsing MaterialList.txt
_PREFAB_PATTERN = re.compile(r"^\s*Prefab Name:\s*(.+?)\s*$")
_MESH_PATTERN = re.compile(r"^\s*Mesh Name:\s*(.+?)\s*$")
_SLOT_PATTERN = re.compile(r"^\s*Slot:\s*(.+?)\s*\((.+?)\)\s*$")


def _parse_slot_line(line: str) -> MaterialSlot | None:
    """Parse a single Slot: line into a MaterialSlot.

    Handles both standard materials with texture hints and custom shader
    materials. The format is: "Slot: MaterialName (TextureOrCustomShader)"

    Args:
        line: A line from MaterialList.txt containing "Slot:".

    Returns:
        MaterialSlot if successfully parsed, None if parsing fails.

    Examples:
        >>> _parse_slot_line("            Slot: Rock_Mat (Rock_01)")
        MaterialSlot(material_name='Rock_Mat', texture_name='Rock_01', uses_custom_shader=False)
        >>> _parse_slot_line("            Slot: Crystal_Mat (Uses custom shader)")
        MaterialSlot(material_name='Crystal_Mat', texture_name=None, uses_custom_shader=True)
    """
    match = _SLOT_PATTERN.match(line)
    if not match:
        logger.warning(f"Failed to parse slot line: {line.strip()!r}")
        return None

    material_name = match.group(1).strip()
    parentheses_content = match.group(2).strip()

    if parentheses_content.lower() == "uses custom shader":
        return MaterialSlot(
            material_name=material_name,
            texture_name=None,
            uses_custom_shader=True,
        )
    else:
        return MaterialSlot(
            material_name=material_name,
            texture_name=parentheses_content,
            uses_custom_shader=False,
        )


def parse_material_list(path: Path) -> list[PrefabMaterials]:
    """Parse a MaterialList.txt file into structured data.

    Reads a Synty MaterialList.txt file and extracts all prefab, mesh,
    and material information into a hierarchical data structure.

    Args:
        path: Path to the MaterialList.txt file.

    Returns:
        List of PrefabMaterials, each containing meshes and their material slots.
        Preserves the order from the source file.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is empty or has no valid entries.

    Example:
        >>> prefabs = parse_material_list(Path("SourceFiles/MaterialList.txt"))
        >>> for prefab in prefabs[:2]:
        ...     print(f"Prefab: {prefab.prefab_name}")
        ...     for mesh in prefab.meshes:
        ...         print(f"  Mesh: {mesh.mesh_name}")
        ...         for slot in mesh.slots:
        ...             print(f"    Slot: {slot.material_name}")
        Prefab: SM_Prop_Crystal_01
          Mesh: SM_Prop_Crystal_01
            Slot: Crystal_Mat_01
        Prefab: SM_Env_Tree_01
          Mesh: SM_Env_Tree_01
            Slot: Foliage_Mat
            Slot: Trunk_Mat

    Input file format:
        Prefab Name: SM_Prop_Crystal_01
            Mesh Name: SM_Prop_Crystal_01
                Slot: Crystal_Mat_01 (Uses custom shader)
            Mesh Name: SM_Prop_Crystal_01_LOD1
                Slot: Crystal_Mat_01 (Uses custom shader)
    """
    if not path.exists():
        raise FileNotFoundError(f"MaterialList.txt not found: {path}")

    prefabs: list[PrefabMaterials] = []
    current_prefab: PrefabMaterials | None = None
    current_mesh: MeshMaterials | None = None

    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            # Skip empty lines
            if not line.strip():
                continue

            # Check for Prefab Name
            prefab_match = _PREFAB_PATTERN.match(line)
            if prefab_match:
                # Save previous prefab if exists
                if current_prefab is not None:
                    if current_mesh is not None:
                        current_prefab.meshes.append(current_mesh)
                    prefabs.append(current_prefab)

                current_prefab = PrefabMaterials(prefab_name=prefab_match.group(1))
                current_mesh = None
                logger.debug(f"Line {line_num}: Found prefab: {current_prefab.prefab_name}")
                continue

            # Check for Mesh Name
            mesh_match = _MESH_PATTERN.match(line)
            if mesh_match:
                if current_prefab is None:
                    logger.warning(
                        f"Line {line_num}: Mesh found outside prefab block: {line.strip()!r}"
                    )
                    continue

                # Save previous mesh if exists
                if current_mesh is not None:
                    current_prefab.meshes.append(current_mesh)

                current_mesh = MeshMaterials(mesh_name=mesh_match.group(1))
                logger.debug(f"Line {line_num}: Found mesh: {current_mesh.mesh_name}")
                continue

            # Check for Slot
            if "Slot:" in line:
                if current_mesh is None:
                    logger.warning(
                        f"Line {line_num}: Slot found outside mesh block: {line.strip()!r}"
                    )
                    continue

                slot = _parse_slot_line(line)
                if slot:
                    current_mesh.slots.append(slot)
                    logger.debug(
                        f"Line {line_num}: Found slot: {slot.material_name} "
                        f"(custom={slot.uses_custom_shader})"
                    )
                continue

    # Save final prefab/mesh
    if current_prefab is not None:
        if current_mesh is not None:
            current_prefab.meshes.append(current_mesh)
        prefabs.append(current_prefab)

    if not prefabs:
        raise ValueError(f"No valid prefab entries found in: {path}")

    logger.debug(
        f"Parsed MaterialList.txt: {len(prefabs)} prefabs, "
        f"{sum(len(p.meshes) for p in prefabs)} meshes"
    )
    return prefabs


def get_mesh_to_materials_map(prefabs: list[PrefabMaterials]) -> dict[str, list[str]]:
    """Flatten prefab data to a simple mesh_name -> [material_names] mapping.

    Converts the hierarchical prefab structure to a flat dictionary suitable
    for JSON serialization. Material order is preserved to maintain correct
    surface index alignment.

    Args:
        prefabs: List of PrefabMaterials from parse_material_list().

    Returns:
        Dictionary mapping mesh names to ordered lists of material names.
        Order matches the original Slot: entries in MaterialList.txt.

    Example:
        >>> prefabs = parse_material_list(Path("MaterialList.txt"))
        >>> mesh_map = get_mesh_to_materials_map(prefabs)
        >>> print(mesh_map["SM_Prop_Crystal_01"])
        ['Crystal_Mat_01']
        >>> print(mesh_map["SM_Env_Tree_01"])
        ['Foliage_Mat', 'Trunk_Mat']

    Note:
        If duplicate mesh names are found, a warning is logged and the
        later entry overwrites the earlier one.
    """
    result: dict[str, list[str]] = {}

    for prefab in prefabs:
        for mesh in prefab.meshes:
            material_names = [slot.material_name for slot in mesh.slots]
            if mesh.mesh_name in result:
                logger.debug(
                    f"Duplicate mesh name found: {mesh.mesh_name!r}. "
                    f"Previous materials: {result[mesh.mesh_name]}, "
                    f"New materials: {material_names}. Using new values."
                )
            result[mesh.mesh_name] = material_names

    logger.debug(f"Built mesh-to-materials map: {len(result)} meshes")
    return result


def generate_mesh_material_mapping_json(
    prefabs: list[PrefabMaterials],
    output_path: Path,
    *,
    indent: int = 2,
) -> None:
    """Generate mesh_material_mapping.json for Godot conversion.

    Creates a JSON file mapping mesh names to their material names.
    This file is consumed by the GDScript converter (godot_converter.gd)
    to apply the correct materials to each mesh surface.

    Args:
        prefabs: List of PrefabMaterials from parse_material_list().
        output_path: Path where the JSON file will be written.
        indent: JSON indentation level (default 2 spaces).

    Raises:
        OSError: If the file cannot be written.

    Example:
        >>> prefabs = parse_material_list(Path("MaterialList.txt"))
        >>> generate_mesh_material_mapping_json(prefabs, Path("mesh_material_mapping.json"))

    Output JSON format:
        {
          "SM_Prop_Crystal_01": ["Crystal_Mat_01"],
          "SM_Env_Tree_01": ["Foliage_Mat", "Trunk_Mat"],
          "SM_Env_Rock_01": ["Rock_Mat"]
        }
    """
    mesh_map = get_mesh_to_materials_map(prefabs)

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Merge with existing mapping if file exists (supports multi-pack workflows)
    if output_path.exists():
        try:
            with output_path.open("r", encoding="utf-8") as f:
                existing_map = json.load(f)
            # Merge: new pack entries take precedence for duplicates
            existing_map.update(mesh_map)
            mesh_map = existing_map
            logger.debug(f"Merged with existing mapping: {len(existing_map)} total meshes")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not read existing mapping, overwriting: {e}")

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(mesh_map, f, indent=indent, ensure_ascii=False)

    logger.debug(f"Wrote mesh material mapping to: {output_path}")


def get_all_material_names(prefabs: list[PrefabMaterials]) -> set[str]:
    """Extract all unique material names from parsed prefabs.

    Useful for validating that all referenced materials exist, or for
    generating a list of materials that need to be converted.

    Args:
        prefabs: List of PrefabMaterials from parse_material_list().

    Returns:
        Set of unique material names (unordered).

    Example:
        >>> prefabs = parse_material_list(Path("MaterialList.txt"))
        >>> materials = get_all_material_names(prefabs)
        >>> print(f"Found {len(materials)} unique materials")
        Found 45 unique materials
        >>> print(sorted(materials)[:3])
        ['Crystal_Mat_01', 'Foliage_Mat', 'Ground_Mat']
    """
    materials: set[str] = set()
    for prefab in prefabs:
        for mesh in prefab.meshes:
            for slot in mesh.slots:
                materials.add(slot.material_name)
    return materials


def get_custom_shader_materials(prefabs: list[PrefabMaterials]) -> set[str]:
    """Extract material names that use custom shaders.

    These materials require Unity package parsing to get full details
    since MaterialList.txt doesn't include texture information for them.
    Custom shader materials are marked with "(Uses custom shader)" in the file.

    Args:
        prefabs: List of PrefabMaterials from parse_material_list().

    Returns:
        Set of material names that use custom shaders.

    Example:
        >>> prefabs = parse_material_list(Path("MaterialList.txt"))
        >>> custom = get_custom_shader_materials(prefabs)
        >>> print(f"Found {len(custom)} custom shader materials")
        Found 12 custom shader materials
        >>> print(sorted(custom)[:3])
        ['Crystal_Mat_01', 'Water_Mat', 'Glass_Mat']
    """
    materials: set[str] = set()
    for prefab in prefabs:
        for mesh in prefab.meshes:
            for slot in mesh.slots:
                if slot.uses_custom_shader:
                    materials.add(slot.material_name)
    return materials


def get_texture_mapped_materials(
    prefabs: list[PrefabMaterials],
) -> dict[str, str]:
    """Extract material name -> texture name mapping for standard materials.

    Only includes materials where texture information is available
    (i.e., not custom shader materials). Useful for simple material
    conversion when Unity package parsing is not needed.

    Args:
        prefabs: List of PrefabMaterials from parse_material_list().

    Returns:
        Dictionary mapping material names to their texture names.
        Only includes materials with texture_name set.

    Example:
        >>> prefabs = parse_material_list(Path("MaterialList.txt"))
        >>> tex_map = get_texture_mapped_materials(prefabs)
        >>> print(tex_map.get("Ground_Mat"))
        'Ground_01'
        >>> print(tex_map.get("Crystal_Mat_01"))  # Custom shader, not included
        None

    Note:
        If a material appears with different textures, a warning is logged
        and the first occurrence is kept.
    """
    result: dict[str, str] = {}
    for prefab in prefabs:
        for mesh in prefab.meshes:
            for slot in mesh.slots:
                if slot.texture_name is not None and not slot.uses_custom_shader:
                    if slot.material_name in result:
                        existing = result[slot.material_name]
                        if existing != slot.texture_name:
                            logger.warning(
                                f"Material {slot.material_name!r} has multiple textures: "
                                f"{existing!r} vs {slot.texture_name!r}. Keeping first."
                            )
                    else:
                        result[slot.material_name] = slot.texture_name
    return result


# CLI entry point for standalone testing
if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Parse Synty MaterialList.txt and optionally generate JSON output."
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="Path to MaterialList.txt",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output path for mesh_material_mapping.json",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print summary statistics",
    )
    args = parser.parse_args()

    try:
        prefabs = parse_material_list(args.input_file)

        if args.summary:
            all_materials = get_all_material_names(prefabs)
            custom_materials = get_custom_shader_materials(prefabs)
            texture_materials = get_texture_mapped_materials(prefabs)

            print(f"\n=== MaterialList.txt Summary ===")
            print(f"Prefabs: {len(prefabs)}")
            print(f"Total meshes: {sum(len(p.meshes) for p in prefabs)}")
            print(f"Unique materials: {len(all_materials)}")
            print(f"Custom shader materials: {len(custom_materials)}")
            print(f"Texture-mapped materials: {len(texture_materials)}")

            if custom_materials:
                print(f"\nCustom shader materials:")
                for mat in sorted(custom_materials):
                    print(f"  - {mat}")

        if args.output:
            generate_mesh_material_mapping_json(prefabs, args.output)
            print(f"\nWrote: {args.output}")

    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
