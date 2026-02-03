# Converter Module API

The `converter` module is the main CLI entry point and pipeline orchestrator for the Synty Shader Converter.

> **For detailed implementation:** See [Step 0: CLI Orchestration](../steps/00-cli-orchestration.md)

## Module Location

```
synty-converter/converter.py
```

## Usage

### Command Line

```bash
python converter.py \
    --unity-package "path/to/.unitypackage" \
    --source-files "path/to/SourceFiles" \
    --output "path/to/output" \
    --godot "path/to/Godot.exe" \
    --dry-run \
    --verbose
```

### Programmatic

```python
from converter import ConversionConfig, run_conversion
from pathlib import Path

config = ConversionConfig(
    unity_package=Path("package.unitypackage"),
    source_files=Path("SourceFiles"),
    output_dir=Path("output"),
    godot_exe=Path("godot.exe")
)

stats = run_conversion(config)
```

---

## Classes

### ConversionConfig

Configuration dataclass for the conversion pipeline.

```python
@dataclass
class ConversionConfig:
    unity_package: Path
    source_files: Path
    output_dir: Path
    godot_exe: Path
    dry_run: bool = False
    verbose: bool = False
    skip_fbx_copy: bool = False
    skip_godot_cli: bool = False
    skip_godot_import: bool = False
    keep_meshes_together: bool = False
    mesh_format: str = "tscn"
    filter_pattern: str | None = None
    godot_timeout: int = 600
    high_quality_textures: bool = False
    mesh_scale: float = 1.0
    output_subfolder: str | None = None
    flatten_output: bool = True
```

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `unity_package` | `Path` | required | Path to Unity `.unitypackage` file |
| `source_files` | `Path` | required | Path to `SourceFiles` folder containing `Textures/` and `FBX/` |
| `output_dir` | `Path` | required | Output directory for the generated Godot project |
| `godot_exe` | `Path` | required | Path to Godot 4.6 executable |
| `dry_run` | `bool` | `False` | Preview without writing files |
| `verbose` | `bool` | `False` | Enable verbose/debug logging |
| `skip_fbx_copy` | `bool` | `False` | Skip copying FBX files (use if `models/` already populated) |
| `skip_godot_cli` | `bool` | `False` | Skip running Godot CLI (generates materials only, no `.tscn` scenes) |
| `skip_godot_import` | `bool` | `False` | Skip Godot import phase (only run converter script) |
| `keep_meshes_together` | `bool` | `False` | Keep all meshes from one FBX in a single scene |
| `mesh_format` | `str` | `"tscn"` | Output format: `"tscn"` (text) or `"res"` (binary) |
| `filter_pattern` | `str \| None` | `None` | Only process FBX files matching this pattern (also filters textures) |
| `godot_timeout` | `int` | `600` | Timeout for Godot CLI operations in seconds |
| `high_quality_textures` | `bool` | `False` | Use BPTC compression for higher quality textures |
| `mesh_scale` | `float` | `1.0` | Scale factor for mesh vertices |
| `output_subfolder` | `str \| None` | `None` | Subfolder path prepended to pack folder names (e.g., "synty/") |
| `flatten_output` | `bool` | `True` | Skip mirroring source directory structure (flattening is default; use --retain-subfolders CLI flag to preserve structure) |

#### Example

```python
config = ConversionConfig(
    unity_package=Path("C:/SyntyComplete/PolygonNature/Nature.unitypackage"),
    source_files=Path("C:/SyntyComplete/PolygonNature/SourceFiles"),
    output_dir=Path("C:/Godot/Projects/converted_nature"),
    godot_exe=Path("C:/Godot/Godot_v4.6.exe"),
    dry_run=True,   # Preview only
    verbose=True,   # Show debug output
    skip_fbx_copy=False,
    skip_godot_cli=False,
    godot_timeout=900  # 15 minute timeout
)
```

---

### ConversionStats

Statistics dataclass collected during conversion.

