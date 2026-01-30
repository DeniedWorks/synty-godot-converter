/******************************************************************************
SKYDOME SHADER - Sky Gradient and Atmosphere

Source: GodotShaders.com community shader
License: CC0 / MIT (check original source)

# Overview
Simple gradient shader for sky domes and backgrounds.
Creates smooth color transitions from horizon to zenith.

# Required Global Uniforms
Optional global uniforms for dynamic sky:
- SkyColor: Top sky color override
- EquatorColor: Horizon color override
- GroundColor: Below-horizon color override

# Key Features
- 3-color gradient (sky, horizon, ground)
- World-space or UV-based coordinates
- Smooth falloff control
- Integrates with global sky system

# Parameter Groups
## Sky Colors
- top_color: Zenith/overhead sky color
- equator_color: Horizon color
- ground_color: Below-horizon color

## Gradient Control
- falloff: Gradient sharpness
- offset: Horizon position adjustment
- distance: Gradient distance scale

# Usage Notes
- Apply to a sky dome mesh (inverted sphere/hemisphere)
- Set render priority to background
- Adjust falloff: 1.0 for smooth, higher for sharper transitions
- Works with WorldEnvironment sky settings

# See Also
- docs/shader-reference.md for full parameter list
- docs/api/constants.md for Unity property mappings
******************************************************************************/

/******************************************************************
SkyDome = Synty models sky dome shader for Godot.
(C) Copyright 2025 - Giancarlo Niccolai
Published under MIT licence.

# Overview

Synty assets use this shader for sky domes in demo scenes. They sky
dome is also quite practical for a simple, cartoon-style sky, and
can be applied to various Godot sky types.

# Behavior

The shader can either use world UV coordinates, blending the top color smootly into
the bottom, or use  arbitrary distance to paint a skydome.

The behavior mimics the same shader in Unity.
*/


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
