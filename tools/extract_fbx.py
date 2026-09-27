"""Extract the FBX out of a .unitypackage, so a pack converts without Unity.

The converter reads meshes from --source-files, so a pack never imported into
Unity has nothing to point it at. Its FBX are in the package all the same, and
writing them out is all Unity's import does for a mesh.

Usage:
    python tools/extract_fbx.py <package.unitypackage> <output_dir>

Then convert against the result:
    python converter.py \
        --unity-package "SIDEKICK_SciFi_Robots_....unitypackage" \
        --source-files "<output_dir>" \
        --output "MyGodotProject" \
        --godot "<godot console exe>"

Two things to know:

- **Keep the output directory outside any Godot project.** Godot imports
  everything beneath its project root, so extracting into one silently doubles
  the imported assets.
- **Sidekick joint adjustments need Side_Kick_Data.db**, which ships with the
  Unity tool rather than in the package. Copy one into the output directory to
  get them; without it a character's gear keeps base-rig placement.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unity_package import extract_fbx_to_directory  # noqa: E402


def main() -> int:
    """CLI entry point.

    Returns:
        Process exit code - non-zero when the package could not be read.
    """
    parser = argparse.ArgumentParser(
        description="Extract FBX from a .unitypackage for use as --source-files."
    )
    parser.add_argument("package", type=Path, help="Path to the .unitypackage")
    parser.add_argument(
        "output", type=Path, help="Directory to extract into (kept outside Godot)"
    )
    args = parser.parse_args()

    if not args.package.is_file():
        print(f"No such package: {args.package}", file=sys.stderr)
        return 1

    count = extract_fbx_to_directory(args.package, args.output)
    if count == 0:
        print(f"No FBX found in {args.package.name}", file=sys.stderr)
        return 1

    print(f"Extracted {count} FBX to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
