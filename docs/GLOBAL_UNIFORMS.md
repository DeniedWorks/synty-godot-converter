# Global Shader Uniforms

This document explains the global shader variables required by the Synty shaders and how to set them up in your Godot project.

## Overview

Several Synty shaders (particularly foliage, water, and clouds) require global shader uniforms to function properly. These uniforms allow centralized control of environmental effects like wind and provide shared resources like gradient textures.

## Required Global Uniforms

| Uniform Name | Type | Used By | Purpose |
|--------------|------|---------|---------|
| `WindDirection` | vec3 | foliage, water | Direction of wind movement |
| `WindIntensity` | float | foliage | Overall wind strength |
| `GaleStrength` | float | foliage, water | Storm/gust intensity |
| `OceanWavesGradient` | sampler2D | water | Wave displacement pattern |

### Optional Global Uniforms (Clouds Shader)

| Uniform Name | Type | Purpose |
|--------------|------|---------|
| `MainLightDirection` | vec3 | Sun/moon direction |
| `SkyColor` | vec4 | Zenith sky color |
| `EquatorColor` | vec4 | Horizon sky color |
| `GroundColor` | vec4 | Ground reflection color |

## Setup Methods

### Method 1: Using the Generated Script (Recommended)

The converter can generate an autoload script that handles all global uniforms:

```bash
python -m synty_converter_v2 --pack MyPack --unity pkg.unitypackage --project ./game
```

This creates `global_shader_uniforms.gd` in your project. Then:

1. Open **Project > Project Settings > Autoload**
2. Click **Add** and select `global_shader_uniforms.gd`
3. Set the **Node Name** to `GlobalShaderUniforms`
4. Enable the autoload

### Method 2: Manual Project Settings

Register uniforms directly in Project Settings:

1. Open **Project > Project Settings > Shader Globals**
2. Click **Add**
3. Add each uniform:

| Name | Type | Default Value |
|------|------|---------------|
| WindDirection | vec3 | (1.0, 0.0, 0.5) |
| WindIntensity | float | 1.0 |
| GaleStrength | float | 0.0 |
| OceanWavesGradient | sampler2D | (create gradient texture) |

### Method 3: Manual Script

Create your own autoload script:

```gdscript
extends Node

## Global shader uniforms for Synty shaders.

@export var wind_direction: Vector3 = Vector3(1.0, 0.0, 0.5)
@export var wind_intensity: float = 1.0
@export var gale_strength: float = 0.0
@export var ocean_waves_gradient: GradientTexture1D

func _ready() -> void:
    _setup_global_uniforms()
    _create_default_gradient()

func _setup_global_uniforms() -> void:
    # Wind uniforms for foliage shaders
    RenderingServer.global_shader_parameter_add(
        "WindDirection", RenderingServer.GLOBAL_VAR_TYPE_VEC3, wind_direction
    )
    RenderingServer.global_shader_parameter_add(
        "WindIntensity", RenderingServer.GLOBAL_VAR_TYPE_FLOAT, wind_intensity
    )
    RenderingServer.global_shader_parameter_add(
        "GaleStrength", RenderingServer.GLOBAL_VAR_TYPE_FLOAT, gale_strength
    )

func _create_default_gradient() -> void:
    # Create default ocean waves gradient if not set
    if ocean_waves_gradient == null:
        ocean_waves_gradient = GradientTexture1D.new()
        var gradient = Gradient.new()
        gradient.set_color(0, Color(0.1, 0.3, 0.5, 1.0))
        gradient.set_color(1, Color(0.2, 0.5, 0.7, 1.0))
        ocean_waves_gradient.gradient = gradient

    RenderingServer.global_shader_parameter_add(
        "OceanWavesGradient", RenderingServer.GLOBAL_VAR_TYPE_SAMPLER2D, ocean_waves_gradient
    )

func _process(delta: float) -> void:
    # Update wind uniforms in real-time
    RenderingServer.global_shader_parameter_set("WindDirection", wind_direction)
    RenderingServer.global_shader_parameter_set("WindIntensity", wind_intensity)
    RenderingServer.global_shader_parameter_set("GaleStrength", gale_strength)

## Call this to simulate a wind gust
func trigger_gust(strength: float = 1.0, duration: float = 2.0) -> void:
    var tween = create_tween()
    tween.tween_property(self, "gale_strength", strength, duration * 0.3)
    tween.tween_property(self, "gale_strength", 0.0, duration * 0.7)

## Set wind from a direction angle (0-360 degrees, 0 = North)
func set_wind_from_angle(angle_degrees: float, strength: float = 1.0) -> void:
    var angle_rad = deg_to_rad(angle_degrees)
    wind_direction = Vector3(sin(angle_rad), 0.0, cos(angle_rad)).normalized()
    wind_intensity = strength
```

## Uniform Details

### WindDirection (vec3)

Controls the direction of wind movement for foliage and water wave direction.

**Expected Values:**
- Normalized or near-normalized vector
- X and Z components control horizontal direction
- Y component typically 0 (horizontal wind)

