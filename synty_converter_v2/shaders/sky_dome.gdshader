shader_type spatial;

uniform vec4 top_color: source_color = vec4(0.1, 0.6, 0.9, 1.0);
uniform vec4 bottom_color: source_color = vec4(0.05, 0.3, 0.45, 1.0);

uniform float falloff: hint_range(0.001, 100.0) = 1.0;
uniform float offset = 32.0;
uniform float distance_: hint_range(1.0, 10000.0) = 1000.0;

uniform bool enable_uv_based;

void fragment() {

	float sky_uv;
	if(enable_uv_based){
		sky_uv = UV.y;
	} else {
		vec3 world_pos = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
		sky_uv = clamp(pow((world_pos.y + offset) / min(1.0, distance_), falloff), 0.0, 1.0);
	}

	ALBEDO = mix(top_color, bottom_color, sky_uv).xyz;
	ROUGHNESS = 0.5;
	AO = 1.0;
}
