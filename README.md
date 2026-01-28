# Synty Asset Converter v2

Convert Synty Unity asset packs to Godot 4.x format with proper material handling.

## Features

- **Unity Package Extraction**: Parse .unitypackage files to extract FBX models, textures, and material metadata
- **Smart Material Classification**: Detect material types (standard, foliage, water, glass, emissive) from Unity metadata
- **Shader Material Generation**: Create proper Godot ShaderMaterial .tres files for each material type
- **Import Configuration**: Generate .fbx.import files with correct material and mesh mappings
- **Mesh Extraction**: Configure Godot to extract meshes to separate .res files
- **Texture Management**: Copy and map textures with fuzzy matching

## Output Directory Structure

```
assets/synty/{PACK_NAME}/
├── Materials/          # .tres ShaderMaterial files
├── Textures/           # Copied PNG/TGA textures
├── Models/             # FBX files + .fbx.import configs
│   ├── Buildings/
│   ├── Characters/
│   ├── Environment/
│   └── Props/
├── Meshes/             # Extracted .res mesh files
└── Prefabs/            # .tscn scene files (optional)
```

## Installation

```bash
# Clone or download the converter
cd synty-converter-v2

# Install in development mode
pip install -e .

# Or just run directly
python -m synty_converter_v2 --help
```

## Usage

### Basic Conversion with Unity Package

```bash
python -m synty_converter_v2 \
    --pack POLYGON_Samurai_Empire \
    --unity "C:/Downloads/SamuraiEmpire.unitypackage" \
    --project "C:/Godot/Projects/MyGame"
```

### From Extracted Directories

```bash
python -m synty_converter_v2 \
    --pack POLYGON_Fantasy \
    --fbx-dir "./Extracted/Models" \
    --textures-dir "./Extracted/Textures" \
    --project "C:/Godot/Projects/MyGame"
```

### Preview Mode (Dry Run)

```bash
python -m synty_converter_v2 \
    --pack POLYGON_Samurai_Empire \
    --unity pkg.unitypackage \
    --dry-run
```

### Verbose Output

```bash
python -m synty_converter_v2 \
    --pack MyPack \
    --unity pkg.unitypackage \
    --project ./game \
    -v
```

## Required Shaders

This converter generates materials that require specific shaders from [godotshaders.com](https://godotshaders.com):

| Shader | URL |
|--------|-----|
| polygon_shader.gdshader | [Synty Polygon Drop-in](https://godotshaders.com/shader/synty-polygon-drop-in-replacement-for-polygonshader/) |
| foliage.gdshader | [Synty Core Foliage](https://godotshaders.com/shader/synty-core-drop-in-foliage-shader/) |
| water.gdshader | [Synty Core Water](https://godotshaders.com/shader/synty-core-drop-in-water-shader/) |
| refractive_transparent.gdshader | [Synty Refractive/Crystal](https://godotshaders.com/shader/synty-refractive_transparent-crystal-shader/) |
| clouds.gdshader | [Synty Core Clouds](https://godotshaders.com/shader/synty-core-drop-in-clouds-shader/) |
| sky_dome.gdshader | [Synty SkyDome](https://godotshaders.com/shader/synty-polygon-drop-in-replacement-for-skydome-shader/) |
| particles_unlit.gdshader | [Synty Particles](https://godotshaders.com/shader/synty-core-drop-in-particles-shader-generic_particlesunlit/) |

Download these shaders and place them in `assets/shaders/synty/` in your Godot project.

## Material Classification

Materials are classified based on Unity .mat file metadata:

| Type | Detection Method |
|------|------------------|
| FOLIAGE | Has `_Leaf_Texture`, `_Trunk_Texture`, or wind properties |
| EMISSIVE | Has `_Enable_Emission: 1` with emission texture/color |
| GLASS | `RenderType == "Transparent"` or name contains Glass/Window/Crystal |
| WATER | Name contains Water/Ocean/River |
| STANDARD | Default - standard PBR material |

## Global Shader Uniforms

Some shaders require global uniforms for features like wind animation. The converter can generate a setup script:

```gdscript
# Add as autoload: GlobalShaderUniforms
# Provides:
# - WindDirection (Vector3)
# - WindIntensity (float)
# - GaleStrength (float)
# - OceanWavesGradient (GradientTexture1D)
```

## API Usage

```python
from synty_converter_v2 import convert_pack
from pathlib import Path

# Simple conversion
summary = convert_pack(
    pack_name="POLYGON_Samurai_Empire",
    godot_project=Path("C:/Godot/Projects/MyGame"),
    unity_package=Path("C:/Downloads/SamuraiEmpire.unitypackage")
)

print(f"Converted {summary['materials']['total']} materials")
print(f"Processed {summary['models']} models")
```

## License

MIT License
