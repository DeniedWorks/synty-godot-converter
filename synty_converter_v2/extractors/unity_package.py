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
class FBXMaterialMapping:
    """Material mapping information from an FBX .meta file."""
    fbx_name: str  # Name of the FBX file (without extension)
    fbx_guid: str  # GUID of the FBX asset
    # Maps FBX material name -> Unity material GUID
    material_mappings: dict[str, str] = field(default_factory=dict)


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
        self.materials_by_guid: dict[str, MaterialInfo] = {}  # guid -> MaterialInfo
        self.textures: dict[str, TextureInfo] = {}  # guid -> TextureInfo
        self.fbx_files: list[tuple[str, Path]] = []  # [(original_path, extracted_path)]
        # FBX material mappings from .meta files
        # Key: FBX filename (without extension)
        # Value: dict mapping FBX material name -> Unity material GUID
        self.fbx_material_mappings: dict[str, dict[str, str]] = {}

    def extract(self) -> Path:
        """Extract the Unity package and parse all assets."""
        logger.info(f"Extracting Unity package: {self.package_path}")

        # Extract the gzipped tar archive
        self._extract_archive()

        # Parse the GUID-based folder structure
        self._parse_guid_structure()

        # Parse all .mat files for material info
        self._parse_materials()

        # Parse FBX .meta files for material mappings
        self._parse_fbx_meta_files()

        # Resolve texture GUIDs to filenames
        self._resolve_texture_guids()

        logger.info(f"Found {len(self.materials)} materials, {len(self.textures)} textures, {len(self.fbx_files)} FBX files")
        logger.info(f"Found {len(self.fbx_material_mappings)} FBX files with material mappings")

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
                        self.materials_by_guid[guid] = mat_info
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

    def _parse_fbx_meta_files(self):
        """Parse FBX .meta files to extract material mappings.

        Unity FBX .meta files contain an externalObjects section that maps
        FBX material names to Unity material GUIDs:

        externalObjects:
          - first:
              type: UnityEngine:Material
              name: MAT_01A              # FBX material name
            second: {guid: abc123def456}  # Unity material GUID
        """
        for guid_dir in self.extract_dir.iterdir():
            if not guid_dir.is_dir():
                continue

            guid = guid_dir.name
            pathname_file = guid_dir / "pathname"
            meta_file = guid_dir / "asset.meta"

            if not pathname_file.exists():
                continue

            path = pathname_file.read_text(encoding='utf-8').strip()

            # Only process FBX .meta files
            if not path.lower().endswith('.fbx'):
                continue

            if not meta_file.exists():
                continue

            try:
                fbx_name = Path(path).stem
                mappings = self._parse_fbx_meta_content(meta_file)

                if mappings:
                    self.fbx_material_mappings[fbx_name] = mappings
                    logger.debug(f"Parsed {len(mappings)} material mappings from {fbx_name}.fbx.meta")

            except Exception as e:
                logger.warning(f"Failed to parse FBX meta file for {path}: {e}")

    def _parse_fbx_meta_content(self, meta_file: Path) -> dict[str, str]:
        """Parse the externalObjects section from an FBX .meta file.

        Returns:
            dict mapping FBX material name -> Unity material GUID
        """
        content = meta_file.read_text(encoding='utf-8', errors='ignore')
        mappings = {}

        # The externalObjects section contains entries like:
        # - first:
        #     type: UnityEngine:Material
        #     name: MAT_01A
        #   second: {fileID: 2100000, guid: abc123def456, type: 2}
        #
        # We need to find Material type entries and extract name + guid

        # Pattern to match each externalObjects entry
        # This handles the YAML-like format (not strict YAML)
        entry_pattern = re.compile(
            r'-\s*first:\s*\n'
            r'\s*type:\s*UnityEngine:Material\s*\n'
            r'\s*(?:assembly:\s*\S+\s*\n)?'  # Optional assembly line
            r'\s*name:\s*([^\n]+)\s*\n'
            r'\s*second:\s*\{[^}]*guid:\s*([a-f0-9]+)',
            re.MULTILINE | re.IGNORECASE
        )

        for match in entry_pattern.finditer(content):
            mat_name = match.group(1).strip()
            mat_guid = match.group(2).strip()
            mappings[mat_name] = mat_guid
            logger.debug(f"  Found mapping: {mat_name} -> {mat_guid}")

        return mappings

    def get_material_by_guid(self, guid: str) -> Optional[MaterialInfo]:
        """Get material info by GUID."""
        return self.materials_by_guid.get(guid)

    def get_fbx_material_mapping(self, fbx_name: str) -> Optional[dict[str, str]]:
        """Get material mappings for an FBX file.

        Args:
            fbx_name: FBX filename without extension

        Returns:
            dict mapping FBX material name -> Unity material GUID, or None
        """
        return self.fbx_material_mappings.get(fbx_name)

    def get_all_fbx_material_names(self) -> set[str]:
        """Get all unique FBX material names from .meta file mappings.

        This is the primary source of FBX material names - no Blender needed!
        The externalObjects section in FBX .meta files contains the exact
        material names as they appear in the FBX file.

        Returns:
            Set of all FBX material names found in externalObjects sections.
        """
        all_names = set()
        for mappings in self.fbx_material_mappings.values():
            all_names.update(mappings.keys())
        return all_names

    def get_fbx_materials_dict(self) -> dict[str, list[str]]:
        """Get FBX material names organized by FBX file.

        Returns:
            Dict mapping FBX filename (without extension) to list of material names.
        """
        return {fbx: list(mappings.keys())
                for fbx, mappings in self.fbx_material_mappings.items()}

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
