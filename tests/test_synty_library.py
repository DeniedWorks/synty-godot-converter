"""Tests for the batch conversion driver's routing decisions.

The driver's job is deciding, per pack, where its meshes come from and whether
it has meshes at all. Those decisions are pure functions of a filename and an
extension census, so they test without a package or Godot.
"""

import argparse
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import converter as converter_module  # noqa: E402
from sidekick import find_sidekick_database  # noqa: E402
from converter import extract_pack_name_from_package  # noqa: E402
from synty_library import (  # noqa: E402
    SKIP_PREFIXES,
    _read_pack_counts,
    _status,
    collect_warnings,
    convert_library,
    convert_mesh_pack,
    install_addon,
    resolve_work_dir,
    find_unity_source,
    has_meshes,
    has_sprites,
    needs_conversion,
    normalise,
)


class TestPackNameExtraction:
    def test_standard_naming(self):
        assert extract_pack_name_from_package(
            Path("POLYGON_Dungeon_Unity_2021_3_v1_9_5.unitypackage")
        ) == "POLYGON_Dungeon"

    def test_nature_biome_naming(self):
        assert extract_pack_name_from_package(
            Path("POLYGON_NatureBiomes_EnchantedForest_Unity_2022_3_v1_6_2.unitypackage")
        ) == "POLYGON_NatureBiomes_EnchantedForest"

    def test_unity_year_without_minor_version(self):
        """Some packs ship as `_Unity_2021_v1_0_2_Unity`: no minor version, and
        the marker repeated at the end."""
        assert extract_pack_name_from_package(
            Path("POLYGON_Goblin_War_Camp_Unity_2021_v1_0_2_Unity.unitypackage")
        ) == "POLYGON_Goblin_War_Camp"

    def test_no_version_pattern_passes_through(self):
        assert extract_pack_name_from_package(Path("Nature.unitypackage")) == "Nature"


class TestUnitySourceLookup:
    def test_normalise_bridges_the_two_conventions(self):
        assert normalise("POLYGON_Dungeon_Realms") == normalise("PolygonDungeonRealms")

    def test_finds_matching_import_folder(self, tmp_path):
        for name in ("PolygonGoblinWarCamp", "PolygonDungeon"):
            models = tmp_path / name / "Models"
            models.mkdir(parents=True)
            # A folder only counts as a source when it actually holds meshes.
            for fbx in ("a.fbx", "b.fbx"):
                (models / fbx).touch()
        found = find_unity_source("POLYGON_Goblin_War_Camp", tmp_path)
        assert found == tmp_path / "PolygonGoblinWarCamp"

    def test_returns_none_when_not_imported(self, tmp_path):
        models = tmp_path / "PolygonDungeon" / "Models"
        models.mkdir(parents=True)
        (models / "a.fbx").touch()
        (models / "b.fbx").touch()
        assert find_unity_source("POLYGON_Kaiju", tmp_path) is None

    def test_returns_none_for_missing_assets_dir(self, tmp_path):
        assert find_unity_source("POLYGON_Kaiju", tmp_path / "absent") is None


class TestRouting:
    def test_mesh_pack_has_meshes_only(self):
        counts = {".fbx": 801, ".png": 50, ".mat": 42}
        assert has_meshes(counts)
        assert not has_sprites(counts)

    def test_pure_ui_pack_has_sprites_only(self):
        counts = {".png": 1043, ".prefab": 210}
        assert not has_meshes(counts)
        assert has_sprites(counts)

    def test_ui_pack_with_a_few_demo_meshes_takes_both_routes(self):
        """A UI pack carries thousands of sprites and a few demo-scene FBX, so
        routing on "no FBX at all" would drop every sprite."""
        counts = {".png": 2205, ".fbx": 6, ".prefab": 327}
        assert has_meshes(counts)
        assert has_sprites(counts)

    def test_mesh_pack_with_many_textures_is_not_a_ui_pack(self):
        """A prop pack's textures must not be mistaken for a sprite set."""
        counts = {".fbx": 520, ".png": 300}
        assert has_meshes(counts)
        assert not has_sprites(counts)


