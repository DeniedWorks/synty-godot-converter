"""
Unity Package Extraction and GUID Mapping Module.

This module handles extraction of .unitypackage files (tar/gzip format)
and builds GUID mappings for materials and textures.

Unity Package Structure:
    .unitypackage is a gzip-compressed tar archive where each asset
    is stored in a folder named with its GUID. Inside each folder:
    - asset: The actual file content (e.g., .mat, .png)
    - pathname: Text file containing the Unity asset path (e.g., "Assets/Materials/Crystal.mat")
    - asset.meta: Unity metadata file
"""

from __future__ import annotations

import logging
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

logger = logging.getLogger(__name__)

# Supported texture formats (case-insensitive)
TEXTURE_EXTENSIONS = frozenset({".png", ".tga", ".jpg", ".jpeg"})


@dataclass
class GuidMap:
    """Container for GUID mappings extracted from a Unity package.

    This class holds the three primary mappings needed for Unity-to-Godot
    material conversion:

    1. GUID to pathname: Maps every asset's GUID to its Unity project path
    2. GUID to content: Maps material GUIDs to their raw .mat file content
    3. Texture GUID to name: Maps texture GUIDs to filenames for resolving
       texture references in materials

    Unity uses GUIDs (32-character hex strings) as stable identifiers for all
    assets. When a material references a texture, it stores the texture's GUID
    rather than the filename. This class provides the mappings needed to
    resolve those references.

    Attributes:
        guid_to_pathname: Maps GUID to Unity asset path. The path is relative
            to the Assets folder (e.g., "Assets/Materials/Crystal.mat",
            "Assets/Textures/Ground_01.png").
        guid_to_content: Maps material GUID to raw file content (bytes) for
            .mat files only. Used for parsing material properties.
        texture_guid_to_name: Maps texture GUID to texture filename with
            extension (e.g., "Ground_01.png"). Only includes PNG, TGA, and
            JPG/JPEG files.

    Example:
        >>> guid_map = extract_unitypackage(Path("MyPack.unitypackage"))
        >>> print(f"Found {len(guid_map.guid_to_pathname)} assets")
        Found 1523 assets

        >>> # Get all material GUIDs
        >>> mat_guids = get_material_guids(guid_map)
        >>> print(f"Found {len(mat_guids)} materials")
        Found 42 materials

        >>> # Resolve a texture GUID to filename
        >>> tex_name = guid_map.texture_guid_to_name.get("abc123...")
        >>> print(tex_name)
        'PolygonNature_Texture_01_A.png'
    """

    guid_to_pathname: dict[str, str] = field(default_factory=dict)
    guid_to_content: dict[str, bytes] = field(default_factory=dict)
    texture_guid_to_name: dict[str, str] = field(default_factory=dict)
    texture_guid_to_path: dict[str, Path] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"GuidMap(pathnames={len(self.guid_to_pathname)}, "
            f"contents={len(self.guid_to_content)}, "
            f"textures={len(self.texture_guid_to_name)}, "
            f"texture_paths={len(self.texture_guid_to_path)})"
        )


