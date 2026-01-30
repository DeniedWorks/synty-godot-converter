/**************************************************************
Foliage = Synty models vegetation shader for Godot.
(C) Copyright 2025 - Giancarlo Niccolai
Published under MIT licence.
v. 1.4

# Overview

This shader is a Godot replacement for the Synty "Foliage" shader (october 2025).
Care has been taken to reproduce all the features of the original Foliage shader,
and reproduce similar visuals (inclusding noise and wind effect) for similar
settings as close as possible.

The shader incldues global shader variables that must be added to the project,
and allow to set weather settings.

Variable names and organisation match the "Foliage" Shader, for an easier
setting copy-and-paste from Unity projects.

# Installation

You'll need to create the following Global Shader Variables in the project
settings:

- WindDirection (vec3)
- WindIntensity (float)
- GaleStrength (float)

The shader variable "use_global_weather_controller" controls whether these
variables are actually used (true by default). If disabled, the Unity shader
would set reasonable defaults; this one reads the following variables (set
to the same defaults as the unity ones) instead:

- vec3 non_global_wind_direction = vec3(1.0, 0.0, 0.0);
- float non_global_wind_intensity: hint_range(0.0, 1.0) = 0.2;
- float non_global_gale_strength: hint_range(0.0, 1.0)  = 0.2;

# Noise and tint settings

Trunks and leaves have noise and tint settings that can alter the base
albedo texture.

Leaves and trunks can be colorised using either:

- A texture
- A noise pattern which will refence either a source texture or a flat matte.
- A flat color.

This behavior matches the reference Unity Synty/Foliage shader.

## Noise

If the _use color noise_ setting is active, a cloud-like noise is
applied to both leaves and trunks.

For leaves, the leaves_base_color is perturbed with two level of noises;
the final noise is then either mixed with the leaves texture, or applied
directly to the leaves mesh when _leaf flat color_ is active.

The same is done with truks but there is only one level of noise applied.

Notice that the noise is applied in world space: this makes patches of
vegetation to look more natural, as the noise is applied to the whole
patch as a unit rather than to single assets.

## Flat Color

If _use color noise_ is not active, it is possible to apply a tint on
leaves and trunks using _leaf flat color_ and _trunk flat color_.


# Gale settings

_Gale_ values provide a very subtle waving of small foliage (as grass), barely noticeable
in larger models. However, they are fed-back into the _strong wind_ settings, so they
influence more than proportionally the appearence in _strong wind_.

They can't be controlled at mesh level, as they are available as global weather settings
only.

The behavior matches the Unity shader.

# Breeze Settings

Breeze provides a wavering ripple in the foliage. The visual effect as seen in the Unity
shader has been replicated as closely as possible, but there are some sublte differences,
due to the slightly different shape of the high-performance three octave noise employed
here. For small breeze settings, the difference shouldn't be noticeable at all.

# Light wind settings

The _light wind_ setting changes the foliage to simulate wind moving and blowing grass,
bushes and tree canopies. They won't affect trunk parts. At extremely high values, the
meshes may be unnaturally deformed (same as in the Unity shader).

# Strong wind settings

The _strong wind_ setting apply a sinusoidal X-Y stretch on the whole mesh around the
pivot point, making trees to rock back and forth, and/or twist around the Y axis.
Gale settings are fed in the X-Y movement making the gale effect less sublte, so you
may want to revise high gale settings when applying high strong wind settings.

The X-Y deformation is around the pivot point. Some meshes have the pivot point at their
base, with their roots below it, which means the root will swing back in those models;
if you plan to use high levels of _strong wind_, take care to place tree assets on the
ground at their pivot point.

At extremely high values, the meshes may be unnaturally deformed (same as in the Unity
shader).

# Frosting

The settings in _frosting_ give a different coloration on top of the foliage. The
behavior matches the Unity Shader.

# Emission

Trunk and foliage emission setting are separate; copying the structure of the Unity
shader, Trunk emission settings are within the _Trunk_ section, while the foliage
emission settings are completely separate in their own _Emission_ section.

_Pulse_ settings apply to the foliage emission only.

## Notes

- This shader applies to vertex-color encoded meshes:
  - Red = Height gradient;
  - Green = Leaf tip gradient;
  - Blue = Leaf Mask; (blue > 0.5 is leaf, otherwise is trunk).
  - Alpha = All.

- Unity rendering pipeline has support for ignoring the direction
  of the normal of flat meshes; many meshes meant to be double-faced
  are imported from FBXs to Unity without caring for their
  normal direction. Godot has a partial support for that (not culling
  the back-faces), but the back-face would still be rendered differently.
  The setting 'mesh_single_faced' (defalut true) make the NORMAL of the
  target mesh absolute, so that both faces of the target mesh are rendered
  exactly the same even if the original mesh wasn't prepared for that.
  This is useful for grass and similar meshes.

***************************************************************/

