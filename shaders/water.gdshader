/******************************************************************************
WATER SHADER - Rivers, Lakes, and Ocean Surfaces

Source: GodotShaders.com community shader
License: CC0 / MIT (check original source)

# Overview
Full-featured water shader with waves, foam, caustics, and shore effects.
Suitable for oceans, rivers, lakes, ponds, and waterfalls.

# Required Global Uniforms
The following global uniforms enhance water appearance:
- OceanWavesGradient: Optional wave height texture

# Key Features
- Animated waves (vertex displacement)
- Shore foam with texture
- Underwater caustics
- Depth-based transparency
- Screen-space distortion/refraction
- Normal map animation

# Parameter Groups
## Water Colors
- deep_color: Deep water tint
- shallow_color: Shallow water tint
- foam_color: Foam/whitecap color

## Waves
- wave_speed: Animation speed
- wave_scale: Wave frequency
- wave_height: Vertex displacement amount

## Foam
- enable_foam: Show shore foam
- foam_amount: Foam coverage
- foam_texture: Foam pattern texture

## Caustics
- enable_caustics: Underwater light patterns
- caustics_scale: Pattern size
- caustics_speed: Animation speed
- caustics_flipbook: Animated caustics texture

## Shore
- shore_depth: Shallow water threshold
- shore_fade: Edge fade distance

# Usage Notes
- Requires proper depth texture setup in Godot
- Wave height affects collision - match with CollisionShape
- Caustics need a texture flipbook for animation
- Foam shows where water meets geometry

# See Also
- docs/shader-reference.md for full parameter list
- docs/api/constants.md for Unity property mappings

# Original Implementation Notes
Water = Synty models water shader for Godot.
(C) Copyright 2025 - Giancarlo Niccolai
Published under MIT licence.
v 1.1

This shader is a Godot replacement for the Synty "Water" shader (october 2025).
Care has been taken to reproduce all the features of the original Water shader,
and reproduce similar visuals (including noise and wind effect) for similar
settings as close as possible.

However, some differences in the rendering pipeline has required slightly
different visuals for _distortion_ and for the _oceanic wave_ mesh displacing.

The options are organised following the same grouping and order of the
Unity Water Shader provided by Synty.

# Set up

This shader uses the global weather system provided by Synty asset packages;
in particular, it is necessary to set the following variables as global
shader variables in the host project:

- float GaleStrength: base wind power, will increase the wave height.
- vec3 WindDirection: direction pushing the waves; only X/Z normal is considered.
- sampler2D OceanWavesGradient: A texture2D used to displace the mesh to emulate
  oceanic waves.

The wave gradient should be a FastNoise or a 2-directional gradient; a
mono-directional gradient will limit the ability to rotate the wind direction.

This Godot shader has the ability to use non-global versions of the above
variables, de-activating the flag **use_global_weather_control**, which is
active by default.

# Improved settings

- ocean_wave_frequency zooms in the wave gradient/noise, reducing the
  size of the waves while maintaining their height and speed.
- maximum_depth cuts the depth at which water becomes completely opaque.
  The Synty package has a fixed constant set to 15 meters, which is
  the default for the setting in this shader.
- distortion_speed works with distortion_size to add a wavy look
  to underwater distortions.

# Main Visual Differences

- The wave generator has a slightly different logic, due to a different
  rendering pipeline in Godot. Given similar gradients, the waves should
  look similar, but you may need to tweak the values a bit.

- The _distortion_ effect uses a slightly different algorithm; it provides
  a nice distorting visual, but it will probably look different than on
  Unity.

- The oceanic wave foam may look a little bit sparser than on Unity, you
  may want to tweak the values.

- Normals are less defined than on Unity; as the reflection isn't as
  clear.

# Note

- Distortion hijacks the alpha setting, applying a manual transparency.
  The effects of borders _colorization_ (shallow, deep, very deep colors)
  are not taken in consideration when distorting, so, for credible results,
  use moderate settings both for colorization and distortion when used
  together.
******************************************************************************/

shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_lambert, specular_disabled;

