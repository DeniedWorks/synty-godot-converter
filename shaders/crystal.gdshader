/******************************************************************************
CRYSTAL SHADER - Transparent/Refractive Materials

Source: GodotShaders.com community shader
License: CC0 / MIT (check original source)

# Overview
Shader for crystals, gems, glass, ice, and other transparent/refractive
materials. Supports fresnel effects, depth-based coloring, and refraction
distortion.

# Required Global Uniforms
None required. All parameters are per-material.

# Key Features
- Fresnel rim lighting effect
- Depth-based color gradient (shallow to deep)
- Refraction distortion
- Triplanar projection option
- Emission for glowing crystals

# Parameter Groups
## Base Properties
- base_albedo: Base color texture
- base_normal: Surface normal map
- metallic: Metallic intensity
- smoothness: Surface smoothness

## Fresnel Effect
- enable_fresnel: Enable rim lighting
- fresnel_power: Fresnel falloff (higher = narrower rim)
- fresnel_color: Rim light color

## Depth Coloring
- enable_depth: Use depth-based colors
- deep_color: Color at depth
- shallow_color: Color at surface
- depth_distance: Blend distance

## Refraction
- enable_refraction: Distort background
- refraction_strength: Distortion amount
- refraction_texture: Distortion normal map

# Usage Notes
- Set render mode to blend_mix for transparency
- Adjust fresnel_power: 2-4 for subtle, 6+ for sharp edges
- Depth coloring creates gem-like appearance
- Works with or without triplanar

# See Also
- docs/shader-reference.md for full parameter list
- docs/api/constants.md for Unity property mappings

# Original Implementation Notes
Refractive_Transparent = Synty crystal models shader for Godot.
(C) Copyright 2025 - Giancarlo Niccolai
Published under MIT licence.
v. 1.1

This shader is applied to Synthy translucent and transparent
material in Synty packages. Crystals and some glass use it.

Either the base properties or the triplanar properties are
applied; Enabling triplanar in the base property sections
effectively disables all the properties except for opacity.

The properties defined under "Triplanar base texture" are
deceptively named "base", but they only work with triplanar enabled.

The Triplanar top texture section allows to set completely
different settings for the top face.

Fresnel setting offer a glow on faces looking away from the view.

Refraction settings offer some glow/specular/prismatic effects
on all the surface.

Depth effect activates translucency, which allows to see things
inside/behind the crystal and colorize them differently, blending
from shallow to deep as the distance in the crystal increases.

Distortion settings are applied to depth, making things behind or
embedded in the crystal distorted with the view.

Most of the settings are world-relative, so moving or rotating the
crystal will shift the look of textures.
******************************************************************************/
shader_type spatial;
render_mode blend_mix, depth_draw_always, cull_disabled, diffuse_lambert, specular_schlick_ggx;

uniform sampler2D DEPTH_TEXTURE : hint_depth_texture, filter_linear_mipmap;

group_uniforms BaseProperties;
uniform bool enable_triplanar = false;
uniform vec4 base_color : source_color = vec4(1.0);
uniform float metallic : hint_range(0.0, 1.0) = 0.8;
uniform float smoothness : hint_range(0.0, 1.0) = 0.2;
uniform float opacity : hint_range(0.0, 1.0) = 1.0;

group_uniforms TriplanarBaseTexture;
uniform float base_tiling = 0.5;
uniform float base_normal_intensity =  -0.1;
uniform sampler2D base_albedo : hint_normal, filter_linear_mipmap;
uniform vec4 base_color_multiplier : source_color = vec4(1.0);
uniform sampler2D base_normal : hint_normal, filter_linear_mipmap;
uniform float base_specular_power : hint_range(0.0, 1.0) = 0.5;
uniform float base_metallic : hint_range(0.0, 1.0) = 0.8;

group_uniforms TriplanarTopTexture;
uniform bool enable_top_projection = false;
uniform float top_tiling = 0.5;
uniform float top_normal_intensity = -0.1;
uniform float spread : hint_range(0.0, 1.0) = 0.3;
uniform float fade_amount : hint_range(0.0, 63.0) = 38.6;

