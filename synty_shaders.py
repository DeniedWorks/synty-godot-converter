#!/usr/bin/env python3
"""
Synty Shaders for Godot
Bundled shader sources that get installed to target projects.

These shaders are based on work by Giancarlo Niccolai, published under MIT license.
"""

import sys
from pathlib import Path

# Shader file paths (relative to res://)
SHADER_DIR = "assets/shaders/synty"
SHADERS = {
    "polygon_shader.gdshader": "polygon",
    "foliage.gdshader": "foliage",
    "refractive_transparent.gdshader": "glass",
    "water.gdshader": "water",
}


def get_shader_source_dir() -> Path | None:
    """
    Find the shader source directory.

    When running from source, looks for shaders/ relative to this file.
    When running as bundled exe, looks in the exe's directory.
    """
    # Try PyInstaller bundled location first
    if getattr(sys, 'frozen', False):
        # Running as bundled exe
        bundle_dir = Path(sys._MEIPASS)
        shader_dir = bundle_dir / "shaders"
        if shader_dir.exists():
            return shader_dir

    # Try relative to this script (development mode) - shaders/ in same directory
    script_dir = Path(__file__).parent
    shader_dir = script_dir / "shaders"
    if shader_dir.exists():
        return shader_dir

    # Try current working directory
    cwd_shaders = Path.cwd() / "shaders"
    if cwd_shaders.exists():
        return cwd_shaders

    return None


def install_shaders(project_root: Path, log_callback=None) -> list[Path]:
    """
    Install required shaders to the target Godot project.

    Args:
        project_root: Path to the Godot project root
        log_callback: Optional function to log messages

    Returns:
        List of installed shader paths
    """
    log = log_callback or print
    installed = []

    target_dir = project_root / "assets" / "shaders" / "synty"
    target_dir.mkdir(parents=True, exist_ok=True)

    source_dir = get_shader_source_dir()

    if source_dir is None:
        log("Warning: Shader source directory not found. Using embedded minimal shaders.", "warning")
        # Install minimal fallback shaders
        for shader_name in SHADERS:
            target_path = target_dir / shader_name
            if not target_path.exists():
                content = get_minimal_shader(shader_name)
                target_path.write_text(content, encoding='utf-8')
                installed.append(target_path)
                log(f"  Installed (minimal): {shader_name}", "info")
        return installed

    # Copy shaders from source
    for shader_name in SHADERS:
        source_path = source_dir / shader_name
        target_path = target_dir / shader_name

        if target_path.exists():
            log(f"  Shader exists: {shader_name}", "info")
            continue

        if source_path.exists():
            import shutil
            shutil.copy2(source_path, target_path)
            installed.append(target_path)
            log(f"  Installed: {shader_name}", "success")
        else:
            log(f"  Warning: Source shader not found: {source_path}", "warning")

    return installed


