"""Global shader uniforms script template for Synty shaders."""

GLOBAL_UNIFORMS_SCRIPT = '''extends Node
## Global shader uniforms for Synty shaders.
## Add this as an autoload singleton in Project Settings.

@export var wind_direction: Vector3 = Vector3(1.0, 0.0, 0.5)
@export var wind_intensity: float = 1.0
@export var gale_strength: float = 0.0
@export var ocean_waves_gradient: GradientTexture1D

func _ready() -> void:
\t_setup_global_uniforms()
\t_create_default_gradient()

func _setup_global_uniforms() -> void:
\t# Wind uniforms for foliage shaders
\tRenderingServer.global_shader_parameter_add(
\t\t"WindDirection", RenderingServer.GLOBAL_VAR_TYPE_VEC3, wind_direction
\t)
\tRenderingServer.global_shader_parameter_add(
\t\t"WindIntensity", RenderingServer.GLOBAL_VAR_TYPE_FLOAT, wind_intensity
\t)
\tRenderingServer.global_shader_parameter_add(
\t\t"GaleStrength", RenderingServer.GLOBAL_VAR_TYPE_FLOAT, gale_strength
\t)

func _create_default_gradient() -> void:
\t# Create default ocean waves gradient if not set
\tif ocean_waves_gradient == null:
\t\tocean_waves_gradient = GradientTexture1D.new()
\t\tvar gradient = Gradient.new()
\t\tgradient.set_color(0, Color(0.1, 0.3, 0.5, 1.0))
\t\tgradient.set_color(1, Color(0.2, 0.5, 0.7, 1.0))
\t\tocean_waves_gradient.gradient = gradient
\t
\tRenderingServer.global_shader_parameter_add(
\t\t"OceanWavesGradient", RenderingServer.GLOBAL_VAR_TYPE_SAMPLER2D, ocean_waves_gradient
\t)

func _process(delta: float) -> void:
\t# Update wind uniforms in real-time
\tRenderingServer.global_shader_parameter_set("WindDirection", wind_direction)
\tRenderingServer.global_shader_parameter_set("WindIntensity", wind_intensity)
\tRenderingServer.global_shader_parameter_set("GaleStrength", gale_strength)

## Call this to simulate a wind gust
func trigger_gust(strength: float = 1.0, duration: float = 2.0) -> void:
\tvar tween = create_tween()
\ttween.tween_property(self, "gale_strength", strength, duration * 0.3)
\ttween.tween_property(self, "gale_strength", 0.0, duration * 0.7)

## Set wind from a direction angle (0-360 degrees, 0 = North)
func set_wind_from_angle(angle_degrees: float, strength: float = 1.0) -> void:
\tvar angle_rad = deg_to_rad(angle_degrees)
\twind_direction = Vector3(sin(angle_rad), 0.0, cos(angle_rad)).normalized()
\twind_intensity = strength
'''