class TestPackGrading:
    """A pack that takes both routes is graded on what each route achieved."""

    def test_both_routes_succeeding_is_ok(self):
        assert _status(True, True) == "ok"

    def test_sprites_without_meshes_is_partial(self):
        """Dark Fantasy HUD: 2205 sprites converted, its 6 demo meshes did not.

        Calling the pack failed buries the sprites that did convert; calling it
        ok hides that something went wrong.
        """
        assert _status(True, False) == "partial"

    def test_meshes_without_sprites_is_partial(self):
        assert _status(False, True) == "partial"

    def test_both_routes_failing_is_failed(self):
        assert _status(False, False) == "failed"

    def test_a_single_route_is_graded_alone(self):
        assert _status(None, True) == "ok"
        assert _status(None, False) == "failed"
        assert _status(True, None) == "ok"

    def test_no_route_attempted_is_failed(self):
        assert _status(None, None) == "failed"


class TestPartialUnityImports:
    """A Unity folder that exists is not automatically the better source.

    A partial import has the directory structure and almost none of the meshes,
    and preferring it silently loses whatever it is missing.
    """

    def test_a_populated_unity_folder_is_used(self, tmp_path):
        pack = tmp_path / "PolygonDungeon" / "Models"
        pack.mkdir(parents=True)
        for name in ("a.fbx", "b.fbx", "c.fbx"):
            (pack / name).touch()
        assert find_unity_source("POLYGON_Dungeon", tmp_path) == tmp_path / "PolygonDungeon"

    def test_a_partial_unity_folder_is_rejected(self, tmp_path):
        pack = tmp_path / "PolygonHorrorCarnival" / "Models"
        pack.mkdir(parents=True)
        (pack / "SM_Prop_BearTrap_01.fbx").touch()
        assert find_unity_source("POLYGON_Horror_Carnival", tmp_path) is None

    def test_an_empty_unity_folder_is_rejected(self, tmp_path):
        (tmp_path / "PolygonKaiju" / "Models").mkdir(parents=True)
        assert find_unity_source("POLYGON_Kaiju", tmp_path) is None


class TestWorkDir:
    """Extracted FBX must land outside the Godot project.

    Godot imports everything beneath its project root, so extracting into the
    output directory silently doubles every imported mesh.
    """

    def test_defaults_beside_the_output(self, tmp_path):
        output = tmp_path / "MyGodotProject"
        assert resolve_work_dir(output, None) == tmp_path / "MyGodotProject_synty_work"

    def test_an_explicit_directory_is_honoured(self, tmp_path):
        chosen = tmp_path / "elsewhere"
        assert resolve_work_dir(tmp_path / "out", chosen) == chosen

    def test_refuses_a_directory_inside_the_project(self, tmp_path):
        output = tmp_path / "out"
        with pytest.raises(ValueError, match="outside"):
            resolve_work_dir(output, output / "work")

    def test_refuses_the_project_itself(self, tmp_path):
        output = tmp_path / "out"
        with pytest.raises(ValueError, match="outside"):
            resolve_work_dir(output, output)

    def test_a_sibling_sharing_a_name_prefix_is_allowed(self, tmp_path):
        """`out_work` is not inside `out`, however the strings compare."""
        output = tmp_path / "out"
        assert resolve_work_dir(output, tmp_path / "out_work") == tmp_path / "out_work"


class TestOptionalUnityAssets:
    def test_no_unity_project_means_every_pack_is_extracted(self):
        """A user with only a Downloads folder must still convert everything."""
        assert find_unity_source("POLYGON_Dungeon", None) is None


