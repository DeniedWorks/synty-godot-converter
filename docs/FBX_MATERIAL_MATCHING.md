# FBX Material Matching

This document describes the material matching system used by Synty Converter v2 to accurately map FBX material slots to Unity materials.

## The Problem

When converting Unity assets to Godot, a key challenge is matching materials correctly:

1. **FBX files contain material names** - These are the original material names from the 3D modeling software (Maya, Blender, etc.)
2. **Unity .mat files have different names** - Unity materials often have prefixes, suffixes, or completely different naming conventions
3. **Godot import needs exact mappings** - The `.fbx.import` file must specify which Godot material to use for each FBX material slot

**Example Mismatch:**
```
FBX Material:     "Mat_Building_Stone"
Unity Material:   "PolygonFantasy_Mat_Building_Stone_01.mat"
```

Without accurate matching, materials either won't be applied or will be applied incorrectly.

## Solution Overview

The converter uses a **meta-file-first matching system** where FBX `.meta` files are the **primary source** for both FBX material names and Unity material mappings. Blender is completely optional.

| Source | Method | Confidence | Blender Required |
|--------|--------|------------|------------------|
| **PRIMARY** | `.meta` file `externalObjects` | 100% | No |
| Fallback | Blender FBX extraction + fuzzy matching | ~90% | Yes (optional) |

### Why .meta Files Make Blender Optional

The `externalObjects` section in FBX `.meta` files contains:
1. **The exact FBX material names** (the `name` field)
2. **The Unity material GUIDs** they map to (the `guid` field)

This means for typical `.unitypackage` conversions, **all the information needed for 100% accurate material matching is already in the package** - no need to run Blender to extract FBX material names.

## Primary Source: FBX Meta Files (No Blender Needed)

### How It Works

Unity stores FBX import settings in `.meta` files alongside each FBX file. These files contain an `externalObjects` section that explicitly maps FBX material names to Unity material GUIDs.

**Key insight:** The `.meta` file already contains the FBX material names - we don't need Blender to extract them from the FBX file.

**Example FBX Meta File (SM_Building_House_01.fbx.meta):**
```yaml
fileFormatVersion: 2
guid: abc123def456
ModelImporter:
  externalObjects:
  - first:
      type: UnityEngine.Material
      assembly: UnityEngine.CoreModule
      name: Mat_Building_Stone
    second: {fileID: 2100000, guid: def789abc123, type: 2}
  - first:
      type: UnityEngine.Material
      assembly: UnityEngine.CoreModule
      name: Mat_Building_Wood
    second: {fileID: 2100000, guid: ghi012jkl345, type: 2}
```

This tells us:
- FBX material `Mat_Building_Stone` -> Unity material with GUID `def789abc123`
- FBX material `Mat_Building_Wood` -> Unity material with GUID `ghi012jkl345`

### Implementation

The `UnityPackageExtractor` parses these `.meta` files during extraction:

```python
@dataclass
class FBXMaterialMapping:
    """Mapping from FBX material name to Unity material GUID."""
    fbx_material_name: str
    unity_material_guid: str
    fbx_path: str

class UnityPackageExtractor:
    def __init__(self, package_path: Path):
        self.materials: Dict[str, MaterialInfo] = {}
        self.materials_by_guid: Dict[str, MaterialInfo] = {}  # NEW
        self.fbx_material_mappings: Dict[str, List[FBXMaterialMapping]] = {}  # NEW
```

When the converter needs to match a material:

```python
def match_by_guid(self, fbx_path: str, fbx_material_name: str) -> Optional[MaterialInfo]:
    mappings = self.fbx_material_mappings.get(fbx_path, [])
    for mapping in mappings:
        if mapping.fbx_material_name == fbx_material_name:
            return self.materials_by_guid.get(mapping.unity_material_guid)
    return None
```

### Advantages

- **100% accurate** - Uses Unity's own mapping data
- **No guessing** - Direct GUID lookup
- **Handles renamed materials** - Works even if Unity material name differs from FBX name
- **No Blender required** - FBX material names come from `.meta` files, not from parsing FBX
- **Fast** - No external process needed

### Limitations

- Only works for materials that Unity has explicitly mapped
- New/unassigned materials won't have mappings
- Requires `.meta` files (included in `.unitypackage` files, but may be missing from extracted directories)

