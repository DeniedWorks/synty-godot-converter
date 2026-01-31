# Synty Converter Pipeline Steps

This directory contains comprehensive documentation for each step of the synty-converter pipeline.

## Pipeline Overview

The converter follows a 12-step pipeline to transform Unity Synty asset packs into Godot-ready resources:

| Step | Document | Description |
|------|----------|-------------|
| 0 | [00-cli-orchestration.md](00-cli-orchestration.md) | CLI interface, configuration, and pipeline orchestration |
| 1 | [01-validate-inputs.md](01-validate-inputs.md) | Input validation (package, source files, Godot exe) |
| 2 | [02-create-directories.md](02-create-directories.md) | Output directory structure creation |
| 3 | [03-extract-unity-package.md](03-extract-unity-package.md) | Unity .unitypackage extraction and GUID mapping |
| 4 | [04-parse-materials.md](04-parse-materials.md) | Unity .mat file parsing |
| 5 | [05-parse-material-list.md](05-parse-material-list.md) | MaterialList.txt parsing for mesh-material mappings |
| 6 | [06-shader-detection.md](06-shader-detection.md) | 3-tier shader detection and property mapping |
| 7 | [07-tres-generation.md](07-tres-generation.md) | Godot .tres ShaderMaterial generation |
| 8 | [08-copy-shaders.md](08-copy-shaders.md) | Community shader file deployment |
| 9 | [09-copy-textures.md](09-copy-textures.md) | Texture copying with fallback resolution |
| 10 | [10-copy-fbx.md](10-copy-fbx.md) | FBX model copying with structure preservation |
| 11 | [11-generate-mapping.md](11-generate-mapping.md) | mesh_material_mapping.json generation |
| 12 | [12-godot-conversion.md](12-godot-conversion.md) | Godot CLI mesh-to-scene conversion |

## Step Number Mapping

The documentation files use logical numbering (00-12), but `converter.py` uses different step numbers in its runtime logging. This table shows the relationship:

| File | Doc Step | Runtime Step | Description |
|------|----------|--------------|-------------|
| 00-cli-orchestration.md | 0 | - | CLI parsing (before pipeline) |
| 01-validate-inputs.md | 1 | Step 1 | Validate inputs |
| 02-create-directories.md | 2 | Step 2 | Create directories |
| 03-extract-unity-package.md | 3 | Step 3 | Extract .unitypackage |
| 04-parse-materials.md | 4 | Step 4 | Parse .mat files |
| 05-parse-material-list.md | 5 | Step 5 | Part of shader mapping |
| 06-shader-detection.md | 6 | Step 5 | Part of shader mapping |
| 07-tres-generation.md | 7 | Step 6 | Generate .tres files |
| 08-copy-shaders.md | 8 | Step 7 | Copy shaders |
| 09-copy-textures.md | 9 | Step 8 | Copy textures |
| 10-copy-fbx.md | 10 | Step 9 | Copy FBX files |
| 11-generate-mapping.md | 11 | Step 10 | Generate mapping JSON |
| 12-godot-conversion.md | 12 | Steps 11-12 | project.godot + Godot CLI |

**Why the difference?**
- **Doc steps (0-12)**: Logical ordering for documentation - each file covers one conceptual area
- **Runtime steps (1-12)**: What appears in `converter.py` console output during execution
- **Merged steps**: Steps 5-6 in docs (MaterialList parsing + shader detection) are performed together as "Step 5: Parse material assignments and detect shaders" in the runtime

When debugging or cross-referencing logs with documentation, use this table to find the correct doc file for a given runtime step.

## Additional Documentation

| Document | Description |
|----------|-------------|
| [gui.md](gui.md) | CustomTkinter GUI wrapper documentation |

## Documentation Standards

Each step document follows a consistent structure:
- **Overview** - Purpose and responsibilities
- **Module/Function Analysis** - Line-by-line code documentation
- **Logic Flow** - Diagrams and pseudocode
- **Error Handling** - How errors are managed
- **Code Examples** - Practical usage
- **Notes for Doc Cleanup** - Findings about other docs needing updates

## Quick Stats

- **Total Documentation**: ~16,000 lines across 14 documents
- **Largest Module**: shader_mapping.py (2,339 lines of code, 1,910 lines of docs)
- **Most Complex Step**: Step 6 (Shader Detection) - 3-tier detection with 56 GUID mappings and 20 name patterns
