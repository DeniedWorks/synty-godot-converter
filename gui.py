#!/usr/bin/env python3
"""
Synty Shader Converter - GUI Application

A modern CustomTkinter-based GUI for converting Unity Synty assets to Godot 4.6 format.
Provides a user-friendly interface for the command-line converter with:
- Pack browser to discover available Synty packs
- Drag & drop support for .unitypackage files
- Real-time conversion log output
- All CLI parameters exposed as GUI widgets

Usage:
    python gui.py

Requirements:
    pip install -r requirements-gui.txt
"""

from __future__ import annotations

import json
import logging
import queue
import re
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable

# Third-party imports
try:
    import customtkinter as ctk
except ImportError:
    print("ERROR: customtkinter not installed. Run: pip install customtkinter")
    sys.exit(1)

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    print("WARNING: tkinterdnd2 not installed. Drag & drop will be disabled.")
    print("Install with: pip install tkinterdnd2")
    TkinterDnD = None
    DND_FILES = None

# Local imports - ensure we can find the converter module
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

from converter import ConversionConfig, ConversionStats, run_conversion


# --- Constants ---

APP_TITLE = "Synty Shader Converter"
APP_VERSION = "1.0.0"
DEFAULT_WINDOW_SIZE = "1200x800"
MIN_WINDOW_SIZE = (900, 600)

# Default paths
DEFAULT_SYNTY_PATH = r"C:\SyntyComplete"
DEFAULT_GODOT_PATH = r"C:\Godot\Godot_v4.6-stable_mono_win64\Godot_v4.6-stable_mono_win64.exe"
DEFAULT_OUTPUT_PATH = r"C:\Godot\Projects\converted-assets"

# Logging queue check interval (ms)
LOG_QUEUE_INTERVAL = 50


# --- Custom Logging Handler ---

class QueueHandler(logging.Handler):
    """Logging handler that puts log records into a queue for GUI consumption."""

    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.log_queue.put(msg)
        except Exception:
            self.handleError(record)


# --- Pack Discovery ---

@dataclass
class SyntyPack:
    """Represents a discovered Synty asset pack."""
    name: str
    path: Path
    unity_package: Path | None
    source_files: Path | None
    has_textures: bool
    has_fbx: bool
    has_material_list: bool


def discover_synty_packs(synty_root: Path) -> list[SyntyPack]:
    """Scan a directory for Synty asset packs.

    Looks for directories containing:
    - A .unitypackage file
    - A SourceFiles/ subdirectory with Textures/

    Args:
        synty_root: Root directory to scan (e.g., C:\\SyntyComplete)

    Returns:
        List of discovered SyntyPack objects, sorted by name.
    """
    packs: list[SyntyPack] = []

    if not synty_root.exists():
        return packs

    for item in synty_root.iterdir():
        if not item.is_dir():
            continue

        # Look for .unitypackage files
        unity_packages = list(item.glob("*.unitypackage"))
        unity_package = unity_packages[0] if unity_packages else None

        # Look for SourceFiles directory
        source_files = item / "SourceFiles"
        if not source_files.exists():
            # Some packs might have SourceFiles directly in root
            continue

        # Check for required subdirectories
        textures_dir = source_files / "Textures"
        fbx_dir = source_files / "FBX"
        material_lists = list(source_files.glob("MaterialList*.txt"))

        pack = SyntyPack(
            name=item.name,
            path=item,
            unity_package=unity_package,
            source_files=source_files if source_files.exists() else None,
            has_textures=textures_dir.exists(),
            has_fbx=fbx_dir.exists(),
            has_material_list=len(material_lists) > 0,
        )

        # Only include packs with minimum requirements
        if pack.unity_package and pack.source_files and pack.has_textures:
            packs.append(pack)

    return sorted(packs, key=lambda p: p.name.lower())


# --- GUI Application ---

