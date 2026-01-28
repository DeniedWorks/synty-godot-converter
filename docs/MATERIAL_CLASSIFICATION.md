# Material Classification Logic

This document describes how the Synty Converter v2 classifies Unity materials into different shader types for Godot.

## Overview

The classifier uses a priority-based system that first checks Unity material metadata (from .mat YAML files), then falls back to name pattern matching.

## Classification Priority

Materials are checked in this order. The first matching condition determines the type:

| Priority | Type | Detection Method |
|----------|------|------------------|
| 1 | FOLIAGE | Metadata: has foliage textures or wind properties |
| 2 | EMISSIVE | Metadata: emission enabled with texture/color |
| 3 | GLASS | Metadata: transparent render type + name check |
| 4 | WATER | Name: contains water-related keywords |
| 5 | STANDARD | Default fallback |

Additional types detected by name patterns only:
- SKY (sky, skydome, skybox)
- CLOUDS (cloud, fog, mist, smoke)
- PARTICLES (particle, fx_, effect)

## Priority 1: FOLIAGE

**Detection via Unity Metadata:**

A material is classified as FOLIAGE if it has ANY of these properties:

```yaml
# Texture properties (in m_TexEnvs section)
_Leaf_Texture    # Leaf/foliage texture slot
_Trunk_Texture   # Bark/trunk texture slot

# Float properties (in m_Floats section)
_Enable_Breeze: 1      # Gentle wind animation
_Enable_Light_Wind: 1  # Light wind animation
_Wind_Enabled: 1       # Wind master toggle
```

**Code Implementation:**
```python
@property
def has_foliage_properties(self) -> bool:
    return (
        "_Leaf_Texture" in self.textures or
        "_Trunk_Texture" in self.textures or
        self.floats.get("_Enable_Breeze", 0) == 1 or
        self.floats.get("_Enable_Light_Wind", 0) == 1 or
        self.floats.get("_Wind_Enabled", 0) == 1
    )
```

**Name Pattern Fallback:**
```
(?i)leaf, (?i)tree, (?i)plant, (?i)grass, (?i)bush,
(?i)hedge, (?i)vine, (?i)flower, (?i)fern, (?i)moss,
(?i)bamboo, (?i)cherry.*blossom, (?i)foliage, (?i)shrub
```

**Shader Used:** `foliage.gdshader`

**Generated Parameters:**
```tres
shader_parameter/leaf_color = ExtResource("2")
shader_parameter/trunk_color = ExtResource("3")
shader_parameter/use_global_weather_controller = true
shader_parameter/enable_breeze = true
shader_parameter/breeze_strength = 0.2
shader_parameter/enable_light_wind = true
shader_parameter/light_wind_strength = 0.2
```

## Priority 2: EMISSIVE

**Detection via Unity Metadata:**

A material is classified as EMISSIVE if it has ANY of these:

```yaml
# Float property explicitly enabling emission
_Enable_Emission: 1

# OR has an emission texture
_Emission_Map: {fileID: ..., guid: abc123}

# OR has a non-black emission color
_Emission_Color: {r: 1.0, g: 0.8, b: 0.4, a: 1.0}
```

**Code Implementation:**
```python
@property
def has_emission(self) -> bool:
    return (
        self.floats.get("_Enable_Emission", 0) == 1 or
        "_Emission_Map" in self.textures or
        self._has_non_black_emission_color()
    )

def _has_non_black_emission_color(self) -> bool:
    color = self.colors.get("_Emission_Color", (0, 0, 0, 1))
    return color[0] > 0 or color[1] > 0 or color[2] > 0
```

**Name Pattern Fallback:**
```
(?i)lantern, (?i)lamp, (?i)light, (?i)glow,
(?i)torch, (?i)fire, (?i)flame, (?i)candle,
(?i)neon, (?i)emissive, (?i)lava, (?i)magic
```

**Shader Used:** `polygon_shader.gdshader` (with emission enabled)

**Generated Parameters:**
```tres
shader_parameter/enable_emission_texture = true
shader_parameter/emission_texture = ExtResource("3")
shader_parameter/emission_color_tint = Color(1.0, 0.8, 0.4, 1.0)
```

## Priority 3: GLASS

**Detection via Unity Metadata:**

A material is classified as GLASS if:

```yaml
# stringTagMap section indicates transparent rendering
stringTagMap:
  RenderType: Transparent
```

**Additional Name Check:**
When `RenderType == "Transparent"`, the classifier also checks if the name matches glass patterns OR does NOT match foliage patterns (to avoid false positives with alpha-tested foliage).

**Code Implementation:**
```python
@property
def is_transparent(self) -> bool:
    return self.tags.get("RenderType") == "Transparent"

# In classification:
if mat_info.is_transparent:
    name_lower = mat_info.name.lower()
    if self._matches_patterns(name_lower, self.GLASS_PATTERNS):
        return MaterialType.GLASS
    if not self._matches_patterns(name_lower, self.FOLIAGE_PATTERNS):
        return MaterialType.GLASS
```

**Name Pattern Fallback:**
```
(?i)glass, (?i)window, (?i)crystal, (?i)ice,
(?i)transparent, (?i)mirror, (?i)lens
```

**Shader Used:** `refractive_transparent.gdshader`

**Generated Parameters:**
```tres
render_priority = 1
shader_parameter/albedo_color = Color(0.9, 0.95, 1.0, 0.3)
shader_parameter/fresnel_power = 3.0
shader_parameter/fresnel_opacity = 0.8
shader_parameter/refraction_strength = 0.05
shader_parameter/roughness = 0.1
```

## Priority 4: WATER

**Detection:**

