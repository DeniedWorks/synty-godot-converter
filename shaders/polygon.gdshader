/******************************************************************************
POLYGON SHADER - General Purpose PBR Material Shader

Source: GodotShaders.com community shader
License: CC0 / MIT (check original source)

# Overview
Primary shader for props, terrain, buildings, and general materials.
Supports PBR workflow with optional features like triplanar mapping,
snow coverage, emission, and ambient occlusion.

# Required Global Uniforms
None required. All parameters are per-material.

# Key Features
- PBR texturing (albedo, normal, roughness, metallic, AO)
- Triplanar projection for seamless terrain/rocks
- Snow/frost coverage with height-based blending
- Emission support for glowing materials
- UV scaling and offset

# Parameter Groups
## Base Textures
- base_texture: Main albedo/color texture
- normal_texture: Surface normal map
- roughness_texture: Surface roughness
- metallic_texture: Metallic areas
- ao_texture: Ambient occlusion

## Material Properties
- smoothness: Surface smoothness (inverse of roughness)
- metallic: Metallic intensity
- color_tint: Color multiplier

## Triplanar (Optional)
- enable_triplanar: Use world-space projection
- triplanar_scale: Projection scale
- triplanar_sharpness: Blend sharpness

## Snow (Optional)
- enable_snow: Add snow coverage
- snow_amount: Coverage percentage
- snow_height_influence: Height-based snow accumulation

# Usage Notes
- Most versatile shader - use for anything that doesn't need special effects
- Enable triplanar for rocks, cliffs, terrain without UV seams
- Snow effect works best with enable_snow=true and adjusting snow_amount

# See Also
- docs/shader-reference.md for full parameter list
- docs/api/constants.md for Unity property mappings

# Original Implementation Notes
PolygonShader = Synty models static and tri-planar shader for Godot.
(C) Copyright 2025 - Giancarlo Niccolai
Published under MIT licence.
v. 1.1

Synty PolygonShader is used as a material shader for many of the
static Synty assets in the Polygon and related packages (e.g.
biomes).

Other than providing basic shading for texture, normal and emission,
it allows:

- Triplanar shading (texture, normal, emission).
- Overlay texture (for effect like i.e. blinking or selection).
- Ambient Occlusion
- Emission (flat/triplanar)
- Snow effects

In particular, instead of a "traditional" XYZ tri-planar shading,
the Synty shader provides top (Y), bottom (-Y) and Side (X and Z)
triplanar projection.

Note: This shader reproduces the behavior of the original Unity Synty
PolygonShader as closely as possible, but the normal tangent pipeline
is extremely different; I tried to replicate the visuals of the
application of the tri-planar normal map as closely as possible,
considering the different rendering pipelines.
******************************************************************************/
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back;

group_uniforms Base;
uniform vec4 color_tint : source_color = vec4(1.0);
uniform float metallic : hint_range(0.0, 1.0) = 0.0;
uniform float smoothness : hint_range(0.0, 1.0) = 0.0;
uniform sampler2D metallic_smoothness_texture: source_color, filter_linear_mipmap, repeat_enable;
uniform vec2 uv_pan = vec2(0.0);

group_uniforms Base.BaseTexture;
uniform bool enable_base_texture = true;
uniform sampler2D base_texture : source_color, filter_linear_mipmap, repeat_enable;
uniform vec2 base_tiling = vec2(1.0);
uniform vec2 base_offset = vec2(0.0);

group_uniforms Base.NormalTexture;
uniform bool enable_normal_texture = true;
uniform sampler2D normal_texture : hint_normal, filter_linear_mipmap, repeat_enable;
uniform float normal_intensity : hint_range(0.0, 2.0) = 1.0;
uniform vec2 normal_tiling = vec2(1.0);
uniform vec2 normal_offset = vec2(0.0);

group_uniforms Base.EmissionTexture;
uniform bool enable_emission_texture = false;
uniform sampler2D emission_texture : source_color, filter_linear_mipmap, repeat_enable;
uniform vec2 emission_tiling = vec2(1.0);
uniform vec2 emission_offset = vec2(0.0);
uniform vec4 emission_color_tint : source_color = vec4(1.0);

