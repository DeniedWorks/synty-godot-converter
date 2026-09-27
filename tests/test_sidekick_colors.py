"""Colour properties and presets from the Sidekick tool database."""

import sqlite3
from pathlib import Path

from sidekick import COLOR_UNSET, find_master_color_map, load_color_tables


def _make_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE sk_color_property (
            id INTEGER PRIMARY KEY, color_group INTEGER,
            name TEXT, u INTEGER, v INTEGER
        );
        CREATE TABLE sk_color_preset (
            id INTEGER PRIMARY KEY, ptr_species INTEGER,
            color_group INTEGER, name TEXT
        );
        CREATE TABLE sk_color_preset_row (
            id INTEGER PRIMARY KEY, ptr_color_preset INTEGER,
            ptr_color_property INTEGER, color TEXT, metallic TEXT,
            smoothness TEXT, reflection TEXT, emission TEXT, opacity TEXT
        );
        INSERT INTO sk_color_property VALUES (1, 1, 'Skin 01', 0, 5);
        INSERT INTO sk_color_property VALUES (159, 3, 'Hip Back Outfit 05', 14, 11);
        INSERT INTO sk_color_preset VALUES (112, 1, 5, 'Elements 01');
        INSERT INTO sk_color_preset_row VALUES
            (1, 112, 1, 'EFC70A', 'FF0000', 'FF0000', 'FF0000', 'FF0000', 'FF0000'),
            (2, 112, 159, 'FF0000', NULL, NULL, NULL, NULL, NULL),
            (3, 112, 999, '00FF00', NULL, NULL, NULL, NULL, NULL);
        """
    )
    connection.commit()
    connection.close()


def test_properties_carry_their_texel_coordinates(tmp_path):
    db = tmp_path / "Side_Kick_Data.db"
    _make_db(db)

    tables = load_color_tables(db)

    assert tables["properties"]["Hip Back Outfit 05"] == {
        "id": 159,
        "group": 3,
        "u": 14,
        "v": 11,
    }


def test_presets_name_their_colours_by_property(tmp_path):
    db = tmp_path / "Side_Kick_Data.db"
    _make_db(db)

    tables = load_color_tables(db)

    assert tables["presets"]["112"]["colors"]["Skin 01"] == "EFC70A"
    assert tables["presets"]["112"]["name"] == "Elements 01"


def test_the_unset_sentinel_is_dropped_rather_than_stored(tmp_path):
    """FF0000 means "this preset says nothing about that slot".

    Storing it would paint the slot bright red, which is the bug this whole
    feature exists to remove.
    """
    db = tmp_path / "Side_Kick_Data.db"
    _make_db(db)

    tables = load_color_tables(db)

    assert COLOR_UNSET == "FF0000"
    assert "Hip Back Outfit 05" not in tables["presets"]["112"]["colors"]


def test_rows_naming_an_unknown_property_are_dropped(tmp_path):
    db = tmp_path / "Side_Kick_Data.db"
    _make_db(db)

    tables = load_color_tables(db)

    assert list(tables["presets"]["112"]["colors"]) == ["Skin 01"]


def test_a_missing_database_yields_empty_tables(tmp_path):
    assert load_color_tables(tmp_path / "absent.db") == {"properties": {}, "presets": {}}


def test_find_master_color_map_locates_the_tool_texture(tmp_path):
    textures = tmp_path / "Synty" / "SidekickCharacters" / "Resources" / "Textures"
    textures.mkdir(parents=True)
    (textures / "T_ColorMap.png").write_bytes(b"stub")

    assert find_master_color_map([tmp_path]) == textures / "T_ColorMap.png"


def test_find_master_color_map_returns_none_when_absent(tmp_path):
    assert find_master_color_map([tmp_path]) is None


def test_find_master_color_map_ignores_the_demo_copy(tmp_path):
    """The _Demos folder carries its own T_ColorMap that is not the master."""
    demo = tmp_path / "SidekickCharacters" / "_Demos" / "Textures"
    demo.mkdir(parents=True)
    (demo / "T_ColorMap.png").write_bytes(b"stub")
    real = tmp_path / "SidekickCharacters" / "Resources" / "Textures"
    real.mkdir(parents=True)
    (real / "T_ColorMap.png").write_bytes(b"stub")

    assert find_master_color_map([tmp_path]) == real / "T_ColorMap.png"
