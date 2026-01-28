"""Modern GUI for Synty Converter v2."""

import customtkinter as ctk
from tkinter import filedialog, messagebox
from pathlib import Path
import threading
import logging
import sys
import re
from typing import Optional

# Handle imports for both module and standalone exe contexts
try:
    from .converter import SyntyConverter
    from .config import ConversionConfig
except ImportError:
    from synty_converter_v2.converter import SyntyConverter
    from synty_converter_v2.config import ConversionConfig


class TextHandler(logging.Handler):
    """Logging handler that writes to a CTkTextbox."""

    def __init__(self, textbox: ctk.CTkTextbox):
        super().__init__()
        self.textbox = textbox

    def emit(self, record):
        msg = self.format(record)
        self.textbox.after(0, self._append, msg)

    def _append(self, msg: str):
        self.textbox.configure(state="normal")
        self.textbox.insert("end", msg + "\n")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")


class SyntyConverterGUI(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        # Window setup
        self.title("Synty Converter v2")
        self.geometry("700x600")
        self.minsize(600, 500)

        # Set theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Variables
        self.package_path: Optional[Path] = None
        self.project_path: Optional[Path] = None
        self.is_converting = False

        # Build UI
        self._create_widgets()
        self._setup_logging()

    def _create_widgets(self):
        """Create all UI widgets."""
        # Configure grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # Header
        header = ctk.CTkLabel(
            self,
            text="Synty Asset Converter",
            font=ctk.CTkFont(size=28, weight="bold"),
        )
        header.grid(row=0, column=0, padx=30, pady=(30, 5), sticky="w")

        subtitle = ctk.CTkLabel(
            self,
            text="Convert Unity Synty packs to Godot 4.x",
            font=ctk.CTkFont(size=14),
            text_color="gray",
        )
        subtitle.grid(row=1, column=0, padx=30, pady=(0, 20), sticky="w")

        # Input frame
        input_frame = ctk.CTkFrame(self, fg_color="transparent")
        input_frame.grid(row=2, column=0, padx=30, pady=10, sticky="ew")
        input_frame.grid_columnconfigure(1, weight=1)

        # Unity Package selection
        pkg_label = ctk.CTkLabel(
            input_frame,
            text="Unity Package",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        pkg_label.grid(row=0, column=0, padx=(0, 15), pady=10, sticky="w")

        self.pkg_entry = ctk.CTkEntry(
            input_frame,
            placeholder_text="Select .unitypackage file...",
            height=40,
            font=ctk.CTkFont(size=13),
        )
        self.pkg_entry.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="ew")

        pkg_btn = ctk.CTkButton(
            input_frame,
            text="Browse",
            width=100,
            height=40,
            command=self._browse_package,
        )
        pkg_btn.grid(row=0, column=2, pady=10)

        # Godot Project selection
        proj_label = ctk.CTkLabel(
            input_frame,
            text="Godot Project",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        proj_label.grid(row=1, column=0, padx=(0, 15), pady=10, sticky="w")

        self.proj_entry = ctk.CTkEntry(
            input_frame,
            placeholder_text="Select Godot project folder...",
            height=40,
            font=ctk.CTkFont(size=13),
        )
        self.proj_entry.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")

        proj_btn = ctk.CTkButton(
            input_frame,
            text="Browse",
            width=100,
            height=40,
            command=self._browse_project,
        )
        proj_btn.grid(row=1, column=2, pady=10)

        # Log output
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=3, column=0, padx=30, pady=(20, 10), sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        log_label = ctk.CTkLabel(
            log_frame,
            text="Output",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        log_label.grid(row=0, column=0, padx=15, pady=(10, 5), sticky="w")

        self.log_text = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(family="Consolas", size=12),
            state="disabled",
            wrap="word",
        )
        self.log_text.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

        # Bottom frame with options and convert button
        bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        bottom_frame.grid(row=4, column=0, padx=30, pady=(10, 30), sticky="ew")
        bottom_frame.grid_columnconfigure(0, weight=1)

        # Options
        options_frame = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        options_frame.grid(row=0, column=0, sticky="w")

        self.dry_run_var = ctk.BooleanVar(value=False)
        dry_run_cb = ctk.CTkCheckBox(
            options_frame,
            text="Dry Run (preview only)",
            variable=self.dry_run_var,
            font=ctk.CTkFont(size=13),
        )
        dry_run_cb.grid(row=0, column=0, padx=(0, 20))

        self.extract_meshes_var = ctk.BooleanVar(value=True)
        extract_cb = ctk.CTkCheckBox(
            options_frame,
            text="Extract Meshes",
            variable=self.extract_meshes_var,
            font=ctk.CTkFont(size=13),
        )
        extract_cb.grid(row=0, column=1)

        # Convert button
        self.convert_btn = ctk.CTkButton(
            bottom_frame,
            text="Convert",
            width=150,
            height=45,
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self._start_conversion,
        )
        self.convert_btn.grid(row=0, column=1, sticky="e")

        # Progress bar (hidden initially)
        self.progress = ctk.CTkProgressBar(self, mode="indeterminate")

    def _setup_logging(self):
        """Configure logging to output to the textbox."""
        handler = TextHandler(self.log_text)
        handler.setFormatter(logging.Formatter("%(message)s"))

        # Get the root logger and synty_converter_v2 logger
        for logger_name in ["synty_converter_v2", ""]:
            logger = logging.getLogger(logger_name)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)

    def _browse_package(self):
        """Open file dialog for Unity package selection."""
        path = filedialog.askopenfilename(
            title="Select Unity Package",
            filetypes=[
                ("Unity Package", "*.unitypackage"),
                ("All Files", "*.*"),
            ],
        )
        if path:
            self.package_path = Path(path)
            self.pkg_entry.delete(0, "end")
            self.pkg_entry.insert(0, path)

    def _browse_project(self):
        """Open folder dialog for Godot project selection."""
        path = filedialog.askdirectory(title="Select Godot Project Folder")
        if path:
            self.project_path = Path(path)
            self.proj_entry.delete(0, "end")
            self.proj_entry.insert(0, path)

    def _log(self, message: str):
        """Add a message to the log."""
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self):
        """Clear the log output."""
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _extract_pack_name(self, package_path: Path) -> str:
        """Extract pack name from package filename."""
        name = package_path.stem
        # Remove common prefixes/suffixes
        name = re.sub(r"(?i)^synty[-_\s]*", "", name)
        name = re.sub(r"(?i)[-_\s]*v?\d+(\.\d+)*$", "", name)
        # Clean up
        name = name.replace(" ", "_").replace("-", "_")
        return name or "SyntyPack"

    def _validate_inputs(self) -> bool:
        """Validate user inputs before conversion."""
        # Check package path
        pkg_text = self.pkg_entry.get().strip()
        if not pkg_text:
            messagebox.showerror("Error", "Please select a Unity package file.")
            return False

        self.package_path = Path(pkg_text)
        if not self.package_path.exists():
            messagebox.showerror("Error", f"Package file not found:\n{pkg_text}")
            return False

        if not self.package_path.suffix.lower() == ".unitypackage":
            messagebox.showwarning(
                "Warning", "File doesn't have .unitypackage extension. Continuing anyway..."
            )

        # Check project path
        proj_text = self.proj_entry.get().strip()
        if not proj_text:
            messagebox.showerror("Error", "Please select a Godot project folder.")
            return False

        self.project_path = Path(proj_text)
        if not self.project_path.exists():
            messagebox.showerror("Error", f"Project folder not found:\n{proj_text}")
            return False

        # Check for project.godot
        godot_file = self.project_path / "project.godot"
        if not godot_file.exists():
            result = messagebox.askyesno(
                "Warning",
                "No project.godot found in selected folder.\n\n"
                "This might not be a Godot project. Continue anyway?",
            )
            if not result:
                return False

        return True

    def _start_conversion(self):
        """Start the conversion process."""
        if self.is_converting:
            return

        if not self._validate_inputs():
            return

        self.is_converting = True
        self._clear_log()

        # Update UI
        self.convert_btn.configure(state="disabled", text="Converting...")
        self.progress.grid(row=5, column=0, padx=30, pady=(0, 20), sticky="ew")
        self.progress.start()

        # Run conversion in background thread
        thread = threading.Thread(target=self._run_conversion, daemon=True)
        thread.start()

    def _run_conversion(self):
        """Run the actual conversion (in background thread)."""
        try:
            pack_name = self._extract_pack_name(self.package_path)
            self._log(f"Converting: {pack_name}")
            self._log(f"Package: {self.package_path}")
            self._log(f"Project: {self.project_path}")
            self._log("-" * 50)

            config = ConversionConfig(
                pack_name=pack_name,
                unity_package_path=self.package_path,
                godot_project_path=self.project_path,
                dry_run=self.dry_run_var.get(),
                extract_meshes=self.extract_meshes_var.get(),
                verbose=True,
            )

            converter = SyntyConverter(config)
            summary = converter.convert()

            # Show results
            self._log("-" * 50)
            self._log("Conversion complete!")
            self._log(f"  Materials: {summary['materials']['total']}")
            self._log(f"  Textures: {summary['textures']}")
            self._log(f"  Models: {summary['models']}")

            if summary.get("errors"):
                self._log(f"\nWarnings/Errors: {len(summary['errors'])}")
                for err in summary["errors"][:5]:
                    self._log(f"  - {err}")

            self.after(0, lambda: messagebox.showinfo("Success", "Conversion completed!"))

        except Exception as e:
            self._log(f"\nERROR: {e}")
            self.after(0, lambda: messagebox.showerror("Error", f"Conversion failed:\n{e}"))

        finally:
            self.after(0, self._conversion_finished)

    def _conversion_finished(self):
        """Reset UI after conversion completes."""
        self.is_converting = False
        self.convert_btn.configure(state="normal", text="Convert")
        self.progress.stop()
        self.progress.grid_forget()


def main():
    """Launch the GUI application."""
    app = SyntyConverterGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
