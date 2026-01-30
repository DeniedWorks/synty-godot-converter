# Material List API Reference

## Overview

The `material_list` module parses Synty's `MaterialList.txt` files to extract mesh-to-material mappings. These files are found in Synty SourceFiles folders and document which materials are assigned to each mesh surface.

**Key Features:**
- Parses the hierarchical Prefab/Mesh/Slot structure
- Distinguishes between standard and custom shader materials
- Extracts texture name mappings where available
- Generates JSON output for the GDScript converter

**Module Location:** `material_list.py`

---

## MaterialList.txt Format

Synty's `MaterialList.txt` uses a hierarchical indented format:

```
Prefab Name: SM_Prop_Crystal_01
    Mesh Name: SM_Prop_Crystal_01
        Slot: Crystal_Mat_01 (Uses custom shader)
        Slot: PolygonNatureBiomes_EnchantedForest_Mat_01_A (TextureName)

Prefab Name: SM_Env_Tree_01
    Mesh Name: SM_Env_Tree_01_LOD0
        Slot: Tree_Trunk_Mat (Trunk_Texture)
        Slot: Tree_Leaves_Mat (Leaves_Texture)
    Mesh Name: SM_Env_Tree_01_LOD1
        Slot: Tree_Trunk_Mat (Trunk_Texture)
        Slot: Tree_Leaves_Mat (Leaves_Texture)
```

### Format Rules

1. **Prefab Name:** - Top-level entry, typically matches the FBX filename
2. **Mesh Name:** - Indented under prefab, represents a MeshInstance3D in Godot
3. **Slot:** - Indented under mesh, one per material surface
   - Format: `MaterialName (TextureName)` for standard materials
   - Format: `MaterialName (Uses custom shader)` for custom shader materials

### Slot Types

| Parentheses Content | Meaning |
|--------------------|---------|
| Texture filename | Standard material with texture mapping |
| `Uses custom shader` | Custom shader material (requires Unity package parsing) |

---

## Classes

### MaterialSlot

Represents a single material slot on a mesh surface.

```python
@dataclass
class MaterialSlot:
    material_name: str
    texture_name: str | None = None
    uses_custom_shader: bool = False
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `material_name` | `str` | Name of the material (before the parentheses) |
| `texture_name` | `str \| None` | Texture name from parentheses, or `None` if custom shader |
| `uses_custom_shader` | `bool` | `True` if the slot uses a custom shader |

**Example:**

```python
# Standard material with texture
slot1 = MaterialSlot(
    material_name="Tree_Trunk_Mat",
    texture_name="Trunk_Texture",
    uses_custom_shader=False
)

# Custom shader material
slot2 = MaterialSlot(
    material_name="Crystal_Mat_01",
    texture_name=None,
    uses_custom_shader=True
)
```

---

### MeshMaterials

Represents a mesh and its material slots.

```python
@dataclass
class MeshMaterials:
    mesh_name: str
    slots: list[MaterialSlot] = field(default_factory=list)
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `mesh_name` | `str` | Name of the mesh (e.g., `SM_Prop_Crystal_01_LOD0`) |
| `slots` | `list[MaterialSlot]` | List of material slots assigned to this mesh |

**Example:**

```python
mesh = MeshMaterials(
    mesh_name="SM_Env_Tree_01_LOD0",
    slots=[
        MaterialSlot("Tree_Trunk_Mat", "Trunk_Texture"),
        MaterialSlot("Tree_Leaves_Mat", "Leaves_Texture"),
    ]
)
```

---

### PrefabMaterials

Represents a prefab and all its meshes with their materials.