shader_type spatial;
render_mode blend_mix, depth_draw_opaque, depth_prepass_alpha, cull_disabled, diffuse_lambert, specular_schlick_ggx;

const vec3 DEFAULT_WIND_DIRECTION = vec3(1.0, 0.0, 0.0);
const float DEFAULT_WIND_INTENSITY = 0.2;
const float DEFAULT_GALE_STRENGTH = 0.2;

group_uniforms General;
uniform float alpha_clip_threshold : hint_range(0.0, 1.0) = 0.25;
uniform bool mesh_single_faced = true;
uniform bool use_color_noise = false;
uniform float color_noise_small_freq = 9.0;
uniform float color_noise_large_freq = 1.0;

group_uniforms Leaf;
uniform sampler2D leaf_color : source_color, filter_linear_mipmap;
uniform vec2 leaf_tiling = vec2(1.0, 1.0);
uniform vec2 leaf_offset = vec2(0.0, 0.0);
uniform float leaf_metallic : hint_range(0.0, 1.0) = 0.0;
uniform float leaf_smoothness : hint_range(0.0, 1.0) = 0.20;

group_uniforms Leaf.Tint;
uniform vec4 leaf_base_color : source_color = vec4(1.0);
uniform vec4 leaf_noise_color : source_color = vec4(1.0);
uniform vec4 leaf_noise_large_color : source_color = vec4(1.0);
uniform bool leaf_flat_color = false;

group_uniforms Leaf.Normal;
uniform bool enable_leaf_normal = false;
uniform sampler2D leaf_normal : hint_normal, filter_linear_mipmap;
uniform vec2 leaf_normal_tiling = vec2(1.0, 1.0);
uniform vec2 leaf_normal_offset = vec2(0.0, 0.0);
uniform float leaf_normal_strength : hint_range(0.0, 1.0) = 0.5;

group_uniforms Leaf.AmbientOcclusion;
uniform sampler2D leaf_ao : source_color, filter_linear_mipmap;
uniform float leaf_ao_intensity : hint_range(0.0, 1.0) = 0.5;

group_uniforms Trunk;
uniform sampler2D trunk_color : source_color, filter_linear_mipmap;
uniform vec2 trunk_tiling = vec2(1.0, 1.0);
uniform vec2 trunk_offset = vec2(0.0, 0.0);
uniform float trunk_metallic : hint_range(0.0, 1.0) = 0.0;
uniform float trunk_smoothness : hint_range(0.0, 1.0) = 0.20;

group_uniforms Trunk.Tint;
uniform vec4 trunk_base_color : source_color = vec4(1.0);
uniform vec4 trunk_noise_color : source_color = vec4(1.0);
uniform bool trunk_flat_color = false;

group_uniforms Trunk.Emission;
uniform vec4 trunk_emissive_color: source_color = vec4(0.0);
uniform sampler2D trunk_emissive_mask : source_color, filter_linear_mipmap;
uniform vec2 trunk_emissive_tiling = vec2(1.0, 1.0);
uniform vec2 trunk_emissive_offset = vec2(0.0, 0.0);


group_uniforms Trunk.Normal;
uniform bool enable_trunk_normal = false;
uniform sampler2D trunk_normal : hint_normal, filter_linear_mipmap;
uniform vec2 trunk_normal_tiling = vec2(1.0, 1.0);
uniform vec2 trunk_normal_offset = vec2(0.0, 0.0);
uniform float trunk_normal_strength : hint_range(0.0, 1.0) = 0.5;

