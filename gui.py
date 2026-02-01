#!/usr/bin/env python3
"""
Synty Shader Converter - GUI Application

A modern CustomTkinter-based GUI for converting Unity Synty assets to Godot 4.6 format.
Provides a user-friendly interface for the command-line converter.

Usage:
    python gui.py

Requirements:
    pip install customtkinter
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import sys
import threading
import tkinter as tk
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
APP_VERSION = "2.1"
DEFAULT_WINDOW_SIZE = "1080x640"

# Default paths
DEFAULT_SYNTY_PATH = ""
DEFAULT_GODOT_PATH = ""
DEFAULT_OUTPUT_PATH = ""

# Settings file location
SETTINGS_DIR = Path(os.environ.get("APPDATA", Path.home())) / "SyntyConverter"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

# Logging queue check interval (ms)
LOG_QUEUE_INTERVAL = 50

# Help text for the Info popup
HELP_TEXT = """SYNTY CONVERTER HELP

PATHS:
- Unity Package: The .unitypackage file from Synty
- Source Files: The SourceFiles folder containing FBX and textures
- Output Directory: Where the converted Godot project will be created
- Godot Executable: Path to Godot 4.6+ executable

OUTPUT OPTIONS:
- Output Format:
  - tscn: Human-readable scene files (default)
  - res: Compiled binary (smaller, faster to load)
- Mesh Mode:
  - Separate: Each mesh becomes its own scene file (default)
  - Combined: All meshes from one FBX stay together

FILTERS:
- Filter by Name: Only convert files containing this text
  Example: "Tree" converts only tree-related assets
  Also filters textures to only copy those needed by matching files.

ADVANCED:
- Verbose: Show detailed logging
- Dry run: Preview what would happen without writing files
- Skip FBX copy: Don't copy FBX files (use if already copied)
- Skip Godot CLI: Generate materials only, no mesh conversion
- Skip Godot import: Skip Godot's import step (manual import needed)
- High quality textures: Use BPTC compression (slower import, better quality)
  Default uses lossless compression for faster Godot import times.
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


# --- GUI Application ---

