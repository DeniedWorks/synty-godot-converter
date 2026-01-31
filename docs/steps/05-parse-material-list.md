# Step 5: Parse MaterialList

This document provides comprehensive documentation for the `material_list.py` module, which parses Synty's `MaterialList.txt` files to extract mesh-to-material mappings for use in Godot conversion.

**Module Location:** `synty-converter/material_list.py` (554 lines)

**Related Documentation:**
- [Architecture](../architecture.md) - Overall pipeline context
- [API: material_list](../api/material_list.md) - Quick API reference
- [Step 4: Parse Materials](04-parse-materials.md) - Unity material parsing (input to this step)

---

## Table of Contents

- [Overview](#overview)
- [MaterialList.txt File Format](#materiallisttxt-file-format)
  - [Hierarchical Structure](#hierarchical-structure)
  - [Slot Format Variants](#slot-format-variants)
  - [Real-World Examples](#real-world-examples)
- [Data Classes](#data-classes)
  - [MaterialSlot](#materialslot)
  - [MeshMaterials](#meshmaterials)
  - [PrefabMaterials](#prefabmaterials)
- [Regex Patterns](#regex-patterns)
  - [_PREFAB_PATTERN](#_prefab_pattern)
  - [_MESH_PATTERN](#_mesh_pattern)
  - [_SLOT_PATTERN](#_slot_pattern)
- [Internal Helper Functions](#internal-helper-functions)
  - [_parse_slot_line()](#_parse_slot_line)
- [Public API Functions](#public-api-functions)
  - [parse_material_list()](#parse_material_list)
  - [get_mesh_to_materials_map()](#get_mesh_to_materials_map)
  - [generate_mesh_material_mapping_json()](#generate_mesh_material_mapping_json)
  - [get_all_material_names()](#get_all_material_names)
  - [get_custom_shader_materials()](#get_custom_shader_materials)
  - [get_texture_mapped_materials()](#get_texture_mapped_materials)
- [CLI Testing Interface](#cli-testing-interface)
- [Hierarchical Parsing Logic](#hierarchical-parsing-logic)
- [JSON Generation Logic](#json-generation-logic)
- [Error Handling](#error-handling)
- [Complete Parsing Flow](#complete-parsing-flow)
- [Code Examples](#code-examples)
- [Notes for Doc Cleanup](#notes-for-doc-cleanup)

---

## Overview

The `material_list.py` module handles MaterialList.txt parsing in the conversion pipeline. It reads Synty's `MaterialList.txt` file from the SourceFiles folder and extracts mesh-to-material mappings. The output is used by the GDScript converter (`godot_converter.gd`) to apply correct materials to each mesh surface in Godot.

**Note:** This doc is Step 5 in the documentation numbering. In runtime, MaterialList parsing is part of Step 5 (combined with shader detection). See [steps/README.md](README.md#step-number-mapping) for the full mapping.

### Key Responsibilities

1. **Parse hierarchical structure** - Handle the Prefab > Mesh > Slot nesting
2. **Extract mesh names** - Map mesh names to their material assignments
3. **Identify material types** - Distinguish standard materials from custom shader materials
4. **Extract texture hints** - Capture texture name information where available
5. **Generate JSON mapping** - Create `mesh_material_mapping.json` for Godot CLI

### Module Dependencies

```
material_list.py
    └── Standard library only:
        ├── json (JSON output generation)
        ├── re (regex patterns)
        ├── logging (debug/warning output)
        └── dataclasses (data structures)
```

No external packages required. This is intentional for portability and to avoid dependency conflicts.

### Why MaterialList.txt Matters

While Unity `.mat` files (parsed in Step 4) contain material property data, they don't tell us which materials are assigned to which meshes. The `MaterialList.txt` file provides this critical mapping:

| Information Source | What It Provides |
|-------------------|------------------|
| Unity `.mat` files | Material properties (textures, colors, floats) |
| `MaterialList.txt` | Which materials go on which mesh surfaces |

Without this mapping, we would have materials but no way to apply them correctly.

---

## MaterialList.txt File Format

### Hierarchical Structure

Synty's `MaterialList.txt` uses a simple hierarchical indented text format with three levels:

```
Prefab Name: <prefab_name>
    Mesh Name: <mesh_name>
        Slot: <material_name> (<texture_or_shader_info>)
```

**Level breakdown:**

| Level | Prefix | Indentation | Content |
|-------|--------|-------------|---------|
| 1 | `Prefab Name:` | None (left-aligned) | Unity prefab name (typically matches FBX filename) |
| 2 | `Mesh Name:` | 4 spaces | Individual mesh within the prefab |
| 3 | `Slot:` | 8 spaces | Material assignment for one surface |

**Key rules:**

1. Empty lines separate prefabs (optional, ignored by parser)
2. Each prefab can contain multiple meshes (typically LOD variants)
3. Each mesh can have multiple slots (multi-material meshes)
4. Slot order matches surface index order (critical for correct assignment)

### Slot Format Variants

The `Slot:` line has two possible formats in the parentheses:

**Format 1: Standard material with texture hint**

```
Slot: Ground_Mat (Ground_Texture_01)
```

- Material name: `Ground_Mat`
- Texture name: `Ground_Texture_01` (the texture applied to this material)
- `uses_custom_shader`: `False`

**Format 2: Custom shader material**

```
Slot: Crystal_Mat_01 (Uses custom shader)
```

- Material name: `Crystal_Mat_01`
- Texture name: `None` (not provided in MaterialList.txt)
- `uses_custom_shader`: `True`

Custom shader materials require Unity package parsing to get full texture and property information.

### Real-World Examples

**Example 1: Simple single-mesh prefab**

```
Prefab Name: SM_Prop_Rock_01
    Mesh Name: SM_Prop_Rock_01
        Slot: Rock_Mat (Rock_01)
```

- One prefab containing one mesh with one material

**Example 2: Multi-material mesh**

```
Prefab Name: SM_Env_Tree_01
    Mesh Name: SM_Env_Tree_01
        Slot: Trunk_Mat (Bark_01)
        Slot: Foliage_Mat (Uses custom shader)
```

- One mesh with two surfaces (trunk and foliage)
- Trunk uses standard material, foliage uses custom shader

**Example 3: LOD variants**

```
Prefab Name: SM_Prop_Crystal_01
    Mesh Name: SM_Prop_Crystal_01
        Slot: Crystal_Mat_01 (Uses custom shader)
        Slot: PolygonNatureBiomes_EnchantedForest_Mat_01_A (TextureName)
    Mesh Name: SM_Prop_Crystal_01_LOD1
        Slot: Crystal_Mat_01 (Uses custom shader)
    Mesh Name: SM_Prop_Crystal_01_LOD2
        Slot: Crystal_Mat_01 (Uses custom shader)
```

- One prefab with three LOD levels
- LOD0 has two materials, LOD1 and LOD2 have one each

**Example 4: Character with multiple meshes**

```
Prefab Name: SK_Chr_Warrior_01
    Mesh Name: SK_Chr_Warrior_01_Head
        Slot: Warrior_Head_Mat (Warrior_Head_01)
    Mesh Name: SK_Chr_Warrior_01_Body
        Slot: Warrior_Body_Mat (Warrior_Body_01)
        Slot: Warrior_Armor_Mat (Warrior_Armor_01)
    Mesh Name: SK_Chr_Warrior_01_Weapon
        Slot: Weapon_Mat (Metal_01)
```

- Prefab with three separate mesh nodes
- Body mesh has two materials (body and armor)

---

## Data Classes

The module defines three dataclasses for structured material data (lines 54-144).

### MaterialSlot

**Purpose:** Represents a single material slot assignment on a mesh surface.

**Definition (lines 54-86):**

```python
@dataclass
class MaterialSlot:
    """Single material slot assignment.

    Represents one material applied to a mesh slot, as parsed from
    MaterialList.txt. Each mesh can have multiple material slots.
    """
    material_name: str
    texture_name: str | None = None
    uses_custom_shader: bool = False
```

**Attributes:**

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `material_name` | `str` | (required) | Name of the material (e.g., `"Crystal_Mat_01"`). This is the text before the parentheses in the `Slot:` line. Used to look up the corresponding `.tres` material file. |
| `texture_name` | `str \| None` | `None` | Optional texture name hint from the parenthetical note. `None` if the material uses a custom shader. For standard materials, this contains the texture name (e.g., `"Bark_01"`). |
| `uses_custom_shader` | `bool` | `False` | `True` if marked `"(Uses custom shader)"` in the file. Custom shader materials require Unity package parsing to get full texture and property information. |

**Example creation:**

```python
# Standard material with texture hint
slot1 = MaterialSlot(
    material_name="Ground_Mat",
    texture_name="Ground_01",
    uses_custom_shader=False
)

# Custom shader material (no texture info available)
slot2 = MaterialSlot(
    material_name="Crystal_Mat_01",
    texture_name=None,
    uses_custom_shader=True
)

# Access attributes
print(slot1.material_name)       # Ground_Mat
print(slot1.texture_name)        # Ground_01
print(slot2.uses_custom_shader)  # True
```

**Usage in pipeline:**

- `material_name` is used to construct the path to the `.tres` file: `res://materials/{material_name}.tres`
- `uses_custom_shader` flag indicates whether the material needs special handling or if texture info should be extracted from Unity package

---

### MeshMaterials

**Purpose:** Represents a mesh and all material slots assigned to its surfaces.

**Definition (lines 88-114):**

```python
@dataclass
class MeshMaterials:
    """Mesh with its material slot assignments.

    Represents a mesh and all materials assigned to its surface slots.
    Material order matters - slot indices must match surface indices.
    """
    mesh_name: str
    slots: list[MaterialSlot] = field(default_factory=list)
```

**Attributes:**

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `mesh_name` | `str` | (required) | Name of the mesh (e.g., `"SM_Prop_Crystal_01_LOD0"`). This corresponds to the MeshInstance3D node name in Godot after FBX import. |
| `slots` | `list[MaterialSlot]` | `[]` | Ordered list of material slots. **Order is critical** - index 0 corresponds to surface 0, index 1 to surface 1, etc. |

**Critical: Slot order preservation**

The order of slots in the list directly maps to surface indices in Godot:

```python
mesh = MeshMaterials(
    mesh_name="SM_Env_Tree_01",
    slots=[
        MaterialSlot("Trunk_Mat", "Bark_01"),      # Surface 0
        MaterialSlot("Foliage_Mat", None, True),   # Surface 1
    ]
)
```

When applying materials in Godot:
- `mesh.surface_set_material(0, trunk_material)`
- `mesh.surface_set_material(1, foliage_material)`

**Example creation:**

```python
mesh = MeshMaterials(
    mesh_name="SM_Env_Rock_01",
    slots=[
        MaterialSlot("Rock_Mat", "Rock_01", False),
        MaterialSlot("Moss_Mat", "Moss_01", False),
    ]
)

print(f"Mesh: {mesh.mesh_name}")           # SM_Env_Rock_01
print(f"Surface count: {len(mesh.slots)}")  # 2
print(f"First material: {mesh.slots[0].material_name}")  # Rock_Mat
```

---

### PrefabMaterials

**Purpose:** Represents a Unity prefab container with all its meshes.

**Definition (lines 117-144):**

```python
@dataclass
class PrefabMaterials:
    """Prefab container with all its meshes.

    Represents a Unity prefab and all meshes contained within it.
    A prefab may contain multiple meshes with different LOD levels.
    """
    prefab_name: str
    meshes: list[MeshMaterials] = field(default_factory=list)
```

**Attributes:**

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `prefab_name` | `str` | (required) | Name of the prefab (e.g., `"SM_Prop_Crystal_01"`). This is typically the asset name without LOD suffix, matching the FBX filename. |
| `meshes` | `list[MeshMaterials]` | `[]` | List of meshes in this prefab with their materials. Often includes LOD variants (LOD0, LOD1, LOD2, etc.). |

**Example creation:**

```python
prefab = PrefabMaterials(
    prefab_name="SM_Prop_Crystal_01",
    meshes=[
        MeshMaterials("SM_Prop_Crystal_01", [
            MaterialSlot("Crystal_Mat_01", None, True),
        ]),
        MeshMaterials("SM_Prop_Crystal_01_LOD1", [
            MaterialSlot("Crystal_Mat_01", None, True),
        ]),
        MeshMaterials("SM_Prop_Crystal_01_LOD2", [
            MaterialSlot("Crystal_Mat_01", None, True),
        ]),
    ]
)

print(f"Prefab: {prefab.prefab_name}")           # SM_Prop_Crystal_01
print(f"LOD levels: {len(prefab.meshes)}")       # 3
for mesh in prefab.meshes:
    print(f"  {mesh.mesh_name}: {len(mesh.slots)} materials")
```

---

## Regex Patterns

The module defines three compiled regex patterns (lines 146-149) for parsing MaterialList.txt lines.

### _PREFAB_PATTERN

**Purpose:** Match and extract prefab name from `Prefab Name:` lines.

**Definition (line 147):**

```python
_PREFAB_PATTERN = re.compile(r"^\s*Prefab Name:\s*(.+?)\s*$")
```

**Pattern breakdown:**

| Component | Meaning |
|-----------|---------|
| `^` | Start of line (important: no MULTILINE needed, matching line by line) |
| `\s*` | Optional leading whitespace (allows some indentation tolerance) |
| `Prefab Name:` | Literal text - the line marker |
| `\s*` | Optional whitespace after colon |
| `(.+?)` | **Capture group 1**: Prefab name (non-greedy to avoid trailing whitespace) |
| `\s*` | Optional trailing whitespace |
| `$` | End of line |

**Matches:**

```
Prefab Name: SM_Prop_Crystal_01
Prefab Name: SM_Env_Tree_Cherry_Blossom_01
```

**Captures:** `SM_Prop_Crystal_01`, `SM_Env_Tree_Cherry_Blossom_01`

**Why non-greedy `(.+?)`:** Prevents capturing trailing whitespace or newline characters. The trailing `\s*$` consumes any whitespace before end of line.

---

### _MESH_PATTERN

**Purpose:** Match and extract mesh name from `Mesh Name:` lines.

**Definition (line 148):**

```python
_MESH_PATTERN = re.compile(r"^\s*Mesh Name:\s*(.+?)\s*$")
```

**Pattern breakdown:**

| Component | Meaning |
|-----------|---------|
| `^` | Start of line |
| `\s*` | Optional leading whitespace (handles indentation) |
| `Mesh Name:` | Literal text - the line marker |
| `\s*` | Optional whitespace after colon |
| `(.+?)` | **Capture group 1**: Mesh name (non-greedy) |
| `\s*` | Optional trailing whitespace |
| `$` | End of line |

**Matches:**

```
    Mesh Name: SM_Prop_Crystal_01
    Mesh Name: SM_Prop_Crystal_01_LOD1
    Mesh Name: SM_Env_Tree_01_Branches_LOD0
```

**Captures:** `SM_Prop_Crystal_01`, `SM_Prop_Crystal_01_LOD1`, `SM_Env_Tree_01_Branches_LOD0`

**Note on indentation:** The pattern uses `\s*` at the start rather than requiring exactly 4 spaces. This makes parsing more robust against formatting variations.

---

### _SLOT_PATTERN

**Purpose:** Match and extract material name and parenthetical content from `Slot:` lines.

**Definition (line 149):**

```python
_SLOT_PATTERN = re.compile(r"^\s*Slot:\s*(.+?)\s*\((.+?)\)\s*$")
```

**Pattern breakdown:**

| Component | Meaning |
|-----------|---------|
| `^` | Start of line |
| `\s*` | Optional leading whitespace (handles indentation) |
| `Slot:` | Literal text - the line marker |
| `\s*` | Optional whitespace after colon |
| `(.+?)` | **Capture group 1**: Material name (non-greedy, stops at space before `(`) |
| `\s*` | Optional whitespace before parentheses |
| `\(` | Opening parenthesis (literal, escaped) |
| `(.+?)` | **Capture group 2**: Content inside parentheses |
| `\)` | Closing parenthesis (literal, escaped) |
| `\s*` | Optional trailing whitespace |
| `$` | End of line |

**Matches:**

```
        Slot: Crystal_Mat_01 (Uses custom shader)
        Slot: Ground_Mat (Ground_Texture_01)
        Slot: PolygonNatureBiomes_EnchantedForest_Mat_01_A (TexName)
```

**Captures:**

| Line | Group 1 (material_name) | Group 2 (parentheses_content) |
|------|------------------------|-------------------------------|
| `Crystal_Mat_01 (Uses custom shader)` | `Crystal_Mat_01` | `Uses custom shader` |
| `Ground_Mat (Ground_Texture_01)` | `Ground_Mat` | `Ground_Texture_01` |

**Special handling:** The parenthetical content is interpreted by `_parse_slot_line()` to determine if it's a custom shader or texture name.

---

## Internal Helper Functions

### _parse_slot_line()

**Purpose:** Parse a single `Slot:` line into a `MaterialSlot` dataclass.

**Definition (lines 152-189):**

```python
def _parse_slot_line(line: str) -> MaterialSlot | None:
    """Parse a single Slot: line into a MaterialSlot.

    Handles both standard materials with texture hints and custom shader
    materials. The format is: "Slot: MaterialName (TextureOrCustomShader)"
    """
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `line` | `str` | A line from MaterialList.txt containing `"Slot:"` |

**Returns:** `MaterialSlot` if successfully parsed, `None` if parsing fails.

**Implementation logic (lines 170-189):**

```python
def _parse_slot_line(line: str) -> MaterialSlot | None:
    # Step 1: Apply regex pattern
    match = _SLOT_PATTERN.match(line)
    if not match:
        logger.warning(f"Failed to parse slot line: {line.strip()!r}")
        return None

    # Step 2: Extract captured groups
    material_name = match.group(1).strip()
    parentheses_content = match.group(2).strip()

    # Step 3: Determine if custom shader or standard texture
    if parentheses_content.lower() == "uses custom shader":
        return MaterialSlot(
            material_name=material_name,
            texture_name=None,
            uses_custom_shader=True,
        )
    else:
        return MaterialSlot(
            material_name=material_name,
            texture_name=parentheses_content,
            uses_custom_shader=False,
        )
```

**Key behaviors:**

1. **Case-insensitive custom shader detection:** Uses `.lower()` to match "Uses custom shader" regardless of casing
2. **Whitespace stripping:** Both material name and parenthetical content are stripped
3. **Warning on parse failure:** Logs a warning if the line doesn't match the expected pattern, returns `None`
4. **Graceful degradation:** Returns `None` rather than raising an exception, allowing caller to skip invalid lines

**Examples:**

```python
# Standard material
slot = _parse_slot_line("        Slot: Rock_Mat (Rock_01)")
# Returns: MaterialSlot(material_name='Rock_Mat', texture_name='Rock_01', uses_custom_shader=False)

# Custom shader material
slot = _parse_slot_line("        Slot: Crystal_Mat (Uses custom shader)")
# Returns: MaterialSlot(material_name='Crystal_Mat', texture_name=None, uses_custom_shader=True)

# Invalid line
slot = _parse_slot_line("        Invalid line format")
# Logs warning, returns: None
```

---

## Public API Functions

### parse_material_list()

**Purpose:** Main parser function. Reads and parses a `MaterialList.txt` file into structured data.

**Definition (lines 192-306):**

```python
def parse_material_list(path: Path) -> list[PrefabMaterials]:
    """Parse a MaterialList.txt file into structured data.

    Reads a Synty MaterialList.txt file and extracts all prefab, mesh,
    and material information into a hierarchical data structure.
    """
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `path` | `Path` | Path to the `MaterialList.txt` file |

**Returns:** `list[PrefabMaterials]` - List of prefabs with their meshes and material slots. Preserves the order from the source file.

**Raises:**

| Exception | Cause |
|-----------|-------|
| `FileNotFoundError` | If the file does not exist |
| `ValueError` | If the file is empty or has no valid entries |

**Implementation (detailed walkthrough):**

**Lines 232-237: Initial setup**

```python
if not path.exists():
    raise FileNotFoundError(f"MaterialList.txt not found: {path}")

prefabs: list[PrefabMaterials] = []
current_prefab: PrefabMaterials | None = None
current_mesh: MeshMaterials | None = None
```

- Validates file exists before attempting to open
- Initializes the result list and state variables for tracking current parsing context

**Lines 239-243: File reading and line iteration**

```python
with path.open("r", encoding="utf-8") as f:
    for line_num, line in enumerate(f, start=1):
        # Skip empty lines
        if not line.strip():
            continue
```

- Opens with UTF-8 encoding (standard for Synty files)
- Uses `enumerate` with `start=1` for 1-based line numbers in logs
- Skips blank lines (prefab separators)

**Lines 245-257: Prefab line handling**

```python
# Check for Prefab Name
prefab_match = _PREFAB_PATTERN.match(line)
if prefab_match:
    # Save previous prefab if exists
    if current_prefab is not None:
        if current_mesh is not None:
            current_prefab.meshes.append(current_mesh)
        prefabs.append(current_prefab)

    current_prefab = PrefabMaterials(prefab_name=prefab_match.group(1))
    current_mesh = None
    logger.debug(f"Line {line_num}: Found prefab: {current_prefab.prefab_name}")
    continue
```

- When a new prefab is encountered, finalize the previous prefab (if any)
- Create new `PrefabMaterials` instance and reset mesh state
- `continue` skips the remaining pattern checks for this line

**Lines 259-274: Mesh line handling**

```python
# Check for Mesh Name
mesh_match = _MESH_PATTERN.match(line)
if mesh_match:
    if current_prefab is None:
        logger.warning(
            f"Line {line_num}: Mesh found outside prefab block: {line.strip()!r}"
        )
        continue

    # Save previous mesh if exists
    if current_mesh is not None:
        current_prefab.meshes.append(current_mesh)

    current_mesh = MeshMaterials(mesh_name=mesh_match.group(1))
    logger.debug(f"Line {line_num}: Found mesh: {current_mesh.mesh_name}")
    continue
```

- Validates mesh is inside a prefab block (warns and skips if not)
- Finalizes previous mesh before creating new one
- Creates new `MeshMaterials` instance

**Lines 276-291: Slot line handling**

```python
# Check for Slot
if "Slot:" in line:
    if current_mesh is None:
        logger.warning(
            f"Line {line_num}: Slot found outside mesh block: {line.strip()!r}"
        )
        continue

    slot = _parse_slot_line(line)
    if slot:
        current_mesh.slots.append(slot)
        logger.debug(
            f"Line {line_num}: Found slot: {slot.material_name} "
            f"(custom={slot.uses_custom_shader})"
        )
    continue
```

- Quick string check for `"Slot:"` before regex (optimization)
- Validates slot is inside a mesh block
- Delegates parsing to `_parse_slot_line()`
- Only appends if parsing succeeded (slot is not None)

**Lines 293-306: Finalization and validation**

```python
# Save final prefab/mesh
if current_prefab is not None:
    if current_mesh is not None:
        current_prefab.meshes.append(current_mesh)
    prefabs.append(current_prefab)

if not prefabs:
    raise ValueError(f"No valid prefab entries found in: {path}")

logger.debug(
    f"Parsed MaterialList.txt: {len(prefabs)} prefabs, "
    f"{sum(len(p.meshes) for p in prefabs)} meshes"
)
return prefabs
```

- Handles the final prefab/mesh that weren't closed by a subsequent prefab
- Raises `ValueError` if file contained no valid prefabs
- Logs summary statistics

**Example usage:**

```python
from pathlib import Path
from material_list import parse_material_list

# Parse the file
prefabs = parse_material_list(Path("SourceFiles/MaterialList.txt"))
print(f"Found {len(prefabs)} prefabs")

# Iterate the hierarchy
for prefab in prefabs:
    print(f"Prefab: {prefab.prefab_name}")
    for mesh in prefab.meshes:
        print(f"  Mesh: {mesh.mesh_name}")
        for slot in mesh.slots:
            shader_info = "(custom)" if slot.uses_custom_shader else f"({slot.texture_name})"
            print(f"    Slot: {slot.material_name} {shader_info}")
```

---

### get_mesh_to_materials_map()

**Purpose:** Flatten the hierarchical prefab structure to a simple mesh_name to material_names mapping.

**Definition (lines 309-349):**

```python
def get_mesh_to_materials_map(prefabs: list[PrefabMaterials]) -> dict[str, list[str]]:
    """Flatten prefab data to a simple mesh_name -> [material_names] mapping.

    Converts the hierarchical prefab structure to a flat dictionary suitable
    for JSON serialization. Material order is preserved to maintain correct
    surface index alignment.
    """
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `prefabs` | `list[PrefabMaterials]` | List of prefabs from `parse_material_list()` |

**Returns:** `dict[str, list[str]]` - Dictionary mapping mesh names to ordered lists of material names. Order matches the original `Slot:` entries in MaterialList.txt.

**Implementation (lines 335-349):**

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

1. **Flattens hierarchy:** Discards prefab grouping, extracts mesh-to-material mapping
2. **Preserves order:** Material list order matches slot order (critical for surface indices)
3. **Handles duplicates:** Logs warning and overwrites with later occurrence
4. **Extracts only material names:** Texture hints and custom shader flags are not included

**Example:**

```python
prefabs = parse_material_list(Path("MaterialList.txt"))
mesh_map = get_mesh_to_materials_map(prefabs)

# Result format:
# {
#     "SM_Env_Tree_01": ["Trunk_Mat", "Foliage_Mat"],
#     "SM_Env_Tree_01_LOD1": ["Trunk_Mat", "Foliage_Mat"],
#     "SM_Prop_Rock_01": ["Rock_Mat"]
# }

for mesh_name, materials in mesh_map.items():
    print(f"{mesh_name}: {materials}")
```

---

### generate_mesh_material_mapping_json()

**Purpose:** Generate `mesh_material_mapping.json` file for the GDScript converter.

**Definition (lines 352-391):**

```python
def generate_mesh_material_mapping_json(
    prefabs: list[PrefabMaterials],
    output_path: Path,
    *,
    indent: int = 2,
) -> None:
    """Generate mesh_material_mapping.json for Godot conversion.

    Creates a JSON file mapping mesh names to their material names.
    This file is consumed by the GDScript converter (godot_converter.gd)
    to apply the correct materials to each mesh surface.
    """
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prefabs` | `list[PrefabMaterials]` | (required) | List of prefabs from `parse_material_list()` |
| `output_path` | `Path` | (required) | Path where the JSON file will be written |
| `indent` | `int` | `2` | JSON indentation level (keyword-only parameter) |

**Returns:** `None`

**Raises:**

| Exception | Cause |
|-----------|-------|
| `OSError` | If the file cannot be written (permissions, disk full, etc.) |

**Implementation (lines 383-391):**

```python
def generate_mesh_material_mapping_json(
    prefabs: list[PrefabMaterials],
    output_path: Path,
    *,
    indent: int = 2,
) -> None:
    mesh_map = get_mesh_to_materials_map(prefabs)

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(mesh_map, f, indent=indent, ensure_ascii=False)

    logger.debug(f"Wrote mesh material mapping to: {output_path}")
```

**Key behaviors:**

1. **Creates parent directories:** Uses `mkdir(parents=True, exist_ok=True)` to ensure output directory exists
2. **UTF-8 encoding:** Writes with UTF-8 for international character support
3. **Preserves non-ASCII:** Uses `ensure_ascii=False` to keep non-ASCII characters readable
4. **Configurable indentation:** Default 2 spaces for human readability

**Output JSON format:**

```json
{
  "SM_Env_Tree_01": [
    "Trunk_Mat",
    "Foliage_Mat"
  ],
  "SM_Env_Tree_01_LOD1": [
    "Trunk_Mat",
    "Foliage_Mat"
  ],
  "SM_Prop_Rock_01": [
    "Rock_Mat"
  ]
}
```

**Usage in pipeline:**

The generated JSON is consumed by `godot_converter.gd`:

```gdscript
# In godot_converter.gd
var mapping = JSON.parse(file.get_as_text())
for mesh_name in mapping.keys():
    var materials = mapping[mesh_name]
    for i in range(materials.size()):
        var mat_name = materials[i]
        var mat_path = "res://materials/" + mat_name + ".tres"
        mesh.surface_set_material(i, load(mat_path))
```

---

### get_all_material_names()

**Purpose:** Extract all unique material names from parsed prefabs.

**Definition (lines 394-419):**

```python
def get_all_material_names(prefabs: list[PrefabMaterials]) -> set[str]:
    """Extract all unique material names from parsed prefabs.

    Useful for validating that all referenced materials exist, or for
    generating a list of materials that need to be converted.
    """
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `prefabs` | `list[PrefabMaterials]` | List of prefabs from `parse_material_list()` |

**Returns:** `set[str]` - Set of unique material names (unordered).

**Implementation (lines 414-419):**

```python
def get_all_material_names(prefabs: list[PrefabMaterials]) -> set[str]:
    materials: set[str] = set()
    for prefab in prefabs:
        for mesh in prefab.meshes:
            for slot in mesh.slots:
                materials.add(slot.material_name)
    return materials
```

**Use cases:**

1. **Material validation:** Check that all referenced materials were converted
2. **Dependency analysis:** Determine which materials are used in a pack
3. **Statistics:** Count unique materials

**Example:**

```python
prefabs = parse_material_list(Path("MaterialList.txt"))
all_materials = get_all_material_names(prefabs)

print(f"Found {len(all_materials)} unique materials")

# Validate all materials exist
for mat_name in sorted(all_materials):
    mat_path = Path(f"output/materials/{mat_name}.tres")
    if not mat_path.exists():
        print(f"WARNING: Missing material: {mat_name}")
```

---

### get_custom_shader_materials()

**Purpose:** Extract material names that use custom shaders.

**Definition (lines 422-449):**

```python
def get_custom_shader_materials(prefabs: list[PrefabMaterials]) -> set[str]:
    """Extract material names that use custom shaders.

    These materials require Unity package parsing to get full details
    since MaterialList.txt doesn't include texture information for them.
    Custom shader materials are marked with "(Uses custom shader)" in the file.
    """
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `prefabs` | `list[PrefabMaterials]` | List of prefabs from `parse_material_list()` |

**Returns:** `set[str]` - Set of material names that use custom shaders.

**Implementation (lines 443-449):**

```python
def get_custom_shader_materials(prefabs: list[PrefabMaterials]) -> set[str]:
    materials: set[str] = set()
    for prefab in prefabs:
        for mesh in prefab.meshes:
            for slot in mesh.slots:
                if slot.uses_custom_shader:
                    materials.add(slot.material_name)
    return materials
```

**Use cases:**

1. **Identify materials needing Unity package parsing:** Custom shader materials don't have texture info in MaterialList.txt
2. **Shader analysis:** Determine what percentage of materials use custom shaders
3. **Debugging:** List materials that might need special handling

**Example:**

```python
prefabs = parse_material_list(Path("MaterialList.txt"))
custom_materials = get_custom_shader_materials(prefabs)

print(f"Custom shader materials ({len(custom_materials)}):")
for mat in sorted(custom_materials):
    print(f"  - {mat}")

# Calculate percentage
all_materials = get_all_material_names(prefabs)
pct = len(custom_materials) / len(all_materials) * 100
print(f"\n{pct:.1f}% of materials use custom shaders")
```

---

### get_texture_mapped_materials()

**Purpose:** Extract material name to texture name mapping for standard (non-custom shader) materials.

**Definition (lines 452-494):**

```python
def get_texture_mapped_materials(
    prefabs: list[PrefabMaterials],
) -> dict[str, str]:
    """Extract material name -> texture name mapping for standard materials.

    Only includes materials where texture information is available
    (i.e., not custom shader materials). Useful for simple material
    conversion when Unity package parsing is not needed.
    """
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `prefabs` | `list[PrefabMaterials]` | List of prefabs from `parse_material_list()` |

**Returns:** `dict[str, str]` - Dictionary mapping material names to their texture names. Only includes materials with `texture_name` set.

**Implementation (lines 480-494):**

```python
def get_texture_mapped_materials(
    prefabs: list[PrefabMaterials],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for prefab in prefabs:
        for mesh in prefab.meshes:
            for slot in mesh.slots:
                if slot.texture_name is not None and not slot.uses_custom_shader:
                    if slot.material_name in result:
                        existing = result[slot.material_name]
                        if existing != slot.texture_name:
                            logger.warning(
                                f"Material {slot.material_name!r} has multiple textures: "
                                f"{existing!r} vs {slot.texture_name!r}. Keeping first."
                            )
                    else:
                        result[slot.material_name] = slot.texture_name
    return result
```

**Key behaviors:**

1. **Excludes custom shader materials:** Only includes materials with texture names
2. **First-occurrence wins:** If a material appears with different textures, warns and keeps first
3. **Returns flat mapping:** Simple material -> texture dictionary

**Use cases:**

1. **Simple material creation:** Create basic materials from texture names without Unity package
2. **Texture validation:** Verify texture files exist
3. **Quick lookup:** Get texture for a material name

**Example:**

```python
prefabs = parse_material_list(Path("MaterialList.txt"))
texture_map = get_texture_mapped_materials(prefabs)

# Result format:
# {
#     "Ground_Mat": "Ground_01",
#     "Rock_Mat": "Rock_01",
#     "Trunk_Mat": "Bark_01"
# }

# Use for simple material creation
for mat_name, tex_name in texture_map.items():
    tex_path = f"res://textures/{tex_name}.png"
    print(f"Material {mat_name} uses texture {tex_path}")
```

---

## CLI Testing Interface

The module includes a CLI for testing and standalone use (lines 497-554).

**Usage:**

```bash
# Basic parsing (validates file, shows debug output)
python material_list.py MaterialList.txt

# With summary statistics
python material_list.py MaterialList.txt --summary

# Generate JSON output
python material_list.py MaterialList.txt -o mesh_material_mapping.json

# Combined
python material_list.py MaterialList.txt --summary -o output/mapping.json
```

**CLI Arguments:**

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `input_file` | Path | Yes | Path to `MaterialList.txt` |
| `-o, --output` | Path | No | Output path for `mesh_material_mapping.json` |
| `--summary` | Flag | No | Print summary statistics |

**Implementation (lines 498-554):**

```python
if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Parse Synty MaterialList.txt and optionally generate JSON output."
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="Path to MaterialList.txt",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output path for mesh_material_mapping.json",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print summary statistics",
    )
    args = parser.parse_args()

    try:
        prefabs = parse_material_list(args.input_file)

        if args.summary:
            all_materials = get_all_material_names(prefabs)
            custom_materials = get_custom_shader_materials(prefabs)
            texture_materials = get_texture_mapped_materials(prefabs)

            print(f"\n=== MaterialList.txt Summary ===")
            print(f"Prefabs: {len(prefabs)}")
            print(f"Total meshes: {sum(len(p.meshes) for p in prefabs)}")
            print(f"Unique materials: {len(all_materials)}")
            print(f"Custom shader materials: {len(custom_materials)}")
            print(f"Texture-mapped materials: {len(texture_materials)}")

            if custom_materials:
                print(f"\nCustom shader materials:")
                for mat in sorted(custom_materials):
                    print(f"  - {mat}")

        if args.output:
            generate_mesh_material_mapping_json(prefabs, args.output)
            print(f"\nWrote: {args.output}")

    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
```

**Example output with `--summary`:**

```
=== MaterialList.txt Summary ===
Prefabs: 150
Total meshes: 450
Unique materials: 45
Custom shader materials: 12
Texture-mapped materials: 33

Custom shader materials:
  - Crystal_Mat_01
  - Foliage_Mat
  - Glass_Mat
  - Water_Mat
  ...

Wrote: mesh_material_mapping.json
```

---

## Hierarchical Parsing Logic

The parser uses a state machine approach to handle the hierarchical structure:

```
State Variables:
  current_prefab: PrefabMaterials | None
  current_mesh: MeshMaterials | None
  prefabs: list[PrefabMaterials]

Transitions:
  "Prefab Name:" line:
    1. Finalize current_mesh -> append to current_prefab.meshes
    2. Finalize current_prefab -> append to prefabs
    3. Create new current_prefab
    4. Reset current_mesh to None

  "Mesh Name:" line:
    1. Validate current_prefab exists
    2. Finalize current_mesh -> append to current_prefab.meshes
    3. Create new current_mesh

  "Slot:" line:
    1. Validate current_mesh exists
    2. Parse slot
    3. Append to current_mesh.slots

  End of file:
    1. Finalize current_mesh -> append to current_prefab.meshes
    2. Finalize current_prefab -> append to prefabs
```

**Visual flow:**

```
File:                           State:
                                prefabs=[], prefab=None, mesh=None
Prefab Name: P1
                                prefabs=[], prefab=P1, mesh=None
    Mesh Name: M1
                                prefabs=[], prefab=P1, mesh=M1
        Slot: S1 (tex)
                                M1.slots=[S1]
        Slot: S2 (custom)
                                M1.slots=[S1,S2]
    Mesh Name: M2
                                P1.meshes=[M1], mesh=M2
        Slot: S1 (tex)
                                M2.slots=[S1]
Prefab Name: P2
                                prefabs=[P1], prefab=P2, mesh=None
    Mesh Name: M3
                                prefabs=[P1], prefab=P2, mesh=M3
        Slot: S3 (tex)
                                M3.slots=[S3]
EOF
                                prefabs=[P1,P2] (P2.meshes=[M3])
```

---

## JSON Generation Logic

The JSON output format is designed for easy consumption by GDScript:

**Input (hierarchical):**

```
PrefabMaterials(
  prefab_name="SM_Env_Tree_01",
  meshes=[
    MeshMaterials(
      mesh_name="SM_Env_Tree_01",
      slots=[
        MaterialSlot("Trunk_Mat", "Bark_01", False),
        MaterialSlot("Foliage_Mat", None, True)
      ]
    ),
    MeshMaterials(
      mesh_name="SM_Env_Tree_01_LOD1",
      slots=[
        MaterialSlot("Trunk_Mat", "Bark_01", False),
        MaterialSlot("Foliage_Mat", None, True)
      ]
    )
  ]
)
```

**Output (flat JSON):**

```json
{
  "SM_Env_Tree_01": ["Trunk_Mat", "Foliage_Mat"],
  "SM_Env_Tree_01_LOD1": ["Trunk_Mat", "Foliage_Mat"]
}
```

**Transformation steps:**

1. **Flatten hierarchy:** Discard prefab grouping (not needed for material assignment)
2. **Extract mesh name as key:** The mesh name becomes the dictionary key
3. **Extract material names as value:** Ordered list of material names only
4. **Discard metadata:** Texture hints and custom shader flags are not included (already processed in earlier steps)

**Why this format:**

- Simple lookup by mesh name in GDScript
- Array index corresponds to surface index
- Minimal file size
- Easy to parse with `JSON.parse()`

---

## Error Handling

The module uses graceful degradation where possible:

| Scenario | Behavior |
|----------|----------|
| File not found | Raises `FileNotFoundError` with descriptive message |
| Empty file / no valid prefabs | Raises `ValueError` with descriptive message |
| Mesh outside prefab block | Logs warning, skips the mesh |
| Slot outside mesh block | Logs warning, skips the slot |
| Malformed slot line | Logs warning, skips the slot |
| Duplicate mesh names | Logs debug, uses later values |
| Conflicting texture mappings | Logs warning, keeps first |

**Logging levels:**

| Level | Usage |
|-------|-------|
| `DEBUG` | Line-by-line parsing details, summary statistics |
| `WARNING` | Parse failures, structural issues, conflicts |

**Example log output:**

```
DEBUG: Line 1: Found prefab: SM_Prop_Crystal_01
DEBUG: Line 2: Found mesh: SM_Prop_Crystal_01
DEBUG: Line 3: Found slot: Crystal_Mat_01 (custom=True)
WARNING: Line 15: Slot found outside mesh block: '        Slot: Orphan_Mat (tex)'
DEBUG: Parsed MaterialList.txt: 150 prefabs, 450 meshes
```

---

## Complete Parsing Flow

```
Input: MaterialList.txt path
          |
          v
   parse_material_list()
          |
          +---> File existence check
          |           | (raises FileNotFoundError if missing)
          |           v
          |     Open file (UTF-8)
          |
          +---> Line-by-line iteration
          |           |
          |           +---> Skip empty lines
          |           |
          |           +---> Match Prefab Name:
          |           |           | (finalize previous, create new)
          |           |           v
          |           |     PrefabMaterials
          |           |
          |           +---> Match Mesh Name:
          |           |           | (validate context, finalize previous)
          |           |           v
          |           |     MeshMaterials
          |           |
          |           +---> Match Slot:
          |                       |
          |                       v
          |               _parse_slot_line()
          |                       | (regex parse, type detection)
          |                       v
          |               MaterialSlot
          |
          +---> Finalize final prefab/mesh
          |
          +---> Validation (raises ValueError if empty)
          |
          v
   list[PrefabMaterials]
          |
          +---> get_mesh_to_materials_map()
          |           | (flatten hierarchy)
          |           v
          |     dict[str, list[str]]
          |
          +---> generate_mesh_material_mapping_json()
          |           | (write JSON file)
          |           v
          |     mesh_material_mapping.json
          |
          +---> get_all_material_names()
          |           | (extract unique names)
          |           v
          |     set[str]
          |
          +---> get_custom_shader_materials()
          |           | (filter custom shader)
          |           v
          |     set[str]
          |
          +---> get_texture_mapped_materials()
                      | (extract texture mappings)
                      v
                dict[str, str]
```

---

## Code Examples

### Basic Usage

```python
from pathlib import Path
from material_list import parse_material_list, generate_mesh_material_mapping_json

# Parse MaterialList.txt
material_list_path = Path("C:/SyntyAssets/SourceFiles/MaterialList.txt")
prefabs = parse_material_list(material_list_path)

print(f"Parsed {len(prefabs)} prefabs")
print(f"Total meshes: {sum(len(p.meshes) for p in prefabs)}")

# Generate JSON for Godot converter
output_path = Path("C:/GodotProject/mesh_material_mapping.json")
generate_mesh_material_mapping_json(prefabs, output_path)
print(f"Wrote mapping to: {output_path}")
```

### Analyzing Material Usage

```python
from pathlib import Path
from material_list import (
    parse_material_list,
    get_all_material_names,
    get_custom_shader_materials,
    get_texture_mapped_materials,
)

prefabs = parse_material_list(Path("MaterialList.txt"))

# Get statistics
all_materials = get_all_material_names(prefabs)
custom_materials = get_custom_shader_materials(prefabs)
texture_map = get_texture_mapped_materials(prefabs)

print(f"=== Material Analysis ===")
print(f"Total unique materials: {len(all_materials)}")
print(f"Custom shader materials: {len(custom_materials)} ({len(custom_materials)/len(all_materials)*100:.1f}%)")
print(f"Standard materials: {len(texture_map)}")

print(f"\nCustom shader materials:")
for mat in sorted(custom_materials):
    print(f"  - {mat}")

print(f"\nStandard materials with textures:")
for mat, tex in sorted(texture_map.items()):
    print(f"  - {mat} -> {tex}")
```

### Validating Material Files

```python
from pathlib import Path
from material_list import parse_material_list, get_all_material_names

prefabs = parse_material_list(Path("MaterialList.txt"))
required_materials = get_all_material_names(prefabs)

materials_dir = Path("output/materials")
missing = []
found = []

for mat_name in sorted(required_materials):
    mat_path = materials_dir / f"{mat_name}.tres"
    if mat_path.exists():
        found.append(mat_name)
    else:
        missing.append(mat_name)

print(f"Material validation:")
print(f"  Found: {len(found)}/{len(required_materials)}")
print(f"  Missing: {len(missing)}")

if missing:
    print(f"\nMissing materials:")
    for mat in missing:
        print(f"  - {mat}")
```

### Finding Meshes Using a Specific Material

```python
from pathlib import Path
from material_list import parse_material_list

prefabs = parse_material_list(Path("MaterialList.txt"))

# Find all meshes using "Crystal_Mat_01"
target_material = "Crystal_Mat_01"
using_meshes = []

for prefab in prefabs:
    for mesh in prefab.meshes:
        for slot in mesh.slots:
            if slot.material_name == target_material:
                using_meshes.append((prefab.prefab_name, mesh.mesh_name))
                break  # Found in this mesh, move to next

print(f"Meshes using {target_material}:")
for prefab_name, mesh_name in using_meshes:
    print(f"  {prefab_name} / {mesh_name}")
```

### Integration with Unity Package Parsing

```python
from pathlib import Path
from material_list import parse_material_list, get_custom_shader_materials
from unity_package import extract_unitypackage, get_material_guids
from unity_parser import parse_material_bytes

# Parse MaterialList.txt to identify custom shader materials
prefabs = parse_material_list(Path("SourceFiles/MaterialList.txt"))
custom_materials = get_custom_shader_materials(prefabs)

# Extract Unity package to get material data for custom shaders
guid_map = extract_unitypackage(Path("Package.unitypackage"))

# Parse only the custom shader materials (they need Unity package data)
for guid in get_material_guids(guid_map):
    mat_bytes = guid_map.guid_to_content[guid]
    material = parse_material_bytes(mat_bytes)

    if material.name in custom_materials:
        print(f"Custom shader material: {material.name}")
        print(f"  Shader GUID: {material.shader_guid}")
        print(f"  Textures: {list(material.tex_envs.keys())}")
```

---

## Notes for Doc Cleanup

After reviewing the existing documentation, here are findings for consolidation:

### Redundant Information

1. **`docs/api/material_list.md`** - This is a quick API reference (473 lines) that duplicates much of what's now in this step documentation:
   - Class definitions (MaterialSlot, MeshMaterials, PrefabMaterials) - repeated verbatim
   - Function signatures and descriptions - repeated
   - Usage examples - similar
   - **Recommendation:** Keep as concise API reference, remove detailed explanations, link to this step doc for implementation details

2. **`docs/architecture.md` Section "Step 10: Parse MaterialList.txt"** (lines 239-249):
   - Brief description of this step's purpose
   - Shows same file format example
   - **Recommendation:** Keep brief overview, add link: "See [Step 5: Parse MaterialList](steps/05-parse-material-list.md) for detailed implementation."

3. **`docs/architecture.md` Section "Module Responsibilities"** (line 94):
   - One-line description of material_list.py
   - **Recommendation:** Keep as-is (appropriate for overview)

### Outdated Information

1. **`docs/architecture.md` line 64-65** - Shows import:
   ```python
   from material_list import parse_material_list, generate_mesh_material_mapping_json
   ```
   This is accurate. No update needed.

2. **`docs/api/material_list.md`** - References are current. Line count (473) is slightly different from source file (554), may indicate doc is for older version or excludes some sections.

3. **Step numbering inconsistency:**
   - `architecture.md` calls this "Step 10"
   - This doc is named "Step 5" (05-parse-material-list.md)
   - **Recommendation:** Clarify that step numbers in `architecture.md` refer to the full 12-step pipeline order, while `steps/` docs may use different numbering for logical grouping

### Information to Incorporate

1. **From `docs/architecture.md` lines 239-249:**
   - Already incorporated the file format example
   - Output description matches

2. **From `docs/api/material_list.md`:**
   - The error handling table (lines 467-473) is well-formatted and was incorporated
   - The CLI usage section was incorporated and expanded

### Suggested Cross-References

Add to the following docs:

1. **`docs/architecture.md`** Step 10 section (around line 249):
   - Add: "See [Step 5: Parse MaterialList](steps/05-parse-material-list.md) for detailed implementation."

2. **`docs/api/material_list.md`**:
   - Add at top: "For detailed implementation documentation, see [Step 5: Parse MaterialList](../steps/05-parse-material-list.md)."
   - Consider reducing detail in this file since step doc now covers it

3. **This document (`05-parse-material-list.md`)**:
   - Already includes links to related docs in the header

### Potential Improvements for api/material_list.md

The API reference could be streamlined to:
1. Keep only function signatures and brief descriptions
2. Remove implementation details (move to step doc)
3. Remove duplicate examples (link to step doc)
4. Keep error handling table (useful quick reference)

This would reduce overlap and make maintenance easier.

---

*Last Updated: 2026-01-31*
*Based on material_list.py (554 lines)*
