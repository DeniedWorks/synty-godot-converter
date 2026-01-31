#!/usr/bin/env python3
"""
Synty Shader Converter - Main CLI Entry Point.

This module orchestrates the full conversion pipeline for converting
Unity Synty assets to Godot 4.6 format.

Usage:
    python converter.py \\
        --unity-package "path/to/.unitypackage" \\
        --source-files "path/to/SourceFiles" \\
        --output "path/to/output" \\
        --godot "path/to/Godot.exe" \\
        --dry-run \\
        --verbose

Pipeline Steps:
    1. Validate inputs (package exists, source-files directory exists, godot exists)
    2. Create output directory structure
    3. Extract Unity package
    4. Parse all .mat files
    4.5. Parse MaterialList.txt early (for shader detection)
    4.6. Build shader cache with LOD inheritance
    5. Detect shaders and map properties (using shader cache)
    6. Generate .tres files
    7. Copy .gdshader files
    8. Copy required textures
    8.5. Copy FBX files
    9. Generate mesh_material_mapping.json (uses cached prefabs)
    10. Generate project.godot with global shader uniforms
    11. Run Godot CLI to convert FBX to .tscn (unless --skip-godot-cli)
    12. Print conversion summary
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Local imports
from unity_package import extract_unitypackage, GuidMap, get_material_guids, get_material_name
from unity_parser import parse_material_bytes, UnityMaterial
from shader_mapping import map_material, detect_shader_type, determine_shader, MappedMaterial
from tres_generator import generate_tres, write_tres_file, sanitize_filename
from material_list import (
    parse_material_list,
    generate_mesh_material_mapping_json,
    get_custom_shader_materials,
    PrefabMaterials,
)

logger = logging.getLogger(__name__)


def has_source_assets_recursive(path: Path) -> bool:
    """Check if a path contains any MaterialList, FBX, or Models anywhere in tree.

    This is used to validate that the source_files path contains usable assets,
    even if they are nested in subdirectories (like Dwarven Dungeon structure).

    Note: Textures are primarily extracted from .unitypackage files, so Textures
    directories are not required for validation. SourceFiles/Textures is used
    as an optional fallback only.

    Args:
        path: Directory to search recursively.

    Returns:
        True if any MaterialList*.txt, FBX directory, or Models directory
        exists anywhere in the tree.
    """
    # Check for MaterialList files
    if list(path.rglob("MaterialList*.txt")):
        return True

    # Check for FBX directories
    for item in path.rglob("FBX"):
        if item.is_dir():
            return True

    # Check for Models directories (some packs use this instead of FBX)
    for item in path.rglob("Models"):
        if item.is_dir():
            return True

    # Note: Textures directories are NOT required - textures come from .unitypackage
    # SourceFiles/Textures is optional fallback only

    return False


def resolve_source_files_path(source_files: Path) -> Path:
    """Validate and return the source files path.

    Since all file discovery is now recursive, users can point to any folder
    containing Synty assets and the converter will find MaterialList*.txt,
    FBX/, and Textures/ folders anywhere in the tree.

    Args:
        source_files: Path provided by the user as --source-files argument.

    Returns:
        The source files path as-is. If the path does not exist or has no
        assets, it will fail validation later with a clear error message.
    """
    if not source_files.exists():
        return source_files  # Will fail validation with clear error

    if has_source_assets_recursive(source_files):
        return source_files

    # Log warning if no assets found
    logger.warning("No MaterialList, FBX, or Models found in: %s", source_files)
    return source_files


# Shader files to copy from project's shaders/ directory
SHADER_FILES = [
    "clouds.gdshader",
    "crystal.gdshader",
    "foliage.gdshader",
    "particles.gdshader",
    "polygon.gdshader",
    "skydome.gdshader",
    "water.gdshader",
]

# Supported texture extensions (for finding textures by name)
TEXTURE_EXTENSIONS = [".png", ".tga", ".jpg", ".jpeg", ".PNG", ".TGA", ".JPG", ".JPEG"]

# Patterns for finding the pack's main texture atlas (fallback for missing generic textures)
# Order matters - first match wins. Prefer "Polygon" prefixed textures as they're the main atlas.
FALLBACK_TEXTURE_PATTERNS = [
    "Polygon*_Texture_01.png",     # Most common: PolygonNature_Texture_01.png
    "Polygon*_Texture_01_A.png",   # Some packs use _A suffix
    "POLYGON*_Texture_01.png",     # Uppercase variant
    "*_Texture_01_A.png",          # Fallback: any pack with _A suffix
    "Texture_01.png",              # Simple naming
]

# Template for .import sidecar files for textures
# This configures VRAM compression (mode=2) with high quality
TEXTURE_IMPORT_TEMPLATE = """[remap]

importer="texture"
type="CompressedTexture2D"
uid="uid://{uid}"
path="res://.godot/imported/{filename}-{hash}.ctex"
metadata={{
"vram_texture": true
}}

[deps]

source_file="{res_path}"
dest_files=["res://.godot/imported/{filename}-{hash}.ctex"]

[params]

compress/mode=2
compress/high_quality=true
compress/lossy_quality=0.7
compress/hdr_compression=1
compress/normal_map=0
compress/channel_pack=0
mipmaps/generate=true
mipmaps/limit=-1
roughness/mode=0
roughness/src_normal=""
process/fix_alpha_border=true
process/premult_alpha=false
process/normal_map_invert_y=false
process/hdr_as_srgb=false
process/hdr_clamp_exposure=false
process/size_limit=0
detect_3d/compress_to=1
"""

# project.godot template with global shader uniforms
PROJECT_GODOT_TEMPLATE = """; Engine configuration file.
; Generated by Synty Shader Converter

[application]

config/name="Synty Converted Assets"
config/features=PackedStringArray("4.6")

[shader_globals]

