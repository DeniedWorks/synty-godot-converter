# Troubleshooting Guide

Common issues and solutions when using the Synty Unity-to-Godot Converter.

**For detailed implementation context, see:**
- [Step 3: Extract Unity Package](./steps/03-extract-unity-package.md) - Package extraction details
- [Step 4: Parse Materials](./steps/04-parse-materials.md) - Material parsing and regex patterns
- [Step 6: Shader Detection](./steps/06-shader-detection.md) - Shader detection algorithm

## Table of Contents

- [Installation Issues](#installation-issues)
- [Conversion Errors](#conversion-errors)
- [Material Issues](#material-issues)
- [Godot Import Issues](#godot-import-issues)
- [Visual Issues](#visual-issues)
- [Understanding the Log](#understanding-the-log)
- [Unity Quirks](#unity-quirks)

---

## Installation Issues

### Python Version Errors

**Symptom**: `SyntaxError` or `ImportError` when running the converter.

**Cause**: The converter requires Python 3.10+ for type hint syntax (`dict[str, str]` instead of `Dict[str, str]`).

**Solution**:
```bash
# Check your Python version
python --version

# Should show Python 3.10.x or higher
# If not, install Python 3.10+ from python.org
```

**Windows-specific**: If you have multiple Python versions, use:
```bash
py -3.10 converter.py --help
```

---

### Godot Not Found

**Symptom**: Error message "Godot executable not found" or Godot CLI fails silently.

**Cause**: The `--godot` path is incorrect or Godot isn't the Mono/CLR version.

**Solution**:

1. **Verify the path exists**:
   ```bash
   # Windows
   dir "C:\Godot\Godot_v4.6-stable_mono_win64\Godot_v4.6-stable_mono_win64.exe"
   ```

2. **Use the correct executable**:
   - Windows: `Godot_v4.6-stable_mono_win64.exe` (not `Godot_v4.6-stable_mono_win64_console.exe`)
   - The path must be absolute, not relative

3. **Test Godot CLI manually**:
   ```bash
   "C:\Godot\Godot_v4.6-stable_mono_win64\Godot_v4.6-stable_mono_win64.exe" --headless --version
   ```
   Should output: `4.6.stable.mono`

---

## Conversion Errors

### "Unity package not found"

**Symptom**: Fatal error at Step 1 validation.

**Cause**: The `--unity-package` path doesn't point to a valid file.

**Solution**:
```bash
# Verify the file exists
dir "C:\SyntyComplete\POLYGON_NatureBiomes_EnchantedForest_Unity_2022_3_v1_6_1.unitypackage"

# Common issues:
# - Typo in path
# - Missing quotes around path with spaces
# - File was moved or renamed
```

**Tip**: Copy the path directly from Windows Explorer address bar.

---

### "Textures directory missing"

**Symptom**: Fatal error about SourceFiles/Textures not existing.

**Cause**: The `--source-files` argument points to the wrong folder level.

**Solution**:

The SourceFiles folder structure varies between Synty packs:

```
# Some packs:
POLYGON_Pack_SourceFiles/
  SourceFiles/              <-- Use THIS path
    FBX/
    Textures/

# Other packs:
POLYGON_Pack/
  SourceFiles/              <-- Use THIS path
    FBX/
    Textures/
```

**Check the structure**:
```bash
dir "C:\SyntyComplete\POLYGON_EnchantedForest_SourceFiles_v2\SourceFiles"

# Should show:
# FBX/
# Textures/
# MaterialList.txt (or similar)
```

---

### "Failed to parse material"

**Symptom**: Warning in log about material parsing failure, material is skipped.

**Cause**: Corrupted or non-standard Unity material file.

**Solution**:

1. **Check if material is critical**: Most packs have 80-150 materials; a few failures are normal.

2. **Inspect the material** (advanced):
   ```bash
   # Extract and view the problematic .mat file
   python -c "
   import tarfile, gzip
   with tarfile.open('package.unitypackage', 'r:gz') as tar:
       for member in tar.getnames():
           if 'MaterialName' in member:
               print(member)
   "
   ```

3. **Common causes**:
   - Empty or truncated material file
   - Material uses experimental Unity features
   - Character encoding issues (non-UTF8)

**Workaround**: Create the material manually in Godot if needed.

---

## Material Issues

### Wrong Shader Detected

**Symptom**: Material uses incorrect shader (e.g., foliage on a rock, polygon on a tree).

**Cause**: The 3-tier detection system made a wrong choice:
1. Unknown shader GUID
2. Name pattern matched incorrectly
3. Property detection was ambiguous

**Diagnosis**:
```bash
# Run with verbose logging
python converter.py --verbose ... 2>&1 | grep "Material_Name"

# Look for lines like:
# "Detected shader 'foliage' for 'Rock_Moss_01' (score: 25)"
```

**Solutions**:

1. **Report the GUID**: Check `conversion_log.txt` for "Unknown shader GUID" warnings. Report these so they can be added to `SHADER_GUID_MAP`.

2. **Manual override**: Edit the generated `.tres` file to point to correct shader:
   ```ini
   [ext_resource type="Shader" path="res://shaders/polygon.gdshader" id="1"]
   ```

3. **Adjust scoring weights** (advanced): Edit `SHADER_NAME_PATTERNS` in `shader_mapping.py` to increase/decrease pattern weights.

---

### Missing Textures

**Symptom**: Material in Godot shows pink/magenta or wrong texture.

**Cause**: Texture file wasn't found in SourceFiles or has different name than referenced.

**Diagnosis**:
```bash
# Check conversion_log.txt for texture warnings
grep -i "texture" conversion_log.txt | grep -i "missing\|not found\|warning"
```

**Common causes**:

1. **Shared textures**: Some textures are shared across multiple Synty packs. If you're converting one pack, it may reference textures from another.
   ```
   # Example: EnchantedForest references "Generic_Biome_Texture_01"
   # which lives in the core NatureBiomes pack
   ```

2. **Case sensitivity**: Windows is case-insensitive, but the texture map uses lowercase keys.

3. **Different extensions**: Unity references texture by name; SourceFiles may use `.png` while Unity expected `.tga`.

**Solutions**:

1. **Find the texture**: Search all your Synty SourceFiles folders:
   ```bash
   dir /s "C:\SyntyComplete\*Generic_Biome_Texture*"
   ```

2. **Copy missing textures**: Copy found textures to `output/textures/`

3. **Use placeholder**: For non-critical textures, use a solid color texture

---

### Colors Look Wrong

**Symptom**: Materials appear too dark, invisible, or have wrong tint.

**Cause**: Unity's alpha=0 color storage quirk wasn't detected for this property.

**Background**: Unity stores many color properties with `alpha=0` even when the color should be fully visible. The converter has a list of known affected properties (`ALPHA_FIX_PROPERTIES`), but may miss some.

**Diagnosis**:
```bash
# Check the .tres file for suspicious colors
grep "Color(" materials/Problem_Material.tres

# Look for: Color(0.5, 0.3, 0.2, 0)
#                                 ^ alpha is 0!
```

**Solution**:

1. **Quick fix**: Edit the `.tres` file and change alpha from 0 to 1:
   ```ini
   # Before
   shader_parameter/base_color = Color(0.5, 0.3, 0.2, 0)

   # After
   shader_parameter/base_color = Color(0.5, 0.3, 0.2, 1)
   ```

2. **Permanent fix**: Add the property name to `ALPHA_FIX_PROPERTIES` in `shader_mapping.py`:
   ```python
   ALPHA_FIX_PROPERTIES = [
       "_Problem_Color_Property",
       # ...
   ]
   ```

---

## Godot Import Issues

### Timeout During Import

**Symptom**: Converter hangs at "Running Godot import..." or reports timeout.

**Cause**: Large asset packs (300+ FBX files) take longer than the default 600-second timeout.

**Solution**:

1. **Increase timeout**:
   ```bash
   python converter.py ... --godot-timeout 1800  # 30 minutes
   ```

2. **Skip Godot CLI** and import manually:
   ```bash
   python converter.py ... --skip-godot-cli

   # Then open the output folder in Godot Editor
   # and let it import at its own pace
   ```

3. **Convert in batches**: For very large packs, split FBX files into groups and convert separately.

---

### FBX Import Failures

**Symptom**: Some meshes missing from `meshes/` folder or Godot errors about FBX.

**Cause**: Godot's FBX importer has limitations, especially with:
- Very old FBX format versions
- Binary FBX (vs ASCII)
- Complex armatures/rigs

**Diagnosis**:
```bash
# Check Godot's output in conversion_log.txt
grep -i "error\|fail\|fbx" conversion_log.txt
```

**Solutions**:

1. **Check Godot version**: Ensure you're using Godot 4.6+ which has improved FBX support.

2. **Re-export from Unity**: If you have Unity, re-export the FBX with "ASCII" format.

3. **Use Blender**: Import FBX into Blender, export as glTF 2.0, convert that instead.

---

### Missing Materials on Meshes

**Symptom**: Meshes load in Godot but appear with default material (gray).

**Cause**: `MaterialList.txt` mapping didn't include this mesh, or material name doesn't match.

**Diagnosis**:
```bash
# Check if mesh is in the mapping
grep "MeshName" mesh_material_mapping.json

# Check if material exists
dir materials\ExpectedMaterial.tres
```

**Solutions**:

1. **Manual assignment**: In Godot, select the MeshInstance3D and drag the `.tres` material onto the Material slot.

2. **Check MaterialList.txt**: Ensure the mesh is listed with its materials. Some Synty packs have incomplete MaterialList files.

3. **Re-convert**: Sometimes a second conversion pass picks up materials that were parsed late.

---

## Visual Issues

### Wind Not Working on Foliage

**Symptom**: Trees and plants are static, no wind animation.

**Cause**: Global shader uniforms aren't set up in the scene.

**Background**: Foliage shaders require global uniforms that must be set at runtime:
- `WindDirection` (vec3)
- `WindIntensity` (float)
- `GaleStrength` (float)

**Solution**:

1. **Check project.godot**: Ensure it has the `[shader_globals]` section with wind uniforms.

2. **Set at runtime**: Add a script to your scene:
   ```gdscript
   func _ready():
       RenderingServer.global_shader_parameter_set("WindDirection", Vector3(1, 0, 0))
       RenderingServer.global_shader_parameter_set("WindIntensity", 0.5)
       RenderingServer.global_shader_parameter_set("GaleStrength", 0.0)

   func _process(delta):
       # Animate wind direction
       var time = Time.get_ticks_msec() / 1000.0
       var dir = Vector3(sin(time * 0.3), 0, cos(time * 0.3))
       RenderingServer.global_shader_parameter_set("WindDirection", dir)
   ```

3. **Enable breeze on material**: Check that the material has `enable_breeze = true`:
   ```ini
   shader_parameter/enable_breeze = true
   shader_parameter/breeze_strength = 0.5
   ```

---

### Water Looks Flat

**Symptom**: Water material shows but lacks waves, foam, or depth effect.

**Cause**: Water features are disabled by default or global uniforms missing.

**Solution**:

1. **Enable water features** in the material `.tres`:
   ```ini
   shader_parameter/enable_normals = true
   shader_parameter/enable_ocean_waves = true
   shader_parameter/enable_shore_foam = true
   shader_parameter/enable_depth = true
   ```

2. **Set global uniforms**:
   ```gdscript
   RenderingServer.global_shader_parameter_set("WindDirection", Vector3(1, 0, 0))
   RenderingServer.global_shader_parameter_set("GaleStrength", 0.3)
   ```

3. **Check depth texture**: Water depth effects require the scene to have a depth pre-pass. Add a Camera3D with `depth` enabled.

---

### Foliage Too Shiny

**Symptom**: Leaves and bark look wet/metallic instead of matte.

**Cause**: Missing smoothness/metallic values (Unity defaults differ from Godot).

**Solution**:

Edit the material `.tres` to add matte settings:
```ini
shader_parameter/leaf_smoothness = 0.1
shader_parameter/trunk_smoothness = 0.15
shader_parameter/leaf_metallic = 0.0
shader_parameter/trunk_metallic = 0.0
```

**Note**: The converter should apply these defaults automatically. If it didn't, check that `SHADER_DEFAULTS` in `shader_mapping.py` has the foliage entries.

---

## Understanding the Log

### Reading conversion_log.txt

The log file contains all conversion output with timestamps:

```
2024-01-29 10:15:32 [INFO] Starting conversion pipeline
2024-01-29 10:15:32 [INFO] Step 1: Validating inputs...
2024-01-29 10:15:33 [INFO] Step 3: Extracting Unity package...
2024-01-29 10:15:35 [INFO] Found 127 materials in package
2024-01-29 10:15:36 [WARNING] Unknown shader GUID: abc123... for material "Special_Mat_01"
2024-01-29 10:15:36 [WARNING] Texture not found: "Missing_Texture_01"
2024-01-29 10:15:40 [ERROR] Failed to parse material "Corrupted_Mat": invalid YAML
2024-01-29 10:16:00 [INFO] Conversion complete. Summary:
```

### Log Levels

| Level | Meaning | Action Required |
|-------|---------|-----------------|
| `INFO` | Normal progress | None |
| `WARNING` | Non-fatal issue, conversion continues | Review after conversion |
| `ERROR` | Problem with specific item, skipped | May need manual fix |
| `CRITICAL` | Fatal error, conversion aborted | Fix before re-running |

### Warning vs Error Severity

**Warnings (usually safe to ignore)**:
- "Unknown shader GUID" - Falls back to name/property detection
- "Texture not found" - Material works but missing one texture
- "No MaterialList.txt" - Mesh-material mapping unavailable

**Errors (may need attention)**:
- "Failed to parse material" - Material completely skipped
- "Godot CLI timeout" - Meshes not converted
- "FBX import failed" - Model not usable

### Conversion Summary

At the end of the log:
```
=== Conversion Summary ===
Materials parsed:    127
Materials generated: 125  # 2 failed
Textures copied:     89
Textures missing:    3
Shaders copied:      7
FBX files copied:    245
Meshes converted:    312
Warnings:            5
Errors:              2
```

---

## Unity Quirks

### Alpha=0 Color Fix

**The Problem**:

Unity frequently stores color properties with `alpha=0` even when the color should be fully opaque. This is a Unity editor quirk, not intentional design.

Example from a Unity `.mat` file:
```yaml
m_Colors:
  - _Base_Color: {r: 0.8, g: 0.6, b: 0.4, a: 0}
  - _Fresnel_Color: {r: 0.3, g: 0.5, b: 1.0, a: 0}
```

Both colors have `a: 0`, making them invisible in Godot.

**The Fix**:

The converter automatically detects this and fixes alpha to 1.0 when:
1. Alpha equals exactly 0.0
2. At least one RGB component is non-zero
3. The property name is in the known-affected list

**Affected Properties** (partial list):
- Crystal/Refractive: `_Base_Color`, `_Deep_Color`, `_Shallow_Color`, `_Fresnel_Color`
- Water: `_Water_Deep_Color`, `_Water_Shallow_Color`, `_Foam_Color`
- Foliage: `_Leaf_Base_Color`, `_Trunk_Base_Color`, `_Emissive_Color`
- Neon/Glow: `_Neon_Colour_01`, `_Neon_Colour_02`, `_Glow_Colour`
- General: `_Color`, `_BaseColor`, `_Color_Tint`, `_Hair_Color`, `_Skin_Color`

**If a color still looks wrong**: The property may not be in the fix list. Add it to `ALPHA_FIX_PROPERTIES` in `shader_mapping.py`.

---

### Boolean Properties as Floats

**The Problem**:

Unity stores boolean shader toggles as floating-point numbers:
- `0.0` = false/disabled
- `1.0` = true/enabled

Example from Unity `.mat`:
```yaml
m_Floats:
  - _Enable_Breeze: 1
  - _Enable_Snow: 0
  - _AlphaClip: 1
```

**The Fix**:

The converter identifies known boolean properties and converts them:
```python
# In shader_mapping.py
BOOL_PROPERTIES = [
    "_Enable_Breeze", "_Enable_Light_Wind", "_Enable_Strong_Wind",
    "_Enable_Fresnel", "_Enable_Depth", "_Enable_Refraction",
    "_Enable_Snow", "_Enable_Frosting", "_Enable_Emission",
    "_AlphaClip", "_Enable_Soft_Particles", "_Enable_Camera_Fade",
    # ... many more
]
```

**Result in .tres**:
```ini
shader_parameter/enable_breeze = true
shader_parameter/enable_snow = false
shader_parameter/alpha_clip = true
```

---

### Default Value Overrides

**The Problem**:

Some Unity materials omit properties entirely, relying on Unity's shader defaults. These defaults often don't match what looks good in Godot.

**Example**: Crystal materials in Unity default to `opacity=1.0` (fully opaque), but crystals should be translucent.

**The Fix**:

The converter applies sensible defaults when properties are missing:

| Shader | Property | Unity Default | Converter Default | Reason |
|--------|----------|---------------|-------------------|--------|
| Crystal | `opacity` | 1.0 (opaque) | 0.7 | Crystals should be translucent |
| Foliage | `leaf_smoothness` | Missing | 0.1 | Leaves are matte, not glossy |
| Foliage | `trunk_smoothness` | Missing | 0.15 | Bark is rough |
| Water | `smoothness` | Missing | 0.95 | Water is very reflective |

**To customize defaults**: Edit `SHADER_DEFAULTS` in `shader_mapping.py`.

---

## Related Documentation

- [Architecture](architecture.md) - Technical deep dive
- [Unity Reference](unity-reference.md) - Unity shader GUIDs and properties
- [Shader Reference](shader-reference.md) - Godot shader parameters
- [Step 3: Extract Unity Package](./steps/03-extract-unity-package.md) - Package extraction details
- [Step 4: Parse Materials](./steps/04-parse-materials.md) - Material parsing implementation
- [Step 6: Shader Detection](./steps/06-shader-detection.md) - Detection algorithm and property mapping