**Example Values:**
```gdscript
# North wind
wind_direction = Vector3(0.0, 0.0, 1.0)

# East wind
wind_direction = Vector3(1.0, 0.0, 0.0)

# Southwest wind
wind_direction = Vector3(-0.7, 0.0, -0.7).normalized()
```

**Shader Usage (foliage.gdshader):**
```glsl
global uniform vec3 WindDirection;

void vertex() {
    vec3 wind_direction;
    if (use_global_weather_controller) {
        wind_direction = normalize(WindDirection * local_model);
    }
    // Apply wind displacement...
}
```

### WindIntensity (float)

Overall wind strength multiplier.

**Expected Values:**
- Range: 0.0 to 1.0
- 0.0 = No wind (static foliage)
- 0.5 = Moderate breeze
- 1.0 = Strong wind

**Shader Usage (foliage.gdshader):**
```glsl
global uniform float WindIntensity;

void vertex() {
    float wind_intensity = clamp(WindIntensity, 0.0, 1.0);
    // ...
    VERTEX = mix(VERTEX, wind_and_gale, wind_intensity);
}
```

### GaleStrength (float)

Storm or gust intensity. Creates more dramatic, sweeping wind effects.

**Expected Values:**
- Range: 0.0 to 1.0+
- 0.0 = Calm (no gale effects)
- 0.5 = Storm conditions
- 1.0+ = Severe storm

**Shader Usage (foliage.gdshader):**
```glsl
global uniform float GaleStrength;

vec3 make_glade(vec3 vertex, vec3 wind_direction, float gale_strength, float vertical_gradient) {
    float gale_displacement = (sin(TIME) * 0.5 + 0.5)
        * (20.0 * gale_strength)
        + 50.0 * gale_strength;
    vec3 rotated_vertex = rotate_around_axis(vertex, wind_direction, gale_displacement / 180.0 * PI);
    return mix(vertex, rotated_vertex, vertical_gradient * gale_blend);
}
```

**Triggering Gusts:**
```gdscript
# Animate a wind gust
func trigger_gust(strength: float = 1.0, duration: float = 2.0) -> void:
    var tween = create_tween()
    # Quick ramp up
    tween.tween_property(self, "gale_strength", strength, duration * 0.3)
    # Slow fade out
    tween.tween_property(self, "gale_strength", 0.0, duration * 0.7)
```

### OceanWavesGradient (sampler2D)

A gradient texture used by the water shader to displace vertices and create wave patterns.

**Expected Format:**
- `GradientTexture1D` or any 1D texture
- Grayscale or colored
- Used for wave height sampling

**Creating the Gradient:**
```gdscript
func _create_default_gradient() -> void:
    ocean_waves_gradient = GradientTexture1D.new()
    var gradient = Gradient.new()

    # Default ocean wave gradient (blue shades)
    gradient.set_color(0, Color(0.1, 0.3, 0.5, 1.0))  # Deep
    gradient.set_color(1, Color(0.2, 0.5, 0.7, 1.0))  # Surface

    ocean_waves_gradient.gradient = gradient
```

**Alternative Wave Patterns:**
```gdscript
# Choppy waves
gradient.set_color(0, Color(0.0, 0.0, 0.2, 1.0))
gradient.add_point(0.3, Color(0.1, 0.2, 0.4, 1.0))
gradient.add_point(0.6, Color(0.15, 0.3, 0.5, 1.0))
gradient.set_color(1, Color(0.2, 0.4, 0.6, 1.0))

# Calm waves
gradient.set_color(0, Color(0.15, 0.35, 0.55, 1.0))
gradient.set_color(1, Color(0.18, 0.38, 0.58, 1.0))
```

**Shader Usage (water.gdshader):**
```glsl
global uniform sampler2D OceanWavesGradient;

vec4 ocean_waves(vec2 uv, float speed, float height, vec3 wind_dir, float gale_strength) {
    vec2 pan_uv = uv + normalize(wind_dir).xz * TIME/10.0;
    vec4 sample = texture(OceanWavesGradient, pan_uv * ocean_wave_frequency);
    float wave_height = height * sample.z * (gale_strength * 1.5);
    return vec4(0.0, wave_height, 0.0, sample.r);
}
```

## Advanced Usage

### Weather System Integration

Create a weather controller that manages all environmental effects:

