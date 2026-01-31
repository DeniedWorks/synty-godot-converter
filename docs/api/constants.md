# Constants Reference

> **For conceptual understanding:** See [Step 6: Shader Detection](../steps/06-shader-detection.md) for how these constants are used in the detection and mapping pipeline.

## Overview

The `shader_mapping.py` module contains extensive constant dictionaries that drive the material conversion process. These constants handle:

1. **Shader Detection** - Mapping Unity shader GUIDs to Godot shader files
2. **Property Conversion** - Translating Unity material properties to Godot equivalents
3. **Quirk Handling** - Fixing Unity's alpha=0 colors and boolean-as-float storage
4. **Default Values** - Sensible defaults when Unity values are missing

**Verified Counts (run `python shader_mapping.py` to confirm):**
- Known shader GUIDs: **56**
- Name fallback patterns: **20**
- Alpha-fix properties: **73**
- Boolean-float properties: **45**

Understanding these constants is essential for:
- Adding support for new Synty packages
- Debugging material conversion issues
- Extending the converter with new shader types

---

## SHADER_GUID_MAP

Maps Unity shader GUIDs to Godot shader filenames. Contains **56 entries** based on analysis of 29 Synty Unity packages (~3,300 materials).

### Quick Lookup (Most Common)

| GUID | Godot Shader | Unity Shader | Usage |
|------|--------------|--------------|-------|
| `0730dae39bc73f34796280af9875ce14` | polygon.gdshader | Synty PolygonLit | Main prop shader |
| `9b98a126c8d4d7a4baeb81b16e4f7b97` | foliage.gdshader | Synty Foliage | Trees/plants |
| `0736e099ec10c9e46b9551b2337d0cc7` | particles.gdshader | Synty Particles | Particle effects |
| `19e269a311c45cd4482cf0ac0e694503` | polygon.gdshader | Synty Triplanar | Terrain mode |
| `436db39b4e2ae5e46a17e21865226b19` | water.gdshader | Synty Water | Water surfaces |
| `5808064c5204e554c89f589a7059c558` | crystal.gdshader | Synty Crystal | Crystals/gems |
| `de1d86872962c37429cb628a7de53613` | skydome.gdshader | Synty Skydome | Sky gradient |
| `4a6c8c23090929241b2a55476a46a9b1` | clouds.gdshader | Synty Clouds | Volumetric clouds |

### Core Synty Shaders

| GUID | Godot Shader | Description |
|------|--------------|-------------|
| `0730dae39bc73f34796280af9875ce14` | polygon.gdshader | Synty PolygonLit (main prop shader) |
| `9b98a126c8d4d7a4baeb81b16e4f7b97` | foliage.gdshader | Synty Foliage (trees/plants) |
| `0736e099ec10c9e46b9551b2337d0cc7` | particles.gdshader | Synty Particles |
| `19e269a311c45cd4482cf0ac0e694503` | polygon.gdshader | Synty Triplanar (triplanar mode) |
| `436db39b4e2ae5e46a17e21865226b19` | water.gdshader | Synty Water |
| `5808064c5204e554c89f589a7059c558` | crystal.gdshader | Synty Crystal |
| `de1d86872962c37429cb628a7de53613` | skydome.gdshader | Synty Skydome |
| `4a6c8c23090929241b2a55476a46a9b1` | clouds.gdshader | Synty Clouds |
| `dfec08fb273e4674bb5398df25a5932c` | foliage.gdshader | Synty Leaf Card |
| `fdea4239d29733541b44cd6960afefcd` | crystal.gdshader | Synty Glass |
| `3b44a38ec6f81134ab0f820ac54d6a93` | polygon.gdshader | Generic_Standard (character hair/skin) |

### Skydome Variants

| GUID | Godot Shader | Description |
|------|--------------|-------------|
| `3d532bc2d70158948859b7839127e562` | skydome.gdshader | Skybox_Generic (procedural) |
| `74fa94d128fe4f348889c6f5f182e0e1` | skydome.gdshader | Skydome variant (NatureBiomes) |

### SciFi Shaders

| GUID | Godot Shader | Description |
|------|--------------|-------------|
| `0835602ed30128f4a88a652bf920fcaa` | polygon.gdshader | Polygon_UVScroll (animated UV) |
| `2b5804ffd3081d344bed894a653e3014` | polygon.gdshader | Hologram |
| `5c2ccdfe181d55b42bd5313305f194e4` | polygon.gdshader | SciFiHorror_Screens (CRT) |
| `77e5bdd170fa4a4459dea431aba43e3c` | polygon.gdshader | SciFiHorror_Decals |
| `972cd3fede1c33342b0f52ad57f47d90` | polygon.gdshader | SciFiHorror_BlinkingLights |
| `c48a4461fec61fc45a01e7d6a50e520f` | foliage.gdshader | SciFiPlant |

### Horror Shaders

| GUID | Godot Shader | Description |
|------|--------------|-------------|
| `325b924500ba5804aa4b407d80084502` | polygon.gdshader | Neon Shader |
| `0ecc70cac2c8895439f5094ba6660db8` | polygon.gdshader | GrungeTriplanar |
| `5d828b280155912429aa717d34cd8879` | polygon.gdshader | Ghost (transparency + rim) |

### Urban/City Shaders