def extract_unitypackage(package_path: Path) -> GuidMap:
    """Extract a Unity package and build GUID mappings.

    This is the main entry point for Unity package extraction. It opens the
    .unitypackage file (a gzip-compressed tar archive), parses its structure,
    and builds the GUID mappings needed for material conversion.

    The extraction process:
    1. Open the tar.gz archive
    2. Parse the directory structure to extract GUID folders
    3. Read 'pathname' files to build GUID-to-path mapping
    4. Identify texture assets (.png, .tga, .jpg) for GUID-to-name mapping
    5. Extract raw content for .mat files for later parsing

    Args:
        package_path: Path to the .unitypackage file. This is a gzip-compressed
            tar archive with a specific structure (see module docstring).

    Returns:
        GuidMap containing:
        - guid_to_pathname: All assets mapped by GUID
        - guid_to_content: Raw bytes of .mat files only
        - texture_guid_to_name: Texture files mapped by GUID

    Raises:
        FileNotFoundError: If package_path does not exist.
        tarfile.ReadError: If the file is not a valid tar/gzip archive or
            is corrupted.
        tarfile.CompressionError: If the gzip decompression fails.

    Example:
        >>> from pathlib import Path
        >>> guid_map = extract_unitypackage(Path("PolygonNature.unitypackage"))
        >>> print(guid_map)
        GuidMap(pathnames=1523, contents=42, textures=156)

        >>> # Access material content for parsing
        >>> for guid in get_material_guids(guid_map):
        ...     content = guid_map.guid_to_content[guid]
        ...     material = parse_material_bytes(content)
    """
    if not package_path.exists():
        raise FileNotFoundError(f"Unity package not found: {package_path}")

    with tarfile.open(package_path, "r:gz") as tar:
        # Parse the tar structure into {guid: {filename: content}}
        guid_data = _parse_tar_structure(tar)

    logger.debug("Parsed %d GUID entries from package", len(guid_data))

    # Build the GUID to pathname mapping
    guid_to_pathname = _build_guid_to_pathname(guid_data)
    logger.debug("Built pathname mapping for %d assets", len(guid_to_pathname))

    # Build texture GUID to name mapping
    texture_guid_to_name = _build_texture_guid_map(guid_to_pathname)
    logger.debug("Found %d texture assets", len(texture_guid_to_name))

    # Extract .mat file contents
    guid_to_content = _extract_material_contents(guid_data, guid_to_pathname)
    logger.debug("Extracted content for %d material files", len(guid_to_content))

    # Extract textures to temp files
    temp_dir = Path(tempfile.mkdtemp(prefix="synty_textures_"))
    texture_guid_to_path = _extract_textures_to_temp(guid_data, guid_to_pathname, temp_dir)
    logger.debug(
        "Extracted %d textures to temp directory: %s",
        len(texture_guid_to_path),
        temp_dir,
    )

    return GuidMap(
        guid_to_pathname=guid_to_pathname,
        guid_to_content=guid_to_content,
        texture_guid_to_name=texture_guid_to_name,
        texture_guid_to_path=texture_guid_to_path,
    )


def _parse_tar_structure(tar: tarfile.TarFile) -> dict[str, dict[str, bytes]]:
    """Parse tar archive into a structured dictionary.

    The Unity package structure has entries like:
        <guid>/asset       - The actual file content
        <guid>/pathname    - Text file with Unity asset path
        <guid>/asset.meta  - Unity metadata (not used by converter)

    Where <guid> is a 32-character hex string identifying the asset.

    This function reads all file entries from the tar archive and organizes
    them by GUID. Entries with invalid GUID format or that cannot be
    extracted are skipped with a warning.

    Args:
        tar: Open tarfile object to read from.

    Returns:
        Dictionary mapping GUID to inner dict of {filename: content}.
        Example: {"abc123...": {"asset": b"...", "pathname": b"Assets/..."}}
    """
    guid_data: dict[str, dict[str, bytes]] = {}

    for member in tar.getmembers():
        # Skip directories
        if not member.isfile():
            continue

        # Parse path: expected format is "<guid>/<filename>"
        path = PurePosixPath(member.name)
        parts = path.parts

        if len(parts) < 2:
            logger.debug("Skipping malformed entry (too few parts): %s", member.name)
            continue

        # The first part is the GUID, second is the filename
        guid = parts[0]
        filename = parts[1]

        # Validate GUID format (should be 32 hex characters)
        if not _is_valid_guid(guid):
            logger.debug("Skipping entry with invalid GUID format: %s", guid)
            continue

        # Extract file content
        try:
            file_obj = tar.extractfile(member)
            if file_obj is None:
                logger.warning("Could not extract file: %s", member.name)
                continue

            content = file_obj.read()

            # Initialize dict for this GUID if needed
            if guid not in guid_data:
                guid_data[guid] = {}

            guid_data[guid][filename] = content

        except Exception as e:
            logger.warning("Error extracting %s: %s", member.name, e)
            continue

    return guid_data


def _is_valid_guid(guid: str) -> bool:
    """Check if a string is a valid Unity GUID (32 hex characters).

    Unity GUIDs are 32-character lowercase hexadecimal strings that uniquely
    identify each asset in a Unity project.

    Args:
        guid: String to validate.

    Returns:
        True if guid is exactly 32 hex characters, False otherwise.

    Example:
        >>> _is_valid_guid("0730dae39bc73f34796280af9875ce14")
        True
        >>> _is_valid_guid("invalid")
        False
        >>> _is_valid_guid("0730dae39bc73f34")  # Too short
        False
    """
    if len(guid) != 32:
        return False

    try:
        int(guid, 16)
        return True
    except ValueError:
        return False