```python
@dataclass
class PrefabMaterials:
    prefab_name: str
    meshes: list[MeshMaterials] = field(default_factory=list)
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `prefab_name` | `str` | Name of the prefab (e.g., `SM_Prop_Crystal_01`) |
| `meshes` | `list[MeshMaterials]` | List of meshes contained in this prefab |

**Example:**

```python
prefab = PrefabMaterials(
    prefab_name="SM_Env_Tree_01",
    meshes=[
        MeshMaterials("SM_Env_Tree_01_LOD0", [...]),
        MeshMaterials("SM_Env_Tree_01_LOD1", [...]),
    ]
)
```

---

## Functions

### parse_material_list(path) -> list[PrefabMaterials]

Main parser function. Reads and parses a `MaterialList.txt` file into structured data.

**Arguments:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `path` | `Path` | Path to the `MaterialList.txt` file |

**Returns:** `list[PrefabMaterials]` - List of prefabs with their meshes and material slots

**Raises:**
- `FileNotFoundError` - If the file does not exist
- `ValueError` - If the file is empty or has no valid entries

**Example:**

```python
from pathlib import Path
from material_list import parse_material_list

prefabs = parse_material_list(Path("SourceFiles/MaterialList.txt"))

for prefab in prefabs:
    print(f"Prefab: {prefab.prefab_name}")
    for mesh in prefab.meshes:
        print(f"  Mesh: {mesh.mesh_name}")
        for slot in mesh.slots:
            print(f"    Material: {slot.material_name}")
```

---

### get_mesh_to_materials_map(prefabs) -> dict[str, list[str]]

Flattens prefab data to a simple mesh_name to material_names mapping.

**Arguments:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `prefabs` | `list[PrefabMaterials]` | List of prefabs from `parse_material_list()` |

**Returns:** `dict[str, list[str]]` - Dictionary mapping mesh names to ordered lists of material names

**Behavior:**
- Preserves slot order (important for surface index alignment)
- Logs warnings for duplicate mesh names (uses later values)

**Example:**

```python
from material_list import parse_material_list, get_mesh_to_materials_map

prefabs = parse_material_list(path)
mesh_map = get_mesh_to_materials_map(prefabs)

# Result:
# {
#     "SM_Env_Tree_01_LOD0": ["Tree_Trunk_Mat", "Tree_Leaves_Mat"],
#     "SM_Env_Tree_01_LOD1": ["Tree_Trunk_Mat", "Tree_Leaves_Mat"],
# }
```

---

### generate_mesh_material_mapping_json(prefabs, output_path, *, indent=2) -> None

Generates `mesh_material_mapping.json` for the GDScript converter.

**Arguments:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prefabs` | `list[PrefabMaterials]` | - | List of prefabs from `parse_material_list()` |
| `output_path` | `Path` | - | Path where the JSON file will be written |
| `indent` | `int` | `2` | JSON indentation level (keyword-only) |

**Returns:** `None`

**Raises:**
- `OSError` - If the file cannot be written

**Side Effects:**
- Creates parent directories if they don't exist
- Writes JSON file with UTF-8 encoding

**Example:**

```python
from pathlib import Path
from material_list import parse_material_list, generate_mesh_material_mapping_json

prefabs = parse_material_list(Path("MaterialList.txt"))
generate_mesh_material_mapping_json(
    prefabs,
    Path("output/mesh_material_mapping.json")
)
```

**Output Format:**

```json
{
  "SM_Env_Tree_01_LOD0": [
    "Tree_Trunk_Mat",
    "Tree_Leaves_Mat"
  ],
  "SM_Env_Tree_01_LOD1": [
    "Tree_Trunk_Mat",
    "Tree_Leaves_Mat"
  ]
}
```

---

### get_all_material_names(prefabs) -> set[str]

Extracts all unique material names from parsed prefabs. Useful for validating that all referenced materials exist.

**Arguments:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `prefabs` | `list[PrefabMaterials]` | List of prefabs from `parse_material_list()` |

**Returns:** `set[str]` - Set of unique material names

**Example:**

```python
all_materials = get_all_material_names(prefabs)
print(f"Found {len(all_materials)} unique materials")

# Check for missing materials
for mat_name in all_materials:
    mat_path = Path(f"materials/{mat_name}.tres")
    if not mat_path.exists():
        print(f"Missing: {mat_name}")
```

---

### get_custom_shader_materials(prefabs) -> set[str]

Extracts material names that use custom shaders. These materials require Unity package parsing to get full property details since `MaterialList.txt` doesn't include texture information for them.

**Arguments:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `prefabs` | `list[PrefabMaterials]` | List of prefabs from `parse_material_list()` |

