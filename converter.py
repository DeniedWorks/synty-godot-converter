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
from tres_generator import (
    generate_tres,
    sanitize_filename,
    stamp_resource_uids,
    write_tres_file,
)
from material_list import (
    parse_material_list,
    generate_mesh_material_mapping_json,
    get_custom_shader_materials,
    PrefabMaterials,
)
from retarget import inject_subresources, render_bone_map, resolve_bone_map
from prefab_parser import (
    build_fbx_material_fallback,
    build_prefabs_from_package,
    build_character_definitions,
    write_character_definitions_json,
)
from sidekick import (
    SIDEKICK_PARTS_DIRNAME,
    build_sidekick_recipes,
    derive_gear_sets_from_names,
    find_master_color_map,
    find_sidekick_database,
    load_color_tables,
    load_part_presets,
    load_rig_adjustments,
    write_sidekick_characters_json,
    write_sidekick_colors_json,
    write_sidekick_gear_sets_json,
    write_sidekick_rig_adjustments_json,
)

logger = logging.getLogger(__name__)

# Records which metadata schema a converted pack was written against, so an
# existing pack converted by an earlier version refreshes its metadata instead
# of skipping ahead forever with whatever fields that version happened to emit.
# Bump this whenever the shape *or the content* of mesh_material_mapping.json,
# fbx_material_fallback.json, character_definitions.json,
# sidekick_characters.json or sidekick_rig_adjustments.json changes. A fix that derives more than the last
# version did is exactly as stale to an existing pack as a renamed field: the
# pack skips straight to mesh generation and keeps the thinner mapping forever.
PACK_METADATA_FILENAME = "pack_metadata.json"
PACK_METADATA_VERSION = 8


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

    # Log debug if no assets found (will be reported later if it's a real problem)
    logger.debug("No MaterialList, FBX, or Models found in: %s", source_files)
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
# High quality version: BPTC compression (mode=2) with high quality - slower import, better quality
TEXTURE_IMPORT_TEMPLATE_HIGH_QUALITY = """[remap]

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

# Lossless version: No compression (mode=0) - faster Godot import times
TEXTURE_IMPORT_TEMPLATE_LOSSLESS = """[remap]

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

compress/mode=0
compress/high_quality=false
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


def extract_pack_name_from_package(unity_package_path: Path) -> str:
    """Extract clean pack name from Unity package filename.

    Synty package files follow the naming convention:
        POLYGON_PackName_Unity_YYYY_V_vX_Y_Z.unitypackage

    This function extracts just the pack name portion (e.g., "POLYGON_PackName")
    by removing the Unity version suffix.

    Args:
        unity_package_path: Path to the .unitypackage file.

    Returns:
        Clean pack name without version information.

    Examples:
        >>> extract_pack_name_from_package(Path("POLYGON_Samurai_Empire_Unity_2022_3_v1_0_1.unitypackage"))
        'POLYGON_Samurai_Empire'
        >>> extract_pack_name_from_package(Path("POLYGON_NatureBiomes_EnchantedForest_Unity_2022_3_v1_6_1.unitypackage"))
        'POLYGON_NatureBiomes_EnchantedForest'
        >>> extract_pack_name_from_package(Path("Nature.unitypackage"))
        'Nature'
    """
    # Get filename without extension
    filename = unity_package_path.stem

    # Pattern to match "_Unity_YYYY_V" suffix (e.g., "_Unity_2022_3").
    # The minor version is optional: Goblin War Camp ships as
    # "_Unity_2021_v1_0_2_Unity", and requiring it left "_Unity_2021" glued to
    # the pack name, which then matched no Unity import folder.
    unity_pattern = re.compile(r'^(.+?)_Unity_\d{4}(?:_\d+)?.*$', re.IGNORECASE)
    match = unity_pattern.match(filename)

    if match:
        return match.group(1)

    # Fallback: try to remove common version patterns like "_vX_Y_Z" or "_v1.0"
    version_pattern = re.compile(r'^(.+?)_v\d+[._]\d+.*$', re.IGNORECASE)
    match = version_pattern.match(filename)

    if match:
        return match.group(1)

    # No version pattern found, return filename as-is
    return filename


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
        prune_models: If True, delete the pack's models/ directory after a
            successful conversion. The FBX are staging input, not output.
        skip_godot_cli: If True, skip Godot CLI conversion phase. This generates
            materials only without producing .tscn scene files.
        retarget: If True, rewrite Polygon character and clip rigs onto
            SkeletonProfileHumanoid so animation clips can bind. Costs a second
            import pass.
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
        output_subfolder: Optional subfolder path to prepend to pack folder names.
            For example, "synty/" creates packs at output/synty/POLYGON_PackName/
            instead of output/POLYGON_PackName/.
        animations: Animation libraries to bind to converted characters.
            None binds nothing, 'all' binds every library in animations/,
            or a comma-separated list of case-insensitive substrings.
        pack_type: Package kind - 'auto' (default, detected from content),
            'assets' (materials, textures and meshes), or 'animations'
            (clip FBX converted to AnimationLibrary resources).
        flatten_output: If True (default), skip mirroring the Source_Files/FBX/
            subdirectory structure when creating mesh files. All meshes go directly
            into meshes/tscn_separate/ instead of preserving source paths. Set to
            False (via --retain-subfolders CLI flag) to preserve original structure.

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
    prune_models: bool = False
    skip_godot_import: bool = False
    retarget: bool = False
    godot_timeout: int = 600
    keep_meshes_together: bool = False
    mesh_format: str = "tscn"
    filter_pattern: str | None = None
    high_quality_textures: bool = False
    mesh_scale: float = 1.0
    output_subfolder: str | None = None
    flatten_output: bool = True
    pack_type: str = "auto"
    animations: str | None = None
    sidekick_database: Path | None = None


@dataclass
class GodotRunReport:
    """What godot_converter.gd reported about its own run.

    Everything the Godot script prints goes to a pipe that run_godot_cli()
    logs at debug level, so on a normal run none of it reaches the user. The
    script therefore ends with a machine-readable ``GODOT_SUMMARY <json>``
    line, and this holds what that line said.

    Attributes:
        seen: True if the GODOT_SUMMARY line was found. When False every count
            below is zero because nothing was parsed, not because nothing
            happened - so do not report them.
        meshes_saved: Meshes written by the Godot script.
        meshes_skipped: Meshes skipped (null mesh, no surfaces).
        characters_saved: Rigged character scenes written.
        animations_bound: Characters that got an animation library bound.
        errors: Errors counted by the Godot script.
        warnings: Warnings counted by the Godot script.
        messages: Up to MAX_GODOT_MESSAGES error and warning texts, reported by
            the Godot script itself rather than scraped from its console
            output. Scraping cannot work: the engine's own messages are worded
            exactly like the script's, so a text match quotes engine noise as
            though it were one of the counts above.
    """

    seen: bool = False
    meshes_saved: int = 0
    meshes_skipped: int = 0
    characters_saved: int = 0
    animations_bound: int = 0
    errors: int = 0
    warnings: int = 0
    messages: list[str] = field(default_factory=list)


# Cap on message examples accepted from the Godot script, mirroring its own
# MAX_REPORTED_MESSAGES. Enforced here too: the summary line is parsed input,
# not something to trust for length.
MAX_GODOT_MESSAGES = 25


