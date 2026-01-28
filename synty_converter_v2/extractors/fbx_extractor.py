"""FBX file analysis using Blender headless mode."""

import subprocess
import json
import tempfile
import sys
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def clean_material_name(name: str) -> str:
    """Clean a material name by removing Blender-added suffixes.

    Blender adds suffixes like .001, .002, etc. when importing FBX files
    if there are name collisions. This strips those suffixes to get the
    original material name from the FBX.

    Args:
        name: Material name potentially with Blender suffix

    Returns:
        Cleaned material name without the suffix
    """
    # Pattern matches .001, .002, etc. at the end of the name
    cleaned = re.sub(r'\.\d{3}$', '', name)
    return cleaned


@dataclass
class MeshInfo:
    """Information about a mesh in an FBX file."""
    name: str
    vertex_count: int = 0
    face_count: int = 0
    materials: list[str] = field(default_factory=list)  # Material names used by this mesh


@dataclass
class FBXInfo:
    """Information extracted from an FBX file."""
    path: Path
    meshes: list[MeshInfo] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)  # All unique material names in FBX (cleaned)
    raw_materials: list[str] = field(default_factory=list)  # Original material names before cleaning

    @property
    def name(self) -> str:
        return self.path.stem

    @property
    def mesh_names(self) -> list[str]:
        return [m.name for m in self.meshes]


class FBXExtractor:
    """Extract material and mesh info from FBX files using Blender."""

    # Blender Python script to extract FBX info
    BLENDER_SCRIPT = '''
import bpy
import json
import sys

# Get arguments after --
argv = sys.argv
argv = argv[argv.index("--") + 1:]
fbx_path = argv[0]
output_path = argv[1]

# Clear default scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Import FBX
try:
    bpy.ops.import_scene.fbx(filepath=fbx_path)
except Exception as e:
    print(f"Import error: {e}", file=sys.stderr)
    sys.exit(1)

# Collect information
info = {
    "meshes": [],
    "materials": []
}

materials_seen = set()

for obj in bpy.data.objects:
    if obj.type == 'MESH':
        mesh = obj.data
        mesh_info = {
            "name": obj.name,
            "vertex_count": len(mesh.vertices),
            "face_count": len(mesh.polygons),
            "materials": []
        }

        for slot in obj.material_slots:
            if slot.material:
                mat_name = slot.material.name
                mesh_info["materials"].append(mat_name)
                if mat_name not in materials_seen:
                    materials_seen.add(mat_name)
                    info["materials"].append(mat_name)

        info["meshes"].append(mesh_info)

# Write output
with open(output_path, 'w') as f:
    json.dump(info, f, indent=2)

print(f"Extracted: {len(info['meshes'])} meshes, {len(info['materials'])} materials")
'''

    def __init__(self, blender_path: Optional[str] = None):
        """Initialize with optional Blender executable path."""
        self.blender_path = blender_path or self._find_blender()
        self._blender_available = None

    def _find_blender(self) -> str:
        """Find Blender executable on the system."""
        common_paths = [
            # Windows
            r"C:\Program Files\Blender Foundation\Blender 4.3\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender 3.6\blender.exe",
            # Linux
            "/usr/bin/blender",
            "/usr/local/bin/blender",
            "/snap/bin/blender",
            # macOS
            "/Applications/Blender.app/Contents/MacOS/Blender",
        ]

        for path in common_paths:
            if Path(path).exists():
                return path

        # Try PATH
        try:
            cmd = ["where", "blender"] if sys.platform == "win32" else ["which", "blender"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.strip().split('\n')[0]
        except Exception:
            pass

        return "blender"  # Hope it's in PATH

    def is_available(self) -> bool:
        """Check if Blender is available."""
        if self._blender_available is not None:
            return self._blender_available

        try:
            result = subprocess.run(
                [self.blender_path, "--version"],
                capture_output=True,
                timeout=10
            )
            self._blender_available = result.returncode == 0
            if self._blender_available:
                version = result.stdout.decode().split('\n')[0]
                logger.info(f"Found Blender: {version}")
        except Exception as e:
            logger.warning(f"Blender not available: {e}")
            self._blender_available = False

        return self._blender_available

    def analyze(self, fbx_path: Path) -> Optional[FBXInfo]:
        """Analyze an FBX file and extract mesh/material information."""
        fbx_path = Path(fbx_path)

        if not self.is_available():
            logger.warning("Blender not available - cannot analyze FBX")
            return None

        if not fbx_path.exists():
            logger.error(f"FBX file not found: {fbx_path}")
            return None

        try:
            return self._analyze_with_blender(fbx_path)
        except Exception as e:
            logger.error(f"Failed to analyze {fbx_path}: {e}")
            return None

    def _analyze_with_blender(self, fbx_path: Path) -> FBXInfo:
        """Run Blender headless to analyze FBX."""
        # Create temp files for script and output
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(self.BLENDER_SCRIPT)
            script_path = f.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            output_path = f.name

        try:
            result = subprocess.run(
                [
                    self.blender_path,
                    "--background",
                    "--python", script_path,
                    "--", str(fbx_path), output_path
                ],
                capture_output=True,
                timeout=60,
                text=True
            )

            if result.returncode != 0:
                raise RuntimeError(f"Blender failed: {result.stderr}")

            with open(output_path, 'r') as f:
                data = json.load(f)

            info = FBXInfo(path=fbx_path)

            # Store raw materials before cleaning
            raw_materials = data.get("materials", [])
            info.raw_materials = raw_materials

            # Clean material names (remove Blender .001, .002 suffixes)
            cleaned_materials = []
            seen_cleaned = set()
            for mat_name in raw_materials:
                cleaned = clean_material_name(mat_name)
                if cleaned not in seen_cleaned:
                    cleaned_materials.append(cleaned)
                    seen_cleaned.add(cleaned)

            info.materials = cleaned_materials

            for mesh_data in data.get("meshes", []):
                # Clean material names in mesh info too
                mesh_materials = [
                    clean_material_name(m) for m in mesh_data.get("materials", [])
                ]
                info.meshes.append(MeshInfo(
                    name=mesh_data["name"],
                    vertex_count=mesh_data.get("vertex_count", 0),
                    face_count=mesh_data.get("face_count", 0),
                    materials=mesh_materials
                ))

            return info

        finally:
            Path(script_path).unlink(missing_ok=True)
            Path(output_path).unlink(missing_ok=True)

    def analyze_batch(self, fbx_paths: list[Path], progress_callback=None) -> dict[str, FBXInfo]:
        """Analyze multiple FBX files."""
        results = {}
        total = len(fbx_paths)

        for i, path in enumerate(fbx_paths):
            if progress_callback:
                progress_callback(i, total, path.name)

            info = self.analyze(path)
            if info:
                results[path.stem] = info

        return results