WindDirection={
"type": "vec3",
"value": Vector3(1, 0, 0)
}
WindIntensity={
"type": "float",
"value": 0.5
}
GaleStrength={
"type": "float",
"value": 0.0
}
MainLightDirection={
"type": "vec3",
"value": Vector3(0.5, -0.5, 0.0)
}
SkyColor={
"type": "color",
"value": Color(0.5, 0.7, 1.0, 1.0)
}
EquatorColor={
"type": "color",
"value": Color(1.0, 0.9, 0.8, 1.0)
}
GroundColor={
"type": "color",
"value": Color(0.4, 0.4, 0.3, 1.0)
}
OceanWavesGradient={
"type": "sampler2D",
"value": ""
}
"""


@dataclass
class ConversionConfig:
    """Configuration dataclass for the conversion pipeline.

    This dataclass holds all configuration options needed to run the
    Unity-to-Godot conversion process. It is populated from command-line
    arguments via parse_args().

    Attributes:
        unity_package: Path to the .unitypackage file to convert. Must exist.
        source_files: Path to SourceFiles directory containing FBX/ and optionally
            Textures/ subdirectories. Textures primarily come from the .unitypackage
            file; SourceFiles/Textures is used as an optional fallback.
        output_dir: Output directory for converted Godot assets. Will be created
            if it does not exist.
        godot_exe: Path to Godot 4.6 executable for CLI operations. Must exist.
        dry_run: If True, preview operations without writing files. Useful for
            testing what the conversion would do.
        verbose: If True, enable DEBUG logging level for detailed output.
        skip_fbx_copy: If True, skip copying FBX files from SourceFiles/FBX.
            Use this if the models/ directory is already populated.
        skip_godot_cli: If True, skip Godot CLI conversion phase. This generates
            materials only without producing .tscn scene files.
        skip_godot_import: If True, skip Godot's headless import step but still
            run the GDScript converter. Useful for large projects where the
            import step times out. You'll need to open the project in Godot
            manually to trigger asset import before running the converter.
        godot_timeout: Timeout in seconds for Godot CLI operations. Each phase
            (import and convert) has this timeout applied separately.
        keep_meshes_together: If True, keep all meshes from one FBX together in
            a single scene file. If False (default), each mesh is saved as a
            separate .tscn file.
        mesh_format: Output format for mesh scenes. Either 'tscn' (text format,
            default) or 'res' (binary compiled resource format).
        filter_pattern: Optional filter pattern for FBX filenames. If specified,
            only FBX files containing this pattern (case-insensitive) are
            processed. If None, all FBX files are processed.

    Example:
        >>> config = ConversionConfig(
        ...     unity_package=Path("C:/SyntyAssets/Nature.unitypackage"),
        ...     source_files=Path("C:/SyntyAssets/SourceFiles"),
        ...     output_dir=Path("C:/Godot/Projects/converted"),
        ...     godot_exe=Path("C:/Godot/Godot_v4.6.exe"),
        ...     dry_run=True,  # Preview only
        ...     verbose=True,  # Detailed logging
        ... )
    """

    unity_package: Path
    source_files: Path
    output_dir: Path
    godot_exe: Path
    dry_run: bool = False
    verbose: bool = False
    skip_fbx_copy: bool = False
    skip_godot_cli: bool = False
    skip_godot_import: bool = False
    godot_timeout: int = 600
    keep_meshes_together: bool = False
    mesh_format: str = "tscn"
    filter_pattern: str | None = None


@dataclass
class ConversionStats:
    """Statistics collected during the conversion pipeline.

    This dataclass tracks all metrics and issues encountered during conversion.
    It is populated by run_conversion() and used to generate the final summary
    and conversion log.

    Attributes:
        materials_parsed: Number of Unity .mat files successfully parsed from
            the unitypackage. Incremented in Step 4 of the pipeline.
        materials_generated: Number of Godot .tres material files written to
            output/materials/. Includes both converted and placeholder materials.
        materials_missing: Number of materials referenced by meshes in
            MaterialList.txt but not found in output/materials/. These meshes
            will use Godot's default material at runtime.
        textures_copied: Number of texture files successfully copied from
            SourceFiles/Textures to output/textures/.
        textures_fallback: Number of missing textures substituted with the pack's
            main texture atlas (e.g., Texture_01.png) as a fallback.
        textures_missing: Number of textures referenced by materials but not
            found in the source directory and no fallback was available.
        shaders_copied: Number of .gdshader files copied to output/shaders/.
            Should equal len(SHADER_FILES) if all shaders are present.
        fbx_copied: Number of FBX model files copied from SourceFiles/FBX to
            output/models/.
        fbx_skipped: Number of FBX files skipped because they already existed
            at the destination with the same file size.
        meshes_converted: Number of .tscn scene files generated by Godot CLI.
            Counted from output/meshes/ after conversion.
        godot_import_success: True if Godot --import phase completed without
            error. False if it failed or was skipped.
        godot_convert_success: True if godot_converter.gd script completed
            successfully. False if it failed or was skipped.
        godot_timeout_occurred: True if either Godot CLI phase exceeded the
            configured timeout.
        warnings: List of warning messages for non-critical issues (e.g.,
            missing textures, parse failures for individual materials).
        errors: List of error messages for critical failures that may have
            stopped the conversion or indicate incomplete output.

    Example:
        >>> stats = ConversionStats()
        >>> stats.materials_parsed = 42
        >>> stats.textures_copied = 15
        >>> stats.warnings.append("Texture 'Missing_Tex' not found")
        >>> print(f"Parsed {stats.materials_parsed} materials")
        Parsed 42 materials
    """

    materials_parsed: int = 0
    materials_generated: int = 0
    materials_missing: int = 0
    textures_copied: int = 0
    textures_fallback: int = 0
    textures_missing: int = 0
    shaders_copied: int = 0
    fbx_copied: int = 0
    fbx_skipped: int = 0
    meshes_converted: int = 0
    godot_import_success: bool = False
    godot_convert_success: bool = False
    godot_timeout_occurred: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def parse_args() -> ConversionConfig:
    """Parse command-line arguments and validate inputs.

    Returns:
        ConversionConfig with validated paths.

    Raises:
        SystemExit: If required arguments are missing or invalid.
    """
    parser = argparse.ArgumentParser(
        description="Convert Synty Unity assets to Godot 4.6 format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python converter.py \\
        --unity-package "C:/SyntyComplete/PolygonNature/Nature.unitypackage" \\
        --source-files "C:/SyntyComplete/PolygonNature/SourceFiles" \\
        --output "C:/Godot/Projects/converted_nature" \\
        --godot "C:/Godot/Godot_v4.6.exe"

    python converter.py \\
        --unity-package package.unitypackage \\
        --source-files ./SourceFiles \\
        --output ./output \\
        --godot godot.exe \\
        --dry-run --verbose
""",
    )

    parser.add_argument(
        "--unity-package",
        type=Path,
        required=True,
        help="Path to Unity .unitypackage file",
    )
    parser.add_argument(
        "--source-files",
        type=Path,
        required=True,
        help="Path to SourceFiles folder containing FBX/ (Textures/ optional - textures come from .unitypackage)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output directory for Godot project",
    )
    parser.add_argument(
        "--godot",
        type=Path,
        required=True,
        help="Path to Godot 4.6 executable",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--skip-fbx-copy",
        action="store_true",
        help="Skip copying FBX files (use if models/ already populated)",
    )
    parser.add_argument(
        "--skip-godot-cli",
        action="store_true",
        help="Skip running Godot CLI (generates materials only, no .tscn scene files)",
    )
    parser.add_argument(
        "--skip-godot-import",
        action="store_true",
        help="Skip Godot's headless import step (useful for large projects that timeout). "
             "The GDScript converter will still run. You'll need to open the project in "
             "Godot manually to trigger asset import before running the converter.",
    )
    parser.add_argument(
        "--godot-timeout",
        type=int,
        default=600,
        help="Timeout for Godot CLI operations in seconds (default: 600)",
    )
    parser.add_argument(
        "--keep-meshes-together",
        action="store_true",
        help="Keep all meshes from one FBX together in a single scene file "
             "(default: each mesh saved as separate .tscn)",
    )
    parser.add_argument(
        "--mesh-format",
        choices=["tscn", "res"],
        default="tscn",
        help="Output format for mesh scenes: 'tscn' (text, default) or 'res' (binary)",
    )
    parser.add_argument(
        "--filter",
        type=str,
        default=None,
        help="Filter pattern for FBX filenames (case-insensitive). "
             "Example: --filter Tree only converts FBX files containing 'Tree'",
    )

    args = parser.parse_args()

    # Validate paths
    if not args.unity_package.exists():
        parser.error(f"Unity package not found: {args.unity_package}")

    if not args.source_files.exists():
        parser.error(f"Source files directory not found: {args.source_files}")

    # Resolve nested SourceFiles folder structure (e.g., PackName_SourceFiles_v2/SourceFiles/)
    resolved_source_files = resolve_source_files_path(args.source_files)

    # Note: Textures directory is optional - textures primarily come from .unitypackage
    # SourceFiles/Textures is used as a fallback only
    textures_dir = resolved_source_files / "Textures"
    if not textures_dir.exists():
        # Try to find any Textures directory recursively
        texture_dirs = list(resolved_source_files.rglob("Textures"))
        texture_dirs = [d for d in texture_dirs if d.is_dir()]
        if not texture_dirs:
            # This is just a warning now, not an error - textures come from .unitypackage
            logger.warning(
                "No Textures directory found in %s or its subdirectories. "
                "Textures will be extracted from .unitypackage only.",
                resolved_source_files
            )

    if not args.godot.exists():
        parser.error(f"Godot executable not found: {args.godot}")

    return ConversionConfig(
        unity_package=args.unity_package.resolve(),
        source_files=resolved_source_files.resolve(),
        output_dir=args.output.resolve(),
        godot_exe=args.godot.resolve(),
        dry_run=args.dry_run,
        verbose=args.verbose,
        skip_fbx_copy=args.skip_fbx_copy,
        skip_godot_cli=args.skip_godot_cli,
        skip_godot_import=args.skip_godot_import,
        godot_timeout=args.godot_timeout,
        keep_meshes_together=args.keep_meshes_together,
        mesh_format=args.mesh_format,
        filter_pattern=args.filter,
    )


def setup_output_directories(output_dir: Path, dry_run: bool) -> None:
    """Create the output directory structure for pack assets.

    Creates:
        output_dir/
            textures/
            materials/
            models/
            meshes/

    Note: shaders/ is created at project root by copy_shaders(), not here.

    Args:
        output_dir: Pack output directory.
        dry_run: If True, only log what would be created.
    """
    directories = [
        output_dir,
        output_dir / "textures",
        output_dir / "materials",
        output_dir / "models",
        output_dir / "meshes",
    ]

    for directory in directories:
        if dry_run:
            logger.info("[DRY RUN] Would create directory: %s", directory)
        else:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug("Created directory: %s", directory)


def copy_shaders(shaders_dest: Path, dry_run: bool) -> int:
    """Copy .gdshader files from project's shaders/ to destination.

    Args:
        shaders_dest: Destination directory for shader files.
        dry_run: If True, only log what would be copied.

    Returns:
        Number of shader files copied (or would be copied in dry run).
    """
    # Source shaders are relative to where this script is located
    script_dir = Path(__file__).parent
    shaders_source = script_dir / "shaders"

    # Ensure destination directory exists
    if not dry_run:
        shaders_dest.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    for shader_file in SHADER_FILES:
        source_path = shaders_source / shader_file
        dest_path = shaders_dest / shader_file

        if not source_path.exists():
            logger.warning("Shader file not found: %s", source_path)
            continue

        # Skip if shader already exists (shared shaders persist across packs)
        if dest_path.exists():
            logger.debug("Shader already exists, skipping: %s", shader_file)
            skipped += 1
            continue

        if dry_run:
            logger.info("[DRY RUN] Would copy shader: %s -> %s", source_path, dest_path)
        else:
            shutil.copy2(source_path, dest_path)
            logger.debug("Copied shader: %s", shader_file)

        copied += 1

    if skipped > 0:
        logger.info("Copied %d shader files (%d already existed)", copied, skipped)
    else:
        logger.info("Copied %d shader files", copied)
    return copied


