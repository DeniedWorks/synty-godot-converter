"""Match FBX material names to Unity material names."""

import re
from typing import Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class MaterialMatch:
    """A match between FBX and Unity material names."""
    fbx_name: str
    unity_name: Optional[str]
    confidence: float  # 0.0 to 1.0
    match_reason: str


class MaterialMatcher:
    """Match FBX material names to Unity .mat names."""

    # Common suffixes to strip for matching
    STRIP_SUFFIXES = [
        '_TGA', '_PNG', '_JPG',  # Texture format suffixes
        '_C', '_D', '_N', '_E',   # Channel suffixes
        '_Mat', '_Material',      # Material suffixes
        '_01', '_02', '_03',      # Number suffixes (be careful with these)
    ]

    # Common prefixes to strip
    STRIP_PREFIXES = [
        'M_', 'Mat_', 'MAT_',
    ]

    def __init__(self, unity_materials: dict[str, any]):
        """
        Initialize with Unity materials.

        Args:
            unity_materials: Dict mapping Unity material names to MaterialInfo
        """
        self.unity_materials = unity_materials
        self.unity_names = list(unity_materials.keys())
        self.unity_names_lower = {name.lower(): name for name in self.unity_names}

    def match(self, fbx_name: str) -> MaterialMatch:
        """
        Find the best Unity material match for an FBX material name.

        Args:
            fbx_name: Material name from FBX file

        Returns:
            MaterialMatch with the best match found
        """
        # Try matching strategies in order of confidence
        strategies = [
            (self._exact_match, 1.0),
            (self._case_insensitive_match, 0.95),
            (self._stripped_match, 0.85),
            (self._fuzzy_contains_match, 0.7),
            (self._number_pattern_match, 0.6),
        ]

        for strategy, base_confidence in strategies:
            result = strategy(fbx_name)
            if result:
                unity_name, reason = result
                return MaterialMatch(
                    fbx_name=fbx_name,
                    unity_name=unity_name,
                    confidence=base_confidence,
                    match_reason=reason
                )

        # No match found
        return MaterialMatch(
            fbx_name=fbx_name,
            unity_name=None,
            confidence=0.0,
            match_reason="No match found"
        )

    def _exact_match(self, fbx_name: str) -> Optional[tuple[str, str]]:
        """Exact name match."""
        if fbx_name in self.unity_materials:
            return fbx_name, "Exact match"
        return None

    def _case_insensitive_match(self, fbx_name: str) -> Optional[tuple[str, str]]:
        """Case-insensitive match."""
        fbx_lower = fbx_name.lower()
        if fbx_lower in self.unity_names_lower:
            return self.unity_names_lower[fbx_lower], "Case-insensitive match"
        return None

    def _stripped_match(self, fbx_name: str) -> Optional[tuple[str, str]]:
        """Match after stripping common suffixes/prefixes."""
        fbx_stripped = self._strip_name(fbx_name)

        for unity_name in self.unity_names:
            unity_stripped = self._strip_name(unity_name)

            if fbx_stripped.lower() == unity_stripped.lower():
                return unity_name, f"Stripped match ({fbx_stripped} = {unity_stripped})"

        return None

    def _fuzzy_contains_match(self, fbx_name: str) -> Optional[tuple[str, str]]:
        """Match if one name contains the other."""
        fbx_lower = fbx_name.lower()
        fbx_stripped = self._strip_name(fbx_name).lower()

        best_match = None
        best_len = 0

        for unity_name in self.unity_names:
            unity_lower = unity_name.lower()
            unity_stripped = self._strip_name(unity_name).lower()

            # Check if FBX name is contained in Unity name or vice versa
            if fbx_stripped in unity_stripped or unity_stripped in fbx_stripped:
                # Prefer longer matches
                match_len = min(len(fbx_stripped), len(unity_stripped))
                if match_len > best_len:
                    best_match = unity_name
                    best_len = match_len

        if best_match:
            return best_match, f"Contains match"

        return None

    def _number_pattern_match(self, fbx_name: str) -> Optional[tuple[str, str]]:
        """
        Match based on number patterns.
        e.g., MAT_01A might match PolygonPack_01_C
        """
        # Extract numbers from FBX name
        fbx_numbers = re.findall(r'\d+', fbx_name)
        if not fbx_numbers:
            return None

        fbx_num = fbx_numbers[0]  # Use first number

        # Find Unity materials with matching numbers
        candidates = []
        for unity_name in self.unity_names:
            unity_numbers = re.findall(r'\d+', unity_name)
            if fbx_num in unity_numbers:
                candidates.append(unity_name)

        if len(candidates) == 1:
            return candidates[0], f"Number pattern match ({fbx_num})"

        # If multiple candidates, try to narrow down by letter suffix
        if len(candidates) > 1:
            # Look for letter suffix in FBX name (e.g., 01A, 02B)
            letter_match = re.search(r'\d+([A-Za-z])', fbx_name)
            if letter_match:
                letter = letter_match.group(1).upper()
                for candidate in candidates:
                    if f"_{letter}" in candidate.upper() or candidate.upper().endswith(letter):
                        return candidate, f"Number+letter match ({fbx_num}{letter})"

        return None

    def _strip_name(self, name: str) -> str:
        """Strip common prefixes and suffixes from a name."""
        result = name

        # Strip prefixes
        for prefix in self.STRIP_PREFIXES:
            if result.upper().startswith(prefix.upper()):
                result = result[len(prefix):]
                break

        # Strip suffixes
        for suffix in self.STRIP_SUFFIXES:
            if result.upper().endswith(suffix.upper()):
                result = result[:-len(suffix)]

        return result

    def match_all(self, fbx_names: list[str]) -> dict[str, MaterialMatch]:
        """
        Match all FBX material names.

        Returns:
            Dict mapping FBX name to MaterialMatch
        """
        results = {}
        for fbx_name in fbx_names:
            results[fbx_name] = self.match(fbx_name)
        return results

    def get_match_summary(self, matches: dict[str, MaterialMatch]) -> dict:
        """Get a summary of match results."""
        matched = sum(1 for m in matches.values() if m.unity_name)
        unmatched = sum(1 for m in matches.values() if not m.unity_name)
        avg_confidence = sum(m.confidence for m in matches.values()) / len(matches) if matches else 0

        return {
            "total": len(matches),
            "matched": matched,
            "unmatched": unmatched,
            "avg_confidence": avg_confidence,
            "unmatched_names": [m.fbx_name for m in matches.values() if not m.unity_name]
        }