```python
@dataclass
class ConversionStats:
    materials_parsed: int = 0
    materials_generated: int = 0
    materials_missing: int = 0
    textures_copied: int = 0
    textures_fallback: int = 0
    textures_missing: int = 0
    shaders_copied: int = 0
    fbx_copied: int = 0
    fbx_skipped: int = 0
    meshes_converted: int = 0
    godot_import_success: bool = False
    godot_convert_success: bool = False
    godot_timeout_occurred: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
```

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `materials_parsed` | `int` | Number of Unity materials successfully parsed |
| `materials_generated` | `int` | Number of Godot `.tres` materials generated |
| `materials_missing` | `int` | Number of materials referenced by meshes but not found |
| `textures_copied` | `int` | Number of texture files copied from .unitypackage |
| `textures_fallback` | `int` | Number of textures copied from SourceFiles/Textures fallback |
| `textures_missing` | `int` | Number of textures that could not be found |
| `shaders_copied` | `int` | Number of shader files copied |
| `fbx_copied` | `int` | Number of FBX files copied |
| `fbx_skipped` | `int` | Number of FBX files skipped (already existed) |
| `meshes_converted` | `int` | Number of `.tscn` scene files generated by Godot |
| `godot_import_success` | `bool` | Whether Godot import phase succeeded |
| `godot_convert_success` | `bool` | Whether Godot converter script succeeded |
| `godot_timeout_occurred` | `bool` | Whether Godot CLI timed out |
| `warnings` | `list[str]` | List of warning messages |
| `errors` | `list[str]` | List of error messages |

#### Example

```python
stats = run_conversion(config)

print(f"Parsed: {stats.materials_parsed}")
print(f"Generated: {stats.materials_generated}")

if stats.errors:
    print("Errors occurred:")
    for error in stats.errors:
        print(f"  - {error}")
```

---

## Functions

### run_conversion

Execute the full conversion pipeline. This is the main entry point for programmatic usage.

```python
def run_conversion(config: ConversionConfig) -> ConversionStats
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `config` | `ConversionConfig` | Conversion configuration |

#### Returns

`ConversionStats` with results and any warnings/errors.

#### Pipeline Steps

1. Validate inputs
2. Create output directory structure
3. Extract Unity package
4. Parse all `.mat` files
5. Map shader properties (parses `MaterialList*.txt`, builds shader cache with LOD inheritance)
6. Generate `.tres` files
7. Copy `.gdshader` files
8. Copy required textures
9. Copy FBX files (unless `skip_fbx_copy=True`)
10. Generate `mesh_material_mapping.json`
11. Generate `project.godot` with global shader uniforms
12. Run Godot CLI (unless `skip_godot_cli=True`)

#### Example

```python
from converter import ConversionConfig, run_conversion
from pathlib import Path

config = ConversionConfig(
    unity_package=Path("package.unitypackage"),
    source_files=Path("SourceFiles"),
    output_dir=Path("output"),
    godot_exe=Path("godot.exe")
)

stats = run_conversion(config)

if stats.errors:
    print(f"Conversion completed with {len(stats.errors)} errors")
else:
    print(f"Success! Generated {stats.materials_generated} materials")
```

---

### parse_args

Parse command-line arguments and validate inputs.

```python
def parse_args() -> ConversionConfig
```

#### Returns

`ConversionConfig` with validated paths.

#### Raises

- `SystemExit` - If required arguments are missing or invalid

#### CLI Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--unity-package` | Yes | Path to Unity `.unitypackage` file |
| `--source-files` | Yes | Path to `SourceFiles` folder |
| `--output` | Yes | Output directory for Godot project |
| `--godot` | Yes | Path to Godot 4.6 executable |
| `--dry-run` | No | Preview without writing files |
| `--verbose` | No | Enable verbose logging |
| `--skip-fbx-copy` | No | Skip copying FBX files |
| `--skip-godot-cli` | No | Skip running Godot CLI |
| `--skip-godot-import` | No | Skip Godot's import phase (only run converter script) |
| `--keep-meshes-together` | No | Keep all meshes from one FBX in a single scene |
| `--mesh-format` | No | Output format: `tscn` (text) or `res` (binary) |
| `--godot-timeout` | No | Timeout for Godot CLI (default: 600s) |
| `--filter` | No | Filter pattern for FBX filenames (also filters textures) |
| `--high-quality-textures` | No | Use BPTC compression for higher quality textures |
| `--mesh-scale` | No | Scale factor for mesh import (default: 1.0) |
| `--output-subfolder` | No | Subfolder path prepended to pack folder names (e.g., `synty/`) |
| `--retain-subfolders` | No | Preserve source directory structure in mesh output (default: flattened) |

---

### find_shader_in_project

Search for a shader file within a Godot project directory.

```python
def find_shader_in_project(shader_name: str, project_dir: Path) -> Path | None
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `shader_name` | `str` | Name of the shader file to find (e.g., `"polygon.gdshader"`) |
| `project_dir` | `Path` | Root directory of the Godot project to search |

#### Returns

`Path` to the shader file if found, `None` otherwise.

#### Behavior

- Recursively searches the project directory for the shader file
- Case-insensitive matching on Windows
- Returns the first match found

---

### get_shader_paths

Build a mapping of shader names to their paths, preferring project shaders over bundled ones.

```python
def get_shader_paths(
    project_dir: Path,
    shaders_src: Path,
    dry_run: bool
) -> dict[str, Path]
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `project_dir` | `Path` | Root directory of the Godot project |
| `shaders_src` | `Path` | Path to the converter's bundled shaders directory |
| `dry_run` | `bool` | If `True`, only log what would be done |

