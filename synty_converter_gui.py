#!/usr/bin/env python3
"""
Synty Asset Converter GUI
A user-friendly interface for converting Synty FBX assets to Godot format.

Build standalone exe:
    pip install pyinstaller
    pyinstaller --onefile --windowed --name "SyntyConverter" synty_converter_gui.py
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# Import the converter module (must be in same directory or Python path)
try:
    from synty_converter import Config, SyntyConverter
    from synty_shaders import install_shaders, install_import_script
except ImportError:
    # When running as exe, the module should be bundled
    install_shaders = None
    install_import_script = None


class ConverterGUI:
    """Main GUI application for Synty Converter."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Synty to Godot Converter")
        self.root.geometry("600x700")
        self.root.minsize(500, 600)

        # Configure dark theme colors
        self.bg_color = "#1e1e1e"
        self.fg_color = "#ffffff"
        self.accent_color = "#4fc3f7"
        self.button_bg = "#333333"
        self.entry_bg = "#2d2d2d"
        self.success_color = "#4caf50"
        self.error_color = "#f44336"

        self.root.configure(bg=self.bg_color)

        # Configure ttk styles
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self._configure_styles()

        # Variables
        self.source_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.pack_name_var = tk.StringVar()
        self.normalize_var = tk.BooleanVar(value=False)
        self.normalize_size_var = tk.DoubleVar(value=2.0)
        self.force_scale_var = tk.StringVar(value="")
        self.dry_run_var = tk.BooleanVar(value=False)
        self.filter_var = tk.StringVar()
        self.skip_existing_var = tk.BooleanVar(value=True)

        # Conversion state
        self.is_converting = False
        self.converter_thread = None

        self._create_widgets()

    def _configure_styles(self):
        """Configure ttk widget styles for dark theme."""
        self.style.configure(".",
            background=self.bg_color,
            foreground=self.fg_color,
            fieldbackground=self.entry_bg)

        self.style.configure("TFrame", background=self.bg_color)
        self.style.configure("TLabel", background=self.bg_color, foreground=self.fg_color)
        self.style.configure("TButton",
            background=self.button_bg,
            foreground=self.fg_color,
            padding=(10, 5))
        self.style.map("TButton",
            background=[("active", self.accent_color), ("disabled", "#555555")])

        self.style.configure("TCheckbutton",
            background=self.bg_color,
            foreground=self.fg_color)
        self.style.map("TCheckbutton",
            background=[("active", self.bg_color)])

        self.style.configure("TEntry",
            fieldbackground=self.entry_bg,
            foreground=self.fg_color,
            insertcolor=self.fg_color)

        self.style.configure("Accent.TButton",
            background=self.accent_color,
            foreground="#000000",
            padding=(20, 10))
        self.style.map("Accent.TButton",
            background=[("active", "#81d4fa"), ("disabled", "#555555")])

        self.style.configure("TLabelframe",
            background=self.bg_color,
            foreground=self.accent_color)
        self.style.configure("TLabelframe.Label",
            background=self.bg_color,
            foreground=self.accent_color)

        # Progress bar
        self.style.configure("TProgressbar",
            background=self.accent_color,
            troughcolor=self.entry_bg)

    def _create_widgets(self):
        """Create all GUI widgets."""
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Title
        title_label = tk.Label(main_frame,
            text="Synty to Godot Converter",
            font=("Segoe UI", 18, "bold"),
            bg=self.bg_color,
            fg=self.accent_color)
        title_label.pack(pady=(0, 5))

        subtitle_label = tk.Label(main_frame,
            text="Convert Synty FBX source files to Godot-native format",
            font=("Segoe UI", 10),
            bg=self.bg_color,
            fg="#888888")
        subtitle_label.pack(pady=(0, 20))

        # === Paths Section ===
        paths_frame = ttk.LabelFrame(main_frame, text="Paths", padding=15)
        paths_frame.pack(fill=tk.X, pady=(0, 15))

        # Source folder
        ttk.Label(paths_frame, text="Synty Source Folder:").pack(anchor=tk.W)
        source_frame = ttk.Frame(paths_frame)
        source_frame.pack(fill=tk.X, pady=(5, 10))

        self.source_entry = ttk.Entry(source_frame, textvariable=self.source_var)
        self.source_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        ttk.Button(source_frame, text="Browse...",
            command=self._browse_source).pack(side=tk.RIGHT)

        # Output folder
        ttk.Label(paths_frame, text="Godot Project Folder:").pack(anchor=tk.W)
        output_frame = ttk.Frame(paths_frame)
        output_frame.pack(fill=tk.X, pady=(5, 0))

        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_var)
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        ttk.Button(output_frame, text="Browse...",
            command=self._browse_output).pack(side=tk.RIGHT)

        # === Settings Section ===
        settings_frame = ttk.LabelFrame(main_frame, text="Settings", padding=15)
        settings_frame.pack(fill=tk.X, pady=(0, 15))

        # Pack name
        pack_frame = ttk.Frame(settings_frame)
        pack_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(pack_frame, text="Pack Name:").pack(side=tk.LEFT)
        self.pack_entry = ttk.Entry(pack_frame, textvariable=self.pack_name_var, width=30)
        self.pack_entry.pack(side=tk.LEFT, padx=(10, 0))

        ttk.Label(pack_frame, text="(auto-detected from folder)",
            foreground="#888888").pack(side=tk.LEFT, padx=(10, 0))

        # Size normalization
        normalize_frame = ttk.Frame(settings_frame)
        normalize_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Checkbutton(normalize_frame,
            text="Normalize asset size",
            variable=self.normalize_var,
            command=self._toggle_normalize).pack(side=tk.LEFT)

        self.size_spinbox = ttk.Spinbox(normalize_frame,
            from_=0.5, to=10.0, increment=0.5,
            textvariable=self.normalize_size_var,
            width=6,
            state=tk.DISABLED)
        self.size_spinbox.pack(side=tk.LEFT, padx=(10, 5))

        ttk.Label(normalize_frame, text="meters (requires Blender)").pack(side=tk.LEFT)

        # Force scale
        force_scale_frame = ttk.Frame(settings_frame)
        force_scale_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(force_scale_frame, text="Force Scale:").pack(side=tk.LEFT)
        self.force_scale_entry = ttk.Entry(force_scale_frame, textvariable=self.force_scale_var, width=8)
        self.force_scale_entry.pack(side=tk.LEFT, padx=(10, 10))

        ttk.Label(force_scale_frame, text="Override scale (e.g., 100 for cm to m). Leave empty for auto.",
            foreground="#888888").pack(side=tk.LEFT)

        # Filter
        filter_frame = ttk.Frame(settings_frame)
        filter_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(filter_frame, text="Filter (optional):").pack(side=tk.LEFT)
        self.filter_entry = ttk.Entry(filter_frame, textvariable=self.filter_var, width=25)
        self.filter_entry.pack(side=tk.LEFT, padx=(10, 10))

        ttk.Label(filter_frame, text="e.g. 'Tree' to only convert trees",
            foreground="#888888").pack(side=tk.LEFT)

        # Checkboxes row
        checks_frame = ttk.Frame(settings_frame)
        checks_frame.pack(fill=tk.X)

        ttk.Checkbutton(checks_frame,
            text="Skip existing files",
            variable=self.skip_existing_var).pack(side=tk.LEFT, padx=(0, 20))

        ttk.Checkbutton(checks_frame,
            text="Dry run (preview only)",
            variable=self.dry_run_var).pack(side=tk.LEFT)

        # === Convert Button ===
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=15)

        self.convert_btn = ttk.Button(button_frame,
            text="Convert",
            style="Accent.TButton",
            command=self._start_conversion)
        self.convert_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 10))

        self.cancel_btn = ttk.Button(button_frame,
            text="Cancel",
            command=self._cancel_conversion,
            state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.RIGHT)

        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame,
            variable=self.progress_var,
            maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(0, 10))

        # Status label
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = tk.Label(main_frame,
            textvariable=self.status_var,
            font=("Segoe UI", 9),
            bg=self.bg_color,
            fg="#888888")
        self.status_label.pack(anchor=tk.W)

        # === Log Section ===
        log_frame = ttk.LabelFrame(main_frame, text="Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        # Log text with scrollbar
        log_scroll = ttk.Scrollbar(log_frame)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.log_text = tk.Text(log_frame,
            height=12,
            bg=self.entry_bg,
            fg=self.fg_color,
            font=("Consolas", 9),
            wrap=tk.WORD,
            yscrollcommand=log_scroll.set)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        log_scroll.config(command=self.log_text.yview)

        # Configure log tags for colored output
        self.log_text.tag_configure("info", foreground=self.fg_color)
        self.log_text.tag_configure("success", foreground=self.success_color)
        self.log_text.tag_configure("error", foreground=self.error_color)
        self.log_text.tag_configure("warning", foreground="#ff9800")
        self.log_text.tag_configure("header", foreground=self.accent_color, font=("Consolas", 9, "bold"))

    def _toggle_normalize(self):
        """Toggle size spinbox state based on checkbox."""
        state = tk.NORMAL if self.normalize_var.get() else tk.DISABLED
        self.size_spinbox.config(state=state)

    def _find_source_folder(self, selected_path: Path) -> Path | None:
        """
        Find the actual SourceFiles folder from user selection.

        Synty packs extract with structure:
          POLYGON_Pack_Name/
          └── POLYGON_Pack_Name_SourceFiles/
              ├── FBX/
              ├── Textures/
              └── MaterialList_*.txt

        If user selects the parent, auto-navigate to SourceFiles subfolder.
        Returns the correct path, or None if not found.
        """
        # Check if MaterialList exists in selected folder
        if list(selected_path.glob("MaterialList*.txt")):
            return selected_path

        # Look for SourceFiles subfolder
        # Common patterns: *_SourceFiles, *_Source, *SourceFiles
        for subfolder in selected_path.iterdir():
            if not subfolder.is_dir():
                continue
            name = subfolder.name.lower()
            if 'sourcefiles' in name or name.endswith('_source'):
                if list(subfolder.glob("MaterialList*.txt")):
                    return subfolder

        # Also check for direct FBX/Textures folders (some packs extract flat)
        if (selected_path / "FBX").exists() or (selected_path / "Textures").exists():
            # MaterialList might be named differently or in a subfolder
            for txt in selected_path.rglob("MaterialList*.txt"):
                return txt.parent

        return None

    def _browse_source(self):
        """Open folder browser for source directory."""
        folder = filedialog.askdirectory(
            title="Select Synty Source Folder",
            initialdir=self.source_var.get() or "C:\\")
        if folder:
            folder_path = Path(folder)

            # Try to find the actual SourceFiles folder
            actual_source = self._find_source_folder(folder_path)
            if actual_source:
                folder = str(actual_source)
                if actual_source != folder_path:
                    self._log(f"Auto-navigated to: {actual_source.name}", "info")

            self.source_var.set(folder)

            # Auto-detect pack name from the actual folder
            folder_name = Path(folder).name
            # Remove common suffixes
            pack_name = folder_name.replace("_SourceFiles", "").replace("_Source", "")
            self.pack_name_var.set(pack_name)
            self._log(f"Source folder: {folder}", "info")
            self._log(f"Detected pack: {pack_name}", "info")

    def _browse_output(self):
        """Open folder browser for output directory."""
        folder = filedialog.askdirectory(
            title="Select Godot Project Folder",
            initialdir=self.output_var.get() or "C:\\")
        if folder:
            self.output_var.set(folder)
            self._log(f"Output folder: {folder}", "info")

    def _log(self, message: str, tag: str = "info"):
        """Add message to log with specified tag."""
        self.log_text.insert(tk.END, message + "\n", tag)
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def _clear_log(self):
        """Clear the log text."""
        self.log_text.delete(1.0, tk.END)

    def _set_status(self, message: str, color: str = None):
        """Update status label."""
        self.status_var.set(message)
        self.status_label.config(fg=color or "#888888")

    def _validate_inputs(self) -> bool:
        """Validate user inputs before conversion."""
        source = self.source_var.get().strip()
        output = self.output_var.get().strip()
        pack_name = self.pack_name_var.get().strip()

        if not source:
            messagebox.showerror("Error", "Please select a Synty source folder.")
            return False

        if not Path(source).exists():
            messagebox.showerror("Error", f"Source folder does not exist:\n{source}")
            return False

        if not output:
            messagebox.showerror("Error", "Please select a Godot project folder.")
            return False

        if not Path(output).exists():
            messagebox.showerror("Error", f"Output folder does not exist:\n{output}")
            return False

        if not pack_name:
            messagebox.showerror("Error", "Please enter a pack name.")
            return False

        # Find the actual source folder (auto-navigate into SourceFiles if needed)
        source_path = Path(source)
        actual_source = self._find_source_folder(source_path)

        if not actual_source:
            messagebox.showerror("Error",
                f"No MaterialList*.txt found in source folder.\n\n"
                f"Make sure you selected the Synty source folder containing:\n"
                f"  - MaterialList_*.txt\n"
                f"  - FBX/ folder\n"
                f"  - Textures/ folder\n\n"
                f"(e.g., POLYGON_Explorer_Kit_SourceFiles)")
            return False

        # Update source path if we found a subfolder
        if actual_source != source_path:
            self.source_var.set(str(actual_source))
            self._log(f"Auto-detected SourceFiles: {actual_source.name}", "info")
            # Update pack name from the actual folder
            folder_name = actual_source.name
            pack_name = folder_name.replace("_SourceFiles", "").replace("_Source", "")
            self.pack_name_var.set(pack_name)
            self._log(f"Updated pack name: {pack_name}", "info")

        return True

    def _start_conversion(self):
        """Start the conversion process in a background thread."""
        if not self._validate_inputs():
            return

        self.is_converting = True
        self.convert_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self._clear_log()
        self.progress_var.set(0)

        # Start conversion in background thread
        self.converter_thread = threading.Thread(target=self._run_conversion, daemon=True)
        self.converter_thread.start()

    def _cancel_conversion(self):
        """Cancel the ongoing conversion."""
        self.is_converting = False
        self._set_status("Cancelling...", self.error_color)

    def _run_conversion(self):
        """Run the conversion (called in background thread)."""
        try:
            source = Path(self.source_var.get().strip())
            output = Path(self.output_var.get().strip())
            pack_name = self.pack_name_var.get().strip()
            normalize = self.normalize_size_var.get() if self.normalize_var.get() else None
            dry_run = self.dry_run_var.get()
            name_filter = self.filter_var.get().strip() or None

            # Parse force scale (empty or 0 means None/auto)
            force_scale_str = self.force_scale_var.get().strip()
            force_scale = None
            if force_scale_str:
                try:
                    force_scale_val = float(force_scale_str)
                    if force_scale_val != 0:
                        force_scale = force_scale_val
                except ValueError:
                    self._log(f"Warning: Invalid force scale '{force_scale_str}', using auto-detection", "warning")

            self._log("=" * 50, "header")
            self._log("SYNTY TO GODOT CONVERTER", "header")
            self._log("=" * 50, "header")
            self._log(f"Pack: {pack_name}", "info")
            self._log(f"Source: {source}", "info")
            self._log(f"Output: {output / 'assets' / 'synty' / pack_name}", "info")
            if force_scale:
                self._log(f"Force scale: {force_scale}x", "info")
            elif normalize:
                self._log(f"Size normalization: {normalize}m", "info")
            if name_filter:
                self._log(f"Filter: {name_filter}", "info")
            if dry_run:
                self._log("DRY RUN MODE - No files will be written", "warning")
            self._log("", "info")

            # Install shaders if needed
            self._set_status("Installing shaders...", self.accent_color)
            self.progress_var.set(2)
            if install_shaders and not dry_run:
                self._log("Checking shaders...", "info")
                installed = install_shaders(output, log_callback=self._log)
                if installed:
                    self._log(f"  Installed {len(installed)} shaders", "success")

            # Install import script for collision generation
            if install_import_script and not dry_run:
                self._log("Checking import script...", "info")
                install_import_script(output, log_callback=self._log)
            self._log("", "info")

            self._set_status("Initializing...", self.accent_color)
            self.progress_var.set(5)

            # Create config
            # Find zip file (optional, for MaterialList fallback)
            zip_path = source.parent / f"{source.name}.zip"
            if not zip_path.exists():
                zip_path = source / "placeholder.zip"  # Dummy path

            config = Config(
                zip_path=zip_path,
                source_dir=source,
                project_root=output,
                pack_name=pack_name,
            )

            # Create converter with custom logging
            converter = SyntyConverterWithCallback(
                config,
                normalize_height=normalize,
                force_scale=force_scale,
                log_callback=self._log,
                progress_callback=self._update_progress,
                cancel_check=lambda: not self.is_converting
            )

            self._set_status("Converting...", self.accent_color)
            stats = converter.convert(dry_run=dry_run, name_filter=name_filter)

            if not self.is_converting:
                self._log("\nConversion cancelled by user.", "warning")
                self._set_status("Cancelled", self.error_color)
            else:
                # Show summary
                self._log("", "info")
                self._log("=" * 50, "header")
                self._log("SUMMARY", "header")
                self._log("=" * 50, "header")
                self._log(f"Textures copied: {stats['textures']}", "success")
                self._log(f"Materials created: {stats['materials']}", "success")
                self._log(f"Models copied: {stats['models']}", "success")
                self._log(f"Prefabs created: {stats['prefabs']}", "success")

                if stats['skipped']:
                    self._log(f"\nSkipped: {len(stats['skipped'])} items", "warning")

                if stats['errors']:
                    self._log(f"\nErrors: {len(stats['errors'])}", "error")
                    for err in stats['errors'][:5]:
                        self._log(f"  - {err}", "error")

                self._log("\nDone!", "success")
                self._set_status(f"Complete! {stats['prefabs']} prefabs created", self.success_color)
                self.progress_var.set(100)

        except Exception as e:
            self._log(f"\nError: {str(e)}", "error")
            self._set_status(f"Error: {str(e)}", self.error_color)
            import traceback
            self._log(traceback.format_exc(), "error")

        finally:
            self.is_converting = False
            self.root.after(0, self._conversion_complete)

    def _update_progress(self, percent: float):
        """Update progress bar (called from converter)."""
        self.progress_var.set(percent)

    def _conversion_complete(self):
        """Called when conversion finishes (in main thread)."""
        self.convert_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)


