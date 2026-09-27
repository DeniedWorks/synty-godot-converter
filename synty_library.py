"""Convert a whole Synty library into a working Godot project, in one command.

`converter.py` converts one pack and has to be told where that pack's meshes
live. Across a library that becomes three decisions per pack, all mechanical:

- **Which packs are left?** A pack whose folder already exists under the output
  has been converted, so a re-run resumes rather than starting over.
- **Where are its meshes?** A pack imported into Unity can be read from there
  directly; one that was not has its FBX written out of the `.unitypackage`
  first, which is all Unity's import does for a mesh. No Unity install is
  needed for any of it.
- **Does it have meshes at all?** The INTERFACE packs are thousands of UI
  sprites and almost no FBX, so they take a second route that writes their
  sprites into the project, where Godot imports them as textures unaided.

Usage:
    python synty_library.py \
        --packages "C:/Users/me/Downloads" \
        --godot "Godot_v4.4-stable_win64_console.exe" \
        --output "MyGodotProject"

Two orderings matter. Animation packs convert first, because `--animations all`
binds their libraries to characters in later packs and a library that does not
exist yet cannot be bound. And rigs are retargeted onto a common humanoid
profile as they go, because a clip poses only the rig whose rest orientations it
was authored against - without that, Synty's character rigs and clip rigs
disagree and binding collapses the character rather than animating it.

Supported character rigs are Polygon and Sidekick. Anything else converts as
meshes and binds no clips, deliberately: guessing a mapping for an unknown rig
produces a mangled character rather than an unanimated one.
"""

import argparse
import contextlib
import json
import logging
import re
import shutil
import sys
import time
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from converter import (  # noqa: E402
    PACK_METADATA_FILENAME,
    ConversionConfig,
    extract_pack_name_from_package,
    pack_metadata_is_current,
    run_conversion,
)
from sidekick import find_sidekick_database  # noqa: E402
from unity_package import (  # noqa: E402
    count_assets_by_suffix,
    extract_assets_to_directory,
    extract_fbx_to_directory,
)

REPO_ROOT = Path(__file__).resolve().parent

# Packages that are not Synty asset packs at all.
SKIP_PREFIXES = ("ParrelSync",)

# The Sidekick runtime, copied into every project that converts a SIDEKICK pack.
ADDON_SOURCE = REPO_ROOT / "addon" / "synty_sidekick"


def install_addon(output: Path, report: Callable[[str], None] = print) -> int:
    """Copies the Sidekick addon into the converted project.

    Refreshed on every run, so a user's own edits inside the emitted
    addons/synty_sidekick/ are overwritten - the addon's README says so.

    Args:
        output: The Godot project directory being built.
        report: Called with each line of progress. Defaults to print; the GUI
            passes one that writes to its log pane instead.

    Returns:
        Files copied. Zero means the addon source was missing, and is reported.
    """
    if not ADDON_SOURCE.is_dir():
        report(f"WARNING: Sidekick addon source not found at {ADDON_SOURCE}")
        return 0

    destination = output / "addons" / "synty_sidekick"
    copied = 0
    for source_file in ADDON_SOURCE.rglob("*"):
        if source_file.is_dir():
            continue
        target = destination / source_file.relative_to(ADDON_SOURCE)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target)
        copied += 1
    return copied


def normalise(name: str) -> str:
    """Reduces a pack or folder name to a form the two conventions share.

    A package is named `POLYGON_Dungeon_Realms` and its Unity import folder
    `PolygonDungeonRealms`; dropping separators and case makes them equal.
    """
    return "".join(c for c in name.lower() if c.isalnum())


# Below this a Unity folder is a partial import - full directory structure,
# almost no meshes - and the .unitypackage is the better source.
MIN_UNITY_SOURCE_FBX = 2


