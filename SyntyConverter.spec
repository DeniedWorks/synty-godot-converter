# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Synty Converter GUI.

Build command:
    pyinstaller SyntyConverter.spec

Output will be in: dist/SyntyConverter.exe
"""

import sys
from pathlib import Path

block_cipher = None

# Get the repo root directory
repo_dir = Path(SPECPATH)

a = Analysis(
    ['synty_converter_gui.py'],
    pathex=[str(repo_dir)],
    binaries=[],
    datas=[
        # Include shaders directory for bundled distribution
        (str(repo_dir / 'shaders'), 'shaders'),
        # Include Godot import script for collision generation
        (str(repo_dir / 'synty_import_script.gd'), '.'),
    ],
    hiddenimports=[
        'synty_converter',
        'synty_shaders',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

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
    console=False,  # No console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if you have one: icon='icon.ico'
)
