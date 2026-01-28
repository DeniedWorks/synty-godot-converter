"""Generate Godot ShaderMaterial .tres files."""

from pathlib import Path
from typing import Optional
import logging

from ..config import MaterialType, ConversionConfig, SHADER_FILES
from ..extractors.unity_package import MaterialInfo

logger = logging.getLogger(__name__)


class MaterialGenerator:
    """Generate Godot ShaderMaterial resource files."""

    def __init__(self, config: ConversionConfig):
        self.config = config

    def generate(
        self,
        material_name: str,
        material_type: MaterialType,
        material_info: Optional[MaterialInfo] = None,
        texture_map: Optional[dict[str, str]] = None
    ) -> str:
        """
        Generate a .tres ShaderMaterial file content.

        Args:
            material_name: Name of the material
            material_type: Type classification
            material_info: Optional Unity material metadata
            texture_map: Optional dict of texture type -> filename

        Returns:
            String content of the .tres file
        """
        shader_file = SHADER_FILES.get(material_type, SHADER_FILES[MaterialType.STANDARD])
        shader_path = f"res://assets/shaders/synty/{shader_file}"

        # Build texture map from material_info if available
        if texture_map is None:
            texture_map = {}

        if material_info and material_info.resolved_textures:
            texture_map = self._build_texture_map(material_info)

        # Generate based on material type
        generators = {
            MaterialType.STANDARD: self._generate_standard,
            MaterialType.FOLIAGE: self._generate_foliage,
            MaterialType.WATER: self._generate_water,
            MaterialType.GLASS: self._generate_glass,
            MaterialType.EMISSIVE: self._generate_emissive,
            MaterialType.SKY: self._generate_sky,
            MaterialType.CLOUDS: self._generate_clouds,
            MaterialType.PARTICLES: self._generate_particles,
        }

        generator = generators.get(material_type, self._generate_standard)
        return generator(material_name, shader_path, texture_map, material_info)

    def _build_texture_map(self, mat_info: MaterialInfo) -> dict[str, str]:
        """Build texture map from MaterialInfo resolved textures."""
        texture_map = {}
        resolved = mat_info.resolved_textures

        # Map Unity property names to our generic names
        mappings = {
            "_Albedo_Map": "albedo",
            "_MainTex": "albedo",
            "_Leaf_Texture": "leaf",
            "_Trunk_Texture": "trunk",
            "_Emission_Map": "emission",
            "_Normal_Map": "normal",
            "_BumpMap": "normal",
            "_Metallic_Map": "metallic",
            "_Roughness_Map": "roughness",
        }

        for unity_prop, generic_name in mappings.items():
            if unity_prop in resolved:
                texture_map[generic_name] = resolved[unity_prop]

        return texture_map

    def _get_texture_path(self, filename: str) -> str:
        """Get the res:// path for a texture file."""
        return f"res://{self.config.textures_dir.relative_to(self.config.godot_project_path).as_posix()}/{filename}"

    def _generate_standard(
        self,
        name: str,
        shader_path: str,
        texture_map: dict[str, str],
        mat_info: Optional[MaterialInfo]
    ) -> str:
        """Generate standard polygon shader material.

        Uses polygon_shader.gdshader parameters:
        - base_texture (sampler2D)
        - color_tint (vec4)
        - metallic (float)
        - smoothness (float)
        - enable_base_texture (bool)
        """
        lines = [
            '[gd_resource type="ShaderMaterial" load_steps=3 format=3]',
            '',
            f'[ext_resource type="Shader" path="{shader_path}" id="1"]',
        ]

        # Add texture external resources
        ext_id = 2
        texture_ids = {}

        albedo_tex = texture_map.get("albedo")
        if albedo_tex:
            tex_path = self._get_texture_path(albedo_tex)
            lines.append(f'[ext_resource type="Texture2D" path="{tex_path}" id="{ext_id}"]')
            texture_ids["albedo"] = ext_id
            ext_id += 1

        normal_tex = texture_map.get("normal")
        if normal_tex:
            tex_path = self._get_texture_path(normal_tex)
            lines.append(f'[ext_resource type="Texture2D" path="{tex_path}" id="{ext_id}"]')
            texture_ids["normal"] = ext_id
            ext_id += 1

        # Build shader params
        lines.append('')
        lines.append('[resource]')
        lines.append('shader = ExtResource("1")')

        # Base texture parameters (matching polygon_shader.gdshader)
        lines.append('shader_parameter/enable_base_texture = true')
        if "albedo" in texture_ids:
            lines.append(f'shader_parameter/base_texture = ExtResource("{texture_ids["albedo"]}")')

        # Normal texture
        if "normal" in texture_ids:
            lines.append('shader_parameter/enable_normal_texture = true')
            lines.append(f'shader_parameter/normal_texture = ExtResource("{texture_ids["normal"]}")')
            lines.append('shader_parameter/normal_intensity = 1.0')
        else:
            lines.append('shader_parameter/enable_normal_texture = false')

        # Default parameters for polygon shader
        lines.append('shader_parameter/color_tint = Color(1, 1, 1, 1)')
        lines.append('shader_parameter/metallic = 0.0')
        lines.append('shader_parameter/smoothness = 0.5')

        # Tiling and offset defaults
        lines.append('shader_parameter/base_tiling = Vector2(1, 1)')
        lines.append('shader_parameter/base_offset = Vector2(0, 0)')

        return '\n'.join(lines)

    def _generate_foliage(
        self,
        name: str,
        shader_path: str,
        texture_map: dict[str, str],
        mat_info: Optional[MaterialInfo]
    ) -> str:
        """Generate foliage shader material with wind parameters.

        Uses foliage.gdshader parameters:
        - leaf_color (sampler2D)
        - trunk_color (sampler2D)
        - leaf_base_color (vec4)
        - trunk_base_color (vec4)
        - enable_breeze, enable_light_wind, etc.
        """
        lines = [
            '[gd_resource type="ShaderMaterial" load_steps=4 format=3]',
            '',
            f'[ext_resource type="Shader" path="{shader_path}" id="1"]',
        ]

        ext_id = 2
        texture_ids = {}

        # Leaf texture
        leaf_tex = texture_map.get("leaf") or texture_map.get("albedo")
        if leaf_tex:
            tex_path = self._get_texture_path(leaf_tex)
            lines.append(f'[ext_resource type="Texture2D" path="{tex_path}" id="{ext_id}"]')
            texture_ids["leaf"] = ext_id
            ext_id += 1

        # Trunk texture
        trunk_tex = texture_map.get("trunk")
        if trunk_tex:
            tex_path = self._get_texture_path(trunk_tex)
            lines.append(f'[ext_resource type="Texture2D" path="{tex_path}" id="{ext_id}"]')
            texture_ids["trunk"] = ext_id
            ext_id += 1

        lines.append('')
        lines.append('[resource]')
        lines.append('shader = ExtResource("1")')

        # Leaf settings
        if "leaf" in texture_ids:
            lines.append(f'shader_parameter/leaf_color = ExtResource("{texture_ids["leaf"]}")')
        lines.append('shader_parameter/leaf_tiling = Vector2(1, 1)')
        lines.append('shader_parameter/leaf_offset = Vector2(0, 0)')
        lines.append('shader_parameter/leaf_metallic = 0.0')
        lines.append('shader_parameter/leaf_smoothness = 0.2')
        lines.append('shader_parameter/leaf_base_color = Color(1, 1, 1, 1)')

        # Trunk settings
        if "trunk" in texture_ids:
            lines.append(f'shader_parameter/trunk_color = ExtResource("{texture_ids["trunk"]}")')
        lines.append('shader_parameter/trunk_tiling = Vector2(1, 1)')
        lines.append('shader_parameter/trunk_offset = Vector2(0, 0)')
        lines.append('shader_parameter/trunk_metallic = 0.0')
        lines.append('shader_parameter/trunk_smoothness = 0.2')
        lines.append('shader_parameter/trunk_base_color = Color(1, 1, 1, 1)')

        # Wind parameters (matching foliage.gdshader)
        lines.append('shader_parameter/use_global_weather_controller = true')
        lines.append('shader_parameter/enable_breeze = true')
        lines.append('shader_parameter/breeze_strength = 0.2')
        lines.append('shader_parameter/enable_light_wind = true')
        lines.append('shader_parameter/light_wind_strength = 0.2')
        lines.append('shader_parameter/light_wind_y_strength = 1.0')
        lines.append('shader_parameter/light_wind_y_offset = 0.0')
        lines.append('shader_parameter/enable_strong_wind = false')
        lines.append('shader_parameter/strong_wind_strength = 0.2')

        # Extract wind params from Unity if available
        if mat_info:
            if mat_info.floats.get("_Breeze_Strength"):
                lines.append(f'shader_parameter/breeze_strength = {mat_info.floats["_Breeze_Strength"]}')
            if mat_info.floats.get("_Light_Wind_Strength"):
                lines.append(f'shader_parameter/light_wind_strength = {mat_info.floats["_Light_Wind_Strength"]}')

        return '\n'.join(lines)

    def _generate_water(
        self,
        name: str,
        shader_path: str,
        texture_map: dict[str, str],
        mat_info: Optional[MaterialInfo]
    ) -> str:
        """Generate water shader material."""
        lines = [
            '[gd_resource type="ShaderMaterial" load_steps=2 format=3]',
            '',
            f'[ext_resource type="Shader" path="{shader_path}" id="1"]',
            '',
            '[resource]',
            'shader = ExtResource("1")',
            # Water shader parameters will vary by shader implementation
            'shader_parameter/water_color = Color(0.1, 0.3, 0.5, 0.8)',
            'shader_parameter/deep_water_color = Color(0.0, 0.1, 0.2, 1.0)',
            'shader_parameter/wave_speed = 1.0',
            'shader_parameter/wave_strength = 0.1',
            'shader_parameter/foam_strength = 0.5',
        ]

        return '\n'.join(lines)

    def _generate_glass(
        self,
        name: str,
        shader_path: str,
        texture_map: dict[str, str],
        mat_info: Optional[MaterialInfo]
    ) -> str:
        """Generate glass/transparent shader material.

        Uses refractive_transparent.gdshader
        """
        lines = [
            '[gd_resource type="ShaderMaterial" load_steps=2 format=3]',
            '',
            f'[ext_resource type="Shader" path="{shader_path}" id="1"]',
            '',
            '[resource]',
            'render_priority = 1',
            'shader = ExtResource("1")',
            'shader_parameter/albedo_color = Color(0.9, 0.95, 1.0, 0.3)',
            'shader_parameter/fresnel_power = 3.0',
            'shader_parameter/fresnel_opacity = 0.8',
            'shader_parameter/refraction_strength = 0.05',
            'shader_parameter/roughness = 0.1',
        ]

        return '\n'.join(lines)

    def _generate_emissive(
        self,
        name: str,
        shader_path: str,
        texture_map: dict[str, str],
        mat_info: Optional[MaterialInfo]
    ) -> str:
        """Generate emissive material using polygon_shader with emission enabled."""
        # Use polygon shader with emission enabled instead of glass shader
        shader_path = f"res://assets/shaders/synty/polygon_shader.gdshader"

        lines = [
            '[gd_resource type="ShaderMaterial" load_steps=4 format=3]',
            '',
            f'[ext_resource type="Shader" path="{shader_path}" id="1"]',
        ]

        ext_id = 2
        texture_ids = {}

        # Albedo texture
        albedo_tex = texture_map.get("albedo")
        if albedo_tex:
            tex_path = self._get_texture_path(albedo_tex)
            lines.append(f'[ext_resource type="Texture2D" path="{tex_path}" id="{ext_id}"]')
            texture_ids["albedo"] = ext_id
            ext_id += 1

        # Emission texture
        emission_tex = texture_map.get("emission")
        if emission_tex:
            tex_path = self._get_texture_path(emission_tex)
            lines.append(f'[ext_resource type="Texture2D" path="{tex_path}" id="{ext_id}"]')
            texture_ids["emission"] = ext_id
            ext_id += 1

        lines.append('')
        lines.append('[resource]')
        lines.append('shader = ExtResource("1")')

        # Base texture
        lines.append('shader_parameter/enable_base_texture = true')
        if "albedo" in texture_ids:
            lines.append(f'shader_parameter/base_texture = ExtResource("{texture_ids["albedo"]}")')

        # Emission settings (polygon_shader supports emission)
        lines.append('shader_parameter/enable_emission_texture = true')
        if "emission" in texture_ids:
            lines.append(f'shader_parameter/emission_texture = ExtResource("{texture_ids["emission"]}")')

        # Get emission color from Unity material
        emission_color = "Color(1.0, 0.8, 0.4, 1.0)"  # Default warm glow
        if mat_info and "_Emission_Color" in mat_info.colors:
            c = mat_info.colors["_Emission_Color"]
            emission_color = f"Color({c[0]}, {c[1]}, {c[2]}, {c[3]})"

        lines.append(f'shader_parameter/emission_color_tint = {emission_color}')
        lines.append('shader_parameter/color_tint = Color(1, 1, 1, 1)')
        lines.append('shader_parameter/metallic = 0.0')
        lines.append('shader_parameter/smoothness = 0.5')

        return '\n'.join(lines)

    def _generate_sky(
        self,
        name: str,
        shader_path: str,
        texture_map: dict[str, str],
        mat_info: Optional[MaterialInfo]
    ) -> str:
        """Generate sky dome shader material."""
        lines = [
            '[gd_resource type="ShaderMaterial" load_steps=2 format=3]',
            '',
            f'[ext_resource type="Shader" path="{shader_path}" id="1"]',
            '',
            '[resource]',
            'shader = ExtResource("1")',
            'shader_parameter/sky_top_color = Color(0.4, 0.6, 1.0, 1.0)',
            'shader_parameter/sky_horizon_color = Color(0.8, 0.85, 0.95, 1.0)',
            'shader_parameter/sun_color = Color(1.0, 0.95, 0.8, 1.0)',
        ]

        return '\n'.join(lines)

    def _generate_clouds(
        self,
        name: str,
        shader_path: str,
        texture_map: dict[str, str],
        mat_info: Optional[MaterialInfo]
    ) -> str:
        """Generate clouds shader material."""
        lines = [
            '[gd_resource type="ShaderMaterial" load_steps=2 format=3]',
            '',
            f'[ext_resource type="Shader" path="{shader_path}" id="1"]',
            '',
            '[resource]',
            'shader = ExtResource("1")',
            'shader_parameter/cloud_color = Color(1.0, 1.0, 1.0, 0.8)',
            'shader_parameter/cloud_speed = 0.01',
            'shader_parameter/cloud_density = 0.5',
        ]

        return '\n'.join(lines)

    def _generate_particles(
        self,
        name: str,
        shader_path: str,
        texture_map: dict[str, str],
        mat_info: Optional[MaterialInfo]
    ) -> str:
        """Generate particles unlit shader material."""
        lines = [
            '[gd_resource type="ShaderMaterial" load_steps=3 format=3]',
            '',
            f'[ext_resource type="Shader" path="{shader_path}" id="1"]',
        ]

        ext_id = 2
        albedo_tex = texture_map.get("albedo")
        if albedo_tex:
            tex_path = self._get_texture_path(albedo_tex)
            lines.append(f'[ext_resource type="Texture2D" path="{tex_path}" id="{ext_id}"]')
            ext_id += 1

        lines.append('')
        lines.append('[resource]')
        lines.append('shader = ExtResource("1")')

        if albedo_tex:
            lines.append('shader_parameter/albedo_texture = ExtResource("2")')

        lines.append('shader_parameter/albedo_color = Color(1.0, 1.0, 1.0, 1.0)')

        return '\n'.join(lines)

    def write_material(
        self,
        material_name: str,
        material_type: MaterialType,
        material_info: Optional[MaterialInfo] = None,
        texture_map: Optional[dict[str, str]] = None
    ) -> Path:
        """Generate and write a material file."""
        content = self.generate(material_name, material_type, material_info, texture_map)

        # Clean material name for filename
        safe_name = self._sanitize_filename(material_name)
        output_path = self.config.materials_dir / f"{safe_name}.tres"

        if not self.config.dry_run:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content, encoding='utf-8')
            logger.info(f"Wrote material: {output_path}")
        else:
            logger.info(f"[DRY RUN] Would write material: {output_path}")

        return output_path

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize a name for use as filename."""
        # Remove or replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '_')
        return name