def find_unity_source(pack_name: str, unity_assets: Path | None) -> Path | None:
    """Locates a pack's already-imported Unity folder, if it has a usable one.

    A Unity project is an accelerator, not a requirement; without one a pack is
    read from its .unitypackage. A folder must hold real meshes to be preferred,
    since a partial import silently loses whatever it is missing.
    """
    if unity_assets is None or not unity_assets.is_dir():
        return None
    target = normalise(pack_name)
    for candidate in unity_assets.iterdir():
        if not candidate.is_dir() or normalise(candidate.name) != target:
            continue
        found = 0
        for _ in candidate.rglob("*.fbx"):
            found += 1
            if found >= MIN_UNITY_SOURCE_FBX:
                return candidate
        return None
    return None


# A pack's PNGs are a sprite set rather than mesh textures once they outnumber
# its meshes by this much: a UI pack ships thousands of sprites and a few FBX.
SPRITE_DOMINANCE = 10


def has_meshes(counts: dict[str, int]) -> bool:
    """True when a pack has meshes for the converter to work on."""
    return counts.get(".fbx", 0) > 0


def has_sprites(counts: dict[str, int]) -> bool:
    """True when a pack's images are a UI sprite set, not mesh textures.

    The routes are not exclusive - a UI pack also ships a few demo-scene meshes -
    so this is about dominance, not the absence of FBX.
    """
    pngs = counts.get(".png", 0)
    return pngs > 0 and pngs > counts.get(".fbx", 0) * SPRITE_DOMINANCE


def is_animation_pack(counts: dict[str, int]) -> bool:
    """True for a pack that is mostly animation clips rather than assets."""
    return counts.get(".anim", 0) > 0 and counts.get(".fbx", 0) > 0


def resolve_work_dir(output: Path, work_dir: Path | None) -> Path:
    """Decides where FBX extracted from packages are staged.

    Godot imports everything beneath its project root, so this must sit outside
    the output or every mesh is imported twice.

    Raises:
        ValueError: The chosen directory is the project, or lies within it.
    """
    if work_dir is not None:
        resolved = work_dir
    else:
        resolved = output.parent / (output.name + "_synty_work")
    output_abs = output.resolve()
    resolved_abs = resolved.resolve()
    if resolved_abs == output_abs or output_abs in resolved_abs.parents:
        raise ValueError(
            "work directory must sit outside the Godot project: %s" % resolved)
    return resolved


def convert_ui_pack(package: Path, pack_name: str, output: Path) -> tuple[bool, str]:
    """Writes a UI pack's sprites where Godot imports them as textures unaided.

    Synty's folder structure is kept so sprite sets stay together.
    """
    destination = output / pack_name / "ui"
    try:
        written = extract_assets_to_directory(
            package, destination, {".png"}, strip_prefix="Assets/Synty/"
        )
    except Exception as error:  # noqa: BLE001 - reported per pack, never fatal
        return False, f"sprite extraction failed: {error}"
    if written == 0:
        return False, "no sprites written"
    return True, f"{written} sprites -> {destination}"


def convert_mesh_pack(
    package: Path,
    pack_name: str,
    source: Path,
    args: argparse.Namespace,
    log_path: Path,
) -> tuple[bool, str]:
    """Converts one pack in this process, logging it to a per-pack file.

    In-process rather than a subprocess so a PyInstaller build works, which has
    no interpreter to re-launch. A crash therefore fails one pack rather than
    the run, and the log is complete enough for _read_pack_counts to read back.
    """
    # The tool database installs as SidekickCharacters/, matching no pack name,
    # so only a search of the whole --unity-assets root finds it.
    database = None
    if getattr(args, "unity_assets", None):
        database = find_sidekick_database([args.unity_assets])

    config = ConversionConfig(
        unity_package=package,
        source_files=source,
        output_dir=args.output,
        godot_exe=args.godot,
        godot_timeout=args.godot_timeout,
        sidekick_database=database,
        animations="all",
        retarget=args.retarget,
        verbose=True,
    )

    # The converter prints its banner and summary outside logging, so stdout is
    # redirected into the same file rather than into this run's own summary.
    log_file = log_path.open("w", encoding="utf8", errors="replace")
    handler = logging.StreamHandler(log_file)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    handler.setLevel(logging.DEBUG)
    # DEBUG is needed for a complete log file, but the GUI's log pane hangs off
    # the same root logger: hold other handlers at INFO, and restore everything.
    root = logging.getLogger()
    previous_level = root.level
    muted = [(h, h.level) for h in root.handlers if h.level < logging.INFO]
    for other, _ in muted:
        other.setLevel(logging.INFO)
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        with contextlib.redirect_stdout(log_file):
            stats = run_conversion(config)
    except Exception as error:  # noqa: BLE001 - one pack's crash, not the run's
        logging.getLogger(__name__).exception(
            "Converting %s raised %s", pack_name, type(error).__name__
        )
        return False, (
            f"converter raised {type(error).__name__}: {error}, see {log_path.name}"
        )
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)
        for other, level in muted:
            other.setLevel(level)
        log_file.close()

    if stats.errors:
        return False, f"{len(stats.errors)} error(s), see {log_path.name}"
    return True, f"see {log_path.name}"


