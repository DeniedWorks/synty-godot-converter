# Synty to Godot Converter

[![Release](https://img.shields.io/github/v/release/DeniedWorks/synty-godot-converter)](https://github.com/DeniedWorks/synty-godot-converter/releases)
[![License](https://img.shields.io/github/license/DeniedWorks/synty-godot-converter)](LICENSE)

Convert [Synty Studios](https://syntystore.com/) POLYGON asset packs to Godot 4.5+ with proper materials, emissive glow effects, and automatic collision generation.

## Features

- **Prefab-level emissive materials** - Auto-detects mushrooms, crystals, lanterns, gems, portals and creates glowing materials
- **Automatic collision generation** - Trimesh collision for all props, skips LOD1+/FX/Glass
- **Smart texture matching** - Scoring algorithm finds the right texture even with naming inconsistencies
- **Material type detection** - Auto-detects glass, foliage, water, crystals, and standard materials
- **Wind animation shader** - Trees and foliage animate with realistic wind effects
- **Refractive glass/crystal shader** - Transparent materials with Fresnel and refraction
- **LOD handling** - Only shows LOD0 (highest detail), hides LOD1/2/3 automatically
- **Optional size normalization** - Uses Blender to measure models and scale to consistent sizes
- **GUI and CLI modes** - User-friendly interface or command-line automation

## Screenshots

*Screenshots coming soon*

<!-- Add screenshots here:
![GUI Screenshot](screenshots/gui.png)
![Converted Assets](screenshots/assets.png)
-->

## Requirements

- **Python 3.10+** (or just download the standalone .exe)
- **Blender 3.6+** - Optional, only needed for size normalization
- **Godot 4.5+** - Target engine version
- **Synty POLYGON source files** - The FBX source files from Synty (not just Unity packages)

### Godot Project Setup

The converter automatically:
1. Copies `synty_import_script.gd` to your project's `tools/` folder
2. Updates `project.godot` to use it for collision generation

No manual setup required!

## Installation

### Option 1: Download Release (Recommended)

1. Download `SyntyConverter.exe` from the [Releases](https://github.com/DeniedWorks/synty-godot-converter/releases) page
2. Run the executable - no installation required
3. Install [Blender](https://www.blender.org/download/) if you want size normalization

### Option 2: Run from Source

```bash
# Clone the repository
git clone https://github.com/DeniedWorks/synty-godot-converter.git
cd synty-godot-converter

# Run the GUI
python synty_converter_gui.py

# Or use the CLI
python synty_converter.py --pack POLYGON_Explorer_Kit --source "C:\Path\To\SourceFiles" --project "C:\Path\To\GodotProject"
```

## Usage

### GUI Mode

1. Launch `SyntyConverter.exe` or run `python synty_converter_gui.py`
2. Select your **Synty Source Folder** (the extracted `*_SourceFiles` folder)
3. Select your **Godot Project Folder** (where `project.godot` is)
4. Click **Convert**

### CLI Mode

```bash
python synty_converter.py \
    --pack POLYGON_Explorer_Kit \
    --source "C:\SyntyGodot\POLYGON_Explorer_Kit_SourceFiles" \
    --project "C:\Godot\Projects\MyGame"
```

#### CLI Options

| Option | Description |
|--------|-------------|
| `--pack`, `-p` | Pack name (default: auto-detected from folder) |
| `--source`, `-s` | Source directory with extracted Synty files (required) |
| `--project`, `-r` | Godot project root directory (required) |
| `--normalize-size` | Target size in meters (disabled by default) |
| `--filter`, `-f` | Only convert assets matching this name |
| `--dry-run`, `-n` | Preview without writing files |

## Output Structure

Converted assets are placed in your Godot project:

```
your-godot-project/
└── assets/synty/{PACK_NAME}/
    ├── Materials/     # ShaderMaterial .tres files
    ├── Textures/      # Copied PNG/TGA textures
    ├── Models/        # FBX files by category
    └── Prefabs/       # .tscn scenes ready to use
```

## Tested Packs

Successfully tested with:

- POLYGON_Apocalypse
- POLYGON_Dungeon_Pack
- POLYGON_Enchanted_Forest
- POLYGON_Explorer_Kit
- POLYGON_Fantasy_Kingdom
- POLYGON_Military
- POLYGON_Samurai_Empire
- POLYGON_Shops
- POLYGON_Street_Racer

Other POLYGON packs should work - please report issues if you encounter problems.

## How It Works

1. **Parse MaterialList** - Reads `MaterialList_*.txt` to map prefabs to materials and textures
2. **Copy Textures** - Finds and copies textures using a scoring algorithm for fuzzy matching
3. **Generate Materials** - Creates Godot ShaderMaterial files with appropriate shaders
4. **Generate Prefabs** - Creates `.tscn` scene files with FBX import and material overrides
5. **Size Normalization** - Uses Blender (headless) to measure FBX dimensions and scale uniformly

### Material Detection

| Type | Detection | Shader |
|------|-----------|--------|
| Glass | `*Glass*` in name, no texture | `refractive_transparent.gdshader` |
| Crystal/Gem | `*crystal*`, `*gem*`, `*jewel*` | `refractive_transparent.gdshader` + emission |
| Foliage | Tree/canopy materials with vertex colors | `foliage.gdshader` (wind animation) |
| Water | `*water*`, `*ocean*`, `*river*` | `water.gdshader` |
| Shiny | `*_Shiny*` suffix | `polygon_shader.gdshader` (metallic 0.8) |
| Standard | Everything else | `polygon_shader.gdshader` |

### Prefab-Level Emissive Materials

Even when glowing objects share textures with non-glowing props, the converter creates unique emissive materials per prefab:

| Type | Keywords | Glow Color |
|------|----------|------------|
| Crystal | `crystal`, `geode` | Blue |
| Gem | `gem`, `jewel`, `ruby`, `emerald`, `sapphire` | Purple/pink |
| Lantern | `lantern`, `lamp`, `torch`, `candle`, `campfire` | Warm orange |
| Mushroom | `mushroom`, `fungi`, `shroom` | Green |
| Magic | `portal`, `rune`, `spell`, `orb`, `magic` | Purple |

### Automatic Collision

The converter installs `synty_import_script.gd` which generates **static trimesh collision** when Godot imports FBX files:

| Mesh Type | Collision |
|-----------|-----------|
| LOD0 meshes | ✅ Trimesh collision |
| LOD1-5 meshes | ❌ Skipped |
| FX/Particle meshes | ❌ Skipped |
| Glass/Water meshes | ❌ Skipped |

Collision is generated automatically on import - no manual setup required.

## Shaders

Custom shaders are bundled and automatically installed to your Godot project:

| Shader | Features |
|--------|----------|
| `polygon_shader.gdshader` | Triplanar, emission, snow, overlay effects |
| `foliage.gdshader` | Wind animation, vertex color-based leaf/trunk detection |
| `refractive_transparent.gdshader` | Fresnel, refraction, depth translucency |
| `water.gdshader` | Waves, caustics, shore foam, distortion |

**Shader Author:** Giancarlo Niccolai
**Shader License:** MIT

## Building from Source

To build a standalone executable:

```bash
# Install PyInstaller
pip install pyinstaller

# Build (Windows)
build_exe.bat

# Or manually
pyinstaller SyntyConverter.spec
```

Output: `dist/SyntyConverter.exe`

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Test with at least one Synty pack
4. Submit a pull request

## License

MIT License - Copyright (c) 2025 Alex G Crisan

See [LICENSE](LICENSE) for details.

## Acknowledgments

- [Synty Studios](https://syntystore.com/) for creating amazing low-poly assets
- [Giancarlo Niccolai](https://github.com/jonnymind) for the original shader implementations
- [Godot Engine](https://godotengine.org/) for the awesome open-source game engine
