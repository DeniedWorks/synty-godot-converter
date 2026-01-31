# API Reference

> **Quick Reference Only** - This API documentation provides concise function signatures and brief descriptions. For detailed implementation explanations, see the [Step-by-Step Documentation](../steps/README.md).

## Overview

The Synty Shader Converter provides a Python API for programmatically converting Unity Synty assets to Godot 4.6 format. The API consists of several modules that work together in a pipeline architecture.

## Module Summary

| Module | Purpose | Step Doc |
|--------|---------|----------|
| [converter](converter.md) | CLI entry point and pipeline orchestration | [Step 0](../steps/00-cli-orchestration.md) |
| [unity_package](unity_package.md) | Package extraction and GUID mapping | [Step 3](../steps/03-extract-unity-package.md) |
| [unity_parser](unity_parser.md) | Material file parsing (regex-based `.mat` files) | [Step 4](../steps/04-parse-materials.md) |
| [shader_mapping](shader_mapping.md) | Shader detection and property mapping (core module) | [Step 6](../steps/06-shader-detection.md) |
| [tres_generator](tres_generator.md) | Godot `.tres` file generation | [Step 7](../steps/07-tres-generation.md) |
| [material_list](material_list.md) | MaterialList.txt parsing for mesh-material assignments | [Step 5](../steps/05-parse-material-list.md) |
| [godot_converter](godot_converter.md) | GDScript FBX to scene conversion | [Step 12](../steps/12-godot-conversion.md) |
| [constants](constants.md) | Shader GUID and property mapping reference | [Step 6](../steps/06-shader-detection.md) |

## Data Flow

```
                    +-------------------+
                    |  .unitypackage    |
                    +--------+----------+
                             |
                             v
                    +-------------------+
                    |  unity_package    |
                    |  - extract_unitypackage()
                    |  - GuidMap        |
                    +--------+----------+
                             |
                             v
                    +-------------------+
                    |  unity_parser     |
                    |  - parse_material_bytes()
                    |  - UnityMaterial  |
                    +--------+----------+
                             |
                             v
                    +-------------------+
                    |  shader_mapping   |
                    |  - detect_shader_type()
                    |  - map_material() |
                    |  - MappedMaterial |
                    +--------+----------+
                             |
                             v
                    +-------------------+
                    |  tres_generator   |
                    |  - generate_tres()|
                    |  - write_tres_file()
                    +--------+----------+
                             |
                             v
                    +-------------------+
                    |  Godot .tres      |
                    |  Material Files   |
                    +-------------------+
```

## Key Types

### GuidMap
Container for GUID mappings extracted from Unity packages. See [unity_package.md](unity_package.md#guidmap).

```python
from unity_package import GuidMap

# Fields:
#   guid_to_pathname: dict[str, str]     - GUID -> Unity asset path
#   guid_to_content: dict[str, bytes]    - GUID -> raw .mat file content
#   texture_guid_to_name: dict[str, str] - texture GUID -> filename
```

### ConversionConfig
Configuration dataclass for the conversion pipeline. See [converter.md](converter.md#conversionconfig).

```python
from converter import ConversionConfig

config = ConversionConfig(
    unity_package=Path("package.unitypackage"),
    source_files=Path("SourceFiles"),
    output_dir=Path("output"),
    godot_exe=Path("godot.exe"),
    dry_run=False,
    verbose=True
)
```

### ConversionStats
Statistics collected during conversion. See [converter.md](converter.md#conversionstats).

```python
from converter import ConversionStats

# Fields include:
#   materials_parsed: int
#   materials_generated: int
#   textures_copied: int
#   warnings: list[str]
#   errors: list[str]
```

## Quick Reference

### Convert a Package (Full Pipeline)

```python
from converter import ConversionConfig, run_conversion
from pathlib import Path

config = ConversionConfig(
    unity_package=Path("C:/SyntyComplete/PolygonNature/Nature.unitypackage"),
    source_files=Path("C:/SyntyComplete/PolygonNature/SourceFiles"),
    output_dir=Path("C:/Godot/Projects/converted_nature"),
    godot_exe=Path("C:/Godot/Godot_v4.6.exe"),
    dry_run=False,
    verbose=True
)

stats = run_conversion(config)
print(f"Generated {stats.materials_generated} materials")
```

### Extract Package Only

```python
from unity_package import extract_unitypackage, get_material_guids
from pathlib import Path

guid_map = extract_unitypackage(Path("package.unitypackage"))
material_guids = get_material_guids(guid_map)
print(f"Found {len(material_guids)} materials")
```

### Parse a Material

```python
from unity_parser import parse_material_bytes

content = guid_map.guid_to_content[material_guid]
material = parse_material_bytes(content)
print(f"Material: {material.name}, Shader: {material.shader}")
```

### Map to Godot Format

```python
from shader_mapping import map_material

mapped = map_material(unity_material, guid_map.texture_guid_to_name)
print(f"Shader: {mapped.shader_file}")
print(f"Textures: {mapped.textures}")
```

### Generate .tres File

```python
from tres_generator import generate_tres, write_tres_file

tres_content = generate_tres(
    mapped_material,
    shader_base="res://shaders",
    texture_base="res://textures"
)
write_tres_file(tres_content, Path("output/materials/MyMaterial.tres"))
```

## Error Handling

All modules use Python's standard exception handling:

- `FileNotFoundError` - Missing input files
- `tarfile.ReadError` - Invalid Unity package format
- `ValueError` - Invalid material format or mapping errors

The `run_conversion()` function catches exceptions and records them in `ConversionStats.errors`, allowing the pipeline to continue processing remaining assets.

## Logging

All modules use Python's `logging` module. Configure logging level via:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Or use the `--verbose` CLI flag for the converter.

---

*Last Updated: 2026-01-31*
