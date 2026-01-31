# Step 6: Shader Detection and Property Mapping

This document provides comprehensive documentation for the `shader_mapping.py` module - the **core intelligence** of the Synty Converter. This module detects Unity shader types and maps material properties to Godot equivalents.

**Module Location:** `synty-converter/shader_mapping.py` (2,339 lines)

**Related Documentation:**
- [Architecture](../architecture.md) - Overall pipeline context
- [Shader Reference](../shader-reference.md) - Godot shader feature details
- [API: shader_mapping](../api/shader_mapping.md) - Quick API reference
- [API: constants](../api/constants.md) - Full constant listings
- [Step 4: Parse Materials](./04-parse-materials.md) - Input format (UnityMaterial)

---

## Table of Contents

- [Overview](#overview)
- [The Shader Detection Challenge](#the-shader-detection-challenge)
- [Data Classes](#data-classes)
  - [Color](#color)
  - [UnityMaterial](#unitymaterial)
  - [MappedMaterial](#mappedmaterial)
- [3-Tier Shader Detection System](#3-tier-shader-detection-system)
  - [Tier 1: GUID Lookup](#tier-1-guid-lookup)
  - [Tier 2: Name Pattern Scoring](#tier-2-name-pattern-scoring)
  - [Tier 3: Property-Based Detection](#tier-3-property-based-detection)
  - [Scoring Algorithm](#scoring-algorithm)
  - [Detection Flow Diagram](#detection-flow-diagram)
- [SHADER_GUID_MAP Reference](#shader_guid_map-reference)
  - [Core Synty Shaders](#core-synty-shaders)
  - [Pack-Specific Shaders](#pack-specific-shaders)
  - [Adding New GUIDs](#adding-new-guids)
- [SHADER_NAME_PATTERNS_SCORED Reference](#shader_name_patterns_scored-reference)
  - [Score Tiers](#score-tiers)
  - [Complete Pattern Table](#complete-pattern-table)
  - [Compound Name Resolution](#compound-name-resolution)
- [Property Mapping Dictionaries](#property-mapping-dictionaries)
  - [TEXTURE_MAPS](#texture_maps)
  - [FLOAT_MAPS](#float_maps)
  - [COLOR_MAPS](#color_maps)
- [Unity Quirk Handling](#unity-quirk-handling)
  - [Alpha=0 Color Fix](#alpha0-color-fix)
  - [Boolean-as-Float Conversion](#boolean-as-float-conversion)
- [Shader-Specific Defaults](#shader-specific-defaults)
- [Shader-Specific Property Validation](#shader-specific-property-validation)
- [Public API Functions](#public-api-functions)
  - [detect_shader_type()](#detect_shader_type)
  - [map_material()](#map_material)
  - [determine_shader()](#determine_shader)
  - [create_placeholder_material()](#create_placeholder_material)
- [Helper Functions](#helper-functions)
  - [_fix_alpha_zero()](#_fix_alpha_zero)
  - [_convert_boolean_floats()](#_convert_boolean_floats)
  - [_unity_to_godot_name()](#_unity_to_godot_name)
  - [_apply_defaults()](#_apply_defaults)
  - [validate_shader_properties()](#validate_shader_properties)
- [Utility Functions](#utility-functions)
- [Error Handling](#error-handling)
- [CLI Testing Interface](#cli-testing-interface)
- [Code Examples](#code-examples)
- [Notes for Doc Cleanup](#notes-for-doc-cleanup)

---

## Overview

The `shader_mapping.py` module is **Step 6** in the 12-step conversion pipeline. It receives parsed `UnityMaterial` objects (from Step 4) and produces `MappedMaterial` objects ready for `.tres` file generation (Step 7).

### Key Responsibilities

1. **Shader Detection** - Determine which of 7 Godot shaders to use for each Unity material
2. **Property Translation** - Map Unity property names (e.g., `_Base_Texture`) to Godot names (`base_texture`)
3. **Texture Resolution** - Convert Unity texture GUIDs to filenames via the texture GUID map
4. **Quirk Handling** - Fix Unity's alpha=0 colors and boolean-as-float storage
5. **Default Values** - Apply sensible defaults when Unity values are missing or problematic

### Module Statistics

Based on analysis of **29 Synty Unity packages** (~3,300 materials):

| Constant | Entry Count |
|----------|-------------|
| `SHADER_GUID_MAP` | 56 entries |
| `SHADER_NAME_PATTERNS_SCORED` | 20 patterns |
| `TEXTURE_MAPS` (total across all shaders) | ~70 mappings |
| `FLOAT_MAPS` (total across all shaders) | ~130 mappings |
| `COLOR_MAPS` (total across all shaders) | ~85 mappings |
| `ALPHA_FIX_PROPERTIES` | 87 properties |
| `BOOLEAN_FLOAT_PROPERTIES` | 55 properties |

### Module Dependencies

```
shader_mapping.py
    ├── re (regex for name patterns)
    ├── logging (debug output)
    └── dataclasses (data structures)
```

No external packages required.

---

## The Shader Detection Challenge

Synty asset packs use **50+ different Unity shaders** that must be mapped to **7 Godot shaders**:

| Godot Shader | Purpose | Common Unity Sources |
|--------------|---------|----------------------|
| `polygon.gdshader` | Props, terrain, characters | PolygonLit, Triplanar, Hologram, Ghost, Generic_Standard |
| `foliage.gdshader` | Trees, grass, plants | Synty Foliage, Leaf Card, SciFiPlant, Wind Animation |
| `water.gdshader` | Rivers, lakes, oceans | Synty Water, Waterfall, Water (Amplify) |
| `crystal.gdshader` | Crystals, glass, gems | Synty Crystal, Synty Glass |
| `particles.gdshader` | Particle effects, fog | Synty Particles, ParticlesLit, ParticlesUnlit |
| `skydome.gdshader` | Sky gradients | Synty Skydome, Skybox_Generic, Aurora |
| `clouds.gdshader` | Volumetric clouds | Synty Clouds |

**Challenges:**

1. **GUID Variance** - The same shader concept may have different GUIDs across packs
2. **Naming Inconsistency** - Materials named "Water_Bucket" might be a metal prop, not water
3. **Property Overlap** - Properties like `_Smoothness` exist in all shader types
4. **Compound Names** - "Dirt_Leaves_Triplanar" contains terms from multiple shader types
5. **Missing Data** - Some materials may lack shader GUIDs entirely (Unity built-in)

The 3-tier detection system addresses all these challenges.

---

## Data Classes

### Color

**Purpose:** RGBA color representation for material properties with alpha-fix helper.

**Definition:**

```python
@dataclass
class Color:
    """RGBA color representation for material properties."""
    r: float = 0.0
    g: float = 0.0
    b: float = 0.0
    a: float = 1.0

    def as_tuple(self) -> tuple[float, float, float, float]:
        """Return color as RGBA tuple for Godot material export."""
        return (self.r, self.g, self.b, self.a)

    def has_rgb(self) -> bool:
        """Check if color has any non-zero RGB component."""
        return self.r != 0.0 or self.g != 0.0 or self.b != 0.0
```

**Attributes:**

| Attribute | Type | Range | Description |
|-----------|------|-------|-------------|
| `r` | `float` | 0.0-1.0+ (HDR) | Red component |
| `g` | `float` | 0.0-1.0+ (HDR) | Green component |
| `b` | `float` | 0.0-1.0+ (HDR) | Blue component |
| `a` | `float` | 0.0-1.0 | Alpha component |

**Methods:**

| Method | Returns | Purpose |
|--------|---------|---------|
| `as_tuple()` | `tuple[float, float, float, float]` | Convert to Godot-compatible tuple |
| `has_rgb()` | `bool` | Check for non-zero RGB (for alpha=0 quirk detection) |

---

### UnityMaterial

**Purpose:** Represents parsed Unity material (input from unity_parser.py).

**Definition:**

```python
@dataclass
class UnityMaterial:
    """Represents a parsed Unity material from a .mat file."""
    name: str
    shader_guid: str
    textures: dict[str, str] = field(default_factory=dict)
    floats: dict[str, float] = field(default_factory=dict)
    colors: dict[str, Color] = field(default_factory=dict)
```

**Note:** The actual `UnityMaterial` from `unity_parser.py` has `tex_envs: dict[str, TextureRef]` instead of `textures`. This class is a simplified representation used in shader_mapping's internal logic. The `map_material()` function accesses `material.tex_envs` directly.

---

### MappedMaterial

**Purpose:** Godot-ready material - the main output of this module.

**Definition:**

```python
@dataclass
class MappedMaterial:
    """Godot-ready material with shader and mapped properties."""
    name: str
    shader_file: str
    textures: dict[str, str] = field(default_factory=dict)
    floats: dict[str, float] = field(default_factory=dict)
    bools: dict[str, bool] = field(default_factory=dict)
    colors: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Material name (sanitized for filesystem) |
| `shader_file` | `str` | Godot shader filename (e.g., `"polygon.gdshader"`) |
| `textures` | `dict[str, str]` | Godot parameter name -> texture filename (no extension) |
| `floats` | `dict[str, float]` | Godot parameter name -> float value |
| `bools` | `dict[str, bool]` | Godot parameter name -> boolean (from boolean-as-float) |
| `colors` | `dict[str, tuple]` | Godot parameter name -> RGBA tuple `(r, g, b, a)` |

**Key Differences from UnityMaterial:**

| Aspect | UnityMaterial | MappedMaterial |
|--------|---------------|----------------|
| Property names | Unity style (`_Base_Texture`) | Godot style (`base_texture`) |
| Textures | GUID references | Resolved filenames |
| Booleans | Stored in floats as 0.0/1.0 | Separate `bools` dict |
| Colors | `Color` objects | RGBA tuples with alpha fixed |
| Defaults | As-is from Unity | Shader-specific defaults applied |

**Example:**

```python
mapped = MappedMaterial(
    name="Tree_Leaves_Mat",
    shader_file="foliage.gdshader",
    textures={
        "leaf_color": "Leaf_Albedo",
        "leaf_normal": "Leaf_Normal",
    },
    floats={
        "leaf_smoothness": 0.1,
        "alpha_clip_threshold": 0.5,
    },
    bools={
        "enable_breeze": True,
        "enable_light_wind": True,
    },
    colors={
        "leaf_base_color": (0.2, 0.5, 0.2, 1.0),
    }
)
```

---

## 3-Tier Shader Detection System

The `detect_shader_type()` function uses a sophisticated 3-tier system to determine the correct Godot shader.

### Tier 1: GUID Lookup

**Highest Priority - Direct Match**

When a Unity material's shader GUID matches a known entry in `SHADER_GUID_MAP`, and that entry maps to a **specific** shader (not the generic polygon), use it immediately.

```python
# Example: Foliage shader GUID
guid = "9b98a126c8d4d7a4baeb81b16e4f7b97"
result = SHADER_GUID_MAP.get(guid)  # -> "foliage.gdshader"
# Immediate return - no further analysis needed
```

**Why GUID detection is preferred:**

1. **Stability** - Unity GUIDs are immutable 32-character hex identifiers
2. **Accuracy** - The GUID definitively identifies the shader regardless of material name
3. **Performance** - Simple dictionary lookup, O(1)

**When GUID detection is skipped:**

- GUID not in map (unknown shader)
- GUID maps to `polygon.gdshader` (generic - may benefit from further analysis)
- Empty GUID string

### Tier 2: Name Pattern Scoring

**Medium Priority - Accumulative Scoring**

When GUID detection is inconclusive, material names are scored against regex patterns.

**Key insight:** Scores **accumulate** across multiple matching patterns. This handles compound names correctly.

```python
# Material: "Crystal_Leaves_01"
# Pattern matches:
#   "crystal" -> crystal.gdshader: +45
#   "leaves"  -> foliage.gdshader: +20
# Result: crystal.gdshader wins (45 > 20)
```

**Score tiers (by specificity):**

| Score Range | Examples | Rationale |
|-------------|----------|-----------|
| 50-60 | `triplanar`, `caustics`, `fresnel` | Technical terms - unambiguous shader indicators |
| 40-49 | `crystal`, `water`, `particle` | Clear material types |
| 30-39 | `glass`, `fog`, `foliage` | Common but fairly specific |
| 20-29 | `tree`, `grass`, `leaf` | Generic vegetation |
| 10-19 | `moss`, `dirt`, `effect` | Very generic, weak signal |

### Tier 3: Property-Based Detection

**Bonus Scoring - Property Analysis**

When floats and colors are provided, the system scores based on shader-specific properties.

**Each matching property adds 10 points** to the associated shader.

**Property groups:**

| Shader | Float Indicators | Color Indicators |
|--------|------------------|------------------|
| water | `_Enable_Shore_Foam`, `_Water_Depth`, `_Caustics_Intensity` | `_Water_Deep_Color`, `_Foam_Color` |
| foliage | `_Enable_Breeze`, `_Leaf_Smoothness`, `_Frosting_Falloff` | `_Leaf_Base_Color`, `_Trunk_Base_Color` |
| crystal | `_Enable_Fresnel`, `_Fresnel_Power`, `_Opacity` | `_Fresnel_Color`, `_Refraction_Color` |
| particles | `_Soft_Power`, `_Camera_Fade_Near` | - |
| skydome | `_Falloff`, `_Offset`, `_Distance` | `_Top_Color`, `_Bottom_Color` |
| clouds | `_Cloud_Speed`, `_Scattering_Multiplier` | `_Scattering_Color` |

**Note:** Some properties like `_Deep_Color` and `_Shallow_Color` are shared between water and crystal, so they're excluded from property-based scoring to avoid false positives.

### Scoring Algorithm

```python
def detect_shader_type(shader_guid, material_name, floats=None, colors=None):
    # TIER 1: GUID lookup
    guid_shader = SHADER_GUID_MAP.get(shader_guid)
    if guid_shader and guid_shader != DEFAULT_SHADER:
        return guid_shader  # Immediate return for specific shaders

    # TIER 2 & 3: Scoring system
    shader_scores = {}

    # Name pattern scoring (all patterns checked)
    for pattern, shader, score in SHADER_NAME_PATTERNS_SCORED:
        if pattern.search(material_name):
            shader_scores[shader] = shader_scores.get(shader, 0) + score

    # Property-based scoring (10 points per matching property)
    if floats or colors:
        # ... water properties check ...
        # ... foliage properties check ...
        # ... crystal properties check ...
        # etc.

    # Select winner
    if shader_scores:
        best_shader = max(shader_scores, key=shader_scores.get)
        best_score = shader_scores[best_shader]

        if best_score >= 20:  # Minimum threshold
            return best_shader

    # Fallback to GUID result or default
    return guid_shader or DEFAULT_SHADER
```

**Minimum threshold of 20 points** prevents weak matches from overriding the default. A single "leaf" mention (20 points) meets the threshold, but a single "moss" mention (15 points) does not.

### Detection Flow Diagram

```
                    +------------------+
                    |   Input Material |
                    +--------+---------+
                             |
                    +--------v---------+
                    |   Shader GUID    |
                    +--------+---------+
                             |
           +-----------------+-----------------+
           |                                   |
           v                                   v
    +------+-------+                   +-------+------+
    | GUID found   |                   | GUID unknown |
    | (specific    |                   | or maps to   |
    | shader)      |                   | polygon      |
    +------+-------+                   +-------+------+
           |                                   |
           v                                   v
    Return shader                    +---------+---------+
    immediately                      |  Scoring System   |
    (foliage,                        +---------+---------+
     water, etc.)                              |
                           +-------------------+-------------------+
                           |                                       |
                           v                                       v
                    +------+-------+                       +-------+------+
                    | Name Pattern |                       | Property     |
                    | Scoring      |                       | Scoring      |
                    | (regex)      |                       | (+10/match)  |
                    +------+-------+                       +-------+------+
                           |                                       |
                           +-------------------+-------------------+
                                               |
                                               v
                                     +---------+---------+
                                     | Sum all scores    |
                                     | per shader type   |
                                     +---------+---------+
                                               |
                                               v
                                     +---------+---------+
                                     | Highest score     |
                                     | >= 20 points?     |
                                     +---------+---------+
                                               |
                           +-------------------+-------------------+
                           |                                       |
                           v                                       v
                    Score >= 20                              Score < 20
                    Return winner                            Return DEFAULT
                                                             (polygon.gdshader)
```

---

## SHADER_GUID_MAP Reference

The `SHADER_GUID_MAP` dictionary maps **56 Unity shader GUIDs** to Godot shader files.

### Core Synty Shaders

These are the primary shaders covering 90%+ of materials:

| GUID | Godot Shader | Unity Shader Name | Notes |
|------|--------------|-------------------|-------|
| `0730dae39bc73f34796280af9875ce14` | polygon | Synty PolygonLit | Main prop shader |
| `9b98a126c8d4d7a4baeb81b16e4f7b97` | foliage | Synty Foliage | Trees/plants |
| `0736e099ec10c9e46b9551b2337d0cc7` | particles | Synty Particles | Effects |
| `19e269a311c45cd4482cf0ac0e694503` | polygon | Synty Triplanar | Terrain mode |
| `436db39b4e2ae5e46a17e21865226b19` | water | Synty Water | Water surfaces |
| `5808064c5204e554c89f589a7059c558` | crystal | Synty Crystal | Crystals/gems |
| `de1d86872962c37429cb628a7de53613` | skydome | Synty Skydome | Sky gradient |
| `4a6c8c23090929241b2a55476a46a9b1` | clouds | Synty Clouds | Volumetric |
| `dfec08fb273e4674bb5398df25a5932c` | foliage | Synty Leaf Card | Billboard leaves |
| `fdea4239d29733541b44cd6960afefcd` | crystal | Synty Glass | Transparent |
| `3b44a38ec6f81134ab0f820ac54d6a93` | polygon | Generic_Standard | Character hair/skin |

### Pack-Specific Shaders

Organized by Synty pack category:

**Skydome Variants:**

| GUID | Description |
|------|-------------|
| `3d532bc2d70158948859b7839127e562` | Skybox_Generic (procedural) |
| `74fa94d128fe4f348889c6f5f182e0e1` | Skydome variant (NatureBiomes) |

**SciFi Shaders:**

| GUID | Description |
|------|-------------|
| `0835602ed30128f4a88a652bf920fcaa` | Polygon_UVScroll (animated UV) |
| `2b5804ffd3081d344bed894a653e3014` | Hologram |
| `5c2ccdfe181d55b42bd5313305f194e4` | SciFiHorror_Screens (CRT) |
| `77e5bdd170fa4a4459dea431aba43e3c` | SciFiHorror_Decals |
| `972cd3fede1c33342b0f52ad57f47d90` | SciFiHorror_BlinkingLights |
| `c48a4461fec61fc45a01e7d6a50e520f` | SciFiPlant -> foliage |

**Horror Shaders:**

| GUID | Description |
|------|-------------|
| `325b924500ba5804aa4b407d80084502` | Neon Shader |
| `0ecc70cac2c8895439f5094ba6660db8` | GrungeTriplanar |
| `5d828b280155912429aa717d34cd8879` | Ghost (transparency + rim) |

**Urban/City Shaders:**

| GUID | Description |
|------|-------------|
| `62e87ad08a1afa642830420bf8e0dd4d` | CyberCity_Triplanar |
| `2a33a166317493947a7be330dcc78a05` | Parallax_Full (interior windows) |
| `e9556606a5f42464fa7dd78d624dc180` | Hologram_01 (urban) |
| `a49be8e7504a48b4fba9b0c2a7fad57b` | EmissiveScroll (LED panels) |
| `1f67b66c29dfd4f45aa8cc07bf5e901a` | EmissiveColourChange |
| `a711ca3b984db6a4e81ec2d50ca4c0ca` | Building (background) |
| `5d014726978e80a43b6178cba929343b` | FlipbookCutout |
| `a7331fc07349b124c8c15d545676f9ed` | Zombies (blood overlay) |

**Dark Fantasy/Magic Shaders:**

| GUID | Description |
|------|-------------|
| `d0be6b296f23e8d459e94b4007017ea0` | Magic Glow/Runes |
| `e8b857c3d7fea464e942e1c1f0940e96` | Magical Portal |
| `e312e3877c798a44dba23093a3417a94` | Liquid/Potion |
| `a2cae5b0e99e16249b9a2163a7087bcb` | Wind Animation (cloth/sail) -> foliage |

**Viking Shaders:**

| GUID | Description |
|------|-------------|
| `d2820334f2975bb47ab3f2fffa1b4cbe` | Aurora (northern lights) -> skydome |
| `b83105300c9f7fb42a6e1b790fd2bd29` | ParticlesLit |
| `00eec7c5cd1f4c6429ffee9a690c3d16` | ParticlesUnlit |

**Elven Realm Shaders:**

| GUID | Description |
|------|-------------|
| `e854bc7dc0cde7044b9000faaf0c4e11` | RockTriplanar |
| `9b1e1d14d7778714391ae095571c3d4f` | WaterFall (animated) -> water |
| `df6b3a02955954d41bb15c534388ba14` | NoFog (celestial) |
| `903fe97c2d85c8147a64932806c92eb1` | Waterfall variant -> water |
| `ca9b700964f37d84a90b00c70d981934` | Aurora (Elven Realm) -> skydome |

**Pro Racer Shaders:**

| GUID | Description |
|------|-------------|
| `ab6da834753539b4989259dbf4bcc39b` | ProRacer_Standard (128 uses) |
| `22e3738818284144eb7ada0a62acca66` | ProRacer_Decal |
| `402ae1c33e4c28c45876b1bc945b77e6` | ProRacer_ParticlesUnlit -> particles |
| `da24369d453e6a547aaa57ebee28fc81` | ProRacer_CutoutFlipbook |
| `8e5d248915e86014095ff0547bc0c755` | ProRacerAdvanced |
| `1bf4a2dc982313347912f313ba25f563` | RoadSHD |

**Character Shaders:**

| GUID | Description |
|------|-------------|
| `e603b0446c7f2804db0c8dd0fb5c1af0` | POLYGON_CustomCharacters (15-zone mask) |

**Legacy/Fallback Shaders:**

| GUID | Description |
|------|-------------|
| `933532a4fcc9baf4fa0491de14d08ed7` | Unity URP Lit (fallback) |
| `56ef766d507df464fb2a1726a99c925f` | Heat Shimmer (AridDesert) -> particles |
| `1ab581f9e0198304996581171522f458` | Water (Amplify) - Nature 2021 -> water |
| `4b0390819f518774fa1a44198298459a` | Foliage (Amplify) - Nature 2021 -> foliage |
| `0000000000000000f000000000000000` | Unity Built-in (default fallback) |

### Adding New GUIDs

**Step 1: Find the GUID**

Extract a Unity package and find the GUID in a `.mat` file:

```yaml
m_Shader: {fileID: 4800000, guid: <NEW_GUID_HERE>, type: 3}
```

**Step 2: Add to SHADER_GUID_MAP**

```python
SHADER_GUID_MAP: dict[str, str] = {
    # ... existing entries ...
    "new_guid_here_32_hex_chars": "appropriate.gdshader",  # Description
}
```

**Step 3: Test**

```bash
python shader_mapping.py
```

Verify the new GUID is recognized in the summary output.

---

## SHADER_NAME_PATTERNS_SCORED Reference

The `SHADER_NAME_PATTERNS_SCORED` list contains **20 regex patterns** with scores for name-based detection.

### Score Tiers

| Tier | Score Range | Description | Example Patterns |
|------|-------------|-------------|------------------|
| High Priority | 50-60 | Technical rendering terms | triplanar, caustics, fresnel |
| Medium-High | 40-49 | Clear material types | crystal, water, particle |
| Medium | 30-39 | Common specific materials | glass, fog, foliage |
| Low-Medium | 20-29 | Generic vegetation | tree, grass, leaf |
| Low | 10-19 | Very generic terms | moss, dirt, effect |

### Complete Pattern Table

| Pattern | Target Shader | Score | Examples Matched |
|---------|---------------|-------|------------------|
| `(?i)triplanar` | polygon | 60 | "Dirt_Triplanar", "TriplanarRock" |
| `(?i)caustics` | water | 55 | "Water_Caustics_01" |
| `(?i)(fresnel\|refractive\|refraction)` | crystal | 55 | "Glass_Fresnel", "Refractive_Mat" |
| `(?i)soft.?particle` | particles | 55 | "SoftParticle_01" |
| `(?i)(skydome\|sky_dome\|skybox\|sky_box)` | skydome | 55 | "Skydome_Day" |
| `(?i)(crystal\|gem\|jewel\|diamond\|ruby\|emerald\|sapphire\|amethyst\|quartz)` | crystal | 45 | "Crystal_Blue", "Ruby_01" |
| `(?i)(water\|ocean\|river\|lake\|waterfall)` | water | 45 | "Water_River_01" |
| `(?i)(particle\|fx_)` | particles | 45 | "Particle_Smoke", "FX_Fire" |
| `(?i)(cloud\|clouds\|sky_cloud)` | clouds | 45 | "Clouds_01" |
| `(?i)(glass\|ice\|transparent\|translucent)` | crystal | 35 | "Glass_Window", "Ice_01" |
| `(?i)(pond\|stream\|liquid\|aqua\|sea)` | water | 35 | "Pond_01", "Liquid_Blue" |
| `(?i)(fog\|mist\|atmosphere)` | clouds | 35 | "Fog_01", "Mist_Mat" |
| `(?i)(spark\|dust\|debris\|smoke\|fire\|rain\|snow\|splash)` | particles | 35 | "Smoke_01", "Fire_Mat" |
| `(?i)(aurora\|sky_gradient)` | skydome | 35 | "Aurora_01" |
| `(?i)(foliage\|vegetation)` | foliage | 35 | "Foliage_Fern" |
| `(?i)(tree\|fern\|grass\|vine\|branch\|willow\|bush\|shrub\|hedge\|bamboo\|koru\|treefern)` | foliage | 25 | "Tree_Oak_01", "Grass_01" |
| `(?i)(leaf\|leaves)` | foliage | 20 | "Leaf_01", "Autumn_Leaves" |
| `(?i)(bark\|trunk\|undergrowth\|plant)` | foliage | 20 | "Bark_01", "Plant_Mat" |
| `(?i)(moss\|dirt)` | polygon | 15 | "Moss_Rock", "Dirt_01" |
| `(?i)(effect\|additive)` | particles | 15 | "Effect_Glow", "Additive_01" |

### Compound Name Resolution

The scoring system handles compound names by summing scores:

**Example 1: "Dirt_Leaves_Triplanar"**

```
Pattern matches:
- "dirt"      -> polygon: +15
- "leaves"    -> foliage: +20
- "triplanar" -> polygon: +60

Final scores:
- polygon:  15 + 60 = 75
- foliage:  20

Winner: polygon.gdshader (75 > 20)
```

This correctly identifies a triplanar terrain material with leaf decals.

**Example 2: "Crystal_Leaves_01"**

```
Pattern matches:
- "crystal"  -> crystal: +45
- "leaves"   -> foliage: +20

Final scores:
- crystal:  45
- foliage:  20

Winner: crystal.gdshader (45 > 20)
```

This correctly identifies a crystallized leaves material.

**Example 3: "Water_Splash_Particles"**

```
Pattern matches:
- "water"    -> water: +45
- "splash"   -> particles: +35
- "particle" -> particles: +45

Final scores:
- water:     45
- particles: 35 + 45 = 80

Winner: particles.gdshader (80 > 45)
```

This correctly identifies splash particles over water.

---

## Property Mapping Dictionaries

### TEXTURE_MAPS

Per-shader dictionaries mapping Unity texture property names to Godot parameter names.

#### TEXTURE_MAP_FOLIAGE (12 entries)

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Leaf_Texture` | `leaf_color` | Main leaf albedo |
| `_Leaf_Normal` | `leaf_normal` | Leaf normal map |
| `_Trunk_Texture` | `trunk_color` | Trunk/bark albedo |
| `_Trunk_Normal` | `trunk_normal` | Trunk normal map |
| `_Leaf_Ambient_Occlusion` | `leaf_ao` | Leaf AO map |
| `_Trunk_Ambient_Occlusion` | `trunk_ao` | Trunk AO map |
| `_Emissive_Mask` | `emissive_mask` | Emission mask |
| `_Emissive_2_Mask` | `emissive_2_mask` | Secondary emission |
| `_Emissive_Pulse_Map` | `emissive_pulse_mask` | Animated emission |
| `_Trunk_Emissive_Mask` | `trunk_emissive_mask` | Trunk emission |
| `_Breeze_Noise_Map` | `breeze_noise_map` | Wind noise |

#### TEXTURE_MAP_POLYGON (47 entries)

The largest texture map, organized by category:

**Base Textures:**

| Unity Property | Godot Parameter | Notes |
|----------------|-----------------|-------|
| `_Base_Texture` | `base_texture` | Primary albedo |
| `_Albedo_Map` | `base_texture` | Alternative name |
| `_BaseMap` | `base_texture` | URP name |
| `_MainTex` | `base_texture` | Built-in name |
| `_MainTexture` | `base_texture` | Legacy name |
| `_Normal_Texture` | `normal_texture` | Normal map |
| `_Normal_Map` | `normal_texture` | Alternative |
| `_BumpMap` | `normal_texture` | Legacy bump |
| `_Emission_Texture` | `emission_texture` | Emission map |
| `_Emission_Map` | `emission_texture` | Alternative |
| `_EmissionMap` | `emission_texture` | URP name |
| `_AO_Texture` | `ao_texture` | Ambient occlusion |
| `_OcclusionMap` | `ao_texture` | URP name |
| `_Metallic_Smoothness_Texture` | `metallic_texture` | PBR packed |
| `_MetallicGlossMap` | `metallic_texture` | URP name |
| `_Metallic_Map` | `metallic_texture` | Pro Racer |

**Triplanar Textures:**

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Triplanar_Texture_Top` | `triplanar_texture_top` |
| `_Triplanar_Texture_Side` | `triplanar_texture_side` |
| `_Triplanar_Texture_Bottom` | `triplanar_texture_bottom` |
| `_Triplanar_Normal_Texture_Top` | `triplanar_normal_top` |
| `_Triplanar_Normal_Texture_Side` | `triplanar_normal_side` |
| `_Triplanar_Normal_Texture_Bottom` | `triplanar_normal_bottom` |
| `_Triplanar_Emission_Texture` | `triplanar_emission_texture` |

**Snow Overlay Textures:**

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Snow_Normal_Texture` | `snow_normal_texture` |
| `_Snow_Metallic_Smoothness_Texture` | `snow_metallic_smoothness` |
| `_Snow_Edge_Noise` | `snow_edge_noise` |

**Character Textures (Modular Fantasy Hero):**

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Hair_Mask` | `hair_mask` |
| `_Skin_Mask` | `skin_mask` |
| `_Mask_01` through `_Mask_05` | `mask_01` through `mask_05` |

**Special Effect Textures:**

| Unity Property | Godot Parameter | Pack |
|----------------|-----------------|------|
| `_Grunge_Map` | `grunge_map` | Horror/Apocalypse |
| `_Blood_Mask` | `blood_mask` | Horror/Zombies |
| `_Blood_Texture` | `blood_texture` | Horror/Zombies |
| `_Rune_Texture` | `rune_texture` | DarkFantasy |
| `_Scan_Line_Map` | `scan_line_map` | SciFi |
| `_LED_Mask_01` | `led_mask` | CyberCity |
| `_Cloth_Mask` | `cloth_mask` | Wind animation |
| `_Overlay_Texture` | `overlay_texture` | Moss/overlay |
| `_Moss` | `overlay_texture` | Legacy moss |
| `_MossTexture` | `overlay_texture` | Alternative |

**Interior Mapping Textures:**

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Floor` | `floor_texture` |
| `_Wall` | `wall_texture` |
| `_Ceiling` | `ceiling_texture` |
| `_Back` | `back_texture` |
| `_Props` | `props_texture` |

#### TEXTURE_MAP_CRYSTAL (7 entries)

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Base_Albedo` | `base_albedo` |
| `_Base_Normal` | `base_normal` |
| `_Refraction_Height` | `refraction_height` |
| `_Refraction_Texture` | `refraction_texture` |
| `_Top_Albedo` | `top_albedo` |
| `_Top_Normal` | `top_normal` |
| `_MainTex` | `base_albedo` |
| `_BumpMap` | `base_normal` |
| `_BaseMap` | `base_albedo` |

#### TEXTURE_MAP_WATER (21 entries)

| Unity Property | Godot Parameter | Notes |
|----------------|-----------------|-------|
| `_Normal_Texture` | `normal_texture` | Water surface normals |
| `_Water_Normal_Texture` | `normal_texture` | Alternative |
| `_WaterNormal` | `normal_texture` | Older naming |
| `_WaterNormal1` | `normal_texture` | Goblin War Camp |
| `_WaterNormal2` | `normal_texture` | Secondary normal |
| `_RipplesNormal` | `normal_texture` | Ripple normals |
| `_Caustics_Flipbook` | `caustics_flipbook` | Animated caustics |
| `_Foam_Noise_Texture` | `noise_texture` | Foam noise |
| `_Foam_Texture` | `noise_texture` | Older naming |
| `_Foam_Texture1` | `noise_texture` | Variant |
| `_FoamMask` | `noise_texture` | Foam masking |
| `_Noise_Texture` | `noise_texture` | Global noise |
| `_Shore_Foam_Noise_Texture` | `shore_foam_noise_texture` | Shore foam |
| `_Shore_Wave_Foam_Noise_Texture` | `shore_foam_noise_texture` | Wave foam |
| `_Scrolling_Texture` | `scrolling_texture` | UV scrolling |

#### TEXTURE_MAP_PARTICLES (3 entries)

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Albedo_Map` | `albedo_map` |
| `_MainTex` | `albedo_map` |
| `_BaseMap` | `albedo_map` |

#### TEXTURE_MAP_SKYDOME & TEXTURE_MAP_CLOUDS

Both are empty - these shaders use procedural generation, no texture inputs.

### FLOAT_MAPS

Per-shader dictionaries mapping Unity float properties to Godot parameters.

#### FLOAT_MAP_FOLIAGE (17 entries)

| Unity Property | Godot Parameter | Description |
|----------------|-----------------|-------------|
| `_Metallic` | `metallic` | Overall metallic |
| `_Smoothness` | `smoothness` | Overall smoothness |
| `_Glossiness` | `smoothness` | Alternative name |
| `_LeafSmoothness` | `leaf_smoothness` | Leaf surface |
| `_Leaf_Smoothness` | `leaf_smoothness` | Alternative |
| `_Leaf_Metallic` | `leaf_metallic` | Leaf metallic |
| `_TrunkSmoothness` | `trunk_smoothness` | Trunk surface |
| `_Trunk_Smoothness` | `trunk_smoothness` | Alternative |
| `_Trunk_Metallic` | `trunk_metallic` | Trunk metallic |
| `_Breeze_Strength` | `breeze_strength` | Light wind |
| `_Light_Wind_Strength` | `light_wind_strength` | Medium wind |
| `_Strong_Wind_Strength` | `strong_wind_strength` | Strong wind |
| `_Wind_Twist_Strength` | `wind_twist_strength` | Twist motion |
| `_Gale_Blend` | `gale_blend` | Storm blend |
| `_Alpha_Clip_Threshold` | `alpha_clip_threshold` | Cutoff |
| `_Normal_Intensity` | `normal_intensity` | Normal strength |
| `_Frosting_Falloff` | `frosting_falloff` | Snow falloff |
| `_Frosting_Height` | `frosting_height` | Snow height |
| `_Leaves_WindAmount` | `breeze_strength` | Legacy wind |
| `_Tree_WindAmount` | `light_wind_strength` | Legacy trunk |
| `_Cutoff` | `alpha_clip_threshold` | Legacy cutoff |
| `_AlphaCutoff` | `alpha_clip_threshold` | URP cutoff |

#### FLOAT_MAP_POLYGON (94 entries)

The largest float map - organized by effect type:

**Surface Properties:**

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Smoothness` | `smoothness` |
| `_Glossiness` | `smoothness` |
| `_Metallic` | `metallic` |
| `_Normal_Intensity` | `normal_intensity` |
| `_Normal_Amount` | `normal_intensity` |
| `_BumpScale` | `normal_intensity` |
| `_AO_Intensity` | `ao_intensity` |
| `_OcclusionStrength` | `ao_intensity` |
| `_Alpha_Clip_Threshold` | `alpha_clip_threshold` |

**Snow Properties:**

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Snow_Level` | `snow_level` |
| `_Snow_Transition` | `snow_transition` |
| `_Snow_Metallic` | `snow_metallic` |
| `_Snow_Smoothness` | `snow_smoothness` |
| `_Snow_Normal_Intensity` | `snow_normal_intensity` |

**Triplanar Properties:**

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Triplanar_Fade` | `triplanar_fade` |
| `_Triplanar_Intensity` | `triplanar_intensity` |
| `_Triplanar_Normal_Intensity_Top` | `triplanar_normal_intensity_top` |
| `_Triplanar_Normal_Intensity_Side` | `triplanar_normal_intensity_side` |
| `_Triplanar_Normal_Intensity_Bottom` | `triplanar_normal_intensity_bottom` |

**Hologram Properties:**

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_HoloLines` | `holo_lines` |
| `_Scroll_Speed` | `scroll_speed` |
| `_Opacity` | `opacity` |
| `_Hologram_Intensity` | `hologram_intensity` |

**Screen/CRT Properties:**

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Screen_Bulge` | `screen_bulge` |
| `_Screen_Flicker_Frequency` | `screen_flicker_frequency` |
| `_Vignette_Amount` | `vignette_amount` |
| `_Pixelation_Amount` | `pixelation_amount` |
| `_CRT_Curve` | `crt_curve` |

**Interior Mapping Properties:**

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_RoomTile` | `room_tile` |
| `_RoomIntensity` | `room_intensity` |
| `_WindowAlpha` | `window_alpha` |
| `_RoomDepth` | `room_depth` |

**Ghost Properties:**

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Transparency` | `transparency` |
| `_RimPower` | `rim_power` |
| `_TransShadow` | `trans_shadow` |
| `_Ghost_Strength` | `ghost_strength` |

**Magic Properties:**

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Glow_Amount` | `glow_amount` |
| `_Glow_Falloff` | `glow_falloff` |
| `_dissolve` | `dissolve` |
| `_twirlstr` | `twirl_strength` |
| `_Rune_Speed` | `rune_speed` |

**Liquid Properties:**

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_liquidamount` | `liquid_amount` |
| `_WobbleX` | `wobble_x` |
| `_WobbleZ` | `wobble_z` |
| `_Wave_Scale` | `wave_scale` |
| `_Foam_Line` | `foam_line` |
| `_Rim_Width` | `rim_width` |

**LED/Neon Properties:**

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Brightness` | `brightness` |
| `_UVScrollSpeed` | `uv_scroll_speed` |
| `_Saturation` | `saturation` |
| `_Neon_Intensity` | `neon_intensity` |
| `_Pulse_Speed` | `pulse_speed` |

#### FLOAT_MAP_CRYSTAL (10 entries)

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Metallic` | `metallic` |
| `_Smoothness` | `smoothness` |
| `_Glossiness` | `smoothness` |
| `_Opacity` | `opacity` |
| `_Fresnel_Power` | `fresnel_power` |
| `_Refraction_Strength` | `refraction_strength` |
| `_Deep_Depth` | `deep_depth` |
| `_Shallow_Depth` | `shallow_depth` |
| `_Normal_Intensity` | `normal_intensity` |
| `_BumpScale` | `normal_intensity` |

#### FLOAT_MAP_WATER (37 entries)

| Unity Property | Godot Parameter | Notes |
|----------------|-----------------|-------|
| `_Smoothness` | `smoothness` | Surface smoothness |
| `_Metallic` | `metallic` | Usually 0 |
| `_Base_Opacity` | `base_opacity` | Water transparency |
| `_Shallows_Opacity` | `shallows_opacity` | Shallow areas |
| `_Maximum_Depth` | `maximum_depth` | Depth fade distance |
| `_Normal_Intensity` | `normal_intensity` | Wave normal strength |
| `_Shore_Wave_Speed` | `shore_wave_speed` | Shore animation |
| `_Ocean_Wave_Height` | `ocean_wave_height` | Vertex displacement |
| `_Ocean_Wave_Speed` | `ocean_wave_speed` | Open water waves |
| `_Distortion_Strength` | `distortion_strength` | Refraction |
| `_Deep_Height` | `deep_height` | Deep zone start |
| `_Very_Deep_Height` | `very_deep_height` | Abyss zone start |
| `_Depth_Distance` | `depth_distance` | Overall depth scale |
| `_Water_Depth` | `water_depth` | Alternative |
| `_ShallowFalloff` | `shallow_intensity` | Goblin War Camp |
| `_OverallFalloff` | `base_opacity` | Alternative |
| `_OpacityFalloff` | `shallows_opacity` | Alternative |
| `_Shore_Foam_Intensity` | `shore_foam_intensity` | Foam strength |
| `_FoamShoreline` | `shore_foam_intensity` | Goblin War Camp |
| `_FoamDepth` | `shore_foam_intensity` | Threshold |
| `_FoamFalloff` | `ocean_foam_opacity` | Fade control |
| `_Caustics_Intensity` | `caustics_intensity` | Caustic brightness |
| `_CausticDepthFade` | `caustics_intensity` | Depth-based |
| `_CausticScale` | `caustics_scale` | Pattern scale |
| `_CausticSpeed` | `caustics_speed` | Animation speed |
| `_Shallow_Intensity` | `shallow_intensity` | Shallow brightness |
| `_FresnelPower` | `fresnel_power` | Waterfall fresnel |
| `_UVScrollSpeed` | `uv_scroll_speed` | Waterfall animation |

#### FLOAT_MAP_PARTICLES (13 entries)

| Unity Property | Godot Parameter | Notes |
|----------------|-----------------|-------|
| `_Alpha_Clip_Treshold` | `alpha_clip_threshold` | Unity typo preserved |
| `_Alpha_Clip_Threshold` | `alpha_clip_threshold` | Correct spelling |
| `_Cutoff` | `alpha_clip_threshold` | Legacy |
| `_AlphaCutoff` | `alpha_clip_threshold` | URP |
| `_Soft_Power` | `soft_power` | Soft blend power |
| `_Soft_Distance` | `soft_distance` | Soft blend range |
| `_Camera_Fade_Near` | `camera_fade_near` | Near fade |
| `_Camera_Fade_Far` | `camera_fade_far` | Far fade |
| `_Camera_Fade_Smoothness` | `camera_fade_smoothness` | Fade curve |
| `_View_Edge_Power` | `view_edge_power` | Edge compensation |
| `_Fog_Density` | `fog_density` | Volumetric density |

#### FLOAT_MAP_SKYDOME (3 entries)

| Unity Property | Godot Parameter | Notes |
|----------------|-----------------|-------|
| `_Falloff` | `falloff` | Gradient curve |
| `_Offset` | `offset` | Horizon offset |
| `_Distance` | `distance_` | Trailing underscore avoids reserved word |

#### FLOAT_MAP_CLOUDS (12 entries)

| Unity Property | Godot Parameter | Notes |
|----------------|-----------------|-------|
| `_Light_Intensity` | `light_intensity` | Cloud lighting |
| `_Fresnel_Power` | `fresnel_power` | Edge highlight |
| `_Fog_Density` | `fog_density` | Fog blending |
| `_Scattering_Multiplier` | `scattering_multiplier` | Light scattering |
| `_Cloud_Speed` | `cloud_speed` | Movement |
| `_Cloud_Strength` | `cloud_strength` | Density |
| `_CloudCoverage` | `cloud_strength` | SciFi Space |
| `_CloudPower` | `cloud_strength` | Alternative |
| `_CloudSpeed` | `cloud_speed` | Alternative |
| `_Cloud_Contrast` | `scattering_multiplier` | Alternative |
| `_Cloud_Falloff` | `fog_density` | Alternative |
| `_Aurora_Speed` | `aurora_speed` | Vikings/ElvenRealm |
| `_Aurora_Intensity` | `aurora_intensity` | Aurora brightness |
| `_Aurora_Scale` | `aurora_scale` | Aurora size |

### COLOR_MAPS

Per-shader dictionaries mapping Unity color properties to Godot parameters.

#### COLOR_MAP_FOLIAGE (12 entries)

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Color` | `color_tint` |
| `_Color_Tint` | `color_tint` |
| `_BaseColor` | `color_tint` |
| `_ColorTint` | `color_tint` |
| `_Leaf_Base_Color` | `leaf_base_color` |
| `_Trunk_Base_Color` | `trunk_base_color` |
| `_Leaf_Noise_Color` | `leaf_noise_color` |
| `_Trunk_Noise_Color` | `trunk_noise_color` |
| `_Emissive_Color` | `emissive_color` |
| `_Emissive_2_Color` | `emissive_2_color` |
| `_Trunk_Emissive_Color` | `trunk_emissive_color` |
| `_Frosting_Color` | `frosting_color` |

#### COLOR_MAP_POLYGON (45 entries)

**Base Colors:**

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Color_Tint` | `color_tint` |
| `_Color` | `color_tint` |
| `_BaseColor` | `color_tint` |
| `_BaseColour` | `color_tint` |
| `_Emission_Color` | `emission_color` |
| `_EmissionColor` | `emission_color` |
| `_Snow_Color` | `snow_color` |

**Character Colors:**

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Hair_Color` | `hair_color` |
| `_Skin_Color` | `skin_color` |

**Hologram/Neon Colors:**

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Neon_Colour_01` | `neon_color_01` |
| `_Neon_Colour_02` | `neon_color_02` |
| `_Hologram_Color` | `hologram_color` |

**Effect Colors:**

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_RimColor` | `rim_color` |
| `_Dust_Colour` | `dust_color` |
| `_Glow_Colour` | `glow_color` |
| `_Glow_Tint` | `glow_tint` |
| `_Liquid_Color` | `liquid_color` |
| `_BloodColor` | `blood_color` |
| `_Blood_Color` | `blood_color` |

**Modular Fantasy Hero (15-Zone System):**

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Color_Primary` | `color_primary` |
| `_Color_Secondary` | `color_secondary` |
| `_Color_Tertiary` | `color_tertiary` |
| `_Color_Metal_Primary` | `color_metal_primary` |
| `_Color_Metal_Secondary` | `color_metal_secondary` |
| `_Color_Metal_Dark` | `color_metal_dark` |
| `_Color_Leather_Primary` | `color_leather_primary` |
| `_Color_Leather_Secondary` | `color_leather_secondary` |
| `_Color_Skin` | `color_skin` |
| `_Color_Hair` | `color_hair` |
| `_Color_Eyes` | `color_eyes` |
| `_Color_Stubble` | `color_stubble` |
| `_Color_Scar` | `color_scar` |
| `_Color_BodyArt` | `color_bodyart` |

#### COLOR_MAP_CRYSTAL (9 entries)

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Base_Color` | `base_color` |
| `_Base_Color_Multiplier` | `base_color` |
| `_Top_Color_Multiplier` | `top_color` |
| `_Deep_Color` | `deep_color` |
| `_Shallow_Color` | `shallow_color` |
| `_Fresnel_Color` | `fresnel_color` |
| `_Refraction_Color` | `refraction_color` |

#### COLOR_MAP_WATER (27 entries)

| Unity Property | Godot Parameter | Notes |
|----------------|-----------------|-------|
| `_Shallow_Color` | `shallow_color` | Near surface |
| `_Deep_Color` | `deep_color` | Deep water |
| `_Very_Deep_Color` | `very_deep_color` | Abyss |
| `_ShallowColour` | `shallow_color` | British spelling |
| `_DeepColour` | `deep_color` | British spelling |
| `_VeryDeepColour` | `very_deep_color` | British spelling |
| `_Foam_Color` | `foam_color` | Wave foam |
| `_Caustics_Color` | `caustics_color` | Caustics tint |
| `_CausticColour` | `caustics_color` | British spelling |
| `_Shore_Foam_Color_Tint` | `shore_foam_color_tint` | Shore foam |
| `_Shore_Wave_Color_Tint` | `shore_wave_color_tint` | Shore waves |
| `_FoamEmitColour` | `shore_foam_color_tint` | Goblin War Camp |
| `_DepthGlowColour` | `very_deep_color` | Deep glow |
| `_Color` | `color_tint` | General tint |
| `_Color_Tint` | `color_tint` | Alternative |
| `_BaseColor` | `color_tint` | URP name |
| `_WaterDeepColor` | `deep_color` | Legacy |
| `_WaterShallowColor` | `shallow_color` | Legacy |
| `_Water_Deep_Color` | `deep_color` | Alternative |
| `_Water_Shallow_Color` | `shallow_color` | Alternative |
| `_Water_Near_Color` | `shallow_color` | Camera-based |
| `_Water_Far_Color` | `deep_color` | Camera-based |
| `_WaterColour` | `water_color` | Waterfall |
| `_FresnelColour` | `fresnel_color` | Waterfall fresnel |

#### COLOR_MAP_PARTICLES (6 entries)

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Base_Color` | `base_color` |
| `_Color` | `base_color` |
| `_Color_Tint` | `base_color` |
| `_BaseColor` | `base_color` |
| `_Fog_Color` | `fog_color` |
| `_EmissionColor` | `emission_color` |

#### COLOR_MAP_SKYDOME (2 entries)

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Top_Color` | `top_color` |
| `_Bottom_Color` | `bottom_color` |

#### COLOR_MAP_CLOUDS (8 entries)

| Unity Property | Godot Parameter |
|----------------|-----------------|
| `_Top_Color` | `top_color` |
| `_Base_Color` | `base_color` |
| `_Fresnel_Color` | `fresnel_color` |
| `_Scattering_Color` | `scattering_color` |
| `_CloudColor` | `top_color` |
| `_Aurora_Color_01` | `aurora_color_01` |
| `_Aurora_Color_02` | `aurora_color_02` |

---

## Unity Quirk Handling

### Alpha=0 Color Fix

**The Problem:**

Unity often stores colors with `alpha=0` even when the material is fully opaque. This happens because:

1. Some Unity shaders ignore alpha for certain properties (tints, base colors)
2. Default material templates in some Synty packs have alpha=0
3. Unity's color picker can default to alpha=0
4. Copy-paste between materials preserves incorrect alpha

**The Fix:**

The `ALPHA_FIX_PROPERTIES` set (87 entries) identifies color properties that should have alpha fixed.

When a color property:
- Is in `ALPHA_FIX_PROPERTIES`
- Has non-zero RGB values (`color.has_rgb()`)
- Has exactly `alpha=0`
- Material is NOT transparent (`_Mode < 1.0`)

Then alpha is set to 1.0.

**Categories of alpha-fix properties:**

| Category | Examples |
|----------|----------|
| Crystal/Refractive | `_Base_Color`, `_Deep_Color`, `_Shallow_Color`, `_Fresnel_Color` |
| Water | `_Water_Deep_Color`, `_Foam_Color`, `_Caustics_Color` |
| Foliage | `_Leaf_Base_Color`, `_Trunk_Base_Color`, `_Emissive_Color` |
| Neon/Glow | `_Neon_Colour_01`, `_Glow_Colour`, `_Hologram_Color` |
| Blood/Overlay | `_BloodColor`, `_Dust_Colour` |
| General | `_Color`, `_BaseColor`, `_Color_Tint` |
| Skydome/Clouds | `_Top_Color`, `_Bottom_Color`, `_Scattering_Color` |
| Character | All 15-zone colors from Modular Fantasy Hero |

**Transparent material exception:**

Materials with `_Mode >= 1.0` skip the alpha fix entirely (Cutout=1, Fade=2, Transparent=3). Their low alpha values are intentional.

### Boolean-as-Float Conversion

**The Problem:**

Unity stores boolean toggles as floats (0.0 = false, 1.0 = true) because the material property system lacks a native boolean type.

**The Fix:**

The `BOOLEAN_FLOAT_PROPERTIES` set (55 entries) identifies properties that should be converted to booleans.

**Conversion logic:**

```python
for unity_name, value in floats.items():
    if unity_name in BOOLEAN_FLOAT_PROPERTIES:
        godot_name = float_map.get(unity_name) or _unity_to_godot_name(unity_name)
        bools[godot_name] = value != 0.0
```

**Categories of boolean-as-float properties:**

| Category | Examples |
|----------|----------|
| Foliage Wind | `_Enable_Breeze`, `_Enable_Light_Wind`, `_Enable_Strong_Wind`, `_Enable_Wind_Twist` |
| Foliage Effects | `_Enable_Frosting`, `_Wind_Enabled` |
| Legacy Wind | `_Leaves_Wave`, `_Tree_Wave` |
| Crystal/Glass | `_Enable_Fresnel`, `_Enable_Depth`, `_Enable_Refraction`, `_Enable_Triplanar` |
| Polygon Features | `_Enable_Triplanar_Texture`, `_Enable_Snow`, `_Enable_Emission`, `_Enable_Normals`, `_AlphaClip` |
| Polygon Effects | `_Enable_Hologram`, `_Enable_Ghost`, `_Enable_Wave`, `_Enable_Parallax`, `_Enable_AO` |
| Water Features | `_Enable_Shore_Wave_Foam`, `_Enable_Shore_Foam`, `_Enable_Ocean_Waves`, `_Enable_Caustics`, `_Enable_Distortion` |
| Waterfall | `_VertexOffset_Toggle` |
| Particles | `_Enable_Soft_Particles`, `_Enable_Camera_Fade`, `_Enable_Scene_Fog` |
| Skydome | `_Enable_UV_Based` |
| Clouds | `_Use_Environment_Override`, `_Enable_Fog`, `_Enable_Scattering` |

---

## Shader-Specific Defaults

The `SHADER_DEFAULTS` dictionary provides sensible defaults when Unity values are missing.

```python
SHADER_DEFAULTS = {
    "crystal.gdshader": {
        "opacity": 0.7,  # Crystals should be translucent, not fully opaque
    },
    "foliage.gdshader": {
        "leaf_smoothness": 0.1,   # Matte leaves
        "trunk_smoothness": 0.15,  # Slightly rough bark
        "leaf_metallic": 0.0,
        "trunk_metallic": 0.0,
    },
    "water.gdshader": {
        "smoothness": 0.95,  # Very smooth reflective surface
        "metallic": 0.0,
    },
    "polygon.gdshader": {
        "smoothness": 0.5,  # Middle-ground default
        "metallic": 0.0,
    },
}
```

**Why defaults are needed:**

1. Unity materials may omit properties that have shader defaults
2. Some Unity defaults don't translate well to Godot's rendering
3. Certain effects need sensible starting values

**Application:**

Defaults are only applied when the property is NOT present in the Unity material. Explicit Unity values are never overridden.

---

## Shader-Specific Property Validation

The `SHADER_SPECIFIC_PROPERTIES` dictionary validates that materials actually need specialized shaders.

**The Problem:**

A material named "Water_Bucket_Prop" might be a metal bucket (polygon shader), not water. Name pattern matching alone can produce false positives.

**The Fix:**

After name-based detection suggests a specialized shader, `validate_shader_properties()` checks if the material has at least one property specific to that shader.

```python
SHADER_SPECIFIC_PROPERTIES = {
    "foliage.gdshader": {
        "textures": {"_Leaf_Texture", "_Trunk_Texture", "_Breeze_Noise_Map", ...},
        "floats": {"_Breeze_Strength", "_Leaf_Smoothness", ...},
        "colors": {"_Leaf_Base_Color", "_Trunk_Base_Color"},
    },
    "crystal.gdshader": {
        "textures": {"_Refraction_Height", "_Top_Albedo", ...},
        "floats": {"_Fresnel_Power", "_Refraction_Strength", ...},
        "colors": {"_Deep_Color", "_Shallow_Color", "_Fresnel_Color"},
    },
    "water.gdshader": {
        "textures": {"_Caustics_Flipbook", "_Foam_Noise_Texture", ...},
        "floats": {"_Maximum_Depth", "_Shore_Wave_Speed", ...},
        "colors": {"_Shallow_Color", "_Deep_Color", "_Foam_Color"},
    },
    # ... etc
}
```

**Validation logic:**

```python
def validate_shader_properties(shader_file: str, material: UnityMaterial) -> bool:
    if shader_file == "polygon.gdshader":
        return True  # Always valid

    specific = SHADER_SPECIFIC_PROPERTIES.get(shader_file)
    if not specific:
        return True  # Unknown shader, don't block

    # Check if ANY specific property exists
    for tex_name in material.tex_envs:
        if tex_name in specific["textures"]:
            return True
    for float_name in material.floats:
        if float_name in specific["floats"]:
            return True
    for color_name in material.colors:
        if color_name in specific["colors"]:
            return True

    return False  # No specific properties found
```

If validation fails, the material falls back to `polygon.gdshader`.

---

## Public API Functions

### detect_shader_type()

**Purpose:** Detect the appropriate Godot shader for a Unity material.

**Signature:**

```python
def detect_shader_type(
    shader_guid: str,
    material_name: str,
    floats: dict[str, float] | None = None,
    colors: dict[str, tuple[float, float, float, float]] | None = None,
) -> str
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `shader_guid` | `str` | Unity shader GUID (32-char hex, can be empty) |
| `material_name` | `str` | Material name for pattern matching |
| `floats` | `dict[str, float]` | Optional float properties for property-based scoring |
| `colors` | `dict[str, tuple]` | Optional colors as RGBA tuples for property-based scoring |

**Returns:** Godot shader filename (e.g., `"foliage.gdshader"`). Always returns a valid filename, never None.

**Example:**

```python
# Tier 1: GUID lookup
shader = detect_shader_type(
    "9b98a126c8d4d7a4baeb81b16e4f7b97",  # Foliage GUID
    "AnyMaterialName"
)  # -> "foliage.gdshader"

# Tier 2+3: Scoring
shader = detect_shader_type(
    "unknown_guid",
    "Crystal_Mat_01",
    floats={"_Enable_Fresnel": 1.0, "_Fresnel_Power": 2.5},
    colors={}
)  # -> "crystal.gdshader" (name: 45 + properties: 20 = 65 points)

# Default fallback
shader = detect_shader_type(
    "unknown_guid",
    "GenericMaterial"
)  # -> "polygon.gdshader"
```

### map_material()

**Purpose:** Convert a Unity material to Godot format. Main entry point.

**Signature:**

```python
def map_material(
    material: UnityMaterial,
    texture_guid_map: dict[str, str],
    override_shader: str | None = None,
) -> MappedMaterial
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `material` | `UnityMaterial` | Parsed Unity material from unity_parser |
| `texture_guid_map` | `dict[str, str]` | Maps texture GUIDs to filenames (no extension) |
| `override_shader` | `str | None` | Optional shader to use (skips detection) |

**Returns:** `MappedMaterial` ready for .tres generation.

**Conversion Steps:**

1. **Detect shader type** (or use override)
2. **Validate shader properties** (fall back to polygon if no specific properties)
3. **Get property maps** for the detected shader
4. **Map textures** (resolve GUIDs to filenames)
5. **Map floats** (convert names, extract booleans)
6. **Map colors** (convert names, fix alpha=0)
7. **Apply defaults**

**Example:**

```python
from unity_parser import parse_material_bytes
from shader_mapping import map_material

# Parse Unity material
unity_mat = parse_material_bytes(mat_bytes)

# Map to Godot format
texture_guid_map = {"abc123...": "Texture_01", "def456...": "Texture_02_N"}
godot_mat = map_material(unity_mat, texture_guid_map)

print(f"Shader: {godot_mat.shader_file}")
print(f"Textures: {godot_mat.textures}")
print(f"Floats: {godot_mat.floats}")
print(f"Bools: {godot_mat.bools}")
print(f"Colors: {godot_mat.colors}")
```

### determine_shader()

**Purpose:** Simplified shader detection for MaterialList-based flow.

**Signature:**

```python
def determine_shader(
    material_name: str,
    uses_custom_shader: bool,
) -> tuple[str, bool]
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `material_name` | `str` | Material name |
| `uses_custom_shader` | `bool` | From MaterialList.txt - True if custom shader |

**Returns:** Tuple of `(shader_filename, matched)`:
- `shader_filename`: The Godot shader to use
- `matched`: False if material needs manual review (unmatched custom shader)

**Logic:**

1. If `uses_custom_shader=False` -> return `("polygon.gdshader", True)`
2. If `uses_custom_shader=True` -> try name pattern matching
3. If match found -> return `(shader, True)`
4. If no match -> return `("polygon.gdshader", False)` (needs review)

**Example:**

```python
# Standard material
shader, matched = determine_shader("Ground_Mat", uses_custom_shader=False)
# -> ("polygon.gdshader", True)

# Custom shader with good name
shader, matched = determine_shader("Crystal_Mat_01", uses_custom_shader=True)
# -> ("crystal.gdshader", True)

# Custom shader with unclear name
shader, matched = determine_shader("UnknownMat", uses_custom_shader=True)
# -> ("polygon.gdshader", False)  # Needs manual review
```

### create_placeholder_material()

**Purpose:** Create placeholder for missing material references.

**Signature:**

```python
def create_placeholder_material(material_name: str) -> MappedMaterial
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `material_name` | `str` | Name of the missing material |

**Returns:** `MappedMaterial` with shader detected from name and appropriate defaults.

**Use case:** When mesh_material_mapping.json references a material that doesn't exist in the Unity package (e.g., shared materials from other packs).

**Example:**

```python
placeholder = create_placeholder_material("Crystal_Blue_01")
# -> MappedMaterial(
#     name="Crystal_Blue_01",
#     shader_file="crystal.gdshader",
#     textures={},  # No textures
#     floats={"opacity": 0.7},
#     bools={"enable_fresnel": True},
#     colors={"base_color": (0.5, 0.7, 1.0, 1.0)}  # Light blue
# )
```

---

## Helper Functions

### _fix_alpha_zero()

**Signature:**

```python
def _fix_alpha_zero(
    color: Color,
    property_name: str,
    floats: dict[str, float] | None = None
) -> Color
```

Fixes Unity's alpha=0 quirk for color properties in `ALPHA_FIX_PROPERTIES`. Skips fix for transparent materials (`_Mode >= 1.0`).

### _convert_boolean_floats()

**Signature:**

```python
def _convert_boolean_floats(
    floats: dict[str, float],
    float_map: dict[str, str]
) -> tuple[dict[str, float], dict[str, bool]]
```

Splits boolean-as-float properties from regular floats. Returns `(remaining_floats, extracted_bools)`.

### _unity_to_godot_name()

**Signature:**

```python
def _unity_to_godot_name(unity_name: str) -> str
```

Converts Unity property names to Godot snake_case style.

Examples:
- `"_Enable_Breeze"` -> `"enable_breeze"`
- `"_BaseColor"` -> `"base_color"`

### _apply_defaults()

**Signature:**

```python
def _apply_defaults(material: MappedMaterial) -> MappedMaterial
```

Applies shader-specific defaults from `SHADER_DEFAULTS`. Only applies when property is missing.

### validate_shader_properties()

**Signature:**

```python
def validate_shader_properties(shader_file: str, material: UnityMaterial) -> bool
```

Checks if material has properties justifying a specialized shader. Returns True for polygon (always valid) and unknown shaders.

---

## Utility Functions

### get_all_shader_guids()

```python
def get_all_shader_guids() -> set[str]
```

Returns all known shader GUIDs from `SHADER_GUID_MAP`.

### get_shader_for_guid()

```python
def get_shader_for_guid(guid: str) -> str | None
```

Simple GUID lookup without fallback detection.

### get_texture_property_mapping()

```python
def get_texture_property_mapping(shader_file: str) -> dict[str, str]
```

Get texture mapping for a shader.

### get_float_property_mapping()

```python
def get_float_property_mapping(shader_file: str) -> dict[str, str]
```

Get float mapping for a shader.

### get_color_property_mapping()

```python
def get_color_property_mapping(shader_file: str) -> dict[str, str]
```

Get color mapping for a shader.

### print_shader_mapping_summary()

```python
def print_shader_mapping_summary() -> None
```

Prints summary statistics to stdout.

---

## Error Handling

The module uses graceful degradation:

| Scenario | Behavior |
|----------|----------|
| Unknown GUID | Falls through to name pattern scoring |
| No pattern match | Falls back to polygon.gdshader |
| Property validation fails | Falls back to polygon.gdshader |
| Texture GUID not in map | Skips that texture, logs debug |
| Float parse error | Skips that float |
| Color parse error | Skips that color |
| Alpha fix skip | Logs debug for transparent materials |

**No exceptions are raised** - the module always returns a valid `MappedMaterial`.

---

## CLI Testing Interface

The module includes a CLI for testing:

```bash
python shader_mapping.py
```

**Output:**

```
============================================================
Shader Mapping Summary
============================================================
Known shader GUIDs: 56
Name fallback patterns: 20
Alpha-fix properties: 87
Boolean-float properties: 55

GUIDs by target shader:
  polygon.gdshader: 28
  foliage.gdshader: 6
  water.gdshader: 5
  particles.gdshader: 5
  skydome.gdshader: 5
  crystal.gdshader: 2
  clouds.gdshader: 1
============================================================

Shader Detection Tests:
  TestMaterial (GUID: 0730dae3...) -> polygon.gdshader
  TreeMaterial (GUID: 9b98a126...) -> foliage.gdshader
  Crystal_Mat_01 (GUID: unknown_g...) -> crystal.gdshader
  GenericMaterial (GUID: unknown_g...) -> polygon.gdshader
  SomeMaterial (GUID: unknown_g...) -> crystal.gdshader
```

---

## Code Examples

### Basic Shader Detection

```python
from shader_mapping import detect_shader_type

# GUID-based detection
shader = detect_shader_type(
    shader_guid="9b98a126c8d4d7a4baeb81b16e4f7b97",
    material_name="Tree_Leaves"
)
print(f"Detected: {shader}")  # foliage.gdshader

# Name-based detection
shader = detect_shader_type(
    shader_guid="",
    material_name="Crystal_Gem_Blue_01"
)
print(f"Detected: {shader}")  # crystal.gdshader

# Property-based detection
shader = detect_shader_type(
    shader_guid="",
    material_name="SomeMaterial",
    floats={"_Enable_Shore_Foam": 1.0, "_Water_Depth": 10.0},
    colors={"_Deep_Color": (0.0, 0.2, 0.4, 1.0)}
)
print(f"Detected: {shader}")  # water.gdshader
```

### Full Material Conversion

```python
from pathlib import Path
from unity_parser import parse_material_bytes
from unity_package import extract_unitypackage
from shader_mapping import map_material

# Extract package
package_path = Path("C:/Downloads/POLYGON_Nature.unitypackage")
guid_map = extract_unitypackage(package_path)

# Parse a material
mat_guid = "abc123..."
mat_bytes = guid_map.guid_to_content[mat_guid]
unity_mat = parse_material_bytes(mat_bytes)

# Convert to Godot
godot_mat = map_material(unity_mat, guid_map.texture_guid_to_name)

print(f"Name: {godot_mat.name}")
print(f"Shader: {godot_mat.shader_file}")
print(f"Textures: {len(godot_mat.textures)}")
print(f"Floats: {godot_mat.floats}")
print(f"Bools: {godot_mat.bools}")
print(f"Colors: {len(godot_mat.colors)}")
```

### Scoring Debug Example

```python
import logging
from shader_mapping import detect_shader_type

# Enable debug logging to see scoring
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")

# Test compound name
shader = detect_shader_type(
    shader_guid="",
    material_name="Dirt_Leaves_Triplanar_Mat",
    floats={"_Triplanar_Intensity": 1.0},
    colors={}
)

# Debug output will show:
#   Name pattern 'triplanar' adds 60 to polygon.gdshader (total: 60)
#   Name pattern 'leaves' adds 20 to foliage.gdshader (total: 20)
#   Name pattern 'dirt' adds 15 to polygon.gdshader (total: 75)
#   Shader detected via SCORING -> polygon.gdshader (score: 75)
```

---

## Notes for Doc Cleanup

After reviewing the existing documentation, here are findings for consolidation:

### Redundant Information

1. **`docs/api/shader_mapping.md`** (799 lines):
   - Duplicates detection flow diagram
   - Duplicates scoring examples
   - Duplicates property mapping tables (partial)
   - **Recommendation:** Keep as concise API reference, remove duplicated explanations, link to this step doc

2. **`docs/api/constants.md`** (1063 lines):
   - Complete listing of all constants with descriptions
   - Overlaps significantly with property mapping sections here
   - **Recommendation:** Keep as exhaustive reference, this doc provides conceptual understanding

3. **`docs/shader-reference.md`** (605 lines):
   - Focuses on Godot shader features (what each shader does)
   - Minimal overlap - complementary to this doc
   - **Recommendation:** Keep as-is, add cross-reference

### Outdated Information

1. **`docs/api/shader_mapping.md`**:
   - References `synty-converter-BLUE/shader_mapping.py` instead of `synty-converter/shader_mapping.py`
   - States "114 total" GUIDs - actual count is 56

2. **`docs/api/constants.md`**:
   - States "81 entries" in SHADER_GUID_MAP - actual count is 56
   - States "18 pattern groups" - correct, but table shows 20 patterns (some combined)

5. **Summary statistics inconsistent across docs**:
   - Various docs cite different counts for BOOLEAN_FLOAT_PROPERTIES (50 vs 55)
   - ALPHA_FIX_PROPERTIES counts vary (75 vs 77 vs 87)

### Information to Incorporate

1. **`docs/unity-reference.md`** has property name history/alternatives that could be mentioned here as context

2. **`docs/shader-reference.md`** Godot shader details should be cross-referenced for what each mapped property actually does

### Suggested Cross-References

Add to the following docs:

1. **`docs/architecture.md`** Step 6 section:
   - Add: "See [Step 6: Shader Detection](steps/06-shader-detection.md) for detailed implementation."

2. **`docs/api/shader_mapping.md`**:
   - Add at top: "For detailed implementation documentation, see [Step 6: Shader Detection](../steps/06-shader-detection.md)."

3. **`docs/api/constants.md`**:
   - Add: "For conceptual understanding of how these constants are used, see [Step 6: Shader Detection](../steps/06-shader-detection.md)."

4. **`docs/shader-reference.md`**:
   - Add: "For how Unity materials are mapped to these shaders, see [Step 6: Shader Detection](steps/06-shader-detection.md)."

### Counts to Verify and Standardize

Run `python shader_mapping.py` to get accurate counts:

```
Known shader GUIDs: 56
Name fallback patterns: 20
Alpha-fix properties: 87
Boolean-float properties: 55
```

Update all docs to use these consistent values.

---

*Last Updated: 2026-01-31*
*Based on shader_mapping.py (2,339 lines)*