def parse_godot_summary(line: str, report: GodotRunReport) -> bool:
    """Fill `report` from a GODOT_SUMMARY line.

    Args:
        line: A single line of Godot output.
        report: Report to populate in place.

    Returns:
        True if the line was a well-formed GODOT_SUMMARY line.
    """
    stripped = line.strip()
    if not stripped.startswith("GODOT_SUMMARY "):
        return False

    try:
        data = json.loads(stripped[len("GODOT_SUMMARY ") :])
    except (json.JSONDecodeError, ValueError):
        logger.debug("Malformed GODOT_SUMMARY line: %s", stripped)
        return False
    if not isinstance(data, dict):
        return False

    for name in (
        "meshes_saved",
        "meshes_skipped",
        "characters_saved",
        "animations_bound",
        "errors",
        "warnings",
    ):
        value = data.get(name, 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        setattr(report, name, int(value))

    messages = data.get("messages")
    if isinstance(messages, list):
        report.messages = [
            str(message) for message in messages[:MAX_GODOT_MESSAGES]
        ]

    report.seen = True
    return True


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
    godot_report: GodotRunReport = field(default_factory=lambda: GodotRunReport())


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
        "--prune-models",
        action="store_true",
        help=(
            "Delete the pack's models/ directory once meshes are generated. "
            "The FBX are input only - generated scenes embed their mesh data - "
            "so this reclaims the staging copy. Skipped if conversion failed."
        ),
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
    parser.add_argument(
        "--high-quality-textures",
        action="store_true",
        help="Use BPTC compression for textures (slower import, higher quality). "
             "Default is lossless compression for faster Godot import times.",
    )
    parser.add_argument(
        "--mesh-scale",
        type=float,
        default=1.0,
        help="Scale factor for mesh output (e.g., 100 for packs that are 100x too small)",
    )
    parser.add_argument(
        "--output-subfolder",
        type=str,
        default=None,
        help="Subfolder path to prepend to pack folder names. "
             "Example: --output-subfolder synty/ creates packs at output/synty/POLYGON_PackName/",
    )
    parser.add_argument(
        "--animations",
        default=None,
        help=(
            "Bind animation libraries to converted characters. "
            "'all', or a comma-separated list of substrings "
            "(e.g. 'sword_combat,base_locomotion')."
        ),
    )
    parser.add_argument(
        "--retarget",
        action="store_true",
        help="Retarget Polygon character and clip rigs onto SkeletonProfileHumanoid "
             "so animation clips bind. Adds a second import pass.",
    )
    parser.add_argument(
        "--pack-type",
        choices=["auto", "assets", "animations"],
        default="auto",
        help="Package kind. Default 'auto' detects from content.",
    )
    parser.add_argument(
        "--retain-subfolders",
        action="store_true",
        help="Retain Source_Files/FBX/ subdirectory structure in mesh output. "
             "By default, paths are flattened and all meshes go directly to meshes/tscn_separate/.",
    )

    args = parser.parse_args()

    # Validate mesh_scale
    if args.mesh_scale <= 0:
        parser.error(f"--mesh-scale must be positive, got: {args.mesh_scale}")

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
            # This is just informational now - textures come from .unitypackage primarily
            logger.debug(
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
        prune_models=args.prune_models,
        skip_godot_import=args.skip_godot_import,
        retarget=args.retarget,
        godot_timeout=args.godot_timeout,
        keep_meshes_together=args.keep_meshes_together,
        mesh_format=args.mesh_format,
        filter_pattern=args.filter,
        high_quality_textures=args.high_quality_textures,
        mesh_scale=args.mesh_scale,
        output_subfolder=args.output_subfolder,
        flatten_output=not args.retain_subfolders,
        pack_type=args.pack_type,
        animations=args.animations,
    )


def write_pack_metadata(pack_output_dir: Path) -> None:
    """Stamp a pack with the metadata schema it was converted against.

    Args:
        pack_output_dir: Pack output directory.
    """
    (pack_output_dir / PACK_METADATA_FILENAME).write_text(
        json.dumps({"schema_version": PACK_METADATA_VERSION}, indent=2),
        encoding="utf-8",
    )


def pack_metadata_is_current(pack_output_dir: Path) -> bool:
    """Check whether a pack's metadata was written by this schema or later.

    A pack converted before a metadata change carries an older stamp, or none
    at all, and must have its metadata regenerated - otherwise the skip-ahead
    path leaves it permanently missing whatever the converter learned to emit
    since. A newer stamp is left alone rather than downgraded.

    Args:
        pack_output_dir: Pack output directory.

    Returns:
        True when the pack's metadata is at least as new as this converter's.
    """
    metadata_path = pack_output_dir / PACK_METADATA_FILENAME
    if not metadata_path.exists():
        return False
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        return int(payload["schema_version"]) >= PACK_METADATA_VERSION
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, OSError) as e:
        logger.debug("Unreadable pack metadata at %s: %s", metadata_path, e)
        return False


def should_prune_models(stats: "ConversionStats") -> bool:
    """Decide whether a pack's staging FBX can be discarded.

    Only ever after mesh generation actually produced something: pruning a
    failed run would delete the very inputs needed to retry it. A non-zero exit
    from the Godot script is tolerated when meshes still came out, matching how
    the caller treats a partial conversion as a success.

    Args:
        stats: Conversion statistics for the finished pack.

    Returns:
        True when pruning is safe.
    """
    if stats.errors or stats.godot_timeout_occurred:
        return False
    if not stats.godot_import_success:
        return False
    return stats.meshes_converted > 0


def prune_pack_models(pack_output_dir: Path, dry_run: bool = False) -> int:
    """Delete a pack's staging FBX, keeping everything else in models/.

    The FBX are input: generated scenes embed their mesh data, so nothing
    points at one once conversion is done. On a shared source pool they are
    also the same bytes in every pack.

    The rest of models/ must stay. Godot's FBX importer extracts a mesh's
    embedded textures as PNGs beside it, and the generated scenes reference
    those by path - deleting the directory wholesale leaves 200+ scenes per
    pack unable to load. The FBX are the bulk of it regardless: 352 MB against
    15 MB of extracted textures on a Sidekick pack.

    Pruning is self-healing: the next run finds no FBX under models/, so it
    takes the full path and re-copies them rather than attempting a metadata
    refresh against an empty pool.

    Args:
        pack_output_dir: Pack output directory.
        dry_run: If True, only log what would be removed.

    Returns:
        Number of FBX removed.
    """
    models_dir = pack_output_dir / "models"
    if not models_dir.is_dir():
        return 0

    fbx_files = sorted(models_dir.rglob("*.fbx"))
    if not fbx_files:
        return 0

    if dry_run:
        logger.info("[DRY RUN] Would prune %d FBX from %s", len(fbx_files), models_dir)
        return 0

    removed = 0
    for fbx_path in fbx_files:
        try:
            fbx_path.unlink()
            # The .import sidecar describes a source that no longer exists.
            sidecar = fbx_path.with_suffix(fbx_path.suffix + ".import")
            if sidecar.exists():
                sidecar.unlink()
            removed += 1
        except OSError as e:
            logger.warning("Could not prune %s: %s", fbx_path, e)

    # Tidy directories the FBX left behind, deepest first so parents empty out.
    for directory in sorted(
        (p for p in models_dir.rglob("*") if p.is_dir()),
        key=lambda p: len(p.parts),
        reverse=True,
    ):
        try:
            directory.rmdir()
        except OSError:
            # Still holds extracted textures, which the scenes reference.
            pass

    logger.info("Pruned %d staging FBX from %s", removed, models_dir)
    return removed


def detect_existing_pack(pack_output_dir: Path) -> dict:
    """Check which phases can be skipped for an existing pack.

    Returns a dict indicating which prerequisites exist:
    - has_materials: True if materials/*.tres files exist
    - has_textures: True if textures/ has files
    - has_models: True if models/**/*.fbx files exist
    - has_mapping: True if mesh_material_mapping.json exists
    - has_current_metadata: True if the pack's metadata matches this schema
    """
    return {
        "has_current_metadata": pack_metadata_is_current(pack_output_dir),
        "has_materials": bool(list((pack_output_dir / "materials").glob("*.tres"))) if (pack_output_dir / "materials").exists() else False,
        "has_textures": bool(list((pack_output_dir / "textures").glob("*.*"))) if (pack_output_dir / "textures").exists() else False,
        "has_models": bool(list((pack_output_dir / "models").rglob("*.fbx"))) if (pack_output_dir / "models").exists() else False,
        "has_mapping": (pack_output_dir / "mesh_material_mapping.json").exists(),
    }


