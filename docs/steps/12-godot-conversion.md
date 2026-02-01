# Step 12: Godot CLI Mesh Conversion

This document provides comprehensive documentation of the `godot_converter.gd` GDScript module, which runs inside Godot's headless mode to convert FBX files into individual mesh scenes with materials applied.

## Table of Contents

- [Overview](#overview)
- [How It Gets Invoked](#how-it-gets-invoked)
- [Script Architecture](#script-architecture)
  - [Class Variables](#class-variables)
  - [Entry Point (_init)](#entry-point-_init)
- [Configuration Loading](#configuration-loading)
  - [load_converter_config()](#load_converter_config)
  - [Configuration Options](#configuration-options)
  - [Pack Targeting with config_pack_name](#pack-targeting-with-config_pack_name)
- [Material Mapping Loading](#material-mapping-loading)
  - [load_material_mapping()](#load_material_mapping)
  - [Per-Pack Mapping Files](#per-pack-mapping-files)
  - [Mapping Format](#mapping-format)
- [Pack Discovery](#pack-discovery)
  - [discover_pack_folders()](#discover_pack_folders)
  - [Pack Structure Requirements](#pack-structure-requirements)
- [FBX Processing Pipeline](#fbx-processing-pipeline)
  - [process_pack_folder()](#process_pack_folder)
  - [find_fbx_files()](#find_fbx_files)
  - [process_fbx_file()](#process_fbx_file)
  - [find_mesh_instances()](#find_mesh_instances)
- [Mesh Extraction and Saving](#mesh-extraction-and-saving)
  - [extract_and_save_mesh()](#extract_and_save_mesh)
  - [save_fbx_as_single_scene()](#save_fbx_as_single_scene)
  - [_set_owner_recursive()](#_set_owner_recursive)
- [Material Assignment](#material-assignment)
  - [get_material_names_for_mesh()](#get_material_names_for_mesh)
  - [find_material_path()](#find_material_path)
  - [_detect_default_material()](#_detect_default_material)
  - [Comprehensive Fallback System](#comprehensive-fallback-system)
- [Mesh Deduplication](#mesh-deduplication)
  - [_strip_numeric_suffix()](#_strip_numeric_suffix)
  - [_try_material_fallbacks()](#_try_material_fallbacks)
  - [Duplicate Name Handling](#duplicate-name-handling)
- [Collision Mesh Handling](#collision-mesh-handling)
- [Utility Functions](#utility-functions)
  - [_ensure_directory_exists()](#_ensure_directory_exists)
  - [print_summary()](#print_summary)
- [Output Formats](#output-formats)
- [Error Handling](#error-handling)
- [Exit Codes](#exit-codes)
- [Complete Processing Flow](#complete-processing-flow)
- [Code Examples](#code-examples)
- [Notes for Doc Cleanup](#notes-for-doc-cleanup)

---

## Overview

The `godot_converter.gd` script is the Godot-side component of the Synty conversion pipeline. It runs inside Godot's headless mode (no GUI) and performs the final conversion step: extracting individual meshes from FBX files and saving them as `.tscn` or `.res` scene files with proper material assignments.

**Key Capabilities:**

- Converts FBX files to individual mesh scenes (one scene per MeshInstance3D)
- Alternatively saves all meshes from one FBX in a combined scene
- Applies pre-generated `.tres` materials as external references
- Handles collision meshes with green wireframe debug material
- Preserves directory structure from source FBX files
- Resolves duplicate mesh names across FBX files
- Supports FBX filename filtering for selective conversion
- Auto-discovers pack folders based on directory structure

**Script Location:** `godot_converter.gd` (at project root during conversion)

**Base Class:** `extends SceneTree` - Required for headless execution via `--script` flag

---

## How It Gets Invoked

The Python converter orchestrates Godot in two phases:

### Phase 1: Import (handled by Godot)

```bash
godot --headless --import --path <project_dir>
```

This triggers Godot's built-in import system to process all FBX files and generate `.import` metadata files. This phase can timeout on large packs.

### Phase 2: Convert (runs godot_converter.gd)

```bash
godot --headless --script res://godot_converter.gd --path <project_dir>
```

This phase runs the `godot_converter.gd` script, which:
1. Reads configuration from `converter_config.json`
2. Loads mesh-to-material mappings from JSON
3. Discovers pack folders
4. Processes each FBX file, extracting meshes and applying materials
5. Saves scene files to the `meshes/` directory

The Python converter generates `converter_config.json` and copies the GDScript to the project before running.

---

## Script Architecture

### Class Variables

The script uses several class-level variables to track state across the conversion process:

```gdscript
extends SceneTree

# Material mapping from mesh names to material name arrays
# Loaded from res://shaders/mesh_material_mapping.json
var mesh_to_materials: Dictionary = {}

# Tracks saved mesh output paths to detect duplicates
# Keys are output paths, values are true (used as a set)
var saved_mesh_names: Dictionary = {}

# Conversion statistics
var meshes_saved: int = 0      # Successfully converted meshes
var meshes_skipped: int = 0    # Skipped meshes (null mesh, no surfaces)
var warnings: int = 0          # Non-fatal warnings
var errors: int = 0            # Fatal errors

# Collision mesh visualization material
var collision_material: StandardMaterial3D = null

# Current pack being processed
var current_pack_folder: String = ""

# Default material for current pack (e.g., "PolygonNature_Mat_01_A")
var default_material_name: String = ""

# Configuration options from converter_config.json
var config_keep_meshes_together: bool = false   # All meshes in one scene
var config_mesh_format: String = "tscn"         # Output format
var config_filter_pattern: String = ""          # FBX filename filter
```

### Entry Point (_init)

The `_init()` function is called automatically when Godot runs the script with `--script`. It orchestrates the complete conversion process:

```gdscript
func _init() -> void:
    print("=" .repeat(60))
    print("Synty Shader Converter - FBX to Scene Files")
    print("=" .repeat(60))
    print("")

    # Create wireframe material for collision meshes
    collision_material = StandardMaterial3D.new()
    collision_material.albedo_color = Color(0.0, 1.0, 0.0)  # Green
    collision_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    collision_material.wireframe = true

    # Load converter configuration
    if not load_converter_config():
        printerr("Failed to parse converter_config.json. Aborting.")
        quit(1)
        return

    # Load the material mapping
    if not load_material_mapping():
        printerr("Failed to load material mapping. Aborting.")
        quit(1)
        return

    # Discover pack folders
    var pack_folders := discover_pack_folders()

    if pack_folders.is_empty():
        print("No pack folders found (directories with models/ and materials/ subdirs)")
        quit(0)
        return

    print("Found %d pack folder(s): %s" % [pack_folders.size(), ", ".join(pack_folders)])
    print("")

    # Process each pack folder
    for pack_folder in pack_folders:
        process_pack_folder(pack_folder)

    print("")
    print_summary()

    # Exit with error code only if no meshes were saved at all
    var exit_code := 0 if meshes_saved > 0 else 1
    quit(exit_code)
```

**Initialization Steps:**

1. Print header banner
2. Create collision material (green wireframe for debugging)
3. Load configuration from `converter_config.json`
4. Load mesh-to-material mapping from JSON
5. Auto-discover pack folders
6. Process each pack folder sequentially
7. Print summary statistics
8. Exit with appropriate code

---

## Configuration Loading

### load_converter_config()

Loads runtime configuration from `converter_config.json`, a file generated by the Python CLI:

```gdscript
func load_converter_config() -> bool:
    const CONFIG_PATH := "res://converter_config.json"

    if not FileAccess.file_exists(CONFIG_PATH):
        print("No converter_config.json found, using defaults")
        return true

    var file := FileAccess.open(CONFIG_PATH, FileAccess.READ)
    if file == null:
        push_warning("Failed to open converter_config.json: %s" % error_string(FileAccess.get_open_error()))
        return true  # Use defaults

    var json_text := file.get_as_text()
    file.close()

    var json := JSON.new()
    var parse_result := json.parse(json_text)

    if parse_result != OK:
        printerr("Failed to parse converter_config.json: %s at line %d" % [
            json.get_error_message(),
            json.get_error_line()
        ])
        return false

    var data = json.get_data()
    if not data is Dictionary:
        printerr("Invalid config format: expected Dictionary, got %s" % typeof(data))
        return false

    # Load options with defaults
    config_keep_meshes_together = data.get("keep_meshes_together", false)
    config_mesh_format = data.get("mesh_format", "tscn")
    var filter_val = data.get("filter_pattern", null)
    config_filter_pattern = filter_val if filter_val != null else ""

    print("Config loaded:")
    print("  keep_meshes_together: %s" % config_keep_meshes_together)
    print("  mesh_format: %s" % config_mesh_format)
    if not config_filter_pattern.is_empty():
        print("  filter_pattern: %s" % config_filter_pattern)

    return true
```

**Behavior:**
- Returns `true` if config loaded successfully OR if using defaults
- Returns `false` only on parse errors (causes script to abort)
- Missing file is not an error - defaults are used

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `keep_meshes_together` | `bool` | `false` | Keep all meshes from one FBX in a single scene file |
| `mesh_format` | `string` | `"tscn"` | Output format: `"tscn"` (text) or `"res"` (binary) |
| `filter_pattern` | `string` | `""` | Only process FBX files containing this pattern (case-insensitive) |
| `pack_name` | `string` | `""` | Target specific pack folder for conversion |

**Example converter_config.json:**

```json
{
  "keep_meshes_together": false,
  "mesh_format": "tscn",
  "filter_pattern": "Tree",
  "pack_name": "POLYGON_NatureBiomes"
}
```

### Pack Targeting with config_pack_name

When `pack_name` is specified in the config, the converter only processes that specific pack:

```gdscript
var config_pack_name: String = ""  # Target pack from config

func _init() -> void:
    # ...
    if not config_pack_name.is_empty():
        # Only process the specified pack
        var target_pack := "res://" + config_pack_name
        if DirAccess.dir_exists_absolute(target_pack):
            pack_folders = [target_pack]
            print("Targeting specific pack: %s" % config_pack_name)
        else:
            printerr("Specified pack not found: %s" % config_pack_name)
            quit(1)
            return
    else:
        # Discover all pack folders
        pack_folders = discover_pack_folders()
```

**Benefits:**
- Faster conversion when only one pack needs processing
- Prevents accidental processing of other packs in the project
- Used when Python converter specifies a target pack

---

## Material Mapping Loading

### load_material_mapping()

Loads the mesh-to-material mapping dictionary from the pack's `mesh_material_mapping.json`:

```gdscript
func load_material_mapping(pack_folder: String) -> bool:
    # Per-pack mapping file
    var mapping_path := pack_folder + "/mesh_material_mapping.json"

    if not FileAccess.file_exists(mapping_path):
        printerr("Material mapping file not found: %s" % mapping_path)
        return false

    var file := FileAccess.open(mapping_path, FileAccess.READ)
    if file == null:
        printerr("Failed to open mapping file: %s (error: %s)" % [
            mapping_path,
            error_string(FileAccess.get_open_error())
        ])
        return false

    var json_text := file.get_as_text()
    file.close()

    var json := JSON.new()
    var parse_result := json.parse(json_text)

    if parse_result != OK:
        printerr("Failed to parse JSON: %s at line %d" % [
            json.get_error_message(),
            json.get_error_line()
        ])
        return false

    var data = json.get_data()
    if not data is Dictionary:
        printerr("Invalid mapping format: expected Dictionary, got %s" % typeof(data))
        return false

    mesh_to_materials = data
    print("Loaded material mapping with %d mesh entries" % mesh_to_materials.size())

    return true
```

### Per-Pack Mapping Files

Each pack has its own mapping file in its directory:

```
res://POLYGON_NatureBiomes/
    mesh_material_mapping.json    <-- Pack-specific mapping
    materials/
    models/

res://POLYGON_Fantasy/
    mesh_material_mapping.json    <-- Separate mapping
    materials/
    models/
```

**Benefits of per-pack mappings:**
- No conflicts between packs with same mesh names
- Clean re-conversion replaces only that pack's mapping
- Simpler JSON structure (no pack prefixes needed)

**Loading per pack:**

```gdscript
func process_pack_folder(pack_folder: String) -> void:
    # Load this pack's material mapping
    if not load_material_mapping(pack_folder):
        printerr("Failed to load mapping for pack: %s" % pack_folder)
        return
    # ... process pack ...
```

### Mapping Format

The JSON maps mesh names to arrays of material names in surface order:

```json
{
  "SM_Env_Tree_01_LOD0": ["Tree_Trunk_Mat", "Tree_Leaves_Mat"],
  "SM_Env_Tree_01_LOD1": ["Tree_Trunk_Mat", "Tree_Leaves_Mat"],
  "SM_Prop_Rock_01": ["Rock_Mat"],
  "SM_Prop_Crystal_01": ["Crystal_Inner_Mat", "Crystal_Outer_Mat"]
}
```

- **Keys:** Mesh names (must match MeshInstance3D node names in FBX)
- **Values:** Arrays of material names in surface index order (surface 0, surface 1, etc.)
- Values can also be single strings (automatically converted to array)

---

## Pack Discovery

### discover_pack_folders()

Auto-discovers pack folders at the project root. A pack folder must have both `models/` and `materials/` subdirectories:

```gdscript
func discover_pack_folders() -> Array[String]:
    var result: Array[String] = []
    var root_dir := DirAccess.open("res://")

    if root_dir == null:
        printerr("Cannot open project root directory")
        return result

    root_dir.list_dir_begin()
    var dir_name := root_dir.get_next()

    while dir_name != "":
        if root_dir.current_is_dir():
            # Skip hidden and special directories
            if not dir_name.begins_with(".") and dir_name != "shaders" and dir_name != "meshes":
                var pack_path := "res://" + dir_name
                var models_path := pack_path + "/models"
                var materials_path := pack_path + "/materials"

                # Check if this is a valid pack folder (has both models and materials)
                if DirAccess.dir_exists_absolute(models_path) and DirAccess.dir_exists_absolute(materials_path):
                    result.append(pack_path)

        dir_name = root_dir.get_next()

    root_dir.list_dir_end()
    return result
```

**Discovery Rules:**

1. Scan root directory (`res://`)
2. Skip hidden directories (starting with `.`)
3. Skip special directories: `.godot`, `shaders`, `meshes`
4. For each remaining directory, check for:
   - `models/` subdirectory
   - `materials/` subdirectory
5. If both exist, add to pack list

### Pack Structure Requirements

A valid pack folder must have this structure:

```
res://PackName/
    models/                    # FBX files to convert (required)
        *.fbx
        subfolder/
            *.fbx
    materials/                 # Pre-generated .tres materials (required)
        MaterialName.tres
        ...
    meshes/                    # Output directory (created automatically)
```

---

## FBX Processing Pipeline

### process_pack_folder()

Processes a single pack folder, converting all FBX files within it:

```gdscript
func process_pack_folder(pack_folder: String) -> void:
    print("Processing pack: %s" % pack_folder)
    current_pack_folder = pack_folder

    # Detect default material for this pack
    var materials_path := pack_folder + "/materials"
    default_material_name = _detect_default_material(materials_path)
    if not default_material_name.is_empty():
        print("  Default material: %s" % default_material_name)
    else:
        print("  No default material found (no *_Mat_01_A.tres files)")

    var models_path := pack_folder + "/models"
    var meshes_output := pack_folder + "/meshes"

    # Ensure output directory exists
    _ensure_directory_exists(meshes_output)

    # Find all FBX files in the pack's models directory
    var fbx_files := find_fbx_files(models_path)

    if fbx_files.is_empty():
        print("  No FBX files found in %s" % models_path)
        return

    var total_fbx := fbx_files.size()
    print("  Found %d FBX file(s) to process" % total_fbx)

    for i in range(fbx_files.size()):
        var fbx_path := fbx_files[i]
        print("[%d/%d] Processing: %s" % [i + 1, total_fbx, fbx_path.get_file()])
        process_fbx_file(fbx_path)
```

**Processing Steps:**

1. Set `current_pack_folder` for relative path calculations
2. Detect default material (scans for `*_Mat_01_A.tres`)
3. Ensure output `meshes/` directory exists
4. Find all FBX files recursively
5. Process each FBX file with progress indicator

### find_fbx_files()

Recursively finds all FBX files in a directory, applying filter pattern if set:

```gdscript
func find_fbx_files(dir_path: String) -> Array[String]:
    var result: Array[String] = []
    var dir := DirAccess.open(dir_path)

    if dir == null:
        push_warning("Cannot open directory: %s (error: %s)" % [
            dir_path,
            error_string(DirAccess.get_open_error())
        ])
        return result

    dir.list_dir_begin()
    var file_name := dir.get_next()

    while file_name != "":
        var full_path := dir_path.path_join(file_name)

        if dir.current_is_dir():
            # Skip hidden directories
            if not file_name.begins_with("."):
                # Recursively search subdirectories
                result.append_array(find_fbx_files(full_path))
        else:
            # Check for FBX files (case-insensitive)
            if file_name.to_lower().ends_with(".fbx"):
                # Apply filter pattern if set
                if config_filter_pattern.is_empty():
                    result.append(full_path)
                else:
                    # Case-insensitive pattern matching
                    var base_name := file_name.get_basename()
                    if base_name.to_lower().contains(config_filter_pattern.to_lower()):
                        result.append(full_path)

        file_name = dir.get_next()

    dir.list_dir_end()
    return result
```

**Features:**

- Recursive directory traversal
- Skips hidden directories (starting with `.`)
- Case-insensitive `.fbx` extension matching
- Case-insensitive filter pattern matching on filename (basename only)
- Returns empty array if directory cannot be opened

### process_fbx_file()

Converts a single FBX file by loading it and extracting meshes:

```gdscript
func process_fbx_file(fbx_path: String) -> void:
    var fbx_name := fbx_path.get_file().get_basename()
    print("  Processing: %s" % fbx_path)

    # Determine relative directory for output (mirror models/ structure in meshes/)
    var models_prefix := current_pack_folder + "/models/"
    var relative_path := fbx_path.trim_prefix(models_prefix)
    var relative_dir := relative_path.get_base_dir()

    # Load the FBX as a PackedScene
    var packed_scene: PackedScene = load(fbx_path)
    if packed_scene == null:
        printerr("    ERROR: Failed to load FBX: %s" % fbx_path)
        errors += 1
        return

    # Instantiate the scene to traverse it
    var scene_instance: Node = packed_scene.instantiate()
    if scene_instance == null:
        printerr("    ERROR: Failed to instantiate scene: %s" % fbx_path)
        errors += 1
        return

    # Find all MeshInstance3D nodes
    var mesh_instances := find_mesh_instances(scene_instance)

    if mesh_instances.is_empty():
        print("    No meshes found in FBX")
        scene_instance.free()
        return

    print("    Found %d mesh(es)" % mesh_instances.size())

    if config_keep_meshes_together:
        # Keep all meshes together in a single scene file
        save_fbx_as_single_scene(scene_instance, mesh_instances, relative_dir, fbx_name)
    else:
        # Extract and save each mesh separately (default behavior)
        for mesh_instance in mesh_instances:
            extract_and_save_mesh(mesh_instance, relative_dir, fbx_name)

    # Clean up
    scene_instance.free()
```

**Key Steps:**

1. Calculate relative path for output directory mirroring
2. Load FBX as `PackedScene` via Godot's import system
3. Instantiate to traverse the node tree
4. Find all `MeshInstance3D` nodes
5. Either save as single combined scene or extract individually
6. Free the instantiated scene to avoid memory leaks

### find_mesh_instances()

Recursively finds all MeshInstance3D nodes in a scene tree:

```gdscript
func find_mesh_instances(node: Node) -> Array[MeshInstance3D]:
    var result: Array[MeshInstance3D] = []

    if node is MeshInstance3D:
        result.append(node as MeshInstance3D)

    for child in node.get_children():
        result.append_array(find_mesh_instances(child))

    return result
```

**Features:**

- Depth-first traversal
- Includes the root node if it's a MeshInstance3D
- Returns all MeshInstance3D nodes in tree order

---

## Mesh Extraction and Saving

### extract_and_save_mesh()

Extracts a mesh from a MeshInstance3D and saves it as an individual scene file:

```gdscript
func extract_and_save_mesh(mesh_instance: MeshInstance3D, relative_dir: String, fbx_name: String) -> void:
    var mesh_name := String(mesh_instance.name)
    var original_mesh := mesh_instance.mesh

    if original_mesh == null:
        print("      Skipping %s (null mesh)" % mesh_name)
        meshes_skipped += 1
        return

    if original_mesh.get_surface_count() == 0:
        print("      Skipping %s (no surfaces)" % mesh_name)
        meshes_skipped += 1
        return

    # Check if this is a collision mesh
    var is_collision := mesh_name.to_lower().contains("collision") or mesh_name.to_lower().ends_with("_col")

    # Create a MeshInstance3D node for the scene
    var scene_mesh_instance := MeshInstance3D.new()
    scene_mesh_instance.mesh = original_mesh  # Use original mesh (no duplication)
    scene_mesh_instance.name = mesh_name

    # Determine output path
    var meshes_dir := current_pack_folder + "/meshes"
    var file_ext := "." + config_mesh_format
    var output_path: String
    if relative_dir.is_empty():
        output_path = "%s/%s%s" % [meshes_dir, mesh_name, file_ext]
    else:
        output_path = "%s/%s/%s%s" % [meshes_dir, relative_dir, mesh_name, file_ext]

    if is_collision:
        # Apply green wireframe material for collision meshes
        for i in range(original_mesh.get_surface_count()):
            scene_mesh_instance.set_surface_override_material(i, collision_material)

        _ensure_directory_exists(output_path.get_base_dir())

        var scene := PackedScene.new()
        var pack_result := scene.pack(scene_mesh_instance)
        if pack_result != OK:
            printerr("      ERROR: Failed to pack collision scene: %s" % mesh_name)
            scene_mesh_instance.free()
            errors += 1
            return

        var save_result := ResourceSaver.save(scene, output_path)
        scene_mesh_instance.free()

        if save_result == OK:
            print("      Saved collision: %s (green wireframe)" % mesh_name)
            meshes_saved += 1
        else:
            printerr("      ERROR: Failed to save collision scene: %s" % mesh_name)
            errors += 1
        return  # Skip normal material lookup for collision meshes

    # Get materials for this mesh
    var material_names := get_material_names_for_mesh(mesh_name)
    var materials_applied := 0

    # Apply materials as surface overrides
    var materials_dir := current_pack_folder + "/materials"
    for i in range(original_mesh.get_surface_count()):
        if i < material_names.size() and material_names[i] != "":
            var mat_name := material_names[i]
            var material_path := find_material_path(mat_name, materials_dir)

            if material_path.is_empty():
                print("      Warning: Material not found: %s (tried fallbacks)" % mat_name)
                warnings += 1
                continue

            var material: Material = load(material_path)
            if material == null:
                print("      Warning: Failed to load material: %s" % material_path)
                warnings += 1
                continue

            scene_mesh_instance.set_surface_override_material(i, material)
            materials_applied += 1

    # Handle duplicate mesh names
    if saved_mesh_names.has(output_path):
        var unique_name := "%s_%s" % [mesh_name, fbx_name]
        if relative_dir.is_empty():
            output_path = "%s/%s%s" % [meshes_dir, unique_name, file_ext]
        else:
            output_path = "%s/%s/%s%s" % [meshes_dir, relative_dir, unique_name, file_ext]
        print("      Note: Renamed to %s (duplicate name)" % unique_name)
        warnings += 1

    _ensure_directory_exists(output_path.get_base_dir())

    # Pack and save as scene
    var scene := PackedScene.new()
    var pack_result := scene.pack(scene_mesh_instance)

    if pack_result != OK:
        printerr("      ERROR: Failed to pack scene: %s (error: %s)" % [
            output_path,
            error_string(pack_result)
        ])
        scene_mesh_instance.free()
        errors += 1
        return

    var save_result := ResourceSaver.save(scene, output_path)
    scene_mesh_instance.free()

    if save_result != OK:
        printerr("      ERROR: Failed to save scene: %s (error: %s)" % [
            output_path,
            error_string(save_result)
        ])
        errors += 1
        return

    # Track saved mesh name
    saved_mesh_names[output_path] = true

    if materials_applied > 0:
        print("      Saved: %s (%d materials)" % [output_path.get_file(), materials_applied])
    else:
        print("      Saved: %s (no materials)" % output_path.get_file())

    meshes_saved += 1
```

**Processing Flow:**

1. **Validation:** Skip null meshes or meshes with no surfaces
2. **Collision Detection:** Check if name contains "collision" or ends with "_col"
3. **Collision Handling:** Apply green wireframe material and save immediately
4. **Material Lookup:** Get material names from mapping, with fallback support
5. **Material Loading:** Load each `.tres` file and apply as surface override
6. **Duplicate Handling:** Append FBX name if mesh name already saved
7. **Saving:** Pack and save using `ResourceSaver.save()`

### save_fbx_as_single_scene()

Saves all meshes from an FBX in a single combined scene (used when `--keep-meshes-together` is enabled):

```gdscript
func save_fbx_as_single_scene(scene_root: Node, mesh_instances: Array[MeshInstance3D], relative_dir: String, fbx_name: String) -> void:
    var materials_dir := current_pack_folder + "/materials"
    var materials_applied := 0

    # Apply materials to each mesh instance
    for mesh_instance in mesh_instances:
        var mesh_name := String(mesh_instance.name)
        var original_mesh := mesh_instance.mesh

        if original_mesh == null or original_mesh.get_surface_count() == 0:
            continue

        # Check if this is a collision mesh
        var is_collision := mesh_name.to_lower().contains("collision") or mesh_name.to_lower().ends_with("_col")

        if is_collision:
            for i in range(original_mesh.get_surface_count()):
                mesh_instance.set_surface_override_material(i, collision_material)
            continue

        # Get and apply materials
        var material_names := get_material_names_for_mesh(mesh_name)
        for i in range(original_mesh.get_surface_count()):
            if i < material_names.size() and material_names[i] != "":
                var mat_name := material_names[i]
                var material_path := find_material_path(mat_name, materials_dir)

                if material_path.is_empty():
                    print("      Warning: Material not found: %s" % mat_name)
                    warnings += 1
                    continue

                var material: Material = load(material_path)
                if material == null:
                    print("      Warning: Failed to load material: %s" % material_path)
                    warnings += 1
                    continue

                mesh_instance.set_surface_override_material(i, material)
                materials_applied += 1

    # Determine output path
    var meshes_dir := current_pack_folder + "/meshes"
    var output_path: String
    var file_ext := "." + config_mesh_format

    if relative_dir.is_empty():
        output_path = "%s/%s%s" % [meshes_dir, fbx_name, file_ext]
    else:
        output_path = "%s/%s/%s%s" % [meshes_dir, relative_dir, fbx_name, file_ext]

    _ensure_directory_exists(output_path.get_base_dir())

    # Create a new root node with proper ownership for all children
    var new_root := Node3D.new()
    new_root.name = fbx_name

    # Duplicate children and add to new root with proper ownership
    for child in scene_root.get_children():
        var duplicated := child.duplicate()
        new_root.add_child(duplicated)
        _set_owner_recursive(duplicated, new_root)

    # Pack and save
    var scene := PackedScene.new()
    var pack_result := scene.pack(new_root)

    if pack_result != OK:
        printerr("      ERROR: Failed to pack scene: %s (error: %s)" % [
            output_path,
            error_string(pack_result)
        ])
        new_root.free()
        errors += 1
        return

    var save_result := ResourceSaver.save(scene, output_path)
    new_root.free()

    if save_result != OK:
        printerr("      ERROR: Failed to save scene: %s (error: %s)" % [
            output_path,
            error_string(save_result)
        ])
        errors += 1
        return

    print("      Saved combined scene: %s (%d meshes, %d materials)" % [
        output_path.get_file(), mesh_instances.size(), materials_applied
    ])
    meshes_saved += 1
```

**Key Differences from Individual Extraction:**

- Applies materials in-place on the original mesh instances
- Creates a new `Node3D` root with duplicated children
- Uses `_set_owner_recursive()` to set ownership for proper packing
- Saves all meshes in a single file named after the FBX

### _set_owner_recursive()

Recursively sets ownership for all nodes (required for `PackedScene.pack()` to include all nodes):

```gdscript
func _set_owner_recursive(node: Node, owner: Node) -> void:
    node.owner = owner
    for child in node.get_children():
        _set_owner_recursive(child, owner)
```

---

## Material Assignment

### get_material_names_for_mesh()

Looks up material names for a mesh, handling Godot's numeric suffixes and various fallback patterns:

```gdscript
func get_material_names_for_mesh(mesh_name: String) -> Array[String]:
    var material_names_result: Array[String] = []
    var lookup_name := mesh_name

    # Try exact match first
    if not mesh_to_materials.has(lookup_name):
        # Try stripping numeric suffixes like "_001", "_002"
        var base_name := _strip_numeric_suffix(mesh_name)
        if base_name != mesh_name and mesh_to_materials.has(base_name):
            lookup_name = base_name
        else:
            # Try fallback patterns for common naming mismatches
            var fallback_name := _try_material_fallbacks(base_name if base_name != mesh_name else mesh_name)
            if not fallback_name.is_empty():
                lookup_name = fallback_name
            else:
                # Final fallback: use default material if available
                if not default_material_name.is_empty():
                    print("      Using default material for mesh '%s': %s" % [mesh_name, default_material_name])
                    material_names_result.append(default_material_name)
                    return material_names_result
                else:
                    print("      Warning: No material mapping for mesh '%s'" % mesh_name)
                    warnings += 1
                    return material_names_result

    var material_names = mesh_to_materials[lookup_name]

    # Handle both array and single string formats
    if material_names is String:
        material_names = [material_names]

    if not material_names is Array:
        print("      Warning: Invalid material format for mesh '%s'" % lookup_name)
        warnings += 1
        return material_names_result

    # Collect material names (preserve empty strings for surface index alignment)
    for material_name in material_names:
        if material_name is String and not material_name.is_empty():
            material_names_result.append(material_name)
        else:
            material_names_result.append("")

    return material_names_result
```

**Lookup Strategy (in order):**

1. Exact match in mapping
2. Strip numeric suffixes (`_001`, `_002`) and retry
3. Try fallback patterns (SK_ to SM_, remove _Static, etc.)
4. Use default material if available
5. Return empty array (log warning)

### find_material_path()

Finds the actual path to a material file, handling naming mismatches:

```gdscript
func find_material_path(mat_name: String, materials_dir: String) -> String:
    var base_path := materials_dir.path_join(mat_name + ".tres")

    # 1. Try exact name
    # NOTE: Use ResourceLoader.exists() instead of FileAccess.file_exists()
    # FileAccess has known issues with res:// paths in headless mode
    if ResourceLoader.exists(base_path):
        return base_path

    # 2. Strip Polygon*_Mat_ or Polygon*_ prefix
    var stripped := mat_name
    if stripped.begins_with("Polygon"):
        var mat_idx := stripped.find("_Mat_")
        if mat_idx > 0:
            stripped = stripped.substr(mat_idx + 5)  # len("_Mat_") = 5
        else:
            var first_underscore := stripped.find("_")
            if first_underscore > 0:
                stripped = stripped.substr(first_underscore + 1)

    # 3. Try stripped name
    var stripped_path := materials_dir.path_join(stripped + ".tres")
    if ResourceLoader.exists(stripped_path):
        return stripped_path

    # 4. Try with _01 suffix if not already present
    if not stripped.ends_with("_01"):
        var with_suffix_path := materials_dir.path_join(stripped + "_01.tres")
        if ResourceLoader.exists(with_suffix_path):
            return with_suffix_path

    # 5. Not found
    return ""
```

**Fallback Order:**

1. Exact name match (`MaterialName.tres`)
2. Strip `Polygon*_Mat_` prefix (e.g., `PolygonFantasyKingdom_Mat_Glass` -> `Glass.tres`)
3. Strip `Polygon*_` prefix (e.g., `PolygonNature_Tree` -> `Tree.tres`)
4. Add `_01` suffix if not present (e.g., `Glass` -> `Glass_01.tres`)

**Important Note:** Uses `ResourceLoader.exists()` instead of `FileAccess.file_exists()` because `FileAccess` has known issues with `res://` paths during headless execution and with `.remap` files created by Godot's import system.

### _detect_default_material()

Scans the materials directory for the pack's default material:

```gdscript
func _detect_default_material(materials_dir: String) -> String:
    var dir := DirAccess.open(materials_dir)
    if dir == null:
        return ""

    dir.list_dir_begin()
    var file_name := dir.get_next()

    while file_name != "":
        if not dir.current_is_dir():
            if file_name.to_lower().ends_with(".tres"):
                var base_name := file_name.get_basename()
                if base_name.ends_with("_Mat_01_A"):
                    dir.list_dir_end()
                    return base_name

        file_name = dir.get_next()

    dir.list_dir_end()
    return ""
```

**Pattern:** Looks for `*_Mat_01_A.tres` files, which is the standard naming for Synty pack base materials (e.g., `PolygonFantasyKingdom_Mat_01_A.tres`).

### Comprehensive Fallback System

The converter implements a comprehensive fallback system to handle naming mismatches between FBX mesh names and MaterialList.txt entries.

#### Fallback Order

1. **Exact match** - Direct lookup in mesh_to_materials
2. **Prefix swap (SK_/SM_)** - Skeletal to static mesh conversion
3. **Suffix handling** - Remove _Static, _LOD, _001 suffixes
4. **Fuzzy matching** - Find closest match when exact fails
5. **Default material** - Use pack's default material as last resort

#### _try_material_fallbacks() Function

```gdscript
func _try_material_fallbacks(mesh_name: String) -> String:
    # Fallback 1: SK_ to SM_ conversion (skeletal to static mesh)
    if mesh_name.begins_with("SK_"):
        var sm_name := "SM_" + mesh_name.substr(3)
        if mesh_to_materials.has(sm_name):
            print("      Fallback: '%s' -> '%s' (SK_ to SM_)" % [mesh_name, sm_name])
            return sm_name

    # Fallback 2: SM_ to SK_ conversion (reverse)
    if mesh_name.begins_with("SM_"):
        var sk_name := "SK_" + mesh_name.substr(3)
        if mesh_to_materials.has(sk_name):
            print("      Fallback: '%s' -> '%s' (SM_ to SK_)" % [mesh_name, sk_name])
            return sk_name

    # Fallback 3: Remove _Static suffix
    if mesh_name.ends_with("_Static"):
        var base_name := mesh_name.substr(0, mesh_name.length() - 7)
        if mesh_to_materials.has(base_name):
            print("      Fallback: '%s' -> '%s' (removed _Static)" % [mesh_name, base_name])
            return base_name

    # Fallback 4: Remove _LOD suffixes (_LOD0, _LOD1, _LOD2, etc.)
    var lod_regex := RegEx.new()
    lod_regex.compile("_LOD\\d+$")
    var lod_match := lod_regex.search(mesh_name)
    if lod_match:
        var base_name := mesh_name.substr(0, lod_match.get_start())
        if mesh_to_materials.has(base_name):
            print("      Fallback: '%s' -> '%s' (removed LOD suffix)" % [mesh_name, base_name])
            return base_name

    # Fallback 5: Remove numeric suffixes (_001, _002, etc.)
    var num_regex := RegEx.new()
    num_regex.compile("_\\d{3}$")
    var num_match := num_regex.search(mesh_name)
    if num_match:
        var base_name := mesh_name.substr(0, num_match.get_start())
        if mesh_to_materials.has(base_name):
            print("      Fallback: '%s' -> '%s' (removed numeric suffix)" % [mesh_name, base_name])
            return base_name

    # Fallback 6: Remove _Preset suffix
    if mesh_name.ends_with("_Preset"):
        var base_name := mesh_name.substr(0, mesh_name.length() - 7)
        if mesh_to_materials.has(base_name):
            print("      Fallback: '%s' -> '%s' (removed _Preset)" % [mesh_name, base_name])
            return base_name

    # Fallback 7: Remove sub-component suffixes
    var component_suffixes: Array[String] = [
        "_Cork", "_Liquid", "_Handle",
        "_Door_1", "_Door_2", "_Door_01", "_Door_02",
        "_Drawer_01", "_Drawer_02", "_Drawer_03",
        "_Chains_01", "_Chains_02",
        "_Arrow_01", "_Arrow_02", "_Arrow_03"
    ]

    for suffix in component_suffixes:
        if mesh_name.ends_with(suffix):
            var base_name := mesh_name.substr(0, mesh_name.length() - suffix.length())
            if mesh_to_materials.has(base_name):
                print("      Fallback: '%s' -> '%s' (removed %s)" % [mesh_name, base_name, suffix])
                return base_name

    # Fallback 8: Fuzzy matching - find closest mesh name
    var best_match := _find_fuzzy_match(mesh_name)
    if not best_match.is_empty():
        print("      Fallback: '%s' -> '%s' (fuzzy match)" % [mesh_name, best_match])
        return best_match

    return ""
```

#### Fuzzy Matching

When exact and suffix-based fallbacks fail, the converter attempts fuzzy matching:

```gdscript
func _find_fuzzy_match(mesh_name: String) -> String:
    # Try to find a mapping key that shares a common prefix
    var best_match := ""
    var best_score := 0

    for key in mesh_to_materials.keys():
        var score := _calculate_match_score(mesh_name, key)
        if score > best_score:
            best_score = score
            best_match = key

    # Only accept matches with a reasonable score
    if best_score >= 5:  # Minimum threshold
        return best_match

    return ""
```

**Fallback Patterns Summary:**

| Pattern | Example | Purpose |
|---------|---------|---------|
| SK_ -> SM_ | `SK_Chr_Knight` -> `SM_Chr_Knight` | Skeletal meshes share materials with static |
| SM_ -> SK_ | `SM_Chr_Knight` -> `SK_Chr_Knight` | Reverse lookup for edge cases |
| Remove _Static | `SM_Barrel_Static` -> `SM_Barrel` | Static variants use base materials |
| Remove _LOD* | `SM_Tree_01_LOD0` -> `SM_Tree_01` | LOD variants use base materials |
| Remove _001 | `SM_Rock_01_001` -> `SM_Rock_01` | Godot import duplicates |
| Remove _Preset | `SM_Chair_Preset` -> `SM_Chair` | Preset variants use base materials |
| Remove components | `SM_Chest_Cork` -> `SM_Chest` | Sub-components use parent materials |
| Fuzzy match | `SM_Env_Tree_Pine` -> `SM_Env_Tree_Pine_01` | Closest available match |

---

## Mesh Deduplication

### _strip_numeric_suffix()

Strips trailing numeric suffixes added by Godot's FBX importer:

```gdscript
func _strip_numeric_suffix(name: String) -> String:
    var regex := RegEx.new()
    regex.compile("(_?\\d+)$")
    return regex.sub(name, "")
```

**Examples:**

- `SM_Tree_01_001` -> `SM_Tree_01`
- `Mesh_002` -> `Mesh`
- `SM_Rock` -> `SM_Rock` (unchanged)

**Pattern:** Removes optional underscore followed by digits at end of string.

### Duplicate Name Handling

When the same mesh name appears in multiple FBX files, the script appends the source FBX name:

```gdscript
# From extract_and_save_mesh():
if saved_mesh_names.has(output_path):
    var unique_name := "%s_%s" % [mesh_name, fbx_name]
    # ... update output_path ...
    print("      Note: Renamed to %s (duplicate name)" % unique_name)
    warnings += 1
```

**Example:**
- First FBX: `SM_Rock_01.tscn`
- Second FBX: `SM_Rock_01_Props.tscn` (appended source FBX name)

---

## Collision Mesh Handling

Collision meshes are identified by name and handled specially:

```gdscript
var is_collision := mesh_name.to_lower().contains("collision") or mesh_name.to_lower().ends_with("_col")
```

**Detection Patterns:**
- Name contains "collision" (case-insensitive)
- Name ends with "_col" (case-insensitive)

**Collision Material:**

```gdscript
collision_material = StandardMaterial3D.new()
collision_material.albedo_color = Color(0.0, 1.0, 0.0)  # Green
collision_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
collision_material.wireframe = true
```

**Special Handling:**
1. No material lookup is performed
2. Green wireframe material is applied
3. Mesh is saved immediately (skips normal material processing)
4. Makes collision geometry visible during development

---

## Utility Functions

### _ensure_directory_exists()

Creates a directory if it doesn't exist:

```gdscript
func _ensure_directory_exists(dir_path: String) -> void:
    if DirAccess.dir_exists_absolute(dir_path):
        return

    var result := DirAccess.make_dir_recursive_absolute(dir_path)
    if result != OK:
        push_warning("Failed to create directory: %s (error: %s)" % [
            dir_path,
            error_string(result)
        ])
```

**Features:**
- No-op if directory already exists
- Creates parent directories recursively
- Logs warning on failure (doesn't abort)

### print_summary()

Prints conversion statistics at the end:

```gdscript
func print_summary() -> void:
    print("=" .repeat(60))
    print("Conversion Complete")
    print("=" .repeat(60))
    print("  Output format:  .%s" % config_mesh_format)
    if config_keep_meshes_together:
        print("  Mode:           Combined scenes (one per FBX)")
    else:
        print("  Mode:           Individual meshes")
    print("  Meshes saved:   %d" % meshes_saved)
    print("  Meshes skipped: %d" % meshes_skipped)
    print("  Warnings:       %d" % warnings)
    print("  Errors:         %d" % errors)
    print("=" .repeat(60))

    if errors > 0:
        print("")
        print("Some meshes failed to save. Check errors above.")
    elif warnings > 0:
        print("")
        print("Conversion completed with warnings. Check logs above.")
    else:
        print("")
        print("All meshes converted successfully!")
```

---

## Output Formats

### Individual Meshes (Default)

Each mesh is saved as a separate scene with a `MeshInstance3D` root:

```
meshes/
    SM_Env_Tree_01_LOD0.tscn
    SM_Env_Tree_01_LOD1.tscn
    SM_Prop_Rock_01.tscn
    subfolder/
        SM_Env_Bush_01.tscn
```

**Scene Structure:**
```gdscript
MeshInstance3D (root)
    name = "SM_Env_Tree_01_LOD0"
    mesh = <imported mesh resource>
    surface_override_material/0 = ExtResource("Tree_Trunk_Mat.tres")
    surface_override_material/1 = ExtResource("Tree_Leaves_Mat.tres")
```

### Combined Scenes (--keep-meshes-together)

All meshes from one FBX are saved together:

```
meshes/
    SM_Env_Tree_01.tscn     # Contains all LOD meshes
    SM_Prop_Rock.tscn        # Contains all rock meshes
```

**Scene Structure:**
```gdscript
Node3D (root)
    name = "SM_Env_Tree_01"
    MeshInstance3D
        name = "SM_Env_Tree_01_LOD0"
        mesh = <mesh>
        surface_override_material/0 = ExtResource(...)
    MeshInstance3D
        name = "SM_Env_Tree_01_LOD1"
        ...
```

### Format Options

| Format | Extension | Description |
|--------|-----------|-------------|
| `tscn` | `.tscn` | Text format, human-readable, diff-friendly |
| `res` | `.res` | Binary compiled format, smaller, faster to load |

---

## Error Handling

### Error Types

| Error | Cause | Handling |
|-------|-------|----------|
| Config parse failure | Invalid JSON in converter_config.json | Aborts with exit code 1 |
| Mapping not found | mesh_material_mapping.json missing | Aborts with exit code 1 |
| FBX load failure | Corrupt or unsupported FBX | Logs error, continues to next file |
| Scene instantiation failure | Memory or format issue | Logs error, continues |
| Material not found | .tres file missing | Logs warning, continues without material |
| Pack/Save failure | Disk or permission issue | Logs error, continues |

### Warning vs Error

- **Warning:** Non-fatal, mesh may still be saved (e.g., missing material, duplicate name)
- **Error:** Fatal for that mesh, not saved (e.g., pack failure, save failure)

Warnings do not affect exit code - they are expected in normal operation.

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success - at least one mesh saved successfully |
| `1` | Failure - no meshes saved OR config/mapping load failed |

The script exits with `quit(exit_code)` at the end of `_init()`.

---

## Complete Processing Flow

```
_init()
    |
    +-> Create collision_material (green wireframe)
    |
    +-> load_converter_config()
    |       |
    |       +-> Load res://converter_config.json
    |       +-> Parse keep_meshes_together, mesh_format, filter_pattern
    |
    +-> load_material_mapping()
    |       |
    |       +-> Load res://shaders/mesh_material_mapping.json
    |       +-> Build mesh_to_materials dictionary
    |
    +-> discover_pack_folders()
    |       |
    |       +-> Scan res:// for directories with models/ and materials/
    |
    +-> For each pack folder:
            |
            +-> process_pack_folder()
                    |
                    +-> _detect_default_material()
                    +-> find_fbx_files() [recursive, with filter]
                    |
                    +-> For each FBX:
                            |
                            +-> process_fbx_file()
                                    |
                                    +-> load() FBX as PackedScene
                                    +-> instantiate() scene
                                    +-> find_mesh_instances() [recursive]
                                    |
                                    +-> If keep_meshes_together:
                                    |       save_fbx_as_single_scene()
                                    |
                                    +-> Else for each mesh:
                                            extract_and_save_mesh()
                                                |
                                                +-> Check collision (apply green material)
                                                +-> get_material_names_for_mesh()
                                                +-> find_material_path() [with fallbacks]
                                                +-> Apply materials as surface overrides
                                                +-> Handle duplicates
                                                +-> PackedScene.pack() + ResourceSaver.save()
    |
    +-> print_summary()
    +-> quit(exit_code)
```

---

## Code Examples

### Programmatic Invocation

```bash
# From Python (how converter.py invokes it):
godot --headless --script res://godot_converter.gd --path "C:/Projects/converted"
```

### Expected Output

```
============================================================
Synty Shader Converter - FBX to Scene Files
============================================================

Config loaded:
  keep_meshes_together: false
  mesh_format: tscn
Loaded material mapping with 42 mesh entries
Found 1 pack folder(s): res://PolygonNature
Processing pack: res://PolygonNature
  Default material: PolygonNature_Mat_01_A
  Found 12 FBX file(s) to process
[1/12] Processing: SM_Env_Tree_Pine_01.fbx
  Processing: res://PolygonNature/models/SM_Env_Tree_Pine_01.fbx
    Found 3 mesh(es)
      Saved: SM_Env_Tree_Pine_01_LOD0.tscn (2 materials)
      Saved: SM_Env_Tree_Pine_01_LOD1.tscn (2 materials)
      Saved: SM_Env_Tree_Pine_01_LOD2.tscn (2 materials)
...

============================================================
Conversion Complete
============================================================
  Output format:  .tscn
  Mode:           Individual meshes
  Meshes saved:   36
  Meshes skipped: 0
  Warnings:       2
  Errors:         0
============================================================

Conversion completed with warnings. Check logs above.
```

### Output Directory Structure

```
res://PolygonNature/
    models/
        SM_Env_Tree_Pine_01.fbx
        Props/
            SM_Prop_Rock_01.fbx
    materials/
        Tree_Trunk_Mat.tres
        Tree_Leaves_Mat.tres
        Rock_Mat.tres
        PolygonNature_Mat_01_A.tres
    meshes/                              # Generated output
        SM_Env_Tree_Pine_01_LOD0.tscn
        SM_Env_Tree_Pine_01_LOD1.tscn
        SM_Env_Tree_Pine_01_LOD2.tscn
        Props/                           # Mirrors models/ structure
            SM_Prop_Rock_01.tscn
```

---

## Notes for Doc Cleanup

After reviewing the existing documentation, the following observations were made:

### Redundant Information

1. **docs/api/godot_converter.md** - Contains a complete API reference with significant overlap:
   - Most function signatures and behaviors are documented there
   - Consider keeping api/godot_converter.md as a concise API-only reference
   - This step doc provides the "how and why" narrative context
   - The api doc has a cleaner table format for quick lookup

2. **docs/architecture.md** - Step 12 description duplicates info:
   - Brief description of Godot CLI phases is appropriate for architecture overview
   - This step doc has implementation details
   - Architecture doc should link here for details

### Outdated Information

1. **docs/api/godot_converter.md** - Material mapping path is incorrect:
   - Shows: `res://mesh_material_mapping.json`
   - Actual: `res://shaders/mesh_material_mapping.json`
   - This was moved to the shaders/ directory

2. **docs/api/godot_converter.md** - Collision material color is wrong:
   - Shows: Magenta (`Color(1.0, 0.0, 1.0)`)
   - Actual: Green (`Color(0.0, 1.0, 0.0)`)
   - The code uses green wireframe for better visibility

3. **docs/api/godot_converter.md** - Missing several newer features:
   - Missing: `_detect_default_material()` function documentation
   - Missing: `_try_material_fallbacks()` fallback pattern documentation
   - Missing: Component suffix removal fallbacks (_Cork, _Liquid, etc.)
   - Missing: `save_fbx_as_single_scene()` function documentation
   - Missing: `_set_owner_recursive()` function documentation
   - Missing: Detailed material path fallback logic (Polygon prefix stripping)

4. **docs/api/godot_converter.md** - Missing info on collision detection:
   - Only documents `collision` in name
   - Missing: `_col` suffix detection
   - Should document both patterns

5. **docs/architecture.md** - Two-phase execution is accurate but could use more detail:
   - Doesn't mention the `converter_config.json` configuration file
   - Doesn't explain that Python generates this file before running

### Information to Incorporate

The following could be added to other docs:

1. **ResourceLoader.exists() vs FileAccess.file_exists()** - The script uses `ResourceLoader.exists()` specifically because `FileAccess.file_exists()` has issues with `res://` paths in headless mode. This is a useful implementation note for troubleshooting.

2. **Default material detection** - The script automatically detects pack default materials by scanning for `*_Mat_01_A.tres` files. This fallback behavior isn't documented in the user guide.

3. **LOD handling** - When using `--keep-meshes-together`, LOD meshes stay together in the same scene. When not used (default), each LOD is a separate scene. This affects how users should organize their imports.

4. **Directory mirroring** - The script mirrors the `models/` subdirectory structure in `meshes/`. This preserves organization (Props/, Environment/, Characters/, etc.).

### Style Inconsistencies

1. **Function naming** - The api doc uses camelCase for some function descriptions while the actual GDScript uses snake_case. Should be consistent.

2. **Return type documentation** - The api doc inconsistently documents return types. Some use `-> Array[String]`, others omit the type.
