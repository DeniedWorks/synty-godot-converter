"""Tests for parsing what godot_converter.gd reports about its own run.

Everything the Godot script prints is logged at debug level and otherwise
ignored, so a run could end with the Python summary saying "Warnings: 1"
while the Godot side had failed on dozens of meshes. The script now ends with
a machine-readable GODOT_SUMMARY line; these tests cover reading it.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from converter import (  # noqa: E402
    MAX_GODOT_MESSAGES,
    ConversionStats,
    GodotRunReport,
    parse_godot_summary,
    print_summary,
)

LINE = (
    'GODOT_SUMMARY {"meshes_saved":1273,"meshes_skipped":4,'
    '"characters_saved":18,"animations_bound":0,"warnings":2,"errors":33}'
)


class TestParseGodotSummary:
    def test_parses_every_field(self):
        report = GodotRunReport()
        assert parse_godot_summary(LINE, report) is True
        assert (report.meshes_saved, report.meshes_skipped) == (1273, 4)
        assert (report.characters_saved, report.animations_bound) == (18, 0)
        assert (report.warnings, report.errors) == (2, 33)
        assert report.seen is True

    def test_tolerates_surrounding_whitespace(self):
        report = GodotRunReport()
        assert parse_godot_summary("  " + LINE + "  \n", report) is True
        assert report.errors == 33

    def test_ignores_unrelated_lines(self):
        report = GodotRunReport()
        assert parse_godot_summary("[1/830] Processing: Chr_Hero.fbx", report) is False
        assert report.seen is False

    def test_malformed_json_is_not_seen(self):
        report = GodotRunReport()
        assert parse_godot_summary("GODOT_SUMMARY {nope", report) is False
        assert report.seen is False

    def test_non_object_json_is_rejected(self):
        report = GodotRunReport()
        assert parse_godot_summary("GODOT_SUMMARY [1,2]", report) is False
        assert report.seen is False

    def test_missing_keys_default_to_zero(self):
        report = GodotRunReport()
        assert parse_godot_summary('GODOT_SUMMARY {"errors":7}', report) is True
        assert report.errors == 7
        assert report.meshes_saved == 0

    def test_non_numeric_value_is_ignored(self):
        report = GodotRunReport()
        parse_godot_summary('GODOT_SUMMARY {"errors":"lots"}', report)
        assert report.errors == 0

    def test_unseen_report_defaults_to_zero(self):
        """A zero count on an unseen report means 'not parsed', not 'none'."""
        report = GodotRunReport()
        assert report.seen is False
        assert (report.errors, report.warnings, report.meshes_saved) == (0, 0, 0)


class TestSummaryMessages:
    """The script carries its own message texts out in the summary line.

    They cannot be recovered by matching console text: the engine writes
    "ERROR:"/"WARNING:" lines worded just like the script's, so a text match
    quotes engine noise as though it were one of the counted failures.
    """

    def test_parses_messages(self):
        report = GodotRunReport()
        parse_godot_summary(
            'GODOT_SUMMARY {"errors":2,"messages":["ERROR: a","ERROR: b"]}',
            report,
        )
        assert report.messages == ["ERROR: a", "ERROR: b"]

    def test_absent_messages_leave_list_empty(self):
        report = GodotRunReport()
        parse_godot_summary('GODOT_SUMMARY {"errors":2}', report)
        assert report.messages == []

    def test_non_list_messages_is_ignored(self):
        report = GodotRunReport()
        parse_godot_summary('GODOT_SUMMARY {"messages":"oops"}', report)
        assert report.messages == []

    def test_messages_are_capped(self):
        flood = ",".join(f'"ERROR: {i}"' for i in range(MAX_GODOT_MESSAGES + 10))
        report = GodotRunReport()
        parse_godot_summary(f'GODOT_SUMMARY {{"messages":[{flood}]}}', report)
        assert len(report.messages) == MAX_GODOT_MESSAGES


class TestPrintSummaryShowsGodotCounts:
    def _output(self, capsys, stats):
        print_summary(stats)
        return capsys.readouterr().out

    def test_reports_godot_errors(self, capsys):
        stats = ConversionStats()
        parse_godot_summary(LINE, stats.godot_report)
        stats.godot_report.messages = ["ERROR: Chr_Nomad produced no meshes"]
        out = self._output(capsys, stats)
        assert "Godot Errors: 33" in out
        assert "Chr_Nomad produced no meshes" in out

    def test_reports_characters(self, capsys):
        stats = ConversionStats()
        parse_godot_summary(LINE, stats.godot_report)
        assert "Characters: 18 rigged" in self._output(capsys, stats)

    def test_silent_when_godot_did_not_run(self, capsys):
        out = self._output(capsys, ConversionStats())
        assert "Godot Errors" not in out
        assert "Characters:" not in out

    def test_silent_when_godot_reported_nothing_wrong(self, capsys):
        stats = ConversionStats()
        parse_godot_summary(
            'GODOT_SUMMARY {"meshes_saved":10,"errors":0,"warnings":0}',
            stats.godot_report,
        )
        out = self._output(capsys, stats)
        assert "Godot Errors" not in out
        assert "Godot Warnings" not in out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