**Returns:** `set[str]` - Set of material names that use custom shaders

**Example:**

```python
custom_materials = get_custom_shader_materials(prefabs)
print(f"Custom shader materials ({len(custom_materials)}):")
for mat in sorted(custom_materials):
    print(f"  - {mat}")
```

---

### get_texture_mapped_materials(prefabs) -> dict[str, str]

Extracts material name to texture name mapping for standard materials (non-custom shader).

**Arguments:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `prefabs` | `list[PrefabMaterials]` | List of prefabs from `parse_material_list()` |

**Returns:** `dict[str, str]` - Dictionary mapping material names to their texture names

**Behavior:**
- Only includes materials where texture information is available
- Excludes custom shader materials
- Logs warnings if a material has conflicting texture assignments (keeps first)

**Example:**

```python
texture_map = get_texture_mapped_materials(prefabs)

# Result:
# {
#     "Tree_Trunk_Mat": "Trunk_Texture",
#     "Tree_Leaves_Mat": "Leaves_Texture",
# }
```

---

## Parsing Example

### Input: MaterialList.txt

```
Prefab Name: SM_Prop_Crystal_01
    Mesh Name: SM_Prop_Crystal_01
        Slot: Crystal_Mat_01 (Uses custom shader)
        Slot: PolygonNatureBiomes_EnchantedForest_Mat_01_A (EnchantedForest_Texture)

Prefab Name: SM_Env_Tree_01
    Mesh Name: SM_Env_Tree_01_LOD0
        Slot: Tree_Trunk_Mat (Trunk_Texture)
        Slot: Tree_Leaves_Mat (Leaves_Texture)
    Mesh Name: SM_Env_Tree_01_LOD1
        Slot: Tree_Trunk_Mat (Trunk_Texture)
        Slot: Tree_Leaves_Mat (Leaves_Texture)
```

### Parsing Code

```python
from pathlib import Path
from material_list import (
    parse_material_list,
    get_all_material_names,
    get_custom_shader_materials,
    get_texture_mapped_materials,
    generate_mesh_material_mapping_json,
)

# Parse the file
prefabs = parse_material_list(Path("MaterialList.txt"))

# Get statistics
all_materials = get_all_material_names(prefabs)
custom_materials = get_custom_shader_materials(prefabs)
texture_map = get_texture_mapped_materials(prefabs)

print(f"Prefabs: {len(prefabs)}")
print(f"Total meshes: {sum(len(p.meshes) for p in prefabs)}")
print(f"Unique materials: {len(all_materials)}")
print(f"Custom shader materials: {len(custom_materials)}")
print(f"Texture-mapped materials: {len(texture_map)}")

# Generate JSON for Godot converter
generate_mesh_material_mapping_json(prefabs, Path("mesh_material_mapping.json"))
```

### Output

```
Prefabs: 2
Total meshes: 3
Unique materials: 4
Custom shader materials: 1
Texture-mapped materials: 3
```

---

## CLI Usage

The module can be run directly for testing and standalone parsing:

```bash
# Basic parsing (validates file)
python material_list.py MaterialList.txt

# With summary statistics
python material_list.py MaterialList.txt --summary

# Generate JSON output
python material_list.py MaterialList.txt -o mesh_material_mapping.json

# Combined
python material_list.py MaterialList.txt --summary -o output/mapping.json
```

**CLI Arguments:**

| Argument | Description |
|----------|-------------|
| `input_file` | Path to `MaterialList.txt` (required) |
| `-o, --output` | Output path for `mesh_material_mapping.json` |
| `--summary` | Print summary statistics |

---

## Logging

The module uses Python's standard logging. Enable debug logging to see line-by-line parsing:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Log messages include:
- Found prefab/mesh/slot entries (DEBUG)
- Parsing warnings (WARNING)
- Summary statistics (INFO)

---

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `FileNotFoundError` | File path doesn't exist | Verify `MaterialList.txt` path |
| `ValueError` | File empty or no valid entries | Check file format |
| Parsing warnings | Malformed slot lines | Check line format matches `Slot: Name (Content)` |
| Duplicate mesh warnings | Same mesh name in multiple prefabs | Later values are used |