| GUID | Godot Shader | Description |
|------|--------------|-------------|
| `62e87ad08a1afa642830420bf8e0dd4d` | polygon.gdshader | CyberCity_Triplanar |
| `2a33a166317493947a7be330dcc78a05` | polygon.gdshader | Parallax_Full (interior window) |
| `e9556606a5f42464fa7dd78d624dc180` | polygon.gdshader | Hologram_01 (urban) |
| `a49be8e7504a48b4fba9b0c2a7fad57b` | polygon.gdshader | EmissiveScroll (LED panels) |
| `1f67b66c29dfd4f45aa8cc07bf5e901a` | polygon.gdshader | EmissiveColourChange |
| `a711ca3b984db6a4e81ec2d50ca4c0ca` | polygon.gdshader | Building (background) |
| `5d014726978e80a43b6178cba929343b` | polygon.gdshader | FlipbookCutout |
| `a7331fc07349b124c8c15d545676f9ed` | polygon.gdshader | Zombies (blood overlay) |

### Dark Fantasy/Magic Shaders

| GUID | Godot Shader | Description |
|------|--------------|-------------|
| `d0be6b296f23e8d459e94b4007017ea0` | polygon.gdshader | Magic Glow/Runes |
| `e8b857c3d7fea464e942e1c1f0940e96` | polygon.gdshader | Magical Portal |
| `e312e3877c798a44dba23093a3417a94` | polygon.gdshader | Liquid/Potion |
| `a2cae5b0e99e16249b9a2163a7087bcb` | foliage.gdshader | Wind Animation (cloth/sail) |

### Viking Shaders

| GUID | Godot Shader | Description |
|------|--------------|-------------|
| `d2820334f2975bb47ab3f2fffa1b4cbe` | skydome.gdshader | Aurora (northern lights) |
| `b83105300c9f7fb42a6e1b790fd2bd29` | particles.gdshader | ParticlesLit |
| `00eec7c5cd1f4c6429ffee9a690c3d16` | particles.gdshader | ParticlesUnlit |

### Apocalypse/Destruction Shaders

| GUID | Godot Shader | Description |
|------|--------------|-------------|
| `f3534f26c7b573c45a1346e0634d57fc` | polygon.gdshader | Generic_Basic_Bloody |
| `e17f8fe2503580447a3784d34b316d11` | polygon.gdshader | Triplanar_Basic |

### Elven Realm Shaders

| GUID | Godot Shader | Description |
|------|--------------|-------------|
| `e854bc7dc0cde7044b9000faaf0c4e11` | polygon.gdshader | RockTriplanar |
| `9b1e1d14d7778714391ae095571c3d4f` | water.gdshader | WaterFall (animated) |
| `df6b3a02955954d41bb15c534388ba14` | polygon.gdshader | NoFog (celestial) |
| `903fe97c2d85c8147a64932806c92eb1` | water.gdshader | Waterfall variant |
| `ca9b700964f37d84a90b00c70d981934` | skydome.gdshader | Aurora (Elven Realm) |

### Pro Racer Shaders

| GUID | Godot Shader | Description |
|------|--------------|-------------|
| `ab6da834753539b4989259dbf4bcc39b` | polygon.gdshader | ProRacer_Standard (128 uses) |
| `22e3738818284144eb7ada0a62acca66` | polygon.gdshader | ProRacer_Decal |
| `402ae1c33e4c28c45876b1bc945b77e6` | particles.gdshader | ProRacer_ParticlesUnlit |
| `da24369d453e6a547aaa57ebee28fc81` | polygon.gdshader | ProRacer_CutoutFlipbook |
| `8e5d248915e86014095ff0547bc0c755` | polygon.gdshader | ProRacerAdvanced |
| `1bf4a2dc982313347912f313ba25f563` | polygon.gdshader | RoadSHD |

### Character Shaders

| GUID | Godot Shader | Description |
|------|--------------|-------------|
| `e603b0446c7f2804db0c8dd0fb5c1af0` | polygon.gdshader | POLYGON_CustomCharacters (15-zone mask) |

### Legacy/Fallback Shaders

| GUID | Godot Shader | Description |
|------|--------------|-------------|
| `933532a4fcc9baf4fa0491de14d08ed7` | polygon.gdshader | Unity URP Lit (fallback) |
| `56ef766d507df464fb2a1726a99c925f` | particles.gdshader | Heat Shimmer (AridDesert) |
| `1ab581f9e0198304996581171522f458` | water.gdshader | Water (Amplify) - Nature 2021 |
| `4b0390819f518774fa1a44198298459a` | foliage.gdshader | Foliage (Amplify) - Nature 2021 |
| `0000000000000000f000000000000000` | polygon.gdshader | Unity Built-in (default fallback) |

### Adding New GUIDs

To add support for a new Unity shader:

1. **Find the GUID** in Unity's `.meta` file for the shader
2. **Determine the closest Godot shader** type (polygon, foliage, water, crystal, particles, skydome, clouds)
3. **Add the entry** to `SHADER_GUID_MAP`:
   ```python
   "new_guid_here": "polygon.gdshader",  # Description of shader
   ```
4. **Test conversion** with a material using that shader
5. **Update this documentation**

---

## SHADER_NAME_PATTERNS_SCORED

Scoring-based pattern matching used as fallback when GUID lookup fails or maps to the generic polygon shader. Contains **20 pattern groups**.

### How Scoring Works

The detection system uses a scoring algorithm:

1. **All patterns are checked** against the material name
2. **Scores accumulate** for each matching pattern
3. **Property-based detection** adds additional points
4. **Highest scoring shader wins** (minimum threshold: 20 points)
5. **Handles compound names** correctly (e.g., "Dirt_Leaves_Triplanar" -> polygon wins because triplanar=60 > leaves=20)

### Score Tiers

| Tier | Score Range | Description |
|------|-------------|-------------|
| High Priority | 50+ | Very specific technical terms |
| Medium-High | 40-49 | Clear material types |
| Medium | 30-39 | Common material types |
| Low-Medium | 20-29 | Generic vegetation terms |
| Low | 10-19 | Ambiguous terms |

