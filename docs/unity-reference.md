# Unity Reference - Synty Shader Converter

Quick reference for Unity material parsing and shader detection.

**For detailed implementation documentation, see:**
- [Step 3: Extract Unity Package](./steps/03-extract-unity-package.md) - Package extraction and GUID mapping
- [Step 4: Parse Materials](./steps/04-parse-materials.md) - Material YAML parsing details
- [Step 6: Shader Detection](./steps/06-shader-detection.md) - Full shader detection algorithm

**Related Documentation:**
- [Architecture](./architecture.md) - Core architecture and usage
- [Shader Reference](./shader-reference.md) - Godot shader details and output format
- [Troubleshooting Guide](./troubleshooting.md) - Common issues and solutions

---

## Table of Contents

- [Quick GUID Lookup](#quick-guid-lookup)
- [Unity Material Structure](#unity-material-structure)
- [Shader Detection Summary](#shader-detection-summary)
- [Parameter Mapping Quick Reference](#parameter-mapping-quick-reference)
- [Unity Parsing Quirks](#unity-parsing-quirks)
- [Texture Handling](#texture-handling)
- [Appendix: Material Property Statistics](#appendix-material-property-statistics)

---

## Quick GUID Lookup

The 10 most commonly used shader GUIDs across all Synty packs:

| GUID | Shader Name | Godot Shader | Frequency |
|------|-------------|--------------|-----------|
| `0730dae39bc73f34796280af9875ce14` | Synty PolygonLit | polygon.gdshader | Very High |
| `9b98a126c8d4d7a4baeb81b16e4f7b97` | Synty Foliage | foliage.gdshader | Very High |
| `933532a4fcc9baf4fa0491de14d08ed7` | Unity URP Lit | polygon.gdshader | High |
| `3b44a38ec6f81134ab0f820ac54d6a93` | Generic_Standard | polygon.gdshader | High |
| `436db39b4e2ae5e46a17e21865226b19` | Synty Water | water.gdshader | Medium |
| `5808064c5204e554c89f589a7059c558` | Synty Crystal | crystal.gdshader | Medium |
| `19e269a311c45cd4482cf0ac0e694503` | Synty Triplanar | polygon.gdshader | Medium |
| `ab6da834753539b4989259dbf4bcc39b` | ProRacer_Standard | polygon.gdshader | Medium |
| `de1d86872962c37429cb628a7de53613` | Synty Skydome | skydome.gdshader | Low |
| `0736e099ec10c9e46b9551b2337d0cc7` | Synty Particles | particles.gdshader | Low |

---

## Unity Material Structure

All Unity .mat files use YAML 1.1 format with this structure:

```yaml
%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!21 &2100000
Material:
  m_Name: MaterialName
  m_Shader: {fileID: 4800000, guid: SHADER_GUID, type: 3}

  m_TexEnvs:
    - _Texture_Name:
        m_Texture: {fileID: 2800000, guid: TEXTURE_GUID, type: 3}
        m_Scale: {x: 1, y: 1}
        m_Offset: {x: 0, y: 0}

  m_Floats:
    - _Parameter_Name: 0.5

  m_Colors:
    - _Color_Name: {r: 1, g: 1, b: 1, a: 1}
```

### Texture GUID Resolution

Materials reference textures by GUID, not path. We need to build a mapping:

1. Each asset in the Unity package has a `pathname` file containing its path
2. The folder name IS the GUID
3. Build map: `GUID -> texture_path`

---

## Shader Detection Summary

The converter uses a **3-tier detection system** documented in detail at [Step 6: Shader Detection](./steps/06-shader-detection.md).

**Quick Summary:**

1. **Tier 1: GUID Lookup** - Direct match against 56 known shader GUIDs
2. **Tier 2: Name Pattern Scoring** - Regex patterns with weighted scores (18 patterns)
3. **Tier 3: Property-Based Detection** - Bonus scoring based on shader-specific properties

**Core Synty Shaders (most common):**

| GUID | Shader | Notes |
|------|--------|-------|
| `0730dae39bc73f34796280af9875ce14` | polygon | Main prop shader |
| `9b98a126c8d4d7a4baeb81b16e4f7b97` | foliage | Trees/plants |
| `436db39b4e2ae5e46a17e21865226b19` | water | Water surfaces |
| `5808064c5204e554c89f589a7059c558` | crystal | Crystals/gems |
| `0736e099ec10c9e46b9551b2337d0cc7` | particles | Effects |
| `de1d86872962c37429cb628a7de53613` | skydome | Sky gradient |
| `4a6c8c23090929241b2a55476a46a9b1` | clouds | Volumetric |

For the complete list of 56 GUIDs organized by category, see [Step 6: SHADER_GUID_MAP Reference](./steps/06-shader-detection.md#shader_guid_map-reference).

**Name Pattern Fallback:**

| Pattern | Godot Shader | Score |
|---------|--------------|-------|
| `triplanar` | polygon | 60 |
| `caustics` | water | 55 |
| `fresnel`, `refractive` | crystal | 55 |
| `crystal`, `gem`, `glass` | crystal | 35-45 |
| `water`, `ocean`, `river` | water | 45 |
| `tree`, `fern`, `grass`, `leaf` | foliage | 20-25 |
| `particle`, `fx_` | particles | 45 |
| `cloud`, `fog` | clouds | 35-45 |
| `skydome`, `skybox` | skydome | 55 |

---

## Parameter Mapping Quick Reference

For complete property mapping tables, see [Step 6: Property Mapping Dictionaries](./steps/06-shader-detection.md#property-mapping-dictionaries).

**Property naming convention:**
- Unity: `_Base_Texture`, `_Enable_Breeze`
- Godot: `base_texture`, `enable_breeze`

**Key texture mappings:**

| Unity | Godot | Shader |
|-------|-------|--------|
| `_MainTex`, `_BaseMap`, `_Albedo_Map` | `base_texture` | polygon |
| `_Leaf_Texture` | `leaf_color` | foliage |
| `_Trunk_Texture` | `trunk_color` | foliage |
| `_Base_Albedo` | `base_albedo` | crystal |
| `_Normal_Texture` | `normal_texture` | water |
| `_Caustics_Flipbook` | `caustics_flipbook` | water |

**Property name alternatives:**

Unity materials may use different property names for the same slot. The converter checks alternatives in order (first match wins). See the step docs for complete alternative mappings.

---

## Unity Parsing Quirks

This section provides a brief overview of Unity material parsing challenges. For detailed troubleshooting and solutions, see **[Troubleshooting](./troubleshooting.md#unity-quirks)**.

### Summary of Key Issues

**Alpha=0 Color Fix**: Unity stores many color properties with `alpha=0` even when colors should be visible. The converter automatically fixes this for known properties.

**Boolean Properties as Floats**: Unity stores boolean toggles as floats (`0.0` or `1.0`). The converter handles this automatically.

**Default Value Overrides**: Some materials need sensible defaults when Unity values are missing:

| Shader | Property | Unity Issue | Converter Default |
|--------|----------|-------------|-------------------|
| Crystal | `opacity` | Often 1.0 (fully opaque) | 0.7 (translucent) |
| Foliage | `leaf_smoothness` | Missing | 0.1 (matte) |
| Foliage | `trunk_smoothness` | Missing | 0.15 (slightly rough) |
| Foliage | `leaf_metallic` | Missing | 0.0 |
| Foliage | `trunk_metallic` | Missing | 0.0 |

**Unity YAML Format**: Unity .mat files use non-standard YAML with custom tags (`!u!21`). Use regex extraction rather than YAML parsing:

```python
# Extract Material section
material_match = re.search(
    r"---\s*!u!21[^\n]*\nMaterial:\s*\n((?:.*\n)*?)(?=---|\Z)",
    content, re.MULTILINE
)
```

---

## Texture Handling

### Supported Texture Formats

Based on analysis of all Synty packs, only 3 formats are used:

| Format | Usage | Notes |
|--------|-------|-------|
| PNG | 76% | Primary format |
| TGA | 23% | Secondary format |
| JPG/JPEG | <1% | Rare |

```python
SUPPORTED_TEXTURE_EXTENSIONS = {".png", ".tga", ".jpg", ".jpeg"}
```

### Texture Discovery

Build a name->path map from SourceFiles:

```python
def build_texture_map(textures_dir: Path) -> dict[str, Path]:
    """Map texture names (lowercase, no extension) to file paths."""
    texture_map = {}
    for tex_file in textures_dir.rglob("*"):
        if tex_file.suffix.lower() in {".png", ".jpg", ".jpeg", ".tga"}:
            # Key: lowercase stem for fuzzy matching
            texture_map[tex_file.stem.lower()] = tex_file
    return texture_map
```

### Texture Resolution Flow

```
Unity Material -> GUID -> pathname (from Unity metadata) -> texture name
                                                              |
                                              texture_map lookup
                                                              |
                                              SourceFiles path
```

### Missing Texture Handling

If a texture name from Unity doesn't exist in SourceFiles:
1. Log warning with material name and missing texture
2. Skip that texture slot in the generated .tres
3. Continue processing

---

## Appendix: Material Property Statistics

Based on analysis of **29 Unity packages** (~3,300 materials total):

### Original 9 Packs (978 materials)

| Pack | Materials | Primary Shaders |
|------|-----------|-----------------|
| POLYGON_Fantasy_Kingdom | 92 | PolygonLit, Generic_Standard |
| POLYGON_NatureBiomes_AlpineMountain | 139 | Foliage, PolygonLit, Triplanar |
| POLYGON_NatureBiomes_AridDesert | 108 | Foliage, PolygonLit, Heat Shimmer |
| POLYGON_NatureBiomes_EnchantedForest | 109 | Foliage, PolygonLit, Crystal |
| POLYGON_NatureBiomes_MeadowForest | 130 | Foliage, PolygonLit, Particles |
| POLYGON_NatureBiomes_SwampMarshland | 82 | Foliage, PolygonLit, Water |
| POLYGON_NatureBiomes_TropicalJungle | 123 | Foliage, PolygonLit |
| POLYGON_Nature (2021) | 78 | Amplify shaders (legacy) |
| POLYGON_Samurai_Empire | 226 | PolygonLit, Foliage, Character |

### Additional 16 Packs (~1,820 materials)

| Pack | Materials | Notable Shaders |
|------|-----------|-----------------|
| POLYGON_SciFi_Space | ~150 | UVScroll, Hologram, SciFiPlant |
| POLYGON_SciFi_Horror | ~120 | Screens, Decals, BlinkingLights |
| POLYGON_Horror_Mansion | ~100 | Neon, GrungeTriplanar, Ghost |
| POLYGON_Cyberpunk | ~180 | Hologram, Neon, EmissiveScroll |
| POLYGON_City | ~200 | Building, Parallax, LED panels |
| POLYGON_Zombies | ~90 | Blood overlay, Decals |
| POLYGON_Dark_Fantasy | ~140 | Magic Glow, Portal, Liquid |
| POLYGON_Viking | ~130 | Aurora, ParticlesLit, Cloth |
| POLYGON_Apocalypse | ~110 | Bloody, Triplanar_Basic, Grunge |
| POLYGON_Western | ~95 | PolygonLit, Dust system |
| POLYGON_Pirates | ~120 | Water, Cloth, Ropes |
| POLYGON_Dungeons | ~85 | Magic, Crystal, Torches |
| POLYGON_Farm | ~90 | PolygonLit, Foliage |
| POLYGON_Town | ~80 | PolygonLit, Glass |
| POLYGON_Kids | ~70 | PolygonLit (bright colors) |
| POLYGON_Prototype | ~60 | Basic PolygonLit |
| POLYGON_Elven_Realm | 127 | RockTriplanar, WaterFall, Aurora, NoFog |
| POLYGON_Pro_Racer | 230 | ProRacer_Standard, Decal, CutoutFlipbook, RoadSHD |
| POLYGON_Military | 111 | PolygonLit (standard PBR) |
| POLYGON_Modular_Fantasy_Hero | 33 | POLYGON_CustomCharacters (15-zone mask) |

### Summary Statistics

| Metric | Count |
|--------|-------|
| Total Packs Analyzed | 29 |
| Total Materials | ~3,300 |
| Unique Shader GUIDs | 56 |
| Unique Texture Properties | ~90 |
| Unique Float Properties | ~450+ |
| Unique Color Properties | ~220+ |
