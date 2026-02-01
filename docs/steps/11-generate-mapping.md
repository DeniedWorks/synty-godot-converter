# Step 11: Generate mesh_material_mapping.json

This document provides comprehensive documentation for the generation of `mesh_material_mapping.json`, the critical data bridge between the Python conversion pipeline and the Godot CLI phase.

**Related Files:**
- `material_list.py` - Contains `generate_mesh_material_mapping_json()` function
- `converter.py` - Orchestrates the generation as Step 11 in the pipeline
- `godot_converter.gd` - Consumes the JSON in Godot headless mode

**Related Documentation:**
- [Architecture](../architecture.md) - Overall pipeline context
- [Step 5: Parse MaterialList](05-parse-material-list.md) - Input data parsing
- [API: godot_converter](../api/godot_converter.md) - How the JSON is consumed

---

## Table of Contents

- [Overview](#overview)
- [Per-Pack Output](#per-pack-output)
  - [Output Location](#output-location)
  - [No Merge Logic](#no-merge-logic)
- [Purpose and Role in Pipeline](#purpose-and-role-in-pipeline)
- [JSON Structure and Schema](#json-structure-and-schema)
  - [Format Specification](#format-specification)
  - [Key-Value Semantics](#key-value-semantics)
  - [Real-World Examples](#real-world-examples)
- [Generation Logic](#generation-logic)
  - [Data Flow](#data-flow)
  - [Flattening Algorithm](#flattening-algorithm)
  - [Implementation Details](#implementation-details)
- [Integration with Converter Pipeline](#integration-with-converter-pipeline)
  - [Step Sequence](#step-sequence)
  - [Dry Run Handling](#dry-run-handling)
- [How Godot CLI Uses the JSON](#how-godot-cli-uses-the-json)
  - [Loading the Mapping](#loading-the-mapping)
  - [Mesh Name Resolution](#mesh-name-resolution)
  - [Material Path Construction](#material-path-construction)
  - [Fallback Strategies](#fallback-strategies)
- [Path Handling](#path-handling)
  - [Relative vs Absolute Paths](#relative-vs-absolute-paths)
  - [Cross-Platform Considerations](#cross-platform-considerations)
- [Error Handling](#error-handling)
  - [Generation Errors](#generation-errors)
  - [Missing Materials Validation](#missing-materials-validation)
- [Code Examples](#code-examples)
- [Troubleshooting](#troubleshooting)
- [Notes for Doc Cleanup](#notes-for-doc-cleanup)

---

## Overview

The `mesh_material_mapping.json` file is a critical intermediate artifact that bridges the Python material parsing phase with the Godot CLI mesh conversion phase. It provides a simple lookup table mapping mesh names to their material assignments, enabling the GDScript converter to apply the correct `.tres` materials to each mesh surface.

### Why This File Exists

The conversion pipeline operates in two distinct phases:

1. **Python Phase**: Parses Unity packages, extracts material data, generates `.tres` files
2. **Godot Phase**: Imports FBX files, extracts meshes, applies materials, saves `.tscn` scenes

The JSON mapping file is the data handoff mechanism between these phases. It encodes the mesh-to-material relationships extracted from `MaterialList.txt` in a format that GDScript can easily consume.

### Key Characteristics

| Characteristic | Value |
|---------------|-------|
| Format | JSON (RFC 8259 compliant) |
| Encoding | UTF-8 |
| Location | `{output}/{pack}/mesh_material_mapping.json` |
| Size | Typically 50KB-500KB depending on pack |
| Consumers | `godot_converter.gd` |
| Producers | `material_list.py` via `generate_mesh_material_mapping_json()` |

---

## Per-Pack Output

### Output Location

The mapping JSON is now written to the pack's own directory, not a shared location:

```
output/
  POLYGON_NatureBiomes/
    mesh_material_mapping.json    <-- Per-pack mapping
    materials/
    models/
    meshes/
  POLYGON_Fantasy/
    mesh_material_mapping.json    <-- Separate mapping for each pack
    materials/
    models/
    meshes/
```

**Previous location (deprecated):**
```
output/
  shaders/
    mesh_material_mapping.json    # Was shared across all packs
```

**Current location:**
```
output/
  {pack_name}/
    mesh_material_mapping.json    # Isolated per pack
```

### No Merge Logic

Each pack conversion generates its own complete mapping file:

- **Isolated data** - Each pack's mapping contains only its own mesh-material relationships
- **No conflicts** - Multiple packs can have meshes with the same name without collision
- **Simpler logic** - No need to merge or deduplicate across packs
- **Clean re-runs** - Re-converting a pack completely replaces its mapping

```python
# Each pack gets its own mapping file
mapping_output = pack_output_dir / "mesh_material_mapping.json"
generate_mesh_material_mapping_json(prefabs, mapping_output)
```

---

## Purpose and Role in Pipeline

### The Material Assignment Problem

When Godot imports an FBX file, it creates `MeshInstance3D` nodes with mesh resources. However, the FBX format does not reliably preserve Unity's material assignments. The mesh surfaces have indices (0, 1, 2...) but no guaranteed association with specific materials.

The `MaterialList.txt` file from Synty's SourceFiles contains this mapping information, but it's in a format that GDScript cannot directly parse (hierarchical indented text).

### The Solution

The Python pipeline:
1. Parses `MaterialList.txt` into structured data (`PrefabMaterials` objects)
2. Flattens the hierarchy to a mesh-to-materials dictionary
3. Writes JSON that GDScript can easily load

The GDScript converter:
1. Loads the JSON mapping at startup
2. For each mesh it extracts from FBX files, looks up the materials
3. Loads the corresponding `.tres` files
4. Applies them as surface override materials

### Data Flow Diagram

```
MaterialList.txt
       |
       v
parse_material_list()
       |
       v
list[PrefabMaterials]
       |
       v
get_mesh_to_materials_map()
       |
       v
dict[str, list[str]]
       |
       v
generate_mesh_material_mapping_json()
       |
       v
mesh_material_mapping.json
       |
       v
godot_converter.gd (load_material_mapping)
       |
       v
Apply materials to meshes
```

---

## JSON Structure and Schema

### Format Specification

The JSON file is a flat dictionary (object) with the following structure:

```json
{
  "<mesh_name>": ["<material_name_1>", "<material_name_2>", ...],
  ...
}
```

**Schema (JSON Schema format):**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "additionalProperties": {
    "type": "array",
    "items": {
      "type": "string"
    }
  }
}
```

### Key-Value Semantics

| Component | Type | Description |
|-----------|------|-------------|
| Key | `string` | Mesh name from `MaterialList.txt` (e.g., `"SM_Prop_Rock_01"`) |
| Value | `array[string]` | Ordered list of material names for each surface |

**Critical: Array Order Matters**

The array index corresponds directly to the mesh surface index:
- `materials[0]` -> Surface 0
- `materials[1]` -> Surface 1
- etc.

This ordering comes from the `Slot:` entries in `MaterialList.txt`, which are parsed in order.

### Real-World Examples

**Example 1: Single-Material Mesh**

```json
{
  "SM_Prop_Rock_01": ["Rock_Mat"]
}
```

- Mesh `SM_Prop_Rock_01` has one surface
- Surface 0 uses material `Rock_Mat`

**Example 2: Multi-Material Mesh**

```json
{
  "SM_Env_Tree_01": ["Trunk_Mat", "Foliage_Mat"]
}
```

- Mesh `SM_Env_Tree_01` has two surfaces
- Surface 0 uses `Trunk_Mat`
- Surface 1 uses `Foliage_Mat`

**Example 3: LOD Variants**

```json
{
  "SM_Prop_Crystal_01": ["Crystal_Mat_01", "PolygonNatureBiomes_Mat_01_A"],
  "SM_Prop_Crystal_01_LOD1": ["Crystal_Mat_01"],
  "SM_Prop_Crystal_01_LOD2": ["Crystal_Mat_01"]
}
```

- LOD0 has two materials (high-detail with extra surface)
- LOD1 and LOD2 have one material each (simplified geometry)

**Example 4: Full Pack Excerpt**

```json
{
  "SM_Env_Tree_Cherry_Blossom_01": ["Cherry_Blossom_01", "Branches_01"],
  "SM_Env_Tree_Cherry_Blossom_01_Branches_LOD0": ["Cherry_Blossom_02"],
  "SM_Env_Tree_Cherry_Blossom_01_LOD0": ["Cherry_Blossom_03"],
  "SM_Env_Tree_Cherry_Blossom_01_LOD1": ["Cherry_Blossom_01"],
  "SM_Env_Tree_Cherry_Blossom_01_LOD2": ["Cherry_Blossom_01"],
  "SM_Env_Tree_Pine_01": ["Pine_01"],
  "SM_Env_Tree_Pine_01_LOD0": ["Pine_01"],
  "SM_Env_Tree_Pine_01_LOD1": ["Pine_01"],
  "SM_Env_Tree_Pine_01_LOD2": ["Pine_01"]
}
```

---

## Generation Logic

### Data Flow

The generation process transforms hierarchical `PrefabMaterials` data into a flat dictionary:

```
Input: list[PrefabMaterials]
  |
  +-- PrefabMaterials
  |     |-- prefab_name: "SM_Env_Tree_01"
  |     +-- meshes: [
  |           MeshMaterials(
  |             mesh_name: "SM_Env_Tree_01",
  |             slots: [
  |               MaterialSlot(material_name: "Trunk_Mat"),
  |               MaterialSlot(material_name: "Foliage_Mat")
  |             ]
  |           ),
  |           MeshMaterials(
  |             mesh_name: "SM_Env_Tree_01_LOD1",
  |             slots: [
  |               MaterialSlot(material_name: "Trunk_Mat"),
  |               MaterialSlot(material_name: "Foliage_Mat")
  |             ]
  |           )
  |         ]
  |
  v
Output: dict[str, list[str]]
  {
    "SM_Env_Tree_01": ["Trunk_Mat", "Foliage_Mat"],
    "SM_Env_Tree_01_LOD1": ["Trunk_Mat", "Foliage_Mat"]
  }
```

### Flattening Algorithm

The `get_mesh_to_materials_map()` function performs the flattening:

```python
def get_mesh_to_materials_map(prefabs: list[PrefabMaterials]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}

    for prefab in prefabs:
        for mesh in prefab.meshes:
            material_names = [slot.material_name for slot in mesh.slots]
            if mesh.mesh_name in result:
                logger.debug(
                    f"Duplicate mesh name found: {mesh.mesh_name!r}. "
                    f"Previous materials: {result[mesh.mesh_name]}, "
                    f"New materials: {material_names}. Using new values."
                )
            result[mesh.mesh_name] = material_names

    logger.debug(f"Built mesh-to-materials map: {len(result)} meshes")
    return result
```

**Key behaviors:**

1. **Discards prefab grouping**: The prefab name is not included in the output
2. **Extracts only material names**: Texture hints and custom shader flags are discarded
3. **Preserves slot order**: List comprehension maintains original order
4. **Handles duplicates**: Later occurrences overwrite earlier ones (with warning)

### Implementation Details

The `generate_mesh_material_mapping_json()` function (lines 352-391 in `material_list.py`):

```python
def generate_mesh_material_mapping_json(
    prefabs: list[PrefabMaterials],
    output_path: Path,
    *,
    indent: int = 2,
) -> None:
    """Generate mesh_material_mapping.json for Godot conversion."""

    # Step 1: Flatten the hierarchy
    mesh_map = get_mesh_to_materials_map(prefabs)

    # Step 2: Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Step 3: Write JSON with proper encoding
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(mesh_map, f, indent=indent, ensure_ascii=False)

    logger.debug(f"Wrote mesh material mapping to: {output_path}")
```

**JSON output options:**

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `indent` | `2` | Human-readable formatting |
| `ensure_ascii` | `False` | Preserve non-ASCII characters (e.g., accented names) |
| `encoding` | `utf-8` | Standard encoding for Godot compatibility |

---

## Integration with Converter Pipeline

### Step Sequence

The JSON generation occurs as Step 11 in the converter pipeline:

```
Step 9:  Copy Textures
Step 10: Copy FBX Files
Step 11: Generate mesh_material_mapping.json  <-- This step
Step 12: Generate project.godot
Step 13: Run Godot CLI
```

### Pipeline Code

```python
# Step 11: Generate mesh_material_mapping.json (uses prefabs parsed in Step 4.5)
# Note: mapping goes to pack directory (per-pack isolation)
logger.info("Step 11: Generating mesh material mapping...")
if prefabs:
    mapping_output = pack_output_dir / "mesh_material_mapping.json"
    if config.dry_run:
        logger.debug("[DRY RUN] Would write mesh_material_mapping.json")
    else:
        generate_mesh_material_mapping_json(prefabs, mapping_output)
        logger.debug("Generated mesh_material_mapping.json at %s", mapping_output)

    # Check for missing material references (no placeholders - just warn)
    if not config.dry_run:
        logger.debug("Checking for missing material references...")
        materials_dir = pack_output_dir / "materials"
        existing_materials = {f.stem for f in materials_dir.glob("*.tres")}

        # Collect all referenced materials from prefabs
        referenced_materials: set[str] = set()
        for prefab in prefabs:
            for mesh in prefab.meshes:
                for slot in mesh.slots:
                    if slot.material_name:
                        referenced_materials.add(slot.material_name)

        # Find missing materials - just warn, don't create placeholders
        missing_materials = referenced_materials - existing_materials
        stats.materials_missing = len(missing_materials)

        if missing_materials:
            logger.debug(
                "Found %d missing material(s) - these meshes will use default materials:",
                len(missing_materials)
            )
            for mat_name in sorted(missing_materials):
                logger.debug("  Missing: %s", mat_name)
else:
    logger.debug("No MaterialList data available, skipping mesh-material mapping")
```

### Dry Run Handling

When `--dry-run` is specified:
- The function is not called
- A debug message indicates what would have been written
- No file is created
- Missing material validation is skipped

---

## How Godot CLI Uses the JSON

The `godot_converter.gd` script loads and uses the mapping JSON during mesh conversion.

### Loading the Mapping

The Godot converter loads the per-pack mapping file:

```gdscript
func load_material_mapping(pack_folder: String) -> bool:
    # Per-pack mapping file location
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

**Key change:** The mapping is loaded from the pack folder (`res://POLYGON_NatureBiomes/mesh_material_mapping.json`) rather than a shared location.

### Mesh Name Resolution

The mapping lookup handles Godot's numeric suffix addition (lines 692-737):

```gdscript
func get_material_names_for_mesh(mesh_name: String) -> Array[String]:
    var material_names_result: Array[String] = []
    var lookup_name := mesh_name

    # Try exact match first
    if not mesh_to_materials.has(lookup_name):
        # Try stripping numeric suffixes like "_001", "_002" (Godot import adds these)
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
    # ... process and return
```

### Material Path Construction

Once material names are retrieved, the GDScript constructs file paths (lines 853-889):

```gdscript
func find_material_path(mat_name: String, materials_dir: String) -> String:
    var base_path := materials_dir.path_join(mat_name + ".tres")

    # 1. Try exact name
    if ResourceLoader.exists(base_path):
        return base_path

    # 2. Strip Polygon*_Mat_ or Polygon*_ prefix
    var stripped := mat_name
    if stripped.begins_with("Polygon"):
        var mat_idx := stripped.find("_Mat_")
        if mat_idx > 0:
            stripped = stripped.substr(mat_idx + 5)
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

### Fallback Strategies

The GDScript implements multiple fallback strategies:

| Strategy | Example | Purpose |
|----------|---------|---------|
| Numeric suffix stripping | `SM_Tree_01_001` -> `SM_Tree_01` | Handle Godot import duplicates |
| SK_ to SM_ conversion | `SK_Chr_01` -> `SM_Chr_01` | Skeletal/static mesh sharing |
| Remove _Static suffix | `SM_Prop_Barrel_Static` -> `SM_Prop_Barrel` | Static variants |
| Remove _Preset suffix | `SM_Prop_Barrel_Preset` -> `SM_Prop_Barrel` | Preset variants |
| Sub-component suffixes | `SM_Prop_Door_Handle` -> `SM_Prop_Door` | Component meshes |
| Default material | (any mesh) -> `PackName_Mat_01_A` | Final fallback |

---

## Path Handling

### Relative vs Absolute Paths

The JSON contains **material names only**, not paths:

```json
{
  "SM_Prop_Rock_01": ["Rock_Mat"]
}
```

Path construction happens at runtime in the GDScript:
- Material directory: `res://{PackName}/materials/`
- Material path: `res://{PackName}/materials/{MaterialName}.tres`

**Why names instead of paths:**
1. Pack folder name varies per conversion
2. Keeps JSON portable between projects
3. Simplifies Python side (no need to know Godot project structure)

### Cross-Platform Considerations

The JSON file uses:
- UTF-8 encoding (universal)
- Forward slashes in any paths (Godot normalizes on read)
- No OS-specific path separators

---

## Error Handling

### Generation Errors

The `generate_mesh_material_mapping_json()` function can raise:

| Exception | Cause | Handling |
|-----------|-------|----------|
| `OSError` | Disk full, permissions, path issues | Propagated to caller |

The parent directory creation uses `exist_ok=True` so existing directories don't cause errors.

### Missing Materials Validation

After generating the JSON, `converter.py` validates that referenced materials exist (lines 1988-2014):

```python
# Check for missing material references (no placeholders - just warn)
if not config.dry_run:
    logger.debug("Checking for missing material references...")
    materials_dir = pack_output_dir / "materials"
    existing_materials = {f.stem for f in materials_dir.glob("*.tres")}

    # Collect all referenced materials from prefabs
    referenced_materials: set[str] = set()
    for prefab in prefabs:
        for mesh in prefab.meshes:
            for slot in mesh.slots:
                if slot.material_name:
                    referenced_materials.add(slot.material_name)

    # Find missing materials - just warn, don't create placeholders
    missing_materials = referenced_materials - existing_materials
    stats.materials_missing = len(missing_materials)
```

**Note:** Missing materials are logged but do not fail the conversion. The GDScript will handle missing materials at runtime with warnings and default material fallbacks.

---

## Code Examples

### Basic Generation

```python
from pathlib import Path
from material_list import parse_material_list, generate_mesh_material_mapping_json

# Parse MaterialList.txt
prefabs = parse_material_list(Path("SourceFiles/MaterialList.txt"))

# Generate JSON
generate_mesh_material_mapping_json(
    prefabs,
    Path("output/shaders/mesh_material_mapping.json")
)
```

### Custom Indent Level

```python
# Generate with 4-space indentation for better readability
generate_mesh_material_mapping_json(
    prefabs,
    Path("output/mesh_material_mapping.json"),
    indent=4
)
```

### Programmatic Access to Mapping

```python
from material_list import parse_material_list, get_mesh_to_materials_map

prefabs = parse_material_list(Path("MaterialList.txt"))
mesh_map = get_mesh_to_materials_map(prefabs)

# Access mapping directly
for mesh_name, materials in mesh_map.items():
    print(f"{mesh_name}: {materials}")

# Check specific mesh
if "SM_Prop_Rock_01" in mesh_map:
    materials = mesh_map["SM_Prop_Rock_01"]
    print(f"Rock has {len(materials)} material(s)")
```

### Validation Example

```python
from pathlib import Path
from material_list import parse_material_list, get_all_material_names

prefabs = parse_material_list(Path("MaterialList.txt"))
referenced = get_all_material_names(prefabs)

materials_dir = Path("output/materials")
existing = {f.stem for f in materials_dir.glob("*.tres")}

missing = referenced - existing
if missing:
    print(f"Warning: {len(missing)} missing materials:")
    for mat in sorted(missing):
        print(f"  - {mat}")
```

---

## Troubleshooting

### JSON Not Generated

**Symptom:** `mesh_material_mapping.json` not created

**Possible causes:**
1. `MaterialList.txt` not found (check Step 4.5 logs)
2. `--dry-run` flag enabled
3. Empty `MaterialList.txt` (no valid prefabs)

**Resolution:**
- Verify `MaterialList.txt` exists in SourceFiles
- Remove `--dry-run` for actual conversion
- Check logs for parsing errors

### Mesh Not Found in Mapping

**Symptom:** GDScript warns "No material mapping for mesh"

**Possible causes:**
1. Mesh name mismatch (Godot suffix vs MaterialList name)
2. Mesh not listed in MaterialList.txt
3. JSON generated from different pack

**Resolution:**
- Check exact mesh name in FBX vs MaterialList.txt
- Verify JSON contains the mesh (search the file)
- Ensure correct pack was converted

### Wrong Materials Applied

**Symptom:** Mesh has incorrect materials

**Possible causes:**
1. Surface index mismatch (slot order in MaterialList.txt)
2. Duplicate mesh names with different materials
3. Fallback matching wrong mesh

**Resolution:**
- Check MaterialList.txt slot order matches FBX surface order
- Look for duplicate mesh warnings in Python logs
- Disable fallback by using exact mesh names

---

## Notes for Doc Cleanup

After reviewing the existing documentation, here are findings for consolidation:

### Redundant Information

1. **`docs/steps/05-parse-material-list.md`** (1658 lines) - Contains a section "JSON Generation Logic" (lines 1293-1343) that duplicates content from this document:
   - Same transformation explanation
   - Same output format examples
   - **Recommendation:** Keep brief overview in Step 5, add link: "See [Step 11: Generate Mapping](11-generate-mapping.md) for detailed JSON generation documentation."

2. **`docs/api/material_list.md`** (473 lines) - Contains `generate_mesh_material_mapping_json()` documentation (lines 228-275):
   - Function signature and parameters
   - Output format example
   - **Recommendation:** Keep as concise API reference, remove implementation details, link to this step doc

3. **`docs/api/godot_converter.md`** (598 lines) - Contains JSON loading documentation (lines 82-97):
   - Schema description matches this doc
   - **Recommendation:** Keep as consumer documentation, link to this doc for producer details

4. **`docs/architecture.md`** (350+ lines) - Contains Step 10 description (lines 238-249):
   - Brief example of MaterialList format
   - One-line output description
   - **Recommendation:** Keep brief, add link to this step doc

### Step Numbering Inconsistency

The step is referred to by different numbers:
- `converter.py` line 29: "Step 9: Generate mesh_material_mapping.json"
- `converter.py` line 1977: "Step 10: Generating mesh material mapping..."
- `architecture.md` line 238: "Step 10: Parse MaterialList.txt" (conflates parsing with generation)
- This doc: "Step 11" (based on filename)

**Recommendation:** Standardize on Step 10 for JSON generation, rename this file to `10-generate-mapping.md`

### Outdated Information

1. **`docs/api/godot_converter.md`** line 209 - States mapping path is:
   ```
   res://mesh_material_mapping.json
   ```
   But actual path is:
   ```
   res://shaders/mesh_material_mapping.json
   ```
   **Action required:** Update the API doc

2. **`docs/user-guide.md`** line 197 - Shows output structure with:
   ```
   output/
     ...
     mesh_material_mapping.json  # Mesh-to-material assignments
   ```
   But actual location is:
   ```
   output/
     shaders/
       mesh_material_mapping.json
   ```
   **Action required:** Update the user guide output structure

3. **Step numbering in filenames** - Files use different numbering schemes:
   - `00-cli-orchestration.md`, `01-validate-inputs.md`, ..., `08-copy-textures.md`
   - This doc would be `11-generate-mapping.md` but pipeline step is 10
   **Action required:** Align filename numbering with pipeline step numbers

### Information to Incorporate

The following information from other docs should be referenced but not duplicated:

1. **From `05-parse-material-list.md`:**
   - Data class definitions (MaterialSlot, MeshMaterials, PrefabMaterials)
   - Parsing logic details
   - Already linked in "Related Documentation"

2. **From `godot_converter.md`:**
   - Complete fallback strategy list
   - Runtime error handling
   - Already linked in "Related Documentation"

### Suggested Cross-References to Add

Add to the following docs:

1. **`docs/steps/05-parse-material-list.md`** (at end of JSON Generation Logic section):
   ```markdown
   For detailed JSON generation documentation, see [Step 11: Generate Mapping](11-generate-mapping.md).
   ```

2. **`docs/api/material_list.md`** (at `generate_mesh_material_mapping_json` section):
   ```markdown
   For detailed implementation documentation, see [Step 11: Generate Mapping](../steps/11-generate-mapping.md).
   ```

3. **`docs/architecture.md`** (at Step 10 section):
   ```markdown
   See [Step 11: Generate Mapping](steps/11-generate-mapping.md) for detailed implementation.
   ```

---

*Last Updated: 2026-02-01*