### Pattern Table (Complete)

| Pattern | Target Shader | Score | Description |
|---------|---------------|-------|-------------|
| `triplanar` | polygon.gdshader | 60 | Rendering technique |
| `caustics` | water.gdshader | 55 | Water-specific effect |
| `fresnel\|refractive\|refraction` | crystal.gdshader | 55 | Crystal-specific optical effects |
| `soft.?particle` | particles.gdshader | 55 | Particle-specific rendering |
| `skydome\|sky_dome\|skybox\|sky_box` | skydome.gdshader | 55 | Sky rendering |
| `crystal\|gem\|jewel\|diamond\|ruby\|emerald\|sapphire\|amethyst\|quartz` | crystal.gdshader | 45 | Crystalline materials |
| `water\|ocean\|river\|lake\|waterfall` | water.gdshader | 45 | Water bodies |
| `particle\|fx_` | particles.gdshader | 45 | Particle/effects |
| `cloud\|clouds\|sky_cloud` | clouds.gdshader | 45 | Atmospheric clouds |
| `glass\|ice\|transparent\|translucent` | crystal.gdshader | 35 | Transparent materials |
| `pond\|stream\|liquid\|aqua\|sea` | water.gdshader | 35 | Water variations |
| `fog\|mist\|atmosphere` | clouds.gdshader | 35 | Atmospheric effects |
| `spark\|dust\|debris\|smoke\|fire\|rain\|snow\|splash` | particles.gdshader | 35 | Particle types |
| `aurora\|sky_gradient` | skydome.gdshader | 35 | Sky effects |
| `foliage\|vegetation` | foliage.gdshader | 35 | Plant life terms |
| `tree\|fern\|grass\|vine\|branch\|willow\|bush\|shrub\|hedge\|bamboo\|koru\|treefern` | foliage.gdshader | 25 | Specific plant types |
| `leaf\|leaves` | foliage.gdshader | 20 | Very common, low priority |
| `bark\|trunk\|undergrowth\|plant` | foliage.gdshader | 20 | Plant parts |
| `moss\|dirt` | polygon.gdshader | 15 | Often combined with triplanar |
| `effect\|additive` | particles.gdshader | 15 | Generic FX terms |

### Property-Based Scoring

In addition to name patterns, the system scores based on material properties:

**Per matching property: +10 points**

| Shader | Float Properties | Color Properties |
|--------|------------------|------------------|
| water.gdshader | `_Enable_Shore_Foam`, `_Shore_Wave_Speed`, `_Ocean_Wave_Height`, `_Maximum_Depth`, etc. | `_Water_Deep_Color`, `_Foam_Color`, `_Caustics_Color`, etc. |
| foliage.gdshader | `_Enable_Breeze`, `_Breeze_Strength`, `_Leaf_Smoothness`, `_Frosting_Falloff`, etc. | `_Leaf_Base_Color`, `_Trunk_Base_Color`, `_Frosting_Color`, etc. |
| clouds.gdshader | `_Cloud_Speed`, `_Cloud_Strength`, `_Scattering_Multiplier`, `_Light_Intensity`, etc. | `_Scattering_Color` |
| particles.gdshader | `_Soft_Power`, `_Soft_Distance`, `_Camera_Fade_Near`, `_Camera_Fade_Far`, etc. | - |
| skydome.gdshader | `_Falloff`, `_Offset`, `_Distance` | `_Top_Color`, `_Bottom_Color` |
| crystal.gdshader | `_Enable_Fresnel`, `_Fresnel_Power`, `_Opacity`, `_Deep_Depth`, etc. | `_Fresnel_Color`, `_Refraction_Color` |

---

## Texture Property Mappings

### TEXTURE_MAP_FOLIAGE

Maps Unity texture properties to Godot parameters for the foliage shader.

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Leaf_Texture` | `leaf_color` | Main leaf albedo texture |
| `_Leaf_Normal` | `leaf_normal` | Leaf normal map |
| `_Trunk_Texture` | `trunk_color` | Trunk/bark albedo texture |
| `_Trunk_Normal` | `trunk_normal` | Trunk normal map |
| `_Leaf_Ambient_Occlusion` | `leaf_ao` | Leaf AO map |
| `_Trunk_Ambient_Occlusion` | `trunk_ao` | Trunk AO map |
| `_Leaves_NoiseTexture` | `leaf_color` | Legacy leaf texture (2021 and earlier) |
| `_Tree_NoiseTexture` | `trunk_color` | Legacy trunk texture (2021 and earlier) |

### TEXTURE_MAP_POLYGON

Maps Unity texture properties to Godot parameters for the polygon shader. This is the largest texture map with **37 entries**.

#### Base Textures

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Base_Texture` | `base_texture` | Primary albedo texture |
| `_Albedo_Map` | `base_texture` | Alternative albedo name |
| `_BaseMap` | `base_texture` | URP standard name |
| `_MainTex` | `base_texture` | Built-in standard name |
| `_MainTexture` | `base_texture` | Legacy name |

#### Normal Maps

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Normal_Texture` | `normal_texture` | Normal map |
| `_Normal_Map` | `normal_texture` | Alternative name |
| `_BumpMap` | `normal_texture` | Legacy bump map |

#### Emission Textures

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Emission_Texture` | `emission_texture` | Emission map |
| `_Emission_Map` | `emission_texture` | Alternative name |
| `_EmissionMap` | `emission_texture` | URP name |
| `_Emission` | `emission_texture` | Legacy name |

