"""
Shader Mapping Module for Synty Material Conversion.

This module provides mappings from Unity shader GUIDs to Godot shaders,
and handles conversion of Unity material properties to Godot format.

Overview
--------
The Synty asset packs use a variety of custom Unity shaders. This module
provides the intelligence to:

1. Identify which Godot shader should be used for each Unity material
2. Map Unity property names to Godot parameter names
3. Handle Unity quirks (alpha=0 colors, boolean-as-float properties)
4. Apply sensible defaults for missing or problematic values

Key Features
------------
- **GUID-based shader detection** (primary method): Direct lookup of Unity
  shader GUIDs to Godot shader filenames. Most reliable method.

- **Name pattern fallback detection**: When GUID is unknown, uses a scoring
  system to match material names against patterns.

- **Property mapping**: Converts textures, floats, and colors from Unity
  naming conventions to Godot parameter names.

- **Alpha=0 color fix**: Unity often stores colors with alpha=0 even when
  the material is opaque. This module detects and corrects this.

- **Boolean-as-float conversion**: Unity stores toggles as floats (0.0/1.0).
  This module separates them into proper boolean values.

- **Default value overrides**: Applies shader-specific sensible defaults
  when Unity values are missing or would produce poor results in Godot.

Architecture
------------
The module is organized into several major sections:

1. SHADER_GUID_MAP: Maps 56 Unity shader GUIDs to 7 Godot shaders
2. SHADER_NAME_PATTERNS_SCORED: Fallback pattern matching with scoring
3. TEXTURE_MAPS: Unity texture property -> Godot parameter mappings
4. FLOAT_MAPS: Unity float property -> Godot parameter mappings
5. COLOR_MAPS: Unity color property -> Godot parameter mappings
6. ALPHA_FIX_PROPERTIES: Properties needing alpha correction
7. BOOLEAN_FLOAT_PROPERTIES: Properties that are actually booleans
8. SHADER_DEFAULTS: Default values to apply per shader type

Usage
-----
The main entry point is `map_material()`:

    >>> from unity_parser import parse_material_bytes
    >>> from shader_mapping import map_material
    >>>
    >>> unity_mat = parse_material_bytes(mat_bytes)
    >>> godot_mat = map_material(unity_mat, texture_guid_map)
    >>> print(godot_mat.shader_file)
    'polygon.gdshader'

For shader detection only:

    >>> from shader_mapping import detect_shader_type
    >>> shader = detect_shader_type(
    ...     shader_guid="0730dae39bc73f34796280af9875ce14",
    ...     material_name="PolygonNature_Ground_01"
    ... )
    >>> shader
    'polygon.gdshader'

Godot Shader Types
------------------
This module maps to 7 Godot shader files:

- **polygon.gdshader**: General-purpose shader for props, terrain, characters.
  Supports triplanar, emission, snow, hologram effects, and more.

- **foliage.gdshader**: Trees, ferns, grass with wind animation support.
  Separate leaf/trunk textures and colors.

- **water.gdshader**: Rivers, lakes, oceans with depth-based coloring,
  shore foam, caustics, and wave animation.

- **crystal.gdshader**: Crystals, gems, glass with fresnel, refraction,
  and depth-based color gradients.

- **particles.gdshader**: Particle effects with soft blending and camera fade.

- **skydome.gdshader**: Procedural sky gradient (top/bottom colors).

- **clouds.gdshader**: Volumetric clouds with scattering and fog support.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

logger = logging.getLogger(__name__)

# =============================================================================
# SHADER GUID MAPPINGS
# =============================================================================
# Maps Unity shader GUIDs to Godot shader filenames.
# GUIDs are found in Unity .mat files under m_Shader.guid field.
#
# Based on analysis of 29 Synty Unity packages (~3,300 materials).
# GUIDs are stable 32-character hex identifiers assigned by Unity.
#
# Categories:
# - Core Synty Shaders: Main shaders used across most packs (polygon, foliage)
# - Effects Shaders: Visual effects (particles, water, crystal, clouds, skydome)
# - SciFi Shaders: Hologram, screen, decal effects (SciFi, Horror packs)
# - Urban/City Shaders: Building, neon, interior mapping (CyberCity, Zombies)
# - Fantasy Shaders: Magic, liquid, portal effects (DarkFantasy, ElvenRealm)
# - Pack-Specific Shaders: Racing, Viking, etc. with unique needs
# - Legacy/Fallback Shaders: Unity built-in and older Synty variants
#
# How to find new GUIDs:
# 1. Extract a .unitypackage containing the material
# 2. Open the .mat file (YAML format)
# 3. Find m_Shader: {fileID: ..., guid: <GUID HERE>, type: 3}
# 4. Add the GUID here with the appropriate Godot shader
# =============================================================================

SHADER_GUID_MAP: dict[str, str] = {
    # --------------------------------------------------------------------------
    # Core Synty Shaders (Most Common - Used Across Multiple Packs)
    # --------------------------------------------------------------------------
    # These are the primary shaders that handle 90%+ of Synty materials.
    "0730dae39bc73f34796280af9875ce14": "polygon.gdshader",    # Synty PolygonLit (main prop shader)
    "9b98a126c8d4d7a4baeb81b16e4f7b97": "foliage.gdshader",    # Synty Foliage (trees/plants)
    "0736e099ec10c9e46b9551b2337d0cc7": "particles.gdshader",  # Synty Particles
    "19e269a311c45cd4482cf0ac0e694503": "polygon.gdshader",    # Synty Triplanar (triplanar mode)
    "436db39b4e2ae5e46a17e21865226b19": "water.gdshader",      # Synty Water
    "5808064c5204e554c89f589a7059c558": "crystal.gdshader",    # Synty Crystal
    "de1d86872962c37429cb628a7de53613": "skydome.gdshader",    # Synty Skydome
    "4a6c8c23090929241b2a55476a46a9b1": "clouds.gdshader",     # Synty Clouds
    "dfec08fb273e4674bb5398df25a5932c": "foliage.gdshader",    # Synty Leaf Card
    "fdea4239d29733541b44cd6960afefcd": "crystal.gdshader",    # Synty Glass
    "3b44a38ec6f81134ab0f820ac54d6a93": "polygon.gdshader",    # Generic_Standard (character hair/skin)

    # --------------------------------------------------------------------------
    # Skydome Variants (Procedural Sky Shaders)
    # --------------------------------------------------------------------------
    "3d532bc2d70158948859b7839127e562": "skydome.gdshader",    # Skybox_Generic (procedural)
    "74fa94d128fe4f348889c6f5f182e0e1": "skydome.gdshader",    # Skydome variant (NatureBiomes)

    # --------------------------------------------------------------------------
    # SciFi Shaders (SciFi, SciFiHorror, SciFiWorlds Packs)
    # --------------------------------------------------------------------------
    # These shaders add futuristic effects like holograms, CRT screens, etc.
    "0835602ed30128f4a88a652bf920fcaa": "polygon.gdshader",    # Polygon_UVScroll (animated UV)
    "2b5804ffd3081d344bed894a653e3014": "polygon.gdshader",    # Hologram
    "5c2ccdfe181d55b42bd5313305f194e4": "polygon.gdshader",    # SciFiHorror_Screens (CRT)
    "77e5bdd170fa4a4459dea431aba43e3c": "polygon.gdshader",    # SciFiHorror_Decals
    "972cd3fede1c33342b0f52ad57f47d90": "polygon.gdshader",    # SciFiHorror_BlinkingLights
    "c48a4461fec61fc45a01e7d6a50e520f": "foliage.gdshader",    # SciFiPlant

    # --------------------------------------------------------------------------
    # Horror Shaders (Horror, Zombies Packs)
    # --------------------------------------------------------------------------
    # Shaders for atmospheric horror effects.
    "325b924500ba5804aa4b407d80084502": "polygon.gdshader",    # Neon Shader
    "0ecc70cac2c8895439f5094ba6660db8": "polygon.gdshader",    # GrungeTriplanar
    "5d828b280155912429aa717d34cd8879": "polygon.gdshader",    # Ghost (transparency + rim)

    # --------------------------------------------------------------------------
    # Urban/City Shaders (CyberCity, Zombies, Town Packs)
    # --------------------------------------------------------------------------
    # Shaders for buildings, interiors, and city environments.
    "62e87ad08a1afa642830420bf8e0dd4d": "polygon.gdshader",    # CyberCity_Triplanar
    "2a33a166317493947a7be330dcc78a05": "polygon.gdshader",    # Parallax_Full (interior window)
    "e9556606a5f42464fa7dd78d624dc180": "polygon.gdshader",    # Hologram_01 (urban)
    "a49be8e7504a48b4fba9b0c2a7fad57b": "polygon.gdshader",    # EmissiveScroll (LED panels)
    "1f67b66c29dfd4f45aa8cc07bf5e901a": "polygon.gdshader",    # EmissiveColourChange
    "a711ca3b984db6a4e81ec2d50ca4c0ca": "polygon.gdshader",    # Building (background)
    "5d014726978e80a43b6178cba929343b": "polygon.gdshader",    # FlipbookCutout
    "a7331fc07349b124c8c15d545676f9ed": "polygon.gdshader",    # Zombies (blood overlay)

    # --------------------------------------------------------------------------
    # Dark Fantasy/Magic Shaders (DarkFantasy, Fantasy, Dungeon Packs)
    # --------------------------------------------------------------------------
    # Magical effects like glowing runes, portals, and potions.
    "d0be6b296f23e8d459e94b4007017ea0": "polygon.gdshader",    # Magic Glow/Runes
    "e8b857c3d7fea464e942e1c1f0940e96": "polygon.gdshader",    # Magical Portal
    "e312e3877c798a44dba23093a3417a94": "polygon.gdshader",    # Liquid/Potion
    "a2cae5b0e99e16249b9a2163a7087bcb": "foliage.gdshader",    # Wind Animation (cloth/sail)

    # --------------------------------------------------------------------------
    # Viking Shaders (Vikings Pack)
    # --------------------------------------------------------------------------
    "d2820334f2975bb47ab3f2fffa1b4cbe": "skydome.gdshader",    # Aurora (northern lights)
    "b83105300c9f7fb42a6e1b790fd2bd29": "particles.gdshader",  # ParticlesLit
    "00eec7c5cd1f4c6429ffee9a690c3d16": "particles.gdshader",  # ParticlesUnlit

    # --------------------------------------------------------------------------
    # Apocalypse/Destruction Shaders (Apocalypse Pack)
    # --------------------------------------------------------------------------
    "f3534f26c7b573c45a1346e0634d57fc": "polygon.gdshader",    # Generic_Basic_Bloody
    "e17f8fe2503580447a3784d34b316d11": "polygon.gdshader",    # Triplanar_Basic

    # --------------------------------------------------------------------------
    # Legacy/Fallback Shaders (Unity Built-in & Older Synty)
    # --------------------------------------------------------------------------
    # These handle materials from older packs or Unity's default shaders.
    "933532a4fcc9baf4fa0491de14d08ed7": "polygon.gdshader",    # Unity URP Lit (fallback)
    "56ef766d507df464fb2a1726a99c925f": "particles.gdshader",  # Heat Shimmer (AridDesert)
    "1ab581f9e0198304996581171522f458": "water.gdshader",      # Water (Amplify) - Nature 2021
    "4b0390819f518774fa1a44198298459a": "foliage.gdshader",    # Foliage (Amplify) - Nature 2021
    "0000000000000000f000000000000000": "polygon.gdshader",    # Unity Built-in (default fallback)

    # --------------------------------------------------------------------------
    # Elven Realm Shaders (ElvenRealm Pack)
    # --------------------------------------------------------------------------
    "e854bc7dc0cde7044b9000faaf0c4e11": "polygon.gdshader",    # RockTriplanar
    "9b1e1d14d7778714391ae095571c3d4f": "water.gdshader",      # WaterFall (animated)
    "df6b3a02955954d41bb15c534388ba14": "polygon.gdshader",    # NoFog (celestial)
    "903fe97c2d85c8147a64932806c92eb1": "water.gdshader",      # Waterfall variant
    "ca9b700964f37d84a90b00c70d981934": "skydome.gdshader",    # Aurora (Elven Realm)

    # --------------------------------------------------------------------------
    # Pro Racer Shaders (ProRacer Pack - Racing Vehicles)
    # --------------------------------------------------------------------------
    "ab6da834753539b4989259dbf4bcc39b": "polygon.gdshader",    # ProRacer_Standard (128 uses)
    "22e3738818284144eb7ada0a62acca66": "polygon.gdshader",    # ProRacer_Decal
    "402ae1c33e4c28c45876b1bc945b77e6": "particles.gdshader",  # ProRacer_ParticlesUnlit
    "da24369d453e6a547aaa57ebee28fc81": "polygon.gdshader",    # ProRacer_CutoutFlipbook
    "8e5d248915e86014095ff0547bc0c755": "polygon.gdshader",    # ProRacerAdvanced
    "1bf4a2dc982313347912f313ba25f563": "polygon.gdshader",    # RoadSHD

    # --------------------------------------------------------------------------
    # Modular Fantasy Hero Shaders (Character Customization)
    # --------------------------------------------------------------------------
    "e603b0446c7f2804db0c8dd0fb5c1af0": "polygon.gdshader",    # POLYGON_CustomCharacters (15-zone mask)
}

# =============================================================================
# SHADER NAME PATTERN SCORING
# =============================================================================
# Fallback detection system used when GUID lookup fails (unknown shader GUID).
#
# How It Works:
# -------------
# 1. Each pattern is a regex that matches against the material name
# 2. All matching patterns contribute their scores to their respective shaders
# 3. Scores accumulate - a material can match multiple patterns
# 4. The shader with the highest total score wins (if score >= 20)
#
# Scoring Philosophy:
# -------------------
# - Higher scores (50-60): Very specific technical terms that unambiguously
#   identify a shader type. Example: "triplanar" (60) is a rendering technique
#   that only applies to polygon shader.
#
# - Medium-high scores (40-49): Clear material type indicators.
#   Example: "crystal" (45), "water" (45), "particle" (45).
#
# - Medium scores (30-39): Common material types that are fairly specific.
#   Example: "glass" (35), "fog" (35), "foliage" (35).
#
# - Low-medium scores (20-29): Generic terms common in compound names.
#   Example: "tree" (25), "grass" (25), "leaf" (20).
#
# - Low scores (10-19): Very generic terms that may appear in many contexts.
#   Example: "moss" (15), "dirt" (15), "effect" (15).
#
# Example: Compound Name Resolution
# ---------------------------------
# Material name: "Dirt_Leaves_Triplanar"
#
# Matching patterns and scores:
# - "dirt"      -> polygon.gdshader   +15
# - "leaves"    -> foliage.gdshader   +20
# - "triplanar" -> polygon.gdshader   +60
#
# Final scores:
# - polygon.gdshader:  15 + 60 = 75
# - foliage.gdshader:  20
#
# Winner: polygon.gdshader (75 > 20)
#
# This correctly identifies that "Dirt_Leaves_Triplanar" should use the
# polygon shader with triplanar blending, even though "Leaves" is in the name.
# =============================================================================

SHADER_NAME_PATTERNS_SCORED: list[tuple[re.Pattern[str], str, int]] = [
    # --------------------------------------------------------------------------
    # HIGH PRIORITY - Technical/Specific Terms (50-60 points)
    # --------------------------------------------------------------------------
    # These describe rendering techniques or very specific material types that
    # unambiguously identify the shader. Rarely appear as false positives.
    (re.compile(r"(?i)triplanar"), "polygon.gdshader", 60),  # Rendering technique
    (re.compile(r"(?i)caustics"), "water.gdshader", 55),  # Water-specific light effect
    (re.compile(r"(?i)(fresnel|refractive|refraction)"), "crystal.gdshader", 55),  # Crystal optics
    (re.compile(r"(?i)soft.?particle"), "particles.gdshader", 55),  # Particle blending mode
    (re.compile(r"(?i)(skydome|sky_dome|skybox|sky_box)"), "skydome.gdshader", 55),  # Sky rendering

    # --------------------------------------------------------------------------
    # MEDIUM-HIGH PRIORITY - Clear Material Types (40-49 points)
    # --------------------------------------------------------------------------
    # These are clear indicators of material type that rarely appear in
    # unrelated contexts.
    (re.compile(r"(?i)(crystal|gem|jewel|diamond|ruby|emerald|sapphire|amethyst|quartz)"), "crystal.gdshader", 45),
    (re.compile(r"(?i)(water|ocean|river|lake|waterfall)"), "water.gdshader", 45),
    (re.compile(r"(?i)(particle|fx_)"), "particles.gdshader", 45),
    (re.compile(r"(?i)(cloud|clouds|sky_cloud)"), "clouds.gdshader", 45),

    # --------------------------------------------------------------------------
    # MEDIUM PRIORITY - Common Material Types (30-39 points)
    # --------------------------------------------------------------------------
    # These are fairly specific but could occasionally appear in compound names
    # where they're not the primary material type.
    (re.compile(r"(?i)(glass|ice|transparent|translucent)"), "crystal.gdshader", 35),
    (re.compile(r"(?i)(pond|stream|liquid|aqua|sea)"), "water.gdshader", 35),
    (re.compile(r"(?i)(fog|mist|atmosphere)"), "clouds.gdshader", 35),
    (re.compile(r"(?i)(spark|dust|debris|smoke|fire|rain|snow|splash)"), "particles.gdshader", 35),
    (re.compile(r"(?i)(aurora|sky_gradient)"), "skydome.gdshader", 35),
    (re.compile(r"(?i)(foliage|vegetation)"), "foliage.gdshader", 35),

    # --------------------------------------------------------------------------
    # LOW-MEDIUM PRIORITY - Generic Vegetation Terms (20-29 points)
    # --------------------------------------------------------------------------
    # These are common in compound names and shouldn't override more specific
    # technical terms. "Dirt_Leaves_Triplanar" should use polygon, not foliage.
    (re.compile(r"(?i)(tree|fern|grass|vine|branch|willow|bush|shrub|hedge|bamboo|koru|treefern)"), "foliage.gdshader", 25),
    (re.compile(r"(?i)(leaf|leaves)"), "foliage.gdshader", 20),  # Very common, low priority
    (re.compile(r"(?i)(bark|trunk|undergrowth|plant)"), "foliage.gdshader", 20),

    # --------------------------------------------------------------------------
    # LOW PRIORITY - Ambiguous Terms (10-19 points)
    # --------------------------------------------------------------------------
    # These terms appear in many contexts and provide weak signals.
    # They can tip the balance when other evidence is inconclusive.
    (re.compile(r"(?i)(moss|dirt)"), "polygon.gdshader", 15),  # Often combined with triplanar
    (re.compile(r"(?i)(effect|additive)"), "particles.gdshader", 15),  # Generic FX terms
]

# Legacy pattern list for backwards compatibility (first-match-wins fallback)
# Used only if the new scoring system is bypassed.
SHADER_NAME_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (pattern, shader) for pattern, shader, _ in SHADER_NAME_PATTERNS_SCORED
]

# Default shader when no match found - polygon is the most versatile
DEFAULT_SHADER = "polygon.gdshader"

# =============================================================================
# TEXTURE PROPERTY MAPPINGS
# =============================================================================
# Maps Unity texture property names to Godot shader parameter names.
#
# Unity materials store texture references in the m_TexEnvs section with
# property names like "_Base_Texture", "_MainTex", etc. These need to be
# mapped to the corresponding Godot shader uniform names.
#
# Each shader type has its own texture map because:
# 1. Different shaders expect different textures (leaf vs base, etc.)
# 2. Property names vary between shader types in Unity
# 3. Some properties have multiple Unity names (legacy support)
# =============================================================================

# Foliage Shader (Trees, Ferns, Grass)
# Foliage materials typically have separate leaf and trunk textures to allow
# different properties for each part of the plant.
TEXTURE_MAP_FOLIAGE: dict[str, str] = {
    "_Leaf_Texture": "leaf_color",
    "_Leaf_Normal": "leaf_normal",
    "_Trunk_Texture": "trunk_color",
    "_Trunk_Normal": "trunk_normal",
    "_Leaf_Ambient_Occlusion": "leaf_ao",
    "_Trunk_Ambient_Occlusion": "trunk_ao",
    # Emissive masks (auto-enables emissive features when present)
    "_Emissive_Mask": "emissive_mask",
    "_Emissive_2_Mask": "emissive_2_mask",
    "_Emissive_Pulse_Map": "emissive_pulse_mask",
    "_Trunk_Emissive_Mask": "trunk_emissive_mask",
    # Wind noise map (procedural wind variation)
    "_Breeze_Noise_Map": "breeze_noise_map",
}

# Polygon Shader (Props, Terrain, Characters, Triplanar)
# This is the most comprehensive map as polygon handles many material types.
TEXTURE_MAP_POLYGON: dict[str, str] = {
    # Standard PBR textures
    "_Base_Texture": "base_texture",
    "_Normal_Texture": "normal_texture",
    "_Emission_Texture": "emission_texture",
    "_AO_Texture": "ao_texture",
    # Triplanar textures (for terrain blending)
    "_Triplanar_Texture_Top": "triplanar_texture_top",
    "_Triplanar_Texture_Side": "triplanar_texture_side",
    "_Triplanar_Texture_Bottom": "triplanar_texture_bottom",
    # Alternative Unity property names (different packs use different names)
    "_Albedo_Map": "base_texture",
    "_BaseMap": "base_texture",
    "_MainTex": "base_texture",
    "_Normal_Map": "normal_texture",
    "_BumpMap": "normal_texture",
    "_Emission_Map": "emission_texture",
    "_EmissionMap": "emission_texture",
    "_OcclusionMap": "ao_texture",
    "_Metallic_Smoothness_Texture": "metallic_texture",
    "_MetallicGlossMap": "metallic_texture",
    # Legacy names (older Unity conventions)
    "_MainTexture": "base_texture",
    "_Emission": "emission_texture",
    # Character-specific textures (for hair/skin masks)
    "_Hair_Mask": "hair_mask",
    "_Skin_Mask": "skin_mask",
    # Mask textures for Modular Fantasy Hero (15-zone color system)
    "_Mask_01": "mask_01",
    "_Mask_02": "mask_02",
    "_Mask_03": "mask_03",
    "_Mask_04": "mask_04",
    "_Mask_05": "mask_05",
    # Pro Racer pack
    "_Metallic_Map": "metallic_texture",
    # Grunge/Weathering overlay
    "_Grunge_Map": "grunge_map",
    # Blood overlay (Horror/Zombies packs)
    "_Blood_Mask": "blood_mask",
    "_Blood_Texture": "blood_texture",
    # Magic runes (DarkFantasy pack)
    "_Rune_Texture": "rune_texture",
    # Interior Mapping (parallax fake interiors for windows)
    "_Floor": "floor_texture",
    "_Wall": "wall_texture",
    "_Ceiling": "ceiling_texture",
    "_Back": "back_texture",
    "_Props": "props_texture",
    # Screen/Monitor effects (SciFi packs)
    "_Scan_Line_Map": "scan_line_map",
    # Flipbook animation
    "_LED_Mask_01": "led_mask",
    # Cloth/Sail wind animation
    "_Cloth_Mask": "cloth_mask",
    # Overlay texture (auto-enables overlay feature when present)
    "_Overlay_Texture": "overlay_texture",
    # Triplanar normal and emission textures (auto-enable triplanar features)
    "_Triplanar_Emission_Texture": "triplanar_emission_texture",
    "_Triplanar_Normal_Texture_Bottom": "triplanar_normal_bottom",
    "_Triplanar_Normal_Texture_Side": "triplanar_normal_side",
    "_Triplanar_Normal_Texture_Top": "triplanar_normal_top",
    # Legacy/alternative names for moss overlay
    "_Moss": "overlay_texture",
    "_MossTexture": "overlay_texture",
    # Parallax/Height map (standard Unity PBR)
    "_ParallaxMap": "height_texture",
    "_HeightMap": "height_texture",
    # Alpha/Cutout texture (transparency mask)
    "_Alpha_Texture": "alpha_texture",
    # Spherical/Matcap environment mapping
    "_Spherical_Map": "spherical_map",
    # Snow overlay textures (auto-enable snow feature when present)
    "_Snow_Normal_Texture": "snow_normal_texture",
    "_Snow_Metallic_Smoothness_Texture": "snow_metallic_smoothness",
    "_Snow_Edge_Noise": "snow_edge_noise",
    # LED/Screen effects (SciFi packs)
    "_LED_Panel_Emissive_Wave_01": "led_emissive_wave",
    "_Pixelation_Map": "pixelation_map",
    # Detail textures
    "_DetailAlbedoMap": "detail_albedo",
    "_DetailNormalMap": "detail_normal",
    "_DetailMask": "detail_mask",
}

# Crystal Shader (Crystals, Glass, Gems)
# Crystal materials use specialized textures for refraction effects.
TEXTURE_MAP_CRYSTAL: dict[str, str] = {
    "_Base_Albedo": "base_albedo",
    "_Base_Normal": "base_normal",
    "_Refraction_Height": "refraction_height",
    "_Refraction_Texture": "refraction_texture",
    # Top textures (auto-enable top layer feature when present)
    "_Top_Albedo": "top_albedo",
    "_Top_Normal": "top_normal",
    # Alternative property names from different packs
    "_MainTex": "base_albedo",
    "_BumpMap": "base_normal",
    "_BaseMap": "base_albedo",
}

# Water Shader (Rivers, Lakes, Oceans)
# Water uses normal maps for surface ripples and caustics for underwater light.
TEXTURE_MAP_WATER: dict[str, str] = {
    "_Caustics_Flipbook": "caustics_flipbook",
    # Foam textures (auto-enable foam features when present)
    "_Foam_Noise_Texture": "noise_texture",
    "_Foam_Texture": "noise_texture",  # Older naming convention
    "_Foam_Texture1": "noise_texture",  # Goblin War Camp variant
    "_FoamMask": "noise_texture",  # Foam masking (Goblin War Camp)
    "_Noise_Texture": "noise_texture",  # Global foam noise texture
    "_Normal_Map": "normal_texture",  # Alternative normal map name
    "_Normal_Texture": "normal_texture",
    "_Scrolling_Texture": "scrolling_texture",
    "_Shore_Foam_Noise_Texture": "shore_foam_noise_texture",
    "_Water_Normal_Texture": "normal_texture",  # Water normal texture
    "_WaterNormal": "normal_texture",  # Older naming for water normal
    "_WaterNormal1": "normal_texture",  # Secondary normal (Goblin War Camp)
    "_WaterNormal2": "normal_texture",  # Tertiary normal (Goblin War Camp)
    # Ripple normal maps (Goblin War Camp, Dwarven Dungeon)
    "_RipplesNormal": "normal_texture",
    "_RipplesNormal2": "normal_texture",
    # Wave mask textures (Goblin War Camp)
    "_WaveMask": "noise_texture",
    "_WaveMaskTuff": "noise_texture",
    "_WaveNoise": "noise_texture",
    # Shore wave foam (separate from shore foam)
    "_Shore_Wave_Foam_Noise_Texture": "shore_foam_noise_texture",
    # Water noise/distortion textures
    "_Water_Noise_Texture": "noise_texture",
    # Standard Unity texture fallbacks
    "_MainTex": "normal_texture",
    "_BumpMap": "normal_texture",
    "_BaseMap": "normal_texture",
}

# Particles Shader (Effects, Fog)
TEXTURE_MAP_PARTICLES: dict[str, str] = {
    "_Albedo_Map": "albedo_map",
    "_MainTex": "albedo_map",  # Standard Unity particle texture
    "_BaseMap": "albedo_map",
}

# Skydome Shader (Sky Gradient)
# Skydome is a procedural gradient shader with no texture uniforms.
TEXTURE_MAP_SKYDOME: dict[str, str] = {}

# Clouds Shader (Volumetric Clouds)
# Clouds typically use procedural noise generation, no textures needed.
TEXTURE_MAP_CLOUDS: dict[str, str] = {
    # Clouds use procedural noise, no external textures
}

# Combined texture map lookup by shader type
TEXTURE_MAPS: dict[str, dict[str, str]] = {
    "foliage.gdshader": TEXTURE_MAP_FOLIAGE,
    "polygon.gdshader": TEXTURE_MAP_POLYGON,
    "crystal.gdshader": TEXTURE_MAP_CRYSTAL,
    "water.gdshader": TEXTURE_MAP_WATER,
    "particles.gdshader": TEXTURE_MAP_PARTICLES,
    "skydome.gdshader": TEXTURE_MAP_SKYDOME,
    "clouds.gdshader": TEXTURE_MAP_CLOUDS,
}

# =============================================================================
# SHADER-SPECIFIC PROPERTIES (for fallback validation)
# =============================================================================
# Defines which properties are unique to each specialized shader.
# Used to validate that a material actually needs a specialized shader,
# rather than just matching by name pattern alone.
#
# If a material matches a specialized shader by name pattern but has none
# of that shader's specific properties, it falls back to polygon.gdshader.
# =============================================================================

SHADER_SPECIFIC_PROPERTIES: dict[str, dict[str, set[str]]] = {
    "foliage.gdshader": {
        "textures": {"_Leaf_Texture", "_Trunk_Texture", "_Leaf_Normal", "_Trunk_Normal", "_Breeze_Noise_Map", "_Leaf_Ambient_Occlusion", "_Trunk_Ambient_Occlusion"},
        "floats": {"_Breeze_Strength", "_Light_Wind_Strength", "_Strong_Wind_Strength", "_Leaf_Smoothness", "_LeafSmoothness", "_Trunk_Smoothness", "_TrunkSmoothness", "_Leaf_Metallic", "_Trunk_Metallic"},
        "colors": {"_Leaf_Base_Color", "_Trunk_Base_Color"},
    },
    "crystal.gdshader": {
        "textures": {"_Refraction_Height", "_Refraction_Texture", "_Top_Albedo", "_Base_Albedo", "_Top_Normal", "_Base_Normal"},
        "floats": {"_Fresnel_Power", "_Refraction_Strength", "_Deep_Depth", "_Shallow_Depth", "_Enable_Fresnel", "_Enable_Refraction"},
        "colors": {"_Deep_Color", "_Shallow_Color", "_Fresnel_Color", "_Refraction_Color"},
    },
    "water.gdshader": {
        "textures": {"_Caustics_Flipbook", "_Foam_Noise_Texture", "_Shore_Foam_Noise_Texture", "_Scrolling_Texture", "_Water_Normal_Texture", "_Foam_Texture"},
        "floats": {"_Maximum_Depth", "_Shore_Wave_Speed", "_Ocean_Wave_Height", "_Shore_Foam_Intensity", "_Caustics_Intensity", "_Base_Opacity", "_Shallows_Opacity"},
        "colors": {"_Shallow_Color", "_Deep_Color", "_Very_Deep_Color", "_Foam_Color", "_Caustics_Color"},
    },
    "particles.gdshader": {
        "textures": set(),
        "floats": {"_Soft_Power", "_Soft_Distance", "_Camera_Fade_Near", "_Camera_Fade_Far", "_View_Edge_Power", "_Fog_Density"},
        "colors": {"_Fog_Color"},
    },
    "skydome.gdshader": {
        "textures": set(),
        "floats": {"_Falloff", "_Offset", "_Distance"},
        "colors": {"_Top_Color", "_Bottom_Color"},
    },
    "clouds.gdshader": {
        "textures": set(),
        "floats": {"_Light_Intensity", "_Scattering_Multiplier", "_Cloud_Speed", "_Cloud_Strength", "_CloudCoverage"},
        "colors": {"_Scattering_Color", "_Aurora_Color_01", "_Aurora_Color_02"},
    },
}

# =============================================================================
# FLOAT PROPERTY MAPPINGS
# =============================================================================
# Maps Unity float property names to Godot shader parameter names.
#
# Unity stores shader parameters in m_Floats as name-value pairs.
# The naming conventions vary between Synty packs and Unity versions.
# =============================================================================

FLOAT_MAP_FOLIAGE: dict[str, str] = {
    # Standard PBR
    "_Metallic": "metallic",
    "_Smoothness": "smoothness",
    "_Glossiness": "smoothness",  # Alternative name
    "_LeafSmoothness": "leaf_smoothness",
    "_Leaf_Smoothness": "leaf_smoothness",
    "_Leaf_Metallic": "leaf_metallic",
    "_TrunkSmoothness": "trunk_smoothness",
    "_Trunk_Smoothness": "trunk_smoothness",
    "_Trunk_Metallic": "trunk_metallic",
    # Wind animation parameters
    "_Breeze_Strength": "breeze_strength",
    "_Light_Wind_Strength": "light_wind_strength",
    "_Strong_Wind_Strength": "strong_wind_strength",
    "_Wind_Twist_Strength": "wind_twist_strength",
    "_Gale_Blend": "gale_blend",
    "_Light_Wind_Y_Strength": "light_wind_y_strength",
    "_Light_Wind_Y_Offset": "light_wind_y_offset",
    # Alpha cutoff (for leaf transparency)
    "_Alpha_Clip_Threshold": "alpha_clip_threshold",
    # Normal intensity
    "_Normal_Intensity": "normal_intensity",
    "_BumpScale": "normal_intensity",
    # Frosting (snow on foliage)
    "_Frosting_Falloff": "frosting_falloff",
    "_Frosting_Height": "frosting_height",
    # Legacy names (2021 and earlier)
    "_Leaves_WindAmount": "breeze_strength",
    "_Tree_WindAmount": "light_wind_strength",
    "_Cutoff": "alpha_clip_threshold",
    "_AlphaCutoff": "alpha_clip_threshold",
}

FLOAT_MAP_POLYGON: dict[str, str] = {
    # Standard PBR properties
    "_Smoothness": "smoothness",
    "_Glossiness": "smoothness",
    "_Metallic": "metallic",
    "_Snow_Level": "snow_level",
    "_Normal_Intensity": "normal_intensity",
    "_Normal_Amount": "normal_intensity",
    "_BumpScale": "normal_intensity",
    "_AO_Intensity": "ao_intensity",
    "_OcclusionStrength": "ao_intensity",
    "_Alpha_Clip_Threshold": "alpha_clip_threshold",
    "_Cutoff": "alpha_clip_threshold",
    "_AlphaCutoff": "alpha_clip_threshold",
    # Hologram effect (SciFi packs)
    "_HoloLines": "holo_lines",
    "_Scroll_Speed": "scroll_speed",
    "_Opacity": "opacity",
    "_Hologram_Intensity": "hologram_intensity",
    # Screen/CRT effect (SciFiHorror)
    "_Screen_Bulge": "screen_bulge",
    "_Screen_Flicker_Frequency": "screen_flicker_frequency",
    "_Vignette_Amount": "vignette_amount",
    "_Pixelation_Amount": "pixelation_amount",
    "_CRT_Curve": "crt_curve",
    # Interior Mapping (fake room interiors for windows)
    "_RoomTile": "room_tile",
    "_RoomIntensity": "room_intensity",
    "_WindowAlpha": "window_alpha",
    "_RoomDepth": "room_depth",
    # Ghost effect (Horror pack)
    "_Transparency": "transparency",
    "_RimPower": "rim_power",
    "_TransShadow": "trans_shadow",
    "_Ghost_Strength": "ghost_strength",
    # Grunge/Weathering (Horror, Apocalypse)
    "_Dirt_Amount": "dirt_amount",
    "_Dust_Amount": "dust_amount",
    "_Grunge_Intensity": "grunge_intensity",
    # Magic effects (DarkFantasy)
    "_Glow_Amount": "glow_amount",
    "_Glow_Falloff": "glow_falloff",
    "_dissolve": "dissolve",
    "_twirlstr": "twirl_strength",
    "_Rune_Speed": "rune_speed",
    # Liquid/Potion (DarkFantasy)
    "_liquidamount": "liquid_amount",
    "_WobbleX": "wobble_x",
    "_WobbleZ": "wobble_z",
    "_Wave_Scale": "wave_scale",
    "_Foam_Line": "foam_line",
    "_Rim_Width": "rim_width",
    # Blood overlay (Zombies)
    "_BloodAmount": "blood_amount",
    "_Blood_Intensity": "blood_intensity",
    # LED/Neon effects (CyberCity)
    "_Brightness": "brightness",
    "_UVScrollSpeed": "uv_scroll_speed",
    "_Saturation": "saturation",
    "_Neon_Intensity": "neon_intensity",
    "_Pulse_Speed": "pulse_speed",
    # Cloth/Sail animation
    "_Wave_Speed": "wave_speed",
    "_Wave_Amplitude": "wave_amplitude",
    "_Wind_Influence": "wind_influence",
    # Character (Modular Fantasy Hero)
    "_BodyArt_Amount": "bodyart_amount",
    "_Tattoo_Amount": "tattoo_amount",
    # Racing (ProRacer)
    "_Flipbook_Width": "flipbook_width",
    "_Flipbook_Height": "flipbook_height",
    "_Flipbook_Speed": "flipbook_speed",
    # Heat Shimmer (AridDesert)
    "_Distortion_strength": "distortion_strength",
    "_Edge_Distortion_Intensity": "edge_distortion_intensity",
    "_Speed_X": "speed_x",
    "_Speed_Y": "speed_y",
    # Snow overlay properties
    "_Snow_Level": "snow_level",
    "_Snow_Transition": "snow_transition",
    "_Snow_Metallic": "snow_metallic",
    "_Snow_Smoothness": "snow_smoothness",
    "_Snow_Normal_Intensity": "snow_normal_intensity",
    # Triplanar properties
    "_Triplanar_Fade": "triplanar_fade",
    "_Triplanar_Intensity": "triplanar_intensity",
    "_Triplanar_Normal_Intensity_Top": "triplanar_normal_intensity_top",
    "_Triplanar_Normal_Intensity_Side": "triplanar_normal_intensity_side",
    "_Triplanar_Normal_Intensity_Bottom": "triplanar_normal_intensity_bottom",
    # Emission intensity
    "_Emission_Intensity": "emission_intensity",
    # Detail texture properties
    "_DetailNormalMapScale": "detail_normal_scale",
}

FLOAT_MAP_CRYSTAL: dict[str, str] = {
    "_Metallic": "metallic",
    "_Smoothness": "smoothness",
    "_Glossiness": "smoothness",  # Alternative name
    "_Opacity": "opacity",
    "_Fresnel_Power": "fresnel_power",
    "_Refraction_Strength": "refraction_strength",
    "_Deep_Depth": "deep_depth",
    "_Shallow_Depth": "shallow_depth",
    "_Normal_Intensity": "normal_intensity",
    "_BumpScale": "normal_intensity",
}

FLOAT_MAP_WATER: dict[str, str] = {
    "_Smoothness": "smoothness",
    "_Glossiness": "smoothness",  # Alternative name
    "_Metallic": "metallic",
    "_Base_Opacity": "base_opacity",
    "_Shallows_Opacity": "shallows_opacity",
    "_Maximum_Depth": "maximum_depth",
    "_Normal_Intensity": "normal_intensity",
    "_BumpScale": "normal_intensity",  # Alternative name
    "_Shore_Wave_Speed": "shore_wave_speed",
    "_Ocean_Wave_Height": "ocean_wave_height",
    "_Ocean_Wave_Speed": "ocean_wave_speed",
    "_Distortion_Strength": "distortion_strength",
    # Depth properties
    "_Deep_Height": "deep_height",
    "_Very_Deep_Height": "very_deep_height",
    "_Depth_Distance": "depth_distance",
    "_Water_Depth": "water_depth",
    # Depth falloff controls (Goblin War Camp, Dwarven Dungeon)
    "_ShallowFalloff": "shallow_intensity",
    "_OverallFalloff": "base_opacity",
    "_OpacityFalloff": "shallows_opacity",
    # Foam properties
    "_Shore_Foam_Intensity": "shore_foam_intensity",
    "_FoamShoreline": "shore_foam_intensity",  # Goblin War Camp variant
    "_FoamDepth": "shore_foam_intensity",  # Foam depth threshold
    "_FoamFalloff": "ocean_foam_opacity",  # Foam fade control
    # Caustics properties
    "_Caustics_Intensity": "caustics_intensity",
    "_CausticDepthFade": "caustics_intensity",  # Depth-based caustic fade
    "_CausticScale": "caustics_scale",  # Caustic pattern scale
    "_CausticSpeed": "caustics_speed",  # Caustic animation speed
    "_Shallow_Intensity": "shallow_intensity",
    # Waterfall (ElvenRealm)
    "_FresnelPower": "fresnel_power",
    "_UVScrollSpeed": "uv_scroll_speed",
}

FLOAT_MAP_PARTICLES: dict[str, str] = {
    "_Alpha_Clip_Treshold": "alpha_clip_threshold",  # Unity typo preserved for input compatibility
    "_Alpha_Clip_Threshold": "alpha_clip_threshold",
    "_Cutoff": "alpha_clip_threshold",
    "_AlphaCutoff": "alpha_clip_threshold",
    "_Soft_Power": "soft_power",
    "_Soft_Distance": "soft_distance",
    "_Camera_Fade_Near": "camera_fade_near",
    "_Camera_Fade_Far": "camera_fade_far",
    "_Camera_Fade_Smoothness": "camera_fade_smoothness",
    "_View_Edge_Power": "view_edge_power",
    "_Fog_Density": "fog_density",
}

FLOAT_MAP_SKYDOME: dict[str, str] = {
    "_Falloff": "falloff",
    "_Offset": "offset",
    "_Distance": "distance_",  # Trailing underscore to avoid Godot reserved word
}

FLOAT_MAP_CLOUDS: dict[str, str] = {
    "_Light_Intensity": "light_intensity",
    "_Fresnel_Power": "fresnel_power",
    "_Fog_Density": "fog_density",
    "_Scattering_Multiplier": "scattering_multiplier",
    "_Cloud_Speed": "cloud_speed",
    "_Cloud_Strength": "cloud_strength",
    # SciFi Space cloud variants
    "_CloudCoverage": "cloud_strength",
    "_CloudPower": "cloud_strength",
    "_CloudSpeed": "cloud_speed",
    "_Cloud_Contrast": "scattering_multiplier",
    "_Cloud_Falloff": "fog_density",
    # Aurora effect (Vikings, ElvenRealm)
    "_Aurora_Speed": "aurora_speed",
    "_Aurora_Intensity": "aurora_intensity",
    "_Aurora_Scale": "aurora_scale",
}

# Combined float map lookup by shader type
FLOAT_MAPS: dict[str, dict[str, str]] = {
    "foliage.gdshader": FLOAT_MAP_FOLIAGE,
    "polygon.gdshader": FLOAT_MAP_POLYGON,
    "crystal.gdshader": FLOAT_MAP_CRYSTAL,
    "water.gdshader": FLOAT_MAP_WATER,
    "particles.gdshader": FLOAT_MAP_PARTICLES,
    "skydome.gdshader": FLOAT_MAP_SKYDOME,
    "clouds.gdshader": FLOAT_MAP_CLOUDS,
}

# =============================================================================
# COLOR PROPERTY MAPPINGS
# =============================================================================
# Maps Unity color property names to Godot shader parameter names.
#
# Unity stores colors in m_Colors as RGBA objects with r, g, b, a fields.
# Note: Many Unity colors have alpha=0 even when opaque (see ALPHA_FIX_PROPERTIES).
# =============================================================================

COLOR_MAP_FOLIAGE: dict[str, str] = {
    "_Color": "color_tint",
    "_Color_Tint": "color_tint",
    "_BaseColor": "color_tint",  # URP variant
    "_Leaf_Base_Color": "leaf_base_color",
    "_Trunk_Base_Color": "trunk_base_color",
    "_Leaf_Noise_Color": "leaf_noise_color",
    "_Trunk_Noise_Color": "trunk_noise_color",
    "_Emissive_Color": "emissive_color",
    "_Emissive_2_Color": "emissive_2_color",
    "_Trunk_Emissive_Color": "trunk_emissive_color",
    "_Frosting_Color": "frosting_color",
    # Legacy naming
    "_ColorTint": "color_tint",
}

COLOR_MAP_POLYGON: dict[str, str] = {
    # Base color/tint
    "_Color_Tint": "color_tint",
    "_Color": "color_tint",
    "_BaseColor": "color_tint",
    "_BaseColour": "color_tint",
    # Emission
    "_Emission_Color": "emission_color",
    "_EmissionColor": "emission_color",
    # Snow overlay
    "_Snow_Color": "snow_color",
    # Character colors (hair/skin)
    "_Hair_Color": "hair_color",
    "_Skin_Color": "skin_color",
    # Hologram/Neon (SciFi packs)
    "_Neon_Colour_01": "neon_color_01",
    "_Neon_Colour_02": "neon_color_02",
    "_Hologram_Color": "hologram_color",
    # Ghost effect (Horror)
    "_RimColor": "rim_color",
    # Grunge/Dust
    "_Dust_Colour": "dust_color",
    # Magic effects (DarkFantasy)
    "_Glow_Colour": "glow_color",
    "_Glow_Tint": "glow_tint",
    # Liquid/Potion
    "_Liquid_Color": "liquid_color",
    # Blood (Zombies)
    "_BloodColor": "blood_color",
    "_Blood_Color": "blood_color",
    # Character (Modular Fantasy Hero - 15-zone color system)
    "_Color_Primary": "color_primary",
    "_Color_Secondary": "color_secondary",
    "_Color_Tertiary": "color_tertiary",
    "_Color_Metal_Primary": "color_metal_primary",
    "_Color_Metal_Secondary": "color_metal_secondary",
    "_Color_Metal_Dark": "color_metal_dark",
    "_Color_Leather_Primary": "color_leather_primary",
    "_Color_Leather_Secondary": "color_leather_secondary",
    "_Color_Skin": "color_skin",
    "_Color_Hair": "color_hair",
    "_Color_Eyes": "color_eyes",
    "_Color_Stubble": "color_stubble",
    "_Color_Scar": "color_scar",
    "_Color_BodyArt": "color_bodyart",
}

COLOR_MAP_CRYSTAL: dict[str, str] = {
    "_Base_Color": "base_color",
    "_Base_Color_Multiplier": "base_color",
    "_Top_Color_Multiplier": "top_color",
    "_Deep_Color": "deep_color",
    "_Shallow_Color": "shallow_color",
    "_Fresnel_Color": "fresnel_color",
    "_Refraction_Color": "refraction_color",
}

COLOR_MAP_WATER: dict[str, str] = {
    # Depth-based colors (core water appearance)
    "_Shallow_Color": "shallow_color",
    "_Deep_Color": "deep_color",
    "_Very_Deep_Color": "very_deep_color",
    # British spelling variants (Goblin War Camp, Dwarven Dungeon)
    "_ShallowColour": "shallow_color",
    "_DeepColour": "deep_color",
    "_VeryDeepColour": "very_deep_color",
    # Foam and effects
    "_Foam_Color": "foam_color",
    "_Caustics_Color": "caustics_color",
    "_CausticColour": "caustics_color",  # British spelling variant
    "_Shore_Foam_Color_Tint": "shore_foam_color_tint",
    "_Shore_Wave_Color_Tint": "shore_wave_color_tint",
    # Glow/emission colors (Goblin War Camp, Dwarven Dungeon)
    "_FoamEmitColour": "shore_foam_color_tint",  # Foam emission color
    "_DepthGlowColour": "very_deep_color",  # Deep water glow
    # Base/Tint colors
    "_Color": "color_tint",
    "_Color_Tint": "color_tint",
    "_BaseColor": "color_tint",
    # Legacy property names (older packs)
    "_WaterDeepColor": "deep_color",
    "_WaterShallowColor": "shallow_color",
    "_Water_Deep_Color": "deep_color",
    "_Water_Shallow_Color": "shallow_color",
    "_Water_Near_Color": "shallow_color",
    "_Water_Far_Color": "deep_color",
    # Waterfall (ElvenRealm)
    "_WaterColour": "water_color",
    "_FresnelColour": "fresnel_color",
}

COLOR_MAP_PARTICLES: dict[str, str] = {
    "_Base_Color": "base_color",
    "_Color": "base_color",  # Standard Unity particle color
    "_Color_Tint": "base_color",
    "_BaseColor": "base_color",
    "_Fog_Color": "fog_color",
    "_EmissionColor": "emission_color",
}

COLOR_MAP_SKYDOME: dict[str, str] = {
    "_Top_Color": "top_color",
    "_Bottom_Color": "bottom_color",
}

COLOR_MAP_CLOUDS: dict[str, str] = {
    "_Top_Color": "top_color",
    "_Base_Color": "base_color",
    "_Fresnel_Color": "fresnel_color",
    "_Scattering_Color": "scattering_color",
    # SciFi Space cloud color variant
    "_CloudColor": "top_color",
    # Aurora (Vikings, ElvenRealm)
    "_Aurora_Color_01": "aurora_color_01",
    "_Aurora_Color_02": "aurora_color_02",
}

# Combined color map lookup by shader type
COLOR_MAPS: dict[str, dict[str, str]] = {
    "foliage.gdshader": COLOR_MAP_FOLIAGE,
    "polygon.gdshader": COLOR_MAP_POLYGON,
    "crystal.gdshader": COLOR_MAP_CRYSTAL,
    "water.gdshader": COLOR_MAP_WATER,
    "particles.gdshader": COLOR_MAP_PARTICLES,
    "skydome.gdshader": COLOR_MAP_SKYDOME,
    "clouds.gdshader": COLOR_MAP_CLOUDS,
}

# =============================================================================
# QUIRK HANDLING: ALPHA=0 FIX
# =============================================================================
# Unity often stores colors with alpha=0 even when the material is fully opaque.
#
# Why This Happens:
# -----------------
# 1. Some Unity shaders ignore alpha for certain properties (e.g., tint colors)
# 2. Default material templates in some packs have alpha=0
# 3. Artists copy-paste colors between materials, preserving incorrect alpha
# 4. Unity's color picker defaults to alpha=0 in some contexts
#
# The Fix:
# --------
# For properties in ALPHA_FIX_PROPERTIES, if the color has:
# - Non-zero RGB values (the color is actually being used)
# - Alpha exactly equal to 0.0
#
# Then we set alpha to 1.0 to make the color visible in Godot.
#
# Properties NOT in this list keep their original alpha (for intentional
# transparency effects like glass tint, particle fade, etc.)
# =============================================================================

ALPHA_FIX_PROPERTIES: set[str] = {
    # Crystal/Refractive materials (depth colors should be opaque)
    "_Base_Color",
    "_Base_Color_Multiplier",
    "_Top_Color_Multiplier",
    "_Deep_Color",
    "_Shallow_Color",
    "_Fresnel_Color",
    "_Refraction_Color",
    # Water (depth colors should be opaque for proper blending)
    "_Water_Deep_Color",
    "_Water_Shallow_Color",
    "_Water_Near_Color",
    "_Water_Far_Color",
    "_Foam_Color",
    "_Caustics_Color",
    "_CausticColour",
    "_Shore_Foam_Color_Tint",
    "_Shore_Wave_Color_Tint",
    "_WaterDeepColor",
    "_WaterShallowColor",
    "_WaterColour",
    "_FresnelColour",
    "_Very_Deep_Color",
    # British spelling variants (Goblin War Camp, Dwarven Dungeon)
    "_ShallowColour",
    "_DeepColour",
    "_VeryDeepColour",
    "_FoamEmitColour",
    "_DepthGlowColour",
    # Foliage (base colors and emissives)
    "_Leaf_Base_Color",
    "_Trunk_Base_Color",
    "_Emissive_Color",
    "_Emissive_2_Color",
    "_Trunk_Emissive_Color",
    "_Frosting_Color",
    # Neon/Glow (emission colors must be visible)
    "_Neon_Colour_01",
    "_Neon_Colour_02",
    "_Glow_Colour",
    "_Glow_Tint",
    "_RimColor",
    "_Hologram_Color",
    # Blood/Overlay
    "_BloodColor",
    "_Blood_Color",
    "_Dust_Colour",
    # General tint/base colors
    "_Color",
    "_BaseColor",
    "_BaseColour",
    "_Color_Tint",
    "_ColorTint",
    "_Hair_Color",
    "_Skin_Color",
    "_Snow_Color",
    "_Emission_Color",
    "_EmissionColor",
    "_Liquid_Color",
    # Skydome/Clouds
    "_Top_Color",
    "_Bottom_Color",
    "_Base_Color",
    "_Scattering_Color",
    # Aurora
    "_Aurora_Color_01",
    "_Aurora_Color_02",
    # Character colors (Modular Fantasy Hero)
    "_Color_Primary",
    "_Color_Secondary",
    "_Color_Tertiary",
    "_Color_Metal_Primary",
    "_Color_Metal_Secondary",
    "_Color_Metal_Dark",
    "_Color_Leather_Primary",
    "_Color_Leather_Secondary",
    "_Color_Skin",
    "_Color_Hair",
    "_Color_Eyes",
    "_Color_Stubble",
    "_Color_Scar",
    "_Color_BodyArt",
    # Foliage noise colors
    "_Leaf_Noise_Color",
    "_Trunk_Noise_Color",
}

# =============================================================================
# QUIRK HANDLING: BOOLEAN-AS-FLOAT PROPERTIES
# =============================================================================
# Unity stores boolean toggles as floats (0.0 = false, 1.0 = true).
#
# Why This Happens:
# -----------------
# Unity's material property system doesn't have a native boolean type.
# Shader authors use [Toggle] attributes which store as floats internally.
#
# The Fix:
# --------
# Properties in BOOLEAN_FLOAT_PROPERTIES are extracted from the float map
# and converted to proper booleans (value != 0.0) in the MappedMaterial.
#
# This allows Godot shaders to use proper boolean uniforms.
# =============================================================================

BOOLEAN_FLOAT_PROPERTIES: set[str] = {
    # Foliage wind animation toggles
    "_Enable_Breeze",
    "_Enable_Light_Wind",
    "_Enable_Strong_Wind",
    "_Enable_Wind_Twist",
    "_Enable_Frosting",
    "_Wind_Enabled",
    # Legacy wind toggles (stored as float)
    "_Leaves_Wave",
    "_Tree_Wave",
    # Crystal/Glass effect toggles
    "_Enable_Fresnel",
    "_Enable_Side_Fresnel",
    "_Enable_Depth",
    "_Enable_Refraction",
    "_Enable_Triplanar",
    # Polygon effect toggles
    "_Enable_Triplanar_Texture",
    "_Enable_Snow",
    "_Enable_Emission",
    "_Enable_Normals",
    "_AlphaClip",
    "_Enable_Hologram",
    "_Enable_Ghost",
    "_Use_Metallic_Map",
    "_Use_Weather_Controller",
    "_Use_Vertex_Color_Wind",
    "_Randomize_Flipbook_From_Location",
    "_Enable_UV_Distortion",
    "_Enable_Brightness_Breakup",
    "_Enable_Wave",
    "_Enable_Detail_Map",
    "_Enable_Parallax",
    "_Enable_AO",
    # Water effect toggles
    "_Enable_Shore_Wave_Foam",
    "_Enable_Shore_Foam",
    "_Enable_Shore_Waves",
    "_Enable_Ocean_Waves",
    "_Enable_Ocean_Wave",
    "_Enable_Caustics",
    "_Enable_Distortion",
    # Waterfall
    "_VertexOffset_Toggle",
    # Particles effect toggles
    "_Enable_Soft_Particles",
    "_Enable_Camera_Fade",
    "_Enable_Scene_Fog",
    # Skydome
    "_Enable_UV_Based",
    # Clouds
    "_Use_Environment_Override",
    "_Enable_Fog",
    "_Enable_Scattering",
}

# =============================================================================
# DEFAULT VALUE OVERRIDES
# =============================================================================
# Shader-specific default values to apply when Unity values are missing
# or would produce poor results in Godot.
#
# Why Defaults Are Needed:
# ------------------------
# 1. Unity materials may omit properties that have shader defaults
# 2. Some Unity defaults don't translate well to Godot's rendering
# 3. Certain effects need sensible starting values
#
# These defaults are applied ONLY when the property is not present in
# the Unity material. Explicit Unity values are never overridden.
# =============================================================================

SHADER_DEFAULTS: dict[str, dict[str, float | bool]] = {
    "crystal.gdshader": {
        # Unity crystals are often fully opaque (1.0), but crystals look
        # better with some translucency in Godot
        "opacity": 0.7,
    },
    "foliage.gdshader": {
        # Foliage should be matte, not shiny
        "leaf_smoothness": 0.1,   # Matte leaves
        "trunk_smoothness": 0.15,  # Slightly rough bark
        "leaf_metallic": 0.0,
        "trunk_metallic": 0.0,
    },
    "water.gdshader": {
        # Water should be very smooth and reflective
        "smoothness": 0.95,
        "metallic": 0.0,
    },
    "polygon.gdshader": {
        # Middle-ground defaults for general props
        "smoothness": 0.5,
        "metallic": 0.0,
    },
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Color:
    """RGBA color representation for material properties.

    Stores color values as floats in the range [0.0, 1.0] for each channel.
    This matches both Unity's internal representation and Godot's Color type.

    Attributes:
        r: Red channel (0.0 to 1.0).
        g: Green channel (0.0 to 1.0).
        b: Blue channel (0.0 to 1.0).
        a: Alpha channel (0.0 to 1.0), where 0.0 is fully transparent.

    Example:
        >>> color = Color(1.0, 0.5, 0.0, 1.0)  # Orange, fully opaque
        >>> color.as_tuple()
        (1.0, 0.5, 0.0, 1.0)
        >>> color.has_rgb()
        True

        >>> transparent = Color(0.0, 0.0, 0.0, 0.0)  # Invisible black
        >>> transparent.has_rgb()
        False
    """
    r: float = 0.0
    g: float = 0.0
    b: float = 0.0
    a: float = 1.0

    def as_tuple(self) -> tuple[float, float, float, float]:
        """Return color as RGBA tuple for Godot material export.

        Returns:
            Tuple of (r, g, b, a) float values.
        """
        return (self.r, self.g, self.b, self.a)

    def has_rgb(self) -> bool:
        """Check if color has any non-zero RGB component.

        Used by _fix_alpha_zero() to determine if a color with alpha=0
        is actually meant to be visible.

        Returns:
            True if any of r, g, b is non-zero.
        """
        return self.r != 0.0 or self.g != 0.0 or self.b != 0.0


@dataclass
class UnityMaterial:
    """Represents a parsed Unity material from a .mat file.

    This is the input format from the unity_parser module. It contains
    the raw Unity property names and values before conversion to Godot.

    Attributes:
        name: Material name from Unity's m_Name field.
        shader_guid: GUID of the Unity shader (32-character hex string).
        textures: Maps Unity texture property names (e.g., "_Base_Texture")
            to texture asset GUIDs.
        floats: Maps Unity float property names (e.g., "_Smoothness") to values.
        colors: Maps Unity color property names (e.g., "_Color") to Color objects.

    Example:
        >>> mat = UnityMaterial(
        ...     name="PolygonNature_Ground_01",
        ...     shader_guid="0730dae39bc73f34796280af9875ce14",
        ...     textures={"_Base_Texture": "abc123def456..."},
        ...     floats={"_Smoothness": 0.5, "_Metallic": 0.0},
        ...     colors={"_Color": Color(1.0, 1.0, 1.0, 1.0)}
        ... )

    Note:
        The actual material file also contains tex_envs with texture references.
        The textures dict here stores the GUID; full texture info (offset, scale)
        is in tex_envs on the real UnityMaterial from unity_parser.
    """
    name: str
    shader_guid: str
    textures: dict[str, str] = field(default_factory=dict)
    floats: dict[str, float] = field(default_factory=dict)
    colors: dict[str, Color] = field(default_factory=dict)


@dataclass
class MappedMaterial:
    """Godot-ready material with shader and mapped properties.

    Represents a material fully converted from Unity format, ready for
    .tres file generation by the material_writer module.

    All property names use Godot conventions (snake_case, no leading underscore).
    All values have been processed (alpha fixed, booleans extracted, defaults applied).

    Attributes:
        name: Material name (sanitized for filesystem compatibility).
        shader_file: Target Godot shader filename (e.g., "polygon.gdshader").
        textures: Maps Godot parameter names to texture filenames (without extension).
            Example: {"base_texture": "Ground_01_A", "normal_texture": "Ground_01_N"}
        floats: Maps Godot parameter names to float values.
            Example: {"smoothness": 0.5, "metallic": 0.0}
        bools: Maps Godot parameter names to boolean values.
            Example: {"enable_emission": True, "enable_snow": False}
        colors: Maps Godot parameter names to RGBA tuples (r, g, b, a).
            Example: {"color_tint": (1.0, 1.0, 1.0, 1.0)}

    Example:
        >>> mat = MappedMaterial(
        ...     name="PolygonNature_Ground_01",
        ...     shader_file="polygon.gdshader",
        ...     textures={"base_texture": "Ground_01_A", "normal_texture": "Ground_01_N"},
        ...     floats={"smoothness": 0.5, "metallic": 0.0},
        ...     bools={"enable_normal_texture": True},
        ...     colors={"color_tint": (1.0, 1.0, 1.0, 1.0)}
        ... )
        >>>
        >>> # Ready for .tres generation
        >>> print(f"Shader: {mat.shader_file}")
        Shader: polygon.gdshader
    """
    name: str
    shader_file: str
    textures: dict[str, str] = field(default_factory=dict)
    floats: dict[str, float] = field(default_factory=dict)
    bools: dict[str, bool] = field(default_factory=dict)
    colors: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)


# =============================================================================
# SHADER DETECTION
# =============================================================================

def detect_shader_type(
    shader_guid: str,
    material_name: str,
    floats: dict[str, float] | None = None,
    colors: dict[str, tuple[float, float, float, float]] | None = None,
) -> str:
    """Detect the appropriate Godot shader for a Unity material.

    Uses a 3-tier detection system to determine the best shader match:

    **Tier 1: GUID Lookup (Highest Priority)**
    Direct lookup in SHADER_GUID_MAP using the Unity shader's GUID.
    This is the most reliable method as Unity shader GUIDs are stable
    32-character hex identifiers that uniquely identify each shader.

    If the GUID maps to a specific shader (not polygon.gdshader), that
    shader is returned immediately without further analysis.

    **Tier 2: Name Pattern Scoring (Medium Priority)**
    When the GUID is unknown or maps to the generic polygon shader,
    the material name is scored against regex patterns. This handles:
    - Materials from new/unknown Synty packs
    - Materials using Unity's built-in shaders
    - Compound names like "Crystal_Leaves_01"

    Multiple patterns can match and scores accumulate. The shader with
    the highest total score wins (if score >= 20 points).

    Example scoring for "Crystal_Leaves_01":
    - "crystal" pattern: +45 to crystal.gdshader
    - "leaves" pattern: +20 to foliage.gdshader
    - Result: crystal.gdshader wins (45 > 20)

    **Tier 3: Property-Based Detection (Bonus Scoring)**
    Analyzes the material's float and color properties for shader-specific
    indicators. Each matching property adds 10 points to the relevant shader.

    For example, presence of these properties indicates crystal shader:
    - _Enable_Fresnel, _Fresnel_Power (float)
    - _Fresnel_Color, _Refraction_Color (color)

    **Default: polygon.gdshader**
    If no strong match is found (score < 20), defaults to polygon shader
    which is the most versatile and handles most material types.

    Args:
        shader_guid: Unity shader GUID from the .mat file's m_Shader.guid field.
            Can be empty string if unknown.
        material_name: Material name for pattern matching fallback.
        floats: Optional dictionary of float properties from m_Floats.
            Used for property-based scoring.
        colors: Optional dictionary of color properties from m_Colors.
            Used for property-based scoring. Colors as (r, g, b, a) tuples.

    Returns:
        Godot shader filename (e.g., "polygon.gdshader", "foliage.gdshader").
        Always returns a valid shader filename, never None.

    Example:
        >>> # Known GUID - direct lookup
        >>> shader = detect_shader_type(
        ...     "0730dae39bc73f34796280af9875ce14",  # PolygonLit GUID
        ...     "PolygonNature_Ground_01",
        ...     {"_Smoothness": 0.5},
        ...     {"_Color": (1, 1, 1, 1)}
        ... )
        >>> shader
        'polygon.gdshader'

        >>> # Unknown GUID - name-based detection
        >>> shader = detect_shader_type(
        ...     "unknown_guid_here",
        ...     "Crystal_Gem_Blue_01",
        ...     {},
        ...     {}
        ... )
        >>> shader
        'crystal.gdshader'

        >>> # Property-based detection
        >>> shader = detect_shader_type(
        ...     "unknown_guid_here",
        ...     "SomeMaterial",  # Name doesn't help
        ...     {"_Enable_Fresnel": 1.0, "_Fresnel_Power": 2.5},
        ...     {"_Deep_Color": (0.1, 0.2, 0.5, 1.0)}
        ... )
        >>> shader
        'crystal.gdshader'
    """
    # =========================================================================
    # TIER 1: Primary method - GUID lookup
    # =========================================================================
    guid_shader = SHADER_GUID_MAP.get(shader_guid)

    # If GUID maps to a SPECIFIC shader (not the generic polygon default), trust it
    if guid_shader and guid_shader != DEFAULT_SHADER:
        logger.debug(
            "Shader detected via GUID %s -> %s for material %s",
            shader_guid[:8], guid_shader, material_name
        )
        return guid_shader

    # =========================================================================
    # TIER 2 & 3: GUID is unknown or maps to polygon - use scoring-based detection
    # =========================================================================
    # Calculate scores for each shader based on name patterns and properties
    shader_scores: dict[str, int] = {}

    # Score name patterns (check ALL patterns, accumulate scores)
    for pattern, shader, score in SHADER_NAME_PATTERNS_SCORED:
        if pattern.search(material_name):
            shader_scores[shader] = shader_scores.get(shader, 0) + score
            logger.debug(
                "  Name pattern '%s' adds %d to %s (total: %d)",
                pattern.pattern, score, shader, shader_scores[shader]
            )

    # Property-based scoring (TIER 3)
    floats = floats or {}
    colors = colors or {}

    if floats or colors:

        # =====================================================================
        # PROPERTY-BASED SCORING (adds to name pattern scores)
        # =====================================================================
        # Each matching property adds points to that shader's score.
        # This helps disambiguate when name patterns are inconclusive.
        PROPERTY_SCORE = 10  # Points per matching property

        # WATER properties (shore foam, caustics, depth-based rendering)
        water_float_props = {
            "_Enable_Shore_Foam", "_Enable_Shore_Waves", "_Enable_Caustics",
            "_Enable_Ocean_Wave", "_Shore_Foam_Intensity", "_Water_Depth",
            "_Depth_Distance", "_Deep_Height", "_Shallow_Intensity",
            "_Shore_Wave_Speed", "_Ocean_Wave_Height", "_Ocean_Wave_Speed",
            "_Caustics_Intensity", "_Maximum_Depth", "_Base_Opacity",
            "_Shallows_Opacity", "_Very_Deep_Height"
        }
        water_color_props = {
            "_Water_Deep_Color", "_Water_Shallow_Color", "_Foam_Color",
            "_Shore_Wave_Color_Tint", "_Shore_Foam_Color_Tint", "_Caustics_Color"
        }
        # Note: _Deep_Color and _Shallow_Color removed - shared with crystal
        water_props = sum(1 for p in water_float_props if p in floats)
        water_props += sum(1 for p in water_color_props if p in colors)
        if water_props > 0:
            shader_scores["water.gdshader"] = shader_scores.get("water.gdshader", 0) + (water_props * PROPERTY_SCORE)

        # FOLIAGE properties (wind animation, separate leaf/trunk)
        foliage_float_props = {
            "_Enable_Breeze", "_Breeze_Strength", "_Enable_Light_Wind",
            "_Light_Wind_Strength", "_Enable_Strong_Wind", "_Strong_Wind_Strength",
            "_Wind_Enabled", "_Leaf_Metallic", "_Leaf_Smoothness",
            "_Trunk_Metallic", "_Trunk_Smoothness", "_Frosting_Falloff",
            "_Frosting_Height", "_Wind_Twist_Strength", "_Gale_Blend",
            "_Light_Wind_Y_Strength", "_Light_Wind_Y_Offset"
        }
        foliage_color_props = {
            "_Leaf_Base_Color", "_Trunk_Base_Color", "_Leaf_Noise_Color",
            "_Trunk_Noise_Color", "_Frosting_Color", "_Trunk_Emissive_Color"
        }
        foliage_props = sum(1 for p in foliage_float_props if p in floats)
        foliage_props += sum(1 for p in foliage_color_props if p in colors)
        if foliage_props > 0:
            shader_scores["foliage.gdshader"] = shader_scores.get("foliage.gdshader", 0) + (foliage_props * PROPERTY_SCORE)

        # CLOUDS properties (volumetric rendering, scattering)
        clouds_float_props = {
            "_Cloud_Speed", "_Cloud_Strength", "_Scattering_Multiplier",
            "_Scattering_Edge_Dist", "_Light_Intensity", "_Fog_Density"
        }
        clouds_color_props = {"_Scattering_Color"}
        clouds_props = sum(1 for p in clouds_float_props if p in floats)
        clouds_props += sum(1 for p in clouds_color_props if p in colors)
        if clouds_props > 0:
            shader_scores["clouds.gdshader"] = shader_scores.get("clouds.gdshader", 0) + (clouds_props * PROPERTY_SCORE)

        # PARTICLES properties (soft blending, camera fade)
        particles_float_props = {
            "_Soft_Power", "_Soft_Distance", "_Enable_Soft_Particles",
            "_Camera_Fade_Near", "_Camera_Fade_Far", "_Camera_Fade_Smoothness",
            "_View_Edge_Power", "_Enable_Camera_Fade"
        }
        particles_props = sum(1 for p in particles_float_props if p in floats)
        if particles_props > 0:
            shader_scores["particles.gdshader"] = shader_scores.get("particles.gdshader", 0) + (particles_props * PROPERTY_SCORE)

        # SKYDOME properties (procedural gradient)
        skydome_float_props = {"_Falloff", "_Offset", "_Distance"}
        skydome_color_props = {"_Top_Color", "_Bottom_Color"}
        skydome_props = sum(1 for p in skydome_float_props if p in floats)
        skydome_props += sum(1 for p in skydome_color_props if p in colors)
        # Bonus for having both sky gradient colors (very strong indicator)
        if "_Top_Color" in colors and "_Bottom_Color" in colors:
            skydome_props += 2
        if skydome_props > 0:
            shader_scores["skydome.gdshader"] = shader_scores.get("skydome.gdshader", 0) + (skydome_props * PROPERTY_SCORE)

        # CRYSTAL properties (fresnel, refraction, depth effects)
        crystal_float_props = {
            "_Enable_Fresnel", "_Enable_Depth", "_Enable_Refraction",
            "_Fresnel_Power", "_Refraction_Strength", "_Opacity",
            "_Deep_Depth", "_Shallow_Depth"
        }
        crystal_color_props = {"_Fresnel_Color", "_Refraction_Color"}
        # Note: _Deep_Color and _Shallow_Color removed - shared with water
        crystal_props = sum(1 for p in crystal_float_props if p in floats)
        crystal_props += sum(1 for p in crystal_color_props if p in colors)
        if crystal_props > 0:
            shader_scores["crystal.gdshader"] = shader_scores.get("crystal.gdshader", 0) + (crystal_props * PROPERTY_SCORE)

    # =========================================================================
    # SELECT HIGHEST SCORING SHADER
    # =========================================================================
    if shader_scores:
        # Find shader with highest score
        best_shader = max(shader_scores, key=shader_scores.get)
        best_score = shader_scores[best_shader]

        # Only use scoring result if score is significant (>= 20 points)
        # This prevents weak matches from overriding the default
        if best_score >= 20:
            logger.debug(
                "Shader detected via SCORING -> %s (score: %d) for material %s | All scores: %s",
                best_shader, best_score, material_name,
                {k: v for k, v in sorted(shader_scores.items(), key=lambda x: -x[1])}
            )
            return best_shader

    # Default fallback - use GUID result (polygon) if available, otherwise default
    result = guid_shader or DEFAULT_SHADER
    if guid_shader:
        logger.debug(
            "Shader detected via GUID %s -> %s (generic) for material %s",
            shader_guid[:8], result, material_name
        )
    else:
        logger.debug(
            "No strong match for material %s (GUID: %s), using default %s",
            material_name, shader_guid[:8] if shader_guid else "none", result
        )
    return result


# =============================================================================
# PROPERTY CONVERSION HELPERS
# =============================================================================

def _fix_alpha_zero(
    color: Color,
    property_name: str,
    floats: dict[str, float] | None = None
) -> Color:
    """Fix Unity's alpha=0 color quirk for specific properties.

    Unity often stores colors with alpha=0 even when the material is opaque.
    This occurs because:
    - Some Unity shaders ignore alpha for certain properties (tints, base colors)
    - Default material templates in some Synty packs have alpha=0
    - Unity's color picker can default to alpha=0 in certain contexts
    - Copy-paste between materials preserves incorrect alpha values

    This function detects affected properties and sets alpha=1.0 when
    the color has visible RGB values but zero alpha.

    Only properties listed in ALPHA_FIX_PROPERTIES are affected. Properties
    not in the list retain their original alpha (for intentional transparency
    like glass tint, particle fade colors, etc.)

    IMPORTANT: Materials using transparency modes (Cutout=1, Fade=2, Transparent=3)
    are skipped entirely - their low alpha values are intentional.

    Args:
        color: Color with potentially incorrect alpha value.
        property_name: Unity property name to check against ALPHA_FIX_PROPERTIES.
        floats: Optional dict of material float properties. If provided and
            contains _Mode >= 1, alpha fix is skipped (transparent material).

    Returns:
        New Color with corrected alpha if property is in fix list and has
        non-zero RGB with zero alpha. Otherwise returns original color.

    Example:
        >>> # Unity stored {r: 0.5, g: 0.3, b: 0.2, a: 0} for _Color (wrong!)
        >>> color = Color(0.5, 0.3, 0.2, 0.0)
        >>> fixed = _fix_alpha_zero(color, "_Color")
        >>> fixed.a
        1.0

        >>> # Property not in fix list - alpha preserved
        >>> color = Color(0.5, 0.3, 0.2, 0.0)
        >>> fixed = _fix_alpha_zero(color, "_SomeOtherProperty")
        >>> fixed.a
        0.0

        >>> # Color with actual alpha=0 and no RGB - not modified
        >>> color = Color(0.0, 0.0, 0.0, 0.0)
        >>> fixed = _fix_alpha_zero(color, "_Color")
        >>> fixed.a
        0.0

        >>> # Transparent material (_Mode >= 1) - alpha preserved
        >>> color = Color(0.5, 0.3, 0.2, 0.3)
        >>> fixed = _fix_alpha_zero(color, "_Color", {"_Mode": 2.0})
        >>> fixed.a
        0.3
    """
    # Skip alpha fix for transparent materials (_Mode: 1=Cutout, 2=Fade, 3=Transparent)
    # These materials have intentionally low alpha values
    if floats is not None and floats.get("_Mode", 0) >= 1.0:
        logger.debug(
            "Skipping alpha fix for property %s (transparent material, _Mode=%s)",
            property_name, floats.get("_Mode")
        )
        return color

    if property_name in ALPHA_FIX_PROPERTIES:
        if color.a == 0.0 and color.has_rgb():
            logger.debug(
                "Fixed alpha=0 for property %s (RGB has values)",
                property_name
            )
            return Color(color.r, color.g, color.b, 1.0)
    return color


def _convert_boolean_floats(
    floats: dict[str, float],
    float_map: dict[str, str]
) -> tuple[dict[str, float], dict[str, bool]]:
    """Split boolean-as-float properties from regular floats.

    Unity stores boolean shader toggles as floats (0.0 = false, 1.0 = true)
    because the material property system lacks a native boolean type.

    This function separates boolean properties (listed in BOOLEAN_FLOAT_PROPERTIES)
    from regular floats and converts them to proper Python booleans.

    The conversion also maps Unity property names to Godot parameter names
    using the provided float_map.

    Args:
        floats: Dictionary of Unity float properties (name -> value).
        float_map: Mapping from Unity names to Godot names for this shader type.

    Returns:
        Tuple of two dictionaries:
        - remaining_floats: Regular float properties with Godot names
        - extracted_bools: Boolean properties converted to bool with Godot names

    Example:
        >>> floats = {
        ...     "_Smoothness": 0.5,
        ...     "_Enable_Emission": 1.0,  # Boolean toggle
        ...     "_Enable_Snow": 0.0,      # Boolean toggle
        ... }
        >>> float_map = {
        ...     "_Smoothness": "smoothness",
        ...     "_Enable_Emission": "enable_emission",
        ...     "_Enable_Snow": "enable_snow",
        ... }
        >>> remaining, bools = _convert_boolean_floats(floats, float_map)
        >>> remaining
        {'smoothness': 0.5}
        >>> bools
        {'enable_emission': True, 'enable_snow': False}
    """
    remaining_floats: dict[str, float] = {}
    extracted_bools: dict[str, bool] = {}

    for unity_name, value in floats.items():
        if unity_name in BOOLEAN_FLOAT_PROPERTIES:
            # Convert to boolean
            godot_name = float_map.get(unity_name)
            if godot_name is None:
                # Try to derive a reasonable Godot name
                godot_name = _unity_to_godot_name(unity_name)
            extracted_bools[godot_name] = value != 0.0
        elif unity_name in float_map:
            godot_name = float_map[unity_name]
            remaining_floats[godot_name] = value

    return remaining_floats, extracted_bools


def _unity_to_godot_name(unity_name: str) -> str:
    """Convert a Unity property name to Godot snake_case style.

    Unity property names typically start with underscore and use PascalCase
    or Mixed_Case. Godot shader parameters use snake_case without leading
    underscore.

    Args:
        unity_name: Unity property name (e.g., "_Enable_Breeze", "_BaseColor").

    Returns:
        Godot style name (e.g., "enable_breeze", "base_color").

    Example:
        >>> _unity_to_godot_name("_Enable_Breeze")
        'enable_breeze'
        >>> _unity_to_godot_name("_BaseColor")
        'base_color'
        >>> _unity_to_godot_name("_Smooth_Amount")
        'smooth_amount'
    """
    name = unity_name.lstrip("_")
    # Insert underscore before uppercase letters and lowercase the result
    result = re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()
    # Handle double underscores (from _Mixed_Case patterns)
    result = re.sub(r'_+', '_', result)
    return result


def _apply_defaults(material: MappedMaterial) -> MappedMaterial:
    """Apply shader-specific default values for missing properties.

    Some materials need sensible defaults when Unity values are missing
    or would produce poor results in Godot. For example:
    - Crystal opacity defaults to 0.7 (semi-transparent) not 1.0
    - Foliage smoothness defaults to 0.1 (matte) not 0.5

    Defaults are only applied if the property is NOT already present
    in the material. Explicit Unity values are never overridden.

    Args:
        material: Mapped material (modified in place).

    Returns:
        The same material object with defaults applied.

    Example:
        >>> mat = MappedMaterial(name="test", shader_file="crystal.gdshader")
        >>> mat.floats  # Empty, no opacity set
        {}
        >>> _apply_defaults(mat)
        >>> mat.floats
        {'opacity': 0.7}
    """
    defaults = SHADER_DEFAULTS.get(material.shader_file, {})

    for prop_name, default_value in defaults.items():
        if isinstance(default_value, bool):
            if prop_name not in material.bools:
                material.bools[prop_name] = default_value
                logger.debug(
                    "Applied default %s=%s to material %s",
                    prop_name, default_value, material.name
                )
        elif isinstance(default_value, (int, float)):
            if prop_name not in material.floats:
                material.floats[prop_name] = float(default_value)
                logger.debug(
                    "Applied default %s=%s to material %s",
                    prop_name, default_value, material.name
                )

    return material


def validate_shader_properties(shader_file: str, material: UnityMaterial) -> bool:
    """Check if material has properties that justify using this specialized shader.

    When a material matches a specialized shader via name pattern matching,
    this function verifies the material actually has properties specific to
    that shader. This prevents false positives where a material named
    "Water_Bucket_Prop" (a metal bucket, not water) gets the water shader.

    Args:
        shader_file: The shader filename to validate (e.g., "water.gdshader").
        material: The Unity material to check properties of.

    Returns:
        True if at least one shader-specific property is present.
        True for polygon.gdshader (always valid as fallback).
        True for unknown shaders (don't block shaders not in the validation dict).
    """
    if shader_file == "polygon.gdshader":
        return True

    specific = SHADER_SPECIFIC_PROPERTIES.get(shader_file)
    if not specific:
        return True  # Unknown shader, don't block it

    # Check textures
    for tex_name in material.tex_envs:
        if tex_name in specific["textures"]:
            return True

    # Check floats
    for float_name in material.floats:
        if float_name in specific["floats"]:
            return True

    # Check colors
    for color_name in material.colors:
        if color_name in specific["colors"]:
            return True

    return False


# =============================================================================
# MAIN CONVERSION FUNCTION
# =============================================================================

def map_material(
    material: UnityMaterial,
    texture_guid_map: dict[str, str],
    override_shader: str | None = None,
) -> MappedMaterial:
    """Convert a Unity material to Godot format.

    This is the main entry point for material conversion. Performs the
    complete property mapping from Unity to Godot:

    **Step 1: Shader Detection**
    If override_shader is provided, uses that directly (from shader cache).
    Otherwise calls detect_shader_type() to determine which Godot shader to use
    via GUID lookup, name patterns, and property analysis.

    **Step 2: Property Map Selection**
    Selects the appropriate TEXTURE_MAP, FLOAT_MAP, and COLOR_MAP
    for the detected shader type. Polygon maps are included as fallback
    for all shaders (common properties like _Color work everywhere).

    **Step 3: Texture Mapping**
    Resolves Unity texture GUIDs to filenames using the provided
    texture_guid_map. Maps Unity property names to Godot parameter names.

    **Step 4: Float Mapping**
    Converts Unity float properties to Godot parameters. Separates
    boolean-as-float properties into proper booleans.

    **Step 5: Color Mapping**
    Converts Unity colors to Godot format. Fixes the alpha=0 quirk
    for affected properties.

    **Step 6: Default Application**
    Applies shader-specific defaults for missing properties.

    Args:
        material: Parsed Unity material from unity_parser module.
        texture_guid_map: Maps texture GUIDs to filename stems (no extension).
            Typically from UnityPackageExtract.texture_guid_to_name.
        override_shader: Optional shader filename to use instead of detection.
            When provided, skips all shader detection logic. Used by the
            converter's shader cache system for MaterialList-based detection.

    Returns:
        MappedMaterial ready for .tres file generation by material_writer.

    Example:
        >>> from unity_parser import parse_material_bytes
        >>> from unity_package import extract_unitypackage
        >>>
        >>> # Extract package to get texture GUID map
        >>> guid_map = extract_unitypackage(Path("PolygonNature.unitypackage"))
        >>>
        >>> # Parse a material file
        >>> unity_mat = parse_material_bytes(
        ...     guid_map.guid_to_content["abc123..."],
        ...     "Ground_01"
        ... )
        >>>
        >>> # Convert to Godot format
        >>> godot_mat = map_material(unity_mat, guid_map.texture_guid_to_name)
        >>>
        >>> print(godot_mat.shader_file)
        'polygon.gdshader'
        >>> print(godot_mat.textures)
        {'base_texture': 'Texture_01', 'normal_texture': 'Texture_01_N'}
        >>> print(godot_mat.floats)
        {'smoothness': 0.5, 'metallic': 0.0}

    Note:
        The material object must have a tex_envs attribute (from unity_parser)
        that contains the full texture references with GUIDs.
    """
    # Step 1: Detect shader type
    # If override_shader provided, use it directly (from shader cache)
    if override_shader:
        shader_file = override_shader
        logger.debug(
            "Using override shader %s for material %s",
            shader_file, material.name
        )
    else:
        # Fall back to full detection (pass floats and colors for property-based detection)
        # Convert Color objects to tuples for the detection function
        color_tuples = {name: color.as_tuple() for name, color in material.colors.items()}
        shader_file = detect_shader_type(
            material.shader_guid,
            material.name,
            floats=material.floats,
            colors=color_tuples,
        )

    # Validate shader-specific properties - fall back to polygon if material
    # doesn't have properties that justify using the specialized shader
    if not validate_shader_properties(shader_file, material):
        logger.debug(
            "Shader %s detected for '%s' via name pattern, but no shader-specific "
            "properties found. Falling back to polygon.gdshader",
            shader_file, material.name
        )
        shader_file = DEFAULT_SHADER

    # Step 2: Get the appropriate property maps for this shader
    texture_map = TEXTURE_MAPS.get(shader_file, {})
    float_map = FLOAT_MAPS.get(shader_file, {})
    color_map = COLOR_MAPS.get(shader_file, {})

    # Also include polygon maps as fallback for all shaders (common properties)
    if shader_file != "polygon.gdshader":
        texture_map = {**TEXTURE_MAP_POLYGON, **texture_map}
        float_map = {**FLOAT_MAP_POLYGON, **float_map}
        color_map = {**COLOR_MAP_POLYGON, **color_map}

    # Step 3: Map textures
    mapped_textures: dict[str, str] = {}
    for unity_name, tex_ref in material.tex_envs.items():
        if unity_name in texture_map:
            godot_name = texture_map[unity_name]
            # Resolve GUID to texture filename
            texture_name = texture_guid_map.get(tex_ref.guid)
            if texture_name:
                mapped_textures[godot_name] = texture_name
            else:
                logger.debug(
                    "Could not resolve texture GUID %s for property %s in material %s",
                    tex_ref.guid[:8], unity_name, material.name
                )

    # Step 4: Map floats (splitting out booleans)
    mapped_floats, mapped_bools = _convert_boolean_floats(material.floats, float_map)

    # Step 5: Map colors (with alpha fix, but preserve alpha for transparent materials)
    mapped_colors: dict[str, tuple[float, float, float, float]] = {}
    for unity_name, color in material.colors.items():
        if unity_name in color_map:
            godot_name = color_map[unity_name]
            fixed_color = _fix_alpha_zero(color, unity_name, material.floats)
            mapped_colors[godot_name] = fixed_color.as_tuple()

    # Create mapped material
    result = MappedMaterial(
        name=material.name,
        shader_file=shader_file,
        textures=mapped_textures,
        floats=mapped_floats,
        bools=mapped_bools,
        colors=mapped_colors,
    )

    # Step 6: Apply defaults
    result = _apply_defaults(result)

    logger.debug(
        "Mapped material %s -> %s (textures=%d, floats=%d, bools=%d, colors=%d)",
        material.name, shader_file,
        len(result.textures), len(result.floats),
        len(result.bools), len(result.colors)
    )

    return result


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_all_shader_guids() -> set[str]:
    """Return all known shader GUIDs from SHADER_GUID_MAP.

    Returns:
        Set of 32-character hex GUID strings.
    """
    return set(SHADER_GUID_MAP.keys())


def get_shader_for_guid(guid: str) -> str | None:
    """Get the Godot shader filename for a Unity shader GUID.

    This is a simple GUID lookup without any fallback detection.
    Use detect_shader_type() for full detection with fallbacks.

    Args:
        guid: Unity shader GUID (32-character hex string).

    Returns:
        Godot shader filename or None if GUID is unknown.

    Example:
        >>> get_shader_for_guid("0730dae39bc73f34796280af9875ce14")
        'polygon.gdshader'
        >>> get_shader_for_guid("unknown_guid") is None
        True
    """
    return SHADER_GUID_MAP.get(guid)


def get_texture_property_mapping(shader_file: str) -> dict[str, str]:
    """Get the texture property mapping for a shader.

    Args:
        shader_file: Godot shader filename (e.g., "polygon.gdshader").

    Returns:
        Dictionary mapping Unity texture property names to Godot names.
        Empty dict if shader is unknown.
    """
    return TEXTURE_MAPS.get(shader_file, {})


def get_float_property_mapping(shader_file: str) -> dict[str, str]:
    """Get the float property mapping for a shader.

    Args:
        shader_file: Godot shader filename (e.g., "polygon.gdshader").

    Returns:
        Dictionary mapping Unity float property names to Godot names.
        Empty dict if shader is unknown.
    """
    return FLOAT_MAPS.get(shader_file, {})


def get_color_property_mapping(shader_file: str) -> dict[str, str]:
    """Get the color property mapping for a shader.

    Args:
        shader_file: Godot shader filename (e.g., "polygon.gdshader").

    Returns:
        Dictionary mapping Unity color property names to Godot names.
        Empty dict if shader is unknown.
    """
    return COLOR_MAPS.get(shader_file, {})


# =============================================================================
# NEW SIMPLIFIED SHADER DETECTION (MaterialList-based)
# =============================================================================
# These functions use the simpler detection flow based on MaterialList.txt:
# 1. If uses_custom_shader=False -> polygon.gdshader (immediate)
# 2. If uses_custom_shader=True -> name pattern matching -> shader or polygon
# 3. LOD inheritance: LOD0's shader decision applies to all LODs


def detect_shader_from_name(material_name: str) -> str | None:
    """Detect shader type using only name pattern matching.

    Used when uses_custom_shader=True in MaterialList.
    Returns shader filename or None if no match (signals logging needed).

    This is a simplified detection method that only uses material name patterns,
    without GUID lookup or property analysis. It's designed for use with
    MaterialList.txt which tells us whether a material uses a custom shader.

    Args:
        material_name: The material name to analyze.

    Returns:
        Shader filename if a strong match is found (score >= 20),
        None if no strong match (caller should log for manual review).

    Example:
        >>> detect_shader_from_name("Crystal_Mat_01")
        'crystal.gdshader'
        >>> detect_shader_from_name("Water_River_01")
        'water.gdshader'
        >>> detect_shader_from_name("SomeUnknownMaterial")
        None
    """
    shader_scores: dict[str, int] = {}

    for pattern, shader, score in SHADER_NAME_PATTERNS_SCORED:
        if pattern.search(material_name):
            shader_scores[shader] = shader_scores.get(shader, 0) + score

    if shader_scores:
        best_shader = max(shader_scores, key=shader_scores.get)
        best_score = shader_scores[best_shader]

        if best_score >= 20:  # Minimum threshold
            logger.debug(
                "Shader detected via name pattern -> %s (score: %d) for material %s",
                best_shader, best_score, material_name
            )
            return best_shader

    # No match - return None to signal logging needed
    return None


def determine_shader(
    material_name: str,
    uses_custom_shader: bool,
) -> tuple[str, bool]:
    """Determine shader for a material using the simplified MaterialList-based flow.

    This is the main entry point for the new detection system. The logic is:
    1. If not a custom shader (uses_custom_shader=False), always use polygon
    2. If custom shader, try name pattern matching
    3. If no match, default to polygon but signal for logging

    Args:
        material_name: The material name.
        uses_custom_shader: From MaterialList.txt - True if marked "(Uses custom shader)".

    Returns:
        Tuple of (shader_filename, matched) where:
        - shader_filename: The Godot shader to use
        - matched: False if the material should be logged for manual review
                   (used to track unmatched custom shader materials)

    Example:
        >>> determine_shader("Ground_Mat", uses_custom_shader=False)
        ('polygon.gdshader', True)
        >>> determine_shader("Crystal_Mat_01", uses_custom_shader=True)
        ('crystal.gdshader', True)
        >>> determine_shader("UnknownMat", uses_custom_shader=True)
        ('polygon.gdshader', False)  # Needs manual review
    """
    # If not a custom shader, always use polygon
    if not uses_custom_shader:
        logger.debug(
            "Material %s: uses_custom_shader=False -> %s",
            material_name, DEFAULT_SHADER
        )
        return DEFAULT_SHADER, True

    # Try name pattern matching
    shader = detect_shader_from_name(material_name)
    if shader:
        return shader, True

    # No match - default to polygon but signal for logging
    logger.debug(
        "Material %s: custom shader, no name pattern match -> %s (unmatched)",
        material_name, DEFAULT_SHADER
    )
    return DEFAULT_SHADER, False


def create_placeholder_material(material_name: str) -> MappedMaterial:
    """Create a placeholder material based on the material name.

    Used when a material is referenced in mesh_material_mapping.json but
    doesn't exist in the Unity package (e.g., shared materials from other packs).

    The shader type is detected from the name using the scoring system.
    Appropriate default values are applied based on the detected shader.

    Args:
        material_name: Name of the missing material (e.g., "Crystal_Mat_01").

    Returns:
        MappedMaterial with appropriate shader and default values.
        No textures are assigned (placeholder has no texture data).

    Example:
        >>> mat = create_placeholder_material("Crystal_Blue_01")
        >>> mat.shader_file
        'crystal.gdshader'
        >>> mat.floats.get('opacity')
        0.7
        >>> mat.colors.get('base_color')
        (0.5, 0.7, 1.0, 1.0)
    """
    # Detect shader from name (no GUID available)
    shader_file = detect_shader_type(
        shader_guid="",  # No GUID
        material_name=material_name,
        floats=None,
        colors=None,
    )

    logger.debug(
        "Creating placeholder material '%s' -> %s",
        material_name, shader_file
    )

    # Get default values for this shader
    defaults = SHADER_DEFAULTS.get(shader_file, {})

    # Build mapped material with defaults
    mapped_floats: dict[str, float] = {}
    mapped_bools: dict[str, bool] = {}
    mapped_colors: dict[str, tuple[float, float, float, float]] = {}

    for key, value in defaults.items():
        if isinstance(value, bool):
            mapped_bools[key] = value
        elif isinstance(value, float):
            mapped_floats[key] = value

    # Add some standard defaults based on shader type
    # These provide reasonable starting visuals for placeholder materials
    if shader_file == "crystal.gdshader":
        if "opacity" not in mapped_floats:
            mapped_floats["opacity"] = 0.7
        if "base_color" not in mapped_colors:
            mapped_colors["base_color"] = (0.5, 0.7, 1.0, 1.0)  # Light blue
        if "enable_fresnel" not in mapped_bools:
            mapped_bools["enable_fresnel"] = True
    elif shader_file == "water.gdshader":
        if "deep_color" not in mapped_colors:
            mapped_colors["deep_color"] = (0.0, 0.2, 0.4, 1.0)
        if "shallow_color" not in mapped_colors:
            mapped_colors["shallow_color"] = (0.2, 0.5, 0.7, 1.0)
    elif shader_file == "foliage.gdshader":
        if "leaf_base_color" not in mapped_colors:
            mapped_colors["leaf_base_color"] = (0.2, 0.5, 0.2, 1.0)

    return MappedMaterial(
        name=material_name,
        shader_file=shader_file,
        textures={},  # No textures for placeholder
        floats=mapped_floats,
        bools=mapped_bools,
        colors=mapped_colors,
    )


def print_shader_mapping_summary() -> None:
    """Print a summary of the shader mappings to stdout.

    Useful for debugging and verification. Shows:
    - Total count of known GUIDs, patterns, and properties
    - Breakdown of GUIDs by target shader type
    """
    print(f"\n{'='*60}")
    print("Shader Mapping Summary")
    print(f"{'='*60}")
    print(f"Known shader GUIDs: {len(SHADER_GUID_MAP)}")
    print(f"Name fallback patterns: {len(SHADER_NAME_PATTERNS)}")
    print(f"Alpha-fix properties: {len(ALPHA_FIX_PROPERTIES)}")
    print(f"Boolean-float properties: {len(BOOLEAN_FLOAT_PROPERTIES)}")

    # Count by target shader
    shader_counts: dict[str, int] = {}
    for shader in SHADER_GUID_MAP.values():
        shader_counts[shader] = shader_counts.get(shader, 0) + 1

    print(f"\nGUIDs by target shader:")
    for shader, count in sorted(shader_counts.items(), key=lambda x: -x[1]):
        print(f"  {shader}: {count}")

    print(f"{'='*60}\n")


# =============================================================================
# CLI ENTRY POINT
# =============================================================================
# For testing shader detection from the command line.

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")

    print_shader_mapping_summary()

    # Test shader detection with various scenarios
    test_cases = [
        ("0730dae39bc73f34796280af9875ce14", "TestMaterial", None, None),  # PolygonLit
        ("9b98a126c8d4d7a4baeb81b16e4f7b97", "TreeMaterial", None, None),  # Foliage
        ("unknown_guid_12345678901234567", "Crystal_Mat_01", None, None),  # Pattern match
        ("unknown_guid_12345678901234567", "GenericMaterial", None, None),  # Default
        # Property-based crystal detection test
        (
            "unknown_guid_12345678901234567",
            "SomeMaterial",
            {"_Enable_Fresnel": 1.0, "_Fresnel_Power": 2.5, "_Opacity": 0.7},
            {"_Deep_Color": (0.1, 0.2, 0.5, 1.0)},
        ),  # Crystal by properties (4 matches)
    ]

    print("Shader Detection Tests:")
    for guid, name, floats, colors in test_cases:
        result = detect_shader_type(guid, name, floats=floats, colors=colors)
        print(f"  {name} (GUID: {guid[:8]}...) -> {result}")
