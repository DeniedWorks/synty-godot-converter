"""Generate .fbx.import files for Godot."""

import json
from pathlib import Path
from typing import Optional
import logging

from ..config import ConversionConfig, MaterialType

logger = logging.getLogger(__name__)


class ImportFileGenerator:
    """Generate Godot .fbx.import configuration files."""

    def __init__(self, config: ConversionConfig):
        self.config = config

    def generate(
        self,
        fbx_path: Path,
        materials: dict[str, tuple[str, MaterialType]],  # {name: (tres_path, type)}
        meshes: Optional[list[str]] = None,
        category: str = "Props"
    ) -> str:
        """
        Generate .fbx.import file content.

        Args:
            fbx_path: Path to the FBX file (relative to models dir)
            materials: Dict mapping material names to their .tres paths and types
            meshes: Optional list of mesh names to extract
            category: Category subfolder (Buildings, Characters, etc.)

        Returns:
            String content of the .import file
        """
        # Calculate resource path
        models_rel = self.config.models_dir.relative_to(self.config.godot_project_path)
        fbx_res_path = f"res://{models_rel.as_posix()}/{category}/{fbx_path.name}"

        # Build subresources dict
        subresources = self._build_subresources(fbx_path, materials, meshes, category)

        content = self._format_import_file(fbx_res_path, subresources)
        return content

    def _build_subresources(
        self,
        fbx_path: Path,
        materials: dict[str, tuple[str, MaterialType]],
        meshes: Optional[list[str]],
        category: str
    ) -> dict:
        """Build the _subresources dictionary for the import file."""
        subresources = {
            "materials": {},
            "meshes": {},
            "nodes": {}
        }

        # Material mappings
        for mat_name, (tres_path, mat_type) in materials.items():
            subresources["materials"][mat_name] = {
                "use_external/enabled": True,
                "use_external/path": tres_path
            }

        # Mesh extraction mappings
        if meshes and self.config.extract_meshes:
            meshes_rel = self.config.meshes_dir.relative_to(self.config.godot_project_path)

            for mesh_name in meshes:
                safe_name = self._sanitize_name(mesh_name)
                mesh_res_path = f"res://{meshes_rel.as_posix()}/{safe_name}.res"

                subresources["meshes"][mesh_name] = {
                    "save_to_file/enabled": True,
                    "save_to_file/path": mesh_res_path
                }

        # Remove empty sections
        subresources = {k: v for k, v in subresources.items() if v}

        return subresources

    def _format_import_file(self, fbx_res_path: str, subresources: dict) -> str:
        """Format the complete .import file content."""
        # Generate UID (simple hash-based approach)
        import hashlib
        uid_hash = hashlib.md5(fbx_res_path.encode()).hexdigest()[:12]
        uid = f"uid://{uid_hash}"

        lines = [
            "[remap]",
            "",
            f'importer="scene"',
            f'importer_version=1',
            f'type="PackedScene"',
            f'uid="{uid}"',
            f'path="{fbx_res_path.replace(".fbx", ".scn")}"',
            "",
            "[deps]",
            "",
            f'source_file="{fbx_res_path}"',
            f'dest_files=["{fbx_res_path.replace(".fbx", ".scn")}"]',
            "",
            "[params]",
            "",
        ]

        # FBX import parameters for Godot 4.x (uses ufbx internally)
        params = {
            "nodes/root_type": "",
            "nodes/root_name": "",
            "nodes/apply_root_scale": True,
            "nodes/root_scale": 1.0,
            "meshes/ensure_tangents": True,
            "meshes/generate_lods": True,
            "meshes/create_shadow_meshes": True,
            "meshes/light_baking": 1,
            "meshes/lightmap_texel_size": 0.2,
            "meshes/force_disable_compression": False,
            "skins/use_named_skins": True,
            "animation/import": True,
            "animation/fps": 30,
            "animation/trimming": False,
            "animation/remove_immutable_tracks": True,
            "import_script/path": "",
            "fbx/importer": 0,  # 0 = ufbx (native), 1 = FBX2glTF
            "fbx/allow_geometry_helper_nodes": False,
            "fbx/embedded_image_handling": 1,
        }

        for key, value in params.items():
            if isinstance(value, bool):
                lines.append(f'{key}={str(value).lower()}')
            elif isinstance(value, str):
                lines.append(f'{key}="{value}"')
            else:
                lines.append(f'{key}={value}')

        # Add _subresources with proper formatting
        if subresources:
            lines.append(f'_subresources={self._format_subresources(subresources)}')

        return '\n'.join(lines)

    def _format_subresources(self, subresources: dict) -> str:
        """Format subresources dict in Godot's specific format."""
        # Godot uses a specific format for nested dicts
        # {
        #   "materials": {
        #     "MaterialName": { "use_external/enabled": true, "use_external/path": "..." }
        #   }
        # }

        def format_value(v):
            if isinstance(v, bool):
                return "true" if v else "false"
            elif isinstance(v, str):
                return f'"{v}"'
            elif isinstance(v, (int, float)):
                return str(v)
            elif isinstance(v, dict):
                items = ", ".join(f'"{k}": {format_value(val)}' for k, val in v.items())
                return "{" + items + "}"
            return str(v)

        parts = []
        for section, items in subresources.items():
            if not items:
                continue
            section_parts = []
            for name, props in items.items():
                props_str = format_value(props)
                section_parts.append(f'"{name}": {props_str}')

            parts.append(f'"{section}": {{{", ".join(section_parts)}}}')

        return "{" + ", ".join(parts) + "}"

    def write_import_file(
        self,
        fbx_path: Path,
        materials: dict[str, tuple[str, MaterialType]],
        meshes: Optional[list[str]] = None,
        category: str = "Props"
    ) -> Path:
        """Generate and write an .import file for an FBX."""
        content = self.generate(fbx_path, materials, meshes, category)

        # Import file goes next to the FBX
        output_dir = self.config.models_dir / category
        import_path = output_dir / f"{fbx_path.name}.import"

        if not self.config.dry_run:
            output_dir.mkdir(parents=True, exist_ok=True)
            import_path.write_text(content, encoding='utf-8')
            logger.info(f"Wrote import file: {import_path}")
        else:
            logger.info(f"[DRY RUN] Would write import file: {import_path}")

        return import_path

    def _sanitize_name(self, name: str) -> str:
        """Sanitize a name for use in paths."""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '_')
        return name

    def categorize_fbx(self, fbx_name: str) -> str:
        """Determine the category for an FBX based on naming conventions."""
        from ..config import FBX_CATEGORIES

        name_upper = fbx_name.upper()

        for category, patterns in FBX_CATEGORIES.items():
            for pattern in patterns:
                if pattern.upper() in name_upper:
                    return category

        # Default category
        return "Props"