class TestPackSelection:
    """Which packages the tool will touch at all."""

    def test_sidekick_packs_are_converted(self):
        """They carry the modular parts; skipping them leaves the addon with
        nothing to assemble. They were excluded while the rest of the library
        was being built out, which is the opposite of what a user needs."""
        assert not "SIDEKICK_Fantasy_Knights_Unity_2021_3_v1_0_7.unitypackage".startswith(
            SKIP_PREFIXES)

    def test_polygon_and_animation_packs_are_converted(self):
        for name in ("POLYGON_Dungeon_Unity_2021_3.unitypackage",
                     "ANIMATION_Sword_Combat_Unity_2021_1.unitypackage",
                     "INTERFACE_Fantasy_Menus_Unity_2022_3.unitypackage"):
            assert not name.startswith(SKIP_PREFIXES)

    def test_non_synty_packages_are_skipped(self):
        assert "ParrelSync-1.5.3.unitypackage".startswith(SKIP_PREFIXES)


class TestAddonEmission:
    def test_copies_every_addon_file(self, tmp_path, monkeypatch):
        source = tmp_path / "addon" / "synty_sidekick"
        (source / "nested").mkdir(parents=True)
        (source / "plugin.cfg").write_text("[plugin]", encoding="utf8")
        (source / "nested" / "x.gd").write_text("extends Node", encoding="utf8")
        monkeypatch.setattr("synty_library.ADDON_SOURCE", source)

        output = tmp_path / "project"
        assert install_addon(output) == 2
        assert (output / "addons" / "synty_sidekick" / "plugin.cfg").exists()
        assert (output / "addons" / "synty_sidekick" / "nested" / "x.gd").exists()

    def test_refreshes_on_rerun_so_fixes_reach_users(self, tmp_path, monkeypatch):
        source = tmp_path / "addon" / "synty_sidekick"
        source.mkdir(parents=True)
        (source / "plugin.cfg").write_text("new", encoding="utf8")
        monkeypatch.setattr("synty_library.ADDON_SOURCE", source)

        output = tmp_path / "project"
        target = output / "addons" / "synty_sidekick"
        target.mkdir(parents=True)
        (target / "plugin.cfg").write_text("old", encoding="utf8")

        install_addon(output)
        assert (target / "plugin.cfg").read_text(encoding="utf8") == "new"

    def test_missing_source_is_reported_not_silent(self, tmp_path, monkeypatch):
        monkeypatch.setattr("synty_library.ADDON_SOURCE", tmp_path / "absent")
        assert install_addon(tmp_path / "project") == 0

    def test_the_shipped_addon_is_where_the_default_points(self):
        import synty_library
        assert (synty_library.ADDON_SOURCE / "sidekick_character.gd").is_file()


class TestDegradationReport:
    def test_names_the_missing_sidekick_database(self, tmp_path):
        results = [{"pack": "SIDEKICK_Starter", "status": "ok"}]
        notes = collect_warnings(tmp_path, results)
        assert any("Side_Kick_Data.db" in n for n in notes)

    def test_silent_when_the_database_produced_adjustments(self, tmp_path):
        (tmp_path / "sidekick_rig_adjustments.json").write_text("{}", encoding="utf8")
        results = [{"pack": "SIDEKICK_Starter", "status": "ok"}]
        notes = collect_warnings(tmp_path, results)
        assert not any("Side_Kick_Data.db" in n for n in notes)

    def test_colour_tables_alone_prove_the_database_was_found(self, tmp_path):
        """Both files come from the database and from nothing else."""
        (tmp_path / "sidekick_colors.json").write_text("{}", encoding="utf8")
        results = [{"pack": "SIDEKICK_Starter", "status": "ok"}]
        assert collect_warnings(tmp_path, results) == []

    def test_the_note_names_every_cost_not_only_the_joints(self, tmp_path):
        """A clean run measured all three: no adjustments, no colour tables,
        and 15 name-derived gear sets in place of the database's hundreds."""
        notes = collect_warnings(tmp_path, [{"pack": "SIDEKICK_S", "status": "ok"}])
        note = " ".join(notes)
        assert "recolour" in note and "gear set" in note and "body size" in note

    def test_no_sidekick_packs_means_no_sidekick_note(self, tmp_path):
        results = [{"pack": "POLYGON_Dungeon", "status": "ok"}]
        assert collect_warnings(tmp_path, results) == []

    def test_names_packs_that_built_no_characters(self, tmp_path):
        results = [{"pack": "POLYGON_X", "status": "ok", "characters": 0,
                    "definitions": 18}]
        notes = collect_warnings(tmp_path, results)
        assert any("POLYGON_X" in n for n in notes)

    def test_a_pack_that_built_its_characters_is_not_named(self, tmp_path):
        results = [{"pack": "POLYGON_X", "status": "ok", "characters": 18,
                    "definitions": 18}]
        assert collect_warnings(tmp_path, results) == []


