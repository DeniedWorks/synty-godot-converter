#!/usr/bin/env python3
"""Build script to create standalone SyntyConverter.exe using PyInstaller."""

import subprocess
import sys
from pathlib import Path


def build():
    """Build the standalone executable."""
    # Get the directory containing this script
    script_dir = Path(__file__).parent.resolve()

    # Path to the main GUI module
    gui_module = script_dir / "synty_converter_v2" / "gui.py"

    if not gui_module.exists():
        print(f"Error: GUI module not found at {gui_module}")
        sys.exit(1)

    # PyInstaller arguments
    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",           # Create a single executable
        "--windowed",          # Don't show console window
        "--name", "SyntyConverter",
        "--clean",             # Clean build cache
        # Add hidden imports for customtkinter
        "--hidden-import", "customtkinter",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL._tkinter_finder",
        # Collect all data files for customtkinter (themes, etc.)
        "--collect-data", "customtkinter",
        # Working directory
        "--workpath", str(script_dir / "build"),
        "--distpath", str(script_dir / "dist"),
        "--specpath", str(script_dir),
        # The entry point
        str(gui_module),
    ]

    print("Building SyntyConverter.exe...")
    print(f"Command: {' '.join(args[3:])}")  # Skip python -m PyInstaller
    print()

    result = subprocess.run(args, cwd=script_dir)

    if result.returncode == 0:
        exe_path = script_dir / "dist" / "SyntyConverter.exe"
        print()
        print("=" * 50)
        print("Build successful!")
        print(f"Executable: {exe_path}")
        print("=" * 50)
    else:
        print()
        print("Build failed!")
        sys.exit(result.returncode)


if __name__ == "__main__":
    build()