def _build_guid_to_pathname(guid_data: dict[str, dict[str, bytes]]) -> dict[str, str]:
    """Build mapping from GUID to Unity asset pathname.

    Each asset folder in the Unity package contains a 'pathname' file with
    the Unity project path (e.g., "Assets/Materials/Crystal.mat"). This
    function extracts and decodes those paths.

    Args:
        guid_data: Parsed tar structure from _parse_tar_structure, mapping
            GUID to {filename: content}.

    Returns:
        Dictionary mapping GUID to Unity asset path string.
        Paths are UTF-8 decoded and stripped of whitespace.

    Example:
        >>> guid_to_pathname = _build_guid_to_pathname(guid_data)
        >>> guid_to_pathname["abc123..."]
        'Assets/Materials/Crystal.mat'
    """
    guid_to_pathname: dict[str, str] = {}

    for guid, files in guid_data.items():
        if "pathname" not in files:
            logger.debug("GUID %s has no pathname file", guid)
            continue

        try:
            # Pathname file contains UTF-8 text
            pathname = files["pathname"].decode("utf-8").strip()

            # Remove any null bytes or unusual characters
            pathname = pathname.replace("\x00", "")

            if pathname:
                guid_to_pathname[guid] = pathname
            else:
                logger.debug("GUID %s has empty pathname", guid)

        except UnicodeDecodeError as e:
            logger.warning("Failed to decode pathname for GUID %s: %s", guid, e)
            continue

    return guid_to_pathname


def _build_texture_guid_map(guid_to_pathname: dict[str, str]) -> dict[str, str]:
    """Build mapping from texture GUID to texture filename (with extension).

    Filters the GUID-to-pathname mapping to include only texture files,
    extracting just the filename (not full path) for each texture.

    Supported texture formats (case-insensitive):
    - PNG (.png)
    - TGA (.tga)
    - JPEG (.jpg, .jpeg)

    Args:
        guid_to_pathname: Complete GUID to pathname mapping from
            _build_guid_to_pathname.

    Returns:
        Dictionary mapping texture GUID to filename with extension.
        Example: {"abc123...": "PolygonNature_Texture_01_A.png"}

    Example:
        >>> texture_map = _build_texture_guid_map(guid_to_pathname)
        >>> texture_map["0730dae39bc73f34796280af9875ce14"]
        'Ground_01.png'
    """
    texture_guid_to_name: dict[str, str] = {}

    for guid, pathname in guid_to_pathname.items():
        # Get the extension (case-insensitive)
        path = PurePosixPath(pathname)
        ext = path.suffix.lower()

        if ext in TEXTURE_EXTENSIONS:
            # Store the full filename with extension
            texture_guid_to_name[guid] = path.name

    return texture_guid_to_name


def _extract_material_contents(
    guid_data: dict[str, dict[str, bytes]], guid_to_pathname: dict[str, str]
) -> dict[str, bytes]:
    """Extract raw content for .mat files.

    Filters the parsed tar data to extract only material files (.mat),
    returning their raw bytes for later parsing by unity_parser.

    Args:
        guid_data: Parsed tar structure from _parse_tar_structure.
        guid_to_pathname: GUID to pathname mapping for identifying .mat files.

    Returns:
        Dictionary mapping material GUID to raw file content (bytes).
        The content is the 'asset' file from the GUID folder.

    Note:
        Materials with no 'asset' file in their GUID folder are skipped
        with a warning.
    """
    guid_to_content: dict[str, bytes] = {}

    for guid, pathname in guid_to_pathname.items():
        # Check if this is a .mat file
        if not pathname.lower().endswith(".mat"):
            continue

        # Get the files for this GUID
        files = guid_data.get(guid, {})

        if "asset" not in files:
            logger.warning("Material %s (GUID: %s) has no asset file", pathname, guid)
            continue

        guid_to_content[guid] = files["asset"]

    return guid_to_content


def _extract_textures_to_temp(
    guid_data: dict[str, dict[str, bytes]],
    guid_to_pathname: dict[str, str],
    temp_dir: Path,
) -> dict[str, Path]:
    """Extract texture assets to temp files.

    Extracts the actual texture file content from the Unity package and writes
    each texture to a temp file. This allows the converter to use textures
    directly from the package instead of searching SourceFiles.

    Args:
        guid_data: Parsed tar structure from _parse_tar_structure, mapping
            GUID to {filename: content}.
        guid_to_pathname: GUID to pathname mapping for identifying texture files.
        temp_dir: Directory to write temp texture files to.

    Returns:
        Dictionary mapping texture GUID to the Path of the extracted temp file.
    """
    texture_guid_to_path: dict[str, Path] = {}

    for guid, pathname in guid_to_pathname.items():
        ext = PurePosixPath(pathname).suffix.lower()
        if ext not in TEXTURE_EXTENSIONS:
            continue

        files = guid_data.get(guid, {})
        if "asset" not in files:
            continue

        # Write to temp file with original extension
        temp_file = temp_dir / f"{guid}{ext}"
        temp_file.write_bytes(files["asset"])
        texture_guid_to_path[guid] = temp_file

    return texture_guid_to_path