group_uniforms Base.AmbientOclusion;
uniform bool enable_ambient_occlusion = false;
uniform float ao_intensity : hint_range(0.0, 5.0) = 1.0;
uniform sampler2D ao_texture : filter_linear_mipmap, repeat_enable;
uniform vec2 ao_tiling = vec2(1.0);
uniform vec2 ao_offset = vec2(0.0);
uniform bool generate_from_base_normals = false;

group_uniforms Overlay;
uniform bool enable_overlay_texture = false;
uniform sampler2D overlay_texture : source_color, filter_linear_mipmap, repeat_enable;
uniform vec2 overlay_tiling = vec2(1.0);
uniform vec2 overlay_offset = vec2(0.0);
uniform int overlay_uv_channel: hint_range(1, 4) = 1;
uniform float overlay_intensity : hint_range(0.0, 1.0) = 1.0;

group_uniforms Triplanar;
group_uniforms Triplanar.Base;
uniform bool triplanar_use_world_space = false;
uniform bool enable_triplanar_texture = false;
uniform sampler2D triplanar_texture_top : source_color, filter_linear_mipmap, repeat_enable;
uniform vec2 triplanar_tiling_top = vec2(1.0);
uniform vec2 triplanar_offset_top = vec2(0.0);
uniform sampler2D triplanar_texture_side : source_color, filter_linear_mipmap, repeat_enable;
uniform vec2 triplanar_tiling_side = vec2(1.0);
uniform vec2 triplanar_offset_side = vec2(0.0);
uniform sampler2D triplanar_texture_bottom : source_color, filter_linear_mipmap, repeat_enable;
uniform vec2 triplanar_tiling_bottom = vec2(1.0);
uniform vec2 triplanar_offset_bottom = vec2(0.0);

uniform float triplanar_top_to_side_difference : hint_range(0.0, 1.0) = 0.5;
uniform float triplanar_fade : hint_range(0.0, 1.0) = 0.5;
uniform float triplanar_intensity : hint_range(0.0, 1.0) = 1.0;
uniform float top_metallic : hint_range(0.0, 1.0) = 0.0;
uniform float side_metallic : hint_range(0.0, 1.0) = 0.0;
uniform float bottom_metallic : hint_range(0.0, 1.0) = 0.0;
uniform float top_smoothness : hint_range(0.0, 1.0) = 0.0;
uniform float side_smoothness : hint_range(0.0, 1.0) = 0.0;
uniform float bottom_smoothness : hint_range(0.0, 1.0) = 0.0;

group_uniforms Triplanar.Normal;
uniform bool enable_triplanar_normals = false;
uniform sampler2D triplanar_normal_top : hint_normal, filter_linear_mipmap, repeat_enable;
uniform float triplanar_normal_intensity_top : hint_range(0.0, 1.0) = 1.0;
uniform vec2 triplanar_normal_tiling_top = vec2(1.0);
uniform vec2 triplanar_normal_offset_top = vec2(0.0);
uniform sampler2D triplanar_normal_bottom : hint_normal, filter_linear_mipmap, repeat_enable;
uniform float triplanar_normal_intensity_bottom : hint_range(0.0, 1.0) = 1.0;
uniform vec2 triplanar_normal_tiling_bottom = vec2(1.0);
uniform vec2 triplanar_normal_offset_bottom = vec2(0.0);
uniform sampler2D triplanar_normal_side : hint_normal, filter_linear_mipmap, repeat_enable;
uniform float triplanar_normal_intensity_side : hint_range(0.0, 1.0) = 1.0;
uniform vec2 triplanar_normal_tiling_side = vec2(1.0);
uniform vec2 triplanar_normal_offset_side = vec2(0.0);
uniform float triplanar_normal_top_to_side_difference : hint_range(0.0, 1.0) = 0.5;
uniform float triplanar_normal_fade : hint_range(0.0, 128.0) = 10.0;


group_uniforms Triplanar.Emission;
uniform bool enable_triplanar_emission = false;
uniform sampler2D triplanar_emission_texture : source_color, filter_linear_mipmap, repeat_enable;
uniform float triplanar_emission_tiling = 1.0;
uniform float triplanar_emission_blend : hint_range(0.0, 50.0) = 4.0;
uniform float triplanar_emission_intensity : hint_range(0.0, 50.0) = 1.0;
uniform vec4 triplanar_emission_color_tint : source_color = vec4(1.0);