uniform sampler2D DEPTH_TEXTURE : hint_depth_texture, filter_linear_mipmap;
uniform sampler2D SCREEN_TEXTURE : hint_screen_texture, filter_linear_mipmap;

group_uniforms General;

uniform bool use_global_weather_controller = false;

uniform float non_global_gale_strength = 0.2;
uniform vec3 non_global_wind_direction = vec3(1.0, 0.0, 0.0);
uniform sampler2D non_global_ocean_waves_gradient: source_color, filter_linear_mipmap;

group_uniforms Base;

uniform float smoothness: hint_range(0.0, 1.0) = 0.766;
uniform float metallic: hint_range(0.0, 1.0) = 0.0;
uniform float base_opacity: hint_range(0.0, 1.0) = 0.941;
uniform float shallows_opacity: hint_range(0.0, 1.0) = 0.661;
uniform vec4 shallow_color: source_color = vec4(0.5, 0.5, 0.2, 1.0);
uniform vec4 deep_color: source_color = vec4(0.4, 0.4, 0.8, 1.0);
uniform vec4 very_deep_color: source_color = vec4(0.1, 0.1, 0.2, 1.0);
uniform float deep_height = 1.16;
uniform float very_deep_height = 4;
uniform float maximum_depth = 15.0;

group_uniforms Base.Normals;
uniform bool enable_normals = false;
uniform sampler2D normal_texture: source_color, filter_linear_mipmap;
uniform vec2 normal_offset = vec2(0.0);
uniform float normal_tiling = 0.0;
uniform float normal_intensity: hint_range(0.0, 10.0) = 1.0;
uniform float normal_pan_speed = 1.0;
uniform float normal_noise_tiling = 0.2;
uniform float normal_noise_intensity = 0.23;

group_uniforms Base.FadeDistantNormals;
uniform bool enable_fresnel_fade  = false;
uniform float fade_distance = 1.0;
uniform float fade_power = 0.0;


group_uniforms ShoreFoam;
uniform bool enable_shore_wave_foam = false;

group_uniforms ShoreFoam.Wave;
uniform bool enable_shore_animation = false;
uniform int animation_offset = 0;

uniform float shore_wave_speed: hint_range(0.0, 1.0) = 1.0;
uniform float shore_wave_return_amount: hint_range(0.0, 1.0) = 1.0;
uniform float shore_wave_tickness: hint_range(0.0, 1.0) = 0.1;
uniform float shore_edge_opacity: hint_range(0.0, 1.0) = 0.1;
uniform vec4 shore_wave_color_tint: source_color = vec4(1.0);
uniform float shore_edge_tickness: hint_range(0.0, 1.0) = 0.1;
uniform float shore_edge_noise_scale = 0.86;

uniform float shore_lap_fade_out_speed: hint_range(0.0, 10.0) = 1.0;
uniform float shore_lap_fade_in_speed: hint_range(0.0, 10.0) = 3.0;

uniform int shore_foam_noise_scale: hint_range(0, 100, 1) = 1;
uniform sampler2D shore_foam_noise_texture: source_color, filter_linear_mipmap;

group_uniforms ShoreFoam.Foam;
uniform bool enable_shore_foam = false;
uniform float shore_small_foam_opacity: hint_range(0.0, 1.0) = 0.725;
uniform float shore_small_foam_tiling = 2.5;
uniform vec4 shore_foam_color_tint: source_color = vec4(1.0);


group_uniforms GlobalFoam;
uniform bool enable_global_foam = false;
uniform sampler2D noise_texture: source_color, filter_linear_mipmap;

group_uniforms GlobalFoam.TopScrollingTexture;
uniform bool enable_top_scrolling_texture = false;
uniform vec2 top_scrolling_direction = vec2(0.0, -0.01);
uniform sampler2D scrolling_texture: source_color, filter_linear_mipmap;
uniform vec2 scrolling_texture_tiling = vec2(1.0, 1.0);
uniform vec4 scrolling_texture_tint: source_color = vec4(0.3, 0.8, 0.95, 1.0);
uniform float scrolling_texture_opacity: hint_range(0.0, 1.0) = 0.25;