#### PBR Textures

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_AO_Texture` | `ao_texture` | Ambient occlusion |
| `_OcclusionMap` | `ao_texture` | URP occlusion |
| `_Metallic_Smoothness_Texture` | `metallic_texture` | Metallic/smoothness packed |
| `_MetallicGlossMap` | `metallic_texture` | URP metallic |
| `_Metallic_Map` | `metallic_texture` | Pro Racer metallic |

#### Triplanar Textures

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Triplanar_Texture_Top` | `triplanar_texture_top` | Top projection texture |
| `_Triplanar_Texture_Side` | `triplanar_texture_side` | Side projection texture |
| `_Triplanar_Texture_Bottom` | `triplanar_texture_bottom` | Bottom projection texture |

#### Character Textures

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Hair_Mask` | `hair_mask` | Hair region mask |
| `_Skin_Mask` | `skin_mask` | Skin region mask |
| `_Mask_01` through `_Mask_05` | `mask_01` through `mask_05` | Modular Fantasy Hero zone masks |

#### Special Effect Textures

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Grunge_Map` | `grunge_map` | Dirt/grunge overlay |
| `_Blood_Mask` | `blood_mask` | Blood splatter mask |
| `_Blood_Texture` | `blood_texture` | Blood color texture |
| `_Rune_Texture` | `rune_texture` | Magic rune glyphs |
| `_Scan_Line_Map` | `scan_line_map` | CRT scan lines |
| `_LED_Mask_01` | `led_mask` | LED panel mask |
| `_Cloth_Mask` | `cloth_mask` | Cloth animation mask |

#### Interior Mapping Textures

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Floor` | `floor_texture` | Interior floor |
| `_Wall` | `wall_texture` | Interior walls |
| `_Ceiling` | `ceiling_texture` | Interior ceiling |
| `_Back` | `back_texture` | Interior back wall |
| `_Props` | `props_texture` | Interior props/furniture |

### TEXTURE_MAP_CRYSTAL

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Base_Albedo` | `base_albedo` | Crystal base color |
| `_Base_Normal` | `base_normal` | Crystal normal map |
| `_Refraction_Texture` | `refraction_texture` | Refraction distortion |
| `_Refraction_Height` | `refraction_height` | Refraction height map |

### TEXTURE_MAP_WATER

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Normal_Texture` | `normal_texture` | Water surface normals |
| `_Caustics_Flipbook` | `caustics_flipbook` | Animated caustics |

### TEXTURE_MAP_PARTICLES

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Albedo_Map` | `albedo_map` | Particle sprite texture |

### TEXTURE_MAP_SKYDOME

*No texture mappings - skydome uses procedural gradient*

### TEXTURE_MAP_CLOUDS

*No texture mappings - clouds use noise generation*

---

## Float Property Mappings

### FLOAT_MAP_FOLIAGE

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Metallic` | `metallic` | Overall metallic value |
| `_Smoothness` | `smoothness` | Overall smoothness |
| `_LeafSmoothness` | `leaf_smoothness` | Leaf surface smoothness |
| `_Leaf_Smoothness` | `leaf_smoothness` | Alternative name |
| `_TrunkSmoothness` | `trunk_smoothness` | Trunk surface smoothness |
| `_Trunk_Smoothness` | `trunk_smoothness` | Alternative name |
| `_Breeze_Strength` | `breeze_strength` | Light wind intensity |
| `_Light_Wind_Strength` | `light_wind_strength` | Medium wind intensity |
| `_Strong_Wind_Strength` | `strong_wind_strength` | Strong wind intensity |
| `_Wind_Twist_Strength` | `wind_twist_strength` | Twist motion amount |
| `_Alpha_Clip_Threshold` | `alpha_clip_threshold` | Alpha cutoff value |
| `_Leaves_WindAmount` | `breeze_strength` | Legacy wind (2021) |
| `_Tree_WindAmount` | `light_wind_strength` | Legacy trunk wind |
| `_Cutoff` | `alpha_clip_threshold` | Legacy alpha cutoff |
| `_AlphaCutoff` | `alpha_clip_threshold` | URP alpha cutoff |

### FLOAT_MAP_POLYGON

This is the largest float map with **77 entries**, organized by category.

#### Surface Properties

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Smoothness` | `smoothness` | Surface smoothness |
| `_Glossiness` | `smoothness` | Legacy smoothness |
| `_Metallic` | `metallic` | Metallic value |
| `_Normal_Intensity` | `normal_intensity` | Normal map strength |
| `_Normal_Amount` | `normal_intensity` | Alternative name |
| `_BumpScale` | `normal_intensity` | Legacy normal scale |
| `_AO_Intensity` | `ao_intensity` | AO map strength |
| `_OcclusionStrength` | `ao_intensity` | URP occlusion |
| `_Alpha_Clip_Threshold` | `alpha_clip_threshold` | Alpha cutoff |
| `_Cutoff` | `alpha_clip_threshold` | Legacy cutoff |
| `_AlphaCutoff` | `alpha_clip_threshold` | URP cutoff |

#### Snow Properties

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Snow_Level` | `snow_level` | Snow coverage amount |

#### Hologram Properties

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_HoloLines` | `holo_lines` | Hologram scan line count |
| `_Scroll_Speed` | `scroll_speed` | Hologram scroll animation |
| `_Opacity` | `opacity` | Hologram transparency |
| `_Hologram_Intensity` | `hologram_intensity` | Hologram brightness |

#### Screen/CRT Properties

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Screen_Bulge` | `screen_bulge` | CRT screen curvature |
| `_Screen_Flicker_Frequency` | `screen_flicker_frequency` | Flicker rate |
| `_Vignette_Amount` | `vignette_amount` | Edge darkening |
| `_Pixelation_Amount` | `pixelation_amount` | Pixel size |
| `_CRT_Curve` | `crt_curve` | CRT curvature strength |

#### Interior Mapping Properties

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_RoomTile` | `room_tile` | Room repetition |
| `_RoomIntensity` | `room_intensity` | Interior brightness |
| `_WindowAlpha` | `window_alpha` | Window transparency |
| `_RoomDepth` | `room_depth` | Parallax depth |