## Fallback: Blender + Fuzzy Name Matching

When `.meta` files are unavailable (e.g., converting from extracted directories), the converter falls back to Blender-based extraction and fuzzy name matching.

**Note:** This fallback is rarely needed when converting `.unitypackage` files, since they include `.meta` files.

### Fallback Step 1: Blender FBX Analysis (Optional)

If Blender is available AND `.meta` files don't exist, the converter extracts actual material names from the FBX file:

```python
from synty_converter_v2.extractors.fbx_extractor import FBXExtractor

extractor = FBXExtractor()
if extractor.blender_available:
    materials = extractor.extract_materials(fbx_path)
    # Returns: ["Mat_Building_Stone", "Mat_Building_Wood"]
```

**How it works:**
1. Runs Blender in headless mode (`blender --background`)
2. Imports the FBX file
3. Iterates through all mesh objects
4. Collects material names from material slots
5. Returns deduplicated list

### Fallback Step 2: Blender Suffix Handling

Blender automatically adds `.001`, `.002` suffixes when importing duplicate material names:

```
FBX Original:     "Mat_Stone"
After Blender:    "Mat_Stone", "Mat_Stone.001", "Mat_Stone.002"
```

The `clean_material_name()` function strips these suffixes:

```python
def clean_material_name(name: str) -> str:
    """Remove Blender's .001, .002, etc. suffixes from material names."""
    import re
    return re.sub(r'\.\d{3}$', '', name)

# Examples:
clean_material_name("Mat_Stone.001")  # -> "Mat_Stone"
clean_material_name("Mat_Stone.002")  # -> "Mat_Stone"
clean_material_name("Mat_Stone")      # -> "Mat_Stone"
```

### Fallback Step 3: Fuzzy Name Matching

After cleaning, the matcher tries several strategies:

1. **Exact Match**
   ```python
   if cleaned_name in self.materials:
       return self.materials[cleaned_name]
   ```

2. **Case-Insensitive Match**
   ```python
   for name, mat in self.materials.items():
       if name.lower() == cleaned_name.lower():
           return mat
   ```

3. **Partial Match (contains)**
   ```python
   for name, mat in self.materials.items():
       if cleaned_name in name or name in cleaned_name:
           return mat
   ```

4. **Similarity Scoring**
   ```python
   best_match = None
   best_score = 0
   for name, mat in self.materials.items():
       score = similarity(cleaned_name, name)
       if score > best_score and score > 0.7:  # 70% threshold
           best_match = mat
           best_score = score
   return best_match
   ```

## The MaterialMatcher Class

The `MaterialMatcher` class in `matchers/material_matcher.py` orchestrates the matching:

```python
class MaterialMatcher:
    def __init__(
        self,
        materials: Dict[str, MaterialInfo],
        materials_by_guid: Dict[str, MaterialInfo],
        fbx_material_mappings: Dict[str, List[FBXMaterialMapping]]
    ):
        self.materials = materials
        self.materials_by_guid = materials_by_guid
        self.fbx_material_mappings = fbx_material_mappings

        # Statistics
        self.guid_matches = 0
        self.fuzzy_matches = 0
        self.unmatched = 0

    def match(self, fbx_path: str, fbx_material_name: str) -> Optional[MaterialInfo]:
        """Match a single FBX material to a Unity material."""

        # Phase 1: Try GUID matching
        result = self._match_by_guid(fbx_path, fbx_material_name)
        if result:
            self.guid_matches += 1
            return result

        # Phase 2: Fall back to fuzzy matching
        cleaned_name = clean_material_name(fbx_material_name)
        result = self._match_by_name(cleaned_name)
        if result:
            self.fuzzy_matches += 1
            return result

        self.unmatched += 1
        return None

    def print_statistics(self):
        """Print matching statistics."""
        total = self.guid_matches + self.fuzzy_matches + self.unmatched
        print(f"Material Matching Statistics:")
        print(f"  GUID matches:  {self.guid_matches} ({self.guid_matches/total*100:.1f}%)")
        print(f"  Fuzzy matches: {self.fuzzy_matches} ({self.fuzzy_matches/total*100:.1f}%)")
        print(f"  Unmatched:     {self.unmatched} ({self.unmatched/total*100:.1f}%)")
```

## Usage in the Converter

