#!/usr/bin/env python3
"""
Synty Shader Converter - GUI Application

A modern CustomTkinter-based GUI for converting Unity Synty assets to Godot 4.6 format.
Provides a user-friendly interface for the command-line converter with:
- Pack browser to discover available Synty packs
- Real-time conversion log output
- All CLI parameters exposed as GUI widgets

Usage:
    python gui.py

Requirements:
    pip install customtkinter
"""

from __future__ import annotations

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

# Third-party imports
try:
    import customtkinter as ctk
except ImportError:
    print("ERROR: customtkinter not installed. Run: pip install customtkinter")
    sys.exit(1)

# Set appearance mode and color theme BEFORE creating any widgets
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# Local imports - ensure we can find the converter module
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

from converter import ConversionConfig, ConversionStats, run_conversion


# --- Constants ---

APP_TITLE = "SYNTY CONVERTER"
APP_VERSION = "1.0.0"
DEFAULT_WINDOW_SIZE = "1100x850"
MIN_WINDOW_SIZE = (900, 700)

# Default paths
DEFAULT_SYNTY_PATH = r"C:\SyntyComplete"
DEFAULT_GODOT_PATH = r"C:\Godot\Godot_v4.6-stable_mono_win64\Godot_v4.6-stable_mono_win64.exe"
DEFAULT_OUTPUT_PATH = r"C:\Godot\Projects\converted-assets"

# Logging queue check interval (ms)
LOG_QUEUE_INTERVAL = 50