class TestPackCounts:
    def test_reads_both_numbers_from_a_log(self, tmp_path):
        log = tmp_path / "POLYGON_X.log"
        log.write_text(
            "Loaded 18 character definition(s) from character_definitions.json\n"
            'GODOT_SUMMARY {"characters_saved": 12, "errors": 0}\n',
            encoding="utf8",
        )
        assert _read_pack_counts(log) == {"characters": 12, "definitions": 18}

    def test_the_failure_this_shipped_for_months_is_visible(self, tmp_path):
        """Definitions loaded, none built - the get_basename() bug's signature."""
        log = tmp_path / "POLYGON_X.log"
        log.write_text(
            "Loaded 18 character definition(s)\n"
            'GODOT_SUMMARY {"characters_saved": 0}\n',
            encoding="utf8",
        )
        counts = _read_pack_counts(log)
        assert counts["definitions"] == 18 and counts["characters"] == 0

    def test_a_missing_log_is_not_an_error(self, tmp_path):
        assert _read_pack_counts(tmp_path / "absent.log") == {
            "characters": 0, "definitions": 0
        }

    def test_a_log_without_a_summary_line_reads_zero(self, tmp_path):
        log = tmp_path / "x.log"
        log.write_text("converter crashed\n", encoding="utf8")
        assert _read_pack_counts(log) == {"characters": 0, "definitions": 0}


