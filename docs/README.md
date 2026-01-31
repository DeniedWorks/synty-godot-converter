# Synty-Converter Documentation

This directory contains comprehensive documentation for the synty-converter tool, which transforms Unity Synty asset packs into Godot 4.6-ready resources.

## Quick Links

| Resource | Description |
|----------|-------------|
| [User Guide](user-guide.md) | Getting started, installation, and basic usage |
| [Troubleshooting](troubleshooting.md) | Common issues and solutions |
| [Architecture](architecture.md) | System design and pipeline overview |

## Documentation Structure

The documentation is organized into three sections:

### Root Docs (Conceptual Guides)

High-level guides covering concepts, usage, and reference material.

| Document | Description |
|----------|-------------|
| [architecture.md](architecture.md) | System design, module relationships, data flow |
| [user-guide.md](user-guide.md) | Installation, CLI usage, GUI usage |
| [troubleshooting.md](troubleshooting.md) | Common errors and their solutions |
| [unity-reference.md](unity-reference.md) | Unity material/shader format reference |
| [shader-reference.md](shader-reference.md) | Supported shaders and property mappings |

### steps/ (Pipeline Documentation)

Detailed documentation for each step of the 12-stage conversion pipeline.

| Step | Document | Description |
|------|----------|-------------|
| 0 | [00-cli-orchestration.md](steps/00-cli-orchestration.md) | CLI interface and pipeline orchestration |
| 1 | [01-validate-inputs.md](steps/01-validate-inputs.md) | Input validation |
| 2 | [02-create-directories.md](steps/02-create-directories.md) | Output directory creation |
| 3 | [03-extract-unity-package.md](steps/03-extract-unity-package.md) | Unity package extraction |
| 4 | [04-parse-materials.md](steps/04-parse-materials.md) | Material file parsing |
| 5 | [05-parse-material-list.md](steps/05-parse-material-list.md) | Mesh-material mapping |
| 6 | [06-shader-detection.md](steps/06-shader-detection.md) | Shader detection and mapping |
| 7 | [07-tres-generation.md](steps/07-tres-generation.md) | Godot .tres generation |
| 8 | [08-copy-shaders.md](steps/08-copy-shaders.md) | Shader file deployment |
| 9 | [09-copy-textures.md](steps/09-copy-textures.md) | Texture copying |
| 10 | [10-copy-fbx.md](steps/10-copy-fbx.md) | FBX model copying |
| 11 | [11-generate-mapping.md](steps/11-generate-mapping.md) | Mapping file generation |
| 12 | [12-godot-conversion.md](steps/12-godot-conversion.md) | Godot mesh-to-scene conversion |
| - | [gui.md](steps/gui.md) | GUI wrapper documentation |

See [steps/README.md](steps/README.md) for pipeline overview and documentation standards.

### api/ (Code Reference)

Concise API documentation for programmatic usage.

| Module | Description |
|--------|-------------|
| [index.md](api/index.md) | API overview and quick reference |
| [converter.md](api/converter.md) | CLI entry point and orchestration |
| [unity_package.md](api/unity_package.md) | Package extraction and GUID mapping |
| [unity_parser.md](api/unity_parser.md) | Material file parsing |
| [shader_mapping.md](api/shader_mapping.md) | Shader detection and property mapping |
| [tres_generator.md](api/tres_generator.md) | Godot .tres file generation |
| [material_list.md](api/material_list.md) | MaterialList.txt parsing |
| [godot_converter.md](api/godot_converter.md) | GDScript FBX conversion |
| [constants.md](api/constants.md) | Shader GUID and property reference |

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines on improving documentation.

---

*Last Updated: 2026-01-31*