# Help text for the Info popup
HELP_TEXT = """=== SYNTY CONVERTER HELP ===

PATHS:
- Unity Package: The .unitypackage file from Synty
- Source Files: The SourceFiles folder containing FBX and textures
- Output Directory: Where the converted Godot project will be created
- Godot Executable: Path to Godot 4.6+ executable

OUTPUT OPTIONS:
- Scene Mode:
  - "One scene per mesh": Each mesh becomes its own .tscn file (default)
  - "Combined scene per FBX": All meshes from one FBX stay together
- Output Format:
  - tscn: Human-readable scene files
  - res: Compiled binary (smaller, faster to load)

FILTERS:
- Filter by Name: Only convert files containing this text
  Example: "Tree" converts only tree-related assets

ADVANCED:
- Verbose: Show detailed logging
- Dry run: Preview what would happen without writing files
- Skip FBX copy: Don't copy FBX files (use if already copied)
- Skip Godot CLI: Generate materials only, no mesh conversion
- Skip Godot import: Skip Godot's import step (manual import needed)
- Godot Timeout: How long to wait for Godot operations
"""


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
        # Create the root window
        self.root = ctk.CTk()

        self.root.title(f"{APP_TITLE} v{APP_VERSION}")
        self.root.geometry(DEFAULT_WINDOW_SIZE)
        self.root.minsize(*MIN_WINDOW_SIZE)

        # State variables
        self.discovered_packs: list[SyntyPack] = []
        self.selected_packs: dict[str, tk.BooleanVar] = {}
        self.conversion_thread: threading.Thread | None = None
        self.conversion_cancelled = threading.Event()
        self.log_queue: queue.Queue = queue.Queue()
        self.pack_browser_visible = True

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
        self.root.grid_columnconfigure(0, weight=0)  # Pack browser (collapsible)
        self.root.grid_columnconfigure(1, weight=1)  # Main content
        self.root.grid_columnconfigure(2, weight=1)  # Log panel
        self.root.grid_rowconfigure(1, weight=1)

        # Header bar
        self._create_header()

        # Left panel - Pack Browser (collapsible)
        self._create_pack_browser()

        # Center panel - Main settings (scrollable)
        self._create_main_panel()

        # Right panel - Log Output
        self._create_log_panel()

        # Bottom bar - Progress and controls
        self._create_bottom_bar()

    def _create_header(self):
        """Create the header bar with title and help button."""
        header_frame = ctk.CTkFrame(self.root, height=50)
        header_frame.grid(row=0, column=0, columnspan=3, sticky="ew", padx=10, pady=(10, 5))
        header_frame.grid_propagate(False)

        # Title
        title_label = ctk.CTkLabel(
            header_frame,
            text=APP_TITLE,
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(side="left", padx=15, pady=10)

        # Help button
        help_btn = ctk.CTkButton(
            header_frame,
            text="?",
            width=35,
            height=35,
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self._show_help
        )
        help_btn.pack(side="right", padx=15, pady=7)

    def _create_pack_browser(self):
        """Create the left panel with pack browser."""
        self.left_frame = ctk.CTkFrame(self.root, width=250)
        self.left_frame.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=5)
        self.left_frame.grid_propagate(False)

        # Toggle button for collapse/expand
        toggle_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        toggle_frame.pack(fill="x", padx=5, pady=5)

        self.toggle_btn = ctk.CTkButton(
            toggle_frame,
            text="Pack Browser",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="transparent",
            hover_color=("gray75", "gray25"),
            anchor="w",
            command=self._toggle_pack_browser
        )
        self.toggle_btn.pack(side="left", fill="x", expand=True)

        # Collapsible content frame
        self.pack_content_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        self.pack_content_frame.pack(fill="both", expand=True, padx=5)

        # Scan directory entry
        scan_frame = ctk.CTkFrame(self.pack_content_frame, fg_color="transparent")
        scan_frame.pack(fill="x", pady=5)

        self.scan_path_var = ctk.StringVar(value=DEFAULT_SYNTY_PATH)
        scan_entry = ctk.CTkEntry(
            scan_frame,
            textvariable=self.scan_path_var,
            placeholder_text="Path to Synty packs...",
            height=28
        )
        scan_entry.pack(side="left", fill="x", expand=True)

        browse_btn = ctk.CTkButton(
            scan_frame,
            text="...",
            width=30,
            height=28,
            command=self._browse_scan_directory
        )
        browse_btn.pack(side="right", padx=(5, 0))

        # Scan button
        scan_btn = ctk.CTkButton(
            self.pack_content_frame,
            text="Scan for Packs",
            height=28,
            command=self._scan_for_packs
        )
        scan_btn.pack(fill="x", pady=5)

        # Pack list with checkboxes
        self.pack_list_frame = ctk.CTkScrollableFrame(self.pack_content_frame, height=200)
        self.pack_list_frame.pack(fill="both", expand=True, pady=5)

        # Pack info label
        self.pack_info_label = ctk.CTkLabel(
            self.pack_content_frame,
            text="No packs scanned",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        self.pack_info_label.pack(pady=(0, 5))

        # Select all / none buttons
        select_frame = ctk.CTkFrame(self.pack_content_frame, fg_color="transparent")
        select_frame.pack(fill="x", pady=(0, 5))

        select_all_btn = ctk.CTkButton(
            select_frame,
            text="All",
            width=60,
            height=25,
            command=self._select_all_packs
        )
        select_all_btn.pack(side="left")

        select_none_btn = ctk.CTkButton(
            select_frame,
            text="None",
            width=60,
            height=25,
            command=self._select_no_packs
        )
        select_none_btn.pack(side="right")

        autofill_btn = ctk.CTkButton(
            self.pack_content_frame,
            text="Auto-fill from Selected",
            height=28,
            command=self._autofill_from_selection
        )
        autofill_btn.pack(fill="x", pady=(0, 5))

    def _create_main_panel(self):
        """Create the center panel with all settings on a single scrollable screen."""
        center_frame = ctk.CTkScrollableFrame(self.root)
        center_frame.grid(row=1, column=1, sticky="nsew", padx=5, pady=5)

        # === PATHS SECTION ===
        self._create_section_header(center_frame, "PATHS")

        paths_frame = ctk.CTkFrame(center_frame, fg_color="transparent")
        paths_frame.pack(fill="x", padx=10, pady=(0, 15))
        paths_frame.grid_columnconfigure(1, weight=1)

        # Unity Package path
        row = 0
        pkg_label = ctk.CTkLabel(paths_frame, text="Unity Package:", anchor="w", width=120)
        pkg_label.grid(row=row, column=0, sticky="w", pady=5)

        self.unity_package_var = ctk.StringVar()
        pkg_entry = ctk.CTkEntry(paths_frame, textvariable=self.unity_package_var)
        pkg_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=5)

        pkg_browse = ctk.CTkButton(
            paths_frame, text="Browse", width=70,
            command=lambda: self._browse_file(
                self.unity_package_var,
                "Select Unity Package",
                [("Unity Package", "*.unitypackage"), ("All Files", "*.*")]
            )
        )
        pkg_browse.grid(row=row, column=2, pady=5)

        # Source Files path
        row += 1
        src_label = ctk.CTkLabel(paths_frame, text="Source Files:", anchor="w", width=120)
        src_label.grid(row=row, column=0, sticky="w", pady=5)

        self.source_files_var = ctk.StringVar()
        src_entry = ctk.CTkEntry(paths_frame, textvariable=self.source_files_var)
        src_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=5)

        src_browse = ctk.CTkButton(
            paths_frame, text="Browse", width=70,
            command=lambda: self._browse_directory(
                self.source_files_var,
                "Select SourceFiles Directory"
            )
        )
        src_browse.grid(row=row, column=2, pady=5)

        # Output directory
        row += 1
        out_label = ctk.CTkLabel(paths_frame, text="Output Directory:", anchor="w", width=120)
        out_label.grid(row=row, column=0, sticky="w", pady=5)

        self.output_dir_var = ctk.StringVar(value=DEFAULT_OUTPUT_PATH)
        out_entry = ctk.CTkEntry(paths_frame, textvariable=self.output_dir_var)
        out_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=5)

        out_browse = ctk.CTkButton(
            paths_frame, text="Browse", width=70,
            command=lambda: self._browse_directory(
                self.output_dir_var,
                "Select Output Directory"
            )
        )
        out_browse.grid(row=row, column=2, pady=5)

        # Godot executable
        row += 1
        godot_label = ctk.CTkLabel(paths_frame, text="Godot Executable:", anchor="w", width=120)
        godot_label.grid(row=row, column=0, sticky="w", pady=5)

        self.godot_exe_var = ctk.StringVar(value=DEFAULT_GODOT_PATH)
        godot_entry = ctk.CTkEntry(paths_frame, textvariable=self.godot_exe_var)
        godot_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=5)

        godot_browse = ctk.CTkButton(
            paths_frame, text="Browse", width=70,
            command=lambda: self._browse_file(
                self.godot_exe_var,
                "Select Godot Executable",
                [("Executable", "*.exe"), ("All Files", "*.*")]
            )
        )
        godot_browse.grid(row=row, column=2, pady=5)

        # === OUTPUT OPTIONS SECTION ===
        self._create_section_header(center_frame, "OUTPUT OPTIONS")

        output_frame = ctk.CTkFrame(center_frame, fg_color="transparent")
        output_frame.pack(fill="x", padx=10, pady=(0, 15))

        # Scene Mode (radio buttons)
        scene_label = ctk.CTkLabel(output_frame, text="Scene Mode:", anchor="w")
        scene_label.grid(row=0, column=0, sticky="w", pady=5)

        self.scene_mode_var = ctk.IntVar(value=0)  # 0 = one per mesh, 1 = combined

        radio_frame = ctk.CTkFrame(output_frame, fg_color="transparent")
        radio_frame.grid(row=0, column=1, sticky="w", padx=10, pady=5)

        radio_separate = ctk.CTkRadioButton(
            radio_frame,
            text="One scene per mesh (default)",
            variable=self.scene_mode_var,
            value=0
        )
        radio_separate.pack(anchor="w")

        radio_combined = ctk.CTkRadioButton(
            radio_frame,
            text="Combined scene per FBX file",
            variable=self.scene_mode_var,
            value=1
        )
        radio_combined.pack(anchor="w")

        # Output Format (dropdown)
        format_label = ctk.CTkLabel(output_frame, text="Output Format:", anchor="w")
        format_label.grid(row=1, column=0, sticky="w", pady=5)

        format_inner = ctk.CTkFrame(output_frame, fg_color="transparent")
        format_inner.grid(row=1, column=1, sticky="w", padx=10, pady=5)

        self.mesh_format_var = ctk.StringVar(value="tscn")
        format_menu = ctk.CTkOptionMenu(
            format_inner,
            variable=self.mesh_format_var,
            values=["tscn", "res"],
            width=100
        )
        format_menu.pack(side="left")

        format_hint = ctk.CTkLabel(
            format_inner,
            text="(tscn = text, res = binary)",
            text_color="gray",
            font=ctk.CTkFont(size=11)
        )
        format_hint.pack(side="left", padx=10)

        # === FILTERS SECTION ===
        self._create_section_header(center_frame, "FILTERS")

        filter_frame = ctk.CTkFrame(center_frame, fg_color="transparent")
        filter_frame.pack(fill="x", padx=10, pady=(0, 15))

        filter_label = ctk.CTkLabel(filter_frame, text="Filter by Name:", anchor="w")
        filter_label.pack(side="left")

        self.filter_var = ctk.StringVar()
        filter_entry = ctk.CTkEntry(
            filter_frame,
            textvariable=self.filter_var,
            placeholder_text='e.g. "Tree" or "Veh"',
            width=200
        )
        filter_entry.pack(side="left", padx=10)

        # === ADVANCED OPTIONS SECTION ===
        self._create_section_header(center_frame, "ADVANCED OPTIONS")

        advanced_frame = ctk.CTkFrame(center_frame, fg_color="transparent")
        advanced_frame.pack(fill="x", padx=10, pady=(0, 15))

        # Checkbox grid
        checkbox_frame = ctk.CTkFrame(advanced_frame, fg_color="transparent")
        checkbox_frame.pack(fill="x")

        # Verbose logging
        self.verbose_var = ctk.BooleanVar(value=False)
        verbose_cb = ctk.CTkCheckBox(
            checkbox_frame,
            text="Verbose logging",
            variable=self.verbose_var
        )
        verbose_cb.grid(row=0, column=0, sticky="w", pady=3, padx=(0, 20))

        # Dry run
        self.dry_run_var = ctk.BooleanVar(value=False)
        dry_run_cb = ctk.CTkCheckBox(
            checkbox_frame,
            text="Dry run (preview only)",
            variable=self.dry_run_var
        )
        dry_run_cb.grid(row=0, column=1, sticky="w", pady=3)

        # Skip FBX copy
        self.skip_fbx_var = ctk.BooleanVar(value=False)
        skip_fbx_cb = ctk.CTkCheckBox(
            checkbox_frame,
            text="Skip FBX copy",
            variable=self.skip_fbx_var
        )
        skip_fbx_cb.grid(row=1, column=0, sticky="w", pady=3, padx=(0, 20))

        # Skip Godot CLI
        self.skip_godot_cli_var = ctk.BooleanVar(value=False)
        skip_cli_cb = ctk.CTkCheckBox(
            checkbox_frame,
            text="Skip Godot CLI",
            variable=self.skip_godot_cli_var
        )
        skip_cli_cb.grid(row=1, column=1, sticky="w", pady=3)

        # Skip Godot import
        self.skip_godot_import_var = ctk.BooleanVar(value=False)
        skip_import_cb = ctk.CTkCheckBox(
            checkbox_frame,
            text="Skip Godot import",
            variable=self.skip_godot_import_var
        )
        skip_import_cb.grid(row=2, column=0, sticky="w", pady=3, padx=(0, 20))

        # Godot timeout slider
        timeout_frame = ctk.CTkFrame(advanced_frame, fg_color="transparent")
        timeout_frame.pack(fill="x", pady=(10, 0))

        timeout_label = ctk.CTkLabel(timeout_frame, text="Godot Timeout:")
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
            text="600s",
            width=60
        )
        self.timeout_value_label.pack(side="left")

    def _create_section_header(self, parent, title: str):
        """Create a section header with a title."""
        header_frame = ctk.CTkFrame(parent, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=(15, 5))

        # Separator line before title
        separator = ctk.CTkFrame(header_frame, height=1, fg_color="gray40")
        separator.pack(fill="x", pady=(0, 5))

        label = ctk.CTkLabel(
            header_frame,
            text=f"=== {title} ===",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="gray70"
        )
        label.pack(anchor="w")

    def _create_log_panel(self):
        """Create the right panel with log output."""
        right_frame = ctk.CTkFrame(self.root)
        right_frame.grid(row=1, column=2, sticky="nsew", padx=(5, 10), pady=5)

        # Title
        title_label = ctk.CTkLabel(
            right_frame,
            text="Live Log Output",
            font=ctk.CTkFont(size=14, weight="bold")
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
            text="Clear",
            width=70,
            height=28,
            command=self._clear_log
        )
        clear_btn.pack(side="left")

        copy_btn = ctk.CTkButton(
            btn_frame,
            text="Copy",
            width=70,
            height=28,
            command=self._copy_log
        )
        copy_btn.pack(side="right")

    def _create_bottom_bar(self):
        """Create the bottom bar with progress and control buttons."""
        bottom_frame = ctk.CTkFrame(self.root)
        bottom_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=10, pady=(5, 10))

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(bottom_frame)
        self.progress_bar.pack(fill="x", padx=10, pady=(10, 5))
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
            text="Convert",
            font=ctk.CTkFont(size=14, weight="bold"),
            width=120,
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

        info_btn = ctk.CTkButton(
            btn_frame,
            text="Info",
            width=80,
            height=40,
            fg_color="gray50",
            hover_color="gray40",
            command=self._show_help
        )
        info_btn.pack(side="left", padx=10)

    # --- Event Handlers ---

    def _show_help(self):
        """Show the help popup window."""
        help_window = ctk.CTkToplevel(self.root)
        help_window.title("Synty Converter Help")
        help_window.geometry("550x500")
        help_window.resizable(False, False)

        # Make it modal
        help_window.transient(self.root)
        help_window.grab_set()

        # Help text
        text_box = ctk.CTkTextbox(help_window, wrap="word")
        text_box.pack(fill="both", expand=True, padx=15, pady=15)
        text_box.insert("1.0", HELP_TEXT)
        text_box.configure(state="disabled")

        # Close button
        close_btn = ctk.CTkButton(
            help_window,
            text="Close",
            width=100,
            command=help_window.destroy
        )
        close_btn.pack(pady=(0, 15))

        # Center the window
        help_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - help_window.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - help_window.winfo_height()) // 2
        help_window.geometry(f"+{x}+{y}")

    def _toggle_pack_browser(self):
        """Toggle the pack browser visibility."""
        if self.pack_browser_visible:
            self.pack_content_frame.pack_forget()
            self.toggle_btn.configure(text="Pack Browser [+]")
            self.left_frame.configure(width=120)
        else:
            self.pack_content_frame.pack(fill="both", expand=True, padx=5)
            self.toggle_btn.configure(text="Pack Browser")
            self.left_frame.configure(width=250)
        self.pack_browser_visible = not self.pack_browser_visible

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
            pack_frame.pack(fill="x", pady=1)

            cb = ctk.CTkCheckBox(
                pack_frame,
                text=pack.name[:25] + "..." if len(pack.name) > 25 else pack.name,
                variable=var,
                font=ctk.CTkFont(size=11)
            )
            cb.pack(side="left", anchor="w")

        self.pack_info_label.configure(
            text=f"Found {len(self.discovered_packs)} packs"
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
        # scene_mode_var: 0 = one per mesh (keep_meshes_together=False), 1 = combined (keep_meshes_together=True)
        keep_meshes_together = self.scene_mode_var.get() == 1

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
            keep_meshes_together=keep_meshes_together,
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

        # Reset cancellation flag
        self.conversion_cancelled.clear()

        # Start conversion thread
        self.conversion_thread = threading.Thread(
            target=self._run_conversion_thread,
            args=(config,),
            daemon=True
        )
        self.conversion_thread.start()

        self._log_message("=" * 40)
        self._log_message(f"Starting conversion: {config.unity_package.name}")
        self._log_message("=" * 40)

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
            # Log summary
            self._log_message("=" * 40)
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

            self._log_message("=" * 40)

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
