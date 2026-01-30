#!/usr/bin/env python3
"""
Extract Unity material property names from .unitypackage files.

.unitypackage files are tar.gz archives containing GUID folders.
Each GUID folder has:
  - /asset (file contents)
  - /pathname (original path)

This script extracts property names from .mat files (Unity materials).
"""

import argparse
import tarfile
import re
import sys
from pathlib import Path
from collections import defaultdict


def extract_unity_properties(unitypackage_path: str) -> dict:
    """
    Extract all material property names from a .unitypackage file.

    Returns a dict with:
        - 'mat_count': number of .mat files found
        - 'textures': set of texture property names
        - 'floats': set of float property names
        - 'colors': set of color property names
        - 'errors': list of error messages
    """
    results = {
        'mat_count': 0,
        'textures': set(),
        'floats': set(),
        'colors': set(),
        'errors': []
    }

    # Maps GUID -> pathname
    guid_to_pathname = {}
    # Maps GUID -> asset content (bytes)
    guid_to_asset = {}

    try:
        with tarfile.open(unitypackage_path, 'r:gz') as tar:
            # First pass: build GUID -> pathname mapping and collect asset content
            for member in tar.getmembers():
                if not member.isfile():
                    continue

                parts = member.name.replace('\\', '/').split('/')
                if len(parts) < 2:
                    continue

                guid = parts[0]
                filename = parts[-1]

                if filename == 'pathname':
                    try:
                        f = tar.extractfile(member)
                        if f:
                            pathname = f.read().decode('utf-8').strip()
                            # pathname may have multiple lines, take first
                            pathname = pathname.split('\n')[0].strip()
                            guid_to_pathname[guid] = pathname
                    except Exception as e:
                        results['errors'].append(f"Error reading pathname for {guid}: {e}")

                elif filename == 'asset':
                    try:
                        f = tar.extractfile(member)
                        if f:
                            guid_to_asset[guid] = f.read()
                    except Exception as e:
                        results['errors'].append(f"Error reading asset for {guid}: {e}")

            # Second pass: find .mat files and extract properties
            for guid, pathname in guid_to_pathname.items():
                if not pathname.lower().endswith('.mat'):
                    continue

                results['mat_count'] += 1

                if guid not in guid_to_asset:
                    results['errors'].append(f"No asset content for .mat file: {pathname}")
                    continue

                try:
                    content = guid_to_asset[guid].decode('utf-8', errors='replace')
                    extract_properties_from_mat(content, results)
                except Exception as e:
                    results['errors'].append(f"Error parsing {pathname}: {e}")

    except Exception as e:
        results['errors'].append(f"Error opening package: {e}")

    return results


def extract_properties_from_mat(content: str, results: dict):
    """
    Extract property names from Unity .mat file content.

    Unity YAML format for materials:
    m_TexEnvs:
    - _MainTex:
        m_Texture: {fileID: ...}
    - _BumpMap:
        m_Texture: {fileID: ...}
    m_Floats:
    - _Glossiness: 0.5
    - _Metallic: 0
    m_Colors:
    - _Color: {r: 1, g: 1, b: 1, a: 1}
    """

    # State machine to track which section we're in
    current_section = None
    section_indent = 0  # Track the indentation of the section header

    lines = content.split('\n')

    for i, line in enumerate(lines):
        stripped = line.strip()
        # Calculate leading whitespace (indentation level)
        leading_space = len(line) - len(line.lstrip())

        # Check for section headers (m_TexEnvs, m_Floats, m_Colors)
        if stripped.startswith('m_TexEnvs:'):
            current_section = 'textures'
            section_indent = leading_space
            continue
        elif stripped.startswith('m_Floats:'):
            current_section = 'floats'
            section_indent = leading_space
            continue
        elif stripped.startswith('m_Colors:'):
            current_section = 'colors'
            section_indent = leading_space
            continue
        elif current_section and stripped.startswith('m_') and ':' in stripped:
            # Only exit section if this is at the same or lower indentation level
            # (not a nested property like m_Texture, m_Scale, m_Offset)
            if leading_space <= section_indent:
                current_section = None
                section_indent = 0
            continue

        # Extract property names based on current section
        if current_section and stripped.startswith('- _'):
            # Pattern: "- _PropertyName:" or "- _PropertyName: value"
            match = re.match(r'^-\s+(_[A-Za-z0-9_]+):', stripped)
            if match:
                prop_name = match.group(1)
                results[current_section].add(prop_name)


def main():
    parser = argparse.ArgumentParser(
        description='Extract Unity material property names from .unitypackage files'
    )
    parser.add_argument(
        'unitypackage',
        help='Path to the .unitypackage file'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show errors encountered during extraction'
    )

    args = parser.parse_args()

    package_path = Path(args.unitypackage)
    if not package_path.exists():
        print(f"Error: File not found: {package_path}")
        sys.exit(1)

    print(f"Extracting properties from: {package_path.name}")
    print("=" * 60)

    results = extract_unity_properties(str(package_path))

    print(f"\n.mat files found: {results['mat_count']}")

    print(f"\n--- Texture Properties ({len(results['textures'])}) ---")
    for prop in sorted(results['textures']):
        print(f"  {prop}")

    print(f"\n--- Float Properties ({len(results['floats'])}) ---")
    for prop in sorted(results['floats']):
        print(f"  {prop}")

    print(f"\n--- Color Properties ({len(results['colors'])}) ---")
    for prop in sorted(results['colors']):
        print(f"  {prop}")

    if args.verbose and results['errors']:
        print(f"\n--- Errors ({len(results['errors'])}) ---")
        for error in results['errors']:
            print(f"  {error}")
    elif results['errors']:
        print(f"\n({len(results['errors'])} errors encountered, use -v to see details)")


if __name__ == '__main__':
    main()