uniform sampler2D top_albedo : hint_normal, filter_linear_mipmap;
uniform vec4 top_color_multiplier : source_color = vec4(1.0);
uniform sampler2D top_normal : hint_normal, filter_linear_mipmap;

uniform float top_opacity : hint_range(0.0, 1.0) = 1.0;
uniform float top_specular_power : hint_range(0.0, 1.0) = 0.5;
uniform float top_metallic : hint_range(0.0, 1.0) = 0.0;

group_uniforms Fresnel;
uniform bool enable_fresnel = false;
uniform vec4 fresnel_color : source_color = vec4(1.0);
uniform float fresnel_border = 3.77;
uniform float fresnel_power = 4.86;

group_uniforms Depth;
uniform bool enable_depth = false;
uniform float depth_power_multiplier = 1.99;
uniform vec4 deep_color : source_color = vec4(1.0);
uniform float deep_power = 8;
uniform vec4 shallow_color : source_color = vec4(1.0);
uniform float shallow_power = 1.2;

group_uniforms Refraction;
uniform bool enable_refraction = false;
uniform sampler2D refraction_texture : hint_normal, filter_linear_mipmap;
uniform sampler2D refraction_height : hint_normal, filter_linear_mipmap;
uniform vec4 refraction_color : source_color = vec4(1.0);
uniform float refraction_power = 1.25;
uniform float steps = 0.0;
uniform float amplitude = -50.0;
uniform float refraction_tiling = 5.0;

group_uniforms Distortion;
uniform bool inner_distortion = false;
uniform float noise_tiling = 2.5;
uniform float inner_distortion_power : hint_range(0.0, 0.05) = 0.05;


struct triplanar_info {
	vec4 sample;
	float top_mask;
	float side_mask;
	float bottom_mask;
};

// Triplanar mapping function
triplanar_info triplanar_sample(sampler2D tex_top, sampler2D tex_bottom, sampler2D tex_side,
				vec3 world_pos, vec3 world_normal,
				vec2 tiling_top, vec2 offset_top,
				vec2 tiling_bottom, vec2 offset_bottom,
				vec2 tiling_side, vec2 offset_side,
				float top_to_side_diff, float fade)
{
	vec3 abs_normal = abs(world_normal);

	// Adjust blend weights based on top_to_side_difference
	float top_boost = mix(0.25, 4.0, clamp(top_to_side_diff, 0.0, 1.0));
	vec3 blend_weights = vec3(1.0, top_boost, 1.0);
	abs_normal *= blend_weights;

	// Apply fade/sharpness
	abs_normal = pow(abs_normal, vec3(fade));
	abs_normal /= dot(abs_normal, vec3(1.0));

	// Sample textures
	vec3 normal_direction = sign(world_normal) * vec3(-1.0, 1.0, 1.0);
	vec3 reversed_pos = world_pos * vec3(1.0, 1.0, -1.0);

	vec2 uv_x = vec2(normal_direction.x, 1.0) * vec2(reversed_pos.z * -1.0, reversed_pos.y);
	vec2 uv_y = vec2(normal_direction.y, 1.0) * reversed_pos.xz;
	vec2 uv_z = vec2(normal_direction.z, 1.0) * reversed_pos.xy;

	vec4 tex_x = texture(tex_side, uv_x * tiling_side + offset_side);
	vec4 tex_y_bottom = texture(tex_bottom, uv_y * tiling_bottom + offset_bottom);
	vec4 tex_y_top = texture(tex_top, uv_y * tiling_top + offset_top);
	vec4 tex_z = texture(tex_side, uv_z * tiling_side + offset_side);

	float modified_y = clamp(ceil(world_normal.y), 0.0, 1.0) * abs_normal.y;
	triplanar_info ret;
	ret.sample = tex_x * abs_normal.x + tex_y_top * modified_y + tex_y_bottom * (1.0 - modified_y) + tex_z * abs_normal.z;
	ret.top_mask = modified_y;
	ret.side_mask = abs_normal.x + abs_normal.z;
	ret.bottom_mask = 1.0 - modified_y;
	return ret;
}


