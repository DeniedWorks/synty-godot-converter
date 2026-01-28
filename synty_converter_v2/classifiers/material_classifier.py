"""Material type classifier based on Unity metadata and naming conventions."""

import re
from typing import Optional
import logging

from ..config import MaterialType
from ..extractors.unity_package import MaterialInfo

logger = logging.getLogger(__name__)


class MaterialClassifier:
    """Classify materials into shader types based on metadata and naming."""

    # Name patterns for fallback classification
    FOLIAGE_PATTERNS = [
        r"(?i)leaf", r"(?i)tree", r"(?i)plant", r"(?i)grass", r"(?i)bush",
        r"(?i)hedge", r"(?i)vine", r"(?i)flower", r"(?i)fern", r"(?i)moss",
        r"(?i)bamboo", r"(?i)cherry.*blossom", r"(?i)foliage", r"(?i)shrub"
    ]

    WATER_PATTERNS = [
        r"(?i)water", r"(?i)ocean", r"(?i)river", r"(?i)lake", r"(?i)pond",
        r"(?i)sea", r"(?i)wave", r"(?i)stream", r"(?i)waterfall"
    ]

    GLASS_PATTERNS = [
        r"(?i)glass", r"(?i)window", r"(?i)crystal", r"(?i)ice",
        r"(?i)transparent", r"(?i)mirror", r"(?i)lens"
    ]

    EMISSIVE_PATTERNS = [
        r"(?i)lantern", r"(?i)lamp", r"(?i)light", r"(?i)glow",
        r"(?i)torch", r"(?i)fire", r"(?i)flame", r"(?i)candle",
        r"(?i)neon", r"(?i)emissive", r"(?i)lava", r"(?i)magic"
    ]

    SKY_PATTERNS = [
        r"(?i)sky", r"(?i)skydome", r"(?i)skybox"
    ]

    CLOUD_PATTERNS = [
        r"(?i)cloud", r"(?i)fog", r"(?i)mist", r"(?i)smoke"
    ]

    PARTICLE_PATTERNS = [
        r"(?i)particle", r"(?i)fx_", r"(?i)effect", r"(?i)spark",
        r"(?i)dust", r"(?i)debris"
    ]

    def classify(self, material_name: str, material_info: Optional[MaterialInfo] = None) -> MaterialType:
        """
        Classify a material into a shader type.

        Priority order:
        1. FOLIAGE - Has leaf/trunk textures or wind properties
        2. EMISSIVE - Has emission enabled with texture or color
        3. GLASS - Has transparent render type or glass name
        4. WATER - Water-related name
        5. STANDARD - Default

        Args:
            material_name: Name of the material
            material_info: Optional MaterialInfo from Unity package parsing

        Returns:
            MaterialType enum value
        """
        # If we have Unity metadata, use property-based detection
        if material_info:
            mat_type = self._classify_from_metadata(material_info)
            if mat_type != MaterialType.STANDARD:
                logger.debug(f"Classified {material_name} as {mat_type.name} from metadata")
                return mat_type

        # Fall back to name-based classification
        mat_type = self._classify_from_name(material_name)
        logger.debug(f"Classified {material_name} as {mat_type.name} from name")
        return mat_type

    def _classify_from_metadata(self, mat_info: MaterialInfo) -> MaterialType:
        """Classify material based on Unity .mat file metadata."""

        # Priority 1: FOLIAGE - check for foliage-specific properties
        if mat_info.has_foliage_properties:
            return MaterialType.FOLIAGE

        # Priority 2: EMISSIVE - check for emission
        if mat_info.has_emission:
            return MaterialType.EMISSIVE

        # Priority 3: GLASS - check for transparent render type
        if mat_info.is_transparent:
            # Also check name to avoid false positives
            name_lower = mat_info.name.lower()
            if self._matches_patterns(name_lower, self.GLASS_PATTERNS):
                return MaterialType.GLASS
            # Could still be glass even without name match if RenderType is Transparent
            # But we need to be careful about alpha-tested foliage
            if not self._matches_patterns(name_lower, self.FOLIAGE_PATTERNS):
                return MaterialType.GLASS

        # Priority 4: Check name for water (Unity water often doesn't have special properties)
        if self._matches_patterns(mat_info.name.lower(), self.WATER_PATTERNS):
            return MaterialType.WATER

        # Default to standard
        return MaterialType.STANDARD

    def _classify_from_name(self, material_name: str) -> MaterialType:
        """Classify material based on name patterns only."""
        name_lower = material_name.lower()

        # Check in priority order
        checks = [
            (self.SKY_PATTERNS, MaterialType.SKY),
            (self.CLOUD_PATTERNS, MaterialType.CLOUDS),
            (self.FOLIAGE_PATTERNS, MaterialType.FOLIAGE),
            (self.WATER_PATTERNS, MaterialType.WATER),
            (self.GLASS_PATTERNS, MaterialType.GLASS),
            (self.EMISSIVE_PATTERNS, MaterialType.EMISSIVE),
            (self.PARTICLE_PATTERNS, MaterialType.PARTICLES),
        ]

        for patterns, mat_type in checks:
            if self._matches_patterns(name_lower, patterns):
                return mat_type

        return MaterialType.STANDARD

    def _matches_patterns(self, text: str, patterns: list[str]) -> bool:
        """Check if text matches any of the regex patterns."""
        for pattern in patterns:
            if re.search(pattern, text):
                return True
        return False

    def classify_batch(
        self,
        material_names: list[str],
        materials_info: Optional[dict[str, MaterialInfo]] = None
    ) -> dict[str, MaterialType]:
        """
        Classify multiple materials.

        Args:
            material_names: List of material names
            materials_info: Optional dict mapping names to MaterialInfo

        Returns:
            Dict mapping material names to MaterialType
        """
        results = {}
        materials_info = materials_info or {}

        for name in material_names:
            mat_info = materials_info.get(name)
            results[name] = self.classify(name, mat_info)

        return results

    def get_summary(self, classifications: dict[str, MaterialType]) -> dict[MaterialType, list[str]]:
        """Get summary of classifications grouped by type."""
        summary: dict[MaterialType, list[str]] = {t: [] for t in MaterialType}

        for name, mat_type in classifications.items():
            summary[mat_type].append(name)

        return {k: v for k, v in summary.items() if v}  # Remove empty lists