def find_fallback_texture(textures_dir: Path) -> Path | None:
    """Find the pack's main texture atlas to use as fallback for missing textures.

    Searches for common Synty texture atlas naming patterns in the root of
    the textures directory. Every Synty pack has a main color palette texture
    (e.g., PolygonNature_Texture_01.png) that can be used as a fallback.

    Args:
        textures_dir: Path to the SourceFiles/Textures directory.

    Returns:
        Path to the fallback texture if found, None otherwise.
    """
    for pattern in FALLBACK_TEXTURE_PATTERNS:
        # Only search in root directory, not subdirectories
        matches = list(textures_dir.glob(pattern))
        if matches:
            # Return first match (prefer shorter names)
            matches.sort(key=lambda p: len(p.name))
            logger.debug("Found fallback texture: %s", matches[0].name)
            return matches[0]

    return None


def find_texture_file(
    textures_dir: Path,
    texture_name: str,
    additional_texture_dirs: list[Path] | None = None,
) -> Path | None:
    """Find a texture file by name, trying various extensions.

    Searches for a texture file first in the root of textures_dir, then
    recursively in subdirectories. Also searches any additional texture
    directories provided (for complex nested structures). Tries all
    extensions in TEXTURE_EXTENSIONS.

    Args:
        textures_dir: Primary directory to search for textures.
        texture_name: Base name of the texture. May include extension (which
            will be stripped) or be just the stem (e.g., "PolygonNature_01").
        additional_texture_dirs: Optional list of additional Textures directories
            to search (for complex nested structures like Dwarven Dungeon).

    Returns:
        Path to the first matching texture file if found, None otherwise.
        Prefers files in the root directory over subdirectories.

    Example:
        >>> path = find_texture_file(Path("Textures"), "Ground_01")
        >>> print(path)
        Textures/Ground_01.png
    """
    # Strip known extension if present to get the base name
    base_name = texture_name
    for ext in TEXTURE_EXTENSIONS:
        if texture_name.lower().endswith(ext.lower()):
            base_name = texture_name[:-len(ext)]
            break

    # Build list of name variations to try
    # Synty SourceFiles often have "_Texture" inserted in names
    # e.g., Unity: "PolygonSamuraiEmpire_01_A" -> SourceFiles: "PolygonSamuraiEmpire_Texture_01_A"
    name_variations = [base_name]

    # Try inserting "_Texture" before numbered suffixes like "_01_A", "_02_B", etc.
    match = re.match(r'^(.+?)(_\d+_[A-Za-z]+(?:_\w+)?)$', base_name)
    if match:
        prefix, suffix = match.groups()
        name_variations.append(f"{prefix}_Texture{suffix}")

    # Also try just appending "_Texture" variations
    if "_Texture" not in base_name:
        name_variations.append(base_name.replace("_01", "_Texture_01"))
        name_variations.append(base_name.replace("_02", "_Texture_02"))
        name_variations.append(base_name.replace("_03", "_Texture_03"))
        name_variations.append(base_name.replace("_04", "_Texture_04"))

    # Build list of all directories to search
    all_texture_dirs = [textures_dir]
    if additional_texture_dirs:
        all_texture_dirs.extend(additional_texture_dirs)

    # Try each directory and name variation with each extension
    for search_dir in all_texture_dirs:
        if not search_dir.exists():
            continue
        for name in name_variations:
            for ext in TEXTURE_EXTENSIONS:
                texture_path = search_dir / f"{name}{ext}"
                if texture_path.exists():
                    return texture_path

    # Try recursive search if not found in root of any directory
    for search_dir in all_texture_dirs:
        if not search_dir.exists():
            continue
        for name in name_variations:
            for ext in TEXTURE_EXTENSIONS:
                for texture_path in search_dir.rglob(f"{name}{ext}"):
                    return texture_path

    return None


def generate_texture_import_file(texture_path: Path) -> None:
    """Generate a .import sidecar file for a texture with VRAM compression settings.

    Creates a Godot .import file that configures the texture to use VRAM
    compression (mode=2) with high quality settings. This prevents textures
    from appearing yellow or incorrectly imported in Godot.

    The .import file is placed next to the texture file with the same name
    plus ".import" extension (e.g., "MyTexture.png.import").

    Args:
        texture_path: Absolute path to the texture file that was copied.

    Example:
        >>> generate_texture_import_file(Path("output/textures/Ground_01.png"))
        # Creates: output/textures/Ground_01.png.import
    """
    # Calculate the res:// path for the texture
    # The texture is in textures/ subdirectory, so res://textures/filename
    filename = texture_path.name
    res_path = f"res://textures/{filename}"

    # Generate a unique hash for this texture (based on filename + random)
    # Godot uses this to track imported files
    hash_input = f"{filename}{random.randint(0, 999999999)}"
    file_hash = hashlib.md5(hash_input.encode()).hexdigest()[:12]

    # Generate a unique uid (Godot's resource UID format)
    # Format: alphanumeric characters, variable length
    uid_chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    uid = "".join(random.choice(uid_chars) for _ in range(5 + random.randint(0, 8)))

    # Format the template
    import_content = TEXTURE_IMPORT_TEMPLATE.format(
        uid=uid,
        filename=filename,
        hash=file_hash,
        res_path=res_path,
    )

    # Write the .import file
    import_path = texture_path.parent / f"{filename}.import"
    import_path.write_text(import_content, encoding="utf-8")
    logger.debug("Generated import file: %s", import_path.name)