class TestInProcessConversion:
    """convert_mesh_pack runs converter.py in this process, not a subprocess.

    These pin the two properties the subprocess gave for free: a crash confined
    to one pack, and a log complete enough for _read_pack_counts to read back.
    """

    @staticmethod
    def _args(tmp_path):
        return argparse.Namespace(
            output=tmp_path / "out",
            godot=tmp_path / "godot.exe",
            godot_timeout=60,
            retarget=True,
        )

    def test_a_converter_crash_fails_one_pack_not_the_run(self, tmp_path, monkeypatch):
        def explode(config):
            raise RuntimeError("the FBX importer fell over")

        monkeypatch.setattr("synty_library.run_conversion", explode)
        log = tmp_path / "P.log"
        ok, detail = convert_mesh_pack(
            tmp_path / "P.unitypackage", "P", tmp_path / "src",
            self._args(tmp_path), log,
        )
        assert ok is False
        assert "RuntimeError" in detail
        # The traceback has to reach the log, or the pack fails with no trail.
        assert "the FBX importer fell over" in log.read_text(encoding="utf8")

    def test_the_log_still_carries_the_numbers_the_warnings_need(
        self, tmp_path, monkeypatch
    ):
        """The counts are parsed out of the log, so in-process logging must
        capture the same DEBUG lines the subprocess's stdout did."""
        def convert(config):
            log = logging.getLogger("converter")
            log.debug("Loaded 18 character definition(s)")
            log.debug('GODOT_SUMMARY {"characters_saved": 18}')
            return converter_module.ConversionStats()

        monkeypatch.setattr("synty_library.run_conversion", convert)
        log = tmp_path / "P.log"
        ok, _ = convert_mesh_pack(
            tmp_path / "P.unitypackage", "P", tmp_path / "src",
            self._args(tmp_path), log,
        )
        assert ok is True
        assert _read_pack_counts(log) == {"characters": 18, "definitions": 18}

    def test_the_root_logger_is_left_as_it_was_found(self, tmp_path, monkeypatch):
        """The GUI shares this process and its own log pane hangs off the root
        logger, so a converted pack must not leave the level or handlers moved."""
        monkeypatch.setattr(
            "synty_library.run_conversion",
            lambda config: converter_module.ConversionStats(),
        )
        root = logging.getLogger()
        before_level = root.level
        before_handlers = list(root.handlers)

        convert_mesh_pack(
            tmp_path / "P.unitypackage", "P", tmp_path / "src",
            self._args(tmp_path), tmp_path / "P.log",
        )
        assert root.level == before_level
        assert root.handlers == before_handlers

    def test_reported_errors_fail_the_pack(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "synty_library.run_conversion",
            lambda config: converter_module.ConversionStats(errors=["no meshes"]),
        )
        ok, detail = convert_mesh_pack(
            tmp_path / "P.unitypackage", "P", tmp_path / "src",
            self._args(tmp_path), tmp_path / "P.log",
        )
        assert ok is False and "1 error" in detail

    def test_the_config_carries_the_settings_the_library_run_chose(
        self, tmp_path, monkeypatch
    ):
        seen = {}

        def capture(config):
            seen["config"] = config
            return converter_module.ConversionStats()

        monkeypatch.setattr("synty_library.run_conversion", capture)
        convert_mesh_pack(
            tmp_path / "P.unitypackage", "P", tmp_path / "src",
            self._args(tmp_path), tmp_path / "P.log",
        )
        config = seen["config"]
        # --animations all is what binds a library to a character, and
        # retargeting is what makes the binding hold.
        assert config.animations == "all"
        assert config.retarget is True
        assert config.verbose is True

    def test_converter_stdout_lands_in_the_log_not_the_summary(
        self, tmp_path, monkeypatch, capsys
    ):
        """The converter prints its banner and summary straight to stdout.

        The subprocess swallowed that into the same redirect; in-process it
        would otherwise print into the middle of this run's own summary.
        """
        def convert(config):
            print("Starting conversion: P.unitypackage")
            return converter_module.ConversionStats()

        monkeypatch.setattr("synty_library.run_conversion", convert)
        log = tmp_path / "P.log"
        convert_mesh_pack(
            tmp_path / "P.unitypackage", "P", tmp_path / "src",
            self._args(tmp_path), log,
        )
        assert "Starting conversion" not in capsys.readouterr().out
        assert "Starting conversion" in log.read_text(encoding="utf8")


