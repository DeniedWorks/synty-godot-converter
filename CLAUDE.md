# Synty Converter

A Python tool for converting Synty Unity asset packs to Godot 4.

## Environment

- **Python**: `C:\Users\alexg\AppData\Local\Programs\Python\Python313\python.exe`
- **Godot**: `C:\Godot\Godot_v4.6-stable_mono_win64\Godot_v4.6-stable_mono_win64.exe`
- **Synty Assets**: `C:\SyntyComplete\` contains all Synty source file packs

## Quick Commands

```bash
# Run converter
python converter.py --unity-package "Pack.unitypackage" --source-files "Pack_SourceFiles" --output "output_dir" --godot "path/to/godot.exe"

# Build exe
python -m PyInstaller synty_converter.spec --noconfirm

# Create release
git tag v2.X && git push origin v2.X
gh release create v2.X dist/SyntyConverter.exe --title "v2.X - Title" --notes "Release notes"
```

## Project Structure

```
synty-converter/
├── converter.py          # Main CLI pipeline (Steps 1-12)
├── gui.py                # Tkinter GUI wrapper
├── godot_converter.gd    # GDScript for Godot-side mesh processing
├── material_list.py      # MaterialList.txt parsing, mesh-material mapping
├── shader_mapping.py     # Unity shader GUID → Godot shader mapping
├── tres_generator.py     # .tres material file generation
├── unity_parser.py       # Unity .mat file parsing
├── shaders/              # Godot shader files (polygon, foliage, water, etc.)
├── dist/                 # Built exe output
└── synty_converter.spec  # PyInstaller spec file
```

## Key Architecture

- **Per-pack isolation**: Each pack gets its own folder with materials/, textures/, models/, meshes/
- **Per-pack mapping**: `mesh_material_mapping.json` is in each pack folder (not shared)
- **Dynamic shader discovery**: Searches project for existing shaders before copying
- **FBX path cleaning**: Strips SourceFiles/FBX/Models prefixes from paths

## Testing

Use medium-sized packs for testing:
- `POLYGON_NatureBiomes_EnchantedForest` - Good variety of assets
- `POLYGON_Prototype` - Small and fast

Test output location: `C:\temp\converter_test\`

---

Last Updated: 2026-02-01
Version: 2.2