group_uniforms Waves;
uniform bool enable_ocean_waves = false;
uniform float ocean_wave_height: hint_range(0.0, 10.0) = 0.40;
uniform float ocean_wave_speed: hint_range(0.0, 1.0) = 0.3;
uniform float ocean_foam_amount: hint_range(0.0, 1.0) = 0.5;
uniform float ocean_foam_opacity: hint_range(0.0, 1.0) = 0.321;
uniform float ocean_wave_frequency: hint_range(1.0, 20.0) = 1.0;
uniform int ocean_breakup_tiling = 1;


group_uniforms Advanced;

group_uniforms Advanced.Caustics;
uniform bool enable_caustics = false;
uniform bool caustics_use_voronoi_noise = false;
uniform float caustics_intensity: hint_range(0.0, 1.0) = 0.5;
uniform vec4 caustics_color: source_color = vec4(1.0);
uniform sampler2D caustics_flipbook: source_color, filter_linear_mipmap;
uniform float caustics_speed: hint_range(0.0, 10.0) = 1.0;
uniform int caustics_scale = 1;

group_uniforms Advanced.Distorsion;
uniform bool enable_distortion = false;
uniform float distortion_speed: hint_range(0.0, 1.0) = 0.5;
uniform vec2 distortion_direction = vec2(1.0, 1.0);
uniform float distortion_size: hint_range(0.0, 1.0) = 0.1;
uniform float distortion_strength: hint_range(0.0, 1.0) = 0.5;


global uniform vec3 WindDirection;
global uniform float GaleStrength;
global uniform sampler2D OceanWavesGradient;

//////// Generic Utilities

vec3 rotate_around_y(vec3 pos, float angle_deg) {
    float angle = radians(angle_deg);
    float c = cos(angle);
    float s = sin(angle);
    mat3 rot = mat3(
        vec3(c, 0.0, -s),
        vec3(0.0, 1.0, 0.0),
        vec3(s, 0.0, c)
    );
    return rot * pos;
}

float saturate_value(float value) {
	return clamp(value, 0.0, 1.0);
}

vec2 unity_voronoi_noise_randomVector(vec2 uv, float offset) {
    mat2 m = mat2(vec2(15.27, 99.41), vec2(47.63, 89.98));
    vec2 temp = transpose(m) * uv;
    uv = fract(sin(temp) * 46839.32);
    return vec2(sin(uv.y * offset) * 0.5 + 0.5, cos(uv.x * offset) * 0.5 + 0.5);
}

vec2 Unity_Voronoi(vec2 uv, float AngleOffset, float CellDensity) {
    vec2 g = floor(uv * CellDensity);
    vec2 f = fract(uv * CellDensity);
    float t = 8.0;
    vec3 res = vec3(t, 0.0, 0.0);
    for (int y = -1; y <= 1; y++) {
        for (int x = -1; x <= 1; x++) {
            vec2 lattice = vec2(float(x), float(y));
            vec2 offset = unity_voronoi_noise_randomVector(lattice + g, AngleOffset);
            vec2 point = lattice + offset - f;
            float d = length(point);
            if (d < res.x) {
                res = vec3(d, offset.x, offset.y);
            }
        }
    }
    return vec2(res.x, res.y);
}


vec2 get_flipbook_uv(vec2 uv, int tile_width, int tile_height, int tile_index, bool invert_x, bool invert_y) {
    vec2 tile_size = vec2(1.0 / float(tile_width), 1.0 / float(tile_height));

	int h_tile = tile_index % tile_width;
	int v_tile = (tile_index / tile_width) % tile_height;
	if(invert_x) {
		h_tile = tile_width - h_tile - 1;
	}
	if(invert_y) {
		v_tile = tile_height - v_tile - 1;
	}

    vec2 tile_offset = vec2(
        float(h_tile) * tile_size.x,
        1.0 - (1.0 + float(v_tile)) * tile_size.y
    );

    vec2 adjusted_uv = uv * tile_size + tile_offset;

    return adjusted_uv;
}

float remap01(float input, float outMin, float outMax) {
    return outMin + input * (outMax - outMin);
}