def setup_output_directories(output_dir: Path, dry_run: bool) -> None:
    """Create the output directory structure for pack assets.

    Creates:
        output_dir/
            textures/
            materials/
            models/
            meshes/

    Note: shaders/ is created at project root by copy_shaders(), not here.
    Note: meshes/ is created but not cleared on re-runs to preserve config subfolders.

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
            logger.debug("[DRY RUN] Would create directory: %s", directory)
        else:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug("Created directory: %s", directory)


def find_shader_in_project(shader_name: str, project_dir: Path) -> Path | None:
    """Search entire project for an existing shader file by name.

    This enables dynamic shader path discovery - if the user has moved shaders
    to a different location in their Godot project, we'll find and use that
    path instead of creating duplicates.

    Args:
        shader_name: Shader filename to search for (e.g., "polygon.gdshader").
        project_dir: Root directory of the Godot project to search.

    Returns:
        Path to the found shader file, or None if not found.
    """
    for shader_path in project_dir.rglob(shader_name):
        return shader_path
    return None


def get_shader_paths(
    project_dir: Path,
    shaders_src: Path,
    dry_run: bool = False
) -> tuple[dict[str, str], int]:
    """Build map of shader filename to res:// path. Copy missing shaders to shaders/.

    Searches the entire project for existing shader files. If found, uses their
    current location. If not found, copies from source to project's shaders/
    directory. This prevents duplicates when users relocate shaders.

    Args:
        project_dir: Root directory of the Godot project.
        shaders_src: Source directory containing shader files.
        dry_run: If True, only log what would be copied.

    Returns:
        Tuple of (shader_paths, copied_count) where:
        - shader_paths: Maps shader filename to res:// path
        - copied_count: Number of shaders copied (or would be copied in dry run)
    """
    shader_paths: dict[str, str] = {}
    shaders_dest = project_dir / "shaders"
    copied = 0

    for shader_file in SHADER_FILES:
        # First, search for existing shader anywhere in project
        found = find_shader_in_project(shader_file, project_dir)

        if found:
            # Use existing location
            rel_path = found.relative_to(project_dir)
            shader_paths[shader_file] = "res://" + str(rel_path).replace("\\", "/")
            logger.debug("Found existing shader: %s at %s", shader_file, shader_paths[shader_file])
        else:
            # Copy to shaders/ and use that path
            src = shaders_src / shader_file
            if src.exists():
                if not dry_run:
                    shaders_dest.mkdir(parents=True, exist_ok=True)
                    dest = shaders_dest / shader_file
                    shutil.copy2(src, dest)
                    logger.debug("Copied shader: %s", shader_file)
                else:
                    logger.debug("[DRY RUN] Would copy shader: %s", shader_file)
                copied += 1
            else:
                logger.warning("Shader file not found in source: %s", src)

            shader_paths[shader_file] = f"res://shaders/{shader_file}"

    logger.debug("Resolved shader paths: %d found, %d copied", len(shader_paths) - copied, copied)
    return shader_paths, copied


def copy_shaders(shaders_dest: Path, dry_run: bool) -> int:
    """Copy .gdshader files from project's shaders/ to destination.

    Note: This function is kept for backwards compatibility. New code should
    use get_shader_paths() which provides dynamic path discovery.

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
            logger.debug("[DRY RUN] Would copy shader: %s -> %s", source_path, dest_path)
        else:
            shutil.copy2(source_path, dest_path)
            logger.debug("Copied shader: %s", shader_file)

        copied += 1

    if skipped > 0:
        logger.debug("Copied %d shader files (%d already existed)", copied, skipped)
    else:
        logger.debug("Copied %d shader files", copied)
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