group_uniforms Trunk.AmbientOcclusion;
uniform sampler2D trunk_ao : source_color, filter_linear_mipmap;
uniform float trunk_ao_intensity : hint_range(0.0, 1.0) = 0.5;

group_uniforms Frosting;
uniform bool enable_frosting = false;
uniform vec4 frosting_color: source_color = vec4(0.0);
uniform float frosting_falloff = 1.0;
uniform float frosting_height = 2.8;
uniform bool frosting_use_world_normal = false;

group_uniforms Emission;
uniform bool enable_emission = false;
uniform vec4 emissive_color: source_color = vec4(0.0);
uniform vec4 emissive_2_color: source_color = vec4(0.0);
uniform sampler2D emissive_mask : source_color, filter_linear_mipmap;
uniform vec2 emissive_tiling = vec2(1.0, 1.0);
uniform vec2 emissive_offset = vec2(0.0, 0.0);
uniform sampler2D emissive_2_mask : source_color, filter_linear_mipmap;
uniform vec2 emissive_2_tiling = vec2(1.0, 1.0);
uniform vec2 emissive_2_offset = vec2(0.0, 0.0);
uniform float emissive_amount: hint_range(0.0, 2.0) = 0.0;

group_uniforms Emission.Pulse;
uniform bool enable_pulse = false;
uniform sampler2D emissive_pulse_mask : source_color, filter_linear_mipmap;
uniform float emissive_pulse_tiling = 0.03;
uniform float emissive_pulse_speed = 0.0;

group_uniforms Wind;
uniform bool use_vertex_color_wind = false;
uniform bool use_global_weather_controller = true;

group_uniforms Wind.Breeze;
uniform bool enable_breeze = false;
uniform float breeze_strength : hint_range(0.0, 1.0) = 0.2;

group_uniforms Wind.LightWind;
uniform bool enable_light_wind = false;
uniform float light_wind_strength : hint_range(0.0, 1.0) = 0.2;
uniform float light_wind_y_strength : hint_range(0.0, 1.0) = 1.0;
uniform float light_wind_y_offset : hint_range(0.0, 1.0) = 0.0;
uniform bool light_wind_use_leaf_fade = false;

group_uniforms Wind.StrongWind;
uniform bool enable_strong_wind = false;
uniform float strong_wind_strength : hint_range(0.0, 1.0) = 0.2;
uniform float strong_wind_frequency : hint_range(0.0, 1.0) = 0.5;

group_uniforms Wind.WindTwist;
uniform bool enable_wind_twist = false;
uniform float wind_twist_strength : hint_range(0.0, 2.0) = 0.15;
uniform float gale_blend : hint_range(0.0, 2.0) = 1.0;

////////// GLOBALS //////////

global uniform vec3 WindDirection;
global uniform float WindIntensity;
global uniform float GaleStrength;

group_uniforms Wind.LocalDefaults;
// These are overriding the local defaults, not applying on the globals if set.
// The name non_global makes it clear -- local_ may be ambiguous.
uniform vec3 non_global_wind_direction = vec3(1.0, 0.0, 0.0); // DEFAULT_WIND_DIRECTION
uniform float non_global_wind_intensity: hint_range(0.0, 1.0) = 0.2; // DEFAULT_WIND_INTENSITY
uniform float non_global_gale_strength: hint_range(0.0, 1.0)  = 0.2; // DEFAULT_GALE_Strength


////////// FUNCTIONS //////////


// Unity-exact hash (2D dot product for better distribution than 1D)
float unity_noise_randomValue(vec2 uv) {
    return fract(sin(dot(uv, vec2(12.9898, 78.233))) * 43758.5453);
}

// Linear interpolation (used after cubic fade)
float unity_noise_interpolate(float a, float b, float t) {
    return (1.0 - t) * a + (t * b);
}