class SyntyConverterApp:
    """Main GUI application class."""

    def __init__(self):
        # Use TkinterDnD if available for drag & drop support
        if TkinterDnD:
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()

        # Apply CustomTkinter styling to the root window
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root.title(f"{APP_TITLE} v{APP_VERSION}")
        self.root.geometry(DEFAULT_WINDOW_SIZE)
        self.root.minsize(*MIN_WINDOW_SIZE)

        # State variables
        self.discovered_packs: list[SyntyPack] = []
        self.selected_packs: dict[str, tk.BooleanVar] = {}
        self.conversion_thread: threading.Thread | None = None
        self.conversion_cancelled = threading.Event()
        self.log_queue: queue.Queue = queue.Queue()

        # Track conversion stats for display
        self.current_stats: ConversionStats | None = None

        # Build the GUI
        self._create_widgets()
        self._setup_logging()

        # Start log queue processing
        self._process_log_queue()

    def _create_widgets(self):
        """Create all GUI widgets."""
        # Main container using grid layout
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        # Left panel - Pack Browser (fixed width)
        self._create_pack_browser()

        # Center panel - Conversion Setup (expandable)
        self._create_conversion_setup()

        # Right panel - Log Output (fixed width)
        self._create_log_panel()

        # Bottom bar - Progress and controls
        self._create_bottom_bar()

    def _create_pack_browser(self):
        """Create the left panel with pack browser."""
        left_frame = ctk.CTkFrame(self.root, width=280)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        left_frame.grid_propagate(False)

        # Title
        title_label = ctk.CTkLabel(
            left_frame,
            text="Pack Browser",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(pady=(10, 5), padx=10)

        # Scan directory entry
        scan_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        scan_frame.pack(fill="x", padx=10, pady=5)

        self.scan_path_var = ctk.StringVar(value=DEFAULT_SYNTY_PATH)
        scan_entry = ctk.CTkEntry(
            scan_frame,
            textvariable=self.scan_path_var,
            placeholder_text="Path to Synty packs..."
        )
        scan_entry.pack(side="left", fill="x", expand=True)

        browse_btn = ctk.CTkButton(
            scan_frame,
            text="...",
            width=30,
            command=self._browse_scan_directory
        )
        browse_btn.pack(side="right", padx=(5, 0))

        # Scan button
        scan_btn = ctk.CTkButton(
            left_frame,
            text="Scan for Packs",
            command=self._scan_for_packs
        )
        scan_btn.pack(fill="x", padx=10, pady=5)

        # Pack list with checkboxes
        self.pack_list_frame = ctk.CTkScrollableFrame(left_frame)
        self.pack_list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Pack info label
        self.pack_info_label = ctk.CTkLabel(
            left_frame,
            text="No packs scanned",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.pack_info_label.pack(pady=(0, 5), padx=10)

        # Select all / none buttons
        select_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        select_frame.pack(fill="x", padx=10, pady=(0, 10))

        select_all_btn = ctk.CTkButton(
            select_frame,
            text="Select All",
            width=80,
            height=25,
            command=self._select_all_packs
        )
        select_all_btn.pack(side="left")

        select_none_btn = ctk.CTkButton(
            select_frame,
            text="Select None",
            width=80,
            height=25,
            command=self._select_no_packs
        )
        select_none_btn.pack(side="right")

    def _create_conversion_setup(self):
        """Create the center panel with conversion setup options."""
        center_frame = ctk.CTkFrame(self.root)
        center_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=10)

        # Title
        title_label = ctk.CTkLabel(
            center_frame,
            text="Conversion Setup",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(pady=(10, 5))

        # Tabview for organized settings
        self.tabview = ctk.CTkTabview(center_frame)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=5)

        # Create tabs
        self._create_required_tab()
        self._create_options_tab()
        self._create_advanced_tab()

    def _create_required_tab(self):
        """Create the Required tab with essential paths."""
        tab = self.tabview.add("Required")
        tab.grid_columnconfigure(1, weight=1)

        row = 0

        # Drop zone for .unitypackage
        drop_frame = ctk.CTkFrame(tab, height=100, border_width=2, border_color="gray40")
        drop_frame.grid(row=row, column=0, columnspan=3, sticky="ew", padx=10, pady=10)
        drop_frame.grid_propagate(False)

        self.drop_label = ctk.CTkLabel(
            drop_frame,
            text="Drag & drop .unitypackage file here\nor use Browse below",
            font=ctk.CTkFont(size=13),
            text_color="gray60"
        )
        self.drop_label.place(relx=0.5, rely=0.5, anchor="center")

        # Enable drag & drop if available
        if TkinterDnD and DND_FILES:
            drop_frame.drop_target_register(DND_FILES)
            drop_frame.dnd_bind("<<Drop>>", self._on_drop)
            drop_frame.dnd_bind("<<DragEnter>>", self._on_drag_enter)
            drop_frame.dnd_bind("<<DragLeave>>", self._on_drag_leave)
        else:
            self.drop_label.configure(
                text="Drag & drop not available\nUse Browse button below"
            )

        row += 1

        # Unity Package path
        pkg_label = ctk.CTkLabel(tab, text="Unity Package:")
        pkg_label.grid(row=row, column=0, sticky="w", padx=10, pady=5)

        self.unity_package_var = ctk.StringVar()
        pkg_entry = ctk.CTkEntry(tab, textvariable=self.unity_package_var)
        pkg_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=5)

        pkg_browse = ctk.CTkButton(
            tab, text="Browse", width=70,
            command=lambda: self._browse_file(
                self.unity_package_var,
                "Select Unity Package",
                [("Unity Package", "*.unitypackage"), ("All Files", "*.*")]
            )
        )
        pkg_browse.grid(row=row, column=2, padx=(0, 10), pady=5)

        row += 1

        # Source Files path
        src_label = ctk.CTkLabel(tab, text="Source Files:")
        src_label.grid(row=row, column=0, sticky="w", padx=10, pady=5)

        self.source_files_var = ctk.StringVar()
        src_entry = ctk.CTkEntry(tab, textvariable=self.source_files_var)
        src_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=5)

        src_browse = ctk.CTkButton(
            tab, text="Browse", width=70,
            command=lambda: self._browse_directory(
                self.source_files_var,
                "Select SourceFiles Directory"
            )
        )
        src_browse.grid(row=row, column=2, padx=(0, 10), pady=5)

        row += 1

        # Output directory
        out_label = ctk.CTkLabel(tab, text="Output Directory:")
        out_label.grid(row=row, column=0, sticky="w", padx=10, pady=5)

        self.output_dir_var = ctk.StringVar(value=DEFAULT_OUTPUT_PATH)
        out_entry = ctk.CTkEntry(tab, textvariable=self.output_dir_var)
        out_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=5)

        out_browse = ctk.CTkButton(
            tab, text="Browse", width=70,
            command=lambda: self._browse_directory(
                self.output_dir_var,
                "Select Output Directory"
            )
        )
        out_browse.grid(row=row, column=2, padx=(0, 10), pady=5)

        row += 1

        # Godot executable
        godot_label = ctk.CTkLabel(tab, text="Godot Executable:")
        godot_label.grid(row=row, column=0, sticky="w", padx=10, pady=5)

        self.godot_exe_var = ctk.StringVar(value=DEFAULT_GODOT_PATH)
        godot_entry = ctk.CTkEntry(tab, textvariable=self.godot_exe_var)
        godot_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=5)

        godot_browse = ctk.CTkButton(
            tab, text="Browse", width=70,
            command=lambda: self._browse_file(
                self.godot_exe_var,
                "Select Godot Executable",
                [("Executable", "*.exe"), ("All Files", "*.*")]
            )
        )
        godot_browse.grid(row=row, column=2, padx=(0, 10), pady=5)

        row += 1

        # Auto-fill from pack selection button
        autofill_btn = ctk.CTkButton(
            tab,
            text="Auto-fill from Selected Pack",
            command=self._autofill_from_selection
        )
        autofill_btn.grid(row=row, column=0, columnspan=3, pady=20)

    def _create_options_tab(self):
        """Create the Options tab with common settings."""
        tab = self.tabview.add("Options")

        # Checkbox options
        options_frame = ctk.CTkFrame(tab, fg_color="transparent")
        options_frame.pack(fill="x", padx=10, pady=10)

        # Verbose logging
        self.verbose_var = ctk.BooleanVar(value=False)
        verbose_cb = ctk.CTkCheckBox(
            options_frame,
            text="Verbose Logging",
            variable=self.verbose_var
        )
        verbose_cb.grid(row=0, column=0, sticky="w", pady=5)

        # Dry run
        self.dry_run_var = ctk.BooleanVar(value=False)
        dry_run_cb = ctk.CTkCheckBox(
            options_frame,
            text="Dry Run (preview only)",
            variable=self.dry_run_var
        )
        dry_run_cb.grid(row=1, column=0, sticky="w", pady=5)

        # Skip FBX copy
        self.skip_fbx_var = ctk.BooleanVar(value=False)
        skip_fbx_cb = ctk.CTkCheckBox(
            options_frame,
            text="Skip FBX Copy",
            variable=self.skip_fbx_var
        )
        skip_fbx_cb.grid(row=2, column=0, sticky="w", pady=5)

        # Skip Godot CLI
        self.skip_godot_cli_var = ctk.BooleanVar(value=False)
        skip_cli_cb = ctk.CTkCheckBox(
            options_frame,
            text="Skip Godot CLI",
            variable=self.skip_godot_cli_var
        )
        skip_cli_cb.grid(row=3, column=0, sticky="w", pady=5)

        # Skip Godot import
        self.skip_godot_import_var = ctk.BooleanVar(value=False)
        skip_import_cb = ctk.CTkCheckBox(
            options_frame,
            text="Skip Godot Import (run converter script only)",
            variable=self.skip_godot_import_var
        )
        skip_import_cb.grid(row=4, column=0, sticky="w", pady=5)

        # Keep meshes together
        self.keep_meshes_var = ctk.BooleanVar(value=False)
        keep_meshes_cb = ctk.CTkCheckBox(
            options_frame,
            text="Keep Meshes Together (single scene per FBX)",
            variable=self.keep_meshes_var
        )
        keep_meshes_cb.grid(row=0, column=1, sticky="w", padx=20, pady=5)

        # Mesh format selection
        format_label = ctk.CTkLabel(options_frame, text="Mesh Format:")
        format_label.grid(row=1, column=1, sticky="w", padx=20, pady=5)

        self.mesh_format_var = ctk.StringVar(value="tscn")
        format_menu = ctk.CTkOptionMenu(
            options_frame,
            variable=self.mesh_format_var,
            values=["tscn", "res"],
            width=100
        )
        format_menu.grid(row=1, column=2, sticky="w", pady=5)

        # Filter pattern
        filter_frame = ctk.CTkFrame(tab, fg_color="transparent")
        filter_frame.pack(fill="x", padx=10, pady=10)

        filter_label = ctk.CTkLabel(filter_frame, text="Filter Pattern:")
        filter_label.pack(side="left")

        self.filter_var = ctk.StringVar()
        filter_entry = ctk.CTkEntry(
            filter_frame,
            textvariable=self.filter_var,
            placeholder_text="e.g., Tree, Chr, Veh (case-insensitive)",
            width=250
        )
        filter_entry.pack(side="left", padx=10)

        filter_help = ctk.CTkLabel(
            filter_frame,
            text="Only process FBX files containing this pattern",
            text_color="gray60",
            font=ctk.CTkFont(size=11)
        )
        filter_help.pack(side="left")

    def _create_advanced_tab(self):
        """Create the Advanced tab with timeout and other settings."""
        tab = self.tabview.add("Advanced")

        # Godot timeout
        timeout_frame = ctk.CTkFrame(tab, fg_color="transparent")
        timeout_frame.pack(fill="x", padx=10, pady=10)

        timeout_label = ctk.CTkLabel(timeout_frame, text="Godot Timeout (seconds):")
        timeout_label.pack(side="left")

        self.timeout_var = ctk.IntVar(value=600)
        timeout_slider = ctk.CTkSlider(
            timeout_frame,
            from_=60,
            to=1800,
            number_of_steps=58,
            variable=self.timeout_var,
            width=200,
            command=self._update_timeout_label
        )
        timeout_slider.pack(side="left", padx=10)

        self.timeout_value_label = ctk.CTkLabel(
            timeout_frame,
            text="600s (10 min)",
            width=100
        )
        self.timeout_value_label.pack(side="left")

        # Help text
        help_frame = ctk.CTkFrame(tab, fg_color="transparent")
        help_frame.pack(fill="x", padx=10, pady=20)

        help_text = """Advanced Options Help:

- Godot Timeout: Maximum time for Godot CLI operations.
  Increase for large packs with many FBX files.

- Filter Pattern: Only convert FBX files matching the pattern.
  Useful for testing or converting specific asset types.

- Skip Options:
  - Skip FBX Copy: Use if models/ already populated from a previous run
  - Skip Godot CLI: Generate materials only, no mesh .tscn files
  - Skip Godot Import: Skip Godot's import phase (must open project manually first)

- Keep Meshes Together: By default, each mesh is saved as a separate scene.
  Enable this to keep all meshes from one FBX in a single scene file.

- Mesh Format:
  - tscn: Text format, human-readable, larger files
  - res: Binary format, smaller files, faster to load
"""
        help_label = ctk.CTkLabel(
            help_frame,
            text=help_text,
            justify="left",
            font=ctk.CTkFont(size=11),
            text_color="gray70"
        )
        help_label.pack(anchor="w")

    def _create_log_panel(self):
        """Create the right panel with log output."""
        right_frame = ctk.CTkFrame(self.root, width=350)
        right_frame.grid(row=0, column=2, sticky="nsew", padx=(5, 10), pady=10)
        right_frame.grid_propagate(False)

        # Title
        title_label = ctk.CTkLabel(
            right_frame,
            text="Conversion Log",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(pady=(10, 5))

        # Log text area
        self.log_text = ctk.CTkTextbox(right_frame, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=5)

        # Configure log text tags for coloring
        self.log_text._textbox.tag_config("INFO", foreground="#90EE90")
        self.log_text._textbox.tag_config("WARNING", foreground="#FFD700")
        self.log_text._textbox.tag_config("ERROR", foreground="#FF6B6B")
        self.log_text._textbox.tag_config("DEBUG", foreground="#87CEEB")

        # Log control buttons
        btn_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=5)

        clear_btn = ctk.CTkButton(
            btn_frame,
            text="Clear Log",
            width=80,
            command=self._clear_log
        )
        clear_btn.pack(side="left")

        copy_btn = ctk.CTkButton(
            btn_frame,
            text="Copy Log",
            width=80,
            command=self._copy_log
        )
        copy_btn.pack(side="right")

        # Stats display
        stats_frame = ctk.CTkFrame(right_frame)
        stats_frame.pack(fill="x", padx=10, pady=(5, 10))

        self.stats_labels = {}
        stats = [
            ("Materials:", "materials"),
            ("Textures:", "textures"),
            ("Meshes:", "meshes"),
        ]

        for i, (label_text, key) in enumerate(stats):
            label = ctk.CTkLabel(stats_frame, text=label_text, font=ctk.CTkFont(size=11))
            label.grid(row=i, column=0, sticky="w", padx=5, pady=2)

            value_label = ctk.CTkLabel(
                stats_frame,
                text="-",
                font=ctk.CTkFont(size=11, weight="bold")
            )
            value_label.grid(row=i, column=1, sticky="w", padx=5, pady=2)
            self.stats_labels[key] = value_label

    def _create_bottom_bar(self):
        """Create the bottom bar with progress and control buttons."""
        bottom_frame = ctk.CTkFrame(self.root)
        bottom_frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 10))

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(bottom_frame)
        self.progress_bar.pack(fill="x", padx=10, pady=10)
        self.progress_bar.set(0)

        # Progress label
        self.progress_label = ctk.CTkLabel(
            bottom_frame,
            text="Ready",
            font=ctk.CTkFont(size=11)
        )
        self.progress_label.pack()

        # Control buttons
        btn_frame = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        btn_frame.pack(pady=10)

        self.convert_btn = ctk.CTkButton(
            btn_frame,
            text="Start Conversion",
            font=ctk.CTkFont(size=14, weight="bold"),
            width=150,
            height=40,
            command=self._start_conversion
        )
        self.convert_btn.pack(side="left", padx=10)

        self.cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=100,
            height=40,
            fg_color="gray40",
            hover_color="gray30",
            command=self._cancel_conversion,
            state="disabled"
        )
        self.cancel_btn.pack(side="left", padx=10)

    # --- Event Handlers ---

    def _browse_scan_directory(self):
        """Open directory browser for scan path."""
        path = filedialog.askdirectory(
            title="Select Synty Packs Directory",
            initialdir=self.scan_path_var.get() or DEFAULT_SYNTY_PATH
        )
        if path:
            self.scan_path_var.set(path)

    def _browse_file(self, var: ctk.StringVar, title: str, filetypes: list):
        """Open file browser dialog."""
        initial_dir = Path(var.get()).parent if var.get() else None
        path = filedialog.askopenfilename(
            title=title,
            initialdir=initial_dir,
            filetypes=filetypes
        )
        if path:
            var.set(path)

    def _browse_directory(self, var: ctk.StringVar, title: str):
        """Open directory browser dialog."""
        initial_dir = var.get() if var.get() else None
        path = filedialog.askdirectory(
            title=title,
            initialdir=initial_dir
        )
        if path:
            var.set(path)

    def _on_drop(self, event):
        """Handle drag & drop of .unitypackage files."""
        # Parse the dropped file path
        path = event.data
        # Handle paths with curly braces (TkDND format for paths with spaces)
        if path.startswith("{") and path.endswith("}"):
            path = path[1:-1]

        # Check if it's a .unitypackage file
        if path.lower().endswith(".unitypackage"):
            self.unity_package_var.set(path)
            self._log_message(f"Dropped: {Path(path).name}")

            # Try to auto-detect source files
            package_dir = Path(path).parent
            source_files = package_dir / "SourceFiles"
            if source_files.exists():
                self.source_files_var.set(str(source_files))
                self._log_message(f"Auto-detected SourceFiles: {source_files}")
        else:
            self._log_message("Please drop a .unitypackage file", level="WARNING")

        # Reset drop zone appearance
        self.drop_label.configure(
            text="Drag & drop .unitypackage file here\nor use Browse below"
        )

    def _on_drag_enter(self, event):
        """Handle drag enter event."""
        self.drop_label.configure(text="Drop .unitypackage here!")

    def _on_drag_leave(self, event):
        """Handle drag leave event."""
        self.drop_label.configure(
            text="Drag & drop .unitypackage file here\nor use Browse below"
        )

    def _scan_for_packs(self):
        """Scan the specified directory for Synty packs."""
        scan_path = Path(self.scan_path_var.get())

        if not scan_path.exists():
            messagebox.showerror("Error", f"Directory not found:\n{scan_path}")
            return

        # Clear existing pack list
        for widget in self.pack_list_frame.winfo_children():
            widget.destroy()
        self.selected_packs.clear()

        # Discover packs
        self.discovered_packs = discover_synty_packs(scan_path)

        if not self.discovered_packs:
            self.pack_info_label.configure(text="No packs found")
            return

        # Create checkboxes for each pack
        for pack in self.discovered_packs:
            var = ctk.BooleanVar(value=False)
            self.selected_packs[pack.name] = var

            # Create a frame for pack info
            pack_frame = ctk.CTkFrame(self.pack_list_frame, fg_color="transparent")
            pack_frame.pack(fill="x", pady=2)

            cb = ctk.CTkCheckBox(
                pack_frame,
                text=pack.name,
                variable=var,
                font=ctk.CTkFont(size=12)
            )
            cb.pack(side="left", anchor="w")

            # Status indicators
            status = ""
            if pack.has_material_list:
                status += "M"
            if pack.has_fbx:
                status += "F"

            if status:
                status_label = ctk.CTkLabel(
                    pack_frame,
                    text=f"[{status}]",
                    font=ctk.CTkFont(size=10),
                    text_color="gray60"
                )
                status_label.pack(side="right", padx=5)

        self.pack_info_label.configure(
            text=f"Found {len(self.discovered_packs)} packs (M=MaterialList, F=FBX)"
        )

    def _select_all_packs(self):
        """Select all discovered packs."""
        for var in self.selected_packs.values():
            var.set(True)

    def _select_no_packs(self):
        """Deselect all packs."""
        for var in self.selected_packs.values():
            var.set(False)

    def _autofill_from_selection(self):
        """Auto-fill paths from the first selected pack."""
        selected = [
            pack for pack in self.discovered_packs
            if self.selected_packs.get(pack.name, ctk.BooleanVar()).get()
        ]

        if not selected:
            messagebox.showinfo(
                "No Selection",
                "Please select a pack from the Pack Browser first."
            )
            return

        pack = selected[0]

        if pack.unity_package:
            self.unity_package_var.set(str(pack.unity_package))

        if pack.source_files:
            self.source_files_var.set(str(pack.source_files))

        self._log_message(f"Auto-filled paths from: {pack.name}")

    def _update_timeout_label(self, value):
        """Update the timeout value label."""
        seconds = int(float(value))
        if seconds >= 60:
            minutes = seconds // 60
            self.timeout_value_label.configure(text=f"{seconds}s ({minutes} min)")
        else:
            self.timeout_value_label.configure(text=f"{seconds}s")

    def _clear_log(self):
        """Clear the log text area."""
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _copy_log(self):
        """Copy log contents to clipboard."""
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log_text.get("1.0", "end"))
        self._log_message("Log copied to clipboard")

    def _log_message(self, message: str, level: str = "INFO"):
        """Add a message to the log display."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}\n"

        self.log_text.configure(state="normal")
        self.log_text.insert("end", formatted, level)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _setup_logging(self):
        """Set up logging to capture converter output."""
        # Create queue handler for the converter's logger
        self.queue_handler = QueueHandler(self.log_queue)
        self.queue_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

        # Get the converter's logger and add our handler
        converter_logger = logging.getLogger("converter")
        converter_logger.addHandler(self.queue_handler)
        converter_logger.setLevel(logging.DEBUG)

        # Also capture the root logger for any other messages
        root_logger = logging.getLogger()
        root_logger.addHandler(self.queue_handler)

    def _process_log_queue(self):
        """Process messages from the log queue and display them."""
        while True:
            try:
                message = self.log_queue.get_nowait()

                # Determine log level from message prefix
                level = "INFO"
                if message.startswith("WARNING:"):
                    level = "WARNING"
                elif message.startswith("ERROR:"):
                    level = "ERROR"
                elif message.startswith("DEBUG:"):
                    level = "DEBUG"

                # Remove the prefix for cleaner display
                clean_message = re.sub(r"^(INFO|WARNING|ERROR|DEBUG):\s*", "", message)

                self._log_message(clean_message, level)

            except queue.Empty:
                break

        # Schedule next check
        self.root.after(LOG_QUEUE_INTERVAL, self._process_log_queue)

    def _validate_inputs(self) -> bool:
        """Validate all input fields before conversion."""
        errors = []

        unity_package = Path(self.unity_package_var.get())
        if not unity_package.exists():
            errors.append(f"Unity package not found: {unity_package}")

        source_files = Path(self.source_files_var.get())
        if not source_files.exists():
            errors.append(f"Source files directory not found: {source_files}")
        elif not (source_files / "Textures").exists():
            errors.append(f"Textures directory not found in: {source_files}")

        godot_exe = Path(self.godot_exe_var.get())
        if not godot_exe.exists():
            errors.append(f"Godot executable not found: {godot_exe}")

        if not self.output_dir_var.get():
            errors.append("Output directory not specified")

        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors))
            return False

        return True

    def _start_conversion(self):
        """Start the conversion process in a background thread."""
        if not self._validate_inputs():
            return

        # Build configuration
        config = ConversionConfig(
            unity_package=Path(self.unity_package_var.get()),
            source_files=Path(self.source_files_var.get()),
            output_dir=Path(self.output_dir_var.get()),
            godot_exe=Path(self.godot_exe_var.get()),
            dry_run=self.dry_run_var.get(),
            verbose=self.verbose_var.get(),
            skip_fbx_copy=self.skip_fbx_var.get(),
            skip_godot_cli=self.skip_godot_cli_var.get(),
            skip_godot_import=self.skip_godot_import_var.get(),
            godot_timeout=self.timeout_var.get(),
            keep_meshes_together=self.keep_meshes_var.get(),
            mesh_format=self.mesh_format_var.get(),
            filter_pattern=self.filter_var.get() if self.filter_var.get() else None,
        )

        # Update UI state
        self.convert_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress_bar.set(0)
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        self.progress_label.configure(text="Converting...")

        # Clear previous stats
        for label in self.stats_labels.values():
            label.configure(text="-")

        # Reset cancellation flag
        self.conversion_cancelled.clear()

        # Start conversion thread
        self.conversion_thread = threading.Thread(
            target=self._run_conversion_thread,
            args=(config,),
            daemon=True
        )
        self.conversion_thread.start()

        self._log_message("=" * 50)
        self._log_message(f"Starting conversion: {config.unity_package.name}")
        self._log_message("=" * 50)

    def _run_conversion_thread(self, config: ConversionConfig):
        """Run the conversion in a background thread."""
        try:
            # Set up logging level based on verbose flag
            log_level = logging.DEBUG if config.verbose else logging.INFO
            logging.getLogger().setLevel(log_level)
            logging.getLogger("converter").setLevel(log_level)

            # Run conversion
            stats = run_conversion(config)

            # Store stats for display
            self.current_stats = stats

            # Schedule UI update on main thread
            self.root.after(0, self._conversion_complete, stats, None)

        except Exception as e:
            self.root.after(0, self._conversion_complete, None, str(e))

    def _conversion_complete(self, stats: ConversionStats | None, error: str | None):
        """Handle conversion completion on the main thread."""
        # Reset UI state
        self.convert_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(1.0 if not error else 0)

        if error:
            self.progress_label.configure(text="Conversion failed!")
            self._log_message(f"ERROR: {error}", level="ERROR")
            messagebox.showerror("Conversion Failed", error)
            return

        if stats:
            # Update stats display
            self.stats_labels["materials"].configure(
                text=f"{stats.materials_generated} generated, {stats.materials_missing} missing"
            )
            self.stats_labels["textures"].configure(
                text=f"{stats.textures_copied} copied, {stats.textures_missing} missing"
            )
            self.stats_labels["meshes"].configure(
                text=f"{stats.meshes_converted} converted"
            )

            # Log summary
            self._log_message("=" * 50)
            self._log_message("Conversion Complete!")
            self._log_message(f"  Materials: {stats.materials_generated} generated")
            self._log_message(f"  Textures: {stats.textures_copied} copied")
            self._log_message(f"  Meshes: {stats.meshes_converted} converted")

            if stats.errors:
                self._log_message(f"  Errors: {len(stats.errors)}", level="ERROR")
                for err in stats.errors[:3]:
                    self._log_message(f"    - {err}", level="ERROR")

            if stats.warnings:
                self._log_message(f"  Warnings: {len(stats.warnings)}", level="WARNING")

            self._log_message("=" * 50)

            if stats.errors:
                self.progress_label.configure(text="Completed with errors")
            elif stats.warnings:
                self.progress_label.configure(text="Completed with warnings")
            else:
                self.progress_label.configure(text="Conversion successful!")

    def _cancel_conversion(self):
        """Request cancellation of the running conversion."""
        self.conversion_cancelled.set()
        self.progress_label.configure(text="Cancelling...")
        self._log_message("Cancellation requested...", level="WARNING")
        # Note: The converter doesn't currently support cancellation,
        # but this sets up the infrastructure for future implementation

    def run(self):
        """Start the application main loop."""
        self.root.mainloop()


# --- Main Entry Point ---

def main():
    """Main entry point for the GUI application."""
    app = SyntyConverterApp()
    app.run()


if __name__ == "__main__":
    main()
