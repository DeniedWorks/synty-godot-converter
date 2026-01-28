shader_type spatial;
render_mode blend_mix;

uniform float alpha_clip_treshold: hint_range(0.0, 1.0) = 0.5;
uniform vec4 base_color: source_color = vec4(1.0);
uniform sampler2D albedo_map: source_color, filter_linear_mipmap;
uniform vec2 tiling = vec2(1.0);
uniform vec2 offset = vec2(0.0);

uniform bool enable_soft_particles = true;
uniform float soft_power: hint_range(0.0, 10.0) = 2.0;
uniform float soft_distance: hint_range(0.0, 2.0) = 0.1;
uniform bool use_view_edge_compensation = false;
uniform float view_edge_power = 1.0;
uniform bool enable_camera_fade = false;
uniform float camera_fade_near = 0.0;
uniform float camera_fade_far = 20.0;
uniform float camera_fade_smoothness: hint_range(0.0, 100.0) = 1.5;
uniform bool enable_scene_fog = false;

uniform sampler2D DEPTH_TEXTURE : hint_depth_texture, filter_linear_mipmap;

uniform vec4 fog_color = vec4(1.0, 1.0, 1.0, 0.0);

float scene_depth(vec2 screen_uv, mat4 inv_prj) {
	float raw_depth = texture(DEPTH_TEXTURE, screen_uv).r;

    vec3 ndc;
    #if CURRENT_RENDERER == RENDERER_COMPATIBILITY
    ndc = vec3(screen_uv * 2.0 - 1.0, raw_depth * 2.0 - 1.0);
    #else
    ndc = vec3(screen_uv * 2.0 - 1.0, raw_depth);
    #endif

    vec4 view_pos = inv_prj * vec4(ndc, 1.0);
    view_pos.xyz /= view_pos.w;
	return -view_pos.z;
}

float remap(float value, vec2 in_minmax, vec2 out_minmax) {
    return out_minmax.x + (value - in_minmax.x) * (out_minmax.y - out_minmax.x) / (in_minmax.y - in_minmax.x);
}

void fragment() {

	vec3 pos_world = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float cam_dist = length(pos_world - CAMERA_POSITION_WORLD);
	float eye_depth = scene_depth(SCREEN_UV, INV_PROJECTION_MATRIX);

	if (use_view_edge_compensation) {
		float view_edge_comp = view_edge_power * (1.0 - VIEW.z);
		eye_depth += view_edge_comp;
	}

	float soft_fade = 1.0;
	if(enable_soft_particles) {
		soft_fade = pow(clamp((eye_depth - cam_dist) * (soft_distance / 10.0), 0.0, 1.0), soft_power);
	}

	float camera_fade = 1.0;
	if (enable_camera_fade) {
		float camera_near = remap(cam_dist, vec2(camera_fade_near, camera_fade_near * camera_fade_smoothness), vec2(0.0, 1.0));
		float camera_far = remap(cam_dist, vec2(camera_fade_far * camera_fade_smoothness, camera_fade_far), vec2(0.0, 1.0));
		camera_fade = clamp(camera_near, 0.0, 1.0) * clamp(camera_far, 0.0, 1.0);
	}

	float fade_factor = soft_fade * camera_fade;
	vec4 albedo_color = base_color * texture(albedo_map, UV * tiling + offset);
	float albedo_alpha = albedo_color.a;
	float alpha = albedo_alpha * fade_factor * COLOR.a;
	if (alpha < alpha_clip_treshold) discard;

	if (enable_scene_fog) {
		albedo_color = mix(fog_color, albedo_color, fog_color.a);
	}

	ALBEDO = albedo_color.rgb;
	ALPHA = alpha;
	ROUGHNESS = 1.0;
}