def get_material_guids(guid_map: GuidMap) -> list[str]:
    """Get all GUIDs that correspond to .mat files.

    Convenience function to filter the GUID map for material assets only.
    This is useful for iterating over materials to parse and convert them.

    Args:
        guid_map: GuidMap instance from extract_unitypackage.

    Returns:
        List of GUIDs for assets with .mat extension (case-insensitive).

    Example:
        >>> guid_map = extract_unitypackage(Path("Package.unitypackage"))
        >>> material_guids = get_material_guids(guid_map)
        >>> for guid in material_guids:
        ...     content = guid_map.guid_to_content[guid]
        ...     material = parse_material_bytes(content)
    """
    material_guids: list[str] = []

    for guid, pathname in guid_map.guid_to_pathname.items():
        if pathname.lower().endswith(".mat"):
            material_guids.append(guid)

    return material_guids


def get_material_name(guid_map: GuidMap, guid: str) -> str | None:
    """Get the material name (without path or extension) for a given GUID.

    Extracts just the filename stem from the asset's full Unity path.

    Args:
        guid_map: GuidMap instance from extract_unitypackage.
        guid: GUID of the material asset.

    Returns:
        Material name (filename without extension) or None if GUID not found.

    Example:
        >>> name = get_material_name(guid_map, "abc123...")
        >>> print(name)
        'PolygonNature_Ground_01'  # from "Assets/Materials/PolygonNature_Ground_01.mat"
    """
    pathname = guid_map.guid_to_pathname.get(guid)
    if pathname is None:
        return None

    return PurePosixPath(pathname).stem


def resolve_texture_guid(guid_map: GuidMap, texture_guid: str) -> str | None:
    """Resolve a texture GUID to its filename.

    Looks up a texture GUID in the texture mapping to get the filename.
    Used when parsing material texture references.

    Args:
        guid_map: GuidMap instance from extract_unitypackage.
        texture_guid: GUID of the texture asset (32 hex characters).

    Returns:
        Texture filename with extension (e.g., "Ground_01.png") or None
        if the GUID is not found in the texture mapping.

    Example:
        >>> filename = resolve_texture_guid(guid_map, "0730dae39bc73f34796280af9875ce14")
        >>> print(filename)
        'PolygonNature_Texture_01_A.png'
    """
    return guid_map.texture_guid_to_name.get(texture_guid)


# Convenience function for testing/debugging
def print_guid_map_summary(guid_map: GuidMap) -> None:
    """Print a summary of the GUID map contents.

    Displays statistics about the extracted Unity package including:
    - Total asset count
    - Material file count
    - Texture file count
    - Breakdown of assets by file extension

    Args:
        guid_map: GuidMap instance to summarize.

    Note:
        Output is written to stdout. This is primarily for debugging
        and CLI usage.
    """
    print(f"\n{'='*60}")
    print("GUID Map Summary")
    print(f"{'='*60}")
    print(f"Total assets:     {len(guid_map.guid_to_pathname)}")
    print(f"Material files:   {len(guid_map.guid_to_content)}")
    print(f"Texture files:    {len(guid_map.texture_guid_to_name)}")
    print(f"Texture temps:    {len(guid_map.texture_guid_to_path)}")

    # Count by extension
    extensions: dict[str, int] = {}
    for pathname in guid_map.guid_to_pathname.values():
        ext = PurePosixPath(pathname).suffix.lower()
        extensions[ext] = extensions.get(ext, 0) + 1

    print(f"\nAssets by type:")
    for ext, count in sorted(extensions.items(), key=lambda x: -x[1]):
        print(f"  {ext or '(no ext)'}: {count}")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    # Basic test/demo usage
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        print("Usage: python unity_package.py <path_to_unitypackage>")
        sys.exit(1)

    package_path = Path(sys.argv[1])

    try:
        guid_map = extract_unitypackage(package_path)
        print_guid_map_summary(guid_map)

        # Print first few materials
        material_guids = get_material_guids(guid_map)
        print(f"Found {len(material_guids)} materials:")
        for guid in material_guids[:10]:
            name = get_material_name(guid_map, guid)
            print(f"  - {name} ({guid})")

        if len(material_guids) > 10:
            print(f"  ... and {len(material_guids) - 10} more")

    except Exception as e:
        logger.error("Failed to extract package: %s", e)
        sys.exit(1)