class SyntyConverterWithCallback(SyntyConverter):
    """Extended converter with progress callbacks for GUI."""

    def __init__(self, config, normalize_height=None, force_scale=None, log_callback=None,
                 progress_callback=None, cancel_check=None):
        super().__init__(config, normalize_height, force_scale=force_scale)
        self.log_callback = log_callback or print
        self.progress_callback = progress_callback or (lambda x: None)
        self.cancel_check = cancel_check or (lambda: False)

    def convert(self, dry_run=False, name_filter=None):
        """Override convert with progress reporting."""
        stats = {
            'prefabs': 0,
            'materials': 0,
            'textures': 0,
            'models': 0,
            'skipped': [],
            'errors': [],
        }

        # Step 1: Parse MaterialList
        self.log_callback("Parsing MaterialList...", "info")
        self.progress_callback(10)

        try:
            prefabs, materials = self.parser.parse_from_directory(self.config.source_dir)
        except FileNotFoundError as e:
            stats['errors'].append(str(e))
            return stats

        self.log_callback(f"  Found {len(prefabs)} prefabs, {len(materials)} unique materials", "info")

        if self.cancel_check():
            return stats

        # Apply filter
        if name_filter:
            filter_lower = name_filter.lower()
            prefabs = [p for p in prefabs if filter_lower in p.prefab_name.lower()]
            self.log_callback(f"  After filter: {len(prefabs)} prefabs", "info")

        if dry_run:
            self.log_callback("\n[DRY RUN] Would create:", "warning")
            self.log_callback(f"  {len(materials)} materials", "info")
            self.log_callback(f"  {len(prefabs)} prefabs", "info")
            self.progress_callback(100)
            return stats

        # Step 2: Copy textures
        self.log_callback("\nCopying textures...", "info")
        self.progress_callback(20)

        copied_textures = self.texture_copier.copy_textures(materials, self.config)
        stats['textures'] = len(copied_textures)
        self.log_callback(f"  Copied {len(copied_textures)} textures", "success")

        if self.cancel_check():
            return stats

        # Step 3: Generate materials
        self.log_callback("\nGenerating materials...", "info")
        self.progress_callback(40)

        texture_map = self.texture_copier.texture_filename_map
        valid_materials = set()

        def needs_texture(mat):
            if mat.is_glass:
                return False
            name_lower = mat.material_name.lower()
            if any(x in name_lower for x in ['water', 'ocean', 'river', 'gem', 'crystal', 'jewel', 'geode']):
                return False
            return True

        for mat in materials.values():
            if self.cancel_check():
                return stats

            if needs_texture(mat) and mat.texture_name and mat.texture_name not in texture_map:
                continue

            try:
                self.material_gen.write_material(mat, self.config, texture_map)
                stats['materials'] += 1
                valid_materials.add(mat.material_name)
            except Exception as e:
                stats['errors'].append(f"Material {mat.material_name}: {e}")

        self.log_callback(f"  Created {stats['materials']} materials", "success")

        # Step 4: Generate prefabs
        self.log_callback("\nGenerating prefabs...", "info")

        skip_patterns = ['FX_', 'LightRay_', 'WeatherControl', 'SyntyWeather',
                        'SM_Env_Cloud_', 'SM_Env_Fog_', 'SM_Env_Skydome_']

        total_prefabs = len(prefabs)
        for i, prefab in enumerate(prefabs):
            if self.cancel_check():
                return stats

            # Update progress (40-95%)
            progress = 40 + (55 * (i / max(total_prefabs, 1)))
            self.progress_callback(progress)

            # Skip patterns
            if any(prefab.prefab_name.startswith(p) for p in skip_patterns):
                stats['skipped'].append(prefab.prefab_name)
                continue

            if '_Collision' in prefab.prefab_name:
                stats['skipped'].append(prefab.prefab_name)
                continue

            try:
                tscn_path, model_path = self.prefab_gen.write_prefab(
                    prefab, self.config, valid_materials
                )
                if tscn_path:
                    stats['prefabs'] += 1
                    if stats['prefabs'] % 50 == 0:
                        self.log_callback(f"  Created {stats['prefabs']} prefabs...", "info")
                else:
                    stats['skipped'].append(prefab.prefab_name)
                if model_path:
                    stats['models'] += 1
            except Exception as e:
                stats['errors'].append(f"Prefab {prefab.prefab_name}: {e}")

        self.progress_callback(95)
        return stats


def main():
    """Main entry point."""
    root = tk.Tk()

    # Set icon if available
    try:
        # For bundled exe, icon would be in same directory
        icon_path = Path(__file__).parent / "icon.ico"
        if icon_path.exists():
            root.iconbitmap(str(icon_path))
    except Exception:
        pass

    app = ConverterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
