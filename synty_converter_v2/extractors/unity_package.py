"""Unity package (.unitypackage) extractor."""

import tarfile
import gzip
import tempfile
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class TextureInfo:
    """Information about a texture asset."""
    guid: str
    filename: str
    path: str
    extracted_path: Optional[Path] = None


@dataclass
class MaterialInfo:
    """Rich material information extracted from Unity .mat files."""
    name: str
    guid: str
    shader_name: str = ""

    # Texture references (GUID -> property name mapping)
    textures: dict = field(default_factory=dict)  # {property_name: guid}

    # Float properties
    floats: dict = field(default_factory=dict)  # {property_name: value}

    # Color properties
    colors: dict = field(default_factory=dict)  # {property_name: (r, g, b, a)}

    # String tags (e.g., RenderType)
    tags: dict = field(default_factory=dict)

    # Resolved texture paths (populated after GUID resolution)
    resolved_textures: dict = field(default_factory=dict)  # {property_name: filename}

    @property
    def has_emission(self) -> bool:
        """Check if material has emission enabled."""
        return (
            self.floats.get("_Enable_Emission", 0) == 1 or
            "_Emission_Map" in self.textures or
            self._has_non_black_emission_color()
        )

    @property
    def has_foliage_properties(self) -> bool:
        """Check if material has foliage/wind properties."""
        return (
            "_Leaf_Texture" in self.textures or
            "_Trunk_Texture" in self.textures or
            self.floats.get("_Enable_Breeze", 0) == 1 or
            self.floats.get("_Enable_Light_Wind", 0) == 1 or
            self.floats.get("_Wind_Enabled", 0) == 1
        )

    @property
    def is_transparent(self) -> bool:
        """Check if material uses transparent rendering."""
        return self.tags.get("RenderType") == "Transparent"

    def _has_non_black_emission_color(self) -> bool:
        """Check if emission color is not black."""
        color = self.colors.get("_Emission_Color", (0, 0, 0, 1))
        return color[0] > 0 or color[1] > 0 or color[2] > 0