def _read_pack_counts(log_path: Path) -> dict:
    """Pulls the two numbers the warning report needs out of a pack's log.

    characters_saved comes from GODOT_SUMMARY; the count of declared definitions
    is only printed as prose. The pair distinguishes "no characters here" from
    "the characters failed to build".
    """
    counts = {"characters": 0, "definitions": 0}
    try:
        text = log_path.read_text(encoding="utf8", errors="replace")
    except OSError:
        return counts
    summary = re.findall(r"GODOT_SUMMARY (\{.*\})", text)
    if summary:
        try:
            counts["characters"] = int(json.loads(summary[-1]).get("characters_saved", 0))
        except (ValueError, TypeError):
            pass
    declared = re.findall(r"Loaded (\d+) character definition", text)
    if declared:
        counts["definitions"] = max(int(n) for n in declared)
    return counts


def collect_warnings(output: Path, results: list[dict]) -> list[str]:
    """Names the degradations a user would otherwise discover by accident.

    A run reporting only counts reads as success even when a pack built no
    characters.
    """
    notes: list[str] = []

    converted_sidekick = any(
        r.get("pack", "").startswith("SIDEKICK_") and r.get("status") in ("ok", "partial")
        for r in results
    )
    # Both files come from Side_Kick_Data.db and nothing else, so either one
    # present means the database was found.
    found_database = (
        (output / "sidekick_rig_adjustments.json").exists()
        or (output / "sidekick_colors.json").exists()
    )
    if converted_sidekick and not found_database:
        notes.append(
            "Side_Kick_Data.db was not found. Characters build and animate "
            "without it, but three things degrade: attachment joints do not "
            "follow body size (a large character's backpack sits where a small "
            "one's would), recolouring is unavailable because the colour tables "
            "come from the database - and since Synty's base body parts carry "
            "no colour of their own, a bare body renders plain white - and gear "
            "sets fall back to what part names imply, which is tens of sets "
            "rather than hundreds, and cannot tell that two families share a "
            "bare torso. Characters still assemble, animate and mix by region. "
            "The "
            "database ships with Synty's Sidekick Unity tool, never inside a "
            ".unitypackage; pass its folder as --unity-assets to pick it up."
        )

    for record in results:
        if record.get("definitions", 0) and not record.get("characters", 0):
            notes.append(
                "%s declared %d character definition(s) and built none - its "
                "meshes converted as static props."
                % (record["pack"], record["definitions"])
            )
    return notes


def needs_conversion(output: Path, pack_name: str, force: bool) -> bool:
    """Whether a pack has to be converted, or can be left as it stands.

    An output folder alone does not mean a pack is up to date. converter.py
    stamps each one with the metadata schema it was written against and
    refreshes a stale pack cheaply, re-deriving everything but the FBX copy -
    so a pack whose stamp has fallen behind is converted rather than skipped,
    and the fixes made since its last run reach it without --force.

    A mesh pack carrying no stamp at all is the oldest conversion of the lot -
    it predates the stamp - so it is stale too. UI and animation packs never
    write one, and re-running those on every invocation would be a surprise;
    mesh_material_mapping.json is what tells the two apart, since only a mesh
    pack writes it.

    Args:
        output: The Godot project directory being built.
        pack_name: Pack folder name within it.
        force: Convert regardless.

    Returns:
        True when the pack should be converted.
    """
    pack_output = output / pack_name
    if force or not pack_output.exists():
        return True
    if (pack_output / PACK_METADATA_FILENAME).exists():
        return not pack_metadata_is_current(pack_output)
    return (pack_output / "mesh_material_mapping.json").exists()