vec4 normal_strength(vec4 normal, float intensity) {
	normal.xy *= intensity;
	normal.z = mix(1.0, normal.z, clamp(intensity, 0.0, 1.0));
	return normal;
}

vec3 normal_blend(vec3 A, vec3 B) {
	return normalize(vec3(A.xy + B.xy, A.z * B.z));
}

// Triplanar normal mapping function
float triplanar_normal_sample(sampler2D tex_top, sampler2D tex_bottom, sampler2D tex_side,
				vec3 world_pos, vec3 world_normal,
				vec2 tiling_top, vec2 offset_top, float intensity_top,
				vec2 tiling_bottom, vec2 offset_bottom, float intensity_bottom,
				vec2 tiling_side, vec2 offset_side, float intensity_side,
				float top_to_side_diff, float fade)
{
	vec3 abs_normal = abs(world_normal);

	// Adjust blend weights based on top_to_side_difference
	float top_boost = mix(0.25, 4.0, clamp(top_to_side_diff, 0.0, 1.0));
	vec3 blend_weights = vec3(1.0, top_boost, 1.0);
	abs_normal *= blend_weights;

	// Apply fade/sharpness
	abs_normal = pow(abs_normal, vec3(fade));
	abs_normal /= dot(abs_normal, vec3(1.0));

	// Sample textures
	vec3 normal_direction = sign(world_normal) * vec3(-1.0, 1.0, 1.0);
	vec3 reversed_pos = world_pos * vec3(1.0, 1.0, -1.0);

	vec2 uv_x = vec2(normal_direction.x, 1.0) * vec2(reversed_pos.z * -1.0, reversed_pos.y);
	vec2 uv_y = vec2(normal_direction.y, 1.0) * reversed_pos.xz;
	vec2 uv_z = vec2(normal_direction.z, 1.0) * reversed_pos.xy;

	vec4 tex_x = texture(tex_side, uv_x * tiling_side + offset_side);
	vec4 tex_y_bottom = texture(tex_bottom, uv_y * tiling_bottom + offset_bottom);
	vec4 tex_y_top = texture(tex_top, uv_y * tiling_top + offset_top);
	vec4 tex_z = texture(tex_side, uv_z* tiling_side + offset_side);

	vec3 strengthened_x = normal_strength(tex_x, intensity_side).xyz;
	vec3 strengthened_top = normal_strength(tex_y_top, intensity_top).xyz;
	vec3 strengthened_bottom = normal_strength(tex_y_bottom, intensity_bottom).xyz;
	vec3 strengthened_z = normal_strength(tex_z, intensity_side).xyz;

	float modified_y = clamp(ceil(world_normal.y), 0.0, 1.0) * abs_normal.y;
	return (strengthened_x * abs_normal.x + strengthened_top * modified_y + strengthened_bottom * (1.0 - modified_y) + strengthened_z * abs_normal.z).y;
}

float fresnel_effect(vec3 normal_ws, vec3 view_dir_ws, float power) {
    return pow(1.0 - clamp(dot(normalize(normal_ws), normalize(view_dir_ws)), 0.0, 1.0), power);
}

// Hash function (required for gradient noise)
vec2 hash2(vec2 p) {
    p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
    return -1.0 + 2.0 * fract(sin(p) * 43758.5453123);
}

// Classic gradient noise (similar to Unity's built-in)
float gradient_noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);

    // Smooth interpolation
    vec2 u = f * f * (3.0 - 2.0 * f);

    // 4 corners of the cell
    float a = dot(hash2(i + vec2(0.0, 0.0)), f - vec2(0.0, 0.0));
    float b = dot(hash2(i + vec2(1.0, 0.0)), f - vec2(1.0, 0.0));
    float c = dot(hash2(i + vec2(0.0, 1.0)), f - vec2(0.0, 1.0));
    float d = dot(hash2(i + vec2(1.0, 1.0)), f - vec2(1.0, 1.0));

    // Interpolate
    return mix(a, b, u.x) + (c - a) * u.y * (1.0 - u.x) + (d - b) * u.x * u.y;
}