vec4 top_down_projection(vec3 world_pos, vec3 world_normal, sampler2D tex, vec2 tile, vec2 off) {
	vec2 tpos = (world_pos * vec3(1, 1, -1)).xz;
	vec2 tnorm = vec2((sign(world_normal) * vec3(-1, 1, 1)).y, 1.0);
	vec2 prj_uv = (tpos * tnorm) * tile + off;
	return(texture(tex, prj_uv));
}

vec2 unity_gradientNoise_dir(vec2 p)
{
    p = mod(p, 289.0);
    float x = (34.0 * p.x + 1.0) * mod(p.x, 289.0) + p.y;
    x = (34.0 * x + 1.0) * mod(x, 289.0);
    x = fract(x / 41.0) * 2.0 - 1.0;
    return normalize(vec2(x - floor(x + 0.5), abs(x) - 0.5));
}

float unity_gradientNoise(vec2 p)
{
    vec2 ip = floor(p);
    vec2 fp = fract(p);
    float d00 = dot(unity_gradientNoise_dir(ip), fp);
    float d01 = dot(unity_gradientNoise_dir(ip + vec2(0.0, 1.0)), fp - vec2(0.0, 1.0));
    float d10 = dot(unity_gradientNoise_dir(ip + vec2(1.0, 0.0)), fp - vec2(1.0, 0.0));
    float d11 = dot(unity_gradientNoise_dir(ip + vec2(1.0, 1.0)), fp - vec2(1.0, 1.0));
    fp = fp * fp * fp * (fp * (fp * 6.0 - 15.0) + 10.0);
    return mix(mix(d00, d01, fp.y), mix(d10, d11, fp.y), fp.x);
}

float unity_gradientNoise_scaled(vec2 uv, float scale)
{
    return unity_gradientNoise(uv * scale) + 0.5;
}

vec2 panner(vec2 uv, float speed) {
	vec2 time_factor = vec2(TIME * speed);
	return uv + time_factor;
}


///// PROCESS STEPS

float scene_depth(vec2 screen_uv, mat4 inv_prj) {
	// Sample nonlinear scene depth (closest opaque surface)
	float raw_depth = texture(DEPTH_TEXTURE, screen_uv).r;

	// Reconstruct NDC (adjust for renderer)
    vec3 ndc;
    #if CURRENT_RENDERER == RENDERER_COMPATIBILITY
    ndc = vec3(screen_uv * 2.0 - 1.0, raw_depth * 2.0 - 1.0);
    #else  // Forward+/Mobile (default, reversed-Z)
    ndc = vec3(screen_uv * 2.0 - 1.0, raw_depth);
    #endif

    // Transform to view space and get linear depth
    vec4 view_pos = inv_prj * vec4(ndc, 1.0);
    view_pos.xyz /= view_pos.w;
	return -view_pos.z; // Positive distance from camera
}

vec2 get_caustic_uv(vec3 camera_pos, vec3 camera_dir, vec3 view_dir, float depth) {
	vec3 view_module = view_dir / dot(view_dir, camera_dir);
	vec3 depth_vector = depth * view_module;
	return (depth_vector + camera_pos).xz;
}

vec4 water_caustics(vec3 camera_pos, vec3 camera_dir, vec3 view_dir, float eye_depth, float depth_fade) {
	vec2 caustic_color_uv = get_caustic_uv(camera_pos, camera_dir, view_dir, eye_depth);

	float caustic_value;
	if (caustics_use_voronoi_noise) {
		// The UNITY branch is not using scale and speed in the voronoi branch.
		float value = Unity_Voronoi(caustic_color_uv / max(0.01, float(caustics_scale)/2.0), (TIME * caustics_speed + 100.0) * 2.0, 3.0).x;
		caustic_value = saturate_value(pow(value, 4.0));
	} else {
		vec2 scaled_in_uv = caustic_color_uv / max(0.01, float(caustics_scale));
		vec2 fract_part = vec2(fract(scaled_in_uv.x), fract(scaled_in_uv.y));

		int flipbook_idx = int(TIME * caustics_speed * 10.0); // at speed scale 1, change 10 indices per second
		vec2 sample_uv = get_flipbook_uv(fract_part, 8, 8, flipbook_idx, false, true);
		caustic_value = texture(caustics_flipbook, sample_uv).r;
	}

	// Fade caustics out the deeper the ocean
	float saturated_depth = saturate_value(depth_fade * 0.1);
	float ocean_foor_fader = (1.0 - saturated_depth) * saturated_depth;

	// Set caustics intensity
	vec4 faded_caustics = caustics_color * ocean_foor_fader * caustic_value;
	faded_caustics *= caustics_intensity * 10.0;
	float cc_intensity = caustics_intensity + 1.0;
	return vec4(
			saturate_value(pow(faded_caustics.r, cc_intensity)),
			saturate_value(pow(faded_caustics.g, cc_intensity)),
			saturate_value(pow(faded_caustics.b, cc_intensity)),
			saturate_value(pow(faded_caustics.a, cc_intensity)));
}