def process(package: Path, args: argparse.Namespace, log_dir: Path) -> dict:
    """Converts one package by whichever route its contents call for."""
    pack_name = extract_pack_name_from_package(package)
    started = time.monotonic()
    record = {"package": package.name, "pack": pack_name}

    if not needs_conversion(args.output, pack_name, args.force):
        record.update(status="skipped", detail="already converted", seconds=0.0)
        return record

    counts = count_assets_by_suffix(package)
    routes: list[str] = []
    details: list[str] = []
    sprites_ok: bool | None = None
    meshes_ok: bool | None = None

    if has_sprites(counts):
        routes.append("ui")
        sprites_ok, detail = convert_ui_pack(package, pack_name, args.output)
        details.append(detail)

    if has_meshes(counts):
        source = find_unity_source(pack_name, args.unity_assets)
        if source is not None:
            routes.append("unity")
        else:
            routes.append("extracted")
            source = args.extract_dir / pack_name
            if not source.exists() or args.force:
                extract_fbx_to_directory(package, source)
        log_path = log_dir / f"{pack_name}.log"
        meshes_ok, detail = convert_mesh_pack(
            package, pack_name, source, args, log_path
        )
        details.append(detail)
        record.update(_read_pack_counts(log_path))

    if not routes:
        details.append("no meshes and no sprites")

    record.update(
        route="+".join(routes),
        status=_status(sprites_ok, meshes_ok),
        detail="; ".join(details),
        seconds=round(time.monotonic() - started, 1),
    )
    return record


def _status(sprites_ok: bool | None, meshes_ok: bool | None) -> str:
    """Grades a pack that took both routes on what each route achieved.

    A UI pack's few demo-scene meshes have no material mapping to derive - its
    prefabs carry no renderer - so the mesh route fails where there was never
    anything to convert. Calling the whole pack failed buries the 2205 sprites
    that did convert; calling it ok hides that something went wrong.
    """
    attempted = [ok for ok in (sprites_ok, meshes_ok) if ok is not None]
    if not attempted:
        return "failed"
    if all(attempted):
        return "ok"
    if any(attempted):
        return "partial"
    return "failed"