group_uniforms Snow;
uniform bool enable_snow = false;
uniform bool snow_use_world_up = true;
uniform vec4 snow_color : source_color = vec4(1.0);
uniform float snow_metallic : hint_range(0.0, 1.0) = 0.0;
uniform float snow_smoothness : hint_range(0.0, 1.0) = 0.8;
uniform float snow_level : hint_range(0.0, 1.0) = 0.5;
uniform float snow_transition = 0.95;


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
	vec2 uv_y = vec2(normal_direction.y, 1.0) * reversed_pos.zx;
	vec2 uv_z = vec2(normal_direction.z, 1.0) * reversed_pos.xy;

	vec4 tex_x = texture(tex_side, uv_x * tiling_side + offset_side);
	vec4 tex_y_top = texture(tex_top, uv_y * tiling_top + offset_top);
	vec4 tex_y_bottom = texture(tex_bottom, uv_y * tiling_bottom + offset_bottom);
	vec4 tex_z = texture(tex_side, uv_z * tiling_side + offset_side);

	//float modified_y = clamp(ceil(world_normal.y), 0.0, 1.0) * abs_normal.y;
	float modified_y = clamp(ceil(world_normal.y), 0.0, 1.0) * abs_normal.y;
	triplanar_info ret;
	//ret.sample = tex_x * abs_normal.x + tex_y_top * modified_y + tex_y_bottom * (1.0 - modified_y) + tex_z * abs_normal.z;
	ret.sample = tex_y_top * modified_y;
	if(world_normal.y < -0.5 ) {
		ret.sample += tex_y_bottom * (1.0 - modified_y);
	} else {
		ret.sample +=  tex_x * abs_normal.x + tex_z * abs_normal.z;
	}
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
	vec4 tex_z = texture(tex_side, uv_z * tiling_side + offset_side);

	vec3 strengthened_x = normal_strength(tex_x, intensity_side).xyz;
	vec3 strengthened_top = normal_strength(tex_y_top, intensity_top).xyz;
	vec3 strengthened_bottom = normal_strength(tex_y_bottom, intensity_bottom).xyz;
	vec3 strengthened_z = normal_strength(tex_z, intensity_side).xyz;

	float modified_y = clamp(ceil(world_normal.y), 0.0, 1.0) * abs_normal.y;
	vec3 sample = strengthened_top * modified_y;
	if(world_normal.y < -0.5 ) {
		sample += strengthened_bottom * (1.0 - modified_y);
	} else {
		sample += strengthened_x * abs_normal.x + strengthened_z * abs_normal.z;
	}
	return normalize(sample).y;
}