#### Ghost Properties

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Transparency` | `transparency` | Ghost transparency |
| `_RimPower` | `rim_power` | Rim lighting power |
| `_TransShadow` | `trans_shadow` | Transparency shadow |
| `_Ghost_Strength` | `ghost_strength` | Overall ghost effect |

#### Grunge Properties

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Dirt_Amount` | `dirt_amount` | Dirt overlay intensity |
| `_Dust_Amount` | `dust_amount` | Dust overlay intensity |
| `_Grunge_Intensity` | `grunge_intensity` | Overall grunge |

#### Magic Properties

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Glow_Amount` | `glow_amount` | Magic glow intensity |
| `_Glow_Falloff` | `glow_falloff` | Glow edge falloff |
| `_dissolve` | `dissolve` | Dissolve animation |
| `_twirlstr` | `twirl_strength` | Portal twirl effect |
| `_Rune_Speed` | `rune_speed` | Rune animation speed |

#### Liquid Properties

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_liquidamount` | `liquid_amount` | Fill level |
| `_WobbleX` | `wobble_x` | X-axis wobble |
| `_WobbleZ` | `wobble_z` | Z-axis wobble |
| `_Wave_Scale` | `wave_scale` | Surface wave size |
| `_Foam_Line` | `foam_line` | Foam edge width |
| `_Rim_Width` | `rim_width` | Container rim highlight |

#### Blood Properties

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_BloodAmount` | `blood_amount` | Blood coverage |
| `_Blood_Intensity` | `blood_intensity` | Blood color intensity |

#### LED/Neon Properties

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Brightness` | `brightness` | LED brightness |
| `_UVScrollSpeed` | `uv_scroll_speed` | UV animation speed |
| `_Saturation` | `saturation` | Color saturation |
| `_Neon_Intensity` | `neon_intensity` | Neon glow strength |
| `_Pulse_Speed` | `pulse_speed` | Neon pulse rate |

#### Cloth Properties

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Wave_Speed` | `wave_speed` | Cloth wave animation |
| `_Wave_Amplitude` | `wave_amplitude` | Wave height |
| `_Wind_Influence` | `wind_influence` | Wind responsiveness |

#### Character Properties

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_BodyArt_Amount` | `bodyart_amount` | Body art/tattoo blend |
| `_Tattoo_Amount` | `tattoo_amount` | Tattoo visibility |

#### Racing Properties

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Flipbook_Width` | `flipbook_width` | Animation columns |
| `_Flipbook_Height` | `flipbook_height` | Animation rows |
| `_Flipbook_Speed` | `flipbook_speed` | Animation FPS |

#### Heat Shimmer Properties

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Distortion_strength` | `distortion_strength` | Shimmer intensity |
| `_Edge_Distortion_Intensity` | `edge_distortion_intensity` | Edge distortion |
| `_Speed_X` | `speed_x` | Horizontal speed |
| `_Speed_Y` | `speed_y` | Vertical speed |

### FLOAT_MAP_CRYSTAL

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Metallic` | `metallic` | Crystal metallic value |
| `_Smoothness` | `smoothness` | Crystal smoothness |
| `_Opacity` | `opacity` | Crystal transparency |
| `_Fresnel_Power` | `fresnel_power` | Edge highlight power |

### FLOAT_MAP_WATER

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Smoothness` | `smoothness` | Water surface smoothness |
| `_Metallic` | `metallic` | Water metallic (usually 0) |
| `_Base_Opacity` | `base_opacity` | Water transparency |
| `_Maximum_Depth` | `maximum_depth` | Depth fade distance |
| `_Normal_Intensity` | `normal_intensity` | Wave normal strength |
| `_Shore_Wave_Speed` | `shore_wave_speed` | Shore animation speed |
| `_Ocean_Wave_Height` | `ocean_wave_height` | Wave vertex displacement |
| `_Ocean_Wave_Speed` | `ocean_wave_speed` | Open water wave speed |
| `_Distortion_Strength` | `distortion_strength` | Refraction distortion |
| `_FresnelPower` | `fresnel_power` | Waterfall fresnel |
| `_UVScrollSpeed` | `uv_scroll_speed` | Waterfall UV animation |

### FLOAT_MAP_PARTICLES

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Alpha_Clip_Treshold` | `alpha_clip_treshold` | Alpha cutoff (Unity typo preserved) |
| `_Soft_Power` | `soft_power` | Soft particle power |
| `_Soft_Distance` | `soft_distance` | Soft particle range |
| `_Camera_Fade_Near` | `camera_fade_near` | Near fade distance |
| `_Camera_Fade_Far` | `camera_fade_far` | Far fade distance |
| `_Fog_Density` | `fog_density` | Volumetric fog density |

### FLOAT_MAP_SKYDOME

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Falloff` | `falloff` | Gradient falloff curve |
| `_Offset` | `offset` | Horizon offset |
| `_Distance` | `distance_` | Sky distance (trailing underscore avoids reserved word) |

