"""Main converter orchestration module."""

import shutil
from pathlib import Path
from typing import Optional
import logging

from .config import ConversionConfig, MaterialType, SHADER_FILES
from .extractors import UnityPackageExtractor
from .classifiers import MaterialClassifier
from .generators import MaterialGenerator, ImportFileGenerator
from .copiers import TextureCopier

logger = logging.getLogger(__name__)


class SyntyConverter:
    """Main orchestrator for Synty asset conversion."""

    def __init__(self, config: ConversionConfig):
        self.config = config
        self.classifier = MaterialClassifier()
        self.material_generator = MaterialGenerator(config)
        self.import_generator = ImportFileGenerator(config)
        self.texture_copier = TextureCopier(config)

        # Extracted data
        self.unity_extractor: Optional[UnityPackageExtractor] = None
        self.material_classifications: dict[str, MaterialType] = {}
        self.generated_materials: dict[str, Path] = {}  # name -> .tres path

    def convert(self) -> dict:
        """
        Run the full conversion pipeline.

        Returns:
            Summary dict with conversion statistics
        """
        logger.info(f"Starting conversion for pack: {self.config.pack_name}")
        logger.info(f"Output directory: {self.config.output_base}")

        summary = {
            "pack_name": self.config.pack_name,
            "materials": {"total": 0, "by_type": {}},
            "textures": 0,
            "models": 0,
            "meshes": 0,
            "errors": []
        }

        try:
            # Step 1: Create output directories
            self._create_directories()

            # Step 2: Extract Unity package if provided
            if self.config.unity_package_path:
                self._extract_unity_package()

            # Step 3: Copy textures
            self._copy_textures()
            summary["textures"] = len(self.texture_copier.copied_textures)

            # Step 4: Collect and classify materials
            self._classify_materials()
            summary["materials"]["total"] = len(self.material_classifications)
            summary["materials"]["by_type"] = self._get_type_counts()

            # Step 5: Generate material files
            self._generate_materials()

            # Step 6: Copy FBX files and generate import configs
            model_count, mesh_count = self._process_models()
            summary["models"] = model_count
            summary["meshes"] = mesh_count

            # Step 7: Install shaders if needed
            self._ensure_shaders()

            logger.info(f"Conversion complete: {summary}")

        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            summary["errors"].append(str(e))
            raise

        finally:
            # Cleanup temporary files
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

        # Model subcategories
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

        logger.info(f"Found {len(self.unity_extractor.materials)} materials in package")
        logger.info(f"Found {len(self.unity_extractor.textures)} textures in package")
        logger.info(f"Found {len(self.unity_extractor.fbx_files)} FBX files in package")

    def _copy_textures(self):
        """Copy textures from all sources."""
        # From Unity package
        if self.unity_extractor:
            self.texture_copier.copy_from_unity_package(self.unity_extractor)

        # From source directory
        if self.config.source_textures_dir:
            self.texture_copier.copy_from_directory(self.config.source_textures_dir)

    def _classify_materials(self):
        """Classify all materials by type."""
        material_names = set()

        # From Unity package
        if self.unity_extractor:
            material_names.update(self.unity_extractor.materials.keys())

        # If no Unity package, we need to discover materials from FBX files
        # This would require FBX analysis which is more complex

        # Classify each material
        for name in material_names:
            mat_info = None
            if self.unity_extractor:
                mat_info = self.unity_extractor.materials.get(name)

            mat_type = self.classifier.classify(name, mat_info)
            self.material_classifications[name] = mat_type
            logger.debug(f"Classified {name} as {mat_type.name}")

        # Log summary
        summary = self.classifier.get_summary(self.material_classifications)
        for mat_type, names in summary.items():
            logger.info(f"  {mat_type.name}: {len(names)} materials")

    def _generate_materials(self):
        """Generate .tres material files using FBX material names.

        The key insight: Godot's FBX importer looks for materials by the name
        used IN the FBX file. Unity's .meta files tell us exactly what those
        names are (in externalObjects), mapped to Unity material GUIDs.

        So we generate: FBX_material_name.tres with Unity material properties.
        """
        # Get FBX material name -> Unity GUID mappings from .meta files
        if self.unity_extractor and self.unity_extractor.fbx_material_mappings:
            # Use FBX material names (the correct approach)
            self._generate_materials_from_meta()
        else:
            # Fallback: use Unity names directly (won't match FBX imports)
            self._generate_materials_unity_names()

    def _generate_materials_from_meta(self):
        """Generate materials using FBX names from .meta files."""
        generated = set()

        for fbx_name, mappings in self.unity_extractor.fbx_material_mappings.items():
            for fbx_mat_name, unity_guid in mappings.items():
                # Skip if already generated (same mat name in multiple FBXs)
                if fbx_mat_name in generated:
                    continue

                try:
                    # Get Unity material info by GUID
                    mat_info = self.unity_extractor.materials_by_guid.get(unity_guid)

                    if mat_info:
                        # Classify based on Unity material
                        mat_type = self.classifier.classify(mat_info.name, mat_info)

                        # Build texture map
                        texture_map = self.texture_copier.build_texture_map(mat_info.name)
                        if mat_info.resolved_textures:
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
                    else:
                        # GUID not found - create basic material
                        mat_type = MaterialType.STANDARD
                        texture_map = {}
                        logger.warning(f"No Unity material for GUID {unity_guid}, creating basic: {fbx_mat_name}")

                    # Generate with FBX material name (what Godot expects!)
                    output_path = self.material_generator.write_material(
                        fbx_mat_name, mat_type, mat_info, texture_map
                    )
                    self.generated_materials[fbx_mat_name] = output_path
                    self.material_classifications[fbx_mat_name] = mat_type  # Store type under FBX name
                    generated.add(fbx_mat_name)

                    logger.debug(f"Generated {fbx_mat_name}.tres from Unity material {mat_info.name if mat_info else 'unknown'}")

                except Exception as e:
                    logger.error(f"Failed to generate material {fbx_mat_name}: {e}")

        logger.info(f"Generated {len(self.generated_materials)} material files (using FBX names from .meta)")

    def _generate_materials_unity_names(self):
        """Fallback: Generate materials using Unity names."""
        for mat_name, mat_type in self.material_classifications.items():
            try:
                mat_info = None
                if self.unity_extractor:
                    mat_info = self.unity_extractor.materials.get(mat_name)

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

                output_path = self.material_generator.write_material(
                    mat_name, mat_type, mat_info, texture_map
                )
                self.generated_materials[mat_name] = output_path

            except Exception as e:
                logger.error(f"Failed to generate material {mat_name}: {e}")

        logger.info(f"Generated {len(self.generated_materials)} material files (using Unity names)")

    def _process_models(self) -> tuple[int, int]:
        """Copy FBX files and generate import configurations."""
        model_count = 0
        mesh_count = 0

        fbx_sources = []

        # From Unity package
        if self.unity_extractor:
            for original_path, extracted_path in self.unity_extractor.fbx_files:
                fbx_sources.append((Path(original_path).name, extracted_path))

        # From source directory
        if self.config.source_fbx_dir and self.config.source_fbx_dir.exists():
            for fbx_path in self.config.source_fbx_dir.rglob("*.fbx"):
                fbx_sources.append((fbx_path.name, fbx_path))
            for fbx_path in self.config.source_fbx_dir.rglob("*.FBX"):
                fbx_sources.append((fbx_path.name, fbx_path))

        for fbx_name, source_path in fbx_sources:
            try:
                # Determine category
                category = self.import_generator.categorize_fbx(fbx_name)

                # Copy FBX to output
                dest_path = self.config.models_dir / category / fbx_name

                if not self.config.dry_run:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_path, dest_path)

                model_count += 1

                # Build material mappings for import file
                # Use the generated materials (which now have FBX names as keys)
                materials_rel = self.config.materials_dir.relative_to(self.config.godot_project_path)

                mat_mappings = {}
                for mat_name in self.generated_materials.keys():
                    tres_path = f"res://{materials_rel.as_posix()}/{mat_name}.tres"
                    # Get type from classifications if available, else STANDARD
                    mat_type = self.material_classifications.get(mat_name, MaterialType.STANDARD)
                    mat_mappings[mat_name] = (tres_path, mat_type)

                # Extract mesh name from FBX filename
                mesh_name = Path(fbx_name).stem
                meshes = [mesh_name]
                mesh_count += 1

                # Generate import file
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
        """Ensure required shaders exist in the shaders directory."""
        required_shaders = set(SHADER_FILES.values())

        for shader_file in required_shaders:
            shader_path = self.config.shaders_dir / shader_file

            if not shader_path.exists() and not self.config.dry_run:
                # Create a placeholder shader
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
    """
    Convenience function to convert a Synty pack.

    Args:
        pack_name: Name of the pack (e.g., "POLYGON_Samurai_Empire")
        godot_project: Path to Godot project root
        unity_package: Optional path to .unitypackage file
        source_fbx_dir: Optional path to directory with FBX files
        source_textures_dir: Optional path to directory with textures
        dry_run: If True, don't write files
        verbose: If True, enable debug logging

    Returns:
        Conversion summary dict
    """
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