def generate_texture_import_file(texture_path: Path, high_quality: bool = False) -> None:
    """Generate a .import sidecar file for a texture with compression settings.

    Creates a Godot .import file that configures the texture compression mode.
    When high_quality is True, uses BPTC compression (mode=2) for better visual
    quality at the cost of slower import times. When False (default), uses
    lossless compression (mode=0) for faster Godot import times.

    The .import file is placed next to the texture file with the same name
    plus ".import" extension (e.g., "MyTexture.png.import").

    Args:
        texture_path: Absolute path to the texture file that was copied.
        high_quality: If True, use BPTC compression (slower, higher quality).
                     If False (default), use lossless compression (faster imports).

    Example:
        >>> generate_texture_import_file(Path("output/textures/Ground_01.png"))
        # Creates: output/textures/Ground_01.png.import (lossless)
        >>> generate_texture_import_file(Path("output/textures/Ground_01.png"), high_quality=True)
        # Creates: output/textures/Ground_01.png.import (BPTC compressed)
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

    # Select template based on quality setting
    template = TEXTURE_IMPORT_TEMPLATE_HIGH_QUALITY if high_quality else TEXTURE_IMPORT_TEMPLATE_LOSSLESS

    # Format the template
    import_content = template.format(
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
    high_quality_textures: bool = False,
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
        high_quality_textures: If True, use BPTC compression for texture import
            files (slower import, higher quality). If False (default), use
            lossless compression for faster Godot import times.

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
                logger.debug("[DRY RUN] Would copy texture from temp: %s", texture_name)
            else:
                shutil.copy2(temp_path, dest_path)
                generate_texture_import_file(dest_path, high_quality_textures)
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
                    logger.debug(
                        "[DRY RUN] Would copy fallback texture: %s -> %s (for missing %s)",
                        fallback_texture.name, dest_name, texture_name
                    )
                else:
                    shutil.copy2(fallback_texture, dest_path)
                    generate_texture_import_file(dest_path, high_quality_textures)
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
            logger.debug("[DRY RUN] Would copy texture: %s -> %s", source_path.name, dest_name)
        else:
            shutil.copy2(source_path, dest_path)
            generate_texture_import_file(dest_path, high_quality_textures)
            if source_path.name != dest_name:
                logger.debug("Copied texture: %s -> %s (renamed)", source_path.name, dest_name)
            else:
                logger.debug("Copied texture: %s", source_path.name)

        copied += 1
        from_source += 1

    # Log summary with source breakdown
    if from_temp > 0 or from_source > 0:
        logger.debug(
            "Copied %d textures (%d from package, %d from SourceFiles), %d fallback, %d missing",
            copied, from_temp, from_source, fallback_count, missing
        )
    elif fallback_count > 0:
        logger.debug(
            "Copied %d textures, %d using fallback atlas, %d missing",
            copied, fallback_count, missing
        )
    else:
        logger.debug("Copied %d textures, %d missing", copied, missing)

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
        # Note: On Windows, rglob is case-insensitive so *.fbx already matches *.FBX
        dir_files = list(fbx_dir.rglob("*.fbx"))
        for f in dir_files:
            fbx_files.append((f, fbx_dir))

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
        logger.debug(
            "Filter '%s' matched %d of %d FBX files",
            filter_pattern, len(fbx_files), original_count
        )

    if not fbx_files:
        dirs_str = ", ".join(str(d) for d in all_fbx_dirs)
        logger.warning("No FBX files found after filtering in: %s", dirs_str)
        return 0, 0

    logger.debug("Found %d FBX files to copy", len(fbx_files))

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
            logger.debug("[DRY RUN] Would copy FBX: %s", relative_path)
            copied += 1
        else:
            # Ensure parent directory exists
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, dest_path)
            logger.debug("Copied FBX: %s", relative_path)
            copied += 1

    logger.debug("Copied %d FBX files, skipped %d existing", copied, skipped)
    return copied, skipped


def generate_converter_config(
    project_dir: Path,
    pack_name: str,
    keep_meshes_together: bool,
    mesh_format: str,
    filter_pattern: str | None,
    mesh_scale: float,
    output_subfolder: str | None,
    flatten_output: bool,
    dry_run: bool,
    mode: str = "assets",
    animation_libraries: list[str] | None = None,
    rig_report: bool = False,
) -> None:
    """Generate converter_config.json for Godot's godot_converter.gd script.

    This JSON file passes configuration options from the Python CLI to the
    GDScript converter. The config is placed in the project root where
    godot_converter.gd will read it.

    Args:
        project_dir: Path to the Godot project directory.
        pack_name: Name of the pack folder to process (e.g., "POLYGON_Nature").
            When set, godot_converter.gd will only process this pack instead
            of discovering all pack folders.
        keep_meshes_together: If True, keep all meshes from one FBX together
            in a single scene file.
        mesh_format: Output format - 'tscn' (text) or 'res' (binary).
        filter_pattern: Optional filter pattern for FBX filenames.
        mesh_scale: Scale factor for mesh vertices.
        output_subfolder: Optional subfolder path prepended to pack folder names.
        flatten_output: If True, skip mirroring source directory structure.
        dry_run: If True, only log what would be written.
        mode: 'assets' to convert meshes, 'animations' to build
            AnimationLibrary resources from clip FBX.
        animation_libraries: res:// paths of AnimationLibrary resources to bind
            to character scenes.
    """
    config = {
        "pack_name": pack_name,
        "keep_meshes_together": keep_meshes_together,
        "mesh_format": mesh_format,
        "filter_pattern": filter_pattern,
        "mesh_scale": mesh_scale,
        "output_subfolder": output_subfolder,
        "flatten_output": flatten_output,
        "mode": mode,
        "animation_libraries": animation_libraries or [],
        "rig_report": rig_report,
    }

    config_path = project_dir / "converter_config.json"

    if dry_run:
        logger.debug("[DRY RUN] Would write converter_config.json: %s", config)
    else:
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        logger.debug("Wrote converter_config.json: %s", config)


def _run_godot_quietly(
    godot_exe: Path, project_dir: Path, timeout_seconds: int, *args: str
) -> bool:
    """Runs Godot and reports only whether it succeeded.

    The main import and convert phases stream their output because they are long
    and their progress is worth watching. The retargeting passes are neither, and
    a second copy of the streaming reader would be the more fragile thing here.
    """
    command = [str(godot_exe), "--headless", *args, "--path", str(project_dir)]
    logger.debug("Running: %s", " ".join(command))
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout_seconds,
            cwd=str(project_dir), check=False,
        )
    except subprocess.TimeoutExpired:
        logger.error("Godot timed out after %ds: %s", timeout_seconds, " ".join(args))
        return False
    except Exception as error:  # noqa: BLE001 - reported, never fatal
        logger.error("Failed to run Godot: %s", error)
        return False
    for line in (result.stdout or "").splitlines():
        logger.debug(line)
    if result.returncode != 0:
        logger.error("Godot exited %d: %s", result.returncode, " ".join(args))
        return False
    return True


def apply_retargeting(project_dir: Path) -> int:
    """Writes bone maps and injects them into .import files, between import passes.

    Reads the rig report the Godot side wrote, resolves the Polygon bone-map
    template against each skeleton's real bone names, and points that file's
    .import at the result.

    Returns:
        Number of FBX prepared. Zero means nothing was retargeted, and the caller
        should skip the second import rather than pay for a no-op.
    """
    report_path = project_dir / "rig_report.json"
    if not report_path.exists():
        logger.warning("Retargeting skipped: no rig report at %s", report_path)
        return 0

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("Retargeting skipped: cannot read rig report: %s", error)
        return 0

    prepared = 0
    for res_path, entry in report.items():
        bones = {name: tuple(origin) for name, origin in entry.get("bones", {}).items()}
        resolved, unresolved = resolve_bone_map(bones)
        if unresolved:
            # Not every skinned thing is a humanoid - capes and tails come
            # through here too. Report and leave it to the unretargeted path.
            logger.debug(
                "No bone map for %s: %d profile bones unresolved (%s)",
                res_path, len(unresolved), ", ".join(unresolved[:6]))
            continue

        fbx_path = project_dir / res_path.removeprefix("res://")
        if not fbx_path.exists():
            logger.warning("Rig report names a missing file: %s", fbx_path)
            continue

        bone_map_path = fbx_path.with_suffix(".bonemap.tres")
        bone_map_path.write_text(render_bone_map(resolved), encoding="utf-8")
        bone_map_res = "res://" + bone_map_path.relative_to(
            project_dir).as_posix()

        import_path = fbx_path.with_suffix(fbx_path.suffix + ".import")
        if not import_path.exists():
            logger.warning("No .import for %s; was it imported?", fbx_path.name)
            continue
        try:
            if inject_subresources(import_path, bone_map_res):
                prepared += 1
            else:
                logger.warning(
                    "%s already carries retarget options; left alone",
                    import_path.name)
        except (ValueError, OSError) as error:
            logger.warning("Retargeting skipped for %s: %s", import_path.name, error)

    # Consume it: a report left behind describes the previous pack.
    try:
        report_path.unlink()
    except OSError as error:
        logger.debug("Could not remove %s: %s", report_path, error)

    logger.info("Retargeting: prepared %d of %d skeletons", prepared, len(report))
    return prepared


def run_godot_cli(
    godot_exe: Path,
    project_dir: Path,
    timeout_seconds: int,
    dry_run: bool,
    skip_import: bool = False,
    keep_meshes_together: bool = False,
    mesh_format: str = "tscn",
    filter_pattern: str | None = None,
    mesh_scale: float = 1.0,
    pack_name: str = "",
    output_subfolder: str | None = None,
    flatten_output: bool = True,
    mode: str = "assets",
    animation_libraries: list[str] | None = None,
    retarget: bool = False,
) -> tuple[bool, bool, bool, GodotRunReport]:
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
        pack_name: Name of the pack folder to process. When set, godot_converter.gd
            will only process this specific pack instead of discovering all packs.

    Returns:
        Tuple of (import_success, convert_success, timeout_occurred) where:
        - import_success: True if Phase 1 completed with exit code 0, or True
          if Phase 1 was skipped via skip_import
        - convert_success: True if Phase 2 completed with exit code 0
        - timeout_occurred: True if either phase exceeded the timeout
        - report: GodotRunReport of what godot_converter.gd said about its own
          run. Its `seen` flag is False when the run never reached the
          converter script.

    Raises:
        No exceptions are raised; errors are logged and reflected in return values.

    Example:
        >>> import_ok, convert_ok, timed_out, report = run_godot_cli(
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
        return False, False, False, GodotRunReport()

    project_godot = project_dir / "project.godot"
    if not project_godot.exists():
        logger.error("project.godot not found in: %s", project_dir)
        return False, False, False, GodotRunReport()

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
        pack_name,
        keep_meshes_together,
        mesh_format,
        filter_pattern,
        mesh_scale,
        output_subfolder,
        flatten_output,
        dry_run,
        mode=mode,
        animation_libraries=animation_libraries,
    )

    import_success = False
    convert_success = False
    timeout_occurred = False
    report = GodotRunReport()

    # Phase 1: Import (can be skipped for large projects that timeout)
    if skip_import:
        logger.debug("Skipping Godot import phase (--skip-godot-import)")
        logger.debug("Note: You must open the project in Godot manually to trigger asset import")
        import_success = True  # Treat as success so converter phase runs
    else:
        import_cmd = [
            str(godot_exe),
            "--headless",
            "--import",
            "--path", str(project_dir),
        ]

        if dry_run:
            logger.debug("[DRY RUN] Would run: %s", " ".join(import_cmd))
            import_success = True
        else:
            logger.debug("Running Godot import (timeout: %ds)...", timeout_seconds)
            logger.debug("Command: %s", " ".join(import_cmd))

            try:
                start_time = time.time()
                # Use Popen for real-time output streaming
                process = subprocess.Popen(
                    import_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,  # Merge stderr into stdout
                    text=True,
                    cwd=str(project_dir),
                    bufsize=1,  # Line buffered
                )

                # Read output in real-time
                try:
                    import_count = 0
                    for line in process.stdout:
                        line = line.rstrip()
                        if line:
                            # Godot import outputs lines like "Importing: res://..." or "file.fbx"
                            if "Importing" in line or line.endswith(".fbx"):
                                import_count += 1
                                # Log every file (GUI handles single-line updating)
                                logger.info("Importing [%d]...", import_count)
                            else:
                                logger.debug(line)

                    # Log completion message
                    if import_count > 0:
                        logger.info("Import complete (%d files)", import_count)

                    process.wait(timeout=timeout_seconds)
                    elapsed = time.time() - start_time

                    if process.returncode == 0:
                        logger.debug("Godot import completed in %.1fs", elapsed)
                        import_success = True
                    else:
                        logger.error("Godot import failed (exit code %d)", process.returncode)
                except subprocess.TimeoutExpired:
                    process.kill()
                    logger.error("Godot import timed out after %ds", timeout_seconds)
                    timeout_occurred = True
                    return import_success, convert_success, timeout_occurred, report
                finally:
                    if process.stdout:
                        process.stdout.close()

            except Exception as e:
                logger.error("Failed to run Godot import: %s", e)
                return import_success, convert_success, timeout_occurred, report

        if not import_success and not dry_run:
            return import_success, convert_success, timeout_occurred, report

    # Phase 1.5: Retarget. Both a character rig and the clip rigs have to be
    # rewritten onto a common profile before anything can bind, and a bone map
    # cannot be written until the file's real bone names are known - so this sits
    # between two imports rather than before one.
    if retarget and import_success and not dry_run:
        logger.info("Retargeting: reporting rigs...")
        generate_converter_config(
            project_dir, pack_name, keep_meshes_together, mesh_format,
            filter_pattern, mesh_scale, output_subfolder, flatten_output,
            dry_run, mode=mode, animation_libraries=animation_libraries,
            rig_report=True,
        )
        if _run_godot_quietly(godot_exe, project_dir, timeout_seconds,
                              "--script", "res://godot_converter.gd"):
            prepared = apply_retargeting(project_dir)
            if prepared:
                logger.info("Retargeting: re-importing %d retargeted FBX...", prepared)
                if not _run_godot_quietly(godot_exe, project_dir, timeout_seconds,
                                          "--import"):
                    # Pass 1's output is still on disk and still valid; the pack
                    # converts unretargeted rather than half-retargeted.
                    logger.warning("Re-import failed; converting without retargeting")
        else:
            logger.warning("Rig report failed; converting without retargeting")

        # Put the config back before the conversion phase reads it.
        generate_converter_config(
            project_dir, pack_name, keep_meshes_together, mesh_format,
            filter_pattern, mesh_scale, output_subfolder, flatten_output,
            dry_run, mode=mode, animation_libraries=animation_libraries,
        )

    # Phase 2: Convert
    convert_cmd = [
        str(godot_exe),
        "--headless",
        "--script", "res://godot_converter.gd",
        "--path", str(project_dir),
    ]

    if dry_run:
        logger.debug("[DRY RUN] Would run: %s", " ".join(convert_cmd))
        convert_success = True
    else:
        logger.debug("Running Godot converter script (timeout: %ds)...", timeout_seconds)
        logger.debug("Command: %s", " ".join(convert_cmd))

        try:
            # Use Popen for real-time output streaming
            process = subprocess.Popen(
                convert_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Merge stderr into stdout
                text=True,
                cwd=str(project_dir),
                bufsize=1,  # Line buffered
            )

            # Read output in real-time
            try:
                last_total = None
                for line in process.stdout:
                    line = line.rstrip()
                    if line:
                        if parse_godot_summary(line, report):
                            logger.debug(line)
                            continue
                        if "[" in line and "Processing:" in line:
                            # Extract [X/Y] from the processing line for compact display
                            # Pattern: "[1/830] Processing: Character_Ghost_01.fbx"
                            match = re.match(r'\[(\d+)/(\d+)\]', line)
                            if match:
                                current = int(match.group(1))
                                total = int(match.group(2))
                                last_total = total
                                # Log every file (GUI handles single-line updating)
                                logger.info("Processing [%d/%d]...", current, total)
                            else:
                                # Fallback: log the line if pattern doesn't match
                                logger.info(line)
                        else:
                            logger.debug(line)

                # Log completion message
                if last_total is not None:
                    logger.info("Processing complete (%d meshes)", last_total)

                process.wait(timeout=timeout_seconds)
                if process.returncode == 0:
                    convert_success = True
                else:
                    logger.error("Godot converter failed (exit code %d)", process.returncode)
            except subprocess.TimeoutExpired:
                process.kill()
                logger.error("Godot converter timed out after %ds", timeout_seconds)
                timeout_occurred = True
            finally:
                if process.stdout:
                    process.stdout.close()

        except Exception as e:
            logger.error("Failed to run Godot converter: %s", e)

    return import_success, convert_success, timeout_occurred, report


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
        logger.debug("All shader uniforms already present in existing project.godot")
        return existing_content

    logger.debug("Adding %d new shader uniform(s): %s", len(new_uniforms), ", ".join(new_uniforms.keys()))

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
            logger.debug("[DRY RUN] Would merge shader uniforms into: %s", project_path)
        else:
            logger.debug("[DRY RUN] Would write project.godot to: %s", project_path)
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
        logger.debug("Updated project.godot with merged shader uniforms")
    else:
        # Create new project.godot with pack name
        project_content = PROJECT_GODOT_TEMPLATE.replace(
            'config/name="Synty Converted Assets"',
            f'config/name="{pack_name}"'
        )
        project_path.write_text(project_content, encoding="utf-8")
        logger.debug("Wrote project.godot with project name '%s'", pack_name)


def write_conversion_log(project_dir: Path, pack_name: str, stats: ConversionStats, config: ConversionConfig) -> None:
    """Write a summary log file with all warnings and errors.

    Appends to existing log file so multiple pack conversions accumulate.

    Args:
        project_dir: Project root directory (next to project.godot).
        pack_name: Name of the pack being converted.
        stats: Conversion statistics.
        config: Conversion configuration.
    """
    log_path = project_dir / "conversion_log.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "",
        "=" * 80,
        f"Conversion: {pack_name}",
        f"Date: {timestamp}",
        "=" * 80,
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

    # The Godot script's own tally, which is independent of the Python one
    # above: the pipeline can succeed while the converter script fails on
    # individual meshes or characters.
    report = stats.godot_report
    if report.seen:
        lines.extend(
            [
                "Godot Converter Script:",
                f"  Meshes Saved: {report.meshes_saved}",
                f"  Meshes Skipped: {report.meshes_skipped}",
                f"  Characters Rigged: {report.characters_saved}",
                f"  Animations Bound: {report.animations_bound}",
                f"  Warnings: {report.warnings}",
                f"  Errors: {report.errors}",
                "",
            ]
        )
        if report.messages:
            lines.append("Godot Messages:")
            lines.extend(f"  - {message}" for message in report.messages)
            lines.append("")

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

    lines.append("=" * 80)
    lines.append("")

    # Append to existing log file (accumulates across multiple pack conversions)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.debug("Appended conversion log to: %s", log_path)


def print_summary(stats: ConversionStats) -> None:
    """Print conversion summary to console.

    Args:
        stats: Conversion statistics.
    """
    print("=" * 40)
    print("Conversion Complete!")
    print(f"  Materials: {stats.materials_generated} generated")
    print(f"  Textures: {stats.textures_copied} copied")
    print(f"  Meshes: {stats.meshes_converted} converted")
    print("=" * 40)

    # Show additional details if there are issues
    if stats.materials_missing > 0:
        print(f"  Materials Missing: {stats.materials_missing}")
    if stats.textures_missing > 0:
        print(f"  Textures Missing: {stats.textures_missing}")

    # Godot CLI status (only show if there was a problem)
    if stats.godot_timeout_occurred:
        print("  Godot CLI: TIMEOUT")
    elif not stats.godot_import_success and not stats.godot_convert_success:
        pass  # Skipped - don't show
    elif not stats.godot_import_success:
        print("  Godot CLI: Import Failed")
    elif not stats.godot_convert_success and stats.meshes_converted == 0:
        print("  Godot CLI: Conversion Failed")

    # What the Godot script reported about itself. Its errors are counted
    # separately from the Python pipeline's: a run can finish with Python
    # reporting nothing wrong while Godot failed on dozens of meshes.
    report = stats.godot_report
    if report.seen:
        if report.characters_saved:
            print(f"  Characters: {report.characters_saved} rigged")
        if report.animations_bound:
            print(f"  Animations bound: {report.animations_bound}")
        if report.meshes_skipped:
            print(f"  Meshes Skipped (Godot): {report.meshes_skipped}")
        if report.warnings:
            print(f"  Godot Warnings: {report.warnings}")
        if report.errors:
            print(f"  Godot Errors: {report.errors}")

    if stats.warnings:
        print(f"  Warnings: {len(stats.warnings)}")

    if stats.errors:
        print(f"  Errors: {len(stats.errors)}")
        for error in stats.errors[:5]:
            print(f"    - {error}")
        if len(stats.errors) > 5:
            print(f"    ... and {len(stats.errors) - 5} more")

    if report.messages and (report.errors or report.warnings):
        print("  From Godot:")
        for message in report.messages[:5]:
            print(f"    - {message}")
        remaining = (report.errors + report.warnings) - 5
        if remaining > 0:
            print(f"    ... and {remaining} more (run with --verbose for all)")

    print()  # Empty line at end


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


def get_filtered_material_names(
    prefabs: list[PrefabMaterials],
    filter_pattern: str,
    source_files: Path,
) -> set[str]:
    """Returns set of material names used by FBX files matching the filter pattern.

    When a filter pattern is specified (e.g., --filter Tree), this function
    identifies which materials are actually used by the matching FBX files,
    allowing the texture copying step to skip textures for unused materials.

    Args:
        prefabs: List of PrefabMaterials from parse_material_list().
        filter_pattern: Case-insensitive pattern to match against FBX filenames.
        source_files: Path to source files directory for FBX discovery.

    Returns:
        Set of material names used by FBX files matching the filter pattern.
    """
    pattern_lower = filter_pattern.lower()
    filtered_materials: set[str] = set()

    for prefab in prefabs:
        # Check if prefab name matches filter
        if pattern_lower in prefab.prefab_name.lower():
            for mesh in prefab.meshes:
                for slot in mesh.slots:
                    if slot.material_name:
                        filtered_materials.add(slot.material_name)

    logger.debug(
        "Filter '%s' matched %d materials from prefabs",
        filter_pattern, len(filtered_materials)
    )
    return filtered_materials


def filter_textures_for_materials(
    textures: set[str],
    material_names: set[str],
    mapped_materials: list[MappedMaterial],
) -> set[str]:
    """Returns only textures that are used by the given materials.

    Cross-references the required textures with materials that are actually
    being used (based on filter), returning only the textures needed.

    Args:
        textures: Full set of required texture names.
        material_names: Set of material names to filter by.
        mapped_materials: List of all mapped materials with texture references.

    Returns:
        Filtered set of texture names used by the specified materials.
    """
    filtered_textures: set[str] = set()

    for mapped_mat in mapped_materials:
        if mapped_mat.name in material_names:
            for texture_name in mapped_mat.textures.values():
                if texture_name in textures:
                    filtered_textures.add(texture_name)

    return filtered_textures


# Fraction of FBX under an Animations/ directory above which a package is
# treated as an animation pack. Measured: ANIMATION_Sword_Combat 242/244 = 0.99,
# POLYGON_Dungeon 0/801 = 0.00, so the separation needs no tuning.
ANIMATION_PACK_FBX_RATIO = 0.5


def detect_pack_type(guid_map) -> str:
    """Classify a package as an asset pack or an animation pack.

    Args:
        guid_map: unity_package.GuidMap with guid_to_pathname populated.

    Returns:
        "animations" or "assets".
    """
    fbx_paths = [
        p for p in guid_map.guid_to_pathname.values() if p.lower().endswith(".fbx")
    ]
    if not fbx_paths:
        return "assets"

    in_animations = sum(1 for p in fbx_paths if "/animations/" in p.lower())
    ratio = in_animations / len(fbx_paths)
    logger.debug(
        "Pack type: %d/%d FBX under Animations/ (ratio %.2f)",
        in_animations,
        len(fbx_paths),
        ratio,
    )
    return "animations" if ratio > ANIMATION_PACK_FBX_RATIO else "assets"


def resolve_animation_libraries(project_dir: Path, selector: str | None) -> list[str]:
    """Resolve --animations selectors to res:// library paths.

    Args:
        project_dir: Godot project root; libraries live in animations/.
        selector: None (bind nothing), "all", or a comma-separated list of
            case-insensitive substrings matched against library filenames.

    Returns:
        Sorted res:// paths. Empty when nothing matches; the caller warns.
    """
    if not selector:
        return []

    animations_dir = project_dir / "animations"
    if not animations_dir.is_dir():
        return []

    libraries = sorted(p.name for p in animations_dir.glob("*.res"))
    if selector.strip().lower() == "all":
        matched = libraries
    else:
        needles = [s.strip().lower() for s in selector.split(",") if s.strip()]
        matched = [
            name for name in libraries if any(n in name.lower() for n in needles)
        ]

    return [f"res://animations/{name}" for name in matched]


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

    # Extract pack name from Unity package filename (not source_files directory)
    # e.g., POLYGON_Samurai_Empire_Unity_2022_3_v1_0_1.unitypackage -> "POLYGON_Samurai_Empire"
    raw_pack_name = extract_pack_name_from_package(config.unity_package)
    # Sanitize to remove invalid filesystem characters
    pack_name = sanitize_filename(raw_pack_name)
    if pack_name != raw_pack_name:
        logger.warning("Pack name sanitized: '%s' -> '%s'", raw_pack_name, pack_name)

    # Consistent output structure:
    # - project.godot at output_dir root (create new or merge uniforms)
    # - shaders/ at output_dir root (shared across all packs)
    # - [output_subfolder/]PackName/ subfolder for pack-specific assets
    if config.output_subfolder:
        # Normalize subfolder path (ensure forward slashes and no leading slash)
        subfolder = config.output_subfolder.replace("\\", "/").strip("/")
        pack_output_dir = config.output_dir / subfolder / pack_name
    else:
        pack_output_dir = config.output_dir / pack_name
    shaders_dir = config.output_dir / "shaders"
    project_dir = config.output_dir

    # Print header
    print("\n" + "=" * 40)
    print(f"Starting conversion: {config.unity_package.name}")
    print("=" * 40)

    # Step 1: Validate inputs (already done in parse_args, but double-check)
    logger.info("Step 1: Validating inputs...")
    logger.debug("  Pack Name: %s", pack_name)
    logger.debug("  Unity Package: %s", config.unity_package)
    logger.debug("  Source Files: %s", config.source_files)
    logger.debug("  Pack Output: %s", pack_output_dir)
    logger.debug("  Shaders Dir: %s", shaders_dir)
    logger.debug("  Project Dir: %s", project_dir)

    # Step 2: Create output directory structure
    logger.info("Step 2: Creating directories...")
    setup_output_directories(pack_output_dir, config.dry_run)

    # Check for existing pack to enable incremental conversion
    existing_pack = detect_existing_pack(pack_output_dir)
    skip_to_godot = all(existing_pack.values())

    # Assets are all present but the metadata predates this converter, so the
    # pack must not skip ahead: it would keep whatever fields the older version
    # emitted forever. Everything re-runs except the FBX copy, which is the one
    # genuinely expensive step and cannot have gone stale - the files are there.
    refresh_metadata = (
        not skip_to_godot
        and not existing_pack["has_current_metadata"]
        and all(
            value
            for key, value in existing_pack.items()
            if key != "has_current_metadata"
        )
    )

    if skip_to_godot:
        logger.info("Existing pack detected with all prerequisites - skipping to mesh generation")
        logger.info("  Materials: %s, Textures: %s, Models: %s, Mapping: %s",
                    existing_pack["has_materials"], existing_pack["has_textures"],
                    existing_pack["has_models"], existing_pack["has_mapping"])
    elif refresh_metadata:
        logger.info("Existing pack has outdated metadata - regenerating it (FBX copy skipped)")

    # Store temp dir path for cleanup (always runs via finally, even on error)
    temp_dir_to_cleanup = None

    # Resolved once the package is extracted; assets is the safe default for the
    # existing-pack path, which never inspects the package at all.
    pack_mode = "assets" if config.pack_type == "auto" else config.pack_type

    # Steps 3-10: Skip if existing pack detected with all prerequisites
    if not skip_to_godot:
        # Step 3: Extract Unity package
        logger.info("Step 3: Extracting Unity package (%s)...", pack_name)
        try:
            guid_map: GuidMap = extract_unitypackage(config.unity_package)
            logger.debug("Extracted %d assets from Unity package", len(guid_map.guid_to_pathname))
        except Exception as e:
            error_msg = f"Failed to extract Unity package: {e}"
            logger.error(error_msg)
            stats.errors.append(error_msg)
            return stats

        if guid_map.texture_guid_to_path:
            temp_dir_to_cleanup = next(iter(guid_map.texture_guid_to_path.values())).parent

        pack_mode = config.pack_type
        if pack_mode == "auto":
            pack_mode = detect_pack_type(guid_map)
        logger.info("Pack type: %s", pack_mode)

    try:
        # Steps 4-10: Parse and generate assets
        # (skipped entirely if existing pack detected with all prerequisites)
        if skip_to_godot:
            logger.info("Steps 3-10: Skipped (existing pack detected)")
        else:
            # Steps 4-8 build materials, shaders and textures. An animation
            # pack has none of those - only clip FBX - so they are skipped.
            if pack_mode == "assets":
                # Step 4: Parse all .mat files
                material_guids = get_material_guids(guid_map)
                logger.info("Step 4: Parsing %d materials...", len(material_guids))
                unity_materials: list[tuple[str, UnityMaterial]] = []

                for guid in material_guids:
                    content = guid_map.guid_to_content.get(guid)
                    if content is None:
                        warning_msg = f"No content for material GUID: {guid}"
                        logger.debug(warning_msg)
                        stats.warnings.append(warning_msg)
                        continue

                    try:
                        material = parse_material_bytes(content)
                        unity_materials.append((guid, material))
                        stats.materials_parsed += 1
                    except Exception as e:
                        warning_msg = f"Failed to parse material GUID {guid}: {e}"
                        logger.debug(warning_msg)
                        stats.warnings.append(warning_msg)

                logger.debug("Parsed %d Unity materials", stats.materials_parsed)

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
                        logger.debug("Parsing %s for shader detection...", material_list_path.name)
                        try:
                            file_prefabs = parse_material_list(material_list_path)
                            prefabs.extend(file_prefabs)
                            logger.debug("  Found %d prefabs in %s", len(file_prefabs), material_list_path.name)
                        except Exception as e:
                            logger.debug("Failed to parse %s: %s", material_list_path.name, e)

                    logger.debug("Total prefabs from all MaterialList files: %d", len(prefabs))

                # Fall back to the package's prefabs when MaterialList*.txt is
                # absent or yielded nothing. Synty ships MaterialList*.txt only in
                # the separate SourceFiles download, never in the .unitypackage,
                # but prefabs carry the same mesh-to-material data (prefab_parser).
                if not prefabs:
                    logger.info("No MaterialList data - deriving mappings from package prefabs")
                    prefabs = build_prefabs_from_package(guid_map)
                    logger.info("Derived mappings for %d prefab(s) from package", len(prefabs))
                    if not prefabs:
                        warning_msg = (
                            "No MaterialList*.txt and no usable prefabs in package - "
                            "meshes will have no materials assigned"
                        )
                        logger.warning(warning_msg)
                        stats.warnings.append(warning_msg)

                # Determine filtered material names early (before .tres generation)
                filtered_material_names: set[str] | None = None
                if config.filter_pattern and prefabs:
                    filtered_material_names = get_filtered_material_names(
                        prefabs, config.filter_pattern, config.source_files
                    )
                    logger.info("Filter limits to %d materials", len(filtered_material_names))

                if prefabs:
                    # Step 5: Build shader cache with LOD inheritance
                    logger.info("Step 5: Mapping shader properties...")
                    shader_cache, unmatched_materials = build_shader_cache(prefabs)
                    logger.debug("Shader cache: %d materials cached", len(shader_cache))

                    # Log unmatched materials for user to add patterns
                    if unmatched_materials:
                        logger.debug("=" * 60)
                        logger.debug("UNMATCHED MATERIALS - Consider adding name patterns for:")
                        for mat_name in sorted(set(unmatched_materials)):
                            logger.debug("  - %s", mat_name)
                        logger.debug("=" * 60)
                else:
                    logger.info("Step 5: Mapping shader properties...")
                    logger.debug("MaterialList*.txt not found, using fallback shader detection")

                # Map material properties to Godot equivalents (continuation of Step 5)
                logger.debug("Mapping materials to Godot format...")
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
                        logger.debug(warning_msg)
                        stats.warnings.append(warning_msg)

                logger.debug("Mapped %d materials, requiring %d textures", len(mapped_materials), len(required_textures))

                # Step 6: Resolve shader paths (find existing or copy missing)
                # This must happen before .tres generation so we can use discovered paths
                logger.info("Step 6: Resolving shader paths...")
                script_dir = Path(__file__).parent
                shaders_src = script_dir / "shaders"
                shader_paths, stats.shaders_copied = get_shader_paths(
                    project_dir,
                    shaders_src,
                    config.dry_run,
                )

                # Step 7: Generate .tres files
                logger.info("Step 7: Generating .tres files...")
                materials_dir = pack_output_dir / "materials"

                # Pack-relative texture path (textures are in pack folder, not root)
                if config.output_subfolder:
                    subfolder = config.output_subfolder.replace("\\", "/").strip("/")
                    texture_base = f"res://{subfolder}/{pack_name}/textures"
                else:
                    texture_base = f"res://{pack_name}/textures"

                # Materials sit beside the textures, so the same base locates
                # both - and the .tres needs its own res:// path to derive a UID.
                material_base = texture_base.rsplit("/", 1)[0] + "/materials"

                for mapped_mat in mapped_materials:
                    # Skip materials not used by filtered FBX files
                    if filtered_material_names is not None and mapped_mat.name not in filtered_material_names:
                        continue

                    try:
                        # Sanitize filename
                        filename = sanitize_filename(mapped_mat.name) + ".tres"
                        output_path = materials_dir / filename

                        # Generate .tres content with discovered shader paths
                        tres_content = generate_tres(
                            mapped_mat,
                            shader_base="res://shaders",  # Fallback if shader not in shader_paths
                            texture_base=texture_base,
                            shader_paths=shader_paths,
                            res_path=f"{material_base}/{filename}"
                        )

                        if config.dry_run:
                            logger.debug("[DRY RUN] Would write material: %s", output_path)
                        else:
                            write_tres_file(tres_content, output_path)
                            logger.debug("Wrote material: %s", filename)

                        stats.materials_generated += 1

                    except Exception as e:
                        warning_msg = f"Failed to generate .tres for '{mapped_mat.name}': {e}"
                        logger.debug(warning_msg)
                        stats.warnings.append(warning_msg)

                logger.debug("Generated %d .tres material files", stats.materials_generated)

                # Step 8: Copy required textures
                # Textures primarily come from .unitypackage extraction (texture_guid_to_path)
                # SourceFiles/Textures is used as optional fallback for any missing textures

                # Apply smart texture filtering when filter pattern is specified
                # (filtered_material_names was computed earlier for .tres filtering)
                if filtered_material_names is not None:
                    original_texture_count = len(required_textures)
                    required_textures = filter_textures_for_materials(
                        required_textures, filtered_material_names, mapped_materials
                    )
                    logger.debug(
                        "Smart texture filter reduced textures from %d to %d",
                        original_texture_count, len(required_textures)
                    )

                logger.info("Step 8: Copying %d textures...", len(required_textures))
                # Find all Textures directories recursively for complex nested structures (optional fallback)
                texture_dirs = [config.source_files / "Textures"]
                if not texture_dirs[0].exists():
                    texture_dirs = [d for d in config.source_files.rglob("Textures") if d.is_dir()]
                    if texture_dirs:
                        logger.debug("Found %d Textures directories as fallback sources", len(texture_dirs))
                        for td in texture_dirs:
                            logger.debug("  Textures dir: %s", td)
                    else:
                        logger.debug("No SourceFiles/Textures found - using .unitypackage textures only")
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
                    high_quality_textures=config.high_quality_textures,
                )

            # Step 9: Copy FBX files
            # Simplified approach: find ALL .fbx files recursively, preserving relative path structure
            if not config.skip_fbx_copy and not refresh_metadata:
                # Find all FBX files recursively from source root
                # Note: On Windows, rglob is case-insensitive so *.fbx matches *.FBX
                fbx_files = list(config.source_files.rglob("*.fbx"))
                total_count = len(fbx_files)

                if config.filter_pattern:
                    # Apply filter to FBX filenames
                    pattern_lower = config.filter_pattern.lower()
                    fbx_files = [f for f in fbx_files if pattern_lower in f.stem.lower()]
                    logger.info(
                        "Step 9: Copying %d of %d FBX files (filter: %s)...",
                        len(fbx_files), total_count, config.filter_pattern
                    )
                else:
                    logger.info("Step 9: Copying %d FBX files...", len(fbx_files))

                models_dir = pack_output_dir / "models"

                # Common prefixes to strip from FBX paths (case-insensitive)
                common_prefixes = {"sourcefiles", "source_files", "source files", "fbx", "models", "bonusfbx"}

                for fbx_path in fbx_files:
                    # Get relative path from source and strip common prefixes
                    rel_path = fbx_path.relative_to(config.source_files)
                    path_parts = list(rel_path.parts)

                    # Strip leading parts that match common prefixes
                    while path_parts and path_parts[0].lower() in common_prefixes:
                        path_parts.pop(0)

                    # Reconstruct path from remaining parts (or use filename if all stripped)
                    if path_parts:
                        clean_rel_path = Path(*path_parts)
                    else:
                        clean_rel_path = Path(rel_path.name)

                    dest_path = models_dir / clean_rel_path

                    # Skip if destination already exists and is same size
                    if dest_path.exists():
                        if dest_path.stat().st_size == fbx_path.stat().st_size:
                            logger.debug("Skipping existing FBX: %s", clean_rel_path)
                            stats.fbx_skipped += 1
                            continue

                    if config.dry_run:
                        logger.debug("[DRY RUN] Would copy FBX: %s", clean_rel_path)
                    else:
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(fbx_path, dest_path)
                        logger.debug("Copied FBX: %s", clean_rel_path)

                    stats.fbx_copied += 1

                if stats.fbx_copied == 0 and stats.fbx_skipped == 0 and total_count == 0:
                    warning_msg = f"No FBX files found in {config.source_files}"
                    stats.warnings.append(warning_msg)
            else:
                logger.info("Step 9: Skipping FBX copy...")

            # Mesh-material mapping and character definitions are asset-pack
            # concepts; animation packs produce AnimationLibrary resources.
            if pack_mode == "assets":
                # Step 10: Generate mesh_material_mapping.json (uses prefabs parsed in Step 4.5)
                # Note: mapping goes to pack_output_dir so each pack has its own mapping
                logger.info("Step 10: Generating mesh material mapping...")
                if prefabs:
                    mapping_output = pack_output_dir / "mesh_material_mapping.json"
                    if config.dry_run:
                        logger.debug("[DRY RUN] Would write mesh_material_mapping.json")
                    else:
                        generate_mesh_material_mapping_json(prefabs, mapping_output)
                        logger.debug("Generated mesh_material_mapping.json to pack folder")

                        # A prefab variant names its mesh by the source FBX, so
                        # the other meshes in a multi-mesh FBX get no mapping of
                        # their own - a hand cart is painted while its wheels
                        # stay untextured. Godot knows which FBX each mesh came
                        # from and falls back to this table.
                        fbx_fallback = build_fbx_material_fallback(guid_map)
                        if fbx_fallback:
                            (pack_output_dir / "fbx_material_fallback.json").write_text(
                                json.dumps(fbx_fallback, indent=2, ensure_ascii=False),
                                encoding="utf-8",
                            )
                            logger.debug(
                                "Wrote FBX material fallback for %d FBX file(s)",
                                len(fbx_fallback),
                            )

                        # Character definitions drive rigged-character output in
                        # godot_converter.gd. Absent file simply means no characters.
                        char_defs = build_character_definitions(guid_map)
                        if char_defs:
                            write_character_definitions_json(
                                char_defs, pack_output_dir / "character_definitions.json"
                            )
                            logger.info("Wrote %d character definition(s)", len(char_defs))

                        # Sidekick packs ship characters as .sk recipes naming
                        # one part FBX per body slot. Resolution scans the
                        # pack's models/ directory, which Step 9 has already
                        # populated - package asset paths would not match,
                        # because copy_fbx_files() rewrites them.
                        sk_recipes = build_sidekick_recipes(
                            guid_map,
                            [config.source_files],
                            pack_output_dir / "models",
                        )
                        if sk_recipes:
                            write_sidekick_characters_json(
                                sk_recipes,
                                pack_output_dir / "sidekick_characters.json",
                            )
                            logger.info(
                                "Wrote %d Sidekick character recipe(s)",
                                len(sk_recipes),
                            )

                            # Proportions reshape the body mesh but leave the
                            # attachment joints where they were, so gear floats
                            # off a heavy character. Synty keeps the per-joint
                            # corrections in its tool database, which ships in
                            # the user's Unity project rather than the package -
                            # so this is available only via --source-files.
                            # A caller that already knows where the database
                            # is says so: it installs as SidekickCharacters/,
                            # which matches no pack name, so a per-pack search
                            # of source_files can never turn it up.
                            sk_database = config.sidekick_database or (
                                find_sidekick_database([config.source_files])
                            )
                            if sk_database:
                                sk_adjustments = load_rig_adjustments(sk_database)
                                if sk_adjustments:
                                    write_sidekick_rig_adjustments_json(
                                        sk_adjustments,
                                        pack_output_dir / "sidekick_rig_adjustments.json",
                                    )
                                    logger.info(
                                        "Wrote joint adjustments for %d bone(s)",
                                        len(sk_adjustments),
                                    )
                                    # Also to the output root, for the runtime
                                    # node: the data is database-derived and
                                    # global, like the gear sets and colour
                                    # tables. The per-pack copy stays, because
                                    # the baked character scenes read it there.
                                    write_sidekick_rig_adjustments_json(
                                        sk_adjustments,
                                        pack_output_dir.parent
                                        / "sidekick_rig_adjustments.json",
                                    )

                                # Gear sets and colour tables describe the whole
                                # shared part library, not this pack, so they go
                                # to the output root. Every Sidekick pack derives
                                # identical content from the same database, which
                                # makes rewriting them idempotent, not a conflict.
                                output_root = pack_output_dir.parent
                                sk_sets = load_part_presets(sk_database)
                                if sk_sets:
                                    write_sidekick_gear_sets_json(
                                        sk_sets, output_root / "sidekick_gear_sets.json"
                                    )
                                    logger.info("Wrote %d gear set(s)", len(sk_sets))

                                sk_colors = load_color_tables(sk_database)
                                if sk_colors["properties"]:
                                    write_sidekick_colors_json(
                                        sk_colors, output_root / "sidekick_colors.json"
                                    )
                                    logger.info(
                                        "Wrote %d colour propert(ies)",
                                        len(sk_colors["properties"]),
                                    )

                                # The master palette defines every colour slot,
                                # so any mix of parts renders against it without
                                # a red texel. Per-character palettes are
                                # recolours of it.
                                # The palette sits in the same tool folder as
                                # the database - Resources/Textures beside
                                # Database - and in no pack's folder, so a
                                # located database says where to look. Without
                                # this, a user with the tool gets its gear sets
                                # and colour tables but no palette to paint
                                # with, and recolouring stays disabled.
                                palette_dirs = [config.source_files]
                                if config.sidekick_database is not None:
                                    palette_dirs.insert(
                                        0, config.sidekick_database.parent.parent
                                    )
                                sk_master = find_master_color_map(palette_dirs)
                                if sk_master:
                                    parts_dir = output_root / SIDEKICK_PARTS_DIRNAME
                                    parts_dir.mkdir(parents=True, exist_ok=True)
                                    shutil.copy2(
                                        sk_master,
                                        parts_dir / "T_SidekickMaster_ColorMap.png",
                                    )
                                    logger.info("Copied master Sidekick palette")
                            else:
                                logger.debug(
                                    "No Sidekick tool database under --source-files; "
                                    "attachment joints will not follow body size"
                                )
                                # No database means no curated sets, but the part
                                # names alone still group into usable ones.
                                #
                                # Guarded on absence: a pack converted with a
                                # database may already have written the richer
                                # file into this same shared root, and a
                                # name-derived one must not clobber it.
                                gear_path = (
                                    pack_output_dir.parent / "sidekick_gear_sets.json"
                                )
                                if not gear_path.is_file():
                                    fbx_names = [
                                        path.stem
                                        for path in (
                                            pack_output_dir / "models"
                                        ).rglob("*.fbx")
                                    ]
                                    fallback_sets = derive_gear_sets_from_names(fbx_names)
                                    if fallback_sets:
                                        write_sidekick_gear_sets_json(
                                            fallback_sets, gear_path
                                        )
                                        logger.info(
                                            "Wrote %d name-derived gear set(s)",
                                            len(fallback_sets),
                                        )

                        # Stamped last: the pack only counts as current once
                        # every metadata file above has actually been written.
                        write_pack_metadata(pack_output_dir)

                    # Check for missing material references (no placeholders - just warn)
                    if not config.dry_run:
                        logger.debug("Checking for missing material references...")
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
                            logger.debug(
                                "Found %d missing material(s) - these meshes will use default materials:",
                                len(missing_materials)
                            )
                            for mat_name in sorted(missing_materials):
                                logger.debug("  Missing: %s", mat_name)
                        else:
                            logger.debug("All referenced materials exist")
                    else:
                        logger.debug("Skipping missing materials check (dry run)")
                else:
                    logger.debug("No MaterialList data available, skipping mesh-material mapping")

        # Step 11: Generate or update project.godot
        logger.info("Step 11: Generating project.godot...")
        generate_project_godot(project_dir, pack_name, config.dry_run)

        # Step 12: Run Godot CLI to convert FBX to .tscn scene files
        if not config.skip_godot_cli:
            logger.info("Step 12: Running Godot CLI...")

            # Build the full pack name including subfolder for GDScript config
            if config.output_subfolder:
                subfolder = config.output_subfolder.replace("\\", "/").strip("/")
                full_pack_name = f"{subfolder}/{pack_name}"
            else:
                full_pack_name = pack_name

            # Resolve requested animation libraries. These live at project root
            # and are produced by earlier animation-pack conversions, so an
            # unmatched selector usually means that pack has not been converted.
            animation_libraries = resolve_animation_libraries(
                project_dir, config.animations
            )
            if config.animations and not animation_libraries:
                warning_msg = (
                    f"No animation libraries matched '{config.animations}' "
                    f"in {project_dir / 'animations'}"
                )
                logger.warning(warning_msg)
                stats.warnings.append(warning_msg)
            elif animation_libraries:
                logger.info(
                    "Binding %d animation library(ies)", len(animation_libraries)
                )

            (
                stats.godot_import_success,
                stats.godot_convert_success,
                stats.godot_timeout_occurred,
                stats.godot_report,
            ) = run_godot_cli(
                config.godot_exe,
                project_dir,
                config.godot_timeout,
                config.dry_run,
                skip_import=config.skip_godot_import,
                retarget=config.retarget,
                keep_meshes_together=config.keep_meshes_together,
                mesh_format=config.mesh_format,
                filter_pattern=config.filter_pattern,
                mesh_scale=config.mesh_scale,
                pack_name=full_pack_name,
                output_subfolder=config.output_subfolder,
                flatten_output=config.flatten_output,
                mode=pack_mode,
                animation_libraries=animation_libraries,
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
                logger.debug("Generated %d .tscn scene files", stats.meshes_converted)
            else:
                logger.debug("No mesh files generated")

            # Staging FBX are no longer referenced by anything once the
            # scenes exist. Never prune a failed run: that would delete the
            # inputs needed to retry it.
            if config.prune_models:
                if should_prune_models(stats):
                    prune_pack_models(pack_output_dir, config.dry_run)
                else:
                    logger.warning(
                        "Not pruning models/: conversion did not complete cleanly"
                    )
        else:
            logger.info("Step 12: Skipping Godot CLI...")

        # Step 13: Give generated resources a UID. Godot assigns one only when
        # the editor saves a resource, so without this every generated scene and
        # material stays unaddressable as uid:// - including from quick-open.
        if not config.dry_run:
            stamped = stamp_resource_uids(pack_output_dir, project_dir)
            if stamped:
                logger.info("Step 13: Stamped %d resource UID(s)", stamped)

        # Write conversion log (not in dry run for the log file itself)
        # Note: log goes to project root (next to project.godot) and appends
        if not config.dry_run:
            write_conversion_log(project_dir, pack_name, stats, config)

        return stats

    finally:
        # Cleanup temp texture files (always runs, even on error)
        if temp_dir_to_cleanup and temp_dir_to_cleanup.exists():
            shutil.rmtree(temp_dir_to_cleanup, ignore_errors=True)
            logger.debug("Cleaned up temp texture directory: %s", temp_dir_to_cleanup)


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
