# GUI Application (gui.py)

This document provides comprehensive documentation of the CustomTkinter-based GUI wrapper for the Synty Unity-to-Godot Converter. The GUI provides a user-friendly interface for all CLI options.

## Table of Contents

- [Overview](#overview)
- [Dependencies](#dependencies)
- [Window Layout and Structure](#window-layout-and-structure)
  - [Main Window Configuration](#main-window-configuration)
  - [Layout Hierarchy](#layout-hierarchy)
- [Widget Components](#widget-components)
  - [Header Section](#header-section)
  - [Path Input Fields](#path-input-fields)
  - [Output Options](#output-options)
  - [Filter Section](#filter-section)
  - [Advanced Options](#advanced-options)
  - [Log Panel](#log-panel)
  - [Bottom Bar](#bottom-bar)
- [Threading Model](#threading-model)
  - [Main Thread vs Background Thread](#main-thread-vs-background-thread)
  - [Thread-Safe Communication](#thread-safe-communication)
- [Queue-Based Logging](#queue-based-logging)
  - [QueueHandler Class](#queuehandler-class)
  - [Log Processing Loop](#log-processing-loop)
  - [Log Level Coloring](#log-level-coloring)
- [Theme and Styling](#theme-and-styling)
  - [Dark Mode Configuration](#dark-mode-configuration)
  - [Font Styling](#font-styling)
  - [Log Colors](#log-colors)
- [Event Handlers](#event-handlers)
  - [Browse Dialogs](#browse-dialogs)
  - [Conversion Lifecycle](#conversion-lifecycle)
  - [Help and Utility Functions](#help-and-utility-functions)
- [Input Validation](#input-validation)
- [Configuration Building](#configuration-building)
- [Application Lifecycle](#application-lifecycle)
- [Code Examples](#code-examples)
- [Notes for Doc Cleanup](#notes-for-doc-cleanup)

---

## Overview

The `gui.py` module provides a graphical user interface for the Synty Converter using the CustomTkinter library. It serves as an alternative to the command-line interface, exposing all the same options in a visual format.

**Key Features:**
- Dark mode with dark-blue color theme
- All CLI options exposed as widgets
- Real-time log output during conversion
- Background thread conversion (UI remains responsive)
- File/directory browse dialogs
- Help popup with documentation
- Progress indication
- Statistics display on completion

**File Location:** `synty-converter/gui.py`

**Entry Point:** `python gui.py` or `from gui import main; main()`

---

## Dependencies

The GUI requires CustomTkinter, which must be installed separately:

```bash
pip install customtkinter
```

The module checks for CustomTkinter at import time and exits with an error if not found:

```python
try:
    import customtkinter as ctk
except ImportError:
    print("ERROR: customtkinter not installed. Run: pip install customtkinter")
    sys.exit(1)
```

**Standard Library Dependencies:**
- `logging` - Python logging framework
- `queue` - Thread-safe queue for log messages
- `re` - Regular expressions for log parsing
- `sys` - System exit and path manipulation
- `threading` - Background thread for conversion
- `tkinter` - Base GUI toolkit (filedialog, messagebox)
- `datetime` - Timestamp formatting
- `pathlib.Path` - Path handling

**Local Dependencies:**
- `converter.ConversionConfig` - Configuration dataclass
- `converter.ConversionStats` - Statistics dataclass
- `converter.run_conversion` - Main conversion function

---

## Window Layout and Structure

### Main Window Configuration

The application creates a single main window with the following properties:

```python
APP_TITLE = "SYNTY CONVERTER"
APP_VERSION = "1.0.0"
DEFAULT_WINDOW_SIZE = "1080x640"
```

The window is centered on screen at startup:

```python
width = 1080
height = 640
screen_width = self.root.winfo_screenwidth()
screen_height = self.root.winfo_screenheight()
x = (screen_width - width) // 2
y = (screen_height - height) // 2
self.root.geometry(f"{width}x{height}+{x}+{y}")
```

### Layout Hierarchy

The main window uses a grid layout with three rows:

```
+--------------------------------------------------+
| Row 0: Header Bar (fixed height 50px)            |
|   [Title]                              [? Help]  |
+--------------------------------------------------+
| Row 1: Main Content (expands to fill)            |
|   +---------------------+----------------------+ |
|   | Settings Panel      | Log Panel            | |
|   | - Path inputs       | - Log textbox        | |
|   | - Output options    | - Clear/Copy buttons | |
|   | - Filter            |                      | |
|   | - Advanced options  |                      | |
|   +---------------------+----------------------+ |
+--------------------------------------------------+
| Row 2: Bottom Bar                                |
|   [Progress Bar] [Status] [Convert][Cancel][Info]|
+--------------------------------------------------+
```

Grid configuration:
```python
self.root.grid_columnconfigure(0, weight=1)  # Single column, expands
self.root.grid_rowconfigure(1, weight=1)     # Row 1 expands vertically
```

---

## Widget Components

### Header Section

**Location:** `_create_header()`

**Purpose:** Contains application title and help button.

**Components:**

| Widget | Type | Properties | Purpose |
|--------|------|------------|---------|
| `header_frame` | `CTkFrame` | height=50, grid_propagate=False | Container with fixed height |
| `title_label` | `CTkLabel` | font=(size=20, weight="bold") | Displays "SYNTY CONVERTER" |
| `help_btn` | `CTkButton` | width=35, height=35, text="?" | Opens help popup |

```python
header_frame = ctk.CTkFrame(self.root, height=50)
header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
header_frame.grid_propagate(False)  # Prevent frame from shrinking

title_label = ctk.CTkLabel(
    header_frame,
    text=APP_TITLE,
    font=ctk.CTkFont(size=20, weight="bold")
)
title_label.pack(side="left", padx=15, pady=10)

help_btn = ctk.CTkButton(
    header_frame,
    text="?",
    width=35,
    height=35,
    font=ctk.CTkFont(size=16, weight="bold"),
    command=self._show_help
)
help_btn.pack(side="right", padx=15, pady=7)
```

### Path Input Fields

**Location:** `_create_path_inputs()`

**Purpose:** Five path entry fields with browse buttons for required and optional paths.

**Fields:**

| Field | Variable | Default | CLI Equivalent |
|-------|----------|---------|----------------|
| Unity Package | `self.unity_package_var` | (empty) | `--unity-package` |
| Source Files | `self.source_files_var` | (empty) | `--source-files` |
| Output Directory | `self.output_dir_var` | `C:\Godot\Projects\converted-assets` | `--output` |
| Godot Executable | `self.godot_exe_var` | `C:\Godot\Godot_v4.6-stable_mono_win64\Godot_v4.6-stable_mono_win64.exe` | `--godot` |
| Output Subfolder | `self.output_subfolder_var` | (empty) | `--output-subfolder` |

**Note:** The Output Subfolder field appears below the Godot Executable field in the paths section.

**Layout:** 3-column grid with label, entry, and browse button.

```python
paths_frame.grid_columnconfigure(1, weight=1)  # Entry column expands

# Each row follows this pattern:
label = ctk.CTkLabel(paths_frame, text="Label:", anchor="w", width=120)
label.grid(row=N, column=0, sticky="w", pady=4)

entry = ctk.CTkEntry(paths_frame, textvariable=self.var)
entry.grid(row=N, column=1, sticky="ew", padx=5, pady=4)

browse = ctk.CTkButton(paths_frame, text="...", width=35, command=browse_handler)
browse.grid(row=N, column=2, pady=4)
```

**Browse Button Handlers:**

- **Unity Package:** Opens file dialog for `.unitypackage` files
- **Source Files:** Opens directory dialog
- **Output Directory:** Opens directory dialog
- **Godot Executable:** Opens file dialog for `.exe` files
- **Output Subfolder:** Opens directory dialog starting from the output directory, computes relative path

### Output Options

**Location:** `_create_output_options()`

**Purpose:** Two segmented buttons for output format and mesh mode selection.

**Components:**

| Widget | Variable | Values | Default | CLI Equivalent |
|--------|----------|--------|---------|----------------|
| Format Selector | `self.format_selector` | "tscn", "res" | "tscn" | `--mesh-format` |
| Mesh Mode Selector | `self.mesh_mode_selector` | "Separate", "Combined" | "Separate" | `--keep-meshes-together` |

```python
# Output Format
self.format_selector = ctk.CTkSegmentedButton(
    format_frame,
    values=["tscn", "res"],
    command=self._on_format_change
)
self.format_selector.set("tscn")

# Mesh Mode
self.mesh_mode_selector = ctk.CTkSegmentedButton(
    mesh_frame,
    values=["Separate", "Combined"],
    command=self._on_mesh_mode_change
)
self.mesh_mode_selector.set("Separate")
```

**Value Mapping:**

| Widget Value | Config Value |
|--------------|--------------|
| "tscn" | `mesh_format="tscn"` |
| "res" | `mesh_format="res"` |
| "Separate" | `keep_meshes_together=False` |
| "Combined" | `keep_meshes_together=True` |

### Filter Section

**Location:** `_create_filter_section()`

**Purpose:** Text entry for FBX filename filtering and mesh scale options.

**Components:**

| Widget | Variable | Default | CLI Equivalent |
|--------|----------|---------|----------------|
| Filter Entry | `self.filter_var` | (empty) | `--filter` |
| Mesh Scale Slider | `self.mesh_scale_var` | 1.0 | `--mesh-scale` |

```python
self.filter_var = ctk.StringVar()
filter_entry = ctk.CTkEntry(
    filter_inner,
    textvariable=self.filter_var,
    placeholder_text='e.g. "Tree" or "Veh"',
    width=200
)
```

**Behavior:**
- **Filter:** Empty string = no filter (all FBX files processed). Non-empty string = case-insensitive pattern match on FBX filenames. Also filters textures and materials to only include those needed by matching FBX files.

**Note:** The Mesh output label appears below the output format/mesh mode/scale selectors to show the target mesh output directory (e.g., "meshes/tscn_separate/").

**Output Subfolder** is now in the Path Input Fields section with a browse button that computes relative paths from the output directory.

**Retain Subfolders** checkbox is now in the first row of Advanced Options (Row 1) with Verbose, Dry Run, and Skip FBX Copy.

### Advanced Options

**Location:** `_create_advanced_options()`

**Purpose:** Timeout slider and boolean option checkboxes.

**Timeout Slider:**

| Widget | Variable | Range | Default | CLI Equivalent |
|--------|----------|-------|---------|----------------|
| Timeout Slider | `self.timeout_var` | 60-1800 | 600 | `--godot-timeout` |
| Timeout Label | `self.timeout_value_label` | N/A | "600s" | (display only) |

```python
self.timeout_var = ctk.IntVar(value=600)
timeout_slider = ctk.CTkSlider(
    timeout_frame,
    from_=60,
    to=1800,
    number_of_steps=58,  # 30-second increments
    variable=self.timeout_var,
    width=180,
    command=self._update_timeout_label
)
```

**Checkbox Options (Row 1):**

| Checkbox | Variable | Default | CLI Equivalent |
|----------|----------|---------|----------------|
| Verbose | `self.verbose_var` | False | `--verbose` |
| Dry Run | `self.dry_run_var` | False | `--dry-run` |
| Skip FBX Copy | `self.skip_fbx_var` | False | `--skip-fbx-copy` |
| Retain Subfolders | `self.retain_subfolders_var` | False | `--retain-subfolders` |

**Checkbox Options (Row 2):**

| Checkbox | Variable | Default | CLI Equivalent |
|----------|----------|---------|----------------|
| Skip Godot CLI | `self.skip_godot_cli_var` | False | `--skip-godot-cli` |
| Skip Godot import | `self.skip_godot_import_var` | False | `--skip-godot-import` |
| HQ textures | `self.high_quality_textures_var` | False | `--high-quality-textures` |

**Note:** All checkboxes in row 1 use equal width (105) and padding (5px) for consistent layout. "High quality textures" is displayed as "HQ textures" to fit within the column width.

```python
self.verbose_var = ctk.BooleanVar(value=False)
verbose_cb = ctk.CTkCheckBox(
    checkbox_frame1,
    text="Verbose",
    variable=self.verbose_var,
    width=105
)
```

### Log Panel

**Location:** `_create_log_panel()`

**Purpose:** Scrollable text area for real-time conversion output.

**Components:**

| Widget | Type | Purpose |
|--------|------|---------|
| `self.log_text` | `CTkTextbox` | Displays log messages |
| Clear button | `CTkButton` | Clears log contents |
| Copy button | `CTkButton` | Copies log to clipboard |

**Text Configuration:**

```python
self.log_text = ctk.CTkTextbox(log_frame, wrap="word", state="disabled")
```

The textbox is kept in "disabled" state to prevent user editing. It is temporarily enabled during log writes:

```python
self.log_text.configure(state="normal")
self.log_text.insert("end", formatted, level)
self.log_text.see("end")  # Auto-scroll to bottom
self.log_text.configure(state="disabled")
```

**Log Tags (for coloring):**

```python
self.log_text._textbox.tag_config("INFO", foreground="#90EE90")     # Light green
self.log_text._textbox.tag_config("WARNING", foreground="#FFD700")  # Gold
self.log_text._textbox.tag_config("ERROR", foreground="#FF6B6B")    # Coral red
self.log_text._textbox.tag_config("DEBUG", foreground="#87CEEB")    # Sky blue
```

### Bottom Bar

**Location:** `_create_bottom_bar()`

**Purpose:** Progress indication and control buttons.

**Components:**

| Widget | Type | Purpose |
|--------|------|---------|
| `self.progress_bar` | `CTkProgressBar` | Shows conversion progress |
| `self.progress_label` | `CTkLabel` | Status text |
| `self.convert_btn` | `CTkButton` | Starts conversion |
| `self.cancel_btn` | `CTkButton` | Cancels conversion |
| `info_btn` | `CTkButton` | Opens help popup |

**Progress Bar States:**

| State | Mode | Value |
|-------|------|-------|
| Ready | determinate | 0 |
| Converting | indeterminate | (animating) |
| Complete | determinate | 1.0 |
| Failed | determinate | 0 |

```python
# During conversion
self.progress_bar.configure(mode="indeterminate")
self.progress_bar.start()

# After completion
self.progress_bar.stop()
self.progress_bar.configure(mode="determinate")
self.progress_bar.set(1.0 if not error else 0)
```

**Button States:**

| State | Convert Button | Cancel Button |
|-------|----------------|---------------|
| Ready | enabled | disabled |
| Converting | disabled | enabled |
| Complete | enabled | disabled |

---

## Threading Model

### Main Thread vs Background Thread

The GUI uses a two-thread model to keep the UI responsive during conversion:

```
+------------------+     +---------------------+
| Main Thread      |     | Background Thread   |
| (UI/Event Loop)  |     | (Conversion)        |
+------------------+     +---------------------+
        |                         |
        | _start_conversion()     |
        |------------------------>|
        |                         | run_conversion()
        | _process_log_queue()    |
        |<------------------------|
        | (reads queue)           | (writes to queue)
        |                         |
        | root.after(0, callback) |
        |<------------------------|
        | _conversion_complete()  |
        +-------------------------+
```

**Main Thread Responsibilities:**
- All widget creation and updates
- Event handling
- Log queue processing (every 50ms)
- Final UI updates after conversion

**Background Thread Responsibilities:**
- Running `run_conversion()` from converter module
- Writing log messages to queue
- Notifying main thread on completion via `root.after()`

### Thread-Safe Communication

**Thread Creation:**

```python
self.conversion_thread = threading.Thread(
    target=self._run_conversion_thread,
    args=(config,),
    daemon=True  # Thread dies when main program exits
)
self.conversion_thread.start()
```

**Cancellation Flag:**

```python
self.conversion_cancelled = threading.Event()

# To request cancellation:
self.conversion_cancelled.set()

# To check (in background thread):
if self.conversion_cancelled.is_set():
    return  # Exit conversion
```

**Completion Notification:**

```python
# From background thread, schedule callback on main thread:
self.root.after(0, self._conversion_complete, stats, None)

# This is thread-safe because root.after() is designed for this pattern
```

---

## Queue-Based Logging

### QueueHandler Class

The `QueueHandler` class is a custom logging handler that redirects log messages to a thread-safe queue:

```python
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
```

**Key Points:**
- Inherits from `logging.Handler`
- Formats the log record using the handler's formatter
- Puts formatted string into queue (thread-safe)
- Handles exceptions gracefully to avoid disrupting logging

### Log Processing Loop

The GUI polls the log queue at regular intervals:

```python
LOG_QUEUE_INTERVAL = 50  # milliseconds

def _process_log_queue(self):
    """Process messages from the log queue and display them."""
    while True:
        try:
            message = self.log_queue.get_nowait()
            # ... process message ...
        except queue.Empty:
            break

    # Schedule next check
    self.root.after(LOG_QUEUE_INTERVAL, self._process_log_queue)
```

**Processing Steps:**

1. Drain all available messages from queue (non-blocking)
2. Determine log level from message prefix
3. Strip the level prefix for cleaner display
4. Add timestamp and insert into log textbox
5. Schedule next check after 50ms

### Log Level Coloring

Log messages are parsed to determine their level for color-coding:

```python
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
```

**Message Format:**

```
[HH:MM:SS] <message text>
```

The timestamp is added by `_log_message()`:

```python
def _log_message(self, message: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    formatted = f"[{timestamp}] {message}\n"

    self.log_text.configure(state="normal")
    self.log_text.insert("end", formatted, level)  # level is used as tag name
    self.log_text.see("end")
    self.log_text.configure(state="disabled")
```

---

## Theme and Styling

### Dark Mode Configuration

CustomTkinter is configured for dark mode before any widgets are created:

```python
# Set appearance mode and color theme BEFORE creating any widgets
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")
```

**Appearance Modes:**
- `"dark"` - Dark background, light text
- `"light"` - Light background, dark text
- `"system"` - Follow OS setting

**Color Themes:**
- `"dark-blue"` - Blue accent color (buttons, selections)
- `"green"` - Green accent color
- `"blue"` - Different blue variant

### Font Styling

Custom fonts are used for emphasis:

| Element | Font Configuration |
|---------|-------------------|
| Title | `CTkFont(size=20, weight="bold")` |
| Help button | `CTkFont(size=16, weight="bold")` |
| Section labels | `CTkFont(size=16, weight="bold")` |
| Convert button | `CTkFont(size=14, weight="bold")` |
| Status label | `CTkFont(size=11)` |

### Log Colors

The log textbox uses Tkinter text tags for color-coded output:

| Level | Color Name | Hex Code |
|-------|------------|----------|
| INFO | Light Green | `#90EE90` |
| WARNING | Gold | `#FFD700` |
| ERROR | Coral Red | `#FF6B6B` |
| DEBUG | Sky Blue | `#87CEEB` |

**Note:** These tags are applied to the underlying Tkinter textbox (`self.log_text._textbox`), not the CustomTkinter wrapper, because CustomTkinter's CTkTextbox doesn't expose tag configuration directly.

---

## Event Handlers

### Browse Dialogs

**File Browse:**

```python
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
```

**Directory Browse:**

```python
def _browse_directory(self, var: ctk.StringVar, title: str):
    """Open directory browser dialog."""
    initial_dir = var.get() if var.get() else None
    path = filedialog.askdirectory(
        title=title,
        initialdir=initial_dir
    )
    if path:
        var.set(path)
```

**Initial Directory Logic:**
- If the variable already has a value, open dialog in its parent directory (files) or same directory (directories)
- If empty, let the system choose the default

### Conversion Lifecycle

**Start Conversion (`_start_conversion`):**

1. Validate all inputs via `_validate_inputs()`
2. Build `ConversionConfig` from widget values
3. Disable Convert button, enable Cancel button
4. Start indeterminate progress bar
5. Clear cancellation flag
6. Create and start background thread
7. Log start message

**Run Conversion (`_run_conversion_thread`):**

```python
def _run_conversion_thread(self, config: ConversionConfig):
    """Run the conversion in a background thread."""
    try:
        # Set logging level
        log_level = logging.DEBUG if config.verbose else logging.INFO
        logging.getLogger().setLevel(log_level)
        logging.getLogger("converter").setLevel(log_level)

        # Run conversion
        stats = run_conversion(config)

        # Store stats and notify main thread
        self.current_stats = stats
        self.root.after(0, self._conversion_complete, stats, None)

    except Exception as e:
        self.root.after(0, self._conversion_complete, None, str(e))
```

**Conversion Complete (`_conversion_complete`):**

1. Re-enable Convert button, disable Cancel button
2. Stop progress bar animation
3. Set progress bar to 1.0 (success) or 0 (failure)
4. If error: show error message box and log
5. If success: log summary statistics

**Cancel Conversion (`_cancel_conversion`):**

```python
def _cancel_conversion(self):
    """Request cancellation of the running conversion."""
    self.conversion_cancelled.set()
    self.progress_label.configure(text="Cancelling...")
    self._log_message("Cancellation requested...", level="WARNING")
```

**Note:** The current implementation sets the cancellation flag but does not check it in the converter. This is a UI-level cancellation request that would need converter support to actually interrupt the conversion.

### Help and Utility Functions

**Show Help (`_show_help`):**

Creates a modal popup window with help text:

```python
def _show_help(self):
    help_window = ctk.CTkToplevel(self.root)
    help_window.title("Synty Converter Help")
    help_window.geometry("500x450")
    help_window.resizable(False, False)

    # Make it modal
    help_window.transient(self.root)  # Stay on top of main window
    help_window.grab_set()             # Block interaction with main window

    # ... add text and close button ...

    # Center on main window
    help_window.update_idletasks()
    x = self.root.winfo_x() + (self.root.winfo_width() - help_window.winfo_width()) // 2
    y = self.root.winfo_y() + (self.root.winfo_height() - help_window.winfo_height()) // 2
    help_window.geometry(f"+{x}+{y}")
```

**Clear Log (`_clear_log`):**

```python
def _clear_log(self):
    self.log_text.configure(state="normal")
    self.log_text.delete("1.0", "end")
    self.log_text.configure(state="disabled")
```

**Copy Log (`_copy_log`):**

```python
def _copy_log(self):
    self.root.clipboard_clear()
    self.root.clipboard_append(self.log_text.get("1.0", "end"))
    self._log_message("Log copied to clipboard")
```

**Update Timeout Label (`_update_timeout_label`):**

```python
def _update_timeout_label(self, value):
    seconds = int(float(value))
    self.timeout_value_label.configure(text=f"{seconds}s")
```

---

## Input Validation

The `_validate_inputs()` method checks all required paths before conversion:

```python
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
```

**Validation Rules:**

| Field | Validation |
|-------|------------|
| Unity Package | File must exist |
| Source Files | Directory must exist |
| Godot Executable | File must exist |
| Output Directory | Must not be empty (created if doesn't exist) |

**Note:** The output directory is not validated for existence because it will be created by the converter.

---

## Configuration Building

The `_start_conversion()` method builds a `ConversionConfig` from all widget values:

```python
def _start_conversion(self):
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
    )
```

**Widget-to-Config Mapping:**

| Widget | Config Field | Transformation |
|--------|--------------|----------------|
| `unity_package_var` | `unity_package` | `Path()` |
| `source_files_var` | `source_files` | `Path()` |
| `output_dir_var` | `output_dir` | `Path()` |
| `godot_exe_var` | `godot_exe` | `Path()` |
| `dry_run_var` | `dry_run` | direct |
| `verbose_var` | `verbose` | direct |
| `skip_fbx_var` | `skip_fbx_copy` | direct |
| `skip_godot_cli_var` | `skip_godot_cli` | direct |
| `skip_godot_import_var` | `skip_godot_import` | direct |
| `timeout_var` | `godot_timeout` | direct |
| `mesh_mode_selector` | `keep_meshes_together` | "Combined" -> True |
| `format_selector` | `mesh_format` | direct |
| `filter_var` | `filter_pattern` | empty string -> None |
| `output_subfolder_var` | `output_subfolder` | empty string -> None |
| `retain_subfolders_var` | `flatten_output` | inverted (retain_subfolders=False -> flatten_output=True) |

---

## Application Lifecycle

### SyntyConverterApp Class

The main application class manages the entire GUI lifecycle:

```python
class SyntyConverterApp:
    """Main GUI application class."""

    def __init__(self):
        # Create the root window
        self.root = ctk.CTk()

        # ... configure window ...

        # State variables
        self.conversion_thread: threading.Thread | None = None
        self.conversion_cancelled = threading.Event()
        self.log_queue: queue.Queue = queue.Queue()
        self.current_stats: ConversionStats | None = None

        # Build the GUI
        self._create_widgets()
        self._setup_logging()

        # Start log queue processing
        self._process_log_queue()

    def run(self):
        """Start the application main loop."""
        self.root.mainloop()
```

**Initialization Order:**

1. Create root window (`CTk()`)
2. Configure window title, size, position
3. Initialize state variables (thread, cancellation flag, queue, stats)
4. Create all widgets (`_create_widgets()`)
5. Set up logging system (`_setup_logging()`)
6. Start log queue processor (`_process_log_queue()`)

### Logging Setup

```python
def _setup_logging(self):
    """Set up logging to capture converter output."""
    # Create queue handler
    self.queue_handler = QueueHandler(self.log_queue)
    self.queue_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    # Configure the converter's logger
    converter_logger = logging.getLogger("converter")
    converter_logger.handlers.clear()
    converter_logger.addHandler(self.queue_handler)
    converter_logger.setLevel(logging.DEBUG)
    converter_logger.propagate = False  # Don't send to root logger

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(self.queue_handler)
    root_logger.setLevel(logging.DEBUG)
```

**Key Points:**
- Clear existing handlers to prevent duplicate messages
- Set `propagate = False` on converter logger to prevent double logging
- Use same queue handler for both converter and root loggers
- Format includes level prefix for later parsing

### Main Entry Point

```python
def main():
    """Main entry point for the GUI application."""
    app = SyntyConverterApp()
    app.run()

if __name__ == "__main__":
    main()
```

---

## Code Examples

### Running the GUI

```bash
# From command line
python gui.py

# Or with Python path
C:\Users\alexg\AppData\Local\Programs\Python\Python313\python.exe C:\Godot\Projects\synty-converter\gui.py
```

### Programmatic Launch

```python
from gui import SyntyConverterApp

app = SyntyConverterApp()
app.run()
```

### Pre-filling Fields

To launch with pre-filled values, modify the StringVar initialization:

```python
# In _create_path_inputs():
self.unity_package_var = ctk.StringVar(value="C:/path/to/package.unitypackage")
```

Or modify after creation but before `run()`:

```python
app = SyntyConverterApp()
app.unity_package_var.set("C:/path/to/package.unitypackage")
app.run()
```

---

## Notes for Doc Cleanup

After reviewing the existing documentation in `C:\Godot\Projects\synty-converter\docs\`, the following observations were made:

### Redundant Information

1. **docs/user-guide.md** - The "Command-Line Options" section (lines 135-158) documents CLI arguments but does not mention the GUI alternative. Consider:
   - Adding a brief note that a GUI alternative exists
   - Adding a section on GUI usage for users who prefer graphical interfaces
   - The user guide could link to this GUI documentation

2. **Help text in gui.py (HELP_TEXT constant)** - Duplicates information from user-guide.md:
   - The help popup content mirrors the user guide's explanation of paths and options
   - This is intentional for standalone help access but should stay synchronized
   - Consider noting in user-guide.md that the same help is available in-app

### Missing Information in Existing Docs

1. **docs/README.md or docs/index.md** - Should mention gui.py as an alternative interface:
   - Currently all documentation assumes CLI usage
   - No mention of CustomTkinter dependency for GUI

2. **Installation instructions** - Should note GUI-specific setup:
   - `pip install customtkinter` is only documented in gui.py itself
   - Could be added to user-guide.md's Installation section

3. **docs/architecture.md** - Does not mention gui.py at all:
   - The module dependency graph should include gui.py
   - Could add a note that GUI is a thin wrapper around converter.py

### Outdated Information

1. **No outdated GUI information found** - This is the first GUI documentation, so there's nothing to correct.

### Information to Incorporate Elsewhere

The following from this document could enhance other docs:

1. **Threading model** - Could be useful context for developers modifying the converter:
   - Understanding that the converter may run in a background thread
   - Awareness of the queue-based logging system

2. **Default paths** - The GUI constants show common Windows paths:
   - `DEFAULT_SYNTY_PATH = r"C:\SyntyComplete"`
   - `DEFAULT_GODOT_PATH = r"C:\Godot\Godot_v4.6-stable_mono_win64\Godot_v4.6-stable_mono_win64.exe"`
   - `DEFAULT_OUTPUT_PATH = r"C:\Godot\Projects\converted-assets"`
   - These could be mentioned in troubleshooting.md as common setup patterns

### Recommendations

1. **Add GUI section to user-guide.md** - Brief overview pointing to this doc
2. **Update architecture.md** - Add gui.py to module diagram
3. **Create INSTALL.md or enhance user-guide.md** - Include `pip install customtkinter`
4. **Keep HELP_TEXT synchronized** - When user-guide.md changes, update HELP_TEXT
