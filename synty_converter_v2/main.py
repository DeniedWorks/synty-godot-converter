"""CLI entry point for Synty Converter v2."""

import argparse
import logging
import sys
from pathlib import Path

from .converter import convert_pack, SyntyConverter
from .config import ConversionConfig


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Convert Synty Unity assets to Godot format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic conversion with Unity package
  python -m synty_converter_v2 --pack POLYGON_Samurai_Empire --unity SamuraiEmpire.unitypackage --project C:\\Godot\\MyGame

  # From extracted FBX/texture directories
  python -m synty_converter_v2 --pack POLYGON_Fantasy --fbx-dir ./Models --textures-dir ./Textures --project C:\\Godot\\MyGame

  # Preview without writing files
  python -m synty_converter_v2 --pack POLYGON_Samurai_Empire --unity pkg.unitypackage --dry-run

  # Verbose output
  python -m synty_converter_v2 --pack MyPack --unity pkg.unitypackage --project ./game -v
        """
    )

    parser.add_argument(
        '--pack', '-p',
        required=True,
        help='Pack name (e.g., POLYGON_Samurai_Empire)'
    )

    parser.add_argument(
        '--project',
        type=Path,
        default=Path.cwd(),
        help='Path to Godot project root (default: current directory)'
    )

    parser.add_argument(
        '--unity', '-u',
        type=Path,
        help='Path to .unitypackage file'
    )

    parser.add_argument(
        '--fbx-dir',
        type=Path,
        help='Path to directory containing FBX files'
    )

    parser.add_argument(
        '--textures-dir',
        type=Path,
        help='Path to directory containing texture files'
    )

    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Preview changes without writing files'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )

    parser.add_argument(
        '--no-meshes',
        action='store_true',
        help='Disable mesh extraction to separate .res files'
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # Validate inputs
    if args.unity and not args.unity.exists():
        logger.error(f"Unity package not found: {args.unity}")
        sys.exit(1)

    if args.fbx_dir and not args.fbx_dir.exists():
        logger.error(f"FBX directory not found: {args.fbx_dir}")
        sys.exit(1)

    if args.textures_dir and not args.textures_dir.exists():
        logger.error(f"Textures directory not found: {args.textures_dir}")
        sys.exit(1)

    if not args.unity and not args.fbx_dir:
        logger.error("Must provide either --unity package or --fbx-dir")
        sys.exit(1)

    # Create configuration
    config = ConversionConfig(
        pack_name=args.pack,
        godot_project_path=args.project.resolve(),
        unity_package_path=args.unity.resolve() if args.unity else None,
        source_fbx_dir=args.fbx_dir.resolve() if args.fbx_dir else None,
        source_textures_dir=args.textures_dir.resolve() if args.textures_dir else None,
        dry_run=args.dry_run,
        verbose=args.verbose,
        extract_meshes=not args.no_meshes
    )

    # Run conversion
    logger.info(f"Synty Converter v2")
    logger.info(f"Pack: {config.pack_name}")
    logger.info(f"Output: {config.output_base}")

    if args.dry_run:
        logger.info("DRY RUN - no files will be written")

    try:
        converter = SyntyConverter(config)
        summary = converter.convert()

        # Print summary
        print("\n" + "=" * 50)
        print("Conversion Summary")
        print("=" * 50)
        print(f"Pack: {summary['pack_name']}")
        print(f"Materials: {summary['materials']['total']}")

        if summary['materials']['by_type']:
            for mat_type, count in summary['materials']['by_type'].items():
                print(f"  - {mat_type}: {count}")

        print(f"Textures: {summary['textures']}")
        print(f"Models: {summary['models']}")
        print(f"Meshes: {summary['meshes']}")

        if summary['errors']:
            print(f"\nErrors: {len(summary['errors'])}")
            for error in summary['errors']:
                print(f"  - {error}")

        print("=" * 50)

        if args.dry_run:
            print("\nDRY RUN complete - no files were written")
        else:
            print(f"\nOutput written to: {config.output_base}")
            print("\nNext steps:")
            print("1. Download shaders from godotshaders.com to assets/shaders/synty/")
            print("2. Open Godot project to trigger reimport")
            print("3. Check Materials/ folder for generated .tres files")

    except Exception as e:
        logger.exception(f"Conversion failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