def copy_textures(
    source_textures: Path,
    output_textures: Path,
    required: set[str],
    dry_run: bool,
    fallback_texture: Path | None = None,
    texture_guid_to_path: dict[str, Path] | None = None,
    texture_name_to_guid: dict[str, str] | None = None,
    additional_texture_dirs: list[Path] | None = None,
) -> tuple[int, int, int]:
    """Copy required texture files from SourceFiles/Textures to output/textures/.

    Iterates through the set of required texture names, finds each one in the
    source directory (using find_texture_file), and copies it to the output.
    Original file extensions are preserved. For each copied texture, a .import
    sidecar file is also generated with VRAM compression settings.

    When texture_guid_to_path and texture_name_to_guid are provided, textures
    are first looked up by GUID and copied from the temp files extracted from
    the .unitypackage. This is preferred over SourceFiles as it ensures the
    exact texture referenced by the material is used.

    When a texture is not found and a fallback texture is provided, the fallback
    is copied with the missing texture's name. This ensures materials referencing
    generic textures (like Generic_Rock.png) still work by using the pack's main
    texture atlas as a substitute.

    Args:
        source_textures: Primary source textures directory (e.g., SourceFiles/Textures).
        output_textures: Destination textures directory (e.g., output/textures).
            Must already exist.
        required: Set of texture names to copy. Can include extensions or just
            stems (e.g., {"Ground_01", "Foliage_02.png"}).
        dry_run: If True, only log what would be copied without actually
            copying files.
        fallback_texture: Optional path to a fallback texture (typically the pack's
            main Texture_01.png atlas). When provided, missing textures will be
            substituted with copies of this fallback.
        texture_guid_to_path: Optional mapping of texture GUID to temp file path.
            When provided along with texture_name_to_guid, textures are copied
            from temp files extracted from the .unitypackage.
        texture_name_to_guid: Optional reverse mapping of texture name to GUID.
            Used to look up the GUID for a texture name.
        additional_texture_dirs: Optional list of additional Textures directories
            to search (for complex nested structures like Dwarven Dungeon).

    Returns:
        Tuple of (textures_copied, textures_fallback, textures_missing) where:
        - textures_copied: Number of files successfully copied (or would be in dry_run)
        - textures_fallback: Number of textures substituted with fallback
        - textures_missing: Number of textures not found and no fallback available

    Example:
        >>> copied, fallback, missing = copy_textures(
        ...     Path("SourceFiles/Textures"),
        ...     Path("output/textures"),
        ...     {"Ground_01", "Trees_02"},
        ...     dry_run=False,
        ...     fallback_texture=Path("SourceFiles/Textures/Pack_Texture_01.png")
        ... )
        >>> print(f"Copied {copied}, fallback {fallback}, missing {missing}")
        Copied 2, fallback 0, missing 0
    """
    copied = 0
    fallback_count = 0
    missing = 0
    from_temp = 0
    from_source = 0

    for texture_name in required:
        # First, try to find texture in temp files from .unitypackage
        temp_path = None
        if texture_guid_to_path and texture_name_to_guid:
            guid = texture_name_to_guid.get(texture_name)
            if guid:
                temp_path = texture_guid_to_path.get(guid)

        if temp_path and temp_path.exists():
            # Copy from temp file
            dest_path = output_textures / texture_name

            if dry_run:
                logger.info("[DRY RUN] Would copy texture from temp: %s", texture_name)
            else:
                shutil.copy2(temp_path, dest_path)
                generate_texture_import_file(dest_path)
                logger.debug("Copied texture from temp: %s", texture_name)

            copied += 1
            from_temp += 1
            continue

        # Fall back to SourceFiles search (including additional directories)
        source_path = find_texture_file(source_textures, texture_name, additional_texture_dirs)

        if source_path is None:
            # Texture not found - try fallback
            if fallback_texture is not None and fallback_texture.exists():
                # Determine the destination filename
                # Strip extension from texture_name if present, use fallback's extension
                base_name = texture_name
                for ext in TEXTURE_EXTENSIONS:
                    if texture_name.lower().endswith(ext.lower()):
                        base_name = texture_name[:-len(ext)]
                        break

                # Use fallback's extension
                dest_name = base_name + fallback_texture.suffix
                dest_path = output_textures / dest_name

                if dry_run:
                    logger.info(
                        "[DRY RUN] Would copy fallback texture: %s -> %s (for missing %s)",
                        fallback_texture.name, dest_name, texture_name
                    )
                else:
                    shutil.copy2(fallback_texture, dest_path)
                    generate_texture_import_file(dest_path)
                    logger.debug(
                        "Copied fallback texture: %s -> %s (for missing %s)",
                        fallback_texture.name, dest_name, texture_name
                    )

                fallback_count += 1
            else:
                logger.warning("Texture not found in package or SourceFiles: %s", texture_name)
                missing += 1
            continue

        # Use the requested texture name (what materials expect), but with source's extension
        # This handles the Synty naming inconsistency where SourceFiles have "Texture" in the name
        # but Unity/materials reference without it (e.g., PolygonSamurai_01_A vs PolygonSamurai_Texture_01_A)
        base_name = texture_name
        for ext in TEXTURE_EXTENSIONS:
            if texture_name.lower().endswith(ext.lower()):
                base_name = texture_name[:-len(ext)]
                break
        dest_name = base_name + source_path.suffix
        dest_path = output_textures / dest_name

        if dry_run:
            logger.info("[DRY RUN] Would copy texture: %s -> %s", source_path.name, dest_name)
        else:
            shutil.copy2(source_path, dest_path)
            generate_texture_import_file(dest_path)
            if source_path.name != dest_name:
                logger.debug("Copied texture: %s -> %s (renamed)", source_path.name, dest_name)
            else:
                logger.debug("Copied texture: %s", source_path.name)

        copied += 1
        from_source += 1

    # Log summary with source breakdown
    if from_temp > 0 or from_source > 0:
        logger.info(
            "Copied %d textures (%d from package, %d from SourceFiles), %d fallback, %d missing",
            copied, from_temp, from_source, fallback_count, missing
        )
    elif fallback_count > 0:
        logger.info(
            "Copied %d textures, %d using fallback atlas, %d missing",
            copied, fallback_count, missing
        )
    else:
        logger.info("Copied %d textures, %d missing", copied, missing)

    return copied, fallback_count, missing


def copy_fbx_files(
    source_fbx_dir: Path,
    output_models_dir: Path,
    dry_run: bool,
    filter_pattern: str | None = None,
    additional_fbx_dirs: list[Path] | None = None,
) -> tuple[int, int]:
    """Copy FBX files from FBX directories to output/models/, preserving structure.

    Recursively finds all .fbx files (case-insensitive) in the source directory
    (and any additional directories) and copies them to the output, preserving
    the subdirectory structure. Files that already exist with the same size are
    skipped.

    Args:
        source_fbx_dir: Primary FBX directory containing FBX models.
        output_models_dir: Path to output/models directory. Subdirectories will
            be created as needed to preserve structure.
        dry_run: If True, only log what would be copied without actually
            copying files.
        filter_pattern: Optional filter pattern for FBX filenames. If specified,
            only FBX files containing this pattern (case-insensitive) are copied.
            If None, all FBX files are copied.
        additional_fbx_dirs: Optional list of additional FBX directories to search
            (for complex nested structures like Dwarven Dungeon).

    Returns:
        Tuple of (fbx_copied, fbx_skipped) where:
        - fbx_copied: Number of FBX files copied (or would be in dry_run)
        - fbx_skipped: Number of FBX files skipped due to existing at destination
          with matching file size

    Example:
        >>> copied, skipped = copy_fbx_files(
        ...     Path("SourceFiles/FBX"),
        ...     Path("output/models"),
        ...     dry_run=False
        ... )
        >>> print(f"Copied {copied} FBX files, skipped {skipped}")
        Copied 150 FBX files, skipped 0
    """
    copied = 0
    skipped = 0

    # Build list of all FBX directories to search
    all_fbx_dirs = [source_fbx_dir]
    if additional_fbx_dirs:
        all_fbx_dirs.extend(additional_fbx_dirs)

    # Find all FBX files from all directories
    fbx_files: list[tuple[Path, Path]] = []  # (source_path, base_dir)
    for fbx_dir in all_fbx_dirs:
        if not fbx_dir.exists():
            logger.debug("FBX directory not found, skipping: %s", fbx_dir)
            continue
        # Find all FBX files recursively (case-insensitive)
        dir_files = list(fbx_dir.rglob("*.fbx")) + list(fbx_dir.rglob("*.FBX"))
        for f in dir_files:
            fbx_files.append((f, fbx_dir))

    # Remove duplicates (Windows is case-insensitive)
    seen_paths: set[Path] = set()
    unique_fbx_files: list[tuple[Path, Path]] = []
    for source_path, base_dir in fbx_files:
        resolved = source_path.resolve()
        if resolved not in seen_paths:
            seen_paths.add(resolved)
            unique_fbx_files.append((source_path, base_dir))
    fbx_files = unique_fbx_files

    if not fbx_files:
        dirs_checked = ", ".join(str(d) for d in all_fbx_dirs if d.exists())
        if dirs_checked:
            logger.warning("No FBX files found in: %s", dirs_checked)
        else:
            logger.warning("No FBX directories found")
        return 0, 0

    # Apply filter pattern if specified
    if filter_pattern:
        pattern_lower = filter_pattern.lower()
        original_count = len(fbx_files)
        fbx_files = [(f, d) for f, d in fbx_files if pattern_lower in f.stem.lower()]
        logger.info(
            "Filter '%s' matched %d of %d FBX files",
            filter_pattern, len(fbx_files), original_count
        )

    if not fbx_files:
        dirs_str = ", ".join(str(d) for d in all_fbx_dirs)
        logger.warning("No FBX files found after filtering in: %s", dirs_str)
        return 0, 0

    logger.info("Found %d FBX files to copy", len(fbx_files))

    for source_path, base_dir in fbx_files:
        # Calculate relative path to preserve subdirectory structure
        # Use the base_dir this file came from to compute relative path
        relative_path = source_path.relative_to(base_dir)
        dest_path = output_models_dir / relative_path

        # Skip if destination already exists and is same size
        if dest_path.exists():
            if dest_path.stat().st_size == source_path.stat().st_size:
                logger.debug("Skipping existing FBX: %s", relative_path)
                skipped += 1
                continue

        if dry_run:
            logger.info("[DRY RUN] Would copy FBX: %s", relative_path)
            copied += 1
        else:
            # Ensure parent directory exists
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, dest_path)
            logger.debug("Copied FBX: %s", relative_path)
            copied += 1

    logger.info("Copied %d FBX files, skipped %d existing", copied, skipped)
    return copied, skipped


def generate_converter_config(
    project_dir: Path,
    keep_meshes_together: bool,
    mesh_format: str,
    filter_pattern: str | None,
    dry_run: bool,
) -> None:
    """Generate converter_config.json for Godot's godot_converter.gd script.

    This JSON file passes configuration options from the Python CLI to the
    GDScript converter. The config is placed in the project root where
    godot_converter.gd will read it.

    Args:
        project_dir: Path to the Godot project directory.
        keep_meshes_together: If True, keep all meshes from one FBX together
            in a single scene file.
        mesh_format: Output format - 'tscn' (text) or 'res' (binary).
        filter_pattern: Optional filter pattern for FBX filenames.
        dry_run: If True, only log what would be written.
    """
    config = {
        "keep_meshes_together": keep_meshes_together,
        "mesh_format": mesh_format,
        "filter_pattern": filter_pattern,
    }

    config_path = project_dir / "converter_config.json"

    if dry_run:
        logger.info("[DRY RUN] Would write converter_config.json: %s", config)
    else:
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        logger.debug("Wrote converter_config.json: %s", config)


