# Shader Reference - Synty Shader Converter

This document covers Godot shader details, output format, and asset handling for the Synty Shader Converter.

**For detailed implementation documentation, see:**
- [Step 6: Shader Detection](./steps/06-shader-detection.md) - Shader detection algorithm and property mapping
- [Step 8: Copy Shaders](./steps/08-copy-shaders.md) - Shader deployment process

**Related Documentation:**
- [Architecture](./architecture.md) - Core architecture and usage
- [Unity Reference](./unity-reference.md) - Unity parsing details and parameter mapping

---

## Table of Contents

- [Quick Reference](#quick-reference)
- [Which Shader Do I Need?](#which-shader-do-i-need)
- [Shader Feature Reference](#shader-feature-reference)
  - [Polygon Shader](#polygon-shader)
  - [Foliage Shader](#foliage-shader)
  - [Crystal Shader](#crystal-shader)
  - [Water Shader](#water-shader)
  - [Clouds Shader](#clouds-shader)
  - [Particles Shader](#particles-shader)
  - [Skydome Shader](#skydome-shader)
- [Output Format](#output-format)
- [LOD Handling](#lod-handling)
- [Material Variants](#material-variants)
- [See Also](#see-also)

---

## Quick Reference

| Shader | Purpose | Key Parameters |
|--------|---------|----------------|
| polygon | Props, terrain, generic materials | base_texture, smoothness, metallic |
| foliage | Trees, grass, vegetation | leaf_color, wind, enable_breeze |
| crystal | Glass, gems, transparent | fresnel, refraction, depth_color |
| water | Rivers, lakes, oceans | wave_speed, foam, caustics |
| clouds | Volumetric clouds | cloud_speed, scattering |
| particles | Particle effects, fog | soft_particles, camera_fade |
| skydome | Sky gradients | top_color, bottom_color |

---

## Which Shader Do I Need?

**Does it move in the wind?** -> `foliage.gdshader`

**Is it transparent/glass/crystal?** -> `crystal.gdshader`

**Is it water/liquid?** -> `water.gdshader`

**Is it a sky/atmosphere?** -> `skydome.gdshader` or `clouds.gdshader`

**Is it a particle effect?** -> `particles.gdshader`

**Everything else** -> `polygon.gdshader`

---

## Shader Feature Reference

---

### Polygon Shader

**Overview:** The default shader for static props, buildings, terrain, and environmental assets. Supports triplanar mapping and snow effects.

**Key Features:**
- Base albedo, normal, emission, and AO texture slots
- Triplanar projection (Y/XZ based)
- Snow coverage effect
- Overlay texture support

**Core Textures:**

| Slot | Uniform | Purpose |
|------|---------|---------|
| Base Albedo | `base_texture` | Primary color texture |
| Normal Map | `normal_texture` | Surface detail |
| Emission | `emission_texture` | Glow/self-illumination |
| AO | `ao_texture` | Ambient occlusion shadows |
| Overlay | `overlay_texture` | Secondary effects layer |

**Feature Toggles:**
- `enable_base_texture` - Use base albedo (default: true)
- `enable_normal_texture` - Use normal map (default: true)
- `enable_emission_texture` - Enable emission (default: false)
- `enable_ambient_occlusion` - Enable AO (default: false)
- `enable_overlay_texture` - Enable overlay (default: false)
- `enable_triplanar_texture` - Enable triplanar albedo (default: false)
- `enable_triplanar_normals` - Enable triplanar normals (default: false)
- `enable_triplanar_emission` - Enable triplanar emission (default: false)
- `enable_snow` - Enable snow coverage (default: false)

**Triplanar System:**

Uses Y/XZ projection (top, side, bottom) rather than XYZ:
- `triplanar_texture_top` / `triplanar_texture_side` / `triplanar_texture_bottom`
- `triplanar_normal_top` / `triplanar_normal_side` / `triplanar_normal_bottom`
- Per-surface metallic/smoothness: `top_metallic`, `side_metallic`, `bottom_metallic`
- `triplanar_intensity` (0-1) - Blend strength
- `triplanar_fade` (0-1) - Transition sharpness

**Snow Effect:**
- `snow_color` - Snow tint (default: white)
- `snow_level` (0-1) - Coverage amount
- `snow_metallic` / `snow_smoothness` - Snow surface properties
- `snow_use_world_up` - Use world Y vs local Y for direction

**Example .tres Snippet:**

```ini
[gd_resource type="ShaderMaterial" load_steps=3 format=3]

[ext_resource type="Shader" path="res://shaders/polygon.gdshader" id="1"]
[ext_resource type="Texture2D" path="res://textures/Building_01.tga" id="2"]

[resource]
shader = ExtResource("1")
shader_parameter/base_texture = ExtResource("2")
shader_parameter/smoothness = 0.3
shader_parameter/metallic = 0.0
```

**Common Issues/Notes:**
- Detection: Materials with `_Triplanar_`, `_Snow_`, or standard `PolygonNatureBiomes_` naming

---

### Foliage Shader

**Overview:** Shader for trees, ferns, grass, bushes, and vegetation with built-in wind animation and color variation.

**Key Features:**
- Separate leaf and trunk texture slots
- Multi-layer wind animation system
- Frost/snow coverage
- Emission and pulse effects
- Procedural color noise

**Vertex Color Requirements:**

| Channel | Encoding | Purpose |
|---------|----------|---------|
| Red | 0.0-1.0 | Height gradient (bottom to top) |
| Green | 0.0-1.0 | Leaf tip gradient |
| Blue | >0.5 = leaf | Leaf vs trunk mask |

**Core Textures:**

| Part | Slots |
|------|-------|
| Leaf | `leaf_color`, `leaf_normal`, `leaf_ao` |
| Trunk | `trunk_color`, `trunk_normal`, `trunk_ao` |
| Emission | `emissive_mask`, `emissive_2_mask`, `emissive_pulse_mask` |

**Required Global Uniforms:**

```ini
WindDirection = Vector3(1, 0, 0)
WindIntensity = 0.5
GaleStrength = 0.0
```

**Wind System:**

| Effect | Toggle | Strength Param | Behavior |
|--------|--------|----------------|----------|
| Breeze | `enable_breeze` | `breeze_strength` | Rippling motion using 3-octave noise |
| Light Wind | `enable_light_wind` | `light_wind_strength` | Bending/pushing leaves |
| Strong Wind | `enable_strong_wind` | `strong_wind_strength` | Object-level swaying |
| Wind Twist | `enable_wind_twist` | `wind_twist_strength` | Rotational twisting |

**Frosting (Snow):**
- `enable_frosting` - Toggle frost effect
- `frosting_color` - Frost tint
- `frosting_height` - Coverage power exponent
- `frosting_falloff` - Fade intensity

**Emission:**
- `enable_emission` - Toggle leaf emission
- `emissive_color` / `emissive_2_color` - Glow colors
- `enable_pulse` - Animated pulsing glow
- `trunk_emissive_color` - Trunk glow (separate)

**Color Noise:**
- `use_color_noise` - Enable procedural variation
- `leaf_noise_color` / `leaf_noise_large_color` - Noise tints
- Creates natural patch-level color variation

**Example .tres Snippet:**

```ini
[gd_resource type="ShaderMaterial" load_steps=4 format=3]

[ext_resource type="Shader" path="res://shaders/foliage.gdshader" id="1"]
[ext_resource type="Texture2D" path="res://textures/Fern_1.tga" id="2"]
[ext_resource type="Texture2D" path="res://textures/Fern_1_Normals.png" id="3"]

[resource]
shader = ExtResource("1")
shader_parameter/leaf_color = ExtResource("2")
shader_parameter/enable_leaf_normal = true
shader_parameter/leaf_normal = ExtResource("3")
shader_parameter/leaf_smoothness = 0.07
shader_parameter/enable_breeze = true
shader_parameter/breeze_strength = 0.2
```

**Common Issues/Notes:**
- Detection: Materials containing `Tree`, `Fern`, `Leaf`, `Grass`, `Vine`, `Branch`, `Willow`
- Requires proper vertex color painting for wind effects to work correctly

---

### Crystal Shader

**Overview:** Shader for crystals, gems, glass, and ice with transparent/translucent rendering, fresnel edge glow, and refraction effects.

**Key Features:**
- Transparent rendering with depth write
- Fresnel edge glow effect
- Depth-based color transition
- Refraction with parallax mapping
- Inner distortion effects

**Render Mode:** Transparent with depth write, double-sided

**Base Properties:**
- `base_color` - Primary crystal color
- `metallic` / `smoothness` - Surface properties
- `opacity` - Overall transparency

**Triplanar System:**
- `enable_triplanar` - Enable triplanar projection
- `base_albedo` / `base_normal` - Base textures
- `enable_top_projection` - Separate top surface
- `top_albedo` / `top_normal` - Top textures
- `spread` (0-1) - Top-to-side transition
- `fade_amount` (0-63) - Blend sharpness

**Fresnel Effect (Edge Glow):**
- `enable_fresnel` - Toggle edge glow
- `fresnel_color` - Glow color
- `fresnel_power` - Glow intensity
- `fresnel_border` - Glow spread

**Depth Coloring (Translucency):**
- `enable_depth` - Toggle depth effect
- `deep_color` - Color at max depth
- `shallow_color` - Color near surface
- `deep_power` / `shallow_power` - Falloff rates
- Creates realistic light-through-crystal appearance

**Refraction:**
- `enable_refraction` - Toggle light bending
- `refraction_texture` / `refraction_height` - Distortion textures
- `refraction_color` - Refraction tint
- `refraction_power` - Effect intensity
- `amplitude` / `steps` - Parallax mapping params

**Inner Distortion:**
- `inner_distortion` - Toggle ripple effect
- `noise_tiling` - Distortion pattern scale
- `inner_distortion_power` - Distortion strength

**Example .tres Snippet:**

```ini
[gd_resource type="ShaderMaterial" load_steps=2 format=3]

[ext_resource type="Shader" path="res://shaders/crystal.gdshader" id="1"]

[resource]
shader = ExtResource("1")
shader_parameter/base_color = Color(0.2, 0.6, 0.9, 1.0)
shader_parameter/opacity = 0.8
shader_parameter/enable_fresnel = true
shader_parameter/fresnel_color = Color(0.5, 0.8, 1.0, 1.0)
shader_parameter/fresnel_power = 2.0
```

**Common Issues/Notes:**
- Detection: Materials containing `Crystal`, `Glass`, `Gem`, `Ice`, or with `Refractive_Transparent` shader

---

### Water Shader

**Overview:** Full-featured water shader for rivers, lakes, oceans, and ponds with wave animation, foam, caustics, and depth coloring.

**Key Features:**
- Animated wave displacement
- Shore and global foam effects
- Caustics projection
- Depth-based color gradient
- Weather system integration

**Render Mode:** Spatial, blend_mix, depth_draw_opaque

**Required Global Uniforms:**

```ini
WindDirection = Vector3(1, 0, 0)
GaleStrength = 0.2
OceanWavesGradient = [Texture2D - wave noise/gradient]
```

**Core Features:**

| Feature Group | Toggle | Key Parameters |
|---------------|--------|----------------|
| Base | - | `smoothness`, `metallic`, `base_opacity`, `shallow_color`, `deep_color`, `very_deep_color` |
| Normals | `enable_normals` | `normal_texture`, `normal_tiling`, `normal_intensity`, `normal_pan_speed` |
| Fresnel Fade | `enable_fresnel_fade` | `fade_distance`, `fade_power` |
| Shore Wave Foam | `enable_shore_wave_foam` | `shore_wave_speed`, `shore_wave_color_tint`, `shore_edge_tickness` |
| Shore Foam | `enable_shore_foam` | `shore_foam_color_tint`, `shore_small_foam_tiling` |
| Global Foam | `enable_global_foam` | `noise_texture`, `ocean_foam_amount`, `ocean_foam_opacity` |
| Top Scrolling | `enable_top_scrolling_texture` | `scrolling_texture`, `scrolling_texture_tiling`, `scrolling_texture_tint` |
| Ocean Waves | `enable_ocean_waves` | `ocean_wave_height`, `ocean_wave_speed`, `ocean_wave_frequency` |
| Caustics | `enable_caustics` | `caustics_flipbook`, `caustics_intensity`, `caustics_color`, `caustics_speed` |
| Distortion | `enable_distortion` | `distortion_speed`, `distortion_strength`, `distortion_size` |

**Weather System:**
- Uses `use_global_weather_controller` to switch between global uniforms and local overrides
- Non-global alternatives: `non_global_wind_direction`, `non_global_gale_strength`

**Example .tres Snippet:**

```ini
[gd_resource type="ShaderMaterial" load_steps=2 format=3]

[ext_resource type="Shader" path="res://shaders/water.gdshader" id="1"]

[resource]
shader = ExtResource("1")
shader_parameter/shallow_color = Color(0.2, 0.5, 0.6, 1.0)
shader_parameter/deep_color = Color(0.05, 0.2, 0.3, 1.0)
shader_parameter/enable_ocean_waves = true
shader_parameter/ocean_wave_height = 0.5
shader_parameter/enable_shore_foam = true
```

**Common Issues/Notes:**
- Detection: Materials containing `Water`, `Ocean`, `River`, `Lake`, `Pond`, or with Water shader GUID
- Requires depth texture for shore foam effects

---

### Clouds Shader

**Overview:** Volumetric cloud shader with lighting, fresnel, and scattering effects for cartoon-style environments.

**Key Features:**
- Gradient-based cloud coloring
- Light scattering simulation
- Fresnel edge highlighting
- Vertex-based animation
- Fog integration

**Render Mode:** Spatial, unshaded

**Required Global Uniforms:**

```ini
MainLightDirection = Vector3(0.5, -0.5, 0.0)
SkyColor = Color(0.5, 0.7, 1.0, 1.0)
EquatorColor = Color(1.0, 0.9, 0.8, 1.0)
GroundColor = Color(0.4, 0.4, 0.3, 1.0)
```

**Core Features:**

| Feature Group | Toggle | Key Parameters |
|---------------|--------|----------------|
| Color | - | `top_color`, `base_color` |
| Environment Override | `use_environment_override` | Uses local colors instead of globals |
| Lighting | - | `light_direction_override`, `light_intensity` |
| Fresnel | `enable_fresnel` | `fresnel_power`, `fresnel_color` |
| Fog | `enable_fog` | `fog_density` |
| Scattering | `enable_scattering` | `scattering_multiplier`, `scattering_edge_dist`, `scattering_color` |
| Vertex Animation | - | `cloud_speed`, `cloud_strength` |

**Vertex Animation:**
- Clouds animate vertically using sine wave based on position and time
- `cloud_strength` controls displacement amplitude
- `cloud_speed` controls animation frequency

**Example .tres Snippet:**

```ini
[gd_resource type="ShaderMaterial" load_steps=2 format=3]

[ext_resource type="Shader" path="res://shaders/clouds.gdshader" id="1"]

[resource]
shader = ExtResource("1")
shader_parameter/top_color = Color(1.0, 1.0, 1.0, 1.0)
shader_parameter/base_color = Color(0.8, 0.85, 0.9, 1.0)
shader_parameter/enable_scattering = true
shader_parameter/cloud_speed = 0.1
```

**Common Issues/Notes:**
- Detection: Materials containing `Cloud` or with Clouds shader GUID

---

### Particles Shader

**Overview:** Shader for soft particles, camera-fading effects, and fog simulation with smooth blending against scene geometry.

**Key Features:**
- Soft particle depth blending
- Camera distance fading
- View edge compensation
- Scene fog integration

**Render Mode:** Spatial, blend_mix

**Core Features:**

| Feature Group | Toggle | Key Parameters |
|---------------|--------|----------------|
| Base | - | `alpha_clip_treshold`, `base_color`, `albedo_map`, `tiling`, `offset` |
| Soft Particles | `enable_soft_particles` | `soft_power`, `soft_distance` |
| View Edge | `use_view_edge_compensation` | `view_edge_power` |
| Camera Fade | `enable_camera_fade` | `camera_fade_near`, `camera_fade_far`, `camera_fade_smoothness` |
| Scene Fog | `enable_scene_fog` | `fog_color` (alpha = density) |

**Soft Particles:**
- Fades particles near scene geometry to prevent hard intersections
- `soft_distance` controls fade zone width
- `soft_power` controls falloff curve

**Camera Fade:**
- Fades particles based on camera distance
- Uses near/far bounds with smoothness interpolation
- Useful for billboard fog and distant particle effects

**Example .tres Snippet:**

```ini
[gd_resource type="ShaderMaterial" load_steps=3 format=3]

[ext_resource type="Shader" path="res://shaders/particles.gdshader" id="1"]
[ext_resource type="Texture2D" path="res://textures/FX/Smoke_01.png" id="2"]

[resource]
shader = ExtResource("1")
shader_parameter/albedo_map = ExtResource("2")
shader_parameter/enable_soft_particles = true
shader_parameter/soft_distance = 0.5
shader_parameter/enable_camera_fade = true
shader_parameter/camera_fade_near = 1.0
shader_parameter/camera_fade_far = 50.0
```

**Common Issues/Notes:**
- Detection: Materials containing `Particle`, `FX_`, `Fog`, or with Particles shader GUID
- Requires depth texture for soft particles to work

---

### Skydome Shader

**Overview:** Simple gradient sky dome shader for cartoon-style environments with world-position or UV-based blending modes.

**Key Features:**
- Two-color gradient sky
- World position or UV-based calculation
- Configurable falloff curve

**Render Mode:** Spatial (default)

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `top_color` | Color | (0.1, 0.6, 0.9, 1.0) | Sky color at top |
| `bottom_color` | Color | (0.05, 0.3, 0.45, 1.0) | Sky color at horizon/bottom |
| `falloff` | float | 1.0 | Gradient curve power (0.001-100) |
| `offset` | float | 32.0 | Y-axis offset for gradient calculation |
| `distance_` | float | 1000.0 | Distance scale (1-10000) |
| `enable_uv_based` | bool | false | Use UV.y instead of world position |

**Modes:**

1. **World Position Mode** (default): Gradient based on world Y coordinate
   - Uses `offset`, `distance_`, and `falloff` to calculate blend
   - Good for large-scale sky domes

2. **UV-Based Mode** (`enable_uv_based = true`): Gradient based on UV.y
   - Simpler, works with any mesh UV layout
   - Ignores `offset`, `distance_`, `falloff` parameters

**Example .tres Snippet:**

```ini
[gd_resource type="ShaderMaterial" load_steps=2 format=3]

[ext_resource type="Shader" path="res://shaders/skydome.gdshader" id="1"]

[resource]
shader = ExtResource("1")
shader_parameter/top_color = Color(0.4, 0.7, 1.0, 1.0)
shader_parameter/bottom_color = Color(0.9, 0.85, 0.7, 1.0)
shader_parameter/falloff = 1.5
```

**Common Issues/Notes:**
- Detection: Materials containing `Skydome`, `SkyDome`, `Sky_Dome`, or with Skydome shader GUID

---

## Output Format

### Godot ShaderMaterial (.tres)

```ini
[gd_resource type="ShaderMaterial" load_steps=4 format=3]

[ext_resource type="Shader" path="res://shaders/foliage.gdshader" id="1"]
[ext_resource type="Texture2D" path="res://textures/Fern_1.tga" id="2"]
[ext_resource type="Texture2D" path="res://textures/Fern_1_Normals.png" id="3"]

[resource]
shader = ExtResource("1")
shader_parameter/leaf_color = ExtResource("2")
shader_parameter/enable_leaf_normal = true
shader_parameter/leaf_normal = ExtResource("3")
shader_parameter/leaf_smoothness = 0.07
shader_parameter/enable_breeze = true
shader_parameter/breeze_strength = 0.2
```

### Output Directory Structure

```
output-project/
  project.godot              # With global shader uniforms
  shaders/
    polygon.gdshader         # Downloaded from GodotShaders.com
    foliage.gdshader
    crystal.gdshader
  textures/
    Core/                    # Utility textures (noise, gradients)
    Cards/                   # Billboard textures
    Emissive/                # Emission maps
    FX/                      # Particle textures
    Alts/                    # Texture variants
    [root textures]          # Main albedo/normal textures
  materials/
    PolygonNatureBiomes_EnchantedForest_Mat_01_A.tres
    Fern_Mat_02.tres
    Crystal_Mat_01.tres
    EnchantedTree_Mat_01a.tres
    ...
  models/
    Props/
      SM_Prop_Crystal_01.fbx
    Environment/
      SM_Env_Fern_01.fbx
    ...
```

---

## LOD Handling

Synty assets have multiple LOD levels: LOD0 (highest), LOD1, LOD2, LOD3/Card (lowest).

**Approach:** Generate separate .res for each LOD variant.

```
SM_Env_Fern_01_LOD0.fbx -> SM_Env_Fern_01_LOD0.res
SM_Env_Fern_01_LOD1.fbx -> SM_Env_Fern_01_LOD1.res
SM_Env_Fern_01_LOD2.fbx -> SM_Env_Fern_01_LOD2.res
```

User can set up Godot's LOD system manually using these assets.

---

## Material Variants

Generate all A/B/C variants:

```
PolygonNatureBiomes_EnchantedForest_Mat_01_A.tres
PolygonNatureBiomes_EnchantedForest_Mat_01_B.tres
PolygonNatureBiomes_EnchantedForest_Mat_01_C.tres
PolygonNatureBiomes_EnchantedForest_Mat_02_A.tres
...etc
```

User chooses which variant to use in their scenes.

---

## See Also

- [Step 6: Shader Detection](./steps/06-shader-detection.md) - Full detection algorithm and property mapping
- [Step 8: Copy Shaders](./steps/08-copy-shaders.md) - Shader deployment details
- [API: Constants](./api/constants.md) - Full property mappings and constant definitions
- [Troubleshooting](./troubleshooting.md) - Visual issues and common problems
