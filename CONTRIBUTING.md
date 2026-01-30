# Contributing to synty-converter-BLUE

Thank you for your interest in contributing! This guide will help you get started.

## Table of Contents
- [Development Setup](#development-setup)
- [Code Standards](#code-standards)
- [Adding New Shader GUIDs](#adding-new-shader-guids)
- [Adding Property Mappings](#adding-property-mappings)
- [Testing Guidelines](#testing-guidelines)
- [Pull Request Process](#pull-request-process)

## Development Setup

### Prerequisites
- Python 3.10+
- Godot 4.6 (mono version recommended)
- A Synty asset pack for testing

### Clone and Run
```bash
git clone <repository-url>
cd synty-converter-BLUE

# No dependencies to install - uses only Python standard library

# Test with a Synty pack
python converter.py \
  --unity-package "path/to/Pack.unitypackage" \
  --source-files "path/to/SourceFiles" \
  --output "output" \
  --godot "path/to/Godot.exe"
```

## Code Standards

### Python Style
- Follow PEP 8 guidelines
- Use type hints for all function signatures
- Use Google-style docstrings

### Docstring Example
```python
def function_name(param1: Type1, param2: Type2) -> ReturnType:
    """Short one-line description.

    Longer description if needed.

    Args:
        param1: Description of param1.
        param2: Description of param2.

    Returns:
        Description of return value.

    Example:
        >>> result = function_name(value1, value2)
    """
```

### Logging
- Use `logging` module, not print statements
- DEBUG for development details
- INFO for user-facing status
- WARNING for recoverable issues
- ERROR for failures

## Adding New Shader GUIDs

When you encounter an unknown Unity shader:

1. **Find the GUID** in a Unity .mat file:
   ```yaml
   m_Shader: {fileID: ..., guid: abc123def456..., type: 3}
   ```

2. **Determine the matching Godot shader** by examining material properties

3. **Add to SHADER_GUID_MAP** in `shader_mapping.py`:
   ```python
   SHADER_GUID_MAP = {
       # ... existing entries ...
       "abc123def456...": "polygon.gdshader",  # PackName - ShaderName
   }
   ```

4. **Update documentation**:
   - Add to `docs/api/constants.md`
   - Add to `docs/unity-reference.md`

## Adding Property Mappings

To map a new Unity property to Godot:

1. **Identify the Unity property name** (e.g., `_New_Property`)

2. **Determine the Godot parameter** (e.g., `new_property`)

3. **Add to the appropriate map** in `shader_mapping.py`:
   - `TEXTURE_MAP_*` for textures
   - `FLOAT_MAP_*` for floats
   - `COLOR_MAP_*` for colors

4. **Handle special cases**:
   - Boolean properties: Add to `BOOLEAN_FLOAT_PROPERTIES`
   - Alpha=0 colors: Add to `ALPHA_FIX_PROPERTIES`

5. **Update documentation** in `docs/api/constants.md`

## Testing Guidelines

### Manual Testing
1. Convert a Synty pack with `--dry-run --verbose` first
2. Check conversion_log.txt for warnings
3. Open in Godot and verify materials look correct
4. Test each shader type (polygon, foliage, crystal, water, etc.)

### Test Checklist
- [ ] Materials parse without errors
- [ ] Correct shader type detected
- [ ] Textures resolve correctly
- [ ] Colors look correct (no alpha=0 issues)
- [ ] Wind animation works on foliage
- [ ] Water effects animate properly
- [ ] Crystal fresnel/refraction works

## Pull Request Process

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/add-new-guid
   ```

2. **Make your changes**:
   - Follow code standards
   - Update documentation
   - Test with at least one Synty pack

3. **Commit with clear messages**:
   ```bash
   git commit -m "Add shader GUID for PolygonHorror pack"
   ```

4. **Open a pull request**:
   - Describe what you changed
   - Note which packs you tested with
   - Include any relevant log output

5. **Address feedback** from review

## Questions?

- Check existing documentation in `docs/`
- Open an issue for discussion
- Look at existing code for patterns
