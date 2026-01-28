"""Texture file copying and matching utilities."""

import shutil
import re
from pathlib import Path
from typing import Optional
import logging

from ..config import ConversionConfig, TEXTURE_PATTERNS
from ..extractors.unity_package import UnityPackageExtractor, TextureInfo

logger = logging.getLogger(__name__)


class TextureCopier:
    """Copy and match textures from source to Godot project."""

    def __init__(self, config: ConversionConfig):
        self.config = config
        self.copied_textures: dict[str, Path] = {}  # original name -> copied path

    def copy_from_directory(self, source_dir: Path) -> dict[str, Path]:
        """
        Copy all texture files from a source directory.

        Args:
            source_dir: Directory containing texture files

        Returns:
            Dict mapping original filename to copied path
        """
        if not source_dir.exists():
            logger.warning(f"Texture source directory not found: {source_dir}")
            return {}

        texture_extensions = {'.png', '.tga', '.jpg', '.jpeg', '.bmp', '.psd'}

        for file_path in source_dir.rglob('*'):
            if file_path.suffix.lower() in texture_extensions:
                self._copy_texture(file_path)

        logger.info(f"Copied {len(self.copied_textures)} textures from {source_dir}")
        return self.copied_textures

    def copy_from_unity_package(self, extractor: UnityPackageExtractor) -> dict[str, Path]:
        """
        Copy textures extracted from a Unity package.

        Args:
            extractor: Unity package extractor with parsed textures

        Returns:
            Dict mapping original filename to copied path
        """
        for guid, tex_info in extractor.textures.items():
            if tex_info.extracted_path and tex_info.extracted_path.exists():
                dest_name = tex_info.filename
                dest_path = self.config.textures_dir / dest_name

                if not self.config.dry_run:
                    self.config.textures_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(tex_info.extracted_path, dest_path)

                self.copied_textures[tex_info.filename] = dest_path
                logger.debug(f"Copied texture: {tex_info.filename}")

        logger.info(f"Copied {len(self.copied_textures)} textures from Unity package")
        return self.copied_textures

    def _copy_texture(self, source_path: Path) -> Optional[Path]:
        """Copy a single texture file."""
        dest_path = self.config.textures_dir / source_path.name

        # Handle duplicates by checking content or adding suffix
        if dest_path.exists():
            if self._files_identical(source_path, dest_path):
                logger.debug(f"Texture already exists (identical): {source_path.name}")
                self.copied_textures[source_path.name] = dest_path
                return dest_path
            else:
                # Add suffix to avoid overwrite
                stem = source_path.stem
                suffix = source_path.suffix
                counter = 1
                while dest_path.exists():
                    dest_path = self.config.textures_dir / f"{stem}_{counter}{suffix}"
                    counter += 1

        if not self.config.dry_run:
            self.config.textures_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, dest_path)

        self.copied_textures[source_path.name] = dest_path
        logger.debug(f"Copied texture: {source_path.name} -> {dest_path.name}")
        return dest_path

    def _files_identical(self, path1: Path, path2: Path) -> bool:
        """Check if two files have identical content."""
        if path1.stat().st_size != path2.stat().st_size:
            return False

        # Compare first and last 1KB for quick check
        with open(path1, 'rb') as f1, open(path2, 'rb') as f2:
            if f1.read(1024) != f2.read(1024):
                return False
            f1.seek(-1024, 2)
            f2.seek(-1024, 2)
            if f1.read() != f2.read():
                return False

        return True

    def find_texture_for_material(
        self,
        material_name: str,
        texture_type: str = "albedo"
    ) -> Optional[str]:
        """
        Find a matching texture for a material using fuzzy matching.

        Args:
            material_name: Name of the material
            texture_type: Type of texture to find (albedo, normal, emission, etc.)

        Returns:
            Filename of matching texture, or None if not found
        """
        patterns = TEXTURE_PATTERNS.get(texture_type, TEXTURE_PATTERNS["albedo"])

        # Extract base name from material (remove common prefixes/suffixes)
        base_name = self._extract_base_name(material_name)

        # Try to find matching texture
        for tex_name in self.copied_textures.keys():
            tex_base = Path(tex_name).stem.lower()

            # Check if base names match and texture has correct type suffix
            if self._names_match(base_name, tex_base):
                for pattern in patterns:
                    if pattern.lower() in tex_base.lower():
                        return tex_name

        # Fallback: just match base name for albedo
        if texture_type == "albedo":
            for tex_name in self.copied_textures.keys():
                tex_base = Path(tex_name).stem.lower()
                if self._names_match(base_name, tex_base):
                    # Exclude textures that are clearly other types
                    is_other_type = any(
                        p.lower() in tex_base
                        for patterns_list in TEXTURE_PATTERNS.values()
                        if patterns_list != TEXTURE_PATTERNS["albedo"]
                        for p in patterns_list
                    )
                    if not is_other_type:
                        return tex_name

        return None

    def _extract_base_name(self, material_name: str) -> str:
        """Extract base name from material name for matching."""
        name = material_name.lower()

        # Remove common prefixes
        prefixes = ['polygon', 'mat_', 'm_', 'material_']
        for prefix in prefixes:
            if name.startswith(prefix):
                name = name[len(prefix):]

        # Remove common suffixes
        suffixes = ['_mat', '_material', '_01', '_02', '_a', '_b']
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[:-len(suffix)]

        return name

    def _names_match(self, name1: str, name2: str) -> bool:
        """Check if two names match (fuzzy)."""
        # Normalize both names
        n1 = re.sub(r'[_\-\s]', '', name1.lower())
        n2 = re.sub(r'[_\-\s]', '', name2.lower())

        # Exact match
        if n1 == n2:
            return True

        # One contains the other
        if n1 in n2 or n2 in n1:
            return True

        # High similarity (simple check)
        # Count matching characters in order
        matches = 0
        j = 0
        for char in n1:
            while j < len(n2):
                if n2[j] == char:
                    matches += 1
                    j += 1
                    break
                j += 1

        similarity = matches / max(len(n1), len(n2))
        return similarity > 0.7

    def get_texture_res_path(self, filename: str) -> str:
        """Get the res:// path for a texture filename."""
        textures_rel = self.config.textures_dir.relative_to(self.config.godot_project_path)
        return f"res://{textures_rel.as_posix()}/{filename}"

    def build_texture_map(self, material_name: str) -> dict[str, str]:
        """
        Build a complete texture map for a material.

        Returns dict with texture types as keys and filenames as values.
        """
        texture_map = {}

        for tex_type in TEXTURE_PATTERNS.keys():
            tex_file = self.find_texture_for_material(material_name, tex_type)
            if tex_file:
                texture_map[tex_type] = tex_file

        return texture_map
