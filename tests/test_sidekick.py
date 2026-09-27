"""Tests for parsing and resolving Sidekick character recipes."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sidekick import (  # noqa: E402
    SidekickPart,
    SidekickRecipe,
    parse_sk_bytes,
)

# Shipped .sk files are CRLF. Building the fixture with explicit \r\n keeps the
# tests honest about the format the parser actually meets.
SK_BODY = (
    "Name: HumanSpecies_01\r\n"
    "Species: 1\r\n"
    "Parts:\r\n"
    "- Name: SK_HUMN_BASE_01_01HEAD_HU01\r\n"
    "  PartType: Head\r\n"
    "  PartVersion: 1\r\n"
    "- Name: SK_HUMN_BASE_01_10TORS_HU01\r\n"
    "  PartType: Torso\r\n"
    "  PartVersion: 1\r\n"
    "ColorSet:\r\n"
    "  Species: 1\r\n"
    "  Name: Custom\r\n"
    "ColorRows:\r\n"
    "- ColorProperty: 1\r\n"
    "  MainColor: FCC19C\r\n"
)


class TestParseSkBytes:
    def test_reads_name_and_species(self):
        recipe = parse_sk_bytes(SK_BODY.encode("utf-8"))
        assert recipe.name == "HumanSpecies_01"
        assert recipe.species == 1

    def test_reads_every_part_in_order(self):
        recipe = parse_sk_bytes(SK_BODY.encode("utf-8"))
        assert [(p.slot, p.mesh) for p in recipe.parts] == [
            ("Head", "SK_HUMN_BASE_01_01HEAD_HU01"),
            ("Torso", "SK_HUMN_BASE_01_10TORS_HU01"),
        ]

    def test_lf_parses_identically(self):
        """The parser must not be accidentally CRLF-only."""
        crlf = parse_sk_bytes(SK_BODY.encode("utf-8"))
        lf = parse_sk_bytes(SK_BODY.replace("\r\n", "\n").encode("utf-8"))
        assert [(p.slot, p.mesh) for p in lf.parts] == [
            (p.slot, p.mesh) for p in crlf.parts
        ]
        assert lf.name == crlf.name

    def test_colorset_name_does_not_override_character_name(self):
        """ColorSet carries an indented 'Name: Custom' that must be ignored."""
        assert parse_sk_bytes(SK_BODY.encode("utf-8")).name == "HumanSpecies_01"

    def test_no_parts_block_yields_none(self):
        data = b"Name: Empty\r\nSpecies: 1\r\nColorRows:\r\n"
        assert parse_sk_bytes(data) is None

    def test_no_name_yields_none(self):
        data = (
            "Parts:\r\n- Name: SK_X\r\n  PartType: Head\r\n"
        ).encode("utf-8")
        assert parse_sk_bytes(data) is None

    def test_missing_species_defaults_to_zero(self):
        data = (
            "Name: NoSpecies\r\nParts:\r\n- Name: SK_X\r\n  PartType: Head\r\n"
        ).encode("utf-8")
        assert parse_sk_bytes(data).species == 0

    def test_parts_start_unresolved(self):
        recipe = parse_sk_bytes(SK_BODY.encode("utf-8"))
        assert all(p.fbx == "" for p in recipe.parts)

    def test_dataclass_defaults(self):
        part = SidekickPart(slot="Head", mesh="SK_X")
        recipe = SidekickRecipe(name="R")
        assert (part.fbx, recipe.species, recipe.parts, recipe.color_map) == (
            "", 0, [], "",
        )


from sidekick import (  # noqa: E402
    build_sidekick_recipes,
    write_sidekick_characters_json,
)


class _FakeGuidMap:
    def __init__(self, sk_content=None, textures=None):
        self.guid_to_sk_content = sk_content or {}
        self.texture_guid_to_name = textures or {}
        self.guid_to_pathname = {}


def _models(tmp_path, relative_fbx):
    """Create a models/ tree containing the named FBX files."""
    models = tmp_path / "models"
    for rel in relative_fbx:
        path = models / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fbx")
    models.mkdir(parents=True, exist_ok=True)
    return models


class TestBuildSidekickRecipes:
    def test_resolves_parts_to_models_relative_paths(self, tmp_path):
        models = _models(tmp_path, [
            "Resources/Meshes/Species/Humans/SK_HUMN_BASE_01_01HEAD_HU01.fbx",
            "Resources/Meshes/Species/Humans/SK_HUMN_BASE_01_10TORS_HU01.fbx",
        ])
        gm = _FakeGuidMap({"g": SK_BODY.encode("utf-8")})
        recipes = build_sidekick_recipes(gm, [], models)
        parts = recipes["HumanSpecies_01"].parts
        assert parts[0].fbx == "Resources/Meshes/Species/Humans/SK_HUMN_BASE_01_01HEAD_HU01"
        assert parts[1].fbx == "Resources/Meshes/Species/Humans/SK_HUMN_BASE_01_10TORS_HU01"

    def test_unresolved_part_keeps_recipe(self, tmp_path):
        """A part from another pack must not lose the whole character."""
        models = _models(tmp_path, [
            "Meshes/SK_HUMN_BASE_01_01HEAD_HU01.fbx",
        ])
        gm = _FakeGuidMap({"g": SK_BODY.encode("utf-8")})
        recipes = build_sidekick_recipes(gm, [], models)
        parts = recipes["HumanSpecies_01"].parts
        assert parts[0].fbx == "Meshes/SK_HUMN_BASE_01_01HEAD_HU01"
        assert parts[1].fbx == ""

    def test_recipe_with_no_resolved_parts_is_dropped(self, tmp_path):
        models = _models(tmp_path, [])
        gm = _FakeGuidMap({"g": SK_BODY.encode("utf-8")})
        assert build_sidekick_recipes(gm, [], models) == {}

    def test_duplicate_basename_takes_first_in_sorted_order(self, tmp_path):
        models = _models(tmp_path, [
            "B/SK_HUMN_BASE_01_01HEAD_HU01.fbx",
            "A/SK_HUMN_BASE_01_01HEAD_HU01.fbx",
        ])
        gm = _FakeGuidMap({"g": SK_BODY.encode("utf-8")})
        recipes = build_sidekick_recipes(gm, [], models)
        assert recipes["HumanSpecies_01"].parts[0].fbx == "A/SK_HUMN_BASE_01_01HEAD_HU01"

    def test_color_map_resolves_when_texture_present(self, tmp_path):
        models = _models(tmp_path, ["M/SK_HUMN_BASE_01_01HEAD_HU01.fbx"])
        gm = _FakeGuidMap(
            {"g": SK_BODY.encode("utf-8")},
            {"t": "T_HumanSpecies_01ColorMap.png"},
        )
        recipes = build_sidekick_recipes(gm, [], models)
        assert recipes["HumanSpecies_01"].color_map == "T_HumanSpecies_01ColorMap"

    def test_color_map_empty_when_absent(self, tmp_path):
        models = _models(tmp_path, ["M/SK_HUMN_BASE_01_01HEAD_HU01.fbx"])
        gm = _FakeGuidMap({"g": SK_BODY.encode("utf-8")})
        assert build_sidekick_recipes(gm, [], models)["HumanSpecies_01"].color_map == ""

    def test_material_name_matches_recipe_name_by_default(self, tmp_path):
        models = _models(tmp_path, ["M/SK_HUMN_BASE_01_01HEAD_HU01.fbx"])
        gm = _FakeGuidMap(
            {"g": SK_BODY.encode("utf-8")},
            {"t": "T_HumanSpecies_01ColorMap.png"},
        )
        recipes = build_sidekick_recipes(gm, [], models)
        assert recipes["HumanSpecies_01"].material == "HumanSpecies_01"

    def test_trailing_letter_variant_resolves_palette(self, tmp_path):
        """Synty ships Starter_01b's palette and material as Starter_01.

        The recipe carries a variant suffix the assets do not, so an exact
        lookup finds neither and the character converts untextured.
        """
        body = SK_BODY.replace("HumanSpecies_01", "Starter_01b")
        models = _models(tmp_path, ["M/SK_HUMN_BASE_01_01HEAD_HU01.fbx"])
        gm = _FakeGuidMap(
            {"g": body.encode("utf-8")}, {"t": "T_Starter_01ColorMap.png"}
        )
        recipe = build_sidekick_recipes(gm, [], models)["Starter_01b"]
        assert recipe.color_map == "T_Starter_01ColorMap"
        assert recipe.material == "Starter_01"

    def test_exact_match_wins_over_trimmed_variant(self, tmp_path):
        """A character with its own palette must never borrow another's."""
        body = SK_BODY.replace("HumanSpecies_01", "Starter_01b")
        models = _models(tmp_path, ["M/SK_HUMN_BASE_01_01HEAD_HU01.fbx"])
        gm = _FakeGuidMap(
            {"g": body.encode("utf-8")},
            {"a": "T_Starter_01bColorMap.png", "b": "T_Starter_01ColorMap.png"},
        )
        recipe = build_sidekick_recipes(gm, [], models)["Starter_01b"]
        assert recipe.color_map == "T_Starter_01bColorMap"
        assert recipe.material == "Starter_01b"

    def test_trailing_letter_not_stripped_without_digit(self, tmp_path):
        """Only a variant suffix on a numbered name is a suffix worth trying."""
        body = SK_BODY.replace("HumanSpecies_01", "Goblin")
        models = _models(tmp_path, ["M/SK_HUMN_BASE_01_01HEAD_HU01.fbx"])
        gm = _FakeGuidMap({"g": body.encode("utf-8")}, {"t": "T_GoblinColorMap.png"})
        recipe = build_sidekick_recipes(gm, [], models)["Goblin"]
        assert recipe.color_map == "T_GoblinColorMap"
        assert recipe.material == "Goblin"

    def test_source_files_recipe_overrides_package(self, tmp_path):
        """A recipe saved in the user's Unity project is the likelier edit."""
        models = _models(tmp_path, ["M/SK_OTHER.fbx"])
        src = tmp_path / "src" / "Characters"
        src.mkdir(parents=True)
        (src / "HumanSpecies_01.sk").write_bytes(
            (
                "Name: HumanSpecies_01\r\nSpecies: 2\r\nParts:\r\n"
                "- Name: SK_OTHER\r\n  PartType: Head\r\n"
            ).encode("utf-8")
        )
        gm = _FakeGuidMap({"g": SK_BODY.encode("utf-8")})
        recipes = build_sidekick_recipes(gm, [tmp_path / "src"], models)
        assert recipes["HumanSpecies_01"].species == 2
        assert [p.mesh for p in recipes["HumanSpecies_01"].parts] == ["SK_OTHER"]

    def test_missing_models_dir_yields_nothing(self, tmp_path):
        gm = _FakeGuidMap({"g": SK_BODY.encode("utf-8")})
        assert build_sidekick_recipes(gm, [], tmp_path / "nope") == {}

    def test_no_recipes_yields_empty(self, tmp_path):
        assert build_sidekick_recipes(_FakeGuidMap(), [], _models(tmp_path, [])) == {}