vec4 water_shore_waves(vec3 position, vec3 normal, float depth) {
	// Foam Noise
	vec4 foam_noise_raw = top_down_projection(position, normal, shore_foam_noise_texture, vec2(float(shore_foam_noise_scale) * 0.005), vec2(0.0));
	float foam_noise = saturate_value(pow(foam_noise_raw.x, 0.2));

	// Shore wave oscillation
	vec4 shore_wave_raw = top_down_projection(position, normal, noise_texture, vec2(float(shore_edge_noise_scale) * 0.005), vec2(0.0));
	float shore_wave_oscillation = saturate_value(shore_wave_raw.r);

	// Normalized Shore Lap Time Loop (0 - 1)
	float animation = enable_shore_animation ? TIME : float(animation_offset);
	float norm_shore_lap_time = fract(shore_wave_oscillation + shore_wave_speed * animation);

	// Shore wave return factor
	float return_factor = PI / (2.0 - shore_wave_return_amount);
	float sin_lap = sin(norm_shore_lap_time * return_factor);
	float wave_lap = depth + sin_lap;

	float wave_motion = saturate_value(wave_lap * foam_noise);

	// Fadein - fadeout
	float rect_lap_fade_in_speed = 1.0 - saturate_value(remap01(norm_shore_lap_time, -shore_lap_fade_in_speed, 1.0));
	float rect_lap_fade_out_speed = 1.0 - saturate_value(remap01(norm_shore_lap_time, 1.0, -shore_lap_fade_out_speed));
	float lap_fade_speed = rect_lap_fade_in_speed * rect_lap_fade_out_speed;

	// Shore lap tickness
	float rectified_shore_wave_tickness = shore_wave_tickness * 0.9999 * lap_fade_speed;

	// Wave direction mask (0 moving back, 1 moving forward)
	float wave_dir = saturate_value(floor(wave_motion + rectified_shore_wave_tickness) - floor(wave_motion));
	float wave_factor = mix(0.0, wave_dir, shore_edge_opacity / 1.5);

	return shore_wave_color_tint * wave_factor;
}

vec4 water_shore_foam(vec3 position, vec3 normal, float depth) {
	float depth_factor = (1.0 - saturate_value(depth / 2.0)) * 0.8;
	float time_offset =  TIME * 0.003;
	vec4 foam = top_down_projection(position, normal, noise_texture, vec2(shore_small_foam_tiling * 0.01), vec2(time_offset));

	// Apply noise to the shore mask to create foam effects
	float effect_factor = saturate_value(pow((depth_factor * foam).r * 5.0, 20.0));
	float effect_mask = mix(0, effect_factor, shore_small_foam_opacity / 3.0);
	return shore_foam_color_tint * effect_mask;
}

vec3 water_distortion(vec2 uv, vec2 screen_pos) {
	vec2 vdist = distortion_direction * distortion_speed * 0.001;
	vec2 noise_source = uv + vdist * TIME;
	float noise = unity_gradientNoise_scaled(noise_source, distortion_size * 200.0);
	vec2 sampler = noise * distortion_strength * 0.05 + screen_pos;
	sampler += sin(TIME/2.0 * (1.0+distortion_speed * 2.0)) * distortion_strength / 100.0;

	return texture(SCREEN_TEXTURE, sampler).xyz * 0.65;
}