// Single-octave value noise (Unity's base layer)
float unity_valueNoise(vec2 uv) {
    vec2 i = floor(uv);
    vec2 f = fract(uv);
    f = f * f * (3.0 - 2.0 * f);  // Cubic Hermite fade

    // Note: Unity code has "uv = abs(fract(uv) - 0.5);" here, but it's unused (relic?); omit for standard value noise

    vec2 c0 = i + vec2(0.0, 0.0);
    vec2 c1 = i + vec2(1.0, 0.0);
    vec2 c2 = i + vec2(0.0, 1.0);
    vec2 c3 = i + vec2(1.0, 1.0);

    float r0 = unity_noise_randomValue(c0);
    float r1 = unity_noise_randomValue(c1);
    float r2 = unity_noise_randomValue(c2);
    float r3 = unity_noise_randomValue(c3);

    float bottom = unity_noise_interpolate(r0, r1, f.x);
    float top = unity_noise_interpolate(r2, r3, f.x);
    return unity_noise_interpolate(bottom, top, f.y);
}

// Unity Simple Noise: 3-octave fBm (key to patchiness—adds fine spots on coarse base)
float three_octaves_noise(vec2 uv, float scale) {
    float t = 0.0;
    for (int octave = 0; octave < 3; octave++) {
        float freq = pow(2.0, float(octave));  // 1, 2, 4
        float amp = pow(0.5, float(3 - octave));  // 0.125, 0.25, 0.5
        t += unity_valueNoise(uv * (scale / freq)) * amp;
    }
    return t;  // ~[0, 0.875]
}


// Hash for Simple 2D.
float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

// Simple 2D value noise (closest to Unity's Simple Noise: pseudo-random value noise)
float simple_noise(vec2 uv) {
    vec2 i = floor(uv);
    vec2 f = fract(uv);

    // Four corners
    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));

    // Smooth interpolation (cubic Hermite)
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(a, b, u.x) + (c - a) * u.y * (1.0 - u.x) + (d - b) * u.x * u.y;
}

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

// Rodrigues' formula for rotation around arbitrary axis
vec3 rotate_around_axis(vec3 v, vec3 axis, float angle_rad) {
	axis = normalize(axis);
	float s = sin(angle_rad);
	float c = cos(angle_rad);
	float oc = 1.0 - c;

	vec3 rotated = vec3(
		(axis.x * axis.x * oc + c) * v.x + (axis.x * axis.y * oc - axis.z * s) * v.y + (axis.x * axis.z * oc + axis.y * s) * v.z,
		(axis.y * axis.x * oc + axis.z * s) * v.x + (axis.y * axis.y * oc + c) * v.y + (axis.y * axis.z * oc - axis.x * s) * v.z,
		(axis.z * axis.x * oc - axis.y * s) * v.x + (axis.z * axis.y * oc + axis.x * s) * v.z + (axis.z * axis.z * oc + c) * v.z
	);
	return rotated;
}

// Helper: RGB to HSV
vec3 rgb2hsv(vec3 c) {
	vec4 K = vec4(0.0, -1.0 / 3.0, 2.0 / 3.0, -1.0);
	vec4 p = mix(vec4(c.bg, K.wz), vec4(c.gb, K.xy), step(c.b, c.g));
	vec4 q = mix(vec4(p.xyw, c.r), vec4(c.r, p.yzx), step(p.x, c.r));
	float d = q.x - min(q.w, q.y);
	float e = 1.0e-10;
	return vec3(abs(q.z + (q.w - q.y) / (6.0 * d + e)), d / (q.x + e), q.x);
}