vec2 parallax_pom(vec2 uv, vec3 view_dir_ts, sampler2D height_tex, float amp, float num_layers, vec2 tiling) {
	if (view_dir_ts.z <= 0.0) return uv; // Flat view, no offset

	vec2 delta_uv = (view_dir_ts.xy / view_dir_ts.z) * (amp / num_layers) * (1.0 / tiling); // Scale by tiling
	float layer_depth = 1.0 / num_layers;
	float current_depth = 0.0;

	vec2 current_uv = uv;
	float current_height = texture(height_tex, current_uv).r; // Red channel

	while (current_depth < current_height && --num_layers > 0.0) {
		current_uv -= delta_uv;
		current_height = texture(height_tex, current_uv).r;
		current_depth += layer_depth;
	}

	// Interpolate for smoothness
	vec2 after_uv = current_uv + delta_uv;
	float after_height = texture(height_tex, after_uv).r;
	float weight = (current_depth - layer_depth - (1.0 - after_height)) /
		((1.0 - current_height) - (1.0 - after_height));
	return mix(current_uv, after_uv, weight);
}

// Standalone edge detection function
float get_depth_edges(vec2 uv, mat4 inv_prj_matrix) {

	float depth = textureLod(DEPTH_TEXTURE, uv, 0.0).r;

    // Reconstruct view-space position from depth buffer.
    // SCREEN_UV is 0..1; convert to NDC (-1..1), then unproject.
    vec4 view_pos = inv_prj_matrix * vec4(uv * 2.0 - 1.0, depth, 1.0);
    view_pos.xyz /= view_pos.w;

    // In Godot's convention, view space looks down -Z,
    // so eye depth is -z to get a positive distance.
    return -view_pos.z;
}



