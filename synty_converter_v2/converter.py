"""Main converter orchestration module."""

import shutil
from pathlib import Path
from typing import Optional
import logging

from .config import ConversionConfig, MaterialType, SHADER_FILES
from .extractors import UnityPackageExtractor, FBXExtractor
from .classifiers import MaterialClassifier
from .generators import MaterialGenerator, ImportFileGenerator
from .copiers import TextureCopier
from .matchers import MaterialMatcher

logger = logging.getLogger(__name__)


class SyntyConverter:
    """Main orchestrator for Synty asset conversion."""

    def __init__(self, config: ConversionConfig):
        self.config = config
        self.classifier = MaterialClassifier()
        self.material_generator = MaterialGenerator(config)
        self.import_generator = ImportFileGenerator(config)
        self.texture_copier = TextureCopier(config)
        self.fbx_extractor = FBXExtractor()

        # Extracted data
        self.unity_extractor: Optional[UnityPackageExtractor] = None
        self.unity_materials: dict[str, any] = {}  # Unity material name -> MaterialInfo
        self.material_classifications: dict[str, MaterialType] = {}  # name -> type
        self.fbx_materials: dict[str, list[str]] = {}  # FBX name -> list of material names
        self.material_matches: dict[str, str] = {}  # FBX mat name -> Unity mat name
        self.generated_materials: dict[str, Path] = {}  # FBX mat name -> .tres path

    def convert(self) -> dict:
        """Run the full conversion pipeline."""
        logger.info(f"Starting conversion for pack: {self.config.pack_name}")
        logger.info(f"Output directory: {self.config.output_base}")

        summary = {
            "pack_name": self.config.pack_name,
            "materials": {"total": 0, "by_type": {}, "matched": 0, "unmatched": 0},
            "textures": 0,
            "models": 0,
            "meshes": 0,
            "material_source": "unknown",  # "meta_files", "blender", or "unity_names_only"
            "blender_available": False,  # Kept for backward compatibility
            "errors": []
        }

        try:
            # Step 1: Create output directories
            self._create_directories()

            # Step 2: Extract Unity package
            if self.config.unity_package_path:
                self._extract_unity_package()

            # Step 3: Copy textures
            self._copy_textures()
            summary["textures"] = len(self.texture_copier.copied_textures)

            # Step 4: Get FBX material names from .meta files (PRIMARY source)
            meta_fbx_materials = self._get_fbx_materials_from_meta()
            has_meta_mappings = bool(meta_fbx_materials)

            if has_meta_mappings:
                # Use .meta file data - no Blender needed!
                logger.info(f"Found {len(meta_fbx_materials)} FBX files with material mappings from .meta files")
                self.fbx_materials = meta_fbx_materials
                summary["material_source"] = "meta_files"
            else:
                # Step 5: Fallback to Blender if .meta files unavailable
                blender_available = self.fbx_extractor.is_available()
                summary["blender_available"] = blender_available

                if blender_available:
                    logger.info("No .meta mappings found - using Blender for FBX analysis (fallback)")
                    self._analyze_fbx_files()
                    summary["material_source"] = "blender"
                else:
                    logger.warning("No .meta mappings and Blender not available - using Unity material names")
                    summary["material_source"] = "unity_names_only"

            # Step 6: Classify Unity materials by type
            self._classify_unity_materials()

            # Step 7: Match FBX materials to Unity materials
            use_fbx_names = bool(self.fbx_materials)
            if self.fbx_materials:
                self._match_materials()
                summary["materials"]["matched"] = len([m for m in self.material_matches.values() if m])
                summary["materials"]["unmatched"] = len([m for m in self.material_matches.values() if not m])

            # Step 8: Generate material files
            self._generate_materials(use_fbx_names=use_fbx_names)
            summary["materials"]["total"] = len(self.generated_materials)
            summary["materials"]["by_type"] = self._get_type_counts()

            # Step 9: Copy FBX files and generate import configs
            model_count, mesh_count = self._process_models(use_fbx_names=use_fbx_names)
            summary["models"] = model_count
            summary["meshes"] = mesh_count

            # Step 10: Install shaders if needed
            self._ensure_shaders()

            logger.info(f"Conversion complete: {summary}")

        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            summary["errors"].append(str(e))
            raise

        finally:
            if self.unity_extractor:
                self.unity_extractor.cleanup()

        return summary

    def _create_directories(self):
        """Create output directory structure."""
        if self.config.dry_run:
            logger.info("[DRY RUN] Would create directories")
            return

        dirs = [
            self.config.materials_dir,
            self.config.textures_dir,
            self.config.models_dir,
            self.config.meshes_dir,
            self.config.shaders_dir,
        ]

        for category in ["Buildings", "Characters", "Environment", "Props", "Vehicles", "FX"]:
            dirs.append(self.config.models_dir / category)

        for dir_path in dirs:
            dir_path.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Created directory: {dir_path}")

    def _extract_unity_package(self):
        """Extract and parse Unity package."""
        if not self.config.unity_package_path:
            return

        logger.info(f"Extracting Unity package: {self.config.unity_package_path}")
        self.unity_extractor = UnityPackageExtractor(self.config.unity_package_path)
        self.unity_extractor.extract()

        self.unity_materials = self.unity_extractor.materials

        logger.info(f"Found {len(self.unity_materials)} materials in package")
        logger.info(f"Found {len(self.unity_extractor.textures)} textures in package")
        logger.info(f"Found {len(self.unity_extractor.fbx_files)} FBX files in package")

    def _copy_textures(self):
        """Copy textures from all sources."""
        if self.unity_extractor:
            self.texture_copier.copy_from_unity_package(self.unity_extractor)

        if self.config.source_textures_dir:
            self.texture_copier.copy_from_directory(self.config.source_textures_dir)

    def _get_fbx_materials_from_meta(self) -> dict[str, list[str]]:
        """Extract FBX material names from .meta file mappings.

        The fbx_material_mappings dict has structure:
            {fbx_filename: {fbx_mat_name: unity_guid}}

        We extract the fbx_mat_name keys as the material list.
        This is the PRIMARY source - no Blender needed!
        """
        result = {}
        if self.unity_extractor:
            for fbx_name, mappings in self.unity_extractor.fbx_material_mappings.items():
                result[fbx_name] = list(mappings.keys())
        return result

    def _analyze_fbx_files(self):
        """Analyze FBX files to extract actual material names.

        NOTE: This is a FALLBACK method using Blender. The primary source
        for FBX material names is the .meta files (see _get_fbx_materials_from_meta).
        """
        fbx_paths = []

        # Collect FBX paths
        if self.unity_extractor:
            for original_path, extracted_path in self.unity_extractor.fbx_files:
                fbx_paths.append(extracted_path)

        if self.config.source_fbx_dir and self.config.source_fbx_dir.exists():
            fbx_paths.extend(self.config.source_fbx_dir.rglob("*.fbx"))
            fbx_paths.extend(self.config.source_fbx_dir.rglob("*.FBX"))

        if not fbx_paths:
            return

        logger.info(f"Analyzing {len(fbx_paths)} FBX files with Blender...")

        all_fbx_materials = set()

        for i, fbx_path in enumerate(fbx_paths):
            fbx_path = Path(fbx_path)
            logger.debug(f"Analyzing {fbx_path.name} ({i+1}/{len(fbx_paths)})")

            info = self.fbx_extractor.analyze(fbx_path)
            if info:
                self.fbx_materials[fbx_path.stem] = info.materials
                all_fbx_materials.update(info.materials)
                logger.debug(f"  Materials: {info.materials}")

        logger.info(f"Found {len(all_fbx_materials)} unique material names in FBX files")

    def _classify_unity_materials(self):
        """Classify Unity materials by type."""
        for name, mat_info in self.unity_materials.items():
            mat_type = self.classifier.classify(name, mat_info)
            self.material_classifications[name] = mat_type
            logger.debug(f"Classified {name} as {mat_type.name}")

        summary = self.classifier.get_summary(self.material_classifications)
        for mat_type, names in summary.items():
            logger.info(f"  {mat_type.name}: {len(names)} materials")

    def _match_materials(self):
        """Match FBX material names to Unity material names.

        Uses a two-phase approach:
        1. First, try exact GUID matching from FBX .meta files (most reliable)
        2. Fall back to fuzzy name matching for any remaining materials
        """
        # Get all unique FBX material names
        all_fbx_names = set()
        for materials in self.fbx_materials.values():
            all_fbx_names.update(materials)

        # Filter out invalid/metadata names
        all_fbx_names = {
            name for name in all_fbx_names
            if not name.startswith('m_') and ':' not in name
        }

        logger.info(f"Matching {len(all_fbx_names)} FBX materials to {len(self.unity_materials)} Unity materials...")

        # Create matcher with GUID lookup capability
        materials_by_guid = {}
        if self.unity_extractor:
            materials_by_guid = self.unity_extractor.materials_by_guid

        matcher = MaterialMatcher(self.unity_materials, materials_by_guid)

        # Track statistics
        guid_matched = 0
        fuzzy_matched = 0
        unmatched = 0
        all_matches = {}

        # Phase 1: Try exact GUID matching per FBX file
        fbx_material_mappings = {}
        if self.unity_extractor:
            fbx_material_mappings = self.unity_extractor.fbx_material_mappings

        # Build a combined mapping of all FBX materials to their Unity GUIDs
        combined_guid_mappings = {}
        for fbx_name, mappings in fbx_material_mappings.items():
            combined_guid_mappings.update(mappings)

        if combined_guid_mappings:
            logger.info(f"Found {len(combined_guid_mappings)} exact material mappings from FBX .meta files")

        # Match each FBX material
        for fbx_mat_name in all_fbx_names:
            # First try exact GUID match
            if fbx_mat_name in combined_guid_mappings:
                unity_guid = combined_guid_mappings[fbx_mat_name]
                guid_match = matcher.match_by_guid(fbx_mat_name, unity_guid)
                if guid_match:
                    self.material_matches[fbx_mat_name] = guid_match.unity_name
                    all_matches[fbx_mat_name] = guid_match
                    guid_matched += 1
                    logger.debug(f"  {fbx_mat_name} -> {guid_match.unity_name} (GUID match)")
                    continue

            # Fall back to fuzzy matching
            match = matcher.match(fbx_mat_name)
            all_matches[fbx_mat_name] = match

            if match.unity_name:
                self.material_matches[fbx_mat_name] = match.unity_name
                fuzzy_matched += 1
                logger.debug(f"  {fbx_mat_name} -> {match.unity_name} ({match.match_reason}, {match.confidence:.0%})")
            else:
                self.material_matches[fbx_mat_name] = None
                unmatched += 1
                logger.warning(f"  {fbx_mat_name} -> NO MATCH")

        total = len(all_fbx_names)
        matched = guid_matched + fuzzy_matched
        logger.info(f"Material matching complete: {matched}/{total} matched")
        logger.info(f"  - GUID exact matches: {guid_matched}")
        logger.info(f"  - Fuzzy matches: {fuzzy_matched}")
        logger.info(f"  - Unmatched: {unmatched}")

        if unmatched > 0:
            unmatched_names = [name for name, match in all_matches.items() if not match.unity_name]
            logger.warning(f"Unmatched materials: {unmatched_names}")

    def _generate_materials(self, use_fbx_names: bool = False):
        """Generate .tres material files."""
        if use_fbx_names and self.material_matches:
            # Generate materials with FBX names but Unity properties
            self._generate_materials_fbx_mode()
        else:
            # Fallback: generate with Unity names
            self._generate_materials_unity_mode()

        logger.info(f"Generated {len(self.generated_materials)} material files")

    def _generate_materials_fbx_mode(self):
        """Generate materials using FBX names."""
        for fbx_name, unity_name in self.material_matches.items():
            try:
                if unity_name:
                    # Get Unity material info and type
                    mat_info = self.unity_materials.get(unity_name)
                    mat_type = self.material_classifications.get(unity_name, MaterialType.STANDARD)

                    # Build texture map using Unity material
                    texture_map = self._build_texture_map(unity_name, mat_info)
                else:
                    # No match - create a basic standard material
                    mat_info = None
                    mat_type = MaterialType.STANDARD
                    texture_map = {}
                    logger.warning(f"Creating placeholder material for unmatched: {fbx_name}")

                # Generate with FBX name
                output_path = self.material_generator.write_material(
                    fbx_name, mat_type, mat_info, texture_map
                )
                self.generated_materials[fbx_name] = output_path

            except Exception as e:
                logger.error(f"Failed to generate material {fbx_name}: {e}")

    def _generate_materials_unity_mode(self):
        """Generate materials using Unity names (fallback mode)."""
        for mat_name, mat_type in self.material_classifications.items():
            try:
                mat_info = self.unity_materials.get(mat_name)
                texture_map = self._build_texture_map(mat_name, mat_info)

                output_path = self.material_generator.write_material(
                    mat_name, mat_type, mat_info, texture_map
                )
                self.generated_materials[mat_name] = output_path

            except Exception as e:
                logger.error(f"Failed to generate material {mat_name}: {e}")

    def _build_texture_map(self, mat_name: str, mat_info) -> dict:
        """Build texture map for a material."""
        texture_map = self.texture_copier.build_texture_map(mat_name)

        if mat_info and mat_info.resolved_textures:
            for prop, filename in mat_info.resolved_textures.items():
                prop_lower = prop.lower()
                if "albedo" in prop_lower or "maintex" in prop_lower:
                    texture_map.setdefault("albedo", filename)
                elif "leaf" in prop_lower:
                    texture_map.setdefault("leaf", filename)
                elif "trunk" in prop_lower:
                    texture_map.setdefault("trunk", filename)
                elif "emission" in prop_lower:
                    texture_map.setdefault("emission", filename)
                elif "normal" in prop_lower or "bump" in prop_lower:
                    texture_map.setdefault("normal", filename)

        return texture_map

    def _process_models(self, use_fbx_names: bool = False) -> tuple[int, int]:
        """Copy FBX files and generate import configurations."""
        model_count = 0
        mesh_count = 0

        fbx_sources = []

        if self.unity_extractor:
            for original_path, extracted_path in self.unity_extractor.fbx_files:
                fbx_sources.append((Path(original_path).name, extracted_path, Path(original_path).stem))

        if self.config.source_fbx_dir and self.config.source_fbx_dir.exists():
            for fbx_path in self.config.source_fbx_dir.rglob("*.fbx"):
                fbx_sources.append((fbx_path.name, fbx_path, fbx_path.stem))
            for fbx_path in self.config.source_fbx_dir.rglob("*.FBX"):
                fbx_sources.append((fbx_path.name, fbx_path, fbx_path.stem))

        materials_rel = self.config.materials_dir.relative_to(self.config.godot_project_path)

        for fbx_name, source_path, fbx_stem in fbx_sources:
            try:
                category = self.import_generator.categorize_fbx(fbx_name)
                dest_path = self.config.models_dir / category / fbx_name

                if not self.config.dry_run:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_path, dest_path)

                model_count += 1

                # Build material mappings for this specific FBX
                mat_mappings = {}

                if use_fbx_names and fbx_stem in self.fbx_materials:
                    # Use the actual materials from this FBX
                    for mat_name in self.fbx_materials[fbx_stem]:
                        # Skip invalid names
                        if mat_name.startswith('m_') or ':' in mat_name:
                            continue

                        if mat_name in self.generated_materials:
                            tres_path = f"res://{materials_rel.as_posix()}/{mat_name}.tres"
                            # Get the type from matched Unity material
                            unity_name = self.material_matches.get(mat_name)
                            mat_type = self.material_classifications.get(unity_name, MaterialType.STANDARD) if unity_name else MaterialType.STANDARD
                            mat_mappings[mat_name] = (tres_path, mat_type)
                else:
                    # Fallback: map all generated materials
                    for mat_name in self.generated_materials:
                        tres_path = f"res://{materials_rel.as_posix()}/{mat_name}.tres"
                        mat_type = self.material_classifications.get(mat_name, MaterialType.STANDARD)
                        mat_mappings[mat_name] = (tres_path, mat_type)

                mesh_name = fbx_stem
                meshes = [mesh_name]
                mesh_count += 1

                self.import_generator.write_import_file(
                    Path(fbx_name),
                    mat_mappings,
                    meshes,
                    category
                )

            except Exception as e:
                logger.error(f"Failed to process model {fbx_name}: {e}")

        logger.info(f"Processed {model_count} models with {mesh_count} meshes")
        return model_count, mesh_count

    def _ensure_shaders(self):
        """Ensure required shaders exist."""
        required_shaders = set(SHADER_FILES.values())

        for shader_file in required_shaders:
            shader_path = self.config.shaders_dir / shader_file

            if not shader_path.exists() and not self.config.dry_run:
                logger.warning(f"Shader not found: {shader_file}")
                logger.info(f"Please download from godotshaders.com and place in {self.config.shaders_dir}")

    def _get_type_counts(self) -> dict[str, int]:
        """Get counts of materials by type."""
        counts = {}
        for mat_type in MaterialType:
            count = sum(1 for t in self.material_classifications.values() if t == mat_type)
            if count > 0:
                counts[mat_type.name] = count
        return counts


def convert_pack(
    pack_name: str,
    godot_project: Path,
    unity_package: Optional[Path] = None,
    source_fbx_dir: Optional[Path] = None,
    source_textures_dir: Optional[Path] = None,
    dry_run: bool = False,
    verbose: bool = False
) -> dict:
    """Convenience function to convert a Synty pack."""
    config = ConversionConfig(
        pack_name=pack_name,
        godot_project_path=godot_project,
        unity_package_path=unity_package,
        source_fbx_dir=source_fbx_dir,
        source_textures_dir=source_textures_dir,
        dry_run=dry_run,
        verbose=verbose
    )

    converter = SyntyConverter(config)
    return converter.convert()