class TestLibraryEntryPoint:
    """convert_library is what the GUI calls, so its commentary must be
    divertible - the GUI's log pane is not stdout."""

    @staticmethod
    def _args(tmp_path, **overrides):
        args = argparse.Namespace(
            packages=tmp_path / "packages",
            output=tmp_path / "out",
            godot=tmp_path / "godot.exe",
            unity_assets=None,
            work_dir=None,
            retarget=True,
            godot_timeout=600,
            force=False,
            only=None,
            dry_run=False,
        )
        for key, value in overrides.items():
            setattr(args, key, value)
        return args

    def test_every_line_goes_to_the_reporter_not_stdout(
        self, tmp_path, monkeypatch, capsys
    ):
        (tmp_path / "packages").mkdir()
        (tmp_path / "packages" / "POLYGON_X_Unity_2021_3_v1_0_0.unitypackage").touch()
        monkeypatch.setattr("synty_library.count_assets_by_suffix", lambda p: {".fbx": 9})
        monkeypatch.setattr(
            "synty_library.convert_mesh_pack",
            lambda *a, **k: (True, "see X.log"),
        )
        monkeypatch.setattr("synty_library.extract_fbx_to_directory", lambda p, d: 9)

        lines = []
        code = convert_library(self._args(tmp_path), report=lines.append)
        assert code == 0
        assert capsys.readouterr().out == ""
        assert any("POLYGON_X" in line for line in lines)

    def test_a_bad_work_dir_is_reported_and_stops_the_run(self, tmp_path):
        lines = []
        args = self._args(tmp_path, work_dir=tmp_path / "out" / "inside")
        assert convert_library(args, report=lines.append) == 2
        assert any("outside" in line for line in lines)

    def test_other_handlers_are_spared_the_debug_flood(self, tmp_path, monkeypatch):
        """The file log needs DEBUG, but the GUI's log pane hangs off the same
        root logger with its own level."""
        pane = logging.Handler()
        pane.setLevel(logging.INFO)
        seen = []
        pane.emit = lambda record: seen.append(record.levelno)
        root = logging.getLogger()
        root.addHandler(pane)
        try:
            def convert(config):
                logging.getLogger("converter").debug("a debug line")
                logging.getLogger("converter").info("an info line")
                return converter_module.ConversionStats()

            monkeypatch.setattr("synty_library.run_conversion", convert)
            log = tmp_path / "P.log"
            convert_mesh_pack(
                tmp_path / "P.unitypackage", "P", tmp_path / "src",
                self._args(tmp_path), log,
            )
        finally:
            root.removeHandler(pane)

        assert logging.DEBUG not in seen, "debug lines reached the GUI pane"
        assert logging.INFO in seen, "the pane stopped seeing normal progress"
        # The file still gets everything.
        assert "a debug line" in log.read_text(encoding="utf8")
        assert pane.level == logging.INFO, "the pane's level was not restored"


class TestSidekickDatabaseDiscovery:
    """Synty's tool database does not live in a pack's own folder.

    It installs as SidekickCharacters/, matching no pack name, so the per-pack
    Unity lookup never finds it.
    """

    def test_the_database_is_found_under_the_unity_assets_root(self, tmp_path):
        assets = tmp_path / "Synty"
        database = assets / "SidekickCharacters" / "Database" / "Side_Kick_Data.db"
        database.parent.mkdir(parents=True)
        database.write_bytes(b"SQLite format 3\x00")
        assert find_sidekick_database([assets]) == database

    def test_the_per_pack_lookup_does_not_find_it(self, tmp_path):
        """Why this needed fixing: the pack folder and the tool folder are
        siblings, and only the pack folder was ever searched."""
        assets = tmp_path / "Synty"
        (assets / "SidekickCharacters" / "Database").mkdir(parents=True)
        (assets / "SidekickCharacters" / "Database" / "Side_Kick_Data.db").touch()
        pack = assets / "SidekickStarter" / "Models"
        pack.mkdir(parents=True)
        (pack / "a.fbx").touch()
        (pack / "b.fbx").touch()

        found = find_unity_source("SIDEKICK_Starter", assets)
        assert found == assets / "SidekickStarter"
        assert find_sidekick_database([found]) is None

    def test_the_config_carries_the_database_to_the_converter(
        self, tmp_path, monkeypatch
    ):
        assets = tmp_path / "Synty"
        database = assets / "SidekickCharacters" / "Database" / "Side_Kick_Data.db"
        database.parent.mkdir(parents=True)
        database.touch()

        seen = {}

        def capture(config):
            seen["config"] = config
            return converter_module.ConversionStats()

        monkeypatch.setattr("synty_library.run_conversion", capture)
        args = argparse.Namespace(
            output=tmp_path / "out", godot=tmp_path / "godot.exe",
            godot_timeout=60, retarget=True, unity_assets=assets,
        )
        convert_mesh_pack(
            tmp_path / "SIDEKICK_Starter.unitypackage", "SIDEKICK_Starter",
            tmp_path / "src", args, tmp_path / "P.log",
        )
        assert seen["config"].sidekick_database == database

    def test_no_unity_assets_means_no_database_and_no_error(self, tmp_path, monkeypatch):
        seen = {}

        def capture(config):
            seen["config"] = config
            return converter_module.ConversionStats()

        monkeypatch.setattr("synty_library.run_conversion", capture)
        args = argparse.Namespace(
            output=tmp_path / "out", godot=tmp_path / "godot.exe",
            godot_timeout=60, retarget=True, unity_assets=None,
        )
        convert_mesh_pack(
            tmp_path / "P.unitypackage", "P", tmp_path / "src", args,
            tmp_path / "P.log",
        )
        assert seen["config"].sidekick_database is None

    def test_the_master_palette_is_found_beside_the_database(self, tmp_path):
        """Both live in the tool folder, and neither in any pack's folder.

        Finding the database but not the palette leaves recolouring disabled
        for a user who has everything needed for it.
        """
        from sidekick import find_master_color_map

        tool = tmp_path / "Synty" / "SidekickCharacters"
        database = tool / "Database" / "Side_Kick_Data.db"
        database.parent.mkdir(parents=True)
        database.touch()
        palette = tool / "Resources" / "Textures" / "T_ColorMap.png"
        palette.parent.mkdir(parents=True)
        palette.touch()
        # The decoy under _Demos is a different texture with the same name.
        decoy = tool / "_Demos" / "Textures" / "T_ColorMap.png"
        decoy.parent.mkdir(parents=True)
        decoy.touch()

        # The tool root is the database's grandparent: Database/<db>.
        assert find_master_color_map([database.parent.parent]) == palette