class UnityPackageExtractor:
    """Extract and parse Unity package files."""

    def __init__(self, package_path: Path, extract_dir: Optional[Path] = None):
        self.package_path = Path(package_path)
        self.extract_dir = extract_dir or Path(tempfile.mkdtemp(prefix="unity_pkg_"))

        # GUID -> asset info mappings
        self.guid_to_path: dict[str, str] = {}
        self.materials: dict[str, MaterialInfo] = {}  # name -> MaterialInfo
        self.textures: dict[str, TextureInfo] = {}  # guid -> TextureInfo
        self.fbx_files: list[tuple[str, Path]] = []  # [(original_path, extracted_path)]

    def extract(self) -> Path:
        """Extract the Unity package and parse all assets."""
        logger.info(f"Extracting Unity package: {self.package_path}")

        # Extract the gzipped tar archive
        self._extract_archive()

        # Parse the GUID-based folder structure
        self._parse_guid_structure()

        # Parse all .mat files for material info
        self._parse_materials()

        # Resolve texture GUIDs to filenames
        self._resolve_texture_guids()

        logger.info(f"Found {len(self.materials)} materials, {len(self.textures)} textures, {len(self.fbx_files)} FBX files")

        return self.extract_dir

    def _extract_archive(self):
        """Extract the .unitypackage archive."""
        # .unitypackage is a gzipped tar file
        with gzip.open(self.package_path, 'rb') as gz:
            with tarfile.open(fileobj=gz, mode='r:') as tar:
                tar.extractall(self.extract_dir)

    def _parse_guid_structure(self):
        """Parse the GUID-based folder structure in extracted package."""
        for guid_dir in self.extract_dir.iterdir():
            if not guid_dir.is_dir():
                continue

            guid = guid_dir.name
            pathname_file = guid_dir / "pathname"
            asset_file = guid_dir / "asset"

            if pathname_file.exists():
                path = pathname_file.read_text(encoding='utf-8').strip()
                self.guid_to_path[guid] = path

                # Categorize by file type
                path_lower = path.lower()

                if path_lower.endswith('.mat'):
                    # Material file - will be parsed later
                    pass
                elif path_lower.endswith(('.png', '.tga', '.jpg', '.jpeg', '.psd')):
                    # Texture file
                    self.textures[guid] = TextureInfo(
                        guid=guid,
                        filename=Path(path).name,
                        path=path,
                        extracted_path=asset_file if asset_file.exists() else None
                    )
                elif path_lower.endswith('.fbx'):
                    # FBX model file
                    if asset_file.exists():
                        self.fbx_files.append((path, asset_file))

    def _parse_materials(self):
        """Parse all .mat YAML files for material properties."""
        for guid_dir in self.extract_dir.iterdir():
            if not guid_dir.is_dir():
                continue

            guid = guid_dir.name
            pathname_file = guid_dir / "pathname"
            asset_file = guid_dir / "asset"

            if not pathname_file.exists() or not asset_file.exists():
                continue

            path = pathname_file.read_text(encoding='utf-8').strip()

            if path.lower().endswith('.mat'):
                try:
                    mat_info = self._parse_mat_file(asset_file, guid, path)
                    if mat_info:
                        self.materials[mat_info.name] = mat_info
                except Exception as e:
                    logger.warning(f"Failed to parse material {path}: {e}")

    def _parse_mat_file(self, asset_path: Path, guid: str, original_path: str) -> Optional[MaterialInfo]:
        """Parse a Unity .mat YAML file."""
        content = asset_path.read_text(encoding='utf-8', errors='ignore')

        # Extract material name
        name_match = re.search(r'm_Name:\s*(.+)', content)
        if not name_match:
            return None

        mat_name = name_match.group(1).strip()

        mat_info = MaterialInfo(
            name=mat_name,
            guid=guid
        )

        # Extract shader name if present
        shader_match = re.search(r'm_Shader:\s*{fileID:\s*\d+,\s*guid:\s*([a-f0-9]+)', content)
        if shader_match:
            mat_info.shader_name = shader_match.group(1)

        # Parse m_SavedProperties section
        self._parse_saved_properties(content, mat_info)

        # Parse stringTagMap for RenderType
        self._parse_string_tags(content, mat_info)

        return mat_info

    def _parse_saved_properties(self, content: str, mat_info: MaterialInfo):
        """Parse the m_SavedProperties section of a .mat file."""
        # Parse texture properties (m_TexEnvs)
        tex_pattern = r'-\s*(\w+):\s*\n\s*m_Texture:\s*{fileID:\s*\d+(?:,\s*guid:\s*([a-f0-9]+))?'
        for match in re.finditer(tex_pattern, content):
            prop_name = match.group(1)
            tex_guid = match.group(2)
            if tex_guid:
                mat_info.textures[prop_name] = tex_guid

        # Parse float properties (m_Floats)
        float_pattern = r'-\s*(\w+):\s*([-\d.]+)'
        floats_section = re.search(r'm_Floats:(.*?)(?=m_Colors:|$)', content, re.DOTALL)
        if floats_section:
            for match in re.finditer(float_pattern, floats_section.group(1)):
                prop_name = match.group(1)
                try:
                    value = float(match.group(2))
                    mat_info.floats[prop_name] = value
                except ValueError:
                    pass

        # Parse color properties (m_Colors)
        color_pattern = r'-\s*(\w+):\s*{r:\s*([-\d.]+),\s*g:\s*([-\d.]+),\s*b:\s*([-\d.]+),\s*a:\s*([-\d.]+)}'
        for match in re.finditer(color_pattern, content):
            prop_name = match.group(1)
            try:
                color = (
                    float(match.group(2)),
                    float(match.group(3)),
                    float(match.group(4)),
                    float(match.group(5))
                )
                mat_info.colors[prop_name] = color
            except ValueError:
                pass

    def _parse_string_tags(self, content: str, mat_info: MaterialInfo):
        """Parse stringTagMap for render type and other tags."""
        # Look for stringTagMap section
        tags_match = re.search(r'stringTagMap:\s*\n((?:\s+\w+:\s*.+\n)*)', content)
        if tags_match:
            tags_content = tags_match.group(1)
            for line in tags_content.split('\n'):
                tag_match = re.match(r'\s*(\w+):\s*(.+)', line)
                if tag_match:
                    mat_info.tags[tag_match.group(1)] = tag_match.group(2).strip()

    def _resolve_texture_guids(self):
        """Resolve texture GUIDs in materials to actual filenames."""
        for mat_info in self.materials.values():
            for prop_name, tex_guid in mat_info.textures.items():
                if tex_guid in self.textures:
                    mat_info.resolved_textures[prop_name] = self.textures[tex_guid].filename

    def get_texture_path(self, guid: str) -> Optional[Path]:
        """Get the extracted path for a texture by GUID."""
        if guid in self.textures:
            return self.textures[guid].extracted_path
        return None

    def get_material_for_name(self, name: str) -> Optional[MaterialInfo]:
        """Get material info by name (case-insensitive fuzzy match)."""
        # Exact match first
        if name in self.materials:
            return self.materials[name]

        # Case-insensitive match
        name_lower = name.lower()
        for mat_name, mat_info in self.materials.items():
            if mat_name.lower() == name_lower:
                return mat_info

        # Partial match (material name contains the search name or vice versa)
        for mat_name, mat_info in self.materials.items():
            if name_lower in mat_name.lower() or mat_name.lower() in name_lower:
                return mat_info

        return None

    def cleanup(self):
        """Remove extracted files."""
        import shutil
        if self.extract_dir.exists():
            shutil.rmtree(self.extract_dir)
