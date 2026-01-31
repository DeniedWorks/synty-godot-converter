# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Synty Shader Converter GUI.

This spec file bundles:
- gui.py as the main script
- All Python converter modules
- Shader files (.gdshader)
- Godot converter script (godot_converter.gd)
- CustomTkinter data files
- tkinterdnd2 DLL files

Build with: pyinstaller synty_converter.spec
"""

import os
import sys
from pathlib import Path

# Import hooks for customtkinter data files
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect customtkinter data files (themes, images, etc.)
customtkinter_datas = collect_data_files('customtkinter')

# Collect tkinterdnd2 data files (platform-specific DLLs)
tkinterdnd2_datas = collect_data_files('tkinterdnd2')

# Collect Pillow data files (if needed for image processing)
pillow_datas = collect_data_files('PIL')

# Project root directory
project_root = Path(SPECPATH)

# Data files to include
datas = [
    # Shader files
    (str(project_root / 'shaders'), 'shaders'),
    # Godot converter script
    (str(project_root / 'godot_converter.gd'), '.'),
]

# Add collected package data
datas.extend(customtkinter_datas)
datas.extend(tkinterdnd2_datas)
datas.extend(pillow_datas)

# Hidden imports that PyInstaller might miss
hidden_imports = [
    # Converter modules
    'converter',
    'shader_mapping',
    'tres_generator',
    'unity_package',
    'unity_parser',
    'material_list',
    # GUI dependencies
    'customtkinter',
    'tkinterdnd2',
    'PIL',
    'PIL._tkinter_finder',
    # Standard library modules sometimes missed
    'json',
    'logging',
    'queue',
    're',
    'threading',
    'dataclasses',
    'pathlib',
    'tarfile',
    'gzip',
    'hashlib',
    'subprocess',
]

# Collect all customtkinter submodules
hidden_imports.extend(collect_submodules('customtkinter'))

# Analysis configuration
a = Analysis(
    ['gui.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unused modules to reduce size
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
        'wx',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# Filter out duplicate or problematic data files
seen = set()
new_datas = []
for dest, source, type_tag in a.datas:
    if dest not in seen:
        seen.add(dest)
        new_datas.append((dest, source, type_tag))
a.datas = new_datas

# Create the PYZ archive
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# Create the executable
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SyntyConverter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Windowed mode - no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Set to 'icon.ico' if an icon file is added later
)
