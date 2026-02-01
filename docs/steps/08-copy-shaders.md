# Step 8: Resolve Shader Paths

This document provides comprehensive documentation for the shader path resolution step in the Synty Shader Converter pipeline, including details on all 7 community drop-in shaders.

**Module Location:** `synty-converter/converter.py` function `copy_shaders()`

**Shader Files:** `synty-converter/shaders/` (7 files)

**Related Documentation:**
- [Architecture](../architecture.md) - Overall pipeline context
- [Shader Reference](../shader-reference.md) - Detailed shader parameters
- [API: shader_mapping](../api/shader_mapping.md) - Shader detection logic

---

## Table of Contents

- [Overview](#overview)
- [Shader Path Resolution](#shader-path-resolution)
  - [get_shader_paths() Function](#get_shader_paths-function)
  - [Project-Wide Shader Search](#project-wide-shader-search)
  - [Using Found Paths in Materials](#using-found-paths-in-materials)
- [Shader Files](#shader-files)
  - [SHADER_FILES Constant](#shader_files-constant)
  - [Output Directory Structure](#output-directory-structure)
- [copy_shaders() Function](#copy_shaders-function)
  - [Function Signature](#function-signature)
  - [Implementation Details](#implementation-details)
  - [Skip Logic for Existing Shaders](#skip-logic-for-existing-shaders)
  - [Error Handling](#error-handling)
- [Community Drop-in Shaders](#community-drop-in-shaders)
  - [polygon.gdshader](#polygongdshader)
  - [foliage.gdshader](#foliagegdshader)
  - [crystal.gdshader](#crystalgdshader)
  - [water.gdshader](#watergdshader)
  - [clouds.gdshader](#cloudsgdshader)
  - [particles.gdshader](#particlesgdshader)
  - [skydome.gdshader](#skydomegdshader)
- [Shader Detection and Selection](#shader-detection-and-selection)
  - [Detection Flow](#detection-flow)
  - [Name Pattern Scoring](#name-pattern-scoring)
  - [Detection Examples](#detection-examples)
- [Global Shader Uniforms](#global-shader-uniforms)
- [Code Examples](#code-examples)
- [Notes for Doc Cleanup](#notes-for-doc-cleanup)

---

## Overview

Step 8 resolves shader paths by searching the entire Godot project for existing shaders. If shaders are found, their existing paths are used in material files. Only missing shaders are copied from the converter's `shaders/` directory.

These shaders are drop-in replacements for Unity's Synty shaders, implementing equivalent visual effects in Godot's shading language.

### Key Responsibilities

1. **Search project for shaders** - Use `get_shader_paths()` to find existing shaders anywhere in the project
2. **Use found paths** - Materials reference shaders at their discovered locations (not hardcoded `res://shaders/`)
3. **Copy only missing shaders** - Skip copying if shader already exists elsewhere in the project
4. **Handle existing files** - Support multi-pack conversions with shared shader directories
5. **Track statistics** - Report number of shaders copied for conversion summary

### Position in Pipeline

```
Step 7: Generate material .tres files
        |
        v
Step 8: Resolve shader paths   <-- THIS STEP
        |
        v
Step 9: Copy texture files
        |
        v
Step 10: Copy FBX files
```

---

## Shader Path Resolution

### get_shader_paths() Function

The converter now uses a new function to discover existing shader locations:

```python
def get_shader_paths(project_dir: Path) -> dict[str, str]:
    """Search entire project for existing shaders and return their res:// paths.

    Args:
        project_dir: Root directory of the Godot project.

    Returns:
        Dictionary mapping shader filename to res:// path.
        Example: {"polygon.gdshader": "res://assets/shaders/synty/polygon.gdshader"}
    """
```

**Key behavior:**
- Searches the entire project directory recursively for `.gdshader` files
- Returns a mapping from shader filename to its `res://` path
- Enables materials to reference shaders at their actual locations

### Project-Wide Shader Search

The search process:

1. **Recursive glob** - Uses `project_dir.rglob("*.gdshader")` to find all shader files
2. **Path conversion** - Converts absolute paths to `res://` format
3. **Filename mapping** - Maps each shader's filename to its full path

```python
shader_paths = {}
for shader_file in project_dir.rglob("*.gdshader"):
    relative_path = shader_file.relative_to(project_dir)
    res_path = f"res://{relative_path.as_posix()}"
    shader_paths[shader_file.name] = res_path
```

**Example results:**

```python
{
    "polygon.gdshader": "res://assets/shaders/synty/polygon.gdshader",
    "foliage.gdshader": "res://assets/shaders/synty/foliage.gdshader",
    "water.gdshader": "res://assets/shaders/synty/water.gdshader",
}
```

### Using Found Paths in Materials

Materials now reference shaders at their discovered locations instead of a hardcoded path:

**Before (hardcoded):**
```ini
[ext_resource type="Shader" path="res://shaders/polygon.gdshader" id="1"]
```

**After (discovered path):**
```ini
[ext_resource type="Shader" path="res://assets/shaders/synty/polygon.gdshader" id="1"]
```

This allows projects to organize shaders in their preferred location while still being able to convert new Synty packs.

---

## Shader Files

### SHADER_FILES Constant

The converter defines a constant list of all shader files to copy:

```python
SHADER_FILES = [
    "clouds.gdshader",
    "crystal.gdshader",
    "foliage.gdshader",
    "particles.gdshader",
    "polygon.gdshader",
    "skydome.gdshader",
    "water.gdshader",
]
```

**Total:** 7 shader files

### Output Directory Structure

Shaders can exist anywhere in the project. The converter searches for them and uses their found paths:

```
output-project/
  project.godot                      # With global shader uniforms
  assets/
    shaders/
      synty/                         # <-- Example: shaders in custom location
        clouds.gdshader
        crystal.gdshader
        foliage.gdshader
        particles.gdshader
        polygon.gdshader
        skydome.gdshader
        water.gdshader
  shaders/                           # <-- Fallback: default location for missing shaders
  POLYGON_NatureBiomes/
    textures/
    materials/                       # Materials reference shaders at found paths
    models/
```

**Key design decision:** Shaders can be stored anywhere in the project:
- `get_shader_paths()` searches the entire project for existing shaders
- Materials reference shaders at their discovered locations
- Only missing shaders are copied to the default `shaders/` directory
- Supports existing project organizations without forcing a specific structure

---

## copy_shaders() Function

### Function Signature

```python
def copy_shaders(
    shaders_dest: Path,
    dry_run: bool,
    existing_shader_paths: dict[str, str] | None = None
) -> int:
    """Copy .gdshader files from project's shaders/ to destination.

    Only copies shaders that don't already exist in the project.

    Args:
        shaders_dest: Destination directory for shader files.
        dry_run: If True, only log what would be copied.
        existing_shader_paths: Optional dict of shader filename to existing res:// path.
            If a shader exists in this dict, it won't be copied.

    Returns:
        Number of shader files copied (or would be copied in dry run).
    """
```

### Implementation Details

**Key behavior changes:**

1. **Check existing paths first** - If a shader is found via `get_shader_paths()`, skip copying
2. **Only copy missing shaders** - Reduces file duplication in projects with existing shaders
3. **Use found paths in materials** - Materials reference shaders at their discovered locations

**Step-by-step flow:**

1. **Locate source shaders** - Find the converter's `shaders/` directory relative to `converter.py`
2. **Check existing paths** - If shader already exists in project (via `existing_shader_paths`), skip
3. **Create destination** - Ensure `output/shaders/` exists (unless dry run)
4. **Iterate SHADER_FILES** - Process each shader in the constant list
5. **Check source exists** - Warn and skip if shader file is missing
6. **Check destination exists** - Skip if already copied to destination
7. **Copy file** - Use `shutil.copy2()` to preserve metadata

**Example with existing shaders:**

```python
# Search project for existing shaders
existing_paths = get_shader_paths(project_dir)
# Returns: {"polygon.gdshader": "res://assets/shaders/synty/polygon.gdshader", ...}

# Copy only shaders not found in project
copied = copy_shaders(
    shaders_dest=project_dir / "shaders",
    dry_run=False,
    existing_shader_paths=existing_paths
)
# polygon.gdshader exists at res://assets/shaders/synty/ - not copied
# crystal.gdshader not found - copied to res://shaders/
```

### Skip Logic for Existing Shaders

The function has two layers of skip logic:

**1. Skip if shader exists anywhere in project (via `get_shader_paths()`):**

```python
if existing_shader_paths and shader_file in existing_shader_paths:
    logger.debug("Shader found in project at %s, skipping copy", existing_shader_paths[shader_file])
    skipped += 1
    continue
```

**2. Skip if shader exists at destination:**

```python
if dest_path.exists():
    logger.debug("Shader already exists at destination, skipping: %s", shader_file)
    skipped += 1
    continue
```

**Why this matters:**

- **Project-wide search** - Shaders can live anywhere in the project (e.g., `res://assets/shaders/synty/`)
- **No duplication** - Won't copy a shader that already exists elsewhere
- **Preserves customizations** - Manual shader modifications are not overwritten
- **Multi-pack support** - Subsequent conversions skip copying because shaders exist

### Error Handling

| Scenario | Behavior |
|----------|----------|
| Source shader missing | Log warning, continue with other shaders |
| Destination exists | Skip copy, increment `skipped` counter |
| Destination directory missing | Created automatically via `mkdir(parents=True)` |
| File copy failure | Exception propagates up (rare, indicates disk issues) |

---

## Community Drop-in Shaders

All shaders are community-developed Godot replacements for Unity's Synty shaders. They are authored by **Giancarlo Niccolai** and released under **MIT license**.

### polygon.gdshader

**Purpose:** The default and most versatile shader. Used for props, terrain, buildings, characters, and any material that doesn't need special effects.

**File:** `shaders/polygon.gdshader` (433 lines)

**Render Mode:** `blend_mix, depth_draw_opaque, cull_back`

**Key Features:**

| Feature | Description |
|---------|-------------|
| Base Textures | Albedo, normal, emission, ambient occlusion |
| Triplanar Projection | Y/XZ-based world-space projection for terrain/rocks |
| Snow Effect | Height-based snow coverage with adjustable level |
| Overlay Texture | Secondary effects layer (selection, damage, etc.) |
| UV Animation | Panning support via `uv_pan` uniform |

**Core Uniform Groups:**

```glsl
group_uniforms Base;
uniform vec4 color_tint : source_color = vec4(1.0);
uniform float metallic : hint_range(0.0, 1.0) = 0.0;
uniform float smoothness : hint_range(0.0, 1.0) = 0.0;

group_uniforms Base.BaseTexture;
uniform bool enable_base_texture = true;
uniform sampler2D base_texture : source_color, filter_linear_mipmap, repeat_enable;
uniform vec2 base_tiling = vec2(1.0);
uniform vec2 base_offset = vec2(0.0);

group_uniforms Triplanar;
uniform bool enable_triplanar_texture = false;
uniform sampler2D triplanar_texture_top : source_color;
uniform sampler2D triplanar_texture_side : source_color;
uniform sampler2D triplanar_texture_bottom : source_color;

group_uniforms Snow;
uniform bool enable_snow = false;
uniform vec4 snow_color : source_color = vec4(1.0);
uniform float snow_level : hint_range(0.0, 1.0) = 0.5;
```

**Triplanar System Details:**

Unlike traditional XYZ triplanar, this shader uses Y/XZ projection:
- **Top (Y+):** Upward-facing surfaces (ground, table tops)
- **Bottom (Y-):** Downward-facing surfaces (ceiling, undersides)
- **Side (X & Z):** Vertical surfaces (walls, cliffs)

This matches Unity's Synty PolygonShader behavior.

**When Used:**
- Materials where `uses_custom_shader=False` in MaterialList.txt
- Materials with `_Triplanar_` in name
- Default fallback when no other shader matches

---

### foliage.gdshader

**Purpose:** Vegetation shader with built-in wind animation, frost effects, and procedural color variation.

**File:** `shaders/foliage.gdshader` (683 lines)

**Render Mode:** `blend_mix, depth_draw_opaque, depth_prepass_alpha, cull_disabled, diffuse_lambert, specular_schlick_ggx`

**Key Features:**

| Feature | Description |
|---------|-------------|
| Separate Leaf/Trunk | Different textures and properties for each |
| Wind System | Breeze, light wind, strong wind, twist effects |
| Frosting | Snow/frost coverage on foliage |
| Color Noise | Procedural patch-level color variation |
| Emission + Pulse | Animated glow effects |

**Required Global Uniforms:**

```glsl
global uniform vec3 WindDirection;
global uniform float WindIntensity;
global uniform float GaleStrength;
```

**Vertex Color Encoding:**

The shader uses mesh vertex colors to control behavior:

| Channel | Value Range | Purpose |
|---------|-------------|---------|
| Red | 0.0-1.0 | Height gradient (bottom=0, top=1) |
| Green | 0.0-1.0 | Leaf tip gradient |
| Blue | >0.5 = leaf | Leaf vs trunk mask |

**Wind System Hierarchy:**

```
Gale (global uniform)
  |
  +-- Breeze (enable_breeze)
  |     3-octave noise ripple
  |
  +-- Light Wind (enable_light_wind)
  |     Bending/pushing based on noise
  |
  +-- Strong Wind (enable_strong_wind)
  |     Object-level sinusoidal sway
  |
  +-- Wind Twist (enable_wind_twist)
        Y-axis rotation effect
```

**When Used:**
- Materials with `Tree`, `Fern`, `Grass`, `Leaf`, `Vine`, `Branch` in name
- Materials with `Foliage`, `Vegetation` in name
- Materials using Synty's Foliage shader GUID

---

### crystal.gdshader

**Purpose:** Transparent and refractive materials like crystals, gems, glass, and ice.

**File:** `shaders/crystal.gdshader` (456 lines)

**Render Mode:** `blend_mix, depth_draw_always, cull_disabled, diffuse_lambert, specular_schlick_ggx`

**Key Features:**

| Feature | Description |
|---------|-------------|
| Fresnel Edge Glow | Rim lighting based on view angle |
| Depth Coloring | Color transition from surface to interior |
| Refraction | Light bending with parallax mapping |
| Inner Distortion | Ripple effect for impure crystals |
| Triplanar | Optional world-space projection |

**Core Effects:**

**Fresnel (Edge Glow):**
```glsl
group_uniforms Fresnel;
uniform bool enable_fresnel = false;
uniform vec4 fresnel_color : source_color = vec4(1.0);
uniform float fresnel_border = 3.77;
uniform float fresnel_power = 4.86;
```

**Depth Coloring (Translucency):**
```glsl
group_uniforms Depth;
uniform bool enable_depth = false;
uniform vec4 deep_color : source_color = vec4(1.0);
uniform vec4 shallow_color : source_color = vec4(1.0);
uniform float deep_power = 8;
uniform float shallow_power = 1.2;
```

**Refraction:**
```glsl
group_uniforms Refraction;
uniform bool enable_refraction = false;
uniform sampler2D refraction_texture : hint_normal;
uniform float refraction_power = 1.25;
uniform float amplitude = -50.0;
```

**When Used:**
- Materials with `Crystal`, `Gem`, `Glass`, `Ice` in name
- Materials with `fresnel`, `refractive`, `refraction` in name
- Materials using Synty's Refractive_Transparent shader GUID

---

### water.gdshader

**Purpose:** Full-featured water shader for rivers, lakes, oceans, and waterfalls.

**File:** `shaders/water.gdshader` (638 lines)

**Render Mode:** `blend_mix, depth_draw_opaque, cull_back, diffuse_lambert, specular_disabled`

**Key Features:**

| Feature | Description |
|---------|-------------|
| Animated Waves | Vertex displacement for wave motion |
| Shore Foam | Foam where water meets geometry |
| Global Foam | Ocean whitecaps and wave crests |
| Caustics | Animated underwater light patterns |
| Distortion | Screen-space underwater refraction |
| Depth Coloring | Shallow to deep color gradient |

**Required Global Uniforms:**

```glsl
global uniform vec3 WindDirection;
global uniform float GaleStrength;
global uniform sampler2D OceanWavesGradient;
```

**Feature Toggles:**

| Toggle | Key Parameters |
|--------|----------------|
| `enable_normals` | `normal_texture`, `normal_tiling`, `normal_intensity` |
| `enable_shore_wave_foam` | `shore_wave_speed`, `shore_wave_color_tint` |
| `enable_shore_foam` | `shore_foam_color_tint`, `shore_small_foam_tiling` |
| `enable_global_foam` | `noise_texture`, `ocean_foam_amount` |
| `enable_ocean_waves` | `ocean_wave_height`, `ocean_wave_speed` |
| `enable_caustics` | `caustics_flipbook`, `caustics_intensity` |
| `enable_distortion` | `distortion_speed`, `distortion_strength` |

**Caustics System:**

Supports two modes:
1. **Flipbook Animation:** Uses 8x8 texture flipbook for pre-rendered caustics
2. **Voronoi Noise:** Procedural caustics via `caustics_use_voronoi_noise`

**When Used:**
- Materials with `Water`, `Ocean`, `River`, `Lake`, `Waterfall` in name
- Materials with `caustics` in name
- Materials using Synty's Water shader GUID

---

### clouds.gdshader

**Purpose:** Volumetric cloud and atmospheric effects with cartoon-style rendering.

**File:** `shaders/clouds.gdshader` (116 lines)

**Render Mode:** `unshaded`

**Key Features:**

| Feature | Description |
|---------|-------------|
| Gradient Coloring | Top to base color gradient |
| Fresnel Highlights | Edge glow based on view angle |
| Scattering | Light scatter simulation |
| Fog Integration | Scene fog support |
| Vertex Animation | Gentle up/down cloud movement |

**Required Global Uniforms:**

```glsl
global uniform vec3 MainLightDirection;
global uniform vec4 SkyColor: source_color;
global uniform vec4 EquatorColor: source_color;
global uniform vec4 GroundColor: source_color;
```

**Environment Override:**

When `use_environment_override = true`, the shader uses local uniforms instead of globals:
- `top_color` instead of `SkyColor`
- `base_color` instead of `EquatorColor`
- `fresnel_color` instead of `GroundColor`

**Vertex Animation:**
```glsl
void vertex() {
    float displacement = cloud_strength * (sin(TIME * cloud_speed + VERTEX.x + VERTEX.z));
    VERTEX += vec3(0.0, displacement, 0.0);
}
```

**When Used:**
- Materials with `Cloud`, `Clouds`, `Sky_Cloud` in name
- Materials with `fog`, `mist`, `atmosphere` in name
- Materials using Synty's Clouds shader GUID

---

### particles.gdshader

**Purpose:** Soft particles with depth blending for fire, smoke, fog, and effects.

**File:** `shaders/particles.gdshader` (160 lines)

**Render Mode:** `blend_mix`

**Key Features:**

| Feature | Description |
|---------|-------------|
| Soft Particles | Blend with scene depth to avoid hard edges |
| Camera Fade | Fade particles near/far from camera |
| View Edge Compensation | Adjust for edge-of-screen distortion |
| Scene Fog | Integration with Godot's fog system |

**Core Uniforms:**

```glsl
uniform float alpha_clip_treshold: hint_range(0.0, 1.0) = 0.5;
uniform vec4 base_color: source_color = vec4(1.0);
uniform sampler2D albedo_map: source_color;
uniform vec2 tiling = vec2(1.0);
uniform vec2 offset = vec2(0.0);

uniform bool enable_soft_particles = true;
uniform float soft_power: hint_range(0.0, 10.0) = 2.0;
uniform float soft_distance: hint_range(0.0, 2.0) = 0.1;

uniform bool enable_camera_fade = false;
uniform float camera_fade_near = 0.0;
uniform float camera_fade_far = 20.0;
```

**Soft Particles Algorithm:**

```glsl
if(enable_soft_particles) {
    soft_fade = pow(clamp((eye_depth - cam_dist) * (soft_distance / 10.0), 0.0, 1.0), soft_power);
}
```

This fades particles as they approach scene geometry, preventing harsh intersection lines.

**When Used:**
- Materials with `Particle`, `FX_`, `Spark`, `Smoke`, `Fire` in name
- Materials with `soft.?particle` pattern
- Materials using Synty's Generic_ParticleUnlit shader GUID

---

### skydome.gdshader

**Purpose:** Simple gradient sky dome for cartoon-style environments.

**File:** `shaders/skydome.gdshader` (90 lines)

**Render Mode:** Spatial (default)

**Key Features:**

| Feature | Description |
|---------|-------------|
| Two-Color Gradient | Smooth blend from top to bottom |
| World Position Mode | Gradient based on world Y coordinate |
| UV-Based Mode | Alternative using mesh UVs |
| Falloff Control | Adjustable gradient curve |

**Core Uniforms:**

```glsl
uniform vec4 top_color: source_color = vec4(0.1, 0.6, 0.9, 1.0);
uniform vec4 bottom_color: source_color = vec4(0.05, 0.3, 0.45, 1.0);
uniform float falloff: hint_range(0.001, 100.0) = 1.0;
uniform float offset = 32.0;
uniform float distance_: hint_range(1.0, 10000.0) = 1000.0;
uniform bool enable_uv_based;
```

**Gradient Calculation (World Position Mode):**

```glsl
vec3 world_pos = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
sky_uv = clamp(pow((world_pos.y + offset) / min(1.0, distance_), falloff), 0.0, 1.0);
ALBEDO = mix(top_color, bottom_color, sky_uv).xyz;
```

**When Used:**
- Materials with `Skydome`, `SkyDome`, `Sky_Dome`, `Skybox` in name
- Materials with `aurora`, `sky_gradient` in name
- Materials using Synty's SkyDome shader GUID

---

## Shader Detection and Selection

### Detection Flow

The shader selection process (handled by `shader_mapping.py` before Step 8) determines which shader each material uses:

```
MaterialList.txt parsed
        |
        v
uses_custom_shader?
        |
   +----+----+
   |         |
  False     True
   |         |
   v         v
polygon    Name pattern
           matching
              |
              v
         Score > 20?
              |
         +----+----+
         |         |
        Yes        No
         |         |
         v         v
    Best match   polygon
                (unmatched)
```

### Name Pattern Scoring

Patterns are scored to resolve conflicts in compound names. Higher scores win.

**Score Tiers:**

| Score | Priority | Examples |
|-------|----------|----------|
| 55-60 | Technical terms | `triplanar`, `caustics`, `fresnel`, `soft.?particle`, `skydome` |
| 45 | Clear material types | `crystal`, `water`, `particle`, `cloud` |
| 35 | Common types | `glass`, `ice`, `fog`, `foliage`, `vegetation` |
| 20-25 | Generic vegetation | `tree`, `fern`, `grass`, `leaf`, `trunk` |
| 15 | Ambiguous terms | `moss`, `dirt`, `effect` |

**Full Pattern List:**

```python
SHADER_NAME_PATTERNS_SCORED = [
    # High priority (50-60)
    (r"(?i)triplanar", "polygon.gdshader", 60),
    (r"(?i)caustics", "water.gdshader", 55),
    (r"(?i)(fresnel|refractive|refraction)", "crystal.gdshader", 55),
    (r"(?i)soft.?particle", "particles.gdshader", 55),
    (r"(?i)(skydome|sky_dome|skybox|sky_box)", "skydome.gdshader", 55),

    # Medium-high priority (40-49)
    (r"(?i)(crystal|gem|jewel|diamond|ruby|emerald|sapphire|amethyst|quartz)", "crystal.gdshader", 45),
    (r"(?i)(water|ocean|river|lake|waterfall)", "water.gdshader", 45),
    (r"(?i)(particle|fx_)", "particles.gdshader", 45),
    (r"(?i)(cloud|clouds|sky_cloud)", "clouds.gdshader", 45),

    # Medium priority (30-39)
    (r"(?i)(glass|ice|transparent|translucent)", "crystal.gdshader", 35),
    (r"(?i)(pond|stream|liquid|aqua|sea)", "water.gdshader", 35),
    (r"(?i)(fog|mist|atmosphere)", "clouds.gdshader", 35),
    (r"(?i)(spark|dust|debris|smoke|fire|rain|snow|splash)", "particles.gdshader", 35),
    (r"(?i)(aurora|sky_gradient)", "skydome.gdshader", 35),
    (r"(?i)(foliage|vegetation)", "foliage.gdshader", 35),

    # Low-medium priority (20-29)
    (r"(?i)(tree|fern|grass|vine|branch|willow|bush|shrub|hedge|bamboo)", "foliage.gdshader", 25),
    (r"(?i)(leaf|leaves)", "foliage.gdshader", 20),
    (r"(?i)(bark|trunk|undergrowth|plant)", "foliage.gdshader", 20),

    # Low priority (10-19)
    (r"(?i)(moss|dirt)", "polygon.gdshader", 15),
    (r"(?i)(effect|additive)", "particles.gdshader", 15),
]
```

### Detection Examples

**Example 1: Compound Name Resolution**

Material: `Dirt_Leaves_Triplanar`

| Pattern | Shader | Score |
|---------|--------|-------|
| `dirt` | polygon | +15 |
| `leaves` | foliage | +20 |
| `triplanar` | polygon | +60 |

**Result:** polygon.gdshader (75 > 20)

**Example 2: Multiple Matching Patterns**

Material: `Crystal_Water_Effect`

| Pattern | Shader | Score |
|---------|--------|-------|
| `crystal` | crystal | +45 |
| `water` | water | +45 |
| `effect` | particles | +15 |

**Result:** crystal.gdshader (45 = 45, first match wins in tie)

**Example 3: Simple Match**

Material: `Tree_Oak_01`

| Pattern | Shader | Score |
|---------|--------|-------|
| `tree` | foliage | +25 |

**Result:** foliage.gdshader (25 >= 20 minimum threshold)

---

## Global Shader Uniforms

The converter generates a `project.godot` file with global shader uniforms required by the shaders:

```ini
[shader_globals]

WindDirection={
"type": "vec3",
"value": Vector3(1, 0, 0)
}
WindIntensity={
"type": "float",
"value": 0.5
}
GaleStrength={
"type": "float",
"value": 0.0
}
MainLightDirection={
"type": "vec3",
"value": Vector3(0.5, -0.5, 0.0)
}
SkyColor={
"type": "color",
"value": Color(0.5, 0.7, 1.0, 1.0)
}
EquatorColor={
"type": "color",
"value": Color(1.0, 0.9, 0.8, 1.0)
}
GroundColor={
"type": "color",
"value": Color(0.4, 0.4, 0.3, 1.0)
}
OceanWavesGradient={
"type": "sampler2D",
"value": ""
}
```

**Uniform Usage by Shader:**

| Uniform | foliage | water | clouds |
|---------|---------|-------|--------|
| WindDirection | Yes | Yes | - |
| WindIntensity | Yes | - | - |
| GaleStrength | Yes | Yes | - |
| MainLightDirection | - | - | Yes |
| SkyColor | - | - | Yes |
| EquatorColor | - | - | Yes |
| GroundColor | - | - | Yes |
| OceanWavesGradient | - | Yes | - |

---

## Code Examples

### Basic Shader Copy

```python
from pathlib import Path
from converter import copy_shaders

output_dir = Path("C:/Projects/converted")
shaders_dir = output_dir / "shaders"

# Copy all shaders
copied = copy_shaders(shaders_dir, dry_run=False)
print(f"Copied {copied} shader files")
```

### Dry Run Mode

```python
# Preview what would be copied
copied = copy_shaders(shaders_dir, dry_run=True)
# Output: [DRY RUN] Would copy shader: polygon.gdshader -> C:/Projects/converted/shaders/polygon.gdshader
```

### Multi-Pack Conversion

```python
# First pack - copies all 7 shaders
copy_shaders(shaders_dir, dry_run=False)  # Returns 7

# Second pack - skips existing shaders
copy_shaders(shaders_dir, dry_run=False)  # Returns 0
# Log: "Copied 0 shader files (7 already existed)"
```

### Manual Shader Reference

Generated materials reference shaders like this:

```ini
[gd_resource type="ShaderMaterial" load_steps=3 format=3]

[ext_resource type="Shader" path="res://shaders/foliage.gdshader" id="1"]
[ext_resource type="Texture2D" path="res://POLYGON_NatureBiomes/textures/Fern_1.tga" id="2"]

[resource]
shader = ExtResource("1")
shader_parameter/leaf_color = ExtResource("2")
shader_parameter/enable_breeze = true
shader_parameter/breeze_strength = 0.2
```

---

## Notes for Doc Cleanup

After reviewing the existing documentation, here are findings for consolidation:

### Redundant Information

1. **`docs/shader-reference.md`** - Contains detailed shader documentation that overlaps with this step doc:
   - Shader Feature Reference section (lines 60-513) duplicates the Community Drop-in Shaders section here
   - **Recommendation:** Keep shader-reference.md as the authoritative shader parameter reference, link here for copy process details

2. **`docs/api/shader_mapping.md`** - Contains detection pattern information:
   - SHADER_NAME_PATTERNS_SCORED is documented there
   - **Recommendation:** Keep pattern details in api/shader_mapping.md, reference from here

### Outdated Information

None found - the shader copy function and shader files appear current.

### Information to Incorporate

1. **Shader licensing** from shader file headers should be noted:
   - All shaders: MIT license, (C) 2025 Giancarlo Niccolai
   - Some header comments reference GodotShaders.com as source

2. **Version numbers** from shader headers:
   - polygon.gdshader: v1.1
   - foliage.gdshader: v1.4
   - crystal.gdshader: v1.1
   - water.gdshader: v1.1
   - Others: not versioned in headers

### Suggested Cross-References

Add to the following docs:

1. **`docs/architecture.md`** Step 7 section:
   - Add: "See [Step 8: Copy Shaders](steps/08-copy-shaders.md) for implementation details."

2. **`docs/shader-reference.md`** at top:
   - Add: "For shader copying process, see [Step 8: Copy Shaders](steps/08-copy-shaders.md)."

3. **`docs/api/shader_mapping.md`**:
   - Add cross-reference to this step for understanding how detection leads to shader deployment

### Potential Improvements

1. **Shader versioning** - Consider adding version tracking to detect when converter shaders are updated vs output project shaders

2. **Custom shader support** - Document how users can add custom shaders to the `shaders/` directory for specialized materials

3. **Shader validation** - Consider adding a validation step to verify shaders compile successfully in Godot

---

*Last Updated: 2026-02-01*