### FLOAT_MAP_CLOUDS

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Light_Intensity` | `light_intensity` | Cloud lighting |
| `_Fresnel_Power` | `fresnel_power` | Cloud edge highlight |
| `_Fog_Density` | `fog_density` | Fog blending |
| `_Scattering_Multiplier` | `scattering_multiplier` | Light scattering |
| `_Cloud_Speed` | `cloud_speed` | Cloud movement |
| `_Cloud_Strength` | `cloud_strength` | Cloud density |
| `_Aurora_Speed` | `aurora_speed` | Aurora animation |
| `_Aurora_Intensity` | `aurora_intensity` | Aurora brightness |
| `_Aurora_Scale` | `aurora_scale` | Aurora size |

---

## Color Property Mappings

### COLOR_MAP_FOLIAGE

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Color` | `color_tint` | Overall color tint |
| `_Color_Tint` | `color_tint` | Alternative name |
| `_ColorTint` | `color_tint` | Legacy name |
| `_Leaf_Base_Color` | `leaf_base_color` | Leaf albedo tint |
| `_Trunk_Base_Color` | `trunk_base_color` | Trunk albedo tint |
| `_Emissive_Color` | `emissive_color` | Leaf emission |
| `_Emissive_2_Color` | `emissive_2_color` | Secondary emission |
| `_Trunk_Emissive_Color` | `trunk_emissive_color` | Trunk emission |
| `_Frosting_Color` | `frosting_color` | Snow/frost tint |

### COLOR_MAP_POLYGON

This is the largest color map with **43 entries**.

#### Base Colors

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Color_Tint` | `color_tint` | Main color tint |
| `_Color` | `color_tint` | Alternative name |
| `_BaseColor` | `color_tint` | URP name |
| `_BaseColour` | `color_tint` | UK spelling |
| `_Emission_Color` | `emission_color` | Emission tint |
| `_EmissionColor` | `emission_color` | URP emission |
| `_Snow_Color` | `snow_color` | Snow tint |

#### Character Colors

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Hair_Color` | `hair_color` | Character hair |
| `_Skin_Color` | `skin_color` | Character skin |

#### Hologram Colors

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Neon_Colour_01` | `neon_color_01` | Primary neon |
| `_Neon_Colour_02` | `neon_color_02` | Secondary neon |
| `_Hologram_Color` | `hologram_color` | Hologram tint |

#### Effect Colors

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_RimColor` | `rim_color` | Ghost rim light |
| `_Dust_Colour` | `dust_color` | Grunge dust tint |
| `_Glow_Colour` | `glow_color` | Magic glow |
| `_Glow_Tint` | `glow_tint` | Glow modifier |
| `_Liquid_Color` | `liquid_color` | Potion liquid |
| `_BloodColor` | `blood_color` | Blood tint |
| `_Blood_Color` | `blood_color` | Alternative name |

#### Modular Fantasy Hero Colors (15-Zone System)

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Color_Primary` | `color_primary` | Primary fabric/material |
| `_Color_Secondary` | `color_secondary` | Secondary fabric |
| `_Color_Tertiary` | `color_tertiary` | Tertiary accents |
| `_Color_Metal_Primary` | `color_metal_primary` | Primary metal |
| `_Color_Metal_Secondary` | `color_metal_secondary` | Secondary metal |
| `_Color_Metal_Dark` | `color_metal_dark` | Dark metal accents |
| `_Color_Leather_Primary` | `color_leather_primary` | Primary leather |
| `_Color_Leather_Secondary` | `color_leather_secondary` | Secondary leather |
| `_Color_Skin` | `color_skin` | Skin tone |
| `_Color_Hair` | `color_hair` | Hair color |
| `_Color_Eyes` | `color_eyes` | Eye color |
| `_Color_Stubble` | `color_stubble` | Facial hair |
| `_Color_Scar` | `color_scar` | Scar tissue |
| `_Color_BodyArt` | `color_bodyart` | Tattoos/body art |

### COLOR_MAP_CRYSTAL

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Base_Color` | `base_color` | Crystal body color |
| `_Base_Color_Multiplier` | `base_color` | Color multiplier |
| `_Top_Color_Multiplier` | `top_color` | Top gradient color |
| `_Deep_Color` | `deep_color` | Deep interior color |
| `_Shallow_Color` | `shallow_color` | Surface color |
| `_Fresnel_Color` | `fresnel_color` | Edge highlight color |
| `_Refraction_Color` | `refraction_color` | Refracted light tint |

### COLOR_MAP_WATER

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Shallow_Color` | `shallow_color` | Near-surface color |
| `_Deep_Color` | `deep_color` | Deep water color |
| `_Very_Deep_Color` | `very_deep_color` | Abyss color |
| `_Foam_Color` | `foam_color` | Wave foam tint |
| `_Caustics_Color` | `caustics_color` | Caustics tint |
| `_Shore_Foam_Color_Tint` | `shore_foam_color_tint` | Shore foam color |
| `_Shore_Wave_Color_Tint` | `shore_wave_color_tint` | Shore wave color |
| `_WaterDeepColor` | `deep_color` | Legacy deep |
| `_WaterShallowColor` | `shallow_color` | Legacy shallow |
| `_Water_Deep_Color` | `deep_color` | Alternative name |
| `_Water_Shallow_Color` | `shallow_color` | Alternative name |
| `_Water_Near_Color` | `shallow_color` | Near camera color |
| `_Water_Far_Color` | `deep_color` | Far camera color |
| `_WaterColour` | `water_color` | Waterfall color |
| `_FresnelColour` | `fresnel_color` | Waterfall fresnel |

### COLOR_MAP_PARTICLES

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Base_Color` | `base_color` | Particle base tint |
| `_Fog_Color` | `fog_color` | Volumetric fog color |

### COLOR_MAP_SKYDOME

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Top_Color` | `top_color` | Sky zenith color |
| `_Bottom_Color` | `bottom_color` | Horizon color |

### COLOR_MAP_CLOUDS

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Top_Color` | `top_color` | Cloud top lit color |
| `_Base_Color` | `base_color` | Cloud base color |
| `_Fresnel_Color` | `fresnel_color` | Cloud edge highlight |
| `_Scattering_Color` | `scattering_color` | Light scattering tint |
| `_Aurora_Color_01` | `aurora_color_01` | Aurora primary |
| `_Aurora_Color_02` | `aurora_color_02` | Aurora secondary |

