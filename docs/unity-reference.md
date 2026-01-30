# Unity Reference - Synty Shader Converter

This document covers Unity-specific parsing details for converting Synty materials to Godot.

**Related Documentation:**
- [Architecture](./architecture.md) - Core architecture and usage
- [Shader Reference](./shader-reference.md) - Godot shader details and output format
- [Troubleshooting Guide](./troubleshooting.md) - Common issues and solutions

---

## Table of Contents

- [Quick GUID Lookup](#quick-guid-lookup)
- [Unity Material Structure](#unity-material-structure)
- [Shader Detection](#shader-detection)
  - [Primary Method: Shader GUID](#primary-method-shader-guid)
    - [Core Synty Shaders](#core-synty-shaders)
    - [Biome-Specific Shaders](#biome-specific-shaders)
    - [Effects Shaders](#effects-shaders)
    - [Legacy/Fallback Shaders](#legacyfallback-shaders)
  - [Fallback: Name Pattern Matching](#fallback-name-pattern-matching)
- [Parameter Mapping](#parameter-mapping)
  - [Foliage Shader](#foliage-shader-trees-ferns-grass)
  - [Polygon Shader](#polygon-shader-props-terrain-triplanar)
  - [Crystal Shader](#crystal-shader-crystals-glass-gems)
  - [Water Shader](#water-shader-rivers-lakes-oceans)
  - [Character Shader](#character-shader-properties-hairskin-system)
  - [Clouds Shader](#clouds-shader-volumetric-clouds)
  - [Particles Shader](#particles-shader-effects-fog)
  - [Skydome Shader](#skydome-shader-sky-gradient)
  - [Advanced Shader Features](#advanced-shader-features)
  - [Biome-Specific Features](#biome-specific-features)
  - [Property Name Alternatives](#property-name-alternatives)
  - [Legacy Property Names](#legacy-property-names-2021-and-earlier-packs)
- [Unity Parsing Quirks](#unity-parsing-quirks)
- [Texture Handling](#texture-handling)
- [Appendix: Material Property Statistics](#appendix-material-property-statistics)

---

## Quick GUID Lookup

The 10 most commonly used shader GUIDs across all Synty packs:

| GUID | Shader Name | Godot Shader | Frequency |
|------|-------------|--------------|-----------|
| `0730dae39bc73f34796280af9875ce14` | Synty PolygonLit | polygon.gdshader | Very High |
| `9b98a126c8d4d7a4baeb81b16e4f7b97` | Synty Foliage | foliage.gdshader | Very High |
| `933532a4fcc9baf4fa0491de14d08ed7` | Unity URP Lit | polygon.gdshader | High |
| `3b44a38ec6f81134ab0f820ac54d6a93` | Generic_Standard | polygon.gdshader | High |
| `436db39b4e2ae5e46a17e21865226b19` | Synty Water | water.gdshader | Medium |
| `5808064c5204e554c89f589a7059c558` | Synty Crystal | crystal.gdshader | Medium |
| `19e269a311c45cd4482cf0ac0e694503` | Synty Triplanar | polygon.gdshader | Medium |
| `ab6da834753539b4989259dbf4bcc39b` | ProRacer_Standard | polygon.gdshader | Medium |
| `de1d86872962c37429cb628a7de53613` | Synty Skydome | skydome.gdshader | Low |
| `0736e099ec10c9e46b9551b2337d0cc7` | Synty Particles | particles.gdshader | Low |

---

## Unity Material Structure

All Unity .mat files use YAML 1.1 format with this structure:

```yaml
%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!21 &2100000
Material:
  m_Name: MaterialName
  m_Shader: {fileID: 4800000, guid: SHADER_GUID, type: 3}

  m_TexEnvs:
    - _Texture_Name:
        m_Texture: {fileID: 2800000, guid: TEXTURE_GUID, type: 3}
        m_Scale: {x: 1, y: 1}
        m_Offset: {x: 0, y: 0}

  m_Floats:
    - _Parameter_Name: 0.5

  m_Colors:
    - _Color_Name: {r: 1, g: 1, b: 1, a: 1}
```

### Texture GUID Resolution

Materials reference textures by GUID, not path. We need to build a mapping:

1. Each asset in the Unity package has a `pathname` file containing its path
2. The folder name IS the GUID
3. Build map: `GUID -> texture_path`

---

## Shader Detection

### Primary Method: Shader GUID

The `m_Shader.guid` field identifies which Unity shader the material uses. The tables below are organized by category for easier lookup.

#### Core Synty Shaders

These are the most commonly used shaders across all Synty packs.

| GUID | Shader Type | Godot Shader | Frequency | Notes |
|------|-------------|--------------|-----------|-------|
| `0730dae39bc73f34796280af9875ce14` | Synty PolygonLit | polygon.gdshader | Very High | Main prop shader |
| `9b98a126c8d4d7a4baeb81b16e4f7b97` | Synty Foliage | foliage.gdshader | Very High | Trees/plants |
| `3b44a38ec6f81134ab0f820ac54d6a93` | Generic_Standard | polygon.gdshader | High | Character hair/skin |
| `19e269a311c45cd4482cf0ac0e694503` | Synty Triplanar | polygon.gdshader | Medium | Triplanar mode |
| `0736e099ec10c9e46b9551b2337d0cc7` | Synty Particles | particles.gdshader | Medium | Particle effects |
| `436db39b4e2ae5e46a17e21865226b19` | Synty Water | water.gdshader | Medium | Water surfaces |
| `5808064c5204e554c89f589a7059c558` | Synty Crystal | crystal.gdshader | Medium | Crystals/gems |
| `fdea4239d29733541b44cd6960afefcd` | Synty Glass | crystal.gdshader | Low | Glass materials |
| `dfec08fb273e4674bb5398df25a5932c` | Synty Leaf Card | foliage.gdshader | Low | Billboard leaves |
| `de1d86872962c37429cb628a7de53613` | Synty Skydome | skydome.gdshader | Low | Sky gradient |
| `4a6c8c23090929241b2a55476a46a9b1` | Synty Clouds | clouds.gdshader | Low | Volumetric clouds |

#### Biome-Specific Shaders

Shaders used by specific biome or themed packs (Nature, Fantasy, Racing, etc.).

| GUID | Shader Type | Godot Shader | Frequency | Pack/Notes |
|------|-------------|--------------|-----------|------------|
| **Skydome/Aurora Variants** |||||
| `3d532bc2d70158948859b7839127e562` | Skybox_Generic | skydome.gdshader | Low | Procedural skybox |
| `74fa94d128fe4f348889c6f5f182e0e1` | Skydome variant | skydome.gdshader | Low | NatureBiomes |
| `d2820334f2975bb47ab3f2fffa1b4cbe` | Aurora | skydome.gdshader | Low | Viking northern lights |
| `ca9b700964f37d84a90b00c70d981934` | Aurora | skydome.gdshader | Low | Elven Realm northern lights |
| **Elven Realm** |||||
| `e854bc7dc0cde7044b9000faaf0c4e11` | RockTriplanar | polygon.gdshader | Low | Triplanar mode |
| `9b1e1d14d7778714391ae095571c3d4f` | WaterFall | water.gdshader | Low | Animated waterfall |
| `903fe97c2d85c8147a64932806c92eb1` | Waterfall variant | water.gdshader | Low | Alternative waterfall |
| `df6b3a02955954d41bb15c534388ba14` | NoFog | polygon.gdshader | Low | Celestial/no fog |
| **Pro Racer** |||||
| `ab6da834753539b4989259dbf4bcc39b` | ProRacer_Standard | polygon.gdshader | Medium | Main racing (128 uses) |
| `22e3738818284144eb7ada0a62acca66` | ProRacer_Decal | polygon.gdshader | Low | Decal shader |
| `402ae1c33e4c28c45876b1bc945b77e6` | ProRacer_ParticlesUnlit | particles.gdshader | Low | Unlit particles |
| `da24369d453e6a547aaa57ebee28fc81` | ProRacer_CutoutFlipbook | polygon.gdshader | Low | Crowd flipbook |
| `8e5d248915e86014095ff0547bc0c755` | ProRacerAdvanced | polygon.gdshader | Low | Advanced vehicle |
| `1bf4a2dc982313347912f313ba25f563` | RoadSHD | polygon.gdshader | Low | Road shader |
| **Desert** |||||
| `56ef766d507df464fb2a1726a99c925f` | Heat Shimmer | particles.gdshader | Rare | AridDesert distortion |
| **Modular Fantasy Hero** |||||
| `e603b0446c7f2804db0c8dd0fb5c1af0` | POLYGON_CustomCharacters | polygon.gdshader | Low | 15-zone mask system |
| **Viking** |||||
| `b83105300c9f7fb42a6e1b790fd2bd29` | ParticlesLit | particles.gdshader | Low | Lit particles |
| `00eec7c5cd1f4c6429ffee9a690c3d16` | ParticlesUnlit | particles.gdshader | Low | Unlit particles |

#### Effects Shaders

Specialized shaders for visual effects (holograms, neon, magic, screens, etc.).

| GUID | Shader Type | Godot Shader | Frequency | Notes |
|------|-------------|--------------|-----------|-------|
| **SciFi Effects** |||||
| `0835602ed30128f4a88a652bf920fcaa` | Polygon_UVScroll | polygon.gdshader | Low | Animated UV scrolling |
| `2b5804ffd3081d344bed894a653e3014` | Hologram | polygon.gdshader | Low | Hologram effect |
| `5c2ccdfe181d55b42bd5313305f194e4` | SciFiHorror_Screens | polygon.gdshader | Low | CRT monitor effect |
| `77e5bdd170fa4a4459dea431aba43e3c` | SciFiHorror_Decals | polygon.gdshader | Low | Decal shader |
| `972cd3fede1c33342b0f52ad57f47d90` | SciFiHorror_BlinkingLights | polygon.gdshader | Low | Animated lights |
| `c48a4461fec61fc45a01e7d6a50e520f` | SciFiPlant | foliage.gdshader | Low | Sci-fi vegetation |
| **Horror/Neon Effects** |||||
| `325b924500ba5804aa4b407d80084502` | Neon Shader | polygon.gdshader | Low | Neon glow effect |
| `0ecc70cac2c8895439f5094ba6660db8` | GrungeTriplanar | polygon.gdshader | Rare | Triplanar + grunge |
| `5d828b280155912429aa717d34cd8879` | Ghost | polygon.gdshader | Rare | Transparency + rim |
| **Urban/City Effects** |||||
| `62e87ad08a1afa642830420bf8e0dd4d` | CyberCity_Triplanar | polygon.gdshader | Low | Urban triplanar |
| `2a33a166317493947a7be330dcc78a05` | Parallax_Full | polygon.gdshader | Low | Interior window mapping |
| `e9556606a5f42464fa7dd78d624dc180` | Hologram_01 | polygon.gdshader | Low | Urban hologram |
| `a49be8e7504a48b4fba9b0c2a7fad57b` | EmissiveScroll | polygon.gdshader | Low | LED panel animation |
| `1f67b66c29dfd4f45aa8cc07bf5e901a` | EmissiveColourChange | polygon.gdshader | Rare | Color-changing emissive |
| `a711ca3b984db6a4e81ec2d50ca4c0ca` | Building | polygon.gdshader | Low | Background buildings |
| `5d014726978e80a43b6178cba929343b` | FlipbookCutout | polygon.gdshader | Rare | Animated flipbook |
| `a7331fc07349b124c8c15d545676f9ed` | Zombies | polygon.gdshader | Rare | Blood overlay system |
| **Dark Fantasy/Magic Effects** |||||
| `d0be6b296f23e8d459e94b4007017ea0` | Magic Glow/Runes | polygon.gdshader | Low | Animated glow runes |
| `e8b857c3d7fea464e942e1c1f0940e96` | Magical Portal | polygon.gdshader | Rare | Portal effect |
| `e312e3877c798a44dba23093a3417a94` | Liquid/Potion | polygon.gdshader | Rare | Liquid wobble effect |
| `a2cae5b0e99e16249b9a2163a7087bcb` | Wind Animation | foliage.gdshader | Rare | Cloth/sail animation |
| **Apocalypse/Destruction** |||||
| `f3534f26c7b573c45a1346e0634d57fc` | Generic_Basic_Bloody | polygon.gdshader | Rare | Blood overlay variant |
| `e17f8fe2503580447a3784d34b316d11` | Triplanar_Basic | polygon.gdshader | Low | Basic triplanar |

#### Legacy/Fallback Shaders

Older shaders from 2021 packs and Unity built-in fallbacks.

| GUID | Shader Type | Godot Shader | Frequency | Notes |
|------|-------------|--------------|-----------|-------|
| `933532a4fcc9baf4fa0491de14d08ed7` | Unity URP Lit | polygon.gdshader | High | URP fallback |
| `1ab581f9e0198304996581171522f458` | Water (Amplify) | water.gdshader | Rare | Nature 2021 legacy |
| `4b0390819f518774fa1a44198298459a` | Foliage (Amplify) | foliage.gdshader | Rare | Nature 2021 legacy |
| `0000000000000000f000000000000000` | Unity Built-in | polygon.gdshader | Rare | Default fallback |

### Fallback: Name Pattern Matching

If GUID lookup fails, the converter uses material name pattern matching:

| Pattern | Godot Shader |
|---------|--------------|
| `*Tree*`, `*Fern*`, `*Leaf*`, `*Grass*`, `*Vine*`, `*Branch*`, `*Willow*` | foliage.gdshader |
| `*Crystal*`, `*Glass*`, `*Gem*`, `*Ice*` | crystal.gdshader |
| `*Water*`, `*Ocean*`, `*River*`, `*Lake*`, `*Pond*` | water.gdshader |
| `*Cloud*`, `*Sky_Cloud*` | clouds.gdshader |
| `*Particle*`, `*FX_*`, `*Fog*` | particles.gdshader |
| `*Skydome*`, `*SkyDome*`, `*Sky_Dome*` | skydome.gdshader |
| `*Triplanar*` | polygon.gdshader (triplanar mode) |
| Everything else | polygon.gdshader |

---

## Parameter Mapping

Parameter mapping converts Unity material properties to Godot shader uniforms. Each shader has specific parameters organized by priority:

- **Required**: Essential for the material to render correctly
- **Visual**: Affects appearance significantly
- **Optional**: Fine-tuning and advanced features

### Foliage Shader (Trees, Ferns, Grass)

**Required Parameters:**

| Unity Parameter | Godot Parameter | Type | Notes |
|-----------------|-----------------|------|-------|
| `_Leaf_Texture` | `leaf_color` | Texture2D | Primary leaf texture |
| `_Trunk_Texture` | `trunk_color` | Texture2D | Primary trunk/bark texture |
| `_Alpha_Clip_Threshold` | `alpha_clip_threshold` | float | Cutoff for transparency |

**Visual Parameters:**

| Unity Parameter | Godot Parameter | Type |
|-----------------|-----------------|------|
| `_Leaf_Normal` | `leaf_normal` | Texture2D |
| `_Trunk_Normal` | `trunk_normal` | Texture2D |
| `_Leaf_Ambient_Occlusion` | `leaf_ao` | Texture2D |
| `_Trunk_Ambient_Occlusion` | `trunk_ao` | Texture2D |
| `_LeafSmoothness` / `_Leaf_Smoothness` | `leaf_smoothness` | float |
| `_TrunkSmoothness` / `_Trunk_Smoothness` | `trunk_smoothness` | float |

**Wind Animation Parameters (Optional):**

| Unity Parameter | Godot Parameter | Type |
|-----------------|-----------------|------|
| `_Enable_Breeze` | `enable_breeze` | bool |
| `_Breeze_Strength` | `breeze_strength` | float |
| `_Enable_Light_Wind` | `enable_light_wind` | bool |
| `_Light_Wind_Strength` | `light_wind_strength` | float |
| `_Enable_Strong_Wind` | `enable_strong_wind` | bool |
| `_Strong_Wind_Strength` | `strong_wind_strength` | float |
| `_Enable_Wind_Twist` | `enable_wind_twist` | bool |
| `_Wind_Twist_Strength` | `wind_twist_strength` | float |
| `_Enable_Frosting` | `enable_frosting` | bool |

**Required Global Shader Variables** (set in project.godot):
- `WindDirection` (vec3)
- `WindIntensity` (float)
- `GaleStrength` (float)

### Polygon Shader (Props, Terrain, Triplanar)

**Required Parameters:**

| Unity Parameter | Godot Parameter | Type | Notes |
|-----------------|-----------------|------|-------|
| `_Base_Texture` | `base_texture` | Texture2D | Primary color/albedo |

**Visual Parameters:**

| Unity Parameter | Godot Parameter | Type |
|-----------------|-----------------|------|
| `_Normal_Texture` | `normal_texture` | Texture2D |
| `_Emission_Texture` | `emission_texture` | Texture2D |
| `_AO_Texture` | `ao_texture` | Texture2D |
| `_Smoothness` | `smoothness` | float |
| `_Metallic` | `metallic` | float |
| `_Color_Tint` | `color_tint` | Color |

**Triplanar Parameters (Optional):**

| Unity Parameter | Godot Parameter | Type |
|-----------------|-----------------|------|
| `_Enable_Triplanar_Texture` | `enable_triplanar_texture` | bool |
| `_Triplanar_Texture_Top` | `triplanar_texture_top` | Texture2D |
| `_Triplanar_Texture_Side` | `triplanar_texture_side` | Texture2D |
| `_Triplanar_Texture_Bottom` | `triplanar_texture_bottom` | Texture2D |
| `_Enable_Snow` | `enable_snow` | bool |
| `_Snow_Level` | `snow_level` | float |

### Crystal Shader (Crystals, Glass, Gems)

**Required Parameters:**

| Unity Parameter | Godot Parameter | Type | Notes |
|-----------------|-----------------|------|-------|
| `_Base_Albedo` | `base_albedo` | Texture2D | Crystal texture |
| `_Opacity` | `opacity` | float | Default: 0.7 for translucency |

**Visual Parameters:**

| Unity Parameter | Godot Parameter | Type |
|-----------------|-----------------|------|
| `_Base_Normal` | `base_normal` | Texture2D |
| `_Base_Color_Multiplier` | `base_color` | Color |
| `_Metallic` | `metallic` | float |
| `_Smoothness` | `smoothness` | float |

**Fresnel & Depth (Optional):**

| Unity Parameter | Godot Parameter | Type |
|-----------------|-----------------|------|
| `_Enable_Fresnel` / `_Enable_Side_Fresnel` | `enable_fresnel` | bool |
| `_Fresnel_Color` | `fresnel_color` | Color |
| `_Fresnel_Power` | `fresnel_power` | float |
| `_Enable_Depth` | `enable_depth` | bool |
| `_Deep_Color` | `deep_color` | Color |
| `_Shallow_Color` | `shallow_color` | Color |

**Refraction (Optional):**

| Unity Parameter | Godot Parameter | Type |
|-----------------|-----------------|------|
| `_Enable_Refraction` | `enable_refraction` | bool |
| `_Refraction_Texture` | `refraction_texture` | Texture2D |
| `_Refraction_Height` | `refraction_height` | Texture2D |
| `_Enable_Triplanar` | `enable_triplanar` | bool |

### Water Shader (Rivers, Lakes, Oceans)

**Required Parameters:**

| Unity Parameter | Godot Parameter | Type | Notes |
|-----------------|-----------------|------|-------|
| `_Shallow_Color` | `shallow_color` | Color | Water edge color |
| `_Deep_Color` | `deep_color` | Color | Water depth color |

**Surface Parameters:**

| Unity Parameter | Godot Parameter | Type |
|-----------------|-----------------|------|
| `_Smoothness` | `smoothness` | float |
| `_Metallic` | `metallic` | float |
| `_Base_Opacity` | `base_opacity` | float |
| `_Very_Deep_Color` | `very_deep_color` | Color |
| `_Maximum_Depth` | `maximum_depth` | float |

**Normal/Wave Parameters:**

| Unity Parameter | Godot Parameter | Type |
|-----------------|-----------------|------|
| `_Enable_Normals` | `enable_normals` | bool |
| `_Normal_Texture` | `normal_texture` | Texture2D |
| `_Normal_Intensity` | `normal_intensity` | float |
| `_Enable_Ocean_Waves` | `enable_ocean_waves` | bool |
| `_Ocean_Wave_Height` | `ocean_wave_height` | float |
| `_Ocean_Wave_Speed` | `ocean_wave_speed` | float |

**Foam & Shore (Optional):**

| Unity Parameter | Godot Parameter | Type |
|-----------------|-----------------|------|
| `_Enable_Shore_Wave_Foam` | `enable_shore_wave_foam` | bool |
| `_Shore_Wave_Speed` | `shore_wave_speed` | float |
| `_Enable_Shore_Foam` | `enable_shore_foam` | bool |

**Effects (Optional):**

| Unity Parameter | Godot Parameter | Type |
|-----------------|-----------------|------|
| `_Enable_Caustics` | `enable_caustics` | bool |
| `_Caustics_Flipbook` | `caustics_flipbook` | Texture2D |
| `_Enable_Distortion` | `enable_distortion` | bool |
| `_Distortion_Strength` | `distortion_strength` | float |

**Required Global Shader Variables:**
- `WindDirection` (vec3)
- `GaleStrength` (float)
- `OceanWavesGradient` (sampler2D)

### Character Shader Properties (Hair/Skin System)

Character materials in Fantasy Kingdom and Samurai Empire use:

| Unity Parameter | Godot Parameter | Type | Priority |
|-----------------|-----------------|------|----------|
| `_Hair_Mask` | `hair_mask` | Texture2D | Required |
| `_Skin_Mask` | `skin_mask` | Texture2D | Required |
| `_Hair_Color` | `hair_color` | Color | Visual |
| `_Skin_Color` | `skin_color` | Color | Visual |

These are alpha=0 fix candidates (add to the fix list).

### Clouds Shader (Volumetric Clouds)

**Core Parameters:**

| Unity Parameter | Godot Parameter | Type | Priority |
|-----------------|-----------------|------|----------|
| `_Top_Color` | `top_color` | Color | Required |
| `_Base_Color` | `base_color` | Color | Required |
| `_Cloud_Speed` | `cloud_speed` | float | Visual |
| `_Cloud_Strength` | `cloud_strength` | float | Visual |

**Lighting (Optional):**

| Unity Parameter | Godot Parameter | Type |
|-----------------|-----------------|------|
| `_Use_Environment_Override` | `use_environment_override` | bool |
| `_Light_Direction_Override` | `light_direction_override` | vec3 |
| `_Light_Intensity` | `light_intensity` | float |

**Effects (Optional):**

| Unity Parameter | Godot Parameter | Type |
|-----------------|-----------------|------|
| `_Enable_Fresnel` | `enable_fresnel` | bool |
| `_Fresnel_Power` | `fresnel_power` | float |
| `_Fresnel_Color` | `fresnel_color` | Color |
| `_Enable_Fog` | `enable_fog` | bool |
| `_Fog_Density` | `fog_density` | float |
| `_Enable_Scattering` | `enable_scattering` | bool |
| `_Scattering_Multiplier` | `scattering_multiplier` | float |
| `_Scattering_Color` | `scattering_color` | Color |

**Required Global Shader Variables:**
- `MainLightDirection` (vec3)
- `SkyColor` (Color)
- `EquatorColor` (Color)
- `GroundColor` (Color)

### Particles Shader (Effects, Fog)

**Core Parameters:**

| Unity Parameter | Godot Parameter | Type | Priority |
|-----------------|-----------------|------|----------|
| `_Albedo_Map` | `albedo_map` | Texture2D | Required |
| `_Base_Color` | `base_color` | Color | Visual |
| `_Alpha_Clip_Treshold` | `alpha_clip_treshold` | float | Visual |

**Transform (Optional):**

| Unity Parameter | Godot Parameter | Type |
|-----------------|-----------------|------|
| `_Tiling` | `tiling` | vec2 |
| `_Offset` | `offset` | vec2 |

**Soft Particles (Optional):**

| Unity Parameter | Godot Parameter | Type |
|-----------------|-----------------|------|
| `_Enable_Soft_Particles` | `enable_soft_particles` | bool |
| `_Soft_Power` | `soft_power` | float |
| `_Soft_Distance` | `soft_distance` | float |

**Camera Fade (Optional):**

| Unity Parameter | Godot Parameter | Type |
|-----------------|-----------------|------|
| `_Enable_Camera_Fade` | `enable_camera_fade` | bool |
| `_Camera_Fade_Near` | `camera_fade_near` | float |
| `_Camera_Fade_Far` | `camera_fade_far` | float |
| `_Enable_Scene_Fog` | `enable_scene_fog` | bool |
| `_Fog_Color` | `fog_color` | Color |

### Skydome Shader (Sky Gradient)

| Unity Parameter | Godot Parameter | Type | Priority |
|-----------------|-----------------|------|----------|
| `_Top_Color` | `top_color` | Color | Required |
| `_Bottom_Color` | `bottom_color` | Color | Required |
| `_Falloff` | `falloff` | float | Visual |
| `_Offset` | `offset` | float | Optional |
| `_Distance` | `distance_` | float | Optional |
| `_Enable_UV_Based` | `enable_uv_based` | bool | Optional |

### Advanced Shader Features

These parameters are used by specialized shaders for specific visual effects.

**Hologram Effects:**
- `_HoloLines`, `_Scroll_Speed`, `_Opacity`, `_Neon_Colour_01`, `_Neon_Colour_02`
- `_Enable_Hologram`, `_Hologram_Color`, `_Hologram_Intensity`

**Screen/Monitor Effects (SciFi):**
- `_Screen_Bulge`, `_Screen_Flicker_Frequency`, `_Scan_Line_Map`
- `_Vignette_Amount`, `_Pixelation_Amount`, `_CRT_Curve`

**Interior Mapping (Parallax Windows):**
- `_Floor`, `_Wall`, `_Ceiling`, `_Back`, `_Props` - Interior textures
- `_RoomTile`, `_RoomIntensity`, `_WindowAlpha`, `_RoomDepth`

**Ghost/Transparency:**
- `_Transparency`, `_RimPower`, `_RimColor`, `_TransShadow`
- `_Enable_Ghost`, `_Ghost_Strength`

**Grunge/Dirt System:**
- `_Dirt_Amount`, `_Dust_Amount`, `_Dust_Colour`, `_Grunge`, `_Large_Grunge`
- `_Grunge_Map`, `_Grunge_Intensity`

**Magic Effects (Dark Fantasy):**
- `_Glow_Amount`, `_Glow_Colour`, `_Glow_Falloff`, `_Glow_Tint`
- `_dissolve`, `_twirlstr`, `_Rune_Texture`, `_Rune_Speed`

**Liquid/Potion:**
- `_liquidamount`, `_WobbleX`, `_WobbleZ`, `_Wave_Scale`
- `_Liquid_Color`, `_Foam_Line`, `_Rim_Width`

**Blood Overlay:**
- `_BloodAmount`, `_Blood_Mask`, `_BloodColor`, `_Blood_Color`
- `_Blood_Intensity`, `_Blood_Texture`

**LED/Neon Animation:**
- `_Brightness`, `_UVScrollSpeed`, `_Saturation`, `_LED_Mask_01`
- `_Neon_Intensity`, `_Pulse_Speed`

**Cloth/Sail Animation:**
- `_Enable_Wave`, `_Wave_Speed`, `_Wave_Amplitude`, `_Wave_Direction_Vector`
- `_Cloth_Mask`, `_Wind_Influence`

**Aurora/Northern Lights:**
- `_Aurora_Color_01`, `_Aurora_Color_02`, `_Aurora_Speed`
- `_Aurora_Intensity`, `_Aurora_Scale`

**Waterfall Effects (Elven Realm):**
- `_WaterColour`, `_FresnelColour`, `_FresnelPower`
- `_UVScrollSpeed`, `_VertexOffset_Toggle`

**Character Customization (Modular Fantasy Hero):**
- 5 mask textures: `_Mask_01`, `_Mask_02`, `_Mask_03`, `_Mask_04`, `_Mask_05`
- 15 color zones: `_Color_Primary`, `_Color_Secondary`, `_Color_Tertiary`
- Metal colors: `_Color_Metal_Primary`, `_Color_Metal_Secondary`, `_Color_Metal_Dark`
- Leather colors: `_Color_Leather_Primary`, `_Color_Leather_Secondary`
- Body colors: `_Color_Skin`, `_Color_Hair`, `_Color_Eyes`, `_Color_Stubble`, `_Color_Scar`, `_Color_BodyArt`
- `_BodyArt_Amount`, `_Tattoo_Amount` - Float controls

**Racing/Vehicle (Pro Racer):**
- `_Metallic_Map`, `_Use_Metallic_Map` - Metallic texture support
- Flipbook crowd: `_Flipbook_Width`, `_Flipbook_Height`, `_Flipbook_Speed`
- `_Randomize_Flipbook_From_Location` - Crowd variation

### Biome-Specific Features

**AridDesert - Heat Shimmer (GUID: `56ef766d507df464fb2a1726a99c925f`)**
- `_Enable_UV_Distortion` - Toggle distortion effect
- `_Distortion_strength` - Distortion amount
- `_Edge_Distortion_Intensity` - Edge blend
- `_Speed_X`, `_Speed_Y` - Animation speed

**AlpineMountain - Snow Sparkle**
- `_Enable_Brightness_Breakup` - Toggle sparkle
- `_Brightness_Breakup_*` - Sparkle parameters

**All NatureBiomes - Weather Controller**
- `_Use_Weather_Controller` - Global weather integration
- `_Use_Vertex_Color_Wind` - Per-vertex wind masking

### Property Name Alternatives

Unity materials may use different property names for the same slot. Check alternatives in order:

| Purpose | Check Order (first match wins) |
|---------|-------------------------------|
| Albedo Texture | `_Albedo_Map` -> `_BaseMap` -> `_MainTex` -> `_Base_Texture` |
| Normal Texture | `_Normal_Map` -> `_BumpMap` -> `_Normal_Texture` |
| Emission Texture | `_Emission_Map` -> `_EmissionMap` -> `_Emission_Texture` |
| AO Texture | `_AO_Texture` -> `_OcclusionMap` |
| Metallic Texture | `_Metallic_Smoothness_Texture` -> `_MetallicGlossMap` |
| Smoothness | `_Smoothness` -> `_Glossiness` |
| Normal Intensity | `_Normal_Intensity` -> `_Normal_Amount` -> `_BumpScale` |
| Alpha Cutoff | `_Alpha_Clip_Threshold` -> `_Cutoff` -> `_AlphaCutoff` |
| Color Tint | `_Color_Tint` -> `_Color` -> `_BaseColor` |
| Emission Color | `_Emission_Color` -> `_EmissionColor` |
| AO Intensity | `_AO_Intensity` -> `_OcclusionStrength` |

### Legacy Property Names (2021 and Earlier Packs)

Older Synty packs (like POLYGON Nature 2021) use Amplify Shader Editor with different property names:

| Modern Name (2022+) | Legacy Name (2021) | Type |
|---------------------|-------------------|------|
| `_Albedo_Map` | `_MainTexture` | Texture |
| `_Normal_Map` | `_BumpMap` | Texture |
| `_Emission_Map` | `_Emission` | Texture |
| `_Leaf_Texture` | `_Leaves_NoiseTexture` | Texture |
| `_Trunk_Texture` | `_Tree_NoiseTexture` | Texture |
| `_Color_Tint` | `_ColorTint` | Color |
| `_Deep_Color` | `_WaterDeepColor` | Color |
| `_Shallow_Color` | `_WaterShallowColor` | Color |
| `_Enable_Breeze` | `_Leaves_Wave` (float) | Bool/Float |
| `_Breeze_Strength` | `_Leaves_WindAmount` | Float |
| `_Enable_Light_Wind` | `_Tree_Wave` (float) | Bool/Float |
| `_Light_Wind_Strength` | `_Tree_WindAmount` | Float |

When parsing materials, check for legacy names as fallback.

---

## Unity Parsing Quirks

This section provides a brief overview of Unity material parsing challenges. For detailed troubleshooting and solutions, see **[Troubleshooting](./troubleshooting.md#unity-quirks)**.

### Summary of Key Issues

**Alpha=0 Color Fix**: Unity stores many color properties with `alpha=0` even when colors should be visible. The converter automatically fixes this for known properties.

**Boolean Properties as Floats**: Unity stores boolean toggles as floats (`0.0` or `1.0`). The converter handles this automatically.

**Default Value Overrides**: Some materials need sensible defaults when Unity values are missing:

| Shader | Property | Unity Issue | Converter Default |
|--------|----------|-------------|-------------------|
| Crystal | `opacity` | Often 1.0 (fully opaque) | 0.7 (translucent) |
| Foliage | `leaf_smoothness` | Missing | 0.1 (matte) |
| Foliage | `trunk_smoothness` | Missing | 0.15 (slightly rough) |
| Foliage | `leaf_metallic` | Missing | 0.0 |
| Foliage | `trunk_metallic` | Missing | 0.0 |

**Unity YAML Format**: Unity .mat files use non-standard YAML with custom tags (`!u!21`). Use regex extraction rather than YAML parsing:

```python
# Extract Material section
material_match = re.search(
    r"---\s*!u!21[^\n]*\nMaterial:\s*\n((?:.*\n)*?)(?=---|\Z)",
    content, re.MULTILINE
)
```

---

## Texture Handling

### Supported Texture Formats

Based on analysis of all Synty packs, only 3 formats are used:

| Format | Usage | Notes |
|--------|-------|-------|
| PNG | 76% | Primary format |
| TGA | 23% | Secondary format |
| JPG/JPEG | <1% | Rare |

```python
SUPPORTED_TEXTURE_EXTENSIONS = {".png", ".tga", ".jpg", ".jpeg"}
```

### Texture Discovery

Build a name->path map from SourceFiles:

```python
def build_texture_map(textures_dir: Path) -> dict[str, Path]:
    """Map texture names (lowercase, no extension) to file paths."""
    texture_map = {}
    for tex_file in textures_dir.rglob("*"):
        if tex_file.suffix.lower() in {".png", ".jpg", ".jpeg", ".tga"}:
            # Key: lowercase stem for fuzzy matching
            texture_map[tex_file.stem.lower()] = tex_file
    return texture_map
```

### Texture Resolution Flow

```
Unity Material -> GUID -> pathname (from Unity metadata) -> texture name
                                                              |
                                              texture_map lookup
                                                              |
                                              SourceFiles path
```

### Missing Texture Handling

If a texture name from Unity doesn't exist in SourceFiles:
1. Log warning with material name and missing texture
2. Skip that texture slot in the generated .tres
3. Continue processing

---

## Appendix: Material Property Statistics

Based on analysis of **29 Unity packages** (~3,300 materials total):

### Original 9 Packs (978 materials)

| Pack | Materials | Primary Shaders |
|------|-----------|-----------------|
| POLYGON_Fantasy_Kingdom | 92 | PolygonLit, Generic_Standard |
| POLYGON_NatureBiomes_AlpineMountain | 139 | Foliage, PolygonLit, Triplanar |
| POLYGON_NatureBiomes_AridDesert | 108 | Foliage, PolygonLit, Heat Shimmer |
| POLYGON_NatureBiomes_EnchantedForest | 109 | Foliage, PolygonLit, Crystal |
| POLYGON_NatureBiomes_MeadowForest | 130 | Foliage, PolygonLit, Particles |
| POLYGON_NatureBiomes_SwampMarshland | 82 | Foliage, PolygonLit, Water |
| POLYGON_NatureBiomes_TropicalJungle | 123 | Foliage, PolygonLit |
| POLYGON_Nature (2021) | 78 | Amplify shaders (legacy) |
| POLYGON_Samurai_Empire | 226 | PolygonLit, Foliage, Character |

### Additional 16 Packs (~1,820 materials)

| Pack | Materials | Notable Shaders |
|------|-----------|-----------------|
| POLYGON_SciFi_Space | ~150 | UVScroll, Hologram, SciFiPlant |
| POLYGON_SciFi_Horror | ~120 | Screens, Decals, BlinkingLights |
| POLYGON_Horror_Mansion | ~100 | Neon, GrungeTriplanar, Ghost |
| POLYGON_Cyberpunk | ~180 | Hologram, Neon, EmissiveScroll |
| POLYGON_City | ~200 | Building, Parallax, LED panels |
| POLYGON_Zombies | ~90 | Blood overlay, Decals |
| POLYGON_Dark_Fantasy | ~140 | Magic Glow, Portal, Liquid |
| POLYGON_Viking | ~130 | Aurora, ParticlesLit, Cloth |
| POLYGON_Apocalypse | ~110 | Bloody, Triplanar_Basic, Grunge |
| POLYGON_Western | ~95 | PolygonLit, Dust system |
| POLYGON_Pirates | ~120 | Water, Cloth, Ropes |
| POLYGON_Dungeons | ~85 | Magic, Crystal, Torches |
| POLYGON_Farm | ~90 | PolygonLit, Foliage |
| POLYGON_Town | ~80 | PolygonLit, Glass |
| POLYGON_Kids | ~70 | PolygonLit (bright colors) |
| POLYGON_Prototype | ~60 | Basic PolygonLit |
| POLYGON_Elven_Realm | 127 | RockTriplanar, WaterFall, Aurora, NoFog |
| POLYGON_Pro_Racer | 230 | ProRacer_Standard, Decal, CutoutFlipbook, RoadSHD |
| POLYGON_Military | 111 | PolygonLit (standard PBR) |
| POLYGON_Modular_Fantasy_Hero | 33 | POLYGON_CustomCharacters (15-zone mask) |

### Summary Statistics

| Metric | Count |
|--------|-------|
| Total Packs Analyzed | 29 |
| Total Materials | ~3,300 |
| Unique Shader GUIDs | ~85 |
| Unique Texture Properties | ~90 |
| Unique Float Properties | ~450+ |
| Unique Color Properties | ~220+ |