vec4 water_top_scrolling(vec2 uv) {
	vec2 time_offset = (1.0 - top_scrolling_direction * TIME);
	vec4 sample = texture(scrolling_texture,uv * scrolling_texture_tiling + time_offset);

	return sample * scrolling_texture_tint * scrolling_texture_opacity;
}

vec3 water_normal(vec3 world_pos, vec3 world_normal) {
	vec2 tiling = vec2(normal_noise_tiling * 0.01);
	// The Unity shader has a quite complex calculation for the offset, but it is set to 0 through a constant.
	vec4 prj1 = top_down_projection(world_pos, world_normal, noise_texture, vec2(tiling), vec2(0,0));
	vec4 prj2 = top_down_projection(world_pos, world_normal, noise_texture, vec2(tiling * 0.5), vec2(0,0));
	vec2 normal_uv = vec2(prj1.r * prj2.r * normal_noise_intensity) + normal_offset;

	// Break up the repetition of the normal map by overlaying multiple scaled versions
	vec2 panned_uv = normal_uv + panner(vec2(0.0), normal_pan_speed * 0.02);

	float tiling_factor = normal_tiling * 0.04;
	vec4 prj_n1 = top_down_projection(world_pos, world_normal, normal_texture, vec2(tiling_factor), panned_uv);
	vec4 prj_n2 = top_down_projection(world_pos, world_normal, normal_texture, vec2(tiling_factor * 0.2), panned_uv * vec2(1.0, -1.0));
	vec3 normal_blend = normalize(vec3(prj_n1.xy + prj_n2.xy, prj_n1.z * prj_n2.z));

	return normal_blend;
}

float water_transparency(float shallows_depth, float depth_fade) {
	return 1.0 - remap01(saturate_value(depth_fade / maximum_depth), shallows_opacity, 1.0);
}

float fresnel_mask(vec3 normal_ws, vec3 view_dir_ws) {
    float fresnel_effect = pow(1.0 - clamp(dot(normalize(normal_ws), normalize(view_dir_ws)), 0.0, 1.0), fade_distance);
	return smoothstep(0.0, 1.0, 1.0 - fresnel_effect * fade_power) * normal_intensity;
}

vec4 ocean_waves(vec2 uv, float speed, float height, vec3 wind_dir, float gale_strenght) {
	vec2 pan_uv = uv + normalize(wind_dir).xz * TIME/10.0;
	vec4 sample;
	if(use_global_weather_controller) {
		sample = texture(OceanWavesGradient, pan_uv * ocean_wave_frequency);
	} else {
		sample = texture(non_global_ocean_waves_gradient, pan_uv * ocean_wave_frequency);
	}
	float wave_height = height * sample.z * (gale_strenght * 1.5);
	return vec4(0.0, wave_height, 0.0, sample.r);
}

/////////// VERTEX

varying float wave_z_offset;
varying vec3 world_pos;

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;

	if (enable_ocean_waves) {
		vec2 uv_w = (MODEL_MATRIX * vec4(UV.x, 0.0, UV.y, 1.0)).xz;

		vec4 vertex;
		if (use_global_weather_controller) {
			vertex = ocean_waves(uv_w, ocean_wave_speed, ocean_wave_height, WindDirection, GaleStrength);
		} else {
			vertex = ocean_waves(uv_w, ocean_wave_speed, ocean_wave_height, non_global_wind_direction, non_global_gale_strength);
		}

		wave_z_offset = vertex.w;
		VERTEX += vertex.xyz - vec3(0.0, ocean_wave_height/2.0, 0.0);
	}
}

/////////// FRAGMENT

