"""Tests for pruning a pack's staging FBX after conversion.

models/ is input, not output: the generated scenes embed their mesh data and
reference only materials, so nothing points at an FBX once conversion is done.
On a shared source pool the directory is also the same bytes in every pack -
2.4 GB across seven Sidekick packs here.

Pruning is only ever safe when mesh generation actually succeeded; otherwise it
would delete the inputs needed to retry.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from converter import ConversionStats, prune_pack_models, should_prune_models  # noqa: E402


def _pack_with_models(tmp_path):
    """A pack whose models/ holds FBX plus the textures Godot extracted.

    Godot's FBX importer writes a mesh's embedded textures out beside it, and
    the generated scenes reference those by path.
    """
    models = tmp_path / "models"
    (models / "Nested").mkdir(parents=True)
    (models / "A.fbx").write_bytes(b"fbx")
    (models / "A.fbx.import").write_text("x", encoding="utf-8")
    (models / "A_0.png").write_bytes(b"png")
    (models / "A_0.png.import").write_text("x", encoding="utf-8")
    (models / "Nested" / "B.fbx").write_bytes(b"fbx")
    (tmp_path / "meshes").mkdir()
    return tmp_path


def _stats(**kwargs):
    stats = ConversionStats()
    stats.godot_import_success = kwargs.get("import_ok", True)
    stats.godot_convert_success = kwargs.get("convert_ok", True)
    stats.godot_timeout_occurred = kwargs.get("timed_out", False)
    stats.meshes_converted = kwargs.get("meshes", 5)
    stats.errors = list(kwargs.get("errors", []))
    return stats


class TestShouldPruneModels:
    def test_prunes_after_a_clean_conversion(self):
        assert should_prune_models(_stats()) is True

    def test_refuses_when_no_meshes_were_generated(self):
        """Nothing was produced, so the inputs are still needed."""
        assert should_prune_models(_stats(meshes=0)) is False

    def test_refuses_after_a_timeout(self):
        assert should_prune_models(_stats(timed_out=True)) is False

    def test_refuses_when_import_failed(self):
        assert should_prune_models(_stats(import_ok=False)) is False

    def test_refuses_when_errors_were_recorded(self):
        assert should_prune_models(_stats(errors=["Godot converter script failed"])) is False

    def test_prunes_on_partial_convert_with_meshes(self):
        """Godot reporting a non-zero exit still leaves usable output."""
        assert should_prune_models(_stats(convert_ok=False)) is True


class TestPrunePackModels:
    def test_removes_every_fbx_including_nested(self, tmp_path):
        pack = _pack_with_models(tmp_path)
        assert prune_pack_models(pack) == 2
        assert list((pack / "models").rglob("*.fbx")) == []

    def test_removes_the_fbx_import_sidecar(self, tmp_path):
        pack = _pack_with_models(tmp_path)
        prune_pack_models(pack)
        assert not (pack / "models" / "A.fbx.import").exists()

    def test_keeps_extracted_textures(self, tmp_path):
        """Scenes reference these by path; deleting them breaks loading."""
        pack = _pack_with_models(tmp_path)
        prune_pack_models(pack)
        assert (pack / "models" / "A_0.png").read_bytes() == b"png"
        assert (pack / "models" / "A_0.png.import").exists()

    def test_keeps_models_dir_when_textures_remain(self, tmp_path):
        pack = _pack_with_models(tmp_path)
        prune_pack_models(pack)
        assert (pack / "models").is_dir()

    def test_removes_directories_left_empty(self, tmp_path):
        pack = _pack_with_models(tmp_path)
        prune_pack_models(pack)
        assert not (pack / "models" / "Nested").exists()

    def test_leaves_generated_output_alone(self, tmp_path):
        pack = _pack_with_models(tmp_path)
        prune_pack_models(pack)
        assert (pack / "meshes").is_dir()

    def test_absent_directory_is_not_an_error(self, tmp_path):
        assert prune_pack_models(tmp_path) == 0

    def test_already_pruned_pack_is_a_no_op(self, tmp_path):
        pack = _pack_with_models(tmp_path)
        prune_pack_models(pack)
        assert prune_pack_models(pack) == 0

    def test_dry_run_keeps_everything(self, tmp_path):
        pack = _pack_with_models(tmp_path)
        assert prune_pack_models(pack, dry_run=True) == 0
        assert (pack / "models" / "A.fbx").exists()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