def convert_library(
    args: argparse.Namespace, report: Callable[[str], None] = print
) -> int:
    """Converts every package in a folder into one Godot project.

    Shared by the CLI and the GUI, which differ only in where progress goes.

    Args:
        args: Parsed arguments, or any namespace carrying the same fields.
        report: Called with each line of progress. Defaults to print; the GUI
            passes one that writes to its log pane instead.

    Returns:
        Process exit code - non-zero when any pack failed.
    """

    try:
        args.extract_dir = resolve_work_dir(args.output, args.work_dir)
    except ValueError as error:
        report("ERROR: %s" % error)
        return 2

    packages = [
        p for p in sorted(args.packages.glob("*.unitypackage"))
        if not p.name.startswith(SKIP_PREFIXES)
    ]
    if args.only:
        wanted = [s.strip().lower() for s in args.only.split(",") if s.strip()]
        packages = [p for p in packages if any(w in p.name.lower() for w in wanted)]

    # Animation libraries must exist before --animations can bind them.
    packages.sort(key=lambda p: (not p.name.startswith("ANIMATION_"), p.name))

    if not packages:
        report("Nothing to convert.")
        return 0

    log_dir = args.output / "conversion_logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        for package in packages:
            pack_name = extract_pack_name_from_package(package)
            if not needs_conversion(args.output, pack_name, args.force):
                route = "skipped (already converted)"
            else:
                counts = count_assets_by_suffix(package)
                parts = []
                if has_sprites(counts):
                    parts.append(f"ui ({counts.get('.png', 0)} sprites)")
                if has_meshes(counts):
                    where = (
                        "unity"
                        if find_unity_source(pack_name, args.unity_assets)
                        else "extracted"
                    )
                    parts.append(f"{where} ({counts.get('.fbx', 0)} fbx)")
                route = " + ".join(parts) or "nothing convertible"
            report(f"{pack_name:<44} {route}")
        return 0

    report(f"Converting {len(packages)} packs into {args.output}\n")
    results = []
    for index, package in enumerate(packages, start=1):
        report(f"[{index}/{len(packages)}] {package.name}")
        record = process(package, args, log_dir)
        results.append(record)
        report(
            f"    {record['status']}: {record['detail']} ({record['seconds']}s)"
        )
        (log_dir / "convert_all_results.json").write_text(
            json.dumps(results, indent=2), encoding="utf8"
        )

    # A library with no Sidekick packs has no parts index for the addon to read.
    # "skipped" counts, so a resume run still refreshes the addon.
    if any(
        r["package"].startswith("SIDEKICK_")
        and r["status"] in ("ok", "partial", "skipped")
        for r in results
    ):
        copied = install_addon(args.output, report)
        if copied:
            report(
                f"\nSidekick addon: {copied} files -> "
                f"{args.output / 'addons' / 'synty_sidekick'}"
            )

    report("\n=== Summary ===")
    for status in ("ok", "partial", "failed", "skipped"):
        matching = [r for r in results if r["status"] == status]
        if matching:
            report(f"\n{status.upper()} ({len(matching)}):")
            for record in matching:
                report(f"  {record['pack']:<44} {record['detail']}")

    notes = collect_warnings(args.output, results)
    if notes:
        report("\nWarnings:")
        for note in notes:
            report(f"  - {note}")

    failed = sum(1 for r in results if r["status"] == "failed")
    partial = sum(1 for r in results if r["status"] == "partial")
    total = sum(r["seconds"] for r in results)
    report(
        f"\n{len(results)} packs, {failed} failed, {partial} partial, "
        f"{total / 60:.1f} minutes"
    )
    return 1 if failed else 0


def main() -> int:
    """CLI entry point.

    Returns:
        Process exit code - non-zero when any pack failed.
    """
    parser = argparse.ArgumentParser(
        description="Convert a whole Synty library into a Godot project, in one command.",
    )
    parser.add_argument("--packages", type=Path, required=True,
                        help="Directory holding your .unitypackage files")
    parser.add_argument("--godot", type=Path, required=True,
                        help="Path to the Godot console executable "
                             "(the _console.exe variant on Windows)")
    parser.add_argument("--output", type=Path, required=True,
                        help="Godot project directory to build")
    parser.add_argument("--unity-assets", type=Path, default=None,
                        help="Optional. A Unity project's Assets/Synty, used as the "
                             "mesh source for packs already imported there. Without "
                             "it every pack is read from its .unitypackage, which "
                             "needs no Unity install.")
    parser.add_argument("--work-dir", type=Path, default=None,
                        help="Where to stage FBX extracted from packages. Defaults "
                             "beside --output, and must sit outside the Godot "
                             "project or Godot imports every mesh twice.")
    parser.add_argument("--no-retarget", dest="retarget", action="store_false",
                        help="Skip rig retargeting. Characters still convert, but "
                             "animation clips will not bind to them.")
    parser.set_defaults(retarget=True)
    parser.add_argument("--godot-timeout", type=int, default=3600,
                        help="Per-pack Godot timeout in seconds (default: 3600)")
    parser.add_argument("--force", action="store_true",
                        help="Re-convert packs whose output folder already exists")
    parser.add_argument("--only", type=str, default=None,
                        help="Comma-separated substrings; convert only matching packages")
    parser.add_argument("--dry-run", action="store_true",
                        help="List what would be converted, by which route, and stop")
    args = parser.parse_args()
    return convert_library(args)


if __name__ == "__main__":
    sys.exit(main())