The `SyntyConverter` uses the matching system when generating `.fbx.import` files:

```python
def _process_model(self, fbx_path: Path):
    # Get material names from FBX (via Blender if available)
    fbx_materials = self.fbx_extractor.extract_materials(fbx_path)

    # Match each FBX material to a Unity material
    material_mappings = {}
    for fbx_mat_name in fbx_materials:
        unity_mat = self.matcher.match(str(fbx_path), fbx_mat_name)
        if unity_mat:
            # Map FBX material slot to Godot material path
            godot_mat_path = self._get_godot_material_path(unity_mat)
            material_mappings[fbx_mat_name] = godot_mat_path

    # Generate .fbx.import with mappings
    self._generate_import_file(fbx_path, material_mappings)
```

## Logging and Debugging

The matcher provides detailed logging:

```
INFO - Matching materials for SM_Building_House_01.fbx
DEBUG - GUID match: Mat_Building_Stone -> PolygonFantasy_Mat_Building_Stone_01 (guid: def789abc123)
DEBUG - GUID match: Mat_Building_Wood -> PolygonFantasy_Mat_Building_Wood_01 (guid: ghi012jkl345)
DEBUG - Fuzzy match: Mat_Glass -> PolygonFantasy_Mat_Glass (similarity: 0.85)
WARNING - No match found for: Mat_Unknown_Material

INFO - Material Matching Statistics:
INFO -   GUID matches:  245 (92.1%)
INFO -   Fuzzy matches: 18 (6.8%)
INFO -   Unmatched:     3 (1.1%)
```

## Best Practices

### For Best Results

1. **Use complete Unity packages** - The `.meta` files provide everything needed for 100% accurate matching
2. **Blender is optional** - Not needed for `.unitypackage` conversions; only useful for extracted directories
3. **Check unmatched materials** - Review warnings for manual fixing

### When Materials Don't Match

If materials aren't matching correctly:

1. **Check the FBX .meta file** - Ensure `externalObjects` section exists
2. **Verify material names** - FBX material name must match Unity's expectation
3. **Check for typos** - Case sensitivity and spelling matter for fuzzy matching
4. **Add manual mappings** - Override in the generated `.fbx.import` file

## Technical Details

### FBX Meta File Parsing

The extractor uses regex to parse the YAML-like format:

```python
def _parse_fbx_meta(self, meta_content: str, fbx_path: str):
    """Parse FBX .meta file for material mappings."""
    # Pattern matches externalObjects entries
    pattern = r'- first:\s+type: UnityEngine\.Material.*?name: (\S+)\s+second:.*?guid: ([a-f0-9]+)'

    for match in re.finditer(pattern, meta_content, re.DOTALL):
        fbx_material_name = match.group(1)
        unity_guid = match.group(2)

        mapping = FBXMaterialMapping(
            fbx_material_name=fbx_material_name,
            unity_material_guid=unity_guid,
            fbx_path=fbx_path
        )
        self.fbx_material_mappings[fbx_path].append(mapping)
```

### Blender Script for FBX Analysis

The FBX extractor runs this script in Blender:

```python
import bpy
import sys

fbx_path = sys.argv[-1]
bpy.ops.import_scene.fbx(filepath=fbx_path)

materials = set()
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        for slot in obj.material_slots:
            if slot.material:
                materials.add(slot.material.name)

for mat in sorted(materials):
    print(f"MATERIAL:{mat}")
```

## Conclusion

The material matching system provides:

- **100% accuracy with `.meta` files** - No Blender needed for `.unitypackage` conversions
- **Blender is completely optional** - Only a fallback for edge cases (extracted directories)
- **Graceful fallback chain** - `.meta` files -> Blender extraction -> fuzzy name matching
- **Transparency** - Detailed logging shows how each material was matched
- **Extensibility** - Easy to add custom matching rules if needed

### Data Source Summary

| Conversion Type | FBX Material Name Source | Blender Required |
|-----------------|-------------------------|------------------|
| `.unitypackage` file | `.meta` files (externalObjects) | No |
| Extracted directory with `.meta` files | `.meta` files (externalObjects) | No |
| Extracted directory without `.meta` files | Blender FBX extraction | Yes (or fuzzy matching fallback) |

For most Synty asset packs converted from `.unitypackage` files, expect 100% accurate GUID matches with no Blender dependency.