#### Returns

`dict[str, Path]` mapping shader names to their absolute paths.

#### Behavior

1. For each shader in `SHADER_FILES`, first searches the project directory
2. If found in project, uses that path (enables custom shader overrides)
3. If not found in project, uses the bundled shader from `shaders_src`
4. Logs which shaders are project-local vs bundled

---

### generate_converter_config

Generate the `converter_config.json` file for the GDScript converter.

```python
def generate_converter_config(
    output_dir: Path,
    pack_name: str,
    keep_meshes_together: bool = False,
    mesh_format: str = "tscn",
    filter_pattern: str | None = None,
    dry_run: bool = False
) -> None
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `output_dir` | `Path` | required | Output directory for the config file |
| `pack_name` | `str` | required | Name of the asset pack being converted |
| `keep_meshes_together` | `bool` | `False` | Keep all meshes from one FBX in a single scene |
| `mesh_format` | `str` | `"tscn"` | Output format: `"tscn"` or `"res"` |
| `filter_pattern` | `str \| None` | `None` | Filter pattern for FBX filenames |
| `dry_run` | `bool` | `False` | If `True`, only log what would be written |

#### Generated Config

```json
{
  "pack_name": "PolygonNature_SourceFiles",
  "keep_meshes_together": false,
  "mesh_format": "tscn",
  "filter_pattern": null
}
```

---

### write_conversion_log

Write or append conversion results to a log file.

```python
def write_conversion_log(
    project_dir: Path,
    pack_name: str,
    stats: ConversionStats,
    dry_run: bool = False
) -> None
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `project_dir` | `Path` | required | Root directory of the Godot project |
| `pack_name` | `str` | required | Name of the asset pack that was converted |
| `stats` | `ConversionStats` | required | Conversion statistics to log |
| `dry_run` | `bool` | `False` | If `True`, only log what would be written |

#### Behavior

- Writes to `{project_dir}/conversion_log.txt`
- Opens in append mode to preserve logs from previous conversions
- Includes timestamp, pack name, and full statistics summary
- Records any warnings or errors encountered

---

### setup_output_directories

Create the output directory structure.

```python
def setup_output_directories(output_dir: Path, dry_run: bool) -> None
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `output_dir` | `Path` | Root output directory |
| `dry_run` | `bool` | If `True`, only log what would be created |

#### Created Directories

```
output_dir/
    textures/
    materials/
    models/
    meshes/
```

> **Note:** The `shaders/` directory is created separately by `copy_shaders()` at the project root level, not inside the pack output directory.

---

### copy_shaders

Copy `.gdshader` files from the converter's bundled `shaders/` directory to output.

```python
def copy_shaders(shaders_dest: Path, dry_run: bool) -> int
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `shaders_dest` | `Path` | Destination directory for shaders |
| `dry_run` | `bool` | If `True`, only log what would be copied |

#### Returns

Number of shader files copied (or would be copied in dry run).

> **Note:** Source directory is determined internally from the converter installation path.

---

### copy_textures

Copy required texture files from `SourceFiles/Textures` to output.

```python
def copy_textures(
    source_textures: Path,
    output_textures: Path,
    required: set[str],
    dry_run: bool,
    fallback_texture: Path | None = None,
    texture_guid_to_path: dict[str, Path] | None = None,
    texture_name_to_guid: dict[str, str] | None = None,
    additional_texture_dirs: list[Path] | None = None,
) -> tuple[int, int, int]
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `source_textures` | `Path` | (required) | Source textures directory |
| `output_textures` | `Path` | (required) | Destination textures directory |
| `required` | `set[str]` | (required) | Set of texture names to copy |
| `dry_run` | `bool` | (required) | If `True`, only log what would be copied |
| `fallback_texture` | `Path \| None` | `None` | Optional fallback texture for missing files |
| `texture_guid_to_path` | `dict[str, Path] \| None` | `None` | GUID to temp file path mapping (from .unitypackage) |
| `texture_name_to_guid` | `dict[str, str] \| None` | `None` | Texture name to GUID reverse mapping |
| `additional_texture_dirs` | `list[Path] \| None` | `None` | Additional directories to search |

#### Returns

Tuple of `(textures_copied, textures_fallback, textures_missing)`.

---

### copy_fbx_files

Copy FBX files from `SourceFiles/FBX` to output, preserving directory structure.

```python
def copy_fbx_files(
    source_fbx_dir: Path,
    output_models_dir: Path,
    dry_run: bool,
    filter_pattern: str | None = None,
    additional_fbx_dirs: list[Path] | None = None,
) -> tuple[int, int]
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `source_fbx_dir` | `Path` | (required) | Path to `SourceFiles/FBX` directory |
| `output_models_dir` | `Path` | (required) | Path to `output/models` directory |
| `dry_run` | `bool` | (required) | If `True`, only log what would be copied |
| `filter_pattern` | `str \| None` | `None` | Optional filter pattern for FBX filenames (case-insensitive) |
| `additional_fbx_dirs` | `list[Path] \| None` | `None` | Additional FBX directories to search (for nested structures) |

