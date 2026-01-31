#!/usr/bin/env python3
"""
Analyze MaterialList*.txt files to find prefabs with multiple material slots.

Usage: python analyze_multi_materials.py "path/to/MaterialList.txt"

Outputs JSON with information about prefabs that have 2+ material slots.
"""

import argparse
import json
import re
import sys
from pathlib import Path


def parse_slot_line(line: str) -> dict:
    """
    Parse a Slot: line to extract material info.

    Formats:
    - "MaterialName (TextureName)" - standard texture
    - "MaterialName (Uses custom shader)" - custom shader
    - "MaterialName (No Albedo Texture)" - no texture

    Returns dict with name, uses_custom_shader, texture
    """
    line = line.strip()
    if not line.startswith("Slot:"):
        return None

    # Remove "Slot: " prefix
    content = line[5:].strip()

    # Match pattern: MaterialName (something)
    match = re.match(r'^(.+?)\s*\((.+?)\)$', content)
    if not match:
        # No parentheses - just material name
        return {
            "name": content,
            "uses_custom_shader": False,
            "texture": None
        }

    material_name = match.group(1).strip()
    paren_content = match.group(2).strip()

    uses_custom_shader = paren_content.lower() == "uses custom shader"
    no_texture = paren_content.lower() == "no albedo texture"

    texture = None
    if not uses_custom_shader and not no_texture:
        texture = paren_content

    return {
        "name": material_name,
        "uses_custom_shader": uses_custom_shader,
        "texture": texture
    }


def parse_material_list(file_path: Path) -> dict:
    """
    Parse a MaterialList.txt file and return structured data.

    Returns dict with pack info and list of multi-material prefabs.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        return {
            "error": f"Failed to read file: {e}",
            "pack_name": None,
            "file_path": str(file_path),
            "multi_material_prefabs": [],
            "total_prefabs": 0,
            "multi_material_count": 0
        }

    # Extract pack name from filename
    # e.g., "MaterialList_PolygonNature.txt" -> "PolygonNature"
    pack_name = file_path.stem
    if pack_name.startswith("MaterialList_"):
        pack_name = pack_name[13:]

    prefabs = {}  # prefab_name -> list of materials
    current_prefab = None

    for line in lines:
        line_stripped = line.strip()

        if line_stripped.startswith("Prefab Name:"):
            current_prefab = line_stripped[12:].strip()
            if current_prefab not in prefabs:
                prefabs[current_prefab] = []

        elif line_stripped.startswith("Slot:") and current_prefab:
            slot_info = parse_slot_line(line_stripped)
            if slot_info:
                # Avoid duplicate materials in same prefab
                existing_names = [m["name"] for m in prefabs[current_prefab]]
                if slot_info["name"] not in existing_names:
                    prefabs[current_prefab].append(slot_info)

    # Filter to prefabs with 2+ materials
    multi_material_prefabs = []
    for prefab_name, materials in prefabs.items():
        if len(materials) >= 2:
            multi_material_prefabs.append({
                "prefab_name": prefab_name,
                "materials": materials
            })

    # Sort by prefab name for consistent output
    multi_material_prefabs.sort(key=lambda x: x["prefab_name"])

    return {
        "pack_name": pack_name,
        "file_path": str(file_path.resolve()),
        "multi_material_prefabs": multi_material_prefabs,
        "total_prefabs": len(prefabs),
        "multi_material_count": len(multi_material_prefabs)
    }


def main():
    parser = argparse.ArgumentParser(
        description="Analyze MaterialList.txt files for prefabs with multiple material slots"
    )
    parser.add_argument(
        "file_path",
        type=str,
        help="Path to MaterialList*.txt file"
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output"
    )

    args = parser.parse_args()

    file_path = Path(args.file_path)
    if not file_path.exists():
        result = {
            "error": f"File not found: {file_path}",
            "pack_name": None,
            "file_path": str(file_path),
            "multi_material_prefabs": [],
            "total_prefabs": 0,
            "multi_material_count": 0
        }
    else:
        result = parse_material_list(file_path)

    if args.pretty:
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps(result))


if __name__ == "__main__":
    main()
