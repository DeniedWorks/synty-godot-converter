# Changelog

All notable changes to synty-converter-BLUE will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-01-29

### Added
- Initial release of synty-converter-BLUE
- 12-step conversion pipeline from Unity to Godot
- 7 drop-in Godot shaders:
  - polygon.gdshader - General purpose PBR
  - foliage.gdshader - Vegetation with wind animation
  - crystal.gdshader - Transparent/refractive materials
  - water.gdshader - Water with waves, foam, caustics
  - clouds.gdshader - Volumetric clouds
  - particles.gdshader - Particle effects
  - skydome.gdshader - Sky gradients
- 3-tier shader detection system:
  - GUID lookup (114+ known Unity shader GUIDs)
  - Scoring-based name pattern matching
  - Property-based detection
- Unity .unitypackage extraction and parsing
- Unity .mat YAML parsing with regex (handles non-standard Unity tags)
- Material property mapping (400+ Unity to Godot mappings)
- .tres ShaderMaterial file generation
- MaterialList.txt parsing for mesh-material assignments
- Godot CLI integration for FBX to TSCN conversion
- Comprehensive documentation:
  - README.md with quick start
  - User guide
  - Architecture documentation
  - Troubleshooting guide
  - Full API reference
  - Shader parameter reference
  - Unity GUID reference

### Known Limitations
- Some pack-specific Unity shaders may not be in GUID database
- Requires MaterialList.txt for mesh-material mapping
- Godot CLI may timeout on very large packs (adjustable with --godot-timeout)