---

## Boolean Float Properties

Unity stores boolean toggles as floats (0.0 or 1.0). The converter automatically detects these and converts them to proper booleans.

Contains **45 properties** organized by shader type.

### Foliage Wind Toggles

| Property Name | Description |
|---------------|-------------|
| `_Enable_Breeze` | Enable light breeze animation |
| `_Enable_Light_Wind` | Enable medium wind |
| `_Enable_Strong_Wind` | Enable strong wind |
| `_Enable_Wind_Twist` | Enable twist motion |
| `_Enable_Frosting` | Enable snow/frost overlay |
| `_Leaves_Wave` | Legacy leaf animation |
| `_Tree_Wave` | Legacy trunk animation |

### Crystal/Glass Toggles

| Property Name | Description |
|---------------|-------------|
| `_Enable_Fresnel` | Enable edge fresnel |
| `_Enable_Side_Fresnel` | Enable side fresnel |
| `_Enable_Depth` | Enable depth-based coloring |
| `_Enable_Refraction` | Enable refraction distortion |
| `_Enable_Triplanar` | Enable triplanar projection |

### Polygon Toggles

| Property Name | Description |
|---------------|-------------|
| `_Enable_Triplanar_Texture` | Enable triplanar texturing |
| `_Enable_Snow` | Enable snow overlay |
| `_Enable_Emission` | Enable emission |
| `_Enable_Normals` | Enable normal mapping |
| `_AlphaClip` | Enable alpha clipping |
| `_Enable_Hologram` | Enable hologram effect |
| `_Enable_Ghost` | Enable ghost transparency |
| `_Use_Metallic_Map` | Use metallic texture |
| `_Use_Weather_Controller` | Use weather system |
| `_Use_Vertex_Color_Wind` | Use vertex colors for wind |
| `_Randomize_Flipbook_From_Location` | Randomize flipbook start |
| `_Enable_UV_Distortion` | Enable UV distortion |
| `_Enable_Brightness_Breakup` | Enable brightness variation |
| `_Enable_Wave` | Enable wave animation |

### Water Toggles

| Property Name | Description |
|---------------|-------------|
| `_Enable_Shore_Wave_Foam` | Enable shore wave foam |
| `_Enable_Shore_Foam` | Enable shore foam |
| `_Enable_Ocean_Waves` | Enable ocean wave animation |
| `_Enable_Caustics` | Enable caustic lighting |
| `_Enable_Distortion` | Enable refraction distortion |
| `_VertexOffset_Toggle` | Enable waterfall vertex offset |

### Particle Toggles

| Property Name | Description |
|---------------|-------------|
| `_Enable_Soft_Particles` | Enable depth-based softness |
| `_Enable_Camera_Fade` | Enable camera distance fade |
| `_Enable_Scene_Fog` | Enable fog integration |

### Skydome Toggles

| Property Name | Description |
|---------------|-------------|
| `_Enable_UV_Based` | Use UV-based gradient |

### Cloud Toggles

| Property Name | Description |
|---------------|-------------|
| `_Use_Environment_Override` | Override environment settings |
| `_Enable_Fog` | Enable fog blending |
| `_Enable_Scattering` | Enable light scattering |

---

## Alpha Fix Properties

Unity incorrectly stores many colors with alpha=0 even when visible. The converter fixes alpha to 1.0 when RGB has any non-zero value.

Contains **73 properties** in the `ALPHA_FIX_PROPERTIES` set.

### Crystal/Refractive

- `_Base_Color`
- `_Base_Color_Multiplier`
- `_Top_Color_Multiplier`
- `_Deep_Color`
- `_Shallow_Color`
- `_Fresnel_Color`
- `_Refraction_Color`

### Water

- `_Water_Deep_Color`
- `_Water_Shallow_Color`
- `_Water_Near_Color`
- `_Water_Far_Color`
- `_Foam_Color`
- `_Caustics_Color`
- `_Shore_Foam_Color_Tint`
- `_Shore_Wave_Color_Tint`
- `_WaterDeepColor`
- `_WaterShallowColor`
- `_WaterColour`
- `_FresnelColour`
- `_Very_Deep_Color`

### Foliage

- `_Leaf_Base_Color`
- `_Trunk_Base_Color`
- `_Emissive_Color`
- `_Emissive_2_Color`
- `_Trunk_Emissive_Color`
- `_Frosting_Color`

### Neon/Glow

- `_Neon_Colour_01`
- `_Neon_Colour_02`
- `_Glow_Colour`
- `_Glow_Tint`
- `_RimColor`
- `_Hologram_Color`

### Blood/Overlay

- `_BloodColor`
- `_Blood_Color`
- `_Dust_Colour`

### General

- `_Color`
- `_BaseColor`
- `_BaseColour`
- `_Color_Tint`
- `_ColorTint`
- `_Hair_Color`
- `_Skin_Color`
- `_Snow_Color`
- `_Emission_Color`
- `_EmissionColor`
- `_Liquid_Color`

### Skydome/Clouds

- `_Top_Color`
- `_Bottom_Color`
- `_Base_Color`
- `_Scattering_Color`

### Aurora

- `_Aurora_Color_01`
- `_Aurora_Color_02`

### Character Colors (Modular Fantasy Hero)

- `_Color_Primary`
- `_Color_Secondary`
- `_Color_Tertiary`
- `_Color_Metal_Primary`
- `_Color_Metal_Secondary`
- `_Color_Metal_Dark`
- `_Color_Leather_Primary`
- `_Color_Leather_Secondary`
- `_Color_Skin`
- `_Color_Hair`
- `_Color_Eyes`
- `_Color_Stubble`
- `_Color_Scar`
- `_Color_BodyArt`