class SyntyConverterApp:
    """Main GUI application class."""

    def __init__(self):
        # Create the root window
        self.root = ctk.CTk()

        self.root.title(f"{APP_TITLE} v{APP_VERSION}")
        self.root.geometry(DEFAULT_WINDOW_SIZE)

        # Center window on screen
        width = 1080
        height = 640
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        # State variables
        self.conversion_thread: threading.Thread | None = None
        self.conversion_cancelled = threading.Event()
        self.log_queue: queue.Queue = queue.Queue()

        # Track if last log line was a progress message (for single-line updating)
        self._last_was_progress = False

        # Track conversion stats for display
        self.current_stats: ConversionStats | None = None

        # Build the GUI
        self._create_widgets()
        self._setup_logging()

        # Load saved settings after widgets are created
        self._load_settings()

        # Start log queue processing
        self._process_log_queue()

    def _create_widgets(self):
        """Create all GUI widgets."""
        # Main container
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        # Header bar
        self._create_header()

        # Main content area
        self._create_main_content()

        # Bottom bar - Progress and controls
        self._create_bottom_bar()

    def _create_header(self):
        """Create the header bar with title and help button."""
        header_frame = ctk.CTkFrame(self.root, height=50)
        header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
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
            text="Info",
            width=50,
            height=35,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._show_help
        )
        help_btn.pack(side="right", padx=15, pady=7)

    def _create_main_content(self):
        """Create the main content area with settings and log."""
        content_frame = ctk.CTkFrame(self.root)
        content_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_columnconfigure(1, weight=1)
        content_frame.grid_rowconfigure(1, weight=1)

        # Left side - Settings
        settings_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        settings_frame.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(10, 5), pady=10)

        self._create_path_inputs(settings_frame)
        self._create_output_options(settings_frame)
        self._create_filter_section(settings_frame)
        self._create_advanced_options(settings_frame)

        # Right side - Log panel
        self._create_log_panel(content_frame)

    def _create_path_inputs(self, parent):
        """Create the path input fields."""
        paths_frame = ctk.CTkFrame(parent, fg_color="transparent")
        paths_frame.pack(fill="x", pady=(0, 15))
        paths_frame.grid_columnconfigure(1, weight=1)

        # Unity Package path
        row = 0
        pkg_label = ctk.CTkLabel(paths_frame, text="Unity Package:", anchor="w", width=120)
        pkg_label.grid(row=row, column=0, sticky="w", pady=4)

        self.unity_package_var = ctk.StringVar()
        pkg_entry = ctk.CTkEntry(paths_frame, textvariable=self.unity_package_var)
        pkg_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=4)

        pkg_browse = ctk.CTkButton(
            paths_frame, text="...", width=35,
            command=lambda: self._browse_file(
                self.unity_package_var,
                "Select Unity Package",
                [("Unity Package", "*.unitypackage"), ("All Files", "*.*")]
            )
        )
        pkg_browse.grid(row=row, column=2, pady=4)

        # Source Files path
        row += 1
        src_label = ctk.CTkLabel(paths_frame, text="Source Files:", anchor="w", width=120)
        src_label.grid(row=row, column=0, sticky="w", pady=4)

        self.source_files_var = ctk.StringVar()
        src_entry = ctk.CTkEntry(paths_frame, textvariable=self.source_files_var)
        src_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=4)

        src_browse = ctk.CTkButton(
            paths_frame, text="...", width=35,
            command=lambda: self._browse_directory(
                self.source_files_var,
                "Select SourceFiles Directory"
            )
        )
        src_browse.grid(row=row, column=2, pady=4)

        # Output directory
        row += 1
        out_label = ctk.CTkLabel(paths_frame, text="Output Directory:", anchor="w", width=120)
        out_label.grid(row=row, column=0, sticky="w", pady=4)

        self.output_dir_var = ctk.StringVar(value=DEFAULT_OUTPUT_PATH)
        out_entry = ctk.CTkEntry(paths_frame, textvariable=self.output_dir_var)
        out_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=4)

        out_browse = ctk.CTkButton(
            paths_frame, text="...", width=35,
            command=lambda: self._browse_directory(
                self.output_dir_var,
                "Select Output Directory"
            )
        )
        out_browse.grid(row=row, column=2, pady=4)

        # Godot executable
        row += 1
        godot_label = ctk.CTkLabel(paths_frame, text="Godot Executable:", anchor="w", width=120)
        godot_label.grid(row=row, column=0, sticky="w", pady=4)

        self.godot_exe_var = ctk.StringVar(value=DEFAULT_GODOT_PATH)
        godot_entry = ctk.CTkEntry(paths_frame, textvariable=self.godot_exe_var)
        godot_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=4)

        godot_browse = ctk.CTkButton(
            paths_frame, text="...", width=35,
            command=lambda: self._browse_file(
                self.godot_exe_var,
                "Select Godot Executable",
                [("Executable", "*.exe"), ("All Files", "*.*")]
            )
        )
        godot_browse.grid(row=row, column=2, pady=4)

    def _create_output_options(self, parent):
        """Create the output format and mesh mode segmented buttons."""
        # Center container for the options
        options_frame = ctk.CTkFrame(parent, fg_color="transparent")
        options_frame.pack(pady=(20, 15), anchor="center")

        # Inner frame to hold both selectors side by side
        selectors_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        selectors_frame.pack(anchor="center")

        # Output Format selector
        format_frame = ctk.CTkFrame(selectors_frame, fg_color="transparent")
        format_frame.pack(side="left", padx=(0, 40))

        format_label = ctk.CTkLabel(
            format_frame,
            text="Output Format",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        format_label.pack(anchor="center")

        self.format_selector = ctk.CTkSegmentedButton(
            format_frame,
            values=["tscn", "res"],
            command=self._on_format_change
        )
        self.format_selector.set("tscn")  # default
        self.format_selector.pack(anchor="center", pady=(5, 0))

        # Mesh Mode selector
        mesh_frame = ctk.CTkFrame(selectors_frame, fg_color="transparent")
        mesh_frame.pack(side="left")

        mesh_label = ctk.CTkLabel(
            mesh_frame,
            text="Mesh Mode",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        mesh_label.pack(anchor="center")

        self.mesh_mode_selector = ctk.CTkSegmentedButton(
            mesh_frame,
            values=["Separate", "Combined"],
            command=self._on_mesh_mode_change
        )
        self.mesh_mode_selector.set("Separate")  # default
        self.mesh_mode_selector.pack(anchor="center", pady=(5, 0))

    def _on_format_change(self, value: str):
        """Handle output format selection change."""
        pass  # Can add logging or other behavior if needed

    def _on_mesh_mode_change(self, value: str):
        """Handle mesh mode selection change."""
        pass  # Can add logging or other behavior if needed

    def _create_filter_section(self, parent):
        """Create the filter input."""
        filter_frame = ctk.CTkFrame(parent, fg_color="transparent")
        filter_frame.pack(pady=(0, 15), anchor="center")

        # Inner frame to hold label and entry together
        filter_inner = ctk.CTkFrame(filter_frame, fg_color="transparent")
        filter_inner.pack(anchor="center")

        filter_label = ctk.CTkLabel(filter_inner, text="Filter by Name:", anchor="w")
        filter_label.pack(side="left")

        self.filter_var = ctk.StringVar()
        filter_entry = ctk.CTkEntry(
            filter_inner,
            textvariable=self.filter_var,
            placeholder_text='e.g. "Tree" or "Veh"',
            width=200
        )
        filter_entry.pack(side="left", padx=10)

    def _create_advanced_options(self, parent):
        """Create the advanced options checkboxes and timeout slider."""
        advanced_frame = ctk.CTkFrame(parent, fg_color="transparent")
        advanced_frame.pack(pady=(0, 10), anchor="center")

        # Timeout slider (placed first, right after filter)
        timeout_frame = ctk.CTkFrame(advanced_frame, fg_color="transparent")
        timeout_frame.pack(anchor="center", pady=(0, 0))

        timeout_label = ctk.CTkLabel(timeout_frame, text="Timeout:")
        timeout_label.pack(side="left")

        self.timeout_var = ctk.IntVar(value=600)
        timeout_slider = ctk.CTkSlider(
            timeout_frame,
            from_=60,
            to=1800,
            number_of_steps=58,
            variable=self.timeout_var,
            width=180,
            command=self._update_timeout_label
        )
        timeout_slider.pack(side="left", padx=10)

        self.timeout_value_label = ctk.CTkLabel(
            timeout_frame,
            text="600s",
            width=50
        )
        self.timeout_value_label.pack(side="left")

        # Spacer between timeout and checkboxes
        spacer_frame = ctk.CTkFrame(advanced_frame, fg_color="transparent", height=45)
        spacer_frame.pack(fill="x")
        spacer_frame.pack_propagate(False)

        # Checkbox grid - row 1
        checkbox_frame1 = ctk.CTkFrame(advanced_frame, fg_color="transparent")
        checkbox_frame1.pack(anchor="center", pady=2)

        self.verbose_var = ctk.BooleanVar(value=False)
        verbose_cb = ctk.CTkCheckBox(
            checkbox_frame1,
            text="Verbose",
            variable=self.verbose_var,
            width=120
        )
        verbose_cb.pack(side="left", padx=(0, 10))

        self.dry_run_var = ctk.BooleanVar(value=False)
        dry_run_cb = ctk.CTkCheckBox(
            checkbox_frame1,
            text="Dry run",
            variable=self.dry_run_var,
            width=120
        )
        dry_run_cb.pack(side="left", padx=(0, 10))

        self.skip_fbx_var = ctk.BooleanVar(value=False)
        skip_fbx_cb = ctk.CTkCheckBox(
            checkbox_frame1,
            text="Skip FBX copy",
            variable=self.skip_fbx_var,
            width=120
        )
        skip_fbx_cb.pack(side="left")

        # Checkbox grid - row 2
        checkbox_frame2 = ctk.CTkFrame(advanced_frame, fg_color="transparent")
        checkbox_frame2.pack(anchor="center", pady=2)

        self.skip_godot_cli_var = ctk.BooleanVar(value=False)
        skip_cli_cb = ctk.CTkCheckBox(
            checkbox_frame2,
            text="Skip Godot CLI",
            variable=self.skip_godot_cli_var,
            width=120
        )
        skip_cli_cb.pack(side="left", padx=(0, 10))

        self.skip_godot_import_var = ctk.BooleanVar(value=False)
        skip_import_cb = ctk.CTkCheckBox(
            checkbox_frame2,
            text="Skip Godot import",
            variable=self.skip_godot_import_var,
            width=140
        )
        skip_import_cb.pack(side="left", padx=(0, 10))

        self.high_quality_textures_var = ctk.BooleanVar(value=False)
        high_quality_cb = ctk.CTkCheckBox(
            checkbox_frame2,
            text="High quality textures",
            variable=self.high_quality_textures_var,
            width=160
        )
        high_quality_cb.pack(side="left")

    def _create_log_panel(self, parent):
        """Create the log output panel."""
        log_frame = ctk.CTkFrame(parent)
        log_frame.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(5, 10), pady=10)
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        # Log text area
        self.log_text = ctk.CTkTextbox(log_frame, wrap="word", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 5))

        # Configure log text tags for coloring
        self.log_text._textbox.tag_config("INFO", foreground="#90EE90")
        self.log_text._textbox.tag_config("WARNING", foreground="#FFD700")
        self.log_text._textbox.tag_config("ERROR", foreground="#FF6B6B")
        self.log_text._textbox.tag_config("DEBUG", foreground="#87CEEB")

        # Log control buttons
        btn_frame = ctk.CTkFrame(log_frame, fg_color="transparent")
        btn_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

        clear_btn = ctk.CTkButton(
            btn_frame,
            text="Clear",
            width=60,
            height=26,
            command=self._clear_log
        )
        clear_btn.pack(side="left")

        copy_btn = ctk.CTkButton(
            btn_frame,
            text="Copy",
            width=60,
            height=26,
            command=self._copy_log
        )
        copy_btn.pack(side="right")

    def _create_bottom_bar(self):
        """Create the bottom bar with progress and control buttons."""
        bottom_frame = ctk.CTkFrame(self.root)
        bottom_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(5, 10))

        # Progress bar and label in same row
        progress_frame = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        progress_frame.pack(fill="x", padx=10, pady=(8, 5))

        self.progress_bar = ctk.CTkProgressBar(progress_frame, width=300)
        self.progress_bar.pack(side="left")
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(
            progress_frame,
            text="Ready",
            font=ctk.CTkFont(size=11)
        )
        self.progress_label.pack(side="left", padx=15)

        # Control buttons on the right
        btn_frame = ctk.CTkFrame(progress_frame, fg_color="transparent")
        btn_frame.pack(side="right")

        self.convert_btn = ctk.CTkButton(
            btn_frame,
            text="Convert",
            font=ctk.CTkFont(size=14, weight="bold"),
            width=100,
            height=36,
            command=self._start_conversion
        )
        self.convert_btn.pack(side="left", padx=5)

    # --- Event Handlers ---

    def _show_help(self):
        """Show the help popup window."""
        help_window = ctk.CTkToplevel(self.root)
        help_window.title("Synty Converter Help")
        help_window.geometry("500x450")
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

    def _update_timeout_label(self, value):
        """Update the timeout value label."""
        seconds = int(float(value))
        self.timeout_value_label.configure(text=f"{seconds}s")

    def _clear_log(self):
        """Clear the log text area."""
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._last_was_progress = False

    def _copy_log(self):
        """Copy log contents to clipboard."""
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log_text.get("1.0", "end"))
        self._log_message("Log copied to clipboard")

    def _is_progress_message(self, message: str) -> bool:
        """Check if a message is a progress update that should replace the last line."""
        return message.startswith("Importing [") or message.startswith("Processing [")

    def _log_message(self, message: str, level: str = "INFO"):
        """Add a message to the log display.

        Progress messages (Importing [...] or Processing [...]) update in place
        instead of appending new lines.
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}\n"

        is_progress = self._is_progress_message(message)

        self.log_text.configure(state="normal")

        # If both current and previous messages are progress, replace the last line
        if is_progress and self._last_was_progress:
            # Delete the last line (from "end-1c linestart" to "end-1c lineend+1c")
            self.log_text._textbox.delete("end-2l linestart", "end-1c")
            self.log_text.insert("end", formatted, level)
        else:
            self.log_text.insert("end", formatted, level)

        self._last_was_progress = is_progress
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _setup_logging(self):
        """Set up logging to capture converter output.
        
        We configure logging to only go to our GUI queue handler,
        not to stdout. This prevents duplicate log messages.
        """
        # Create queue handler for capturing log messages
        self.queue_handler = QueueHandler(self.log_queue)
        self.queue_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

        # Configure the converter's logger
        converter_logger = logging.getLogger("converter")
        converter_logger.handlers.clear()  # Remove any existing handlers
        converter_logger.addHandler(self.queue_handler)
        converter_logger.setLevel(logging.DEBUG)
        converter_logger.propagate = False  # Don't send to root logger

        # Configure root logger to only use our queue handler
        # This captures any other log messages from dependencies
        root_logger = logging.getLogger()
        root_logger.handlers.clear()  # Remove default StreamHandler
        root_logger.addHandler(self.queue_handler)
        root_logger.setLevel(logging.DEBUG)

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

    # --- Settings Persistence ---

    def _load_settings(self):
        """Load settings from JSON file in AppData."""
        try:
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    settings = json.load(f)

                # Restore path fields
                if "unity_package" in settings:
                    self.unity_package_var.set(settings["unity_package"])
                if "source_files" in settings:
                    self.source_files_var.set(settings["source_files"])
                if "output_dir" in settings:
                    self.output_dir_var.set(settings["output_dir"])
                if "godot_exe" in settings:
                    self.godot_exe_var.set(settings["godot_exe"])

                # Restore options
                if "output_format" in settings:
                    self.format_selector.set(settings["output_format"])
                if "mesh_mode" in settings:
                    self.mesh_mode_selector.set(settings["mesh_mode"])
                if "filter" in settings:
                    self.filter_var.set(settings["filter"])
                if "timeout" in settings:
                    self.timeout_var.set(settings["timeout"])
                    self._update_timeout_label(settings["timeout"])

                # Restore checkboxes
                if "verbose" in settings:
                    self.verbose_var.set(settings["verbose"])
                if "dry_run" in settings:
                    self.dry_run_var.set(settings["dry_run"])
                if "skip_fbx" in settings:
                    self.skip_fbx_var.set(settings["skip_fbx"])
                if "skip_godot_cli" in settings:
                    self.skip_godot_cli_var.set(settings["skip_godot_cli"])
                if "skip_godot_import" in settings:
                    self.skip_godot_import_var.set(settings["skip_godot_import"])
                if "high_quality_textures" in settings:
                    self.high_quality_textures_var.set(settings["high_quality_textures"])

        except (json.JSONDecodeError, OSError, KeyError):
            # Corrupted or missing settings - use defaults silently
            pass

    def _save_settings(self):
        """Save current settings to JSON file in AppData."""
        settings = {
            # Paths
            "unity_package": self.unity_package_var.get(),
            "source_files": self.source_files_var.get(),
            "output_dir": self.output_dir_var.get(),
            "godot_exe": self.godot_exe_var.get(),
            # Options
            "output_format": self.format_selector.get(),
            "mesh_mode": self.mesh_mode_selector.get(),
            "filter": self.filter_var.get(),
            "timeout": self.timeout_var.get(),
            # Checkboxes
            "verbose": self.verbose_var.get(),
            "dry_run": self.dry_run_var.get(),
            "skip_fbx": self.skip_fbx_var.get(),
            "skip_godot_cli": self.skip_godot_cli_var.get(),
            "skip_godot_import": self.skip_godot_import_var.get(),
            "high_quality_textures": self.high_quality_textures_var.get(),
        }

        try:
            # Create directory if it doesn't exist
            SETTINGS_DIR.mkdir(parents=True, exist_ok=True)

            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2)
        except OSError:
            # Silently ignore save errors - not critical
            pass

    def _validate_inputs(self) -> bool:
        """Validate all input fields before conversion."""
        errors = []

        unity_package = Path(self.unity_package_var.get())
        if not unity_package.exists():
            errors.append(f"Unity package not found: {unity_package}")

        source_files = Path(self.source_files_var.get())
        if not source_files.exists():
            errors.append(f"Source files directory not found: {source_files}")

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
        # Save settings before conversion
        self._save_settings()

        if not self._validate_inputs():
            return

        # Build configuration from segmented buttons
        mesh_format = self.format_selector.get()  # "tscn" or "res"
        keep_meshes_together = self.mesh_mode_selector.get() == "Combined"

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
            mesh_format=mesh_format,
            filter_pattern=self.filter_var.get() if self.filter_var.get() else None,
            high_quality_textures=self.high_quality_textures_var.get(),
        )

        # Update UI state
        self.convert_btn.configure(state="disabled")
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