def run_godot_cli(
    godot_exe: Path,
    project_dir: Path,
    timeout_seconds: int,
    dry_run: bool,
    skip_import: bool = False,
    keep_meshes_together: bool = False,
    mesh_format: str = "tscn",
    filter_pattern: str | None = None,
) -> tuple[bool, bool, bool]:
    """Run Godot CLI in two phases: import and convert.

    This function orchestrates the Godot CLI operations needed to import
    FBX models and convert them to Godot scene files (.tscn).

    Phase 1 - Import:
        Runs: godot --headless --import --path <project_dir>
        This triggers Godot's asset import system to process all FBX files
        in the models/ directory, generating .import files and .scn resources.
        Can be skipped with skip_import=True for large projects where the
        import step times out. In that case, open the project in Godot manually
        to trigger asset import before running the converter.

    Phase 2 - Convert:
        Runs: godot --headless --script res://godot_converter.gd --path <project_dir>
        This executes the godot_converter.gd script which converts imported
        models to .tscn scene files in the meshes/ directory.

    The godot_converter.gd script is copied from the converter project to the
    output project directory before execution. A converter_config.json file
    is also generated to pass configuration options to the GDScript.

    Args:
        godot_exe: Path to Godot 4.6 executable. Must exist.
        project_dir: Path to the Godot project directory containing project.godot.
            The models/ and meshes/ directories should be present.
        timeout_seconds: Maximum time in seconds for each phase. If exceeded,
            the subprocess is terminated and timeout_occurred is set True.
        dry_run: If True, only log what would be executed without running Godot.
        skip_import: If True, skip the import phase and only run the converter
            script. Useful for large projects where Godot's headless import
            times out. The user must open the project in Godot manually first.
        keep_meshes_together: If True, keep all meshes from one FBX together
            in a single scene file. If False (default), each mesh is saved
            as a separate scene file.
        mesh_format: Output format for mesh scenes - 'tscn' (text, default)
            or 'res' (binary compiled resource).
        filter_pattern: Optional filter pattern for FBX filenames. Only FBX
            files containing this pattern (case-insensitive) are processed.

    Returns:
        Tuple of (import_success, convert_success, timeout_occurred) where:
        - import_success: True if Phase 1 completed with exit code 0, or True
          if Phase 1 was skipped via skip_import
        - convert_success: True if Phase 2 completed with exit code 0
        - timeout_occurred: True if either phase exceeded the timeout

    Raises:
        No exceptions are raised; errors are logged and reflected in return values.

    Example:
        >>> import_ok, convert_ok, timed_out = run_godot_cli(
        ...     Path("C:/Godot/Godot.exe"),
        ...     Path("output"),
        ...     timeout_seconds=300,
        ...     dry_run=False
        ... )
        >>> if import_ok and convert_ok:
        ...     print("Conversion successful!")
    """
    if not godot_exe.exists():
        logger.error("Godot executable not found: %s", godot_exe)
        return False, False, False

    project_godot = project_dir / "project.godot"
    if not project_godot.exists():
        logger.error("project.godot not found in: %s", project_dir)
        return False, False, False

    # Copy godot_converter.gd to project directory
    script_dir = Path(__file__).parent
    converter_script = script_dir / "godot_converter.gd"
    dest_script = project_dir / "godot_converter.gd"

    if not converter_script.exists():
        logger.error("godot_converter.gd not found: %s", converter_script)
        return False, False, False

    if not dry_run:
        shutil.copy2(converter_script, dest_script)
        logger.debug("Copied godot_converter.gd to project")

    # Generate converter config JSON for the GDScript to read
    generate_converter_config(
        project_dir,
        keep_meshes_together,
        mesh_format,
        filter_pattern,
        dry_run,
    )

    import_success = False
    convert_success = False
    timeout_occurred = False

    # Phase 1: Import (can be skipped for large projects that timeout)
    if skip_import:
        logger.info("Skipping Godot import phase (--skip-godot-import)")
        logger.info("Note: You must open the project in Godot manually to trigger asset import")
        import_success = True  # Treat as success so converter phase runs
    else:
        import_cmd = [
            str(godot_exe),
            "--headless",
            "--import",
            "--path", str(project_dir),
        ]

        if dry_run:
            logger.info("[DRY RUN] Would run: %s", " ".join(import_cmd))
            import_success = True
        else:
            logger.info("Running Godot import (timeout: %ds)...", timeout_seconds)
            logger.debug("Command: %s", " ".join(import_cmd))

            try:
                start_time = time.time()
                result = subprocess.run(
                    import_cmd,
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                )
                elapsed = time.time() - start_time

                if result.returncode == 0:
                    logger.info("Godot import completed in %.1fs", elapsed)
                    import_success = True
                else:
                    logger.error("Godot import failed (exit code %d)", result.returncode)
                    if result.stderr:
                        logger.error("Stderr: %s", result.stderr[:1000])

            except subprocess.TimeoutExpired:
                logger.error("Godot import timed out after %ds", timeout_seconds)
                timeout_occurred = True
                return import_success, convert_success, timeout_occurred

            except Exception as e:
                logger.error("Failed to run Godot import: %s", e)
                return import_success, convert_success, timeout_occurred

        if not import_success and not dry_run:
            return import_success, convert_success, timeout_occurred

    # Phase 2: Convert
    convert_cmd = [
        str(godot_exe),
        "--headless",
        "--script", "res://godot_converter.gd",
        "--path", str(project_dir),
    ]

    if dry_run:
        logger.info("[DRY RUN] Would run: %s", " ".join(convert_cmd))
        convert_success = True
    else:
        logger.info("Running Godot converter script (timeout: %ds)...", timeout_seconds)
        logger.debug("Command: %s", " ".join(convert_cmd))

        try:
            start_time = time.time()
            result = subprocess.run(
                convert_cmd,
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            elapsed = time.time() - start_time

            if result.returncode == 0:
                logger.info("Godot converter completed in %.1fs", elapsed)
                convert_success = True

                # Log output for debugging
                if result.stdout:
                    for line in result.stdout.strip().split("\n"):
                        logger.debug("Godot: %s", line)
            else:
                logger.error("Godot converter failed (exit code %d)", result.returncode)
                if result.stderr:
                    logger.error("Stderr: %s", result.stderr[:1000])
                if result.stdout:
                    logger.error("Stdout: %s", result.stdout[:1000])

        except subprocess.TimeoutExpired:
            logger.error("Godot converter timed out after %ds", timeout_seconds)
            timeout_occurred = True

        except Exception as e:
            logger.error("Failed to run Godot converter: %s", e)

    return import_success, convert_success, timeout_occurred


def count_mesh_files(meshes_dir: Path, mesh_format: str = "tscn") -> int:
    """Count mesh scene files in the meshes directory.

    Recursively counts all files with the specified extension in the given
    directory. Used to verify the Godot converter script produced output.

    Args:
        meshes_dir: Path to the meshes/ directory to search.
        mesh_format: File extension to count - 'tscn' or 'res'.

    Returns:
        Number of mesh files found, or 0 if the directory does not exist.
    """
    if not meshes_dir.exists():
        return 0
    return len(list(meshes_dir.rglob(f"*.{mesh_format}")))


def _extract_shader_globals_section(content: str) -> str:
    """Extract the [shader_globals] section from a project.godot content string.

    Args:
        content: Full project.godot file content.

    Returns:
        The [shader_globals] section including the header, or empty string if not found.
    """
    lines = content.split("\n")
    in_section = False
    section_lines = []

    for line in lines:
        if line.strip() == "[shader_globals]":
            in_section = True
            section_lines.append(line)
        elif in_section:
            # New section starts - stop collecting
            if line.startswith("[") and line.endswith("]"):
                break
            section_lines.append(line)

    return "\n".join(section_lines)


def _parse_shader_globals(section: str) -> dict[str, str]:
    """Parse shader globals section into a dict of uniform_name -> full definition.

    Args:
        section: The [shader_globals] section content (including or excluding header).

    Returns:
        Dictionary mapping uniform names to their full definition strings.
    """
    uniforms: dict[str, str] = {}
    lines = section.split("\n")
    current_name = None
    current_lines: list[str] = []

    for line in lines:
        if line.strip() == "[shader_globals]":
            continue

        # Check if this is a new uniform definition (Name={)
        if "={" in line and not line.startswith(" ") and not line.startswith("\t"):
            # Save previous uniform if any
            if current_name:
                uniforms[current_name] = "\n".join(current_lines)

            # Start new uniform
            name_part = line.split("={")[0]
            current_name = name_part.strip()
            current_lines = [line]
        elif current_name:
            current_lines.append(line)
            # Check if uniform definition is complete (ends with })
            if line.strip() == "}":
                uniforms[current_name] = "\n".join(current_lines)
                current_name = None
                current_lines = []

    # Handle last uniform if not closed properly
    if current_name:
        uniforms[current_name] = "\n".join(current_lines)

    return uniforms


def _merge_shader_globals(existing_content: str, template_section: str) -> str:
    """Merge shader globals from template into existing project.godot content.

    Args:
        existing_content: Full existing project.godot file content.
        template_section: The [shader_globals] section from template to merge.

    Returns:
        Updated project.godot content with merged shader globals.
    """
    # Extract existing shader globals section
    existing_section = _extract_shader_globals_section(existing_content)

    # Parse uniforms from both
    template_uniforms = _parse_shader_globals(template_section)
    existing_uniforms = _parse_shader_globals(existing_section) if existing_section else {}

    # Find uniforms to add (in template but not in existing)
    new_uniforms = {
        name: definition
        for name, definition in template_uniforms.items()
        if name not in existing_uniforms
    }

    if not new_uniforms:
        logger.info("All shader uniforms already present in existing project.godot")
        return existing_content

    logger.info("Adding %d new shader uniform(s): %s", len(new_uniforms), ", ".join(new_uniforms.keys()))

    if existing_section:
        # Append new uniforms to existing section
        # Find where the existing section ends and insert before next section
        lines = existing_content.split("\n")
        result_lines = []
        in_section = False
        section_ended = False

        for i, line in enumerate(lines):
            if line.strip() == "[shader_globals]":
                in_section = True
                result_lines.append(line)
            elif in_section and line.startswith("[") and line.endswith("]"):
                # New section starts - insert new uniforms before it
                in_section = False
                section_ended = True
                for uniform_def in new_uniforms.values():
                    result_lines.append(uniform_def)
                result_lines.append(line)
            else:
                result_lines.append(line)

        # If we were still in section at EOF, append uniforms
        if in_section and not section_ended:
            for uniform_def in new_uniforms.values():
                result_lines.append(uniform_def)

        return "\n".join(result_lines)
    else:
        # No existing shader_globals section - append the entire template section
        return existing_content.rstrip() + "\n\n" + template_section


def generate_project_godot(
    output_dir: Path,
    pack_name: str,
    dry_run: bool,
) -> None:
    """Write or update project.godot with global shader uniforms.

    If project.godot already exists, merges in any missing shader uniforms
    from the template while preserving all other settings (project name, etc.).

    If project.godot does not exist, creates a new file with the pack name
    and all shader uniforms from the template.

    Args:
        output_dir: Output directory where project.godot will be written/updated.
        pack_name: Name of the pack to use as the project name (only used when
            creating a new file).
        dry_run: If True, only log what would be written.
    """
    project_path = output_dir / "project.godot"

    if dry_run:
        if project_path.exists():
            logger.info("[DRY RUN] Would merge shader uniforms into: %s", project_path)
        else:
            logger.info("[DRY RUN] Would write project.godot to: %s", project_path)
        return

    if project_path.exists():
        # Read existing content
        existing_content = project_path.read_text(encoding="utf-8")

        # Extract shader_globals section from template
        template_section = _extract_shader_globals_section(PROJECT_GODOT_TEMPLATE)

        if not template_section:
            logger.warning("No [shader_globals] section found in template")
            return

        # Merge uniforms
        updated_content = _merge_shader_globals(existing_content, template_section)

        # Write back
        project_path.write_text(updated_content, encoding="utf-8")
        logger.info("Updated project.godot with merged shader uniforms")
    else:
        # Create new project.godot with pack name
        project_content = PROJECT_GODOT_TEMPLATE.replace(
            'config/name="Synty Converted Assets"',
            f'config/name="{pack_name}"'
        )
        project_path.write_text(project_content, encoding="utf-8")
        logger.info("Wrote project.godot with project name '%s'", pack_name)


def write_conversion_log(output_dir: Path, stats: ConversionStats, config: ConversionConfig) -> None:
    """Write a summary log file with all warnings and errors.

    Args:
        output_dir: Output directory where conversion_log.txt will be written.
        stats: Conversion statistics.
        config: Conversion configuration.
    """
    log_path = output_dir / "conversion_log.txt"

    lines = [
        "=" * 60,
        "Synty Shader Converter - Conversion Log",
        "=" * 60,
        f"Date: {datetime.now().isoformat()}",
        f"Unity Package: {config.unity_package}",
        f"Source Files: {config.source_files}",
        f"Output Directory: {config.output_dir}",
        f"Dry Run: {config.dry_run}",
        "",
        "Statistics:",
        f"  Materials Parsed: {stats.materials_parsed}",
        f"  Materials Generated: {stats.materials_generated}",
        f"  Materials Missing: {stats.materials_missing}",
        f"  Textures Copied: {stats.textures_copied}",
        f"  Textures Fallback: {stats.textures_fallback}",
        f"  Textures Missing: {stats.textures_missing}",
        f"  Shaders Copied: {stats.shaders_copied}",
        f"  FBX Files Copied: {stats.fbx_copied}",
        f"  FBX Files Skipped: {stats.fbx_skipped}",
        f"  Meshes Converted: {stats.meshes_converted}",
        "",
        "Godot CLI Status:",
        f"  Import Success: {stats.godot_import_success}",
        f"  Convert Success: {stats.godot_convert_success}",
        f"  Timeout Occurred: {stats.godot_timeout_occurred}",
        "",
    ]

    if stats.warnings:
        lines.append(f"Warnings ({len(stats.warnings)}):")
        for warning in stats.warnings:
            lines.append(f"  - {warning}")
        lines.append("")

    if stats.errors:
        lines.append(f"Errors ({len(stats.errors)}):")
        for error in stats.errors:
            lines.append(f"  - {error}")
        lines.append("")

    lines.append("=" * 60)

    log_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote conversion log to: %s", log_path)


def print_summary(stats: ConversionStats) -> None:
    """Print conversion summary to console.

    Args:
        stats: Conversion statistics.
    """
    print("\n" + "=" * 60)
    print("Conversion Complete")
    print("=" * 60)
    print(f"  Materials Parsed:    {stats.materials_parsed}")
    print(f"  Materials Generated: {stats.materials_generated}")
    if stats.materials_missing > 0:
        print(f"  Materials Missing:   {stats.materials_missing}")
    print(f"  Textures Copied:     {stats.textures_copied}")
    print(f"  Textures Missing:    {stats.textures_missing}")
    print(f"  Shaders Copied:      {stats.shaders_copied}")
    print(f"  FBX Files Copied:    {stats.fbx_copied}")
    if stats.fbx_skipped > 0:
        print(f"  FBX Files Skipped:   {stats.fbx_skipped} (already existed)")
    print(f"  Meshes Converted:    {stats.meshes_converted}")

    # Godot CLI status
    if stats.godot_import_success and stats.godot_convert_success:
        print("  Godot CLI:           Success")
    elif stats.godot_import_success and stats.meshes_converted > 0:
        # Meshes were converted even if script reported warnings
        print("  Godot CLI:           Success (with warnings)")
    elif stats.godot_timeout_occurred:
        print("  Godot CLI:           TIMEOUT")
    elif not stats.godot_import_success and not stats.godot_convert_success:
        print("  Godot CLI:           Skipped")
    elif not stats.godot_import_success:
        print("  Godot CLI:           Import Failed")
    elif not stats.godot_convert_success:
        print("  Godot CLI:           Conversion Failed")

    if stats.warnings:
        print(f"\n  Warnings: {len(stats.warnings)}")

    if stats.errors:
        print(f"\n  Errors: {len(stats.errors)}")
        for error in stats.errors[:5]:
            print(f"    - {error}")
        if len(stats.errors) > 5:
            print(f"    ... and {len(stats.errors) - 5} more")

    print("=" * 60 + "\n")


def build_shader_cache(
    prefabs: list[PrefabMaterials],
) -> tuple[dict[str, str], list[str]]:
    """Build shader decision cache from MaterialList prefabs with LOD inheritance.

    Uses the simplified detection flow:
    1. If uses_custom_shader=False -> polygon.gdshader (immediate)
    2. If uses_custom_shader=True -> name pattern matching -> shader or polygon
    3. LOD inheritance: LOD0's shader decision applies to all LODs

    Args:
        prefabs: List of PrefabMaterials from parse_material_list().

    Returns:
        Tuple of (shader_cache, unmatched_materials) where:
        - shader_cache: Maps material_name -> shader_filename
        - unmatched_materials: Materials that need manual pattern addition
    """
    shader_cache: dict[str, str] = {}
    unmatched_materials: list[str] = []

    for prefab in prefabs:
        # Track shader decisions per slot index within this prefab
        # This enables LOD inheritance: LOD0's slot 0 shader -> all LODs' slot 0
        prefab_slot_shaders: dict[int, str] = {}

        for mesh_idx, mesh in enumerate(prefab.meshes):
            is_lod0 = mesh_idx == 0  # First mesh is LOD0

            for slot_idx, slot in enumerate(mesh.slots):
                mat_name = slot.material_name

                if mat_name in shader_cache:
                    continue  # Already decided

                if is_lod0:
                    # LOD0: make the shader decision
                    shader, matched = determine_shader(mat_name, slot.uses_custom_shader)

                    shader_cache[mat_name] = shader
                    prefab_slot_shaders[slot_idx] = shader

                    if not matched:
                        unmatched_materials.append(mat_name)
                else:
                    # LOD1+: inherit from LOD0's slot
                    if slot_idx in prefab_slot_shaders:
                        shader_cache[mat_name] = prefab_slot_shaders[slot_idx]
                    else:
                        # No LOD0 slot to inherit from, use custom shader check
                        shader, matched = determine_shader(mat_name, slot.uses_custom_shader)
                        shader_cache[mat_name] = shader
                        if not matched:
                            unmatched_materials.append(mat_name)

    return shader_cache, unmatched_materials


def run_conversion(config: ConversionConfig) -> ConversionStats:
    """Execute the full conversion pipeline.

    This is the main orchestration function that runs all conversion steps
    in sequence. The pipeline steps are:

    1. Validate inputs (already done in parse_args)
    2. Create output directory structure (shaders/, textures/, materials/, etc.)
    3. Extract Unity package and build GUID mappings
    4. Parse all .mat files from the package
    4.5. Parse MaterialList*.txt early (for shader detection cache)
    4.6. Build shader cache with LOD inheritance using determine_shader()
    5. Map material properties to Godot equivalents (using shader cache)
    6. Generate .tres material files
    7. Copy .gdshader files from the converter project
    8. Copy required textures from SourceFiles/Textures
    8.5. Copy FBX files from SourceFiles/FBX (unless --skip-fbx-copy)
    9. Generate mesh_material_mapping.json (uses cached prefabs)
    10. Generate project.godot with global shader uniforms (if not existing project)
    11. Run Godot CLI to convert FBX to .tscn (unless --skip-godot-cli)

    Args:
        config: ConversionConfig instance with all required paths and options.

    Returns:
        ConversionStats populated with all metrics, warnings, and errors
        encountered during the conversion process.

    Raises:
        No exceptions are raised to the caller; all errors are captured in
        ConversionStats.errors and logged.

    Example:
        >>> config = ConversionConfig(...)
        >>> stats = run_conversion(config)
        >>> if stats.errors:
        ...     print(f"Conversion failed with {len(stats.errors)} errors")
        ... else:
        ...     print(f"Success! Generated {stats.materials_generated} materials")
    """
    stats = ConversionStats()

    # Extract pack name from source_files parent directory
    # e.g., C:\SyntyComplete\PolygonNature\SourceFiles -> pack_name = "PolygonNature"
    raw_pack_name = config.source_files.parent.name
    # Sanitize to remove invalid filesystem characters
    pack_name = sanitize_filename(raw_pack_name)
    if pack_name != raw_pack_name:
        logger.warning("Pack name sanitized: '%s' -> '%s'", raw_pack_name, pack_name)

    # Consistent output structure:
    # - project.godot at output_dir root (create new or merge uniforms)
    # - shaders/ at output_dir root (shared across all packs)
    # - PackName/ subfolder for pack-specific assets
    pack_output_dir = config.output_dir / pack_name
    shaders_dir = config.output_dir / "shaders"
    project_dir = config.output_dir

    # Step 1: Validate inputs (already done in parse_args, but double-check)
    logger.info("Starting conversion pipeline...")
    logger.info("  Pack Name: %s", pack_name)
    logger.info("  Unity Package: %s", config.unity_package)
    logger.info("  Source Files: %s", config.source_files)
    logger.info("  Pack Output: %s", pack_output_dir)
    logger.info("  Shaders Dir: %s", shaders_dir)
    logger.info("  Project Dir: %s", project_dir)

    # Step 2: Create output directory structure
    logger.info("Creating output directory structure...")
    setup_output_directories(pack_output_dir, config.dry_run)

    # Step 3: Extract Unity package
    logger.info("Extracting Unity package...")
    try:
        guid_map: GuidMap = extract_unitypackage(config.unity_package)
        logger.info("Extracted %d assets from Unity package", len(guid_map.guid_to_pathname))
    except Exception as e:
        error_msg = f"Failed to extract Unity package: {e}"
        logger.error(error_msg)
        stats.errors.append(error_msg)
        return stats

    # Store temp dir path for cleanup (always runs via finally, even on error)
    temp_dir_to_cleanup = None
    if guid_map.texture_guid_to_path:
        temp_dir_to_cleanup = next(iter(guid_map.texture_guid_to_path.values())).parent

    try:
        # Step 4: Parse all .mat files
        logger.info("Parsing Unity materials...")
        material_guids = get_material_guids(guid_map)
        unity_materials: list[tuple[str, UnityMaterial]] = []

        for guid in material_guids:
            content = guid_map.guid_to_content.get(guid)
            if content is None:
                warning_msg = f"No content for material GUID: {guid}"
                logger.warning(warning_msg)
                stats.warnings.append(warning_msg)
                continue

            try:
                material = parse_material_bytes(content)
                unity_materials.append((guid, material))
                stats.materials_parsed += 1
            except Exception as e:
                warning_msg = f"Failed to parse material GUID {guid}: {e}"
                logger.warning(warning_msg)
                stats.warnings.append(warning_msg)

        logger.info("Parsed %d Unity materials", stats.materials_parsed)

        # Step 4.5: Parse MaterialList*.txt early for shader detection
        # This needs to happen BEFORE shader detection so we can use the
        # uses_custom_shader information from MaterialList
        # Use rglob for recursive search to handle complex nested structures
        material_list_files = list(config.source_files.rglob("MaterialList*.txt"))
        prefabs: list[PrefabMaterials] = []
        shader_cache: dict[str, str] = {}
        unmatched_materials: list[str] = []

        if material_list_files:
            for material_list_path in material_list_files:
                logger.info("Parsing %s for shader detection...", material_list_path.name)
                try:
                    file_prefabs = parse_material_list(material_list_path)
                    prefabs.extend(file_prefabs)
                    logger.info("  Found %d prefabs in %s", len(file_prefabs), material_list_path.name)
                except Exception as e:
                    logger.warning("Failed to parse %s: %s", material_list_path.name, e)

            logger.info("Total prefabs from all MaterialList files: %d", len(prefabs))

            # Build shader cache with LOD inheritance
            logger.info("Building shader decision cache...")
            shader_cache, unmatched_materials = build_shader_cache(prefabs)
            logger.info("Shader cache: %d materials cached", len(shader_cache))

            # Log unmatched materials for user to add patterns
            if unmatched_materials:
                logger.warning("=" * 60)
                logger.warning("UNMATCHED MATERIALS - Consider adding name patterns for:")
                for mat_name in sorted(set(unmatched_materials)):
                    logger.warning("  - %s", mat_name)
                logger.warning("=" * 60)
        else:
            logger.info("MaterialList*.txt not found, using fallback shader detection")

        # Step 5: Detect shaders and map properties
        logger.info("Mapping materials to Godot format...")
        mapped_materials: list[MappedMaterial] = []
        required_textures: set[str] = set()

        for guid, unity_mat in unity_materials:
            try:
                # Use cached shader decision if available
                cached_shader = shader_cache.get(unity_mat.name)
                mapped = map_material(unity_mat, guid_map.texture_guid_to_name, override_shader=cached_shader)
                mapped_materials.append(mapped)

                # Collect required textures
                for texture_name in mapped.textures.values():
                    required_textures.add(texture_name)

            except Exception as e:
                warning_msg = f"Failed to map material '{unity_mat.name}': {e}"
                logger.warning(warning_msg)
                stats.warnings.append(warning_msg)

        logger.info("Mapped %d materials, requiring %d textures", len(mapped_materials), len(required_textures))

        # Step 6: Generate .tres files
        logger.info("Generating Godot .tres material files...")
        materials_dir = pack_output_dir / "materials"

        # Pack-relative texture path (textures are in pack folder, not root)
        texture_base = f"res://{pack_name}/textures"

        for mapped_mat in mapped_materials:
            try:
                # Generate .tres content
                tres_content = generate_tres(
                    mapped_mat,
                    shader_base="res://shaders",
                    texture_base=texture_base
                )

                # Sanitize filename
                filename = sanitize_filename(mapped_mat.name) + ".tres"
                output_path = materials_dir / filename

                if config.dry_run:
                    logger.info("[DRY RUN] Would write material: %s", output_path)
                else:
                    write_tres_file(tres_content, output_path)
                    logger.debug("Wrote material: %s", filename)

                stats.materials_generated += 1

            except Exception as e:
                warning_msg = f"Failed to generate .tres for '{mapped_mat.name}': {e}"
                logger.warning(warning_msg)
                stats.warnings.append(warning_msg)

        logger.info("Generated %d .tres material files", stats.materials_generated)

        # Step 7: Copy .gdshader files
        logger.info("Copying shader files...")
        stats.shaders_copied = copy_shaders(
            shaders_dir,
            config.dry_run,
        )

        # Step 8: Copy required textures
        # Textures primarily come from .unitypackage extraction (texture_guid_to_path)
        # SourceFiles/Textures is used as optional fallback for any missing textures
        logger.info("Copying texture files...")
        # Find all Textures directories recursively for complex nested structures (optional fallback)
        texture_dirs = [config.source_files / "Textures"]
        if not texture_dirs[0].exists():
            texture_dirs = [d for d in config.source_files.rglob("Textures") if d.is_dir()]
            if texture_dirs:
                logger.info("Found %d Textures directories as fallback sources", len(texture_dirs))
                for td in texture_dirs:
                    logger.debug("  Textures dir: %s", td)
            else:
                logger.info("No SourceFiles/Textures found - using .unitypackage textures only")
        source_textures = texture_dirs[0] if texture_dirs else config.source_files / "Textures"
        # Additional texture directories (all except the primary one)
        additional_texture_dirs = texture_dirs[1:] if len(texture_dirs) > 1 else None
        output_textures = pack_output_dir / "textures"

        # Build reverse lookup: texture_name -> GUID
        texture_name_to_guid = {name: guid for guid, name in guid_map.texture_guid_to_name.items()}

        # Copy required textures (no fallback - missing textures will be logged as warnings)
        # Prefer textures from .unitypackage temp files over SourceFiles
        stats.textures_copied, stats.textures_fallback, stats.textures_missing = copy_textures(
            source_textures,
            output_textures,
            required_textures,
            config.dry_run,
            fallback_texture=None,  # No fallback - let missing textures fail
            texture_guid_to_path=guid_map.texture_guid_to_path,
            texture_name_to_guid=texture_name_to_guid,
            additional_texture_dirs=additional_texture_dirs,
        )

        # Step 8.5: Copy FBX files
        if not config.skip_fbx_copy:
            logger.info("Copying FBX files...")
            # Find all FBX directories recursively for complex nested structures
            # Also check for "Models" directories which some packs use (e.g., Generic folder)
            fbx_dirs = [config.source_files / "FBX"]
            if not fbx_dirs[0].exists():
                # Search for both FBX and Models directories
                fbx_dirs = [d for d in config.source_files.rglob("FBX") if d.is_dir()]
                models_dirs = [d for d in config.source_files.rglob("Models") if d.is_dir()]
                fbx_dirs.extend(models_dirs)
                if fbx_dirs:
                    logger.info("Found %d FBX/Models directories in nested structure", len(fbx_dirs))
                    for fd in fbx_dirs:
                        logger.debug("  FBX/Models dir: %s", fd)
            source_fbx = fbx_dirs[0] if fbx_dirs else config.source_files / "FBX"
            additional_fbx_dirs = fbx_dirs[1:] if len(fbx_dirs) > 1 else None
            output_models = pack_output_dir / "models"

            stats.fbx_copied, stats.fbx_skipped = copy_fbx_files(
                source_fbx,
                output_models,
                config.dry_run,
                config.filter_pattern,
                additional_fbx_dirs=additional_fbx_dirs,
            )

            if stats.fbx_copied == 0 and stats.fbx_skipped == 0:
                dirs_str = ", ".join(str(d) for d in fbx_dirs) if fbx_dirs else str(source_fbx)
                warning_msg = f"No FBX files found in {dirs_str}"
                stats.warnings.append(warning_msg)
        else:
            logger.info("Skipping FBX copy (--skip-fbx-copy)")

        # Step 9: Generate mesh_material_mapping.json (uses prefabs parsed in Step 4.5)
        # Note: mapping goes to shaders_dir to be shared across packs
        if prefabs:
            mapping_output = shaders_dir / "mesh_material_mapping.json"
            if config.dry_run:
                logger.info("[DRY RUN] Would write mesh_material_mapping.json")
            else:
                generate_mesh_material_mapping_json(prefabs, mapping_output)
                logger.info("Generated mesh_material_mapping.json")

            # Step 9.5: Check for missing material references (no placeholders - just warn)
            if not config.dry_run:
                logger.info("Checking for missing material references...")
                materials_dir = pack_output_dir / "materials"
                existing_materials = {f.stem for f in materials_dir.glob("*.tres")}

                # Collect all referenced materials from prefabs
                referenced_materials: set[str] = set()
                for prefab in prefabs:
                    for mesh in prefab.meshes:
                        for slot in mesh.slots:
                            if slot.material_name:
                                referenced_materials.add(slot.material_name)

                # Find missing materials - just warn, don't create placeholders
                missing_materials = referenced_materials - existing_materials
                stats.materials_missing = len(missing_materials)

                if missing_materials:
                    logger.warning(
                        "Found %d missing material(s) - these meshes will use default materials:",
                        len(missing_materials)
                    )
                    for mat_name in sorted(missing_materials):
                        logger.warning("  Missing: %s", mat_name)
                else:
                    logger.info("All referenced materials exist")
            else:
                logger.info("Skipping missing materials check (dry run)")
        else:
            logger.info("No MaterialList data available, skipping mesh-material mapping")

        # Step 11: Generate or update project.godot
        logger.info("Generating/updating project.godot...")
        generate_project_godot(project_dir, pack_name, config.dry_run)

        # Step 12: Run Godot CLI to convert FBX to .tscn scene files
        if not config.skip_godot_cli:
            logger.info("Running Godot CLI conversion...")

            (
                stats.godot_import_success,
                stats.godot_convert_success,
                stats.godot_timeout_occurred,
            ) = run_godot_cli(
                config.godot_exe,
                project_dir,
                config.godot_timeout,
                config.dry_run,
                skip_import=config.skip_godot_import,
                keep_meshes_together=config.keep_meshes_together,
                mesh_format=config.mesh_format,
                filter_pattern=config.filter_pattern,
            )

            # Count generated mesh files
            meshes_dir = pack_output_dir / "meshes"
            stats.meshes_converted = count_mesh_files(meshes_dir, config.mesh_format)

            if stats.godot_timeout_occurred:
                error_msg = f"Godot CLI timed out after {config.godot_timeout}s"
                stats.errors.append(error_msg)
            elif not stats.godot_import_success:
                error_msg = "Godot import phase failed"
                stats.errors.append(error_msg)
            elif not stats.godot_convert_success and stats.meshes_converted == 0:
                # Only error if no meshes were converted at all
                error_msg = "Godot converter script failed"
                stats.errors.append(error_msg)
            elif stats.meshes_converted > 0:
                logger.info("Generated %d .tscn scene files", stats.meshes_converted)
            else:
                logger.warning("No mesh files generated")
        else:
            logger.info("Skipping Godot CLI (--skip-godot-cli)")

        # Write conversion log (not in dry run for the log file itself)
        # Note: log goes to shaders_dir to be shared across packs
        if not config.dry_run:
            write_conversion_log(shaders_dir, stats, config)

        return stats

    finally:
        # Cleanup temp texture files (always runs, even on error)
        if temp_dir_to_cleanup and temp_dir_to_cleanup.exists():
            shutil.rmtree(temp_dir_to_cleanup, ignore_errors=True)
            logger.info("Cleaned up temp texture directory: %s", temp_dir_to_cleanup)


def main() -> int:
    """CLI entry point.

    Returns:
        Exit code (0 for success, 1 for errors).
    """
    # Parse arguments
    try:
        config = parse_args()
    except SystemExit:
        return 1

    # Setup logging
    log_level = logging.DEBUG if config.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s: %(message)s",
    )

    # Run conversion
    try:
        stats = run_conversion(config)
    except KeyboardInterrupt:
        print("\nConversion interrupted by user.")
        return 1
    except Exception as e:
        logger.exception("Unexpected error during conversion: %s", e)
        return 1

    # Print summary
    print_summary(stats)

    # Return error code if there were critical errors
    if stats.errors:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