class TestStalePackRefresh:
    """An existing pack's output folder is not proof that it is up to date.

    converter.py stamps each pack with the metadata schema it was written
    against and refreshes a stale one without re-copying its FBX. The library
    driver skipped on the folder alone, so the whole mechanism never fired for
    anyone converting through it - every fix since their last run stayed
    invisible until they passed --force and paid for a full re-extract.
    """

    def _pack(self, tmp_path, version):
        import json

        pack = tmp_path / "POLYGON_Dungeon"
        pack.mkdir(parents=True)
        if version is not None:
            (pack / "pack_metadata.json").write_text(
                json.dumps({"schema_version": version})
            )
        return tmp_path

    def test_current_pack_is_skipped(self, tmp_path):
        output = self._pack(tmp_path, converter_module.PACK_METADATA_VERSION)
        assert needs_conversion(output, "POLYGON_Dungeon", force=False) is False

    def test_stale_pack_is_converted(self, tmp_path):
        output = self._pack(tmp_path, converter_module.PACK_METADATA_VERSION - 1)
        assert needs_conversion(output, "POLYGON_Dungeon", force=False) is True

    def test_ui_pack_without_metadata_is_skipped(self, tmp_path):
        """UI and animation packs write no metadata, and re-running those on
        every invocation would be a surprise."""
        output = self._pack(tmp_path, None)
        assert needs_conversion(output, "POLYGON_Dungeon", force=False) is False

    def test_mesh_pack_without_metadata_is_converted(self, tmp_path):
        """A mesh pack with no stamp predates the stamp, so it is the stalest
        output there is - POLYGON_Dungeon in a real library was exactly this."""
        output = self._pack(tmp_path, None)
        (output / "POLYGON_Dungeon" / "mesh_material_mapping.json").write_text("{}")
        assert needs_conversion(output, "POLYGON_Dungeon", force=False) is True

    def test_missing_pack_is_converted(self, tmp_path):
        assert needs_conversion(tmp_path, "POLYGON_Nothing", force=False) is True

    def test_force_converts_a_current_pack(self, tmp_path):
        output = self._pack(tmp_path, converter_module.PACK_METADATA_VERSION)
        assert needs_conversion(output, "POLYGON_Dungeon", force=True) is True
