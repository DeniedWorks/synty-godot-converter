"""Configuration for Synty Converter v2."""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum, auto


class MaterialType(Enum):
    """Material type classification."""
    STANDARD = auto()
    FOLIAGE = auto()
    EMISSIVE = auto()
    GLASS = auto()
    WATER = auto()
    SKY = auto()
    CLOUDS = auto()
    PARTICLES = auto()


@dataclass
class ConversionConfig:
    """Configuration for asset conversion."""

    # Source paths
    pack_name: str
    unity_package_path: Optional[Path] = None
    source_fbx_dir: Optional[Path] = None
    source_textures_dir: Optional[Path] = None

    # Output paths
    godot_project_path: Path = field(default_factory=lambda: Path.cwd())

    # Options
    dry_run: bool = False
    verbose: bool = False
    extract_meshes: bool = True

    @property
    def output_base(self) -> Path:
        """Base output directory for this pack."""
        return self.godot_project_path / "assets" / "synty" / self.pack_name

    @property
    def materials_dir(self) -> Path:
        return self.output_base / "Materials"

    @property
    def textures_dir(self) -> Path:
        return self.output_base / "Textures"

    @property
    def models_dir(self) -> Path:
        return self.output_base / "Models"

    @property
    def meshes_dir(self) -> Path:
        return self.output_base / "Meshes"

    @property
    def shaders_dir(self) -> Path:
        return self.godot_project_path / "assets" / "shaders" / "synty"


# Shader mappings
SHADER_FILES = {
    MaterialType.STANDARD: "polygon_shader.gdshader",
    MaterialType.FOLIAGE: "foliage.gdshader",
    MaterialType.WATER: "water.gdshader",
    MaterialType.GLASS: "refractive_transparent.gdshader",
    MaterialType.EMISSIVE: "refractive_transparent.gdshader",  # With emission params
    MaterialType.SKY: "sky_dome.gdshader",
    MaterialType.CLOUDS: "clouds.gdshader",
    MaterialType.PARTICLES: "particles_unlit.gdshader",
}

# Shader download URLs
SHADER_URLS = {
    "polygon_shader.gdshader": "https://godotshaders.com/shader/synty-polygon-drop-in-replacement-for-polygonshader/",
    "foliage.gdshader": "https://godotshaders.com/shader/synty-core-drop-in-foliage-shader/",
    "water.gdshader": "https://godotshaders.com/shader/synty-core-drop-in-water-shader/",
    "refractive_transparent.gdshader": "https://godotshaders.com/shader/synty-refractive_transparent-crystal-shader/",
    "clouds.gdshader": "https://godotshaders.com/shader/synty-core-drop-in-clouds-shader/",
    "sky_dome.gdshader": "https://godotshaders.com/shader/synty-polygon-drop-in-replacement-for-skydome-shader/",
    "particles_unlit.gdshader": "https://godotshaders.com/shader/synty-core-drop-in-particles-shader-generic_particlesunlit/",
    "biomes_tree.gdshader": "https://godotshaders.com/shader/synty-biomes-tree-compatible-shader/",
}

# FBX categorization patterns
FBX_CATEGORIES = {
    "Buildings": ["Bld_", "Building_", "House_", "Castle_", "Temple_", "Shrine_"],
    "Characters": ["Char_", "Character_", "NPC_", "Player_"],
    "Environment": ["Env_", "Tree_", "Rock_", "Grass_", "Plant_", "Terrain_"],
    "Props": ["Prop_", "Item_", "Weapon_", "Tool_", "Furniture_"],
    "Vehicles": ["Veh_", "Vehicle_", "Cart_", "Boat_", "Ship_"],
    "FX": ["FX_", "Particle_", "Effect_"],
}

# Texture name patterns for fuzzy matching
TEXTURE_PATTERNS = {
    "albedo": ["_Albedo", "_Color", "_Diffuse", "_BaseColor", "_D", "_01_A", "_A"],
    "normal": ["_Normal", "_N", "_Nrm", "_Bump"],
    "emission": ["_Emission", "_Emissive", "_E", "_Glow"],
    "metallic": ["_Metallic", "_M", "_Metal"],
    "roughness": ["_Roughness", "_R", "_Rough"],
    "ao": ["_AO", "_Occlusion", "_AmbientOcclusion"],
}