```gdscript
extends Node
class_name WeatherController

signal weather_changed(weather_type)

enum Weather { CALM, BREEZY, WINDY, STORMY }

var current_weather: Weather = Weather.CALM
var weather_configs = {
    Weather.CALM: {
        "wind_direction": Vector3(0.5, 0.0, 0.5),
        "wind_intensity": 0.1,
        "gale_strength": 0.0
    },
    Weather.BREEZY: {
        "wind_direction": Vector3(1.0, 0.0, 0.3),
        "wind_intensity": 0.4,
        "gale_strength": 0.0
    },
    Weather.WINDY: {
        "wind_direction": Vector3(1.0, 0.0, 0.0),
        "wind_intensity": 0.7,
        "gale_strength": 0.2
    },
    Weather.STORMY: {
        "wind_direction": Vector3(0.8, 0.0, -0.6),
        "wind_intensity": 1.0,
        "gale_strength": 0.8
    }
}

func set_weather(weather: Weather, transition_time: float = 2.0) -> void:
    var config = weather_configs[weather]
    var tween = create_tween()

    tween.tween_property(GlobalShaderUniforms, "wind_direction",
        config.wind_direction, transition_time)
    tween.parallel().tween_property(GlobalShaderUniforms, "wind_intensity",
        config.wind_intensity, transition_time)
    tween.parallel().tween_property(GlobalShaderUniforms, "gale_strength",
        config.gale_strength, transition_time)

    current_weather = weather
    weather_changed.emit(weather)

func add_random_gusts() -> void:
    while true:
        await get_tree().create_timer(randf_range(5.0, 15.0)).timeout
        if current_weather in [Weather.WINDY, Weather.STORMY]:
            GlobalShaderUniforms.trigger_gust(randf_range(0.5, 1.5), randf_range(1.0, 3.0))
```

### Day/Night Cycle Integration

Update wind based on time of day:

```gdscript
func update_wind_for_time(hour: float) -> void:
    # Morning breeze (6-10)
    if hour >= 6 and hour < 10:
        GlobalShaderUniforms.wind_intensity = lerp(0.1, 0.4, (hour - 6) / 4.0)
    # Afternoon calm (10-16)
    elif hour >= 10 and hour < 16:
        GlobalShaderUniforms.wind_intensity = 0.2
    # Evening wind (16-20)
    elif hour >= 16 and hour < 20:
        GlobalShaderUniforms.wind_intensity = lerp(0.2, 0.5, (hour - 16) / 4.0)
    # Night calm
    else:
        GlobalShaderUniforms.wind_intensity = 0.1
```

### Performance Considerations

The global uniforms are updated via `RenderingServer.global_shader_parameter_set()` which is efficient, but consider:

1. **Update Frequency:** Don't update every frame unless animating
2. **Batched Updates:** Group multiple uniform updates together
3. **Conditional Updates:** Only update when values actually change

```gdscript
var _last_wind_dir: Vector3
var _last_wind_intensity: float
var _last_gale_strength: float

func _process(delta: float) -> void:
    # Only update if values changed
    if wind_direction != _last_wind_dir:
        RenderingServer.global_shader_parameter_set("WindDirection", wind_direction)
        _last_wind_dir = wind_direction

    if wind_intensity != _last_wind_intensity:
        RenderingServer.global_shader_parameter_set("WindIntensity", wind_intensity)
        _last_wind_intensity = wind_intensity

    if gale_strength != _last_gale_strength:
        RenderingServer.global_shader_parameter_set("GaleStrength", gale_strength)
        _last_gale_strength = gale_strength
```

## Troubleshooting

### "Global uniform not found" Error

**Cause:** Shader references a global uniform that hasn't been registered.

**Solution:** Ensure the autoload script runs before any scene with Synty materials:
1. Check autoload order in Project Settings
2. Move GlobalShaderUniforms higher in the list

### Foliage Not Moving

**Possible Causes:**
1. `WindIntensity` is 0
2. `use_global_weather_controller = false` in material
3. Global uniforms not registered

**Debug:**
```gdscript
func _ready() -> void:
    print("WindDirection: ", RenderingServer.global_shader_parameter_get("WindDirection"))
    print("WindIntensity: ", RenderingServer.global_shader_parameter_get("WindIntensity"))
```

### Water Waves Not Appearing

**Possible Causes:**
1. `enable_ocean_waves = false` in material
2. `OceanWavesGradient` texture not assigned
3. `ocean_wave_height` is 0

### Materials Show Magenta

**Cause:** Shader file missing or has syntax error.

**Solution:**
1. Check that shader files exist in `assets/shaders/synty/`
2. Open shader in Godot editor to check for errors
3. Re-download from godotshaders.com if needed

## API Reference

### GlobalShaderUniforms Singleton

After setting up the autoload, access it globally:

```gdscript
# Get current values
var wind = GlobalShaderUniforms.wind_direction
var intensity = GlobalShaderUniforms.wind_intensity

# Set new values
GlobalShaderUniforms.wind_direction = Vector3(1, 0, 0)
GlobalShaderUniforms.wind_intensity = 0.5

# Trigger effects
GlobalShaderUniforms.trigger_gust(1.0, 2.0)
GlobalShaderUniforms.set_wind_from_angle(45.0, 0.7)  # NE wind, 70% strength
```

### RenderingServer Direct Access

For advanced use cases:

```gdscript
# Register new uniform
RenderingServer.global_shader_parameter_add(
    "MyCustomUniform",
    RenderingServer.GLOBAL_VAR_TYPE_FLOAT,
    1.0
)

# Update existing uniform
RenderingServer.global_shader_parameter_set("WindIntensity", 0.5)

# Get current value
var value = RenderingServer.global_shader_parameter_get("WindIntensity")

# Remove uniform (rarely needed)
RenderingServer.global_shader_parameter_remove("MyCustomUniform")
```