class TestWriteSidekickCharactersJson:
    def test_writes_expected_shape(self, tmp_path):
        models = _models(tmp_path, [
            "Resources/Meshes/Species/Humans/SK_HUMN_BASE_01_01HEAD_HU01.fbx",
            "Resources/Meshes/Species/Humans/SK_HUMN_BASE_01_10TORS_HU01.fbx",
        ])
        gm = _FakeGuidMap(
            {"g": SK_BODY.encode("utf-8")},
            {"t": "T_HumanSpecies_01ColorMap.png"},
        )
        recipes = build_sidekick_recipes(gm, [], models)
        out = tmp_path / "sidekick_characters.json"
        write_sidekick_characters_json(recipes, out)

        import json as _json

        assert _json.loads(out.read_text(encoding="utf-8")) == {
            "HumanSpecies_01": {
                "species": 1,
                "color_map": "T_HumanSpecies_01ColorMap",
                "material": "HumanSpecies_01",
                "blend_shapes": {"body_type": 50, "body_size": 0, "muscle": 50},
                "parts": [
                    {
                        "slot": "Head",
                        "mesh": "SK_HUMN_BASE_01_01HEAD_HU01",
                        "fbx": "Resources/Meshes/Species/Humans/SK_HUMN_BASE_01_01HEAD_HU01",
                    },
                    {
                        "slot": "Torso",
                        "mesh": "SK_HUMN_BASE_01_10TORS_HU01",
                        "fbx": "Resources/Meshes/Species/Humans/SK_HUMN_BASE_01_10TORS_HU01",
                    },
                ],
            }
        }

    def test_creates_parent_directory(self, tmp_path):
        out = tmp_path / "deep" / "sidekick_characters.json"
        write_sidekick_characters_json({}, out)
        assert out.exists()