// Helper: HSV to RGB
vec3 hsv2rgb(vec3 c) {
	vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
	vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
	return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

vec3 saturation(vec3 color, float sat) {
	vec3 hsv = rgb2hsv(color);
	hsv.y = clamp(hsv.y * (1.0 + sat), 0.0, 1.0);  // Adjust saturation
	return hsv2rgb(hsv);
}


vec3 make_glade(vec3 vertex, vec3 wind_direction, float gale_strength, float vertical_gradient) {
	// Bend meshes to gale strength and oscillate the bend.
	float gale_displacement = (sin(TIME) * 0.5 + 0.5)
		* (20.0 * gale_strength)
		+ 50.0 * gale_strength;
	vec3 rotated_vertex = rotate_around_axis(vertex, wind_direction, gale_displacement / 180.0 * PI);
	return mix(vertex, rotated_vertex, vertical_gradient * gale_blend);
}

vec3 make_strong_wind(vec3 vertex, vec3 wind_direction, vec3 blended_gale, float gale_strength) {
	// Calculate strong wind and its twist.
	// In most cases, we have both disabled, so we deserve an early exit.
	if (! (enable_strong_wind || enable_wind_twist)) {
		return blended_gale;
	}

	vec3 strong_wind;
	float twist_pos = vertex.x + vertex.z + TIME;
	if(enable_strong_wind) {
		float frequency = (gale_strength + 2.0) * 1.5 * strong_wind_frequency;
		strong_wind = sin(twist_pos * frequency) * (strong_wind_strength * 5.0) * wind_direction;
		strong_wind += blended_gale;
	}
	else {
		strong_wind = blended_gale;
	}

	if(enable_wind_twist) {
		float twist_factor = sin(twist_pos * strong_wind_frequency) * wind_twist_strength;
		strong_wind = rotate_around_y(strong_wind, twist_factor);
	}

	return strong_wind;
}


vec3 make_light_wind(vec3 vertex, vec3 normal, vec4 color, vec3 wind_direction, float gale_strength) {
	if (! enable_light_wind){
		return vec3(0.0);
	}

	float remapped_gale_strength = gale_strength * 0.75 + 0.25;
	float time_gale_factor = remapped_gale_strength * 0.2 * TIME;
	vec3 counter_sway = wind_direction * vec3(-1) * time_gale_factor;
	vec3 position_factor = vertex * vec3(0.01);
	vec3 light_wind_base = counter_sway + position_factor;

	float noise_value = simple_noise(vec2(light_wind_base.x, light_wind_base.z) * 50.0);
	float corrected_noise = (noise_value - (light_wind_y_offset * 0.5)) * 0.5; // was * 2 in UNITY,

	vec3 normal_strength = normal * vec3(1.0, light_wind_y_strength, 1.0) * corrected_noise;
	vec3 strength = (light_wind_strength * 3.0) * normal_strength;
	strength *= light_wind_use_leaf_fade ? color.g : color.b;
	return strength;
}

vec3 make_breeze(vec3 vertex, vec3 normal, vec4 color, vec3 wind_direction, float gale_strength) {
	if(! enable_breeze) {
		return vec3(0.0);
	}

	vec3 time_factor = vertex * vec3(10.0) + TIME * wind_direction;
	float noise_value = three_octaves_noise(vec2(time_factor.x, time_factor.z), 10.0);
	float corrected_noise = (noise_value - 0.5) * 2.0;
	vec3 normal_noise = normal * corrected_noise;

	float remapped_gale = gale_strength * 2.0 + 2.0; // remamp 0..1 -> 2..4
	vec3 gale = vec3(breeze_strength, 0.0, breeze_strength) * remapped_gale;

	return gale * normal_noise * color.g;
}

vec4 leaf_emissive(vec2 uv) {
	float value_1 = texture(emissive_mask, (uv * emissive_tiling) + emissive_offset).b;
	float value_2 = texture(emissive_2_mask, (uv * emissive_2_tiling) + emissive_2_offset).b;
	vec4 emissive_1 = mix(emissive_color, vec4(0.0), 1.0 - value_1);
	vec4 emissive_2 = mix(emissive_2_color, vec4(0.0), 1.0 - value_2);
	return emissive_1 + emissive_2;
}

vec4 trunk_emissive(vec2 uv) {
	float value = texture(trunk_emissive_mask, (uv * trunk_emissive_tiling) + trunk_emissive_offset).b;
	return mix(trunk_emissive_color, vec4(0.0), 1.0 - value);
}

vec4 compute_leaf_noise(vec3 vertex) {
	float small_noise_level = three_octaves_noise(vec2(vertex.x, vertex.z), color_noise_small_freq);
	float large_noise_level = three_octaves_noise(vec2(vertex.x, vertex.z), color_noise_large_freq);

	vec4 small_noise_color = mix(leaf_noise_color, leaf_base_color, small_noise_level);
	vec4 large_noise_color = mix(small_noise_color, leaf_noise_large_color, large_noise_level);
	return large_noise_color;
}

vec4 compute_trunk_noise(vec3 vertex) {
	float noise_level = three_octaves_noise(vec2(vertex.x, vertex.z), color_noise_small_freq);
	return mix(trunk_noise_color, trunk_base_color, noise_level);
}

vec3 compute_pulse(vec3 vertex, vec2 uv) {
	vec3 time_factor = saturation(sin(vertex * 0.5 + TIME * 4.0), 0.0);
	vec2 pulse_uv = uv * emissive_pulse_tiling + emissive_pulse_speed * TIME;
	float pulse_value = texture(emissive_pulse_mask, pulse_uv).r;

	float pulse_r = clamp(max(time_factor.x, pulse_value), 0.0, 1.0);
	float pulse_g = clamp(max(time_factor.y, pulse_value), 0.0, 1.0);
	float pulse_b = clamp(max(time_factor.z, pulse_value), 0.0, 1.0);
	vec3 pulse_power = vec3(pulse_r, pulse_g, pulse_b);

	return pulse_power * 0.5 + 0.5;  // remap 0 : 1 -> 0.5 : 1
}

vec3 triplanar_map(vec3 x, vec3 y, vec3 z, vec3 n) {
	n = n*n;
    return (x*n.x + y*n.y + z*n.z)/(n.x+n.y+n.z);
}

////////////////// VERTEX


varying vec3 world_vertex;
varying vec3 world_normal;
varying vec3 local_normal;


void vertex() {
	// We are working in world coordinates, so we don't need to globalise the model by unwinding the rotation.

	// Get Weather Control Data.
	vec3 wind_direction;
	float gale_strength;
	float wind_intensity;

	mat3 local_model = transpose(mat3(MODEL_MATRIX));
	if (use_global_weather_controller) {
		wind_direction = normalize(WindDirection * local_model);
		gale_strength = GaleStrength;
		wind_intensity = clamp(WindIntensity, 0.0, 1.0);
	} else {
		wind_direction = normalize(non_global_wind_direction * local_model);
		gale_strength = non_global_gale_strength;
		wind_intensity = non_global_wind_intensity;
	}

	float height_gradient = COLOR.r;

	vec3 blended_gale;
	// Skip some pretty complicated logic if we don't need gale.
	if(gale_strength > 0.0) {
		// Gale has a very subtle effect, barely noticeable in bushes when you approach them.
		// It has also a feedback in the strong wind, so that it's not canceled under it.
		blended_gale = make_glade(VERTEX, wind_direction, gale_strength, height_gradient);
	} else {
		blended_gale = VERTEX;
	}

	world_vertex = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	local_normal = NORMAL;
	world_normal = (MODEL_MATRIX * vec4(NORMAL, 0.1)).xyz;

	// Strong wind wants the global rendered object origin, not the vertex position.
	vec3 strong_wind = make_strong_wind(MODEL_MATRIX[3].xyz, wind_direction, blended_gale, gale_strength);
	vec3 light_wind = make_light_wind(world_vertex, world_normal, COLOR, wind_direction, gale_strength);
	vec3 breeze = make_breeze(world_vertex, world_normal, COLOR, wind_direction, gale_strength);

	vec3 wind_component = strong_wind + light_wind + breeze;

	float gale_factor = use_vertex_color_wind ? height_gradient : VERTEX.y * 0.5;
	vec3 wind_and_gale = mix(blended_gale, wind_component, gale_factor);

	VERTEX = mix(VERTEX, wind_and_gale, wind_intensity);  // Object
}


/////// FRAGMENT
void fragment() {
	// Meshes are painted with a high blue value if they are leaves; else they are trunks.

	vec3 emission = vec3(0.0);
	if (COLOR.b > 0.5) {

		// Noise and base
		vec4 texture_color = texture(leaf_color, (UV * leaf_tiling) + leaf_offset);
		float texture_alpha = texture_color.a;

		if (leaf_flat_color) {
			texture_color.rgb = leaf_base_color.rgb;
		}

		if (use_color_noise) {
			vec4 noise_color = compute_leaf_noise(world_vertex);
			if(leaf_flat_color) {
				texture_color = noise_color;
			} else {
				texture_color *= noise_color;
			}
		}

		// Frosting
		if(enable_frosting) {
			vec3 normal = frosting_use_world_normal ? world_normal : local_normal;
			float frost_level = clamp(pow(normal.y, frosting_height) * frosting_falloff, 0.0, 1.0);
			texture_color = mix(texture_color, frosting_color, frost_level);
		}

		ALBEDO = texture_color.xyz;
		ALPHA = texture_alpha;
		METALLIC = leaf_metallic;
		ROUGHNESS = 1.0 - leaf_smoothness;
		AO = mix(1, texture(leaf_ao, UV * leaf_tiling + leaf_offset).r, leaf_ao_intensity);

		if (enable_leaf_normal) {
			BINORMAL = triplanar_map(
				normalize((VIEW_MATRIX * vec4(0.,-1.,0.,0)).xyz),
				normalize((VIEW_MATRIX * vec4(0.,0.,1.,0)).xyz),
				normalize((VIEW_MATRIX * vec4(0,-1.,0.,0)).xyz),
				world_normal
			);

			TANGENT = triplanar_map(
				normalize((VIEW_MATRIX * vec4(0.,1.,0.,-1.)).xyz),
				normalize((VIEW_MATRIX * vec4(1.,0.,0.,1.)).xyz),
				normalize((VIEW_MATRIX * vec4(0,0.,1.,-1.)).xyz),
				world_normal
			);
			NORMAL_MAP = texture(leaf_normal, (UV * leaf_normal_tiling) + leaf_normal_offset).rgb * leaf_normal_strength;
		}

		if (enable_emission) {
			EMISSION = leaf_emissive(UV).rgb * emissive_amount * 1.5;
		}
	} else {
		vec4 texture_color = texture(trunk_color, (UV * trunk_tiling) + trunk_offset);
		float texture_alpha = texture_color.a;

		if (trunk_flat_color) {
			texture_color.rgb = trunk_base_color.rgb;
		}

		if (use_color_noise) {
			vec4 noise_color = compute_trunk_noise(world_vertex);
			if(trunk_flat_color) {
				texture_color = noise_color;
			} else {
				texture_color *= noise_color;
			}
		}

		ALBEDO = texture_color.rgb;
		ALPHA = texture_alpha;
		METALLIC = trunk_metallic;
		ROUGHNESS = 1.0 - trunk_smoothness;
		AO = mix(1, texture(trunk_ao, UV * trunk_tiling + trunk_offset).r, trunk_ao_intensity);

		if (enable_trunk_normal) {
			BINORMAL = triplanar_map(
				normalize((VIEW_MATRIX * vec4(0.,-1.,0.,0)).xyz),
				normalize((VIEW_MATRIX * vec4(0.,0.,1.,0)).xyz),
				normalize((VIEW_MATRIX * vec4(0,-1.,0.,0)).xyz),
				world_normal
			);

			TANGENT = triplanar_map(
				normalize((VIEW_MATRIX * vec4(0.,1.,0.,-1.)).xyz),
				normalize((VIEW_MATRIX * vec4(1.,0.,0.,1.)).xyz),
				normalize((VIEW_MATRIX * vec4(0,0.,1.,-1.)).xyz),
				world_normal
			);

			NORMAL_MAP = texture(trunk_normal, (UV * trunk_normal_tiling) + trunk_normal_offset).rgb * trunk_normal_strength;
		}

		if (enable_emission) {
			EMISSION = trunk_emissive(UV).rgb * emissive_amount * 1.5;
		}
	}

	if (enable_pulse) {
		EMISSION *= compute_pulse(world_vertex, UV);
	}

	if(mesh_single_faced && !FRONT_FACING) {
		NORMAL = -NORMAL;
	}

	ALPHA_SCISSOR_THRESHOLD = alpha_clip_threshold;
}
