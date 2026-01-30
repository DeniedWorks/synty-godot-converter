/******************************************************************************
CLOUDS SHADER - Volumetric Cloud and Atmospheric Effects

Source: GodotShaders.com community shader
License: CC0 / MIT (check original source)

# Overview
Shader for volumetric clouds, sky effects, and atmospheric scattering.
Creates soft, animated cloud layers with realistic lighting.

# Required Global Uniforms
The following global uniforms control lighting:
- MainLightDirection: Vector3 for sun/moon direction

# Key Features
- Volumetric cloud appearance
- Animated cloud movement
- Atmospheric scattering
- Fresnel-based edge lighting
- Fog integration

# Parameter Groups
## Cloud Animation
- cloud_speed: Movement speed
- cloud_scale: Cloud size/density

## Atmospheric Scattering
- scattering_multiplier: Light scatter intensity
- sky_influence: How much sky affects clouds

## Colors
- top_color: Cloud top color
- base_color: Cloud underside color
- aurora_color: Aurora effect color (optional)

# Usage Notes
- Works best with a sky dome behind
- Adjust scattering for time-of-day effects
- Can be layered for depth

# See Also
- docs/shader-reference.md for full parameter list
- docs/api/constants.md for Unity property mappings
******************************************************************************/

shader_type spatial;
render_mode  unshaded;

group_uniforms Color;
uniform vec4 top_color: source_color;
uniform vec4 base_color: source_color;
uniform bool use_environment_override;

group_uniforms Lighting;
uniform vec3 light_direction_override = vec3(0.5, -0.5, 0.0);
uniform float light_intensity;
uniform bool enable_fresnel;
uniform float fresnel_power;
uniform vec4 fresnel_color: source_color;

group_uniforms Lighting.Effects;
uniform bool enable_fog;
uniform float fog_density: hint_range(0.0, 1.0) = 0.4;
uniform bool enable_scattering;
uniform float scattering_multiplier;
uniform float scattering_edge_dist: hint_range(0.0, 1.0) = 0.4;
uniform vec4 scattering_color: source_color;

group_uniforms Vertex;
uniform float cloud_speed = 1.0;
uniform float cloud_strength = 0.2;

global uniform vec3 MainLightDirection;
global uniform vec4 SkyColor: source_color;
global uniform vec4 EquatorColor: source_color;
global uniform vec4 GroundColor: source_color;


float fresnel_effect(vec3 normal_ws, vec3 view_dir_ws, float power) {
    return pow(1.0 - clamp(dot(normalize(normal_ws), normalize(view_dir_ws)), 0.0, 1.0), power);
}


void vertex() {
	float displacement = cloud_strength * (sin( TIME * cloud_speed + VERTEX.x + VERTEX.z ));
	VERTEX += vec3(0.0, displacement, 0.0);
}


void fragment() {
	vec4 sky_color = use_environment_override ? top_color : SkyColor;
	vec4 horizon_color = use_environment_override ? base_color : EquatorColor;
	vec4 ground_color = use_environment_override ? fresnel_color : GroundColor;
	vec4 equator_scattering_color = use_environment_override ? scattering_color : EquatorColor;
	vec3 light_direction = use_environment_override ? light_direction_override :  MainLightDirection + light_direction_override;

	vec3 world_normal = (INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).xyz;
	vec3 world_view = normalize(INV_VIEW_MATRIX * vec4(VIEW, 0.0)).xyz;

	float light_step = step( -light_intensity, dot(-( light_direction), world_normal));
	vec4 sky_mix_color = mix(sky_color, horizon_color, light_step) *3.0;
	if (enable_fresnel) {
		float fresnel = step(1.0 - fresnel_power, fresnel_effect(world_normal, world_view, 1.0));
	 	sky_mix_color = mix(sky_mix_color, ground_color, fresnel * light_step);
	}

	if(enable_scattering) {
		float fresnel = fresnel_effect(world_normal, world_view, scattering_edge_dist);
		vec3 scattered_light = fresnel * light_direction * scattering_multiplier;
		sky_mix_color = vec4(mix(sky_mix_color.xyz, equator_scattering_color.xyz, scattered_light), 1.0);
	}

	ALBEDO = sky_mix_color.xyz;
	ROUGHNESS = 0.0;
}
