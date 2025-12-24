#!/usr/bin/env python3
"""
Synty Asset Converter for Godot
Converts Synty FBX source files to Godot-native format with proper materials.

Usage:
    py tools/synty_converter.py                    # Convert Explorer Kit
    py tools/synty_converter.py --dry-run          # Preview only
    py tools/synty_converter.py --pack OTHER_PACK  # Different pack
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

# Tree foliage material configurations
# Maps material_name -> (leaf_texture, trunk_texture)
TREE_FOLIAGE_CONFIG = {
    # === Samurai Empire trees ===
    # Cherry Blossom trees
    'Cherry_Blossom_02': ('Blossom_02', 'Branches_01'),
    'Cherry_Blossom_03': ('Blossom_02', 'Branches_01'),
    # Maple trees - both canopy and branches meshes need foliage shader
    'Maple_Orange_01': ('MapleSparse_01_TGA', 'Branches_01'),
    'Maple_Branches_01': ('MapleSparse_01_TGA', 'Branches_01'),
    # Pine trees
    'Pine_01': ('Pine_01', 'Branches_01'),
    # Ginko trees
    'Ginko_01': ('Ginko_01_TGA', 'Branches_01'),
    # Bamboo (leaves use BambooLeaf texture, stalks use main atlas)
    'Bamboo_Leaf_01': ('BambooLeaf_01', 'PolygonSamuraiEmpire_Texture_01_A'),

    # === Enchanted Forest trees ===
    'EnchantedTree_Mat_01a': ('enchantedLeaves_01', 'Branches_01'),
    'EnchantedTree_Mat_02': ('enchantedLeaves_02', 'Branches_01'),
    'EnchantedWillow_Mat_01': ('Leaves_Willow_01', 'Branches_01'),
}


# ============================================================================
# FBX Bounds Reader (Blender Headless)
# ============================================================================

class FBXBoundsReader:
    """
    Reads FBX model bounds using Blender in headless mode.
    Falls back to None if Blender is not available.
    """

    # Common Blender installation paths on Windows
    BLENDER_PATHS = [
        r"C:\Program Files\Blender Foundation\Blender 4.3\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 3.6\blender.exe",
    ]

    # Blender Python script to extract FBX bounds
    BLENDER_SCRIPT = '''
import bpy
import sys
import json
import mathutils

# Clear default cube
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Get FBX path from command line args (after --)
argv = sys.argv
argv = argv[argv.index("--") + 1:]
fbx_path = argv[0]
output_path = argv[1]

# Import FBX
bpy.ops.import_scene.fbx(filepath=fbx_path)

# Calculate combined bounding box of all mesh objects
min_coords = [float('inf')] * 3
max_coords = [float('-inf')] * 3

for obj in bpy.context.scene.objects:
    if obj.type == 'MESH':
        # Get world-space bounding box corners
        bbox_corners = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
        for corner in bbox_corners:
            for i in range(3):
                min_coords[i] = min(min_coords[i], corner[i])
                max_coords[i] = max(max_coords[i], corner[i])

# Calculate dimensions
if min_coords[0] != float('inf'):
    dimensions = {
        'width': max_coords[0] - min_coords[0],
        'height': max_coords[2] - min_coords[2],  # Z is up in Blender
        'depth': max_coords[1] - min_coords[1],
        'min': min_coords,
        'max': max_coords
    }
else:
    dimensions = None

# Write result
with open(output_path, 'w') as f:
    json.dump(dimensions, f)
'''

    def __init__(self):
        self.blender_path = self._find_blender()
        self._cache: dict[Path, dict | None] = {}

    def _find_blender(self) -> str | None:
        """Find Blender executable."""
        # Check PATH first
        for name in ['blender', 'blender.exe']:
            result = shutil.which(name)
            if result:
                return result

        # Check common installation paths
        for path in self.BLENDER_PATHS:
            if os.path.exists(path):
                return path

        return None

    @property
    def available(self) -> bool:
        """Check if Blender is available."""
        return self.blender_path is not None

    MAX_RETRIES = 3
    TIMEOUT_SECONDS = 30

    def get_bounds(self, fbx_path: Path) -> dict | None:
        """
        Get the bounding box dimensions of an FBX file.

        Returns dict with keys: width, height, depth, min, max
        Or None if bounds couldn't be read.
        Retries up to MAX_RETRIES times on timeout.
        """
        if not self.available:
            return None

        # Check cache
        if fbx_path in self._cache:
            return self._cache[fbx_path]

        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                # Create temp files for script and output
                with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as script_file:
                    script_file.write(self.BLENDER_SCRIPT)
                    script_path = script_file.name

                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as output_file:
                    output_path = output_file.name

                try:
                    # Run Blender in background mode
                    result = subprocess.run(
                        [
                            self.blender_path,
                            '--background',
                            '--python', script_path,
                            '--',
                            str(fbx_path),
                            output_path
                        ],
                        capture_output=True,
                        text=True,
                        timeout=self.TIMEOUT_SECONDS
                    )

                    # Read output
                    if os.path.exists(output_path):
                        with open(output_path, 'r') as f:
                            content = f.read().strip()
                            if content:
                                dimensions = json.loads(content)
                                self._cache[fbx_path] = dimensions
                                return dimensions

                finally:
                    # Clean up temp files
                    if os.path.exists(script_path):
                        os.unlink(script_path)
                    if os.path.exists(output_path):
                        os.unlink(output_path)

            except subprocess.TimeoutExpired as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    continue  # Retry
                print(f"  Warning: Failed to get bounds for {fbx_path.name} after {self.MAX_RETRIES} attempts: timeout")

            except (subprocess.SubprocessError, json.JSONDecodeError) as e:
                print(f"  Warning: Failed to get bounds for {fbx_path.name}: {e}")
                break  # Don't retry on non-timeout errors

        self._cache[fbx_path] = None
        return None

    def get_height(self, fbx_path: Path) -> float | None:
        """Get just the height of an FBX model."""
        bounds = self.get_bounds(fbx_path)
        if bounds:
            return bounds.get('height')
        return None

    def batch_get_bounds(self, fbx_paths: list[Path], progress_callback=None) -> dict[Path, dict | None]:
        """
        Get bounds for multiple FBX files.
        Uses a single Blender session for efficiency.
        """
        if not self.available or not fbx_paths:
            return {p: None for p in fbx_paths}

        # Filter out cached paths
        uncached = [p for p in fbx_paths if p not in self._cache]
        if not uncached:
            return {p: self._cache.get(p) for p in fbx_paths}

        # Batch script that processes multiple files
        batch_script = '''
import bpy
import sys
import json
import mathutils

argv = sys.argv
argv = argv[argv.index("--") + 1:]
input_path = argv[0]
output_path = argv[1]

# Read input file list
with open(input_path, 'r') as f:
    fbx_paths = json.load(f)

results = {}

for fbx_path in fbx_paths:
    # Clear scene
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

    try:
        # Import FBX
        bpy.ops.import_scene.fbx(filepath=fbx_path)

        # Calculate combined bounding box
        min_coords = [float('inf')] * 3
        max_coords = [float('-inf')] * 3

        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH':
                bbox_corners = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
                for corner in bbox_corners:
                    for i in range(3):
                        min_coords[i] = min(min_coords[i], corner[i])
                        max_coords[i] = max(max_coords[i], corner[i])

        if min_coords[0] != float('inf'):
            results[fbx_path] = {
                'width': max_coords[0] - min_coords[0],
                'height': max_coords[2] - min_coords[2],
                'depth': max_coords[1] - min_coords[1],
            }
        else:
            results[fbx_path] = None
    except Exception as e:
        results[fbx_path] = None

with open(output_path, 'w') as f:
    json.dump(results, f)
'''

        try:
            # Create temp files
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as script_file:
                script_file.write(batch_script)
                script_path = script_file.name

            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as input_file:
                json.dump([str(p) for p in uncached], input_file)
                input_path = input_file.name

            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as output_file:
                output_path = output_file.name

            try:
                # Run Blender
                timeout = 30 + len(uncached) * 5  # Base + 5 sec per model
                result = subprocess.run(
                    [
                        self.blender_path,
                        '--background',
                        '--python', script_path,
                        '--',
                        input_path,
                        output_path
                    ],
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )

                # Read results
                if os.path.exists(output_path):
                    with open(output_path, 'r') as f:
                        content = f.read().strip()
                        if content:
                            batch_results = json.loads(content)
                            for path_str, bounds in batch_results.items():
                                path = Path(path_str)
                                self._cache[path] = bounds

            finally:
                for path in [script_path, input_path, output_path]:
                    if os.path.exists(path):
                        os.unlink(path)

        except Exception as e:
            print(f"  Warning: Batch bounds extraction failed: {e}")

        return {p: self._cache.get(p) for p in fbx_paths}


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class MaterialSlot:
    """Represents a material slot on a mesh."""
    material_name: str
    texture_name: str  # Empty string if "No Albedo Texture"


@dataclass
class MeshInfo:
    """Information about a mesh within a prefab."""
    mesh_name: str
    slots: list[MaterialSlot] = field(default_factory=list)


@dataclass
class PrefabInfo:
    """Information about a prefab (Unity term) / Scene (Godot term)."""
    prefab_name: str
    category: str
    meshes: list[MeshInfo] = field(default_factory=list)


@dataclass
class MaterialInfo:
    """Information about a material to generate."""
    material_name: str
    texture_name: str
    is_shiny: bool = False
    is_glass: bool = False
    trunk_texture_name: str = ""  # For foliage materials needing separate trunk texture
    emission_texture_name: str = ""  # For emissive materials (mushrooms, crystals, etc.)


# ============================================================================
# Configuration
# ============================================================================

class Config:
    """Converter configuration."""

    def __init__(
        self,
        zip_path: Path,
        source_dir: Path,
        project_root: Path,
        pack_name: str,
    ):
        self.zip_path = zip_path
        self.source_dir = source_dir  # Extracted source files
        self.project_root = project_root
        self.pack_name = pack_name

        # Output paths
        self.output_dir = project_root / "assets" / "synty" / pack_name
        self.materials_dir = self.output_dir / "Materials"
        self.textures_dir = self.output_dir / "Textures"
        self.models_dir = self.output_dir / "Models"
        self.prefabs_dir = self.output_dir / "Prefabs"

        # Shared generic assets folder (avoids duplicating SM_Gen_* across packs)
        self.generic_dir = project_root / "assets" / "synty" / "POLYGON_Generic"
        self.generic_models_dir = self.generic_dir / "Models"
        self.generic_prefabs_dir = self.generic_dir / "Prefabs"
        self.generic_textures_dir = self.generic_dir / "Textures"
        self.generic_materials_dir = self.generic_dir / "Materials"

        # Godot resource paths (res://)
        self.res_base = f"res://assets/synty/{pack_name}"
        self.generic_res_base = "res://assets/synty/POLYGON_Generic"


# ============================================================================
# MaterialList Parser
# ============================================================================

class MaterialListParser:
    """
    Parses MaterialList_*.txt files to extract prefab-mesh-material mappings.

    Format:
    -------------------
    Folder Name: [Category]
    -------------------
    Prefab Name: [Prefab_Name]
        Mesh Name: [Mesh_Name]
            Slot: [Material_Name] ([Texture_Name])
    """

    # Regex patterns
    FOLDER_PATTERN = re.compile(r'^Folder Name:\s*(.+)$')
    PREFAB_PATTERN = re.compile(r'^Prefab Name:\s*(.+)$')
    MESH_PATTERN = re.compile(r'^\s+Mesh Name:\s*(.+)$')
    SLOT_PATTERN = re.compile(r'^\s+Slot:\s*(\S+)\s*\(([^)]+)\)$')

    # Explicit material-to-texture mappings for names that don't follow conventions
    MATERIAL_TEXTURE_MAP = {
        # === Samurai Empire ===
        'Ivy_01': 'Generic_Ivy',         # Ivy uses Generic_Ivy.tga
        # Cutout materials (for pile/ground assets) map to sparse textures
        'Ginko_01_Cutout': 'Ginko_Sparse_01_TGA',
        'Maple_Leaf_01_Cutout': 'MapleLeaf_Small_TGA_01',
        'Maple_Leaf_01_Heavy': 'MapleLeaves_Heavy_01',
        # Flowers (material has 's', texture doesn't)
        'Flowers_01': 'Flower_01',
        'Flowers_02': 'Flower_02',
        'Flowers_03': 'Flower_03',
        'Flowers_04': 'Flower_04',

        # === Enchanted Forest - Tree leaves ===
        'EnchantedTree_Mat_01a': 'enchantedLeaves_01',
        'EnchantedTree_Mat_02': 'enchantedLeaves_02',
        'EnchantedWillow_Mat_01': 'Leaves_Willow_01',
        'Branches_Mat_01': 'Branches_01',

        # === Enchanted Forest - Ferns ===
        'Fern_Mat_02': 'Fern_2_TGA',
        'TreeFern_Mat_02': 'TreeFern_01',
        'TreeFern_01_Card': 'TreeFern_01',
        'Koru_Mat_01': 'Fern_1_TGA',

        # === Enchanted Forest - Leaves/Vegetation ===
        'Leaves': 'Leaves_TGA',
        'Undergrowth_Mat': 'Undergrowth',

        # === Enchanted Forest - Card/LOD materials ===
        'EnchantedTree_Large_01_Card': 'TreeLarge_01',
        'EnchantedTree_Large_02_Card': 'TreeLarge_02',
        'EnchantedTree_Medium_01_Card': 'TreeMedium_01',
        'EnchantedTree_Medium_02_Card': 'TreeMedium_02',
        'EnchantedTree_Small_01_Card': 'treeSmall_01',
        'EnchantedTree_Small_02_Card': 'treeSmall_02',
        'EnchantedTree_Giant_01_Card': 'treeGiant_01',
        'EnchantedTree_Giant_02_Card': 'treeGiant_02',
        'EnchantedTree_House_01_Card': 'treeHouse_01',

        # === Enchanted Forest - Triplanar (use standard shader) ===
        'Dirt_Leaves_Triplanar_01': 'Dirt_Texture_Enchanted_01',
        'Moss_Enchanted_Triplanar_01': 'Moss_Enchanted_Texture_01',

        # === Enchanted Forest - Crystals (use main texture for emissive glow) ===
        'Crystal_Mat_01': 'PolygonNatureBiomesS2_Texture_01',
    }

    def _infer_texture_from_material(self, material_name: str, pack_prefix: str = "") -> str:
        """
        Infer texture name from material name for packs using 'Uses custom shader'.

        Common patterns:
        - PolygonSamuraiEmpire_01_A -> PolygonSamuraiEmpire_Texture_01_A
        - Generic_01_A -> Generic_01_A (already correct, don't transform)
        - Wall_01 -> Wall_01 (search for matching texture)
        - Cherry_Blossom_02 -> Blossom_02 (Samurai Empire special case)
        - Vines_01 -> Generic_Ivy (explicit mapping)
        """
        # Check explicit mappings first
        if material_name in self.MATERIAL_TEXTURE_MAP:
            return self.MATERIAL_TEXTURE_MAP[material_name]

        # Special case: Cherry_Blossom_XX -> Blossom_XX (Samurai Empire trees)
        if material_name.startswith('Cherry_Blossom_') and material_name[-2:].isdigit():
            # Cherry_Blossom_02 -> Blossom_02, Cherry_Blossom_03 -> Blossom_03
            suffix = material_name.split('_')[-1]  # Get the number suffix
            return f"Blossom_{suffix}"

        # Don't transform Generic_ materials - they already match texture names directly
        if material_name.startswith('Generic_'):
            return material_name

        # If material name contains pack-specific prefix + numbered suffix like _01_A, insert "Texture_"
        # Only for pack-prefixed names (PolygonSamuraiEmpire_01_A, PolygonExplorer_01_A, etc.)
        if re.match(r'^Polygon[A-Za-z]+_\d+_[A-Z]$', material_name):
            # Insert "Texture_" before the number suffix
            parts = material_name.rsplit('_', 2)
            if len(parts) == 3:
                return f"{parts[0]}_Texture_{parts[1]}_{parts[2]}"
        return material_name

    def parse(self, content: str) -> tuple[list[PrefabInfo], dict[str, MaterialInfo]]:
        """
        Parse MaterialList content.

        Returns:
            - List of PrefabInfo
            - Dict of material_name -> MaterialInfo
        """
        prefabs = []
        materials = {}

        current_category = ""
        current_prefab = None
        current_mesh = None

        for line in content.splitlines():
            line = line.rstrip()

            # Skip separators and empty lines
            if line.startswith('---') or not line.strip():
                continue

            # Folder/Category
            folder_match = self.FOLDER_PATTERN.match(line)
            if folder_match:
                current_category = folder_match.group(1).strip()
                continue

            # Prefab
            prefab_match = self.PREFAB_PATTERN.match(line)
            if prefab_match:
                if current_prefab:
                    prefabs.append(current_prefab)
                current_prefab = PrefabInfo(
                    prefab_name=prefab_match.group(1).strip(),
                    category=current_category
                )
                current_mesh = None
                continue

            # Mesh
            mesh_match = self.MESH_PATTERN.match(line)
            if mesh_match and current_prefab:
                current_mesh = MeshInfo(mesh_name=mesh_match.group(1).strip())
                current_prefab.meshes.append(current_mesh)
                continue

            # Slot (material)
            slot_match = self.SLOT_PATTERN.match(line)
            if slot_match and current_mesh:
                material_name = slot_match.group(1).strip()
                texture_raw = slot_match.group(2).strip()

                # Handle different texture formats:
                # - "No Albedo Texture" -> no texture (glass)
                # - "Uses custom shader" -> infer texture from material name
                # - Normal texture name -> use as-is
                if "No Albedo" in texture_raw:
                    texture_name = ""
                elif "custom shader" in texture_raw.lower():
                    texture_name = self._infer_texture_from_material(material_name)
                else:
                    texture_name = texture_raw

                slot = MaterialSlot(
                    material_name=material_name,
                    texture_name=texture_name
                )
                current_mesh.slots.append(slot)

                # Track unique materials
                if material_name not in materials:
                    # Check if this is a tree foliage material that needs trunk texture
                    trunk_texture = ""
                    if material_name in TREE_FOLIAGE_CONFIG:
                        leaf_tex, trunk_tex = TREE_FOLIAGE_CONFIG[material_name]
                        texture_name = leaf_tex  # Override with correct leaf texture
                        trunk_texture = trunk_tex

                    materials[material_name] = MaterialInfo(
                        material_name=material_name,
                        texture_name=texture_name,
                        is_shiny="_Shiny" in material_name,
                        is_glass="_Glass" in material_name or "Glass" in material_name,
                        trunk_texture_name=trunk_texture
                    )

        # Don't forget the last prefab
        if current_prefab:
            prefabs.append(current_prefab)

        return prefabs, materials

    def parse_from_directory(self, source_dir: Path) -> tuple[list[PrefabInfo], dict[str, MaterialInfo]]:
        """Parse all MaterialList files from source directory."""
        all_prefabs = []
        all_materials = {}

        # Find all MaterialList files in the source directory
        material_list_files = list(source_dir.glob("MaterialList*.txt"))

        if not material_list_files:
            raise FileNotFoundError(f"MaterialList not found in {source_dir}")

        print(f"  Found {len(material_list_files)} MaterialList files:")
        for mat_file in material_list_files:
            print(f"    - {mat_file.name}")
            content = mat_file.read_text(encoding='utf-8')
            prefabs, materials = self.parse(content)
            all_prefabs.extend(prefabs)
            all_materials.update(materials)

        return all_prefabs, all_materials

    def parse_from_zip(self, zip_path: Path, material_list_pattern: str) -> tuple[list[PrefabInfo], dict[str, MaterialInfo]]:
        """Extract and parse all MaterialList files from zip file."""
        all_prefabs = []
        all_materials = {}

        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Find all MaterialList files
            material_list_files = [
                name for name in zf.namelist()
                if 'MaterialList' in name and name.endswith('.txt')
            ]

            if not material_list_files:
                raise FileNotFoundError(f"MaterialList not found in {zip_path}")

            print(f"  Found {len(material_list_files)} MaterialList files:")
            for name in material_list_files:
                print(f"    - {name}")
                content = zf.read(name).decode('utf-8')
                prefabs, materials = self.parse(content)
                all_prefabs.extend(prefabs)
                all_materials.update(materials)

        return all_prefabs, all_materials


# ============================================================================
# Material Generator
# ============================================================================

class MaterialGenerator:
    """Generates Godot ShaderMaterial .tres files using custom Synty shaders."""

    # Shader paths (relative to res://)
    POLYGON_SHADER = "res://assets/shaders/synty/polygon_shader.gdshader"
    GLASS_SHADER = "res://assets/shaders/synty/refractive_transparent.gdshader"
    FOLIAGE_SHADER = "res://assets/shaders/synty/foliage.gdshader"
    WATER_SHADER = "res://assets/shaders/synty/water.gdshader"

    # Standard material with polygon_shader
    STANDARD_TEMPLATE = '''\
[gd_resource type="ShaderMaterial" load_steps=3 format=3]

[ext_resource type="Shader" path="{shader_path}" id="1"]
[ext_resource type="Texture2D" path="{texture_path}" id="2"]

[resource]
resource_name = "{material_name}"
shader = ExtResource("1")
shader_parameter/color_tint = Color(1, 1, 1, 1)
shader_parameter/metallic = {metallic}
shader_parameter/smoothness = {smoothness}
shader_parameter/enable_base_texture = true
shader_parameter/base_texture = ExtResource("2")
shader_parameter/base_tiling = Vector2(1, 1)
shader_parameter/base_offset = Vector2(0, 0)
'''

    # NOTE: Opaque material template reserved for future use
    # Currently not used - _detect_material_type() never returns 'opaque'
    # Uncomment when needed for materials that require force_opaque = true
    #
    # OPAQUE_TEMPLATE = '''\
    # [gd_resource type="ShaderMaterial" load_steps=3 format=3]
    #
    # [ext_resource type="Shader" path="{shader_path}" id="1"]
    # [ext_resource type="Texture2D" path="{texture_path}" id="2"]
    #
    # [resource]
    # resource_name = "{material_name}"
    # shader = ExtResource("1")
    # shader_parameter/color_tint = Color(1, 1, 1, 1)
    # shader_parameter/metallic = {metallic}
    # shader_parameter/smoothness = {smoothness}
    # shader_parameter/force_opaque = true
    # shader_parameter/enable_base_texture = true
    # shader_parameter/base_texture = ExtResource("2")
    # shader_parameter/base_tiling = Vector2(1, 1)
    # shader_parameter/base_offset = Vector2(0, 0)
    # '''

    # Shiny material (higher metallic/smoothness)
    SHINY_TEMPLATE = '''\
[gd_resource type="ShaderMaterial" load_steps=3 format=3]

[ext_resource type="Shader" path="{shader_path}" id="1"]
[ext_resource type="Texture2D" path="{texture_path}" id="2"]

[resource]
resource_name = "{material_name}"
shader = ExtResource("1")
shader_parameter/color_tint = Color(1, 1, 1, 1)
shader_parameter/metallic = 0.8
shader_parameter/smoothness = 0.8
shader_parameter/enable_base_texture = true
shader_parameter/base_texture = ExtResource("2")
shader_parameter/base_tiling = Vector2(1, 1)
shader_parameter/base_offset = Vector2(0, 0)
'''

    # Glass material with refractive_transparent shader
    GLASS_TEMPLATE = '''\
[gd_resource type="ShaderMaterial" load_steps=2 format=3]

[ext_resource type="Shader" path="{shader_path}" id="1"]

[resource]
resource_name = "{material_name}"
shader = ExtResource("1")
shader_parameter/enable_triplanar = false
shader_parameter/base_color = Color(0.8, 0.9, 1.0, 0.3)
shader_parameter/metallic = 0.1
shader_parameter/smoothness = 0.9
shader_parameter/opacity = 0.3
shader_parameter/enable_fresnel = true
shader_parameter/fresnel_color = Color(1, 1, 1, 0.5)
shader_parameter/fresnel_border = 2.0
shader_parameter/fresnel_power = 3.0
'''

    # Glass/crystal material with emission texture support (transparent + glow)
    GLASS_EMISSIVE_TEMPLATE = '''\
[gd_resource type="ShaderMaterial" load_steps=3 format=3]

[ext_resource type="Shader" path="{shader_path}" id="1"]
[ext_resource type="Texture2D" path="{emission_texture_path}" id="2"]

[resource]
resource_name = "{material_name}"
shader = ExtResource("1")
shader_parameter/enable_triplanar = false
shader_parameter/base_color = Color(0.7, 0.85, 1.0, 0.4)
shader_parameter/metallic = 0.2
shader_parameter/smoothness = 0.95
shader_parameter/opacity = 0.4
shader_parameter/enable_fresnel = true
shader_parameter/fresnel_color = Color(0.8, 0.9, 1.0, 0.6)
shader_parameter/fresnel_border = 2.5
shader_parameter/fresnel_power = 3.5
shader_parameter/enable_emission_texture = true
shader_parameter/emission_texture = ExtResource("2")
shader_parameter/emission_tiling = Vector2(1, 1)
shader_parameter/emission_offset = Vector2(0, 0)
shader_parameter/emission_color_tint = Color(1, 1, 1, 1)
shader_parameter/emission_intensity = 1.5
'''

    # Foliage material with wind animation and alpha cutout
    FOLIAGE_TEMPLATE = '''\
[gd_resource type="ShaderMaterial" load_steps=4 format=3]

[ext_resource type="Shader" path="{shader_path}" id="1"]
[ext_resource type="Texture2D" path="{leaf_texture_path}" id="2"]
[ext_resource type="Texture2D" path="{trunk_texture_path}" id="3"]

[resource]
resource_name = "{material_name}"
shader = ExtResource("1")
shader_parameter/leaf_color = ExtResource("2")
shader_parameter/trunk_color = ExtResource("3")
shader_parameter/alpha_clip_threshold = 0.25
shader_parameter/enable_breeze = {enable_breeze}
shader_parameter/breeze_strength = {breeze_strength}
shader_parameter/enable_light_wind = {enable_light_wind}
shader_parameter/light_wind_strength = {light_wind_strength}
'''

    # Water material with wave animation
    WATER_TEMPLATE = '''\
[gd_resource type="ShaderMaterial" load_steps=2 format=3]

[ext_resource type="Shader" path="{shader_path}" id="1"]

[resource]
resource_name = "{material_name}"
shader = ExtResource("1")
shader_parameter/water_color = Color(0.2, 0.4, 0.6, 0.8)
shader_parameter/wave_speed = 1.0
shader_parameter/wave_strength = 0.1
'''

    # Solid color material (no texture)
    SOLID_COLOR_TEMPLATE = '''\
[gd_resource type="ShaderMaterial" load_steps=2 format=3]

[ext_resource type="Shader" path="{shader_path}" id="1"]

[resource]
resource_name = "{material_name}"
shader = ExtResource("1")
shader_parameter/color_tint = Color(1, 1, 1, 1)
shader_parameter/metallic = 0.0
shader_parameter/smoothness = 0.2
shader_parameter/enable_base_texture = false
'''

    # Standard material with emission texture support
    EMISSIVE_TEMPLATE = '''\
[gd_resource type="ShaderMaterial" load_steps=4 format=3]

[ext_resource type="Shader" path="{shader_path}" id="1"]
[ext_resource type="Texture2D" path="{texture_path}" id="2"]
[ext_resource type="Texture2D" path="{emission_texture_path}" id="3"]

[resource]
resource_name = "{material_name}"
shader = ExtResource("1")
shader_parameter/color_tint = Color(1, 1, 1, 1)
shader_parameter/metallic = {metallic}
shader_parameter/smoothness = {smoothness}
shader_parameter/enable_base_texture = true
shader_parameter/base_texture = ExtResource("2")
shader_parameter/base_tiling = Vector2(1, 1)
shader_parameter/base_offset = Vector2(0, 0)
shader_parameter/enable_emission_texture = true
shader_parameter/emission_texture = ExtResource("3")
shader_parameter/emission_tiling = Vector2(1, 1)
shader_parameter/emission_offset = Vector2(0, 0)
shader_parameter/emission_color_tint = Color(1, 1, 1, 1)
'''

    def _detect_material_type(self, material: MaterialInfo) -> str:
        """Detect material type from name patterns."""
        name = material.material_name.lower()

        # Check TREE_FOLIAGE_CONFIG first - explicit foliage materials
        if material.material_name in TREE_FOLIAGE_CONFIG:
            return 'foliage'

        # Check for specific types
        if material.is_glass or 'glass' in name:
            return 'glass'

        # Crystals/gems/jewels - transparent with glow
        if any(x in name for x in ['crystal', 'gem', 'jewel', 'geode']):
            return 'crystal'

        if material.is_shiny or '_shiny' in name:
            return 'shiny'

        # Water detection
        if any(x in name for x in ['water', 'ocean', 'river', 'lake', 'pond']):
            return 'water'

        # Foliage shader ONLY for actual trees with vertex color encoding
        # These are Synty tree materials that have proper COLOR.b vertex encoding
        tree_canopy_keywords = [
            'tree', 'blossom', 'canopy',  # Generic tree terms
            'pine', 'maple', 'ginko', 'cherry', 'oak', 'willow', 'birch',  # Deciduous
            'palm', 'cypress', 'fir', 'spruce', 'cedar', 'redwood',  # Evergreen
        ]

        # Materials that should NOT use foliage shader even if they match tree keywords
        static_exclusions = [
            # Ground/pile items (static decorations)
            'ground', 'floor', 'pile', 'heavy', 'cutout', 'small',
            # Non-tree foliage (no vertex colors)
            'vine', 'ivy', 'fern', 'grass', 'bush', 'shrub', 'hedge',
            # Tree parts without vertex color encoding
            'bark', 'trunk', 'branch', 'log', 'wood', 'stump', 'root',
            # Non-foliage items that may contain tree keywords
            'fire', 'flame', 'door', 'frame', 'particle', 'effect', 'fx',
            # Standalone leaf textures (not tree canopies)
            'leaf_01', 'leaf_02', 'leaf_03',
            # LOD billboard/card materials (no vertex color encoding)
            'card',
        ]

        # Only use foliage shader if material contains tree keyword AND no exclusions
        if any(x in name for x in tree_canopy_keywords) and \
           not any(x in name for x in static_exclusions):
            return 'foliage'

        return 'standard'

    def generate(
        self,
        material: MaterialInfo,
        config: Config,
        texture_filename_map: dict[str, str] | None = None
    ) -> str:
        """Generate .tres content for a material."""
        mat_type = self._detect_material_type(material)

        if mat_type == 'glass':
            return self.GLASS_TEMPLATE.format(
                material_name=material.material_name,
                shader_path=self.GLASS_SHADER
            )

        # Crystal - transparent glass with emission glow
        if mat_type == 'crystal':
            # Use emission texture if available
            if material.emission_texture_name:
                emission_filename = f"{material.emission_texture_name}.png"
                emission_texture_path = f"{config.res_base}/Textures/{emission_filename}"
                return self.GLASS_EMISSIVE_TEMPLATE.format(
                    material_name=material.material_name,
                    shader_path=self.GLASS_SHADER,
                    emission_texture_path=emission_texture_path
                )
            else:
                # No emission texture - use regular glass
                return self.GLASS_TEMPLATE.format(
                    material_name=material.material_name,
                    shader_path=self.GLASS_SHADER
                )

        if mat_type == 'water':
            return self.WATER_TEMPLATE.format(
                material_name=material.material_name,
                shader_path=self.WATER_SHADER
            )

        # Check for materials without textures (solid color)
        if not material.texture_name or material.texture_name.strip() == '':
            return self.SOLID_COLOR_TEMPLATE.format(
                material_name=material.material_name,
                shader_path=self.POLYGON_SHADER
            )

        # Get actual texture filename from map, or construct from texture_name
        if texture_filename_map and material.texture_name in texture_filename_map:
            texture_filename = texture_filename_map[material.texture_name]
        else:
            texture_filename = f"{material.texture_name}.png"

        texture_path = f"{config.res_base}/Textures/{texture_filename}"

        if mat_type == 'shiny':
            return self.SHINY_TEMPLATE.format(
                material_name=material.material_name,
                texture_path=texture_path,
                shader_path=self.POLYGON_SHADER
            )

        # Foliage uses foliage.gdshader for wind animation and alpha cutout
        # Synty models have vertex colors for leaf/trunk detection
        if mat_type == 'foliage':
            leaf_texture_path = texture_path  # Already resolved above

            # Get trunk texture path (use Branches_01 as default for trees)
            trunk_texture = material.trunk_texture_name or 'Branches_01'
            if texture_filename_map and trunk_texture in texture_filename_map:
                trunk_filename = texture_filename_map[trunk_texture]
            else:
                trunk_filename = f"{trunk_texture}.tga"
            trunk_texture_path = f"{config.res_base}/Textures/{trunk_filename}"

            return self.FOLIAGE_TEMPLATE.format(
                material_name=material.material_name,
                leaf_texture_path=leaf_texture_path,
                trunk_texture_path=trunk_texture_path,
                shader_path=self.FOLIAGE_SHADER,
                enable_breeze='true',
                breeze_strength=0.2,
                enable_light_wind='true',
                light_wind_strength=0.15,
            )

        # NOTE: Opaque material handling reserved for future use
        # Uncomment when _detect_material_type() is updated to return 'opaque'
        #
        # if mat_type == 'opaque':
        #     return self.OPAQUE_TEMPLATE.format(
        #         material_name=material.material_name,
        #         texture_path=texture_path,
        #         shader_path=self.POLYGON_SHADER,
        #         metallic=0.0,
        #         smoothness=0.2
        #     )

        # Check for emissive texture (mushrooms, crystals, etc.)
        if material.emission_texture_name:
            # Resolve emission texture filename (prefer PNG, fallback to TGA)
            emission_filename = f"{material.emission_texture_name}.png"
            emission_texture_path = f"{config.res_base}/Textures/{emission_filename}"
            return self.EMISSIVE_TEMPLATE.format(
                material_name=material.material_name,
                texture_path=texture_path,
                emission_texture_path=emission_texture_path,
                shader_path=self.POLYGON_SHADER,
                metallic=0.0,
                smoothness=0.2
            )

        # Standard material
        return self.STANDARD_TEMPLATE.format(
            material_name=material.material_name,
            texture_path=texture_path,
            shader_path=self.POLYGON_SHADER,
            metallic=0.0,
            smoothness=0.2
        )

    def write_material(
        self,
        material: MaterialInfo,
        config: Config,
        texture_filename_map: dict[str, str] | None = None
    ) -> Path:
        """Write material .tres file and return the path."""
        content = self.generate(material, config, texture_filename_map)
        output_path = config.materials_dir / f"{material.material_name}.tres"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding='utf-8')
        return output_path


# ============================================================================
# Prefab Generator
# ============================================================================

class PrefabGenerator:
    """Generates Godot .tscn scene files for prefabs."""

    # Mesh name patterns to ALWAYS hide (redundant geometry)
    # Branches mesh - trunk is rendered via vertex colors in canopy mesh
    ALWAYS_HIDDEN_PATTERNS = ['_Branches_']

    # LOD patterns - only LOD0 should be visible, hide LOD1, LOD2, LOD3, etc.
    # Synty packs stack all LODs in the same prefab, causing massive overdraw if all visible
    LOD_HIDE_PATTERNS = ['_LOD1', '_LOD2', '_LOD3', '_LOD4', '_LOD5']

    # Target heights in meters for different asset categories
    # Assets will be scaled to fit these heights
    TARGET_HEIGHTS = {
        'tree': 8.0,        # Trees ~8m tall
        'bush': 1.2,        # Bushes ~1.2m
        'grass': 0.4,       # Grass clumps ~40cm
        'flower': 0.5,      # Flowers ~50cm
        'rock': 1.5,        # Rocks ~1.5m
        'fern': 0.6,        # Ferns ~60cm
        'vine': 2.0,        # Vines ~2m
        'bamboo': 4.0,      # Bamboo ~4m
        'prop': 1.0,        # Generic props ~1m
        'building': None,   # Buildings - don't scale
        'character': None,  # Characters - don't scale
        'vehicle': None,    # Vehicles - don't scale
        'default': 1.0,     # Default ~1m
    }

    def __init__(self, fbx_bounds_reader: FBXBoundsReader | None = None, normalize_height: float | None = None):
        """
        Initialize PrefabGenerator.

        Args:
            fbx_bounds_reader: Optional FBXBoundsReader for height normalization.
            normalize_height: Target height in meters for normalized scaling.
                              If provided with a bounds reader, assets will be scaled
                              to this height. If None, uses fixed category-based scaling.
        """
        # Cache of FBX path -> list of mesh names found in the file
        self._fbx_mesh_cache: dict[Path, list[str]] = {}
        self._bounds_reader = fbx_bounds_reader
        self._normalize_height = normalize_height

    def _get_asset_category(self, prefab_name: str) -> str:
        """Determine asset category from prefab name for target height selection."""
        name_lower = prefab_name.lower()

        # Check for specific categories
        if any(x in name_lower for x in ['_tree_', 'tree_']):
            return 'tree'
        if any(x in name_lower for x in ['_bush_', 'bush_']):
            return 'bush'
        if any(x in name_lower for x in ['_grass_', 'grass_']):
            return 'grass'
        if any(x in name_lower for x in ['_flower_', 'flower_']):
            return 'flower'
        if any(x in name_lower for x in ['_rock_', 'rock_', '_stone_']):
            return 'rock'
        if any(x in name_lower for x in ['_fern_', 'fern_']):
            return 'fern'
        if any(x in name_lower for x in ['_vine_', 'vine_', '_ivy_']):
            return 'vine'
        if any(x in name_lower for x in ['_bamboo_', 'bamboo_']):
            return 'bamboo'
        if any(x in name_lower for x in ['_bld_', 'building_', 'house_', 'temple_']):
            return 'building'
        if any(x in name_lower for x in ['character_', 'chr_', 'sk_chr_']):
            return 'character'
        if any(x in name_lower for x in ['_veh_', 'vehicle_', 'cart_', 'boat_']):
            return 'vehicle'
        if '_prop_' in name_lower or name_lower.startswith('sm_prop_'):
            return 'prop'

        return 'default'

    def _calculate_scale(self, fbx_path: Path, prefab_name: str) -> float | None | str:
        """
        Calculate the scale factor for an asset using size normalization.

        Uses Blender to get the actual model dimensions and scales based on
        the largest dimension (width, height, or depth) to match the target size.

        Returns scale factor, or None if:
        - Normalization is disabled
        - Blender is unavailable
        - Category is excluded (buildings, characters, vehicles)
        - Asset is a water plane (flat objects)

        Returns 'skip' if Blender failed to read bounds (asset will be skipped).
        """
        category = self._get_asset_category(prefab_name)
        name_lower = prefab_name.lower()

        # Skip scaling for certain categories (already in correct scale)
        if category in ('building', 'character', 'vehicle'):
            return None

        # Skip normalization for water planes (they're flat)
        if any(x in name_lower for x in ['water_plane', 'water_dip']):
            return None

        # If size normalization is enabled and we have a bounds reader
        if self._normalize_height is not None and self._bounds_reader is not None:
            bounds = self._bounds_reader.get_bounds(fbx_path)
            if bounds:
                width = bounds.get('width', 0)
                height = bounds.get('height', 0)
                depth = bounds.get('depth', 0)
                # Use the largest dimension (handles both tall trees and wide floors)
                max_dimension = max(width, height, depth)
                if max_dimension > 0:
                    target_size_m = self._normalize_height
                    scale = target_size_m / max_dimension
                    return scale
                else:
                    # Zero or negative dimension - skip this asset
                    return 'skip'
            else:
                # Blender failed to read bounds - return special marker
                # Caller should skip this asset
                return 'skip'

        # Normalization disabled or Blender unavailable
        return None

    def _should_hide_mesh(self, mesh_name: str) -> bool:
        """
        Check if a mesh should be hidden.

        Hides:
        - Branches meshes (trunk rendered via vertex colors in canopy)
        - Non-LOD0 meshes (LOD1, LOD2, LOD3, etc. - Synty stacks all LODs)
        """
        # Always hide these patterns (branches, etc.)
        for pattern in self.ALWAYS_HIDDEN_PATTERNS:
            if pattern in mesh_name:
                return True

        # Hide non-LOD0 meshes (only show highest detail)
        for pattern in self.LOD_HIDE_PATTERNS:
            if pattern in mesh_name:
                return True

        return False

    def _extract_fbx_mesh_names(self, fbx_path: Path) -> list[str]:
        """Extract mesh names from FBX file by parsing binary content."""
        if fbx_path in self._fbx_mesh_cache:
            return self._fbx_mesh_cache[fbx_path]

        mesh_names = set()
        try:
            with open(fbx_path, 'rb') as f:
                content = f.read()
                # Look for mesh name patterns (SM_, SK_, FX_, Chr_, pCube, etc.)
                patterns = [
                    rb'pCube\d*SM_[A-Za-z0-9_]+',  # pCube8SM_... pattern (some Synty FBX files)
                    rb'SM_[A-Za-z0-9_]+',
                    rb'SK_[A-Za-z0-9_]+',
                    rb'FX_[A-Za-z0-9_]+',
                    rb'Chr_[A-Za-z0-9_]+',
                ]
                for pattern in patterns:
                    matches = re.findall(pattern, content)
                    for m in matches:
                        name = m.decode('utf-8', errors='ignore')
                        # Filter out likely non-mesh names (too short)
                        if len(name) > 5:
                            mesh_names.add(name)
        except Exception:
            pass

        result = list(mesh_names)
        self._fbx_mesh_cache[fbx_path] = result
        return result

    def _fuzzy_match_mesh_name(self, material_list_name: str, fbx_mesh_names: list[str]) -> str:
        """
        Find the best matching FBX mesh name for a MaterialList mesh name.
        Returns the FBX name if a good match is found, otherwise the original name.
        """
        if not fbx_mesh_names:
            return material_list_name

        # Try exact match first
        if material_list_name in fbx_mesh_names:
            return material_list_name

        # Try case-insensitive match
        lower_name = material_list_name.lower()
        for fbx_name in fbx_mesh_names:
            if fbx_name.lower() == lower_name:
                return fbx_name

        # Try Character_ -> Chr_ transformation (common Synty naming)
        # e.g., "Character_Explorer_Female_01" -> "Chr_Explorer_Female_01"
        if material_list_name.startswith("Character_"):
            chr_name = material_list_name.replace("Character_", "Chr_", 1)
            for fbx_name in fbx_mesh_names:
                if fbx_name.lower() == chr_name.lower():
                    return fbx_name

        # Try matching without "Alt" suffix (common variation)
        name_no_alt = re.sub(r'_Alt(?=_\d+$|$)', '', material_list_name)
        if name_no_alt != material_list_name:
            for fbx_name in fbx_mesh_names:
                if fbx_name.lower() == name_no_alt.lower():
                    return fbx_name

        # Try fuzzy matching - find best similarity
        best_match = None
        best_ratio = 0.0

        for fbx_name in fbx_mesh_names:
            # Compare lowercase versions
            ratio = SequenceMatcher(None, lower_name, fbx_name.lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = fbx_name

        # Only accept matches with >70% similarity
        if best_ratio > 0.7 and best_match:
            return best_match

        return material_list_name

    def _find_fbx_file(self, prefab: PrefabInfo, config: Config) -> Path | None:
        """Find the FBX file for a prefab."""
        # Build list of possible file names
        possible_names = [f"{prefab.prefab_name}.fbx"]

        # For character prefabs, try SK_Chr_ transformation
        if prefab.prefab_name.startswith("Character_"):
            # Character_Explorer_Female_01 -> SK_Chr_Explorer_Female_01
            transformed = prefab.prefab_name.replace("Character_", "SK_Chr_")
            possible_names.append(f"{transformed}.fbx")

        # Also try mesh names directly
        for mesh in prefab.meshes:
            mesh_name = mesh.mesh_name.lstrip('_')  # Remove leading underscore
            possible_names.append(f"{mesh_name}.fbx")
            # Try with SM_ or SK_ prefix if not present
            if not mesh_name.startswith(('SM_', 'SK_')):
                possible_names.append(f"SM_{mesh_name}.fbx")
                possible_names.append(f"SK_{mesh_name}.fbx")

        # Search in different directories
        search_dirs = [
            config.source_dir / prefab.category if prefab.category else None,
            config.source_dir / "FBX",
            config.source_dir / "Characters",
            config.source_dir,
        ]

        for search_dir in search_dirs:
            if search_dir is None or not search_dir.exists():
                continue
            for name in possible_names:
                fbx_path = search_dir / name
                if fbx_path.exists():
                    return fbx_path

        # If not found, search recursively under FBX directory
        fbx_root = config.source_dir / "FBX"
        if fbx_root.exists():
            for name in possible_names:
                matches = list(fbx_root.glob(f"**/{name}"))
                if matches:
                    return matches[0]

        # Search for any */FBX subdirectory (e.g., Shops/FBX, Generic/FBX)
        for subdir in config.source_dir.iterdir():
            if subdir.is_dir():
                fbx_subdir = subdir / "FBX"
                if fbx_subdir.exists():
                    for name in possible_names:
                        matches = list(fbx_subdir.glob(f"**/{name}"))
                        if matches:
                            return matches[0]

        return None

    def generate(
        self,
        prefab: PrefabInfo,
        config: Config,
        valid_materials: set[str] | None = None
    ) -> tuple[str, Path | None]:
        """
        Generate .tscn content for a prefab.

        Returns:
            - tscn content string
            - FBX source path (or None if not found)
        """
        fbx_source = self._find_fbx_file(prefab, config)
        if not fbx_source:
            return "", None

        # Determine model path in Godot
        model_subdir = prefab.category if prefab.category else "Props"
        model_res_path = f"{config.res_base}/Models/{model_subdir}/{fbx_source.name}"

        # Collect unique materials for this prefab (only valid ones)
        materials_used = {}
        for mesh in prefab.meshes:
            for slot in mesh.slots:
                # Skip materials that don't have valid textures
                if valid_materials and slot.material_name not in valid_materials:
                    continue
                if slot.material_name not in materials_used:
                    materials_used[slot.material_name] = slot

        # Build external resources
        ext_resources = [
            f'[ext_resource type="PackedScene" path="{model_res_path}" id="1"]'
        ]

        mat_id = 2
        mat_id_map = {}
        for mat_name in materials_used:
            mat_res_path = f"{config.res_base}/Materials/{mat_name}.tres"
            ext_resources.append(
                f'[ext_resource type="Material" path="{mat_res_path}" id="{mat_id}"]'
            )
            mat_id_map[mat_name] = mat_id
            mat_id += 1

        load_steps = 1 + len(materials_used)

        # Extract actual mesh names from FBX for fuzzy matching
        fbx_mesh_names = self._extract_fbx_mesh_names(fbx_source)
        fbx_mesh_names_lower = {n.lower(): n for n in fbx_mesh_names}

        # Determine mesh type for structure and scaling
        fbx_root_name = fbx_source.stem
        # is_skinned: has skeleton structure (SK_ prefix) - affects node paths
        is_skinned = fbx_root_name.startswith('SK_')
        # is_character: already in meters, don't scale (SK_ or Character_ prefix)
        is_character = is_skinned or fbx_root_name.startswith('Character_')

        # Calculate scale factor for this asset
        scale = self._calculate_scale(fbx_source, prefab.prefab_name)

        # If Blender failed to read bounds, skip this asset
        if scale == 'skip':
            return "", None

        # Build the scene content
        content = f'[gd_scene load_steps={load_steps} format=3]\n\n'
        content += '\n'.join(ext_resources) + '\n\n'
        content += f'[node name="{prefab.prefab_name}" type="Node3D"]\n\n'

        # Model instance with scale transform if needed
        content += f'[node name="Model" parent="." instance=ExtResource("1")]\n'
        if scale is not None:
            # Apply uniform scale transform
            content += f'transform = Transform3D({scale}, 0, 0, 0, {scale}, 0, 0, 0, {scale}, 0, 0, 0)\n'
        content += '\n'

        # Apply material overrides to each child mesh node inside the instanced FBX
        # FBX structure varies:
        # - Static meshes (SM_): Model -> SM_Root -> child meshes
        # - Skinned meshes (SK_): Model -> Skeleton3D -> SK_Mesh

        # Track which nodes we've already added to avoid duplicates
        added_nodes = set()

        for mesh in prefab.meshes:
            if not mesh.slots:
                continue

            # Get the mesh name and fuzzy match to actual FBX node name
            mesh_name = mesh.mesh_name.lstrip('_')  # Remove leading underscore
            godot_name = self._fuzzy_match_mesh_name(mesh_name, fbx_mesh_names)

            # Skip if this mesh doesn't actually exist in the FBX
            # (fuzzy match returns original name if no match found)
            if godot_name.lower() not in fbx_mesh_names_lower and godot_name != fbx_root_name:
                continue

            # Skip if we've already added this node (avoid duplicates)
            if godot_name in added_nodes:
                continue
            added_nodes.add(godot_name)

            # Build material overrides for this mesh
            overrides = []

            # Check if this mesh should be hidden (redundant geometry)
            if self._should_hide_mesh(godot_name):
                overrides.append('visible = false')

            for slot_idx, slot in enumerate(mesh.slots):
                if slot.material_name in mat_id_map:
                    overrides.append(
                        f'surface_material_override/{slot_idx} = ExtResource("{mat_id_map[slot.material_name]}")'
                    )

            if overrides:
                # Determine parent path based on mesh type
                if is_skinned:
                    # SK_ meshes have different structures based on type
                    if '_Veh_' in fbx_root_name:
                        # SK_ Vehicles have same structure as SM_ when instanced:
                        # Body is root node, parts are direct children
                        if godot_name == fbx_root_name:
                            # Main body mesh - is the root node
                            content += f'[node name="{godot_name}" parent="Model"]\n'
                        else:
                            # Part meshes - direct children of root
                            content += f'[node name="{godot_name}" parent="Model/{fbx_root_name}"]\n'
                        content += '\n'.join(overrides) + '\n\n'
                    elif '_Chr_' in fbx_root_name:
                        # Characters: Model/Root/Skeleton3D/{mesh_name}
                        # The mesh is directly under Skeleton3D
                        content += f'[node name="{fbx_root_name}" parent="Model/Root/Skeleton3D"]\n'
                        content += '\n'.join(overrides) + '\n\n'
                    else:
                        # Unknown SK_ type - skip with warning
                        print(f"  Warning: Unknown SK_ type for {godot_name}, skipping material override")
                elif godot_name == fbx_root_name:
                    # Static mesh root (e.g., main car body)
                    content += f'[node name="{godot_name}" parent="Model"]\n'
                    content += '\n'.join(overrides) + '\n\n'
                else:
                    # Static mesh parts are children of the FBX root node
                    content += f'[node name="{godot_name}" parent="Model/{fbx_root_name}"]\n'
                    content += '\n'.join(overrides) + '\n\n'

        content += '[node name="StaticBody3D" type="StaticBody3D" parent="."]\n\n'
        content += '[node name="CollisionShape3D" type="CollisionShape3D" parent="StaticBody3D"]\n'

        return content, fbx_source

    def _is_generic_prefab(self, prefab: PrefabInfo) -> bool:
        """Check if prefab is a shared generic asset (SM_Gen_*, SM_Generic_*, etc.)."""
        name = prefab.prefab_name
        # Generic prefab patterns
        return (
            name.startswith('SM_Gen_') or
            name.startswith('SM_Generic_') or
            name.startswith('SK_Gen_') or
            prefab.category == 'Generic'
        )

    def _generic_prefab_exists(self, prefab: PrefabInfo, config: Config) -> bool:
        """Check if generic prefab already exists in any pack's folder."""
        synty_dir = config.project_root / "assets" / "synty"
        if not synty_dir.exists():
            return False

        prefab_filename = f"{prefab.prefab_name}.tscn"
        category = prefab.category or "Props"

        for pack_dir in synty_dir.iterdir():
            if not pack_dir.is_dir():
                continue
            existing = pack_dir / "Prefabs" / category / prefab_filename
            if existing.exists():
                return True
        return False

    def write_prefab(
        self,
        prefab: PrefabInfo,
        config: Config,
        valid_materials: set[str] | None = None
    ) -> tuple[Path | None, Path | None, bool]:
        """
        Write prefab .tscn file and copy FBX to models folder.

        Returns:
            - tscn output path (or None)
            - model output path (or None)
            - True if this was a generic prefab that already existed (skipped)
        """
        is_generic = self._is_generic_prefab(prefab)

        # For generic prefabs, check if already exists in any pack
        if is_generic and self._generic_prefab_exists(prefab, config):
            return None, None, True  # Already exists, skip

        # Generate content (always use current pack's paths for materials)
        content, fbx_source = self.generate(prefab, config, valid_materials)
        if not content or not fbx_source:
            return None, None, False

        # Write prefab to current pack
        category_dir = config.prefabs_dir / (prefab.category or "Props")
        category_dir.mkdir(parents=True, exist_ok=True)
        tscn_path = category_dir / f"{prefab.prefab_name}.tscn"
        tscn_path.write_text(content, encoding='utf-8')

        # Copy FBX to models folder
        model_category_dir = config.models_dir / (prefab.category or "Props")
        model_category_dir.mkdir(parents=True, exist_ok=True)
        model_path = model_category_dir / fbx_source.name
        if not model_path.exists():
            shutil.copy2(fbx_source, model_path)

        return tscn_path, model_path, False


# ============================================================================
# Texture Copier
# ============================================================================

class TextureCopier:
    """Copies required textures to the output folder."""

    def __init__(self):
        # Maps material texture_name -> actual copied filename
        self.texture_filename_map: dict[str, str] = {}
        # Maps base texture_name -> emissive texture filename
        self.emissive_texture_map: dict[str, str] = {}

    def _find_emissive_texture(self, textures_dir: Path, base_tex_name: str) -> Path | None:
        """
        Find an emissive texture that corresponds to a base texture.

        Patterns handled:
        1. PolygonPack_Texture_01 -> PolygonPack_Emissive_01_A (replaces Texture_ with Emissive_, adds _A)
        2. PolygonPack_Texture_01_A -> PolygonPack_Emissive_01_A (replaces Texture_ with Emissive_)
        3. PolygonPack_Texture_01_A -> PolygonPack_01_A_Emissive (removes Texture_, adds _Emissive)
        4. Wall_01 -> Wall_01_Emissive (appends _Emissive)
        """
        extensions = ['.png', '.tga', '.jpg']
        search_dirs = [textures_dir / "Emissive", textures_dir]

        # Pattern 1: Replace "_Texture_" with "_Emissive_", try adding _A suffix for base names without variant
        # PolygonNatureBiomesS2_Texture_01 -> PolygonNatureBiomesS2_Emissive_01_A
        if '_Texture_' in base_tex_name:
            emissive_base = base_tex_name.replace('_Texture_', '_Emissive_')
            # Check if base name already has a variant suffix like _A, _B, _C
            has_variant = re.search(r'_[A-C]$', emissive_base)

            for search_dir in search_dirs:
                if not search_dir.exists():
                    continue
                for ext in extensions:
                    if has_variant:
                        # Direct replacement (Texture_01_A -> Emissive_01_A)
                        for pattern in [f"{emissive_base}{ext}", f"**/{emissive_base}{ext}"]:
                            matches = list(search_dir.glob(pattern))
                            if matches:
                                return matches[0]
                    else:
                        # Add _A variant suffix as default (Texture_01 -> Emissive_01_A)
                        emissive_with_variant = f"{emissive_base}_A"
                        for pattern in [f"{emissive_with_variant}{ext}", f"**/{emissive_with_variant}{ext}"]:
                            matches = list(search_dir.glob(pattern))
                            if matches:
                                return matches[0]
                        # Also try without variant suffix
                        for pattern in [f"{emissive_base}{ext}", f"**/{emissive_base}{ext}"]:
                            matches = list(search_dir.glob(pattern))
                            if matches:
                                return matches[0]

        # Pattern 2: Remove "_Texture_" and append "_Emissive"
        # PolygonCyberCity_Texture_01_A -> PolygonCyberCity_01_A_Emissive
        if '_Texture_' in base_tex_name:
            emissive_name = base_tex_name.replace('_Texture_', '_') + '_Emissive'
            for search_dir in search_dirs:
                if not search_dir.exists():
                    continue
                for ext in extensions:
                    for pattern in [f"{emissive_name}{ext}", f"**/{emissive_name}{ext}"]:
                        matches = list(search_dir.glob(pattern))
                        if matches:
                            return matches[0]

        # Pattern 3: Simple append "_Emissive"
        # Wall_01 -> Wall_01_Emissive
        emissive_name = f"{base_tex_name}_Emissive"
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            for ext in extensions:
                for pattern in [f"{emissive_name}{ext}", f"**/{emissive_name}{ext}"]:
                    matches = list(search_dir.glob(pattern))
                    if matches:
                        return matches[0]

        # Pattern 4: Prefix with "Emissive_" (for simple numbered textures)
        # Texture_01 -> Emissive_01
        if base_tex_name.startswith('Texture_'):
            emissive_name = 'Emissive_' + base_tex_name[8:]
            for search_dir in search_dirs:
                if not search_dir.exists():
                    continue
                for ext in extensions:
                    for pattern in [f"{emissive_name}{ext}", f"**/{emissive_name}{ext}"]:
                        matches = list(search_dir.glob(pattern))
                        if matches:
                            return matches[0]

        return None

    def _find_texture_recursive(self, textures_dir: Path, tex_name: str) -> Path | None:
        """Search for a texture file recursively in the textures directory."""

        def is_normal_map(filename: str) -> bool:
            """Check if filename is a normal map (should never be used as albedo)."""
            lower = filename.lower()
            return any(p in lower for p in ['_normal', '_normals', '_normalmap', '_n.'])

        def is_water_texture(filename: str) -> bool:
            """Check if filename is a water texture."""
            return 'water' in filename.lower()

        def score_match(candidate_stem: str, target_name: str) -> int:
            """
            Score texture match quality. Negative = excluded.
            Higher scores = better matches.
            """
            lower_cand = candidate_stem.lower()
            lower_target = target_name.lower()

            # Exclusions return negative scores
            if is_normal_map(candidate_stem):
                return -1000
            if is_water_texture(candidate_stem) and not is_water_texture(target_name):
                return -50

            # Scoring (higher = better match)
            if lower_cand == lower_target:
                return 100  # Exact match
            if lower_cand.startswith(lower_target + '_'):
                return 90   # Exact + suffix (Grass_01 -> Grass_01_TGA)
            if lower_cand.startswith(lower_target):
                return 80   # Target is prefix
            if lower_target in lower_cand:
                return 70   # Contains target

            # Try comparing without underscores (Bamboo_Leaf_01 vs BambooLeaf_01)
            cand_no_underscore = lower_cand.replace('_', '')
            target_no_underscore = lower_target.replace('_', '')
            if cand_no_underscore == target_no_underscore:
                return 95  # Match ignoring underscores
            if cand_no_underscore.startswith(target_no_underscore):
                return 75  # Prefix match ignoring underscores
            if target_no_underscore in cand_no_underscore:
                return 65  # Contains match ignoring underscores

            # Name part overlap
            target_parts = set(p for p in lower_target.split('_') if len(p) > 2)
            cand_parts = set(p for p in lower_cand.split('_') if len(p) > 2)
            overlap = len(target_parts & cand_parts)
            if overlap >= 2:
                return 30 + overlap * 5

            return 0  # No meaningful match

        # Prefer TGA (usually has alpha for cutout) over PNG
        extensions = ['.tga', '.png', '.jpg']

        # Step 1: Try direct exact match first, including _TGA suffix (prefer TGA)
        for ext in extensions:
            # Check with _TGA suffix first (better alpha)
            direct_tga = textures_dir / f"{tex_name}_TGA{ext}"
            if direct_tga.exists() and not is_normal_map(direct_tga.stem):
                return direct_tga
            # Then exact name
            direct = textures_dir / f"{tex_name}{ext}"
            if direct.exists() and not is_normal_map(direct.stem):
                return direct

        # Step 2: Search recursively for exact name match (with _TGA priority)
        for ext in extensions:
            # Try _TGA suffix first
            pattern_tga = f"**/{tex_name}_TGA{ext}"
            matches = list(textures_dir.glob(pattern_tga))
            for m in matches:
                if not is_normal_map(m.stem):
                    return m
            # Then exact name
            pattern = f"**/{tex_name}{ext}"
            matches = list(textures_dir.glob(pattern))
            for m in matches:
                if not is_normal_map(m.stem):
                    return m

        # Step 3: Search with other common suffixes
        for ext in extensions:
            for suffix in ['_01', '']:
                if suffix:  # Skip empty suffix (already checked above)
                    pattern = f"**/{tex_name}{suffix}{ext}"
                    matches = list(textures_dir.glob(pattern))
                    for m in matches:
                        if not is_normal_map(m.stem):
                            return m

        # Fallback Steps 4-6: Fuzzy matching cascade
        # Each step tries progressively looser patterns if previous steps found nothing
        all_candidates = []

        # Step 4: Try patterns containing the full texture name
        for ext in extensions:
            pattern = f"**/*{tex_name}*{ext}"
            matches = list(textures_dir.glob(pattern))
            for m in matches:
                score = score_match(m.stem, tex_name)
                if score > 0:
                    all_candidates.append((score, m))

        if all_candidates:
            all_candidates.sort(key=lambda x: x[0], reverse=True)
            return all_candidates[0][1]

        # Step 5: Try simplified name (remove number suffixes like _01, _02)
        simplified = re.sub(r'_\d+(?=_|$)', '', tex_name)
        if simplified != tex_name:
            for ext in extensions:
                pattern = f"**/*{simplified}*{ext}"
                matches = list(textures_dir.glob(pattern))
                for m in matches:
                    score = score_match(m.stem, simplified)
                    if score > 0:
                        all_candidates.append((score, m))

            if all_candidates:
                all_candidates.sort(key=lambda x: x[0], reverse=True)
                return all_candidates[0][1]

        # Step 6: Try matching key name parts (first 2 significant parts)
        parts = [p for p in tex_name.split('_') if len(p) > 2 and not p.isdigit()]
        if len(parts) >= 2:
            key_parts = parts[:2]
            for ext in extensions:
                pattern = f"**/*{'*'.join(key_parts)}*{ext}"
                matches = list(textures_dir.glob(pattern))
                for m in matches:
                    score = score_match(m.stem, tex_name)
                    if score > 0:
                        all_candidates.append((score, m))

            if all_candidates:
                all_candidates.sort(key=lambda x: x[0], reverse=True)
                return all_candidates[0][1]

        return None

    def copy_textures(
        self,
        materials: dict[str, MaterialInfo],
        config: Config
    ) -> list[Path]:
        """Copy all textures referenced by materials."""
        copied = []
        not_found = []
        config.textures_dir.mkdir(parents=True, exist_ok=True)

        texture_names = set()
        for mat in materials.values():
            if mat.texture_name:
                texture_names.add(mat.texture_name)
            if mat.trunk_texture_name:
                texture_names.add(mat.trunk_texture_name)

        # Check both Textures subfolder and root source folder
        textures_source = config.source_dir / "Textures"
        for tex_name in sorted(texture_names):
            src = self._find_texture_recursive(textures_source, tex_name)
            # Also check root source folder if not found in Textures subfolder
            if not src:
                src = self._find_texture_recursive(config.source_dir, tex_name)
            if src:
                dst = config.textures_dir / src.name
                if not dst.exists():
                    shutil.copy2(src, dst)
                copied.append(dst)
                # Store mapping from texture_name to actual filename
                self.texture_filename_map[tex_name] = src.name
            else:
                not_found.append(tex_name)

        if not_found:
            print(f"  Warning: {len(not_found)} textures not found")
            for name in not_found[:5]:
                print(f"    - {name}")
            if len(not_found) > 5:
                print(f"    ... and {len(not_found) - 5} more")

        # Discover and copy emissive textures
        emissive_count = 0
        for mat in materials.values():
            if not mat.texture_name:
                continue

            emissive_src = self._find_emissive_texture(textures_source, mat.texture_name)
            if emissive_src:
                dst = config.textures_dir / emissive_src.name
                if not dst.exists():
                    shutil.copy2(emissive_src, dst)
                    copied.append(dst)
                # Update material with emission texture name
                mat.emission_texture_name = emissive_src.stem
                self.emissive_texture_map[mat.texture_name] = emissive_src.name
                emissive_count += 1

        if emissive_count > 0:
            print(f"  Found {emissive_count} emissive textures")

        return copied


# ============================================================================
# Main Converter
# ============================================================================

class SyntyConverter:
    """Main converter orchestrating the conversion process."""

    def __init__(self, config: Config, normalize_height: float | None = None):
        """
        Initialize SyntyConverter.

        Args:
            config: Converter configuration.
            normalize_height: Optional target height in meters for normalized scaling.
                              If provided, assets will be scaled so their height matches
                              this value. Requires Blender to be installed.
        """
        self.config = config
        self.parser = MaterialListParser()
        self.material_gen = MaterialGenerator()
        self.texture_copier = TextureCopier()

        # Set up height normalization if requested
        self._normalize_height = normalize_height
        self._bounds_reader = None

        if normalize_height is not None:
            self._bounds_reader = FBXBoundsReader()
            if not self._bounds_reader.available:
                print("Warning: Size normalization requested but Blender not found.")
                print("         Falling back to fixed category-based scaling.")
                self._bounds_reader = None
                self._normalize_height = None
            else:
                print(f"Size normalization enabled: target = {normalize_height}m (uses max dimension)")
                print(f"  Using Blender: {self._bounds_reader.blender_path}")

        self.prefab_gen = PrefabGenerator(
            fbx_bounds_reader=self._bounds_reader,
            normalize_height=self._normalize_height
        )

    def convert(self, dry_run: bool = False, name_filter: str | None = None) -> dict:
        """
        Run the conversion process.

        Returns:
            Summary statistics
        """
        stats = {
            'prefabs': 0,
            'materials': 0,
            'textures': 0,
            'models': 0,
            'skipped': [],
            'errors': [],
        }

        # Step 1: Parse MaterialList (try source directory first, then zip)
        print("Parsing MaterialList...")
        try:
            # Try source directory first (MaterialList files extracted there)
            prefabs, materials = self.parser.parse_from_directory(self.config.source_dir)
        except FileNotFoundError:
            # Fall back to zip file
            print("  Not found in source dir, trying zip file...")
            try:
                prefabs, materials = self.parser.parse_from_zip(
                    self.config.zip_path,
                    "MaterialList"
                )
            except FileNotFoundError as e:
                stats['errors'].append(str(e))
                return stats

        print(f"  Found {len(prefabs)} prefabs, {len(materials)} unique materials")

        # Apply name filter if provided
        if name_filter:
            filter_lower = name_filter.lower()
            prefabs = [p for p in prefabs if filter_lower in p.prefab_name.lower()]
            materials = {k: v for k, v in materials.items() if filter_lower in k.lower() or any(filter_lower in p.prefab_name.lower() for p in prefabs if any(m.material_name == k for mesh in p.meshes for m in mesh.slots))}
            print(f"  After filter '{name_filter}': {len(prefabs)} prefabs, {len(materials)} materials")

        if dry_run:
            print("\n[DRY RUN] Would create:")
            print("\nMaterials:")
            for mat in materials.values():
                mat_type = self.material_gen._detect_material_type(mat)
                print(f"  - {mat.material_name} ({mat_type})")
            print("\nPrefabs:")
            for prefab in prefabs:
                fbx = self.prefab_gen._find_fbx_file(prefab, self.config)
                status = "OK" if fbx else "MISSING FBX"
                print(f"  - {prefab.category}/{prefab.prefab_name} [{status}]")
            return stats

        # Step 2: Copy textures
        print("\nCopying textures...")
        copied_textures = self.texture_copier.copy_textures(materials, self.config)
        stats['textures'] = len(copied_textures)
        for tex in copied_textures:
            print(f"  Copied: {tex.name}")

        # Step 3: Generate materials (only for those with valid textures or special types)
        print("\nGenerating materials...")
        texture_map = self.texture_copier.texture_filename_map
        valid_materials = set()  # Track materials that can be created

        # Materials that don't need textures (use color/procedural shaders)
        def needs_texture(mat: MaterialInfo) -> bool:
            if mat.is_glass:
                return False
            name_lower = mat.material_name.lower()
            # Water materials use color-based shader
            if any(x in name_lower for x in ['water', 'ocean', 'river', 'lake', 'pond']):
                return False
            # Gems/crystals/jewels/geodes use refractive shader (color-based, emission optional)
            if any(x in name_lower for x in ['gem', 'crystal', 'jewel', 'geode']):
                return False
            return True

        for mat in materials.values():
            # Skip materials with missing textures (except those that don't need textures)
            if needs_texture(mat) and mat.texture_name and mat.texture_name not in texture_map:
                print(f"  Skipped: {mat.material_name} (texture not found: {mat.texture_name})")
                continue

            try:
                path = self.material_gen.write_material(mat, self.config, texture_map)
                stats['materials'] += 1
                valid_materials.add(mat.material_name)
                mat_type = self.material_gen._detect_material_type(mat)
                print(f"  Created: {path.name} ({mat_type})")
            except Exception as e:
                stats['errors'].append(f"Material {mat.material_name}: {e}")

        # Step 4: Generate prefabs
        print("\nGenerating prefabs...")
        # Prefab name patterns to skip (FX/effects that need custom shaders)
        skip_patterns = [
            'FX_', 'LightRay_', 'WeatherControl', 'SyntyWeather',
            # Enchanted Forest FX prefabs
            'SM_Env_Cloud_', 'SM_Env_Fog_', 'SM_Env_Skydome_', 'SM_Env_Grass_01',
        ]

        for prefab in prefabs:
            # Skip effect prefabs that won't work without custom shaders
            if any(prefab.prefab_name.startswith(p) or prefab.prefab_name == p for p in skip_patterns):
                stats['skipped'].append(prefab.prefab_name)
                print(f"  Skipped: {prefab.prefab_name} (FX/effect)")
                continue

            # Skip collision mesh prefabs (Godot can auto-generate collision)
            if '_Collision' in prefab.prefab_name:
                stats['skipped'].append(prefab.prefab_name)
                continue

            try:
                tscn_path, model_path, was_generic_duplicate = self.prefab_gen.write_prefab(
                    prefab, self.config, valid_materials
                )
                if was_generic_duplicate:
                    # Generic prefab already exists in another pack, skip silently
                    continue
                if tscn_path:
                    stats['prefabs'] += 1
                    print(f"  Created: {prefab.category}/{prefab.prefab_name}.tscn")
                else:
                    stats['skipped'].append(prefab.prefab_name)
                    print(f"  Skipped: {prefab.prefab_name} (no FBX found)")
                if model_path:
                    stats['models'] += 1
            except Exception as e:
                stats['errors'].append(f"Prefab {prefab.prefab_name}: {e}")

        return stats


# ============================================================================
# CLI Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Convert Synty FBX source files to Godot-native format'
    )
    parser.add_argument(
        '--pack', '-p',
        default='POLYGON_Explorer_Kit',
        help='Pack name (default: POLYGON_Explorer_Kit)'
    )
    parser.add_argument(
        '--source', '-s',
        type=Path,
        required=True,
        help='Source directory with extracted Synty files (required)'
    )
    parser.add_argument(
        '--zip', '-z',
        type=Path,
        default=None,
        help='Source zip file (optional, for MaterialList fallback)'
    )
    parser.add_argument(
        '--project', '-r',
        type=Path,
        required=True,
        help='Godot project root directory (required)'
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Preview without writing files'
    )
    parser.add_argument(
        '--filter', '-f',
        type=str,
        default=None,
        help='Filter prefabs/materials by name (e.g., "Cherry_Blossom" to only process cherry blossom assets)'
    )
    parser.add_argument(
        '--normalize-size', '--normalize-height',
        type=float,
        default=2.0,
        dest='normalize_size',
        metavar='METERS',
        help='Normalize all assets to this size in meters using largest dimension (default: 2.0).'
    )

    args = parser.parse_args()

    # Use zip path if provided, otherwise use a placeholder
    zip_path = args.zip if args.zip else args.source / "placeholder.zip"

    config = Config(
        zip_path=zip_path,
        source_dir=args.source,
        project_root=args.project,
        pack_name=args.pack,
    )

    print("=" * 60)
    print("SYNTY TO GODOT CONVERTER")
    print("=" * 60)
    print(f"Pack: {config.pack_name}")
    print(f"Source: {config.source_dir}")
    print(f"Zip: {config.zip_path}")
    print(f"Output: {config.output_dir}")
    print("=" * 60)

    converter = SyntyConverter(config, normalize_height=args.normalize_size)
    stats = converter.convert(dry_run=args.dry_run, name_filter=args.filter)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Textures copied: {stats['textures']}")
    print(f"Materials created: {stats['materials']}")
    print(f"Models copied: {stats['models']}")
    print(f"Prefabs created: {stats['prefabs']}")

    if stats['skipped']:
        print(f"\nSkipped ({len(stats['skipped'])}):")
        for name in stats['skipped']:
            print(f"  - {name}")

    if stats['errors']:
        print(f"\nErrors ({len(stats['errors'])}):")
        for err in stats['errors']:
            print(f"  - {err}")

    print("\nDone!")


if __name__ == '__main__':
    main()