void fragment() {
	// Get world position and normal
	vec3 world_pos = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vec3 world_normal = normalize((INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).xyz);

	// Triplanar Side Only
	vec4 tri_vec = triplanar_sample(base_albedo, base_albedo, base_albedo,
				world_pos, world_normal,
				vec2(base_tiling), vec2(0.0),
				vec2(base_tiling), vec2(0.0),
				vec2(base_tiling), vec2(0.0),
				0.2, 64.0).sample;

	float tri_normal = triplanar_normal_sample(base_normal, base_normal, base_normal,
				world_pos, world_normal,
				vec2(base_tiling), vec2(0.0), base_normal_intensity,
				vec2(base_tiling), vec2(0.0), base_normal_intensity,
				vec2(base_tiling), vec2(0.0), base_normal_intensity,
				0.2, 64.0);

	// Triplanar Top/Side
	triplanar_info tri_top_side_vec_and_mask = triplanar_sample(top_albedo, base_albedo, base_albedo,
				world_pos, world_normal,
				vec2(top_tiling), vec2(0.0),
				vec2(base_tiling), vec2(0.0),
				vec2(base_tiling), vec2(0.0),
				spread, fade_amount);

	float tri_top_side_normal = triplanar_normal_sample(top_normal, base_normal, base_normal,
				world_pos, world_normal,
				vec2(top_tiling), vec2(0.0), top_normal_intensity,
				vec2(base_tiling), vec2(0.0), base_normal_intensity,
				vec2(base_tiling), vec2(0.0), base_normal_intensity,
				spread, fade_amount);

	// Base color switcher ri-planar
	vec4 albedo_color;
	float tangent_normal = 0.0;
	if (enable_triplanar) {
		if (enable_top_projection) {
			albedo_color = mix(tri_vec * base_color_multiplier, tri_top_side_vec_and_mask.sample * top_color_multiplier, tri_top_side_vec_and_mask.top_mask);
			tangent_normal = tri_top_side_normal;
		} else {
			albedo_color = tri_vec * base_color_multiplier;
			tangent_normal = tri_normal;
		}
	} else {
		albedo_color = base_color;
		tangent_normal = 0.0;
	}

	// Depth
	if(enable_depth) {
		float distorted_sample = 0.0;
		if (inner_distortion) {
			// Distortion
			vec3 world_view = normalize(INV_VIEW_MATRIX * vec4(VIEW, 0.0)).xyz;
			distorted_sample = (1.0 - fresnel_effect(world_normal, world_view, inner_distortion_power)) * gradient_noise(UV + noise_tiling);
		}

		float depth = get_depth_edges(SCREEN_UV + distorted_sample, INV_PROJECTION_MATRIX) + VERTEX.z;
		vec4 depth_color = (1.0 - clamp(depth / deep_power, 0.0, 1.0)) * deep_color +
					       (1.0 - clamp(depth / shallow_power, 0.0, 1.0)) * shallow_color;

		vec4 crystal_color;
		if(enable_top_projection && enable_triplanar) {
			crystal_color = mix(depth_color, vec4(0.0), tri_top_side_vec_and_mask.top_mask) * depth_power_multiplier;
		} else {
			crystal_color = depth_color * depth_power_multiplier;
		}
		albedo_color += crystal_color;
	}

	if(enable_fresnel) {
		vec3 world_view = normalize(INV_VIEW_MATRIX * vec4(VIEW, 0.0)).xyz;
		vec4 fresnel_base = fresnel_effect(world_normal, world_view, fresnel_border) * fresnel_color * fresnel_power;

	if(enable_triplanar && enable_top_projection) {
		albedo_color = mix(albedo_color, albedo_color + fresnel_base, 1.0 - tri_top_side_vec_and_mask.top_mask);
	} else {
			albedo_color += fresnel_base;
		}
	}

	ALBEDO = albedo_color.xyz;
	NORMAL = normalize(NORMAL + vec3(0.0, tangent_normal * 2.0 -1.0, 0.0));
	ALPHA = mix(opacity, top_opacity, tri_top_side_vec_and_mask.top_mask);
	AO = 1.0;

	// Refraction
	if(enable_refraction) {
		// Tangentizing the normals
		mat3 TBN = mat3(normalize(TANGENT.xyz), normalize(BINORMAL), normalize(NORMAL));   // tangent space → view space
		vec3 viewTS = normalize(TBN * VIEW);
		vec2 refraction_uv = parallax_pom(UV, viewTS, refraction_height, amplitude, 0.0, vec2(refraction_tiling));
		vec4 refraction_sample = texture(refraction_texture, refraction_uv) * refraction_color * refraction_power;

		if (enable_top_projection) {
			EMISSION = mix(vec4(0.0), refraction_sample, tri_top_side_vec_and_mask.top_mask).xyz;
		} else {
			EMISSION = refraction_sample.xyz;
		}
	}

	// Metallic triplanar
	if (enable_triplanar) {
		if (enable_top_projection) {
			METALLIC = mix(base_metallic, top_metallic, tri_top_side_vec_and_mask.top_mask);
		} else {
			METALLIC = base_metallic;
		}
	} else {
		METALLIC = metallic;
	}

	// Smoothness triplanar
	float specular_triplanar;
	if (enable_triplanar) {
		if (enable_top_projection) {
			specular_triplanar = mix(base_specular_power, top_specular_power, tri_top_side_vec_and_mask.top_mask);
		} else {
			specular_triplanar = base_specular_power;
		}
	} else {
		specular_triplanar = smoothness;
	}
	ROUGHNESS = 1.0 - clamp(specular_triplanar, 0.0, 1.0);

	// Unity specular grayscale transformation (from gray 0.5)
	float specular_value = dot(vec3(0.5), vec3(0.2126, 0.7152, 0.0722));
    SPECULAR = clamp(specular_value, 0.0, 1.0);
}