void fragment() {
	// Get world position and normal
	vec3 world_pos = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vec3 world_normal = normalize((INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).xyz);

	// Triplanar position - world-space or object-space
	vec3 triplanar_pos = world_pos;
	if (!triplanar_use_world_space) {
		triplanar_pos = (inverse(MODEL_MATRIX) * vec4(world_pos, 1.0)).xyz;
	}

	// UV with panning
	vec2 uv_panned = UV + uv_pan * TIME;

	// === BASE ALBEDO ===
	vec4 base_albedo = vec4(1.0);
	if (enable_base_texture) {
	    base_albedo = texture(base_texture, uv_panned * base_tiling + base_offset);
	}

	// === OVERLAY ===
	vec4 overlay = vec4(1.0);
	if (enable_overlay_texture) {
		vec4 overlay_sample = texture(overlay_texture, uv_panned * overlay_tiling + overlay_offset);
		overlay = overlay_sample + vec4(vec3(1.0 - overlay_intensity), 0.0);
		overlay = clamp(overlay, vec4(0.0), vec4(1.0));
	}

	// === TRIPLANAR ALBEDO ===
	vec4 triplanar_albedo = vec4(1.0);
	// === METALLIC & SMOOTHNESS ===
	float final_metallic = metallic;
	float final_smoothness = smoothness;
	if (enable_triplanar_texture) {
		triplanar_info tri_info = triplanar_sample(
			triplanar_texture_top,
			triplanar_texture_bottom,
			triplanar_texture_side,
			triplanar_pos, world_normal,
			triplanar_tiling_top * 0.01, triplanar_offset_top,
			triplanar_tiling_bottom * 0.01, triplanar_offset_bottom,
			triplanar_tiling_side * 0.01, triplanar_offset_side,
			triplanar_top_to_side_difference, 0.1 + triplanar_fade * 49.9);

		triplanar_albedo = clamp((1.0 - triplanar_intensity) + tri_info.sample, vec4(0.0), vec4(1.0));
		final_metallic = tri_info.top_mask * top_metallic + tri_info.bottom_mask * bottom_metallic + tri_info.side_mask * side_metallic;
		final_smoothness = tri_info.top_mask * top_smoothness + tri_info.bottom_mask * bottom_smoothness + tri_info.side_mask * side_smoothness;
	}

	// Combine albedo layers
	vec4 final_albedo = base_albedo * overlay * triplanar_albedo * color_tint;

        // === SNOW ===
        float snow_mask = 0.0;
	if (enable_snow) {
		vec3 normal_for_snow = snow_use_world_up ? world_normal : (inverse(MODEL_MATRIX) * INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).xyz;
		float snow_fade = mix(0.35, 50.0, snow_level);
		snow_mask = pow(max(0.0, normal_for_snow.y), snow_fade) * snow_transition;
		snow_mask = clamp(snow_mask, 0.0, 1.0);

		final_albedo = mix(final_albedo, snow_color, snow_mask);
	}

	// === NORMALS ===
	// Only modify normals if at least one normal source is enabled
	float normal_sample = 0.0;
	float t_normal_sample = 0.0;
	if (enable_normal_texture) {
		vec4 normal_sample_a = texture(normal_texture, uv_panned * normal_tiling + normal_offset);
		normal_sample = normal_strength(normal_sample_a, normal_intensity).y;
	}

        if (enable_triplanar_normals) {
		t_normal_sample = triplanar_normal_sample(
			triplanar_normal_top, triplanar_normal_bottom, triplanar_normal_side,
			triplanar_pos, world_normal,
			triplanar_normal_tiling_top * 0.01, triplanar_normal_offset_top, triplanar_normal_intensity_top,
			triplanar_normal_tiling_bottom * 0.01, triplanar_normal_offset_bottom, triplanar_normal_intensity_bottom,
			triplanar_normal_tiling_side * 0.01, triplanar_normal_offset_side, triplanar_normal_intensity_side,
			triplanar_normal_top_to_side_difference, triplanar_normal_fade);
	}

	NORMAL = normalize(NORMAL + vec3(0.0, (t_normal_sample + normal_sample) * 2.0 - 1.0, 0.0));

        // === EMISSION ===
	vec3 emission = vec3(0.0);
	if (enable_emission_texture) {
		vec4 emission_sample = texture(emission_texture, uv_panned * emission_tiling + emission_offset);
		emission = (emission_sample * emission_color_tint).rgb;
	}

	if (enable_triplanar_emission) {
		vec3 triplanar_uv = world_pos * triplanar_emission_tiling;
		vec3 blend = pow(abs(world_normal), vec3(triplanar_emission_blend));
		blend /= dot(blend, vec3(1.0));

		vec4 em_x = texture(triplanar_emission_texture, triplanar_uv.zy);
		vec4 em_y = texture(triplanar_emission_texture, triplanar_uv.xz);
		vec4 em_z = texture(triplanar_emission_texture, triplanar_uv.xy);

		vec4 triplanar_em = em_x * blend.x + em_y * blend.y + em_z * blend.z;
		emission = (triplanar_em * triplanar_emission_color_tint * triplanar_emission_intensity).rgb;
        }


	if (enable_snow) {
		final_metallic = mix(final_metallic, snow_metallic, snow_mask);
		final_smoothness = mix(final_smoothness, snow_smoothness, snow_mask);
	}

	// === AMBIENT OCCLUSION ===
	float ao = 1.0;
	if (enable_ambient_occlusion) {
		if (generate_from_base_normals) {
			ao = texture(normal_texture, uv_panned * normal_tiling + normal_offset).r;
		} else {
			ao = texture(ao_texture, UV * ao_tiling + ao_offset).r;
		}
		ao = pow(ao, ao_intensity);
	}

	// === OUTPUT ===
	ALBEDO = final_albedo.rgb;
	EMISSION = emission;
	METALLIC = final_metallic;
	ROUGHNESS = 1.0 - final_smoothness;
	AO = ao;
	ALPHA = final_albedo.a;
	ALPHA_SCISSOR_THRESHOLD = 0.1;
}
