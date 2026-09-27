"""Tests for Unity-to-Godot shader property mapping."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shader_mapping import TEXTURE_MAP_POLYGON  # noqa: E402


class TestSidekickColorMap:
    def test_color_map_maps_to_base_texture(self):
        """Sidekick materials name their palette _ColorMap.

        Each Sidekick character carries a baked 32x32 palette that its part
        meshes' UVs index into. Without this entry the palette never reaches
        the generated material and the texture copy never pulls the PNG, so
        every Sidekick character converts untextured.
        """
        assert TEXTURE_MAP_POLYGON["_ColorMap"] == "base_texture"

    def test_known_albedo_aliases_still_map(self):
        """The aliases other packs rely on must not regress."""
        for unity_name in ("_MainTex", "_BaseMap", "_Base_Texture", "_Texture"):
            assert TEXTURE_MAP_POLYGON[unity_name] == "base_texture"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
