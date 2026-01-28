"""FBX file analysis and extraction utilities."""

import subprocess
import json
import tempfile
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class MeshInfo:
    """Information about a mesh in an FBX file."""
    name: str
    vertex_count: int = 0
    face_count: int = 0
    material_indices: list = field(default_factory=list)


@dataclass
class FBXInfo:
    """Information extracted from an FBX file."""
    path: Path
    meshes: list[MeshInfo] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)
    embedded_textures: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        """Get the base name without extension."""
        return self.path.stem

    @property
    def mesh_names(self) -> list[str]:
        """Get list of mesh names."""
        return [m.name for m in self.meshes]


class FBXExtractor:
    """Extract information from FBX files using Blender headless."""

    BLENDER_SCRIPT = '''
import bpy
import json
import sys

# Clear default scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Import FBX
fbx_path = sys.argv[-2]
output_path = sys.argv[-1]

try:
    bpy.ops.import_scene.fbx(filepath=fbx_path)
except Exception as e:
    print(f"Import error: {e}", file=sys.stderr)
    sys.exit(1)

# Collect information
info = {
    "meshes": [],
    "materials": [],
    "embedded_textures": []
}

materials_seen = set()

for obj in bpy.data.objects:
    if obj.type == 'MESH':
        mesh = obj.data
        mesh_info = {
            "name": obj.name,
            "vertex_count": len(mesh.vertices),
            "face_count": len(mesh.polygons),
            "material_indices": []
        }

        for slot in obj.material_slots:
            if slot.material:
                mat_name = slot.material.name
                mesh_info["material_indices"].append(mat_name)
                if mat_name not in materials_seen:
                    materials_seen.add(mat_name)
                    info["materials"].append(mat_name)

        info["meshes"].append(mesh_info)

# Check for embedded textures
for image in bpy.data.images:
    if image.packed_file:
        info["embedded_textures"].append(image.name)

# Write output
with open(output_path, 'w') as f:
    json.dump(info, f, indent=2)

print(f"Extracted info for {len(info['meshes'])} meshes, {len(info['materials'])} materials")
'''

    def __init__(self, blender_path: Optional[str] = None):
        """Initialize with optional Blender executable path."""
        self.blender_path = blender_path or self._find_blender()

    def _find_blender(self) -> str:
        """Find Blender executable on the system."""
        # Common Blender installation paths
        common_paths = [
            # Windows
            r"C:\Program Files\Blender Foundation\Blender 4.3\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender 3.6\blender.exe",
            # Linux/Mac
            "/usr/bin/blender",
            "/usr/local/bin/blender",
            "/Applications/Blender.app/Contents/MacOS/Blender",
        ]

        for path in common_paths:
            if Path(path).exists():
                return path

        # Try to find in PATH
        try:
            result = subprocess.run(
                ["where", "blender"] if sys.platform == "win32" else ["which", "blender"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return result.stdout.strip().split('\n')[0]
        except Exception:
            pass

        logger.warning("Blender not found - FBX analysis will be limited")
        return "blender"

    def analyze_fbx(self, fbx_path: Path) -> FBXInfo:
        """Analyze an FBX file and extract mesh/material information."""
        fbx_path = Path(fbx_path)
        info = FBXInfo(path=fbx_path)

        # Try Blender-based analysis first
        if self._blender_available():
            try:
                return self._analyze_with_blender(fbx_path)
            except Exception as e:
                logger.warning(f"Blender analysis failed for {fbx_path}: {e}")

        # Fall back to basic filename-based analysis
        return self._analyze_basic(fbx_path)

    def _blender_available(self) -> bool:
        """Check if Blender is available."""
        try:
            result = subprocess.run(
                [self.blender_path, "--version"],
                capture_output=True,
                timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False

    def _analyze_with_blender(self, fbx_path: Path) -> FBXInfo:
        """Analyze FBX using Blender headless mode."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as script_file:
            script_file.write(self.BLENDER_SCRIPT)
            script_path = script_file.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as output_file:
            output_path = output_file.name

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
            for mesh_data in data.get("meshes", []):
                info.meshes.append(MeshInfo(
                    name=mesh_data["name"],
                    vertex_count=mesh_data.get("vertex_count", 0),
                    face_count=mesh_data.get("face_count", 0),
                    material_indices=mesh_data.get("material_indices", [])
                ))
            info.materials = data.get("materials", [])
            info.embedded_textures = data.get("embedded_textures", [])

            return info

        finally:
            Path(script_path).unlink(missing_ok=True)
            Path(output_path).unlink(missing_ok=True)

    def _analyze_basic(self, fbx_path: Path) -> FBXInfo:
        """Basic FBX analysis without Blender - uses filename conventions."""
        info = FBXInfo(path=fbx_path)

        # Extract mesh name from filename
        mesh_name = fbx_path.stem
        info.meshes.append(MeshInfo(name=mesh_name))

        # Try to guess material from naming conventions
        # SM_Bld_House_01 -> might use PolygonPackName_01_A material
        # This is a rough heuristic

        return info

    def batch_analyze(self, fbx_paths: list[Path]) -> dict[str, FBXInfo]:
        """Analyze multiple FBX files."""
        results = {}
        for path in fbx_paths:
            try:
                results[path.stem] = self.analyze_fbx(path)
            except Exception as e:
                logger.warning(f"Failed to analyze {path}: {e}")
        return results


# Import sys for platform check
import sys