void fragment() {
	float effect_alpha_cover = 0.0;
	float fresnel = normal_intensity;

	// Get the view direction in world coordinates by reversing the local view direction
	vec3 view_dir_world = normalize((INV_VIEW_MATRIX * vec4(VIEW, 0.0)).xyz);
	vec3 normal_world = normalize((INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).xyz);

	// Get the eye-depth of current buffer, the depth buffer linear distance and the distance between them.
	// We'll be using them a lot.
	float frag_depth = 1.0 / FRAGCOORD.w;
	float bottom_depth = scene_depth(SCREEN_UV, INV_PROJECTION_MATRIX);
	float depth_fade = bottom_depth - frag_depth;

	// Set color to ocean depth
	// The abs() seems superfluous, but let's use it in case reliance break some user code.
	// The UNITY Synty graph use gradient sampling, but their sampling is on a black-white square-ramp gradient.
	float corrected_deep = pow(1.0 - saturate_value(depth_fade / abs(deep_height)), 1.8);
	float corrected_very_deep = pow(saturate_value(depth_fade / abs(very_deep_height)), 1.8);

	ALBEDO = mix(mix(deep_color, shallow_color, corrected_deep), very_deep_color, corrected_very_deep).xyz;


	if (enable_top_scrolling_texture) {
		ALBEDO += water_top_scrolling(UV).xyz;
	}

	if (enable_caustics) {
		ALBEDO += water_caustics(CAMERA_POSITION_WORLD,-CAMERA_DIRECTION_WORLD, view_dir_world, bottom_depth, depth_fade).xyz;
	}

	if (enable_shore_wave_foam) {
		// Shore edge masks using depth pass
		//-- we compute it here because it goes both in the alpha and in the albedo.
		float shore_edge = (1.0 - saturate_value(pow(depth_fade / shore_edge_tickness, 2.0))) * shore_edge_opacity;
		vec4 shore_edge_tint = shore_wave_color_tint * shore_edge;

		ALBEDO += water_shore_waves(world_pos, normal_world, depth_fade).xyz + shore_edge_tint.xyz;
		// make the edge opaque
		effect_alpha_cover += shore_edge_tint.r;
	}

	if (enable_shore_foam) {
		vec4 shore_foam = water_shore_foam(world_pos, normal_world, depth_fade);
		ALBEDO += shore_foam.xyz;
		// make the foam opaque
		effect_alpha_cover += shore_foam.r;
	}

	if(enable_global_foam || enable_normals) {
		fresnel = fresnel_mask(normal_world, view_dir_world);
	}

	if (enable_normals) {
		// Water noise applied twice and panned in opposite directions then overlayed
		// This is then fed into the UVs of the normal maps to create some water like distortion for the normals
		NORMAL = mix(vec3(0.0, 0.0, 1.0), water_normal(world_pos, normal_world), fresnel);
	} else {
		NORMAL = vec3(0.5, 0.5, 1.0);
	}

	if (enable_global_foam) {
		// World position sin wave generation
		float foam = ocean_foam_amount;
		float rev_foam = 5.0 - 4.0 * foam;
		float foam_amount = saturate_value(pow(wave_z_offset, rev_foam)) * foam;
		float noise_sample = top_down_projection(world_pos, normal_world, noise_texture, vec2(0.02), vec2(0.0)).r;
		float noise_amount = saturate_value(noise_sample * foam_amount * 2.0);

		float time_factor = TIME * -0.002;
		float retiling = float(ocean_breakup_tiling) * 0.01;
		float tile_sample = top_down_projection(world_pos, normal_world, noise_texture, vec2(retiling), vec2(time_factor, 2.0)).r;

		// Apply noise to the wave mask to create foam effects
		float depth_factor = saturate_value(depth_fade * 0.05) * 0.18 * tile_sample * noise_amount;
		float depth_mutl = saturate_value(pow(depth_factor * 20.0, 20.0));

		// TODO: Multiply by the fresnel mask
		float fresnel = 3.0;
		ALBEDO += depth_mutl * ocean_foam_opacity * fresnel;
	}

	// Compute the transparency: opacity - water shallow transparency + effect coverage.
	float alpha = saturate_value(base_opacity - water_transparency(shallows_opacity, depth_fade) + effect_alpha_cover);

	// Mix the alpha manually if we're using distortion.
	if (enable_distortion) {
		//ALBEDO += mix(water_distortion(UV, SCREEN_UV), very_deep_color.xyz, alpha);
		ALBEDO += mix(water_distortion(UV, SCREEN_UV), vec3(0.0, 0.0, 0.0), alpha);
	} else {
		ALPHA = alpha;
	}

	METALLIC = metallic;
	ROUGHNESS = 1.0 - smoothness;
	AO = 1.0;
}