Water materials are primarily detected by name patterns, as Unity water shaders often don't have distinctive metadata properties.

**Name Patterns:**
```
(?i)water, (?i)ocean, (?i)river, (?i)lake, (?i)pond,
(?i)sea, (?i)wave, (?i)stream, (?i)waterfall
```

**Code Implementation:**
```python
if self._matches_patterns(mat_info.name.lower(), self.WATER_PATTERNS):
    return MaterialType.WATER
```

**Shader Used:** `water.gdshader`

**Generated Parameters:**
```tres
shader_parameter/water_color = Color(0.1, 0.3, 0.5, 0.8)
shader_parameter/deep_water_color = Color(0.0, 0.1, 0.2, 1.0)
shader_parameter/wave_speed = 1.0
shader_parameter/wave_strength = 0.1
shader_parameter/foam_strength = 0.5
```

## Priority 5: STANDARD

**Detection:**

Default fallback when no other type matches.

**Shader Used:** `polygon_shader.gdshader`

**Generated Parameters:**
```tres
shader_parameter/enable_base_texture = true
shader_parameter/base_texture = ExtResource("2")
shader_parameter/color_tint = Color(1, 1, 1, 1)
shader_parameter/metallic = 0.0
shader_parameter/smoothness = 0.5
shader_parameter/enable_normal_texture = false
shader_parameter/base_tiling = Vector2(1, 1)
shader_parameter/base_offset = Vector2(0, 0)
```

## Name-Only Classifications

These types are detected only by name patterns (no metadata detection):

### SKY

**Name Patterns:**
```
(?i)sky, (?i)skydome, (?i)skybox
```

**Shader Used:** `sky_dome.gdshader`

**Generated Parameters:**
```tres
shader_parameter/sky_top_color = Color(0.4, 0.6, 1.0, 1.0)
shader_parameter/sky_horizon_color = Color(0.8, 0.85, 0.95, 1.0)
shader_parameter/sun_color = Color(1.0, 0.95, 0.8, 1.0)
```

### CLOUDS

**Name Patterns:**
```
(?i)cloud, (?i)fog, (?i)mist, (?i)smoke
```

**Shader Used:** `clouds.gdshader`

**Generated Parameters:**
```tres
shader_parameter/cloud_color = Color(1.0, 1.0, 1.0, 0.8)
shader_parameter/cloud_speed = 0.01
shader_parameter/cloud_density = 0.5
```

### PARTICLES

**Name Patterns:**
```
(?i)particle, (?i)fx_, (?i)effect, (?i)spark,
(?i)dust, (?i)debris
```

**Shader Used:** `particles_unlit.gdshader`

**Generated Parameters:**
```tres
shader_parameter/albedo_texture = ExtResource("2")
shader_parameter/albedo_color = Color(1.0, 1.0, 1.0, 1.0)
```

## Classification Flow Diagram

```
                    Material Input
                          |
                          v
                 +------------------+
                 | Has Metadata?    |
                 +------------------+
                    |           |
                   Yes          No
                    |           |
                    v           |
           +----------------+   |
           | Check Foliage  |   |
           | Properties     |   |
           +----------------+   |
                |   |           |
              Yes   No          |
                |   |           |
                v   v           |
          FOLIAGE   |           |
                    v           |
           +----------------+   |
           | Check Emission |   |
           +----------------+   |
                |   |           |
              Yes   No          |
                |   |           |
                v   v           |
          EMISSIVE  |           |
                    v           |
           +----------------+   |
           | Check Trans +  |   |
           | Name Pattern   |   |
           +----------------+   |
                |   |           |
              Yes   No          |
                |   |           |
                v   v           |
            GLASS   |           |
                    v           |
           +----------------+   |
           | Check Water    |<--+
           | Name Pattern   |
           +----------------+
                |   |
              Yes   No
                |   |
                v   v
            WATER   |
                    v
           +----------------+
           | Check Other    |
           | Name Patterns  |
           +----------------+
                |
          +-----+-----+-----+
          |     |     |     |
          v     v     v     v
        SKY  CLOUDS PARTICLES STANDARD
```

## Batch Classification

The classifier provides a batch processing method:

```python
classifier = MaterialClassifier()

material_names = ["Tree_Oak_01", "Water_Ocean", "Glass_Window"]
materials_info = {...}  # Optional dict of name -> MaterialInfo

results = classifier.classify_batch(material_names, materials_info)
# Returns: {"Tree_Oak_01": FOLIAGE, "Water_Ocean": WATER, "Glass_Window": GLASS}

summary = classifier.get_summary(results)
# Returns: {FOLIAGE: ["Tree_Oak_01"], WATER: ["Water_Ocean"], GLASS: ["Glass_Window"]}
```

## Customization

### Adding New Patterns

To add new detection patterns, modify the pattern lists in `MaterialClassifier`:

```python
FOLIAGE_PATTERNS = [
    r"(?i)leaf", r"(?i)tree", r"(?i)plant",
    r"(?i)my_custom_foliage"  # Add your pattern
]
```

### Adding New Material Types

1. Add to `MaterialType` enum in `config.py`
2. Add detection logic in `_classify_from_metadata()` or `_classify_from_name()`
3. Add shader mapping in `SHADER_FILES`
4. Add generator in `MaterialGenerator`

## Debugging Classification

Enable verbose logging to see classification decisions:

```python
import logging
logging.getLogger("synty_converter_v2.classifiers.material_classifier").setLevel(logging.DEBUG)
```

Output example:
```
DEBUG - Classified Tree_Oak_01 as FOLIAGE from metadata
DEBUG - Classified Glass_Window_01 as GLASS from metadata
DEBUG - Classified Generic_Material as STANDARD from name
```