def get_minimal_shader(shader_name: str) -> str:
    """
    Get minimal fallback shader source for when full shaders aren't available.
    These are simplified versions that will at least render the models.
    """

    if shader_name == "polygon_shader.gdshader":
        return '''\
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_disabled;

uniform vec4 color_tint : source_color = vec4(1.0);
uniform float metallic : hint_range(0.0, 1.0) = 0.0;
uniform float smoothness : hint_range(0.0, 1.0) = 0.2;
uniform bool enable_base_texture = true;
uniform sampler2D base_texture : source_color, filter_linear_mipmap;
uniform vec2 base_tiling = vec2(1.0);
uniform vec2 base_offset = vec2(0.0);
uniform bool force_opaque = false;

// Emission support
uniform bool enable_emission_texture = false;
uniform sampler2D emission_texture : source_color, filter_linear_mipmap;
uniform vec2 emission_tiling = vec2(1.0);
uniform vec2 emission_offset = vec2(0.0);
uniform vec4 emission_color_tint : source_color = vec4(1.0);

void fragment() {
    vec4 albedo = color_tint;
    if (enable_base_texture) {
        albedo *= texture(base_texture, UV * base_tiling + base_offset);
    }
    ALBEDO = albedo.rgb;
    ALPHA = force_opaque ? 1.0 : albedo.a;
    ALPHA_SCISSOR_THRESHOLD = 0.1;
    METALLIC = metallic;
    ROUGHNESS = 1.0 - smoothness;

    if (enable_emission_texture) {
        vec4 emission = texture(emission_texture, UV * emission_tiling + emission_offset);
        EMISSION = emission.rgb * emission_color_tint.rgb;
    }
}
'''

    elif shader_name == "foliage.gdshader":
        return '''\
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, depth_prepass_alpha, cull_disabled;

uniform float alpha_clip_threshold : hint_range(0.0, 1.0) = 0.25;
uniform sampler2D leaf_color : source_color, filter_linear_mipmap;
uniform vec2 leaf_tiling = vec2(1.0);
uniform vec2 leaf_offset = vec2(0.0);
uniform sampler2D trunk_color : source_color, filter_linear_mipmap;
uniform vec2 trunk_tiling = vec2(1.0);
uniform vec2 trunk_offset = vec2(0.0);

// Wind settings (simplified)
uniform bool enable_breeze = false;
uniform float breeze_strength : hint_range(0.0, 1.0) = 0.2;
uniform bool enable_light_wind = false;
uniform float light_wind_strength : hint_range(0.0, 1.0) = 0.2;

void vertex() {
    if (enable_breeze || enable_light_wind) {
        float wind = sin(TIME * 2.0 + VERTEX.x + VERTEX.z) * 0.05;
        wind *= COLOR.g * (enable_breeze ? breeze_strength : 0.0);
        wind += sin(TIME * 1.5 + VERTEX.x * 0.5) * 0.03 * COLOR.b * (enable_light_wind ? light_wind_strength : 0.0);
        VERTEX.x += wind;
        VERTEX.z += wind * 0.5;
    }
}

void fragment() {
    if (COLOR.b > 0.5) {
        vec4 tex = texture(leaf_color, UV * leaf_tiling + leaf_offset);
        ALBEDO = tex.rgb;
        ALPHA = tex.a;
    } else {
        vec4 tex = texture(trunk_color, UV * trunk_tiling + trunk_offset);
        ALBEDO = tex.rgb;
        ALPHA = 1.0;
    }
    ALPHA_SCISSOR_THRESHOLD = alpha_clip_threshold;
    ROUGHNESS = 0.8;
}
'''

    elif shader_name == "refractive_transparent.gdshader":
        return '''\
shader_type spatial;
render_mode blend_mix, depth_draw_always, cull_disabled;

uniform bool enable_triplanar = false;
uniform vec4 base_color : source_color = vec4(1.0);
uniform float metallic : hint_range(0.0, 1.0) = 0.8;
uniform float smoothness : hint_range(0.0, 1.0) = 0.9;
uniform float opacity : hint_range(0.0, 1.0) = 0.3;
uniform bool enable_fresnel = false;
uniform vec4 fresnel_color : source_color = vec4(1.0);
uniform float fresnel_border = 2.0;
uniform float fresnel_power = 3.0;

// Emission support
uniform bool enable_emission_texture = false;
uniform sampler2D emission_texture : source_color, filter_linear_mipmap;
uniform vec2 emission_tiling = vec2(1.0);
uniform vec2 emission_offset = vec2(0.0);
uniform vec4 emission_color_tint : source_color = vec4(1.0);
uniform float emission_intensity : hint_range(0.0, 10.0) = 1.0;

void fragment() {
    ALBEDO = base_color.rgb;
    ALPHA = opacity;
    METALLIC = metallic;
    ROUGHNESS = 1.0 - smoothness;

    if (enable_fresnel) {
        float fresnel = pow(1.0 - dot(NORMAL, VIEW), fresnel_power);
        ALBEDO += fresnel_color.rgb * fresnel * fresnel_border;
    }

    if (enable_emission_texture) {
        vec4 emission = texture(emission_texture, UV * emission_tiling + emission_offset);
        EMISSION = emission.rgb * emission_color_tint.rgb * emission_intensity;
    }
}
'''

    elif shader_name == "water.gdshader":
        return '''\
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back;

uniform vec4 water_color : source_color = vec4(0.2, 0.4, 0.6, 0.8);
uniform float wave_speed : hint_range(0.0, 5.0) = 1.0;
uniform float wave_strength : hint_range(0.0, 1.0) = 0.1;
uniform float smoothness : hint_range(0.0, 1.0) = 0.9;

void vertex() {
    float wave = sin(TIME * wave_speed + VERTEX.x + VERTEX.z) * wave_strength;
    VERTEX.y += wave;
}

void fragment() {
    ALBEDO = water_color.rgb;
    ALPHA = water_color.a;
    ROUGHNESS = 1.0 - smoothness;
    METALLIC = 0.0;
}
'''

    return "shader_type spatial;\nvoid fragment() { ALBEDO = vec3(1.0, 0.0, 1.0); }"


def install_import_script(project_root: Path, log_callback=None) -> Path | None:
    """Install the Godot import script for automatic collision generation."""
    import shutil
    import re
    log = log_callback or print

    target_dir = project_root / "tools"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / "synty_import_script.gd"

    # Copy script if not exists
    if not target_path.exists():
        source_path = None
        if getattr(sys, 'frozen', False):
            bundle_dir = Path(sys._MEIPASS)
            source_path = bundle_dir / "synty_import_script.gd"
        if source_path is None or not source_path.exists():
            source_path = Path(__file__).parent / "synty_import_script.gd"

        if source_path.exists():
            shutil.copy2(source_path, target_path)
            log(f"  Installed: synty_import_script.gd", "success")
        else:
            log(f"  Warning: Import script not found", "warning")
            return None

    # Update project.godot to use the import script
    project_file = project_root / "project.godot"
    if project_file.exists():
        content = project_file.read_text(encoding='utf-8')
        script_path = 'res://tools/synty_import_script.gd'

        if script_path in content:
            log(f"  project.godot already configured", "info")
        elif '"import_script/path"' in content:
            # Replace existing empty import_script/path
            content = re.sub(
                r'"import_script/path":\s*""',
                f'"import_script/path": "{script_path}"',
                content
            )
            project_file.write_text(content, encoding='utf-8')
            log(f"  Updated project.godot with import script", "success")
        elif '[importer_defaults]' in content:
            # Add to existing importer_defaults
            content = content.replace(
                'scene={',
                f'scene={{\n"import_script/path": "{script_path}",',
                1
            )
            project_file.write_text(content, encoding='utf-8')
            log(f"  Added import script to project.godot", "success")
        else:
            log(f"  NOTE: Manually add import_script/path to project.godot", "warning")

    return target_path