#### Returns

Tuple of `(fbx_copied, fbx_skipped)`. Files are skipped if they already exist with the same size.

---

### run_godot_cli

Run Godot CLI in two phases: import and convert.

```python
def run_godot_cli(
    godot_exe: Path,
    project_dir: Path,
    timeout_seconds: int,
    dry_run: bool,
    skip_import: bool = False,
    keep_meshes_together: bool = False,
    mesh_format: str = "tscn",
    filter_pattern: str | None = None,
) -> tuple[bool, bool, bool]
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `godot_exe` | `Path` | (required) | Path to Godot 4.6 executable |
| `project_dir` | `Path` | (required) | Path to the Godot project directory |
| `timeout_seconds` | `int` | (required) | Maximum time for each phase |
| `dry_run` | `bool` | (required) | If `True`, only log what would be executed |
| `skip_import` | `bool` | `False` | Skip Godot import phase (manual import required) |
| `keep_meshes_together` | `bool` | `False` | Keep all meshes from one FBX in single scene |
| `mesh_format` | `str` | `"tscn"` | Output format: `"tscn"` or `"res"` |
| `filter_pattern` | `str \| None` | `None` | Optional FBX filename filter pattern |

#### Returns

Tuple of `(import_success, convert_success, timeout_occurred)`.

#### Phases

1. **Import Phase**: `godot --headless --import` - Imports FBX files into Godot
2. **Convert Phase**: `godot --headless --script res://godot_converter.gd` - Converts to `.tscn`

---

## Constants

### SHADER_FILES

List of shader files copied to output.

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

### TEXTURE_EXTENSIONS

Supported texture file extensions.

```python
TEXTURE_EXTENSIONS = [".png", ".tga", ".jpg", ".jpeg", ".PNG", ".TGA", ".JPG", ".JPEG"]
```

### PROJECT_GODOT_TEMPLATE

Template for generated `project.godot` file with global shader uniforms.

```python
PROJECT_GODOT_TEMPLATE = """; Engine configuration file.
; Generated by Synty Shader Converter

[application]
config/name="Synty Converted Assets"
config/features=PackedStringArray("4.6")

[shader_globals]
WindDirection={...}
WindIntensity={...}
GaleStrength={...}
MainLightDirection={...}
SkyColor={...}
EquatorColor={...}
GroundColor={...}
OceanWavesGradient={...}
"""
```

---

## Complete Example

```python
#!/usr/bin/env python3
"""Example: Convert a Synty asset pack."""

import logging
from pathlib import Path
from converter import ConversionConfig, run_conversion

# Enable verbose logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)s: %(message)s"
)

# Configure the conversion
config = ConversionConfig(
    unity_package=Path("C:/SyntyComplete/PolygonNature/Nature.unitypackage"),
    source_files=Path("C:/SyntyComplete/PolygonNature/SourceFiles"),
    output_dir=Path("C:/Godot/Projects/converted_nature"),
    godot_exe=Path("C:/Godot/Godot_v4.6.exe"),
    dry_run=False,
    verbose=True,
    skip_fbx_copy=False,
    skip_godot_cli=False,
    godot_timeout=900
)

# Run the conversion
stats = run_conversion(config)

# Report results
print(f"\nConversion Summary:")
print(f"  Materials: {stats.materials_generated}/{stats.materials_parsed}")
print(f"  Textures: {stats.textures_copied} copied, {stats.textures_missing} missing")
print(f"  FBX: {stats.fbx_copied} copied, {stats.fbx_skipped} skipped")
print(f"  Meshes: {stats.meshes_converted}")

if stats.warnings:
    print(f"\nWarnings ({len(stats.warnings)}):")
    for w in stats.warnings[:5]:
        print(f"  - {w}")

if stats.errors:
    print(f"\nErrors ({len(stats.errors)}):")
    for e in stats.errors:
        print(f"  - {e}")
    exit(1)
```