from sidekick import SidekickBlendShapes  # noqa: E402

# The proportion block sits at the very end of a real .sk, after ColorRows.
BLEND_TAIL = (
    "BlendShapes:\r\n"
    "  BodyTypeValue: 100\r\n"
    "  BodySizeValue: -64\r\n"
    "  MuscleValue: -17.1000004\r\n"
)


class TestParseBlendShapes:
    def test_reads_all_three_values(self):
        recipe = parse_sk_bytes((SK_BODY + BLEND_TAIL).encode("utf-8"))
        assert recipe.blend_shapes.body_type == 100
        assert recipe.blend_shapes.body_size == -64
        assert recipe.blend_shapes.muscle == pytest.approx(-17.1000004)

    def test_lf_parses_identically(self):
        body = (SK_BODY + BLEND_TAIL).replace("\r\n", "\n")
        assert parse_sk_bytes(body.encode("utf-8")).blend_shapes.body_size == -64

    def test_omitted_key_falls_back_to_unity_default(self):
        """The tool omits a value equal to its default.

        Only BodySizeValue is omitted in practice, and Synty's
        SerializedBlendShapeValues defaults it to 0 - so an omitted key must
        restore that default, not zero everything.
        """
        tail = "BlendShapes:\r\n  BodyTypeValue: -100\r\n  MuscleValue: 100\r\n"
        shapes = parse_sk_bytes((SK_BODY + tail).encode("utf-8")).blend_shapes
        assert (shapes.body_type, shapes.body_size, shapes.muscle) == (-100, 0, 100)

    def test_absent_block_yields_unity_defaults(self):
        shapes = parse_sk_bytes(SK_BODY.encode("utf-8")).blend_shapes
        assert (shapes.body_type, shapes.body_size, shapes.muscle) == (50, 0, 50)

    def test_defaults_match_synty_serializer(self):
        """Mirrors SerializedBlendShapeValues: 50 / 0 / 50, not all zero."""
        shapes = SidekickBlendShapes()
        assert (shapes.body_type, shapes.body_size, shapes.muscle) == (50, 0, 50)

    def test_colorrows_values_are_not_mistaken_for_proportions(self):
        """ColorRows precedes the block and carries its own indented keys."""
        recipe = parse_sk_bytes((SK_BODY + BLEND_TAIL).encode("utf-8"))
        assert recipe.blend_shapes.body_type == 100

    def test_recipe_without_parts_still_yields_none(self):
        data = ("Name: X\r\nSpecies: 1\r\n" + BLEND_TAIL).encode("utf-8")
        assert parse_sk_bytes(data) is None


class TestBlendShapesInJson:
    def test_written_json_carries_proportions(self, tmp_path):
        models = _models(tmp_path, ["M/SK_HUMN_BASE_01_01HEAD_HU01.fbx"])
        gm = _FakeGuidMap({"g": (SK_BODY + BLEND_TAIL).encode("utf-8")})
        recipes = build_sidekick_recipes(gm, [], models)
        out = tmp_path / "sidekick_characters.json"
        write_sidekick_characters_json(recipes, out)

        import json as _json

        payload = _json.loads(out.read_text(encoding="utf-8"))
        assert payload["HumanSpecies_01"]["blend_shapes"] == {
            "body_type": 100,
            "body_size": -64,
            "muscle": pytest.approx(-17.1000004),
        }


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