---

## Property Defaults

Default values applied per shader type when Unity values are missing or problematic.

### Polygon Defaults

| Property | Default Value |
|----------|---------------|
| `smoothness` | 0.5 |
| `metallic` | 0.0 |

### Foliage Defaults

| Property | Default Value |
|----------|---------------|
| `leaf_smoothness` | 0.1 |
| `trunk_smoothness` | 0.15 |
| `leaf_metallic` | 0.0 |
| `trunk_metallic` | 0.0 |

### Crystal Defaults

| Property | Default Value |
|----------|---------------|
| `opacity` | 0.7 |

*Note: Unity often stores crystals as fully opaque (1.0), but they should be translucent*

### Water Defaults

| Property | Default Value |
|----------|---------------|
| `smoothness` | 0.95 |
| `metallic` | 0.0 |

### Placeholder Material Defaults

When creating placeholder materials for missing references:

**Crystal placeholders:**
- `opacity`: 0.7
- `base_color`: (0.5, 0.7, 1.0, 1.0) - Light blue
- `enable_fresnel`: true

**Water placeholders:**
- `deep_color`: (0.0, 0.2, 0.4, 1.0)
- `shallow_color`: (0.2, 0.5, 0.7, 1.0)

**Foliage placeholders:**
- `leaf_base_color`: (0.2, 0.5, 0.2, 1.0) - Green

---

## Adding New Mappings

### Adding a Texture Mapping

1. **Identify the Unity property name** from the material file (e.g., `_New_Texture`)
2. **Choose the Godot parameter name** following snake_case convention (e.g., `new_texture`)
3. **Determine which shader** uses this property
4. **Add to the appropriate `TEXTURE_MAP_*`** dictionary:
   ```python
   TEXTURE_MAP_POLYGON: dict[str, str] = {
       # ... existing entries ...
       "_New_Texture": "new_texture",
   }
   ```
5. **Update this documentation** with the new entry

### Adding a Float Mapping

1. **Identify the Unity property name** (e.g., `_New_Float`)
2. **Choose the Godot parameter name** (e.g., `new_float`)
3. **Check if it's a boolean-as-float** (values only 0.0 or 1.0)
   - If yes, add to `BOOLEAN_FLOAT_PROPERTIES` instead
4. **Add to the appropriate `FLOAT_MAP_*`**:
   ```python
   FLOAT_MAP_POLYGON: dict[str, str] = {
       # ... existing entries ...
       "_New_Float": "new_float",
   }
   ```
5. **Update this documentation**

### Adding a Color Mapping

1. **Identify the Unity property name** (e.g., `_New_Color`)
2. **Choose the Godot parameter name** (e.g., `new_color`)
3. **Check if it needs alpha fix** (Unity stores with alpha=0)
   - If yes, add to `ALPHA_FIX_PROPERTIES`
4. **Add to the appropriate `COLOR_MAP_*`**:
   ```python
   COLOR_MAP_POLYGON: dict[str, str] = {
       # ... existing entries ...
       "_New_Color": "new_color",
   }
   ```
5. **Update this documentation**

### Adding a Boolean-as-Float Property

1. **Identify properties stored as 0.0/1.0** but representing booleans
2. **Add to `BOOLEAN_FLOAT_PROPERTIES`**:
   ```python
   BOOLEAN_FLOAT_PROPERTIES: set[str] = {
       # ... existing entries ...
       "_New_Enable_Flag",
   }
   ```
3. **The converter will automatically**:
   - Detect the property
   - Convert to boolean
   - Derive the Godot name (e.g., `new_enable_flag`)
4. **Update this documentation**

### Adding Shader Defaults

1. **Identify when Unity values are problematic** for a shader type
2. **Add to `SHADER_DEFAULTS`**:
   ```python
   SHADER_DEFAULTS: dict[str, dict[str, float | bool]] = {
       "crystal.gdshader": {
           "opacity": 0.7,
           "new_default": 0.5,  # Add new default
       },
       # ...
   }
   ```
3. **Update this documentation**

---

## Summary Statistics

| Constant | Entry Count |
|----------|-------------|
| `SHADER_GUID_MAP` | 56 |
| `SHADER_NAME_PATTERNS_SCORED` | 20 |
| `TEXTURE_MAP_FOLIAGE` | 8 |
| `TEXTURE_MAP_POLYGON` | 37 |
| `TEXTURE_MAP_CRYSTAL` | 4 |
| `TEXTURE_MAP_WATER` | 2 |
| `TEXTURE_MAP_PARTICLES` | 1 |
| `FLOAT_MAP_FOLIAGE` | 15 |
| `FLOAT_MAP_POLYGON` | 77 |
| `FLOAT_MAP_CRYSTAL` | 4 |
| `FLOAT_MAP_WATER` | 11 |
| `FLOAT_MAP_PARTICLES` | 6 |
| `FLOAT_MAP_SKYDOME` | 3 |
| `FLOAT_MAP_CLOUDS` | 9 |
| `COLOR_MAP_FOLIAGE` | 9 |
| `COLOR_MAP_POLYGON` | 43 |
| `COLOR_MAP_CRYSTAL` | 7 |
| `COLOR_MAP_WATER` | 15 |
| `COLOR_MAP_PARTICLES` | 2 |
| `COLOR_MAP_SKYDOME` | 2 |
| `COLOR_MAP_CLOUDS` | 6 |
| `BOOLEAN_FLOAT_PROPERTIES` | 45 |
| `ALPHA_FIX_PROPERTIES` | 73 |
