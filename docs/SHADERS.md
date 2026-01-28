# Synty Shaders Documentation

This document describes the 8 Godot shaders included with the Synty Converter v2. All shaders are ports of Unity Synty shaders, available from [godotshaders.com](https://godotshaders.com).

## Shader Sources

| Shader File | Source URL |
|-------------|-----------|
| polygon_shader.gdshader | https://godotshaders.com/shader/synty-polygon-drop-in-replacement-for-polygonshader/ |
| foliage.gdshader | https://godotshaders.com/shader/synty-core-drop-in-foliage-shader/ |
| water.gdshader | https://godotshaders.com/shader/synty-core-drop-in-water-shader/ |
| refractive_transparent.gdshader | https://godotshaders.com/shader/synty-refractive_transparent-crystal-shader/ |
| clouds.gdshader | https://godotshaders.com/shader/synty-core-drop-in-clouds-shader/ |
| sky_dome.gdshader | https://godotshaders.com/shader/synty-polygon-drop-in-replacement-for-skydome-shader/ |
| particles_unlit.gdshader | https://godotshaders.com/shader/synty-core-drop-in-particles-shader-generic_particlesunlit/ |
| biomes_tree.gdshader | https://godotshaders.com/shader/synty-biomes-tree-compatible-shader/ |

---

## 1. polygon_shader.gdshader

**Purpose:** Standard material shader for static Synty assets. Provides base texturing, triplanar mapping, emission, ambient occlusion, and snow effects.

**Author:** Giancarlo Niccolai (MIT License, v1.1)

**Render Mode:** `blend_mix, depth_draw_opaque, cull_back`

### Uniform Parameters

#### Base Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `color_tint` | vec4 (color) | (1,1,1,1) | Overall color multiplier |
| `metallic` | float [0-1] | 0.0 | Metallic factor |
| `smoothness` | float [0-1] | 0.0 | Smoothness (inverse roughness) |
| `metallic_smoothness_texture` | sampler2D | - | Combined metallic/smoothness texture |
| `uv_pan` | vec2 | (0,0) | UV animation panning speed |

#### Base Texture Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_base_texture` | bool | true | Enable base albedo texture |
| `base_texture` | sampler2D | - | Base albedo texture |
| `base_tiling` | vec2 | (1,1) | UV tiling |
| `base_offset` | vec2 | (0,0) | UV offset |

#### Normal Texture Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_normal_texture` | bool | true | Enable normal mapping |
| `normal_texture` | sampler2D | - | Normal map |
| `normal_intensity` | float [0-2] | 1.0 | Normal strength |
| `normal_tiling` | vec2 | (1,1) | Normal UV tiling |
| `normal_offset` | vec2 | (0,0) | Normal UV offset |

#### Emission Texture Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_emission_texture` | bool | false | Enable emission |
| `emission_texture` | sampler2D | - | Emission map |
| `emission_tiling` | vec2 | (1,1) | Emission UV tiling |
| `emission_offset` | vec2 | (0,0) | Emission UV offset |
| `emission_color_tint` | vec4 (color) | (1,1,1,1) | Emission color multiplier |

#### Ambient Occlusion Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_ambient_occlusion` | bool | false | Enable AO |
| `ao_intensity` | float [0-5] | 1.0 | AO strength |
| `ao_texture` | sampler2D | - | AO texture |
| `ao_tiling` | vec2 | (1,1) | AO UV tiling |
| `ao_offset` | vec2 | (0,0) | AO UV offset |
| `generate_from_base_normals` | bool | false | Generate AO from normal map |

#### Overlay Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_overlay_texture` | bool | false | Enable overlay (selection/highlight) |
| `overlay_texture` | sampler2D | - | Overlay texture |
| `overlay_tiling` | vec2 | (1,1) | Overlay UV tiling |
| `overlay_offset` | vec2 | (0,0) | Overlay UV offset |
| `overlay_uv_channel` | int [1-4] | 1 | UV channel to use |
| `overlay_intensity` | float [0-1] | 1.0 | Overlay blend strength |

#### Triplanar Base Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_triplanar_texture` | bool | false | Enable triplanar projection |
| `triplanar_texture_top` | sampler2D | - | Top projection texture |
| `triplanar_texture_side` | sampler2D | - | Side projection texture |
| `triplanar_texture_bottom` | sampler2D | - | Bottom projection texture |
| `triplanar_tiling_*` | vec2 | (1,1) | Tiling per direction |
| `triplanar_offset_*` | vec2 | (0,0) | Offset per direction |
| `triplanar_top_to_side_difference` | float [0-1] | 0.5 | Blend bias |
| `triplanar_fade` | float [0-1] | 0.5 | Edge fade sharpness |
| `triplanar_intensity` | float [0-1] | 1.0 | Triplanar blend strength |
| `top_metallic`, `side_metallic`, `bottom_metallic` | float [0-1] | 0.0 | Per-direction metallic |
| `top_smoothness`, `side_smoothness`, `bottom_smoothness` | float [0-1] | 0.0 | Per-direction smoothness |

#### Triplanar Normal Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_triplanar_normals` | bool | false | Enable triplanar normals |
| `triplanar_normal_top/bottom/side` | sampler2D | - | Normal maps per direction |
| `triplanar_normal_intensity_*` | float [0-1] | 1.0 | Normal strength per direction |
| `triplanar_normal_tiling_*` | vec2 | (1,1) | Tiling per direction |
| `triplanar_normal_fade` | float [0-128] | 10.0 | Normal blend sharpness |

#### Triplanar Emission Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_triplanar_emission` | bool | false | Enable triplanar emission |
| `triplanar_emission_texture` | sampler2D | - | Emission texture |
| `triplanar_emission_tiling` | float | 1.0 | Emission tiling |
| `triplanar_emission_blend` | float [0-50] | 4.0 | Emission blend sharpness |
| `triplanar_emission_intensity` | float [0-50] | 1.0 | Emission strength |
| `triplanar_emission_color_tint` | vec4 (color) | (1,1,1,1) | Emission color |

#### Snow Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_snow` | bool | false | Enable snow overlay |
| `snow_use_world_up` | bool | true | Use world Y for snow direction |
| `snow_color` | vec4 (color) | (1,1,1,1) | Snow color |
| `snow_metallic` | float [0-1] | 0.0 | Snow metallic |
| `snow_smoothness` | float [0-1] | 0.8 | Snow smoothness |
| `snow_level` | float [0-1] | 0.5 | Snow coverage amount |
| `snow_transition` | float | 0.95 | Snow edge softness |

---

## 2. foliage.gdshader

**Purpose:** Vegetation shader with wind animation. Supports separate leaf and trunk textures, color noise, frosting, and multiple wind modes.

**Author:** Giancarlo Niccolai (MIT License, v1.4)

**Render Mode:** `blend_mix, depth_draw_opaque, depth_prepass_alpha, cull_disabled, diffuse_lambert, specular_schlick_ggx`

**Required Global Uniforms:** `WindDirection`, `WindIntensity`, `GaleStrength`

### Uniform Parameters

#### General Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `alpha_clip_threshold` | float [0-1] | 0.25 | Alpha cutoff |
| `mesh_single_faced` | bool | true | Flip normals for back faces |
| `use_color_noise` | bool | false | Enable procedural color variation |
| `color_noise_small_freq` | float | 9.0 | Small-scale noise frequency |
| `color_noise_large_freq` | float | 1.0 | Large-scale noise frequency |

#### Leaf Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `leaf_color` | sampler2D | - | Leaf texture |
| `leaf_tiling` | vec2 | (1,1) | Leaf UV tiling |
| `leaf_offset` | vec2 | (0,0) | Leaf UV offset |
| `leaf_metallic` | float [0-1] | 0.0 | Leaf metallic |
| `leaf_smoothness` | float [0-1] | 0.2 | Leaf smoothness |
| `leaf_base_color` | vec4 (color) | (1,1,1,1) | Leaf tint |
| `leaf_noise_color` | vec4 (color) | (1,1,1,1) | Small noise color |
| `leaf_noise_large_color` | vec4 (color) | (1,1,1,1) | Large noise color |
| `leaf_flat_color` | bool | false | Use flat color instead of texture |

#### Leaf Normal Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_leaf_normal` | bool | false | Enable leaf normal map |
| `leaf_normal` | sampler2D | - | Leaf normal texture |
| `leaf_normal_tiling` | vec2 | (1,1) | Normal UV tiling |
| `leaf_normal_offset` | vec2 | (0,0) | Normal UV offset |
| `leaf_normal_strength` | float [0-1] | 0.5 | Normal intensity |

#### Leaf AO Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `leaf_ao` | sampler2D | - | Leaf AO texture |
| `leaf_ao_intensity` | float [0-1] | 0.5 | AO strength |

#### Trunk Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `trunk_color` | sampler2D | - | Trunk/bark texture |
| `trunk_tiling` | vec2 | (1,1) | Trunk UV tiling |
| `trunk_offset` | vec2 | (0,0) | Trunk UV offset |
| `trunk_metallic` | float [0-1] | 0.0 | Trunk metallic |
| `trunk_smoothness` | float [0-1] | 0.2 | Trunk smoothness |
| `trunk_base_color` | vec4 (color) | (1,1,1,1) | Trunk tint |
| `trunk_noise_color` | vec4 (color) | (1,1,1,1) | Trunk noise color |
| `trunk_flat_color` | bool | false | Use flat color |

#### Trunk Emission Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `trunk_emissive_color` | vec4 (color) | (0,0,0,0) | Trunk emission color |
| `trunk_emissive_mask` | sampler2D | - | Trunk emission mask |
| `trunk_emissive_tiling` | vec2 | (1,1) | Emission UV tiling |
| `trunk_emissive_offset` | vec2 | (0,0) | Emission UV offset |

#### Frosting Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_frosting` | bool | false | Enable frost/snow on leaves |
| `frosting_color` | vec4 (color) | (0,0,0,0) | Frost color |
| `frosting_falloff` | float | 1.0 | Frost edge falloff |
| `frosting_height` | float | 2.8 | Height-based frost threshold |
| `frosting_use_world_normal` | bool | false | Use world normal for frost |

#### Emission Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_emission` | bool | false | Enable leaf emission |
| `emissive_color` | vec4 (color) | (0,0,0,0) | Primary emission color |
| `emissive_2_color` | vec4 (color) | (0,0,0,0) | Secondary emission color |
| `emissive_mask` | sampler2D | - | Primary emission mask |
| `emissive_2_mask` | sampler2D | - | Secondary emission mask |
| `emissive_tiling/offset` | vec2 | (1,1)/(0,0) | Emission UV |
| `emissive_amount` | float [0-2] | 0.0 | Emission intensity |

#### Emission Pulse Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_pulse` | bool | false | Enable emission pulsing |
| `emissive_pulse_mask` | sampler2D | - | Pulse pattern texture |
| `emissive_pulse_tiling` | float | 0.03 | Pulse UV tiling |
| `emissive_pulse_speed` | float | 0.0 | Pulse animation speed |

#### Wind Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `use_vertex_color_wind` | bool | false | Use vertex color for wind weights |
| `use_global_weather_controller` | bool | true | Use global uniforms |

#### Wind Breeze Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_breeze` | bool | false | Enable gentle breeze |
| `breeze_strength` | float [0-1] | 0.2 | Breeze intensity |

#### Wind Light Wind Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_light_wind` | bool | false | Enable light wind |
| `light_wind_strength` | float [0-1] | 0.2 | Wind intensity |
| `light_wind_y_strength` | float [0-1] | 1.0 | Vertical wind component |
| `light_wind_y_offset` | float [0-1] | 0.0 | Vertical offset |
| `light_wind_use_leaf_fade` | bool | false | Fade based on vertex color |

#### Wind Strong Wind Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_strong_wind` | bool | false | Enable strong gusts |
| `strong_wind_strength` | float [0-1] | 0.2 | Gust intensity |
| `strong_wind_frequency` | float [0-1] | 0.5 | Gust frequency |

#### Wind Twist Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_wind_twist` | bool | false | Enable twisting motion |
| `wind_twist_strength` | float [0-2] | 0.15 | Twist amount |
| `gale_blend` | float [0-2] | 1.0 | Gale effect blend |

#### Local Defaults Group (when not using globals)
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `non_global_wind_direction` | vec3 | (1,0,0) | Local wind direction |
| `non_global_wind_intensity` | float [0-1] | 0.2 | Local wind strength |
| `non_global_gale_strength` | float [0-1] | 0.2 | Local gale strength |

---

## 3. water.gdshader

**Purpose:** Water surface shader with waves, foam, caustics, refraction, and depth-based coloring.

**Author:** Giancarlo Niccolai (MIT License, v1.1)

**Render Mode:** `blend_mix, depth_draw_opaque, cull_back, diffuse_lambert, specular_disabled`

**Required Global Uniforms:** `WindDirection`, `GaleStrength`, `OceanWavesGradient`

### Uniform Parameters

#### General Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `use_global_weather_controller` | bool | false | Use global wind uniforms |
| `non_global_gale_strength` | float | 0.2 | Local gale strength |
| `non_global_wind_direction` | vec3 | (1,0,0) | Local wind direction |
| `non_global_ocean_waves_gradient` | sampler2D | - | Local wave gradient |

#### Base Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `smoothness` | float [0-1] | 0.766 | Water smoothness |
| `metallic` | float [0-1] | 0.0 | Water metallic |
| `base_opacity` | float [0-1] | 0.941 | Deep water opacity |
| `shallows_opacity` | float [0-1] | 0.661 | Shallow water opacity |
| `shallow_color` | vec4 (color) | (0.5,0.5,0.2,1) | Shallow water color |
| `deep_color` | vec4 (color) | (0.4,0.4,0.8,1) | Deep water color |
| `very_deep_color` | vec4 (color) | (0.1,0.1,0.2,1) | Very deep color |
| `deep_height` | float | 1.16 | Deep water threshold |
| `very_deep_height` | float | 4.0 | Very deep threshold |
| `maximum_depth` | float | 15.0 | Maximum depth for transparency |

#### Base Normals Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_normals` | bool | false | Enable normal distortion |
| `normal_texture` | sampler2D | - | Water normal map |
| `normal_offset` | vec2 | (0,0) | Normal UV offset |
| `normal_tiling` | float | 0.0 | Normal UV tiling |
| `normal_intensity` | float [0-10] | 1.0 | Normal strength |
| `normal_pan_speed` | float | 1.0 | Normal scroll speed |
| `normal_noise_tiling` | float | 0.2 | Noise overlay tiling |
| `normal_noise_intensity` | float | 0.23 | Noise overlay strength |

#### Fresnel Fade Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_fresnel_fade` | bool | false | Fade normals at distance |
| `fade_distance` | float | 1.0 | Fade start distance |
| `fade_power` | float | 0.0 | Fade falloff power |

#### Shore Foam Wave Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_shore_wave_foam` | bool | false | Enable shore waves |
| `enable_shore_animation` | bool | false | Animate shore waves |
| `animation_offset` | int | 0 | Animation time offset |
| `shore_wave_speed` | float [0-1] | 1.0 | Wave animation speed |
| `shore_wave_return_amount` | float [0-1] | 1.0 | Wave return strength |
| `shore_wave_tickness` | float [0-1] | 0.1 | Wave thickness |
| `shore_edge_opacity` | float [0-1] | 0.1 | Edge visibility |
| `shore_wave_color_tint` | vec4 (color) | (1,1,1,1) | Wave color |
| `shore_edge_tickness` | float [0-1] | 0.1 | Edge detection thickness |
| `shore_edge_noise_scale` | float | 0.86 | Edge noise scale |
| `shore_lap_fade_out_speed` | float [0-10] | 1.0 | Fadeout speed |
| `shore_lap_fade_in_speed` | float [0-10] | 3.0 | Fadein speed |
| `shore_foam_noise_scale` | int [0-100] | 1 | Foam noise scale |
| `shore_foam_noise_texture` | sampler2D | - | Foam noise texture |

#### Shore Foam Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_shore_foam` | bool | false | Enable edge foam |
| `shore_small_foam_opacity` | float [0-1] | 0.725 | Foam opacity |
| `shore_small_foam_tiling` | float | 2.5 | Foam texture tiling |
| `shore_foam_color_tint` | vec4 (color) | (1,1,1,1) | Foam color |

#### Global Foam Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_global_foam` | bool | false | Enable wave foam |
| `noise_texture` | sampler2D | - | Foam noise texture |

#### Top Scrolling Texture Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_top_scrolling_texture` | bool | false | Enable scrolling overlay |
| `top_scrolling_direction` | vec2 | (0,-0.01) | Scroll direction |
| `scrolling_texture` | sampler2D | - | Scrolling texture |
| `scrolling_texture_tiling` | vec2 | (1,1) | Texture tiling |
| `scrolling_texture_tint` | vec4 (color) | (0.3,0.8,0.95,1) | Texture tint |
| `scrolling_texture_opacity` | float [0-1] | 0.25 | Texture opacity |

#### Waves Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_ocean_waves` | bool | false | Enable vertex displacement waves |
| `ocean_wave_height` | float [0-10] | 0.4 | Wave amplitude |
| `ocean_wave_speed` | float [0-1] | 0.3 | Wave animation speed |
| `ocean_foam_amount` | float [0-1] | 0.5 | Wave foam amount |
| `ocean_foam_opacity` | float [0-1] | 0.321 | Foam visibility |
| `ocean_wave_frequency` | float [1-20] | 1.0 | Wave frequency |
| `ocean_breakup_tiling` | int | 1 | Foam breakup tiling |

#### Caustics Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_caustics` | bool | false | Enable underwater caustics |
| `caustics_use_voronoi_noise` | bool | false | Use procedural caustics |
| `caustics_intensity` | float [0-1] | 0.5 | Caustics brightness |
| `caustics_color` | vec4 (color) | (1,1,1,1) | Caustics color |
| `caustics_flipbook` | sampler2D | - | Caustics animation (8x8 flipbook) |
| `caustics_speed` | float [0-10] | 1.0 | Animation speed |
| `caustics_scale` | int | 1 | Caustics size |

#### Distortion Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_distortion` | bool | false | Enable refraction distortion |
| `distortion_speed` | float [0-1] | 0.5 | Distortion animation speed |
| `distortion_direction` | vec2 | (1,1) | Distortion direction |
| `distortion_size` | float [0-1] | 0.1 | Distortion scale |
| `distortion_strength` | float [0-1] | 0.5 | Distortion amount |

---

## 4. refractive_transparent.gdshader

**Purpose:** Glass, crystal, and ice shader with refraction, fresnel, and depth effects. Supports triplanar texturing.

**Render Mode:** `blend_mix, depth_draw_always, cull_disabled, diffuse_lambert, specular_schlick_ggx`

### Uniform Parameters

#### Base Properties Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_triplanar` | bool | false | Enable triplanar texturing |
| `base_color` | vec4 (color) | (1,1,1,1) | Base glass color |
| `metallic` | float [0-1] | 0.8 | Metallic factor |
| `smoothness` | float [0-1] | 0.2 | Smoothness |
| `opacity` | float [0-1] | 1.0 | Base opacity |

#### Triplanar Base Texture Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_tiling` | float | 0.5 | Triplanar tiling |
| `base_normal_intensity` | float | -0.1 | Normal intensity |
| `base_albedo` | sampler2D | - | Base triplanar texture |
| `base_color_multiplier` | vec4 (color) | (1,1,1,1) | Color multiplier |
| `base_normal` | sampler2D | - | Base normal map |
| `base_specular_power` | float [0-1] | 0.5 | Specular power |
| `base_metallic` | float [0-1] | 0.8 | Triplanar metallic |

#### Triplanar Top Texture Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_top_projection` | bool | false | Enable top projection |
| `top_tiling` | float | 0.5 | Top texture tiling |
| `top_normal_intensity` | float | -0.1 | Top normal strength |
| `spread` | float [0-1] | 0.3 | Top/side blend spread |
| `fade_amount` | float [0-63] | 38.6 | Blend sharpness |
| `top_albedo` | sampler2D | - | Top texture |
| `top_color_multiplier` | vec4 (color) | (1,1,1,1) | Top color |
| `top_normal` | sampler2D | - | Top normal map |
| `top_opacity` | float [0-1] | 1.0 | Top opacity |
| `top_specular_power` | float [0-1] | 0.5 | Top specular |
| `top_metallic` | float [0-1] | 0.0 | Top metallic |

#### Fresnel Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_fresnel` | bool | false | Enable fresnel effect |
| `fresnel_color` | vec4 (color) | (1,1,1,1) | Fresnel rim color |
| `fresnel_border` | float | 3.77 | Fresnel edge position |
| `fresnel_power` | float | 4.86 | Fresnel intensity |

#### Depth Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_depth` | bool | false | Enable depth-based coloring |
| `depth_power_multiplier` | float | 1.99 | Depth effect strength |
| `deep_color` | vec4 (color) | (1,1,1,1) | Deep color |
| `deep_power` | float | 8.0 | Deep threshold |
| `shallow_color` | vec4 (color) | (1,1,1,1) | Shallow color |
| `shallow_power` | float | 1.2 | Shallow threshold |

#### Refraction Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_refraction` | bool | false | Enable refraction |
| `refraction_texture` | sampler2D | - | Refraction pattern |
| `refraction_height` | sampler2D | - | Height map for parallax |
| `refraction_color` | vec4 (color) | (1,1,1,1) | Refraction tint |
| `refraction_power` | float | 1.25 | Refraction intensity |
| `steps` | float | 0.0 | Parallax steps |
| `amplitude` | float | -50.0 | Parallax amplitude |
| `refraction_tiling` | float | 5.0 | Refraction UV tiling |

#### Distortion Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `inner_distortion` | bool | false | Enable inner distortion |
| `noise_tiling` | float | 2.5 | Noise UV tiling |
| `inner_distortion_power` | float [0-0.05] | 0.05 | Distortion strength |

---

## 5. clouds.gdshader

**Purpose:** Animated cloud mesh shader with lighting, fresnel, and scattering effects.

**Render Mode:** `unshaded`

### Uniform Parameters

#### Color Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `top_color` | vec4 (color) | - | Cloud top color |
| `base_color` | vec4 (color) | - | Cloud bottom color |
| `use_environment_override` | bool | - | Use local colors instead of globals |

#### Lighting Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `light_direction_override` | vec3 | (0.5,-0.5,0) | Light direction |
| `light_intensity` | float | - | Light brightness |
| `enable_fresnel` | bool | - | Enable rim lighting |
| `fresnel_power` | float | - | Fresnel intensity |
| `fresnel_color` | vec4 (color) | - | Fresnel color |

#### Lighting Effects Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_fog` | bool | - | Enable fog blending |
| `fog_density` | float [0-1] | 0.4 | Fog amount |
| `enable_scattering` | bool | - | Enable light scattering |
| `scattering_multiplier` | float | - | Scatter intensity |
| `scattering_edge_dist` | float [0-1] | 0.4 | Scatter edge distance |
| `scattering_color` | vec4 (color) | - | Scatter color |

#### Vertex Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cloud_speed` | float | 1.0 | Vertex animation speed |
| `cloud_strength` | float | 0.2 | Animation amplitude |

**Global Uniforms Used:**
- `MainLightDirection` (vec3)
- `SkyColor` (vec4)
- `EquatorColor` (vec4)
- `GroundColor` (vec4)

---

## 6. sky_dome.gdshader

**Purpose:** Simple sky dome gradient shader for Synty skybox meshes.

**Render Mode:** Default spatial

### Uniform Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `top_color` | vec4 (color) | (0.1,0.6,0.9,1) | Zenith color |
| `bottom_color` | vec4 (color) | (0.05,0.3,0.45,1) | Horizon color |
| `falloff` | float [0.001-100] | 1.0 | Gradient falloff |
| `offset` | float | 32.0 | Gradient vertical offset |
| `distance_` | float [1-10000] | 1000.0 | Gradient scale |
| `enable_uv_based` | bool | - | Use UV instead of world position |

---

## 7. particles_unlit.gdshader

**Purpose:** Unlit particle shader with soft particles, camera fade, and fog support.

**Render Mode:** `blend_mix`

### Uniform Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `alpha_clip_treshold` | float [0-1] | 0.5 | Alpha cutoff |
| `base_color` | vec4 (color) | (1,1,1,1) | Particle color |
| `albedo_map` | sampler2D | - | Particle texture |
| `tiling` | vec2 | (1,1) | UV tiling |
| `offset` | vec2 | (0,0) | UV offset |

#### Soft Particles
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_soft_particles` | bool | true | Enable depth fade |
| `soft_power` | float [0-10] | 2.0 | Fade power |
| `soft_distance` | float [0-2] | 0.1 | Fade distance |
| `use_view_edge_compensation` | bool | false | Compensate for view angle |
| `view_edge_power` | float | 1.0 | Edge compensation strength |

#### Camera Fade
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_camera_fade` | bool | false | Enable distance fade |
| `camera_fade_near` | float | 0.0 | Near fade start |
| `camera_fade_far` | float | 20.0 | Far fade end |
| `camera_fade_smoothness` | float [0-100] | 1.5 | Fade smoothness |

#### Scene Fog
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_scene_fog` | bool | false | Blend with fog |
| `fog_color` | vec4 | (1,1,1,0) | Fog color |

---

## 8. biomes_tree.gdshader

**Purpose:** Alternative tree shader for Synty Biomes packs with vertex-based wind animation and frost effects.

**Render Mode:** `depth_prepass_alpha, cull_disabled, diffuse_burley, specular_schlick_ggx`

### Uniform Parameters

#### General Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `alpha_scissor_threshold` | float [0-1] | 0.4 | Alpha cutoff |
| `specular` | float [0-1] | 0.4 | Specular amount |
| `roughness` | float [0-1] | 0.85 | Surface roughness |
| `face_tint` | float [0-1] | 0.2 | Face angle tinting |

#### Leaf Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `Leaf_Texture` | sampler2D | - | Leaf albedo |
| `Leaf_Texture_Normal` | sampler2D | - | Leaf normal map |
| `Leaf_UV_Scale` | vec2 | (1,1) | Leaf UV scale |
| `Leaf_Tint_Base` | vec3 (color) | (0,0,0) | Leaf base tint |
| `Leaf_Tint_Highlight` | vec3 (color) | (1,1,1) | Leaf highlight tint |
| `Leaf_Tint_Str` | float [0-1] | 0.0 | Tint strength |
| `Texture_As_Brightness` | bool | true | Use texture luminance |
| `Brightness` | float [1-16] | 8.0 | Brightness multiplier |

#### Leaf Emission Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `Leaf_Emmisive_Color` | vec3 (color) | (0,0,0) | Leaf glow color |
| `Leaf_Emissive_Str` | float [0-2] | 0.0 | Glow strength |
| `Leaf_Emmisive_Mask` | sampler2D | - | Emission mask |

#### Trunk Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `Trunk_Texture` | sampler2D | - | Trunk albedo |
| `Trunk_Texture_Normal` | sampler2D | - | Trunk normal |
| `Trunk_UV_Scale` | vec2 | (1,1) | Trunk UV scale |
| `Trunk_Tint` | vec3 (color) | (0,0,0) | Trunk tint |
| `Trunk_Tint_Str` | float [0-1] | 0.0 | Tint strength |

#### Frost Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `F_Texture_As_Brightness` | bool | true | Use texture for frost brightness |
| `F_Brightness` | float [1-16] | 8.0 | Frost brightness |
| `frost_amount` | float [0-1] | 0.0 | Frost coverage |
| `frost_fade` | float [0-2] | 1.0 | Frost edge softness |
| `Frost_Color` | vec3 (color) | (1,1,1) | Frost color |

#### Wind Group
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `Wind_Enable` | bool | true | Enable wind animation |
| `wind_noise` | sampler2D | - | Wind noise texture |
| `wind_color_shift` | vec3 (color) | (0,0,0) | Color shift in wind |
| `wind_color_strength` | float [0-1] | 0.5 | Color shift strength |
| `wind_strength` | float [0-1] | 0.33 | Overall wind strength |
| `wind_direction_rads` | float [-PI, PI] | 0.0 | Wind direction (radians) |
| `sway_multiplier` | float [0-4] | 2.0 | Large sway amount |
| `jitter_multiplier` | float [0-4] | 2.0 | Small jitter amount |
| `deform_multiplier` | float [0-4] | 2.0 | Deformation amount |
| `bend_multiplier` | float [0-4] | 2.0 | Bending amount |

---

## Installation

### Automatic (via script)

```bash
python -m synty_converter_v2.shaders.shader_installer ./assets/shaders/synty
```

### Manual

1. Visit each shader's godotshaders.com URL
2. Copy the shader code
3. Save to `assets/shaders/synty/{shader_name}.gdshader`

### Placeholder Shaders

If automatic download fails, the installer creates placeholder shaders with instructions:

```gdshader
// PLACEHOLDER SHADER - polygon_shader.gdshader
// Please download the actual shader from:
// https://godotshaders.com/shader/synty-polygon-drop-in-replacement-for-polygonshader/

shader_type spatial;

void fragment() {
    ALBEDO = vec3(1.0, 0.0, 1.0); // Magenta = missing shader
}
```

## FBX Import Configuration

The converter generates `.fbx.import` files with proper parameters for Godot's FBX/ufbx importer:

```ini
[params]
# Force native ufbx importer (not Blender)
fbx/importer=0

# Material remapping to generated .tres files
_subresources={
"materials": {
"Mat_Building_Stone": {"use_external/enabled": true, "use_external/path": "res://assets/synty/MyPack/Materials/Mat_Building_Stone.tres"}
}
}
```

**Key Import Parameters:**
- `fbx/importer=0` - Uses Godot's native ufbx importer instead of Blender
- Material subresources point to generated `.tres` ShaderMaterial files
- Mesh extraction settings for reusable `.res` mesh files

## License

All shaders are copyright Giancarlo Niccolai and published under the MIT License.
