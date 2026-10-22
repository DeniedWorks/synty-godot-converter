"""
Asset Store Package Support Module.

Synty's Unity Asset Store downloads are a single .unitypackage with no
SourceFiles folder. This module rebuilds what the converter expects from
SourceFiles using only the package:

    package.unitypackage
        ├── *.fbx      ──────────────► <dest>/FBX/*.fbx
        ├── *.prefab ─┐
        ├── *.mat    ─┼─────────────► <dest>/MaterialList.txt
        └── *.meta   ─┴─ globalScale ► per-FBX scale for Godot's .import files

MaterialList.txt Reconstruction:
    Each prefab links meshes to materials in one of two ways:
    - A MeshFilter/SkinnedMeshRenderer (mesh) plus a renderer (materials)
      on the same GameObject.
    - A PrefabInstance of an FBX whose m_Modifications override
      m_Materials.Array.data[i].

    Mesh names come from the FBX .meta internalIDToNameTable. Unity 2020+
    leaves that table empty, so the GameObject name is used instead; Synty
    names each GameObject after its mesh.

    Meshes no prefab uses (orphaned or legacy FBX files) get the pack's
    most-used material, which for Synty packs is the main texture atlas.

Usage:
    >>> from pathlib import Path
    >>> from asset_store import build_source_files, apply_fbx_scales
    >>> scales = build_source_files(Path("Pack.unitypackage"), Path("tmp/SourceFiles"))
    >>> # ... copy tmp/SourceFiles/FBX/*.fbx into pack/models/ ...
    >>> apply_fbx_scales(Path("pack/models"), scales, Path("project"))
"""

from __future__ import annotations

import logging
import re
import tarfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

logger = logging.getLogger(__name__)

# Unity's built-in shaders (Standard, etc.) live under this GUID.
BUILTIN_SHADER_GUID = "0000000000000000f000000000000000"

# Effect, collision and light-shaft meshes have no sensible atlas material.
_NO_FALLBACK = re.compile(r"^(FX_|SunShafts)|Collision|Convex|Particle", re.I)

_REF = re.compile(r"\{fileID: (-?\d+)(?:, guid: ([0-9a-f]{32}))?")
_MODIFICATION = re.compile(
    r"- target: \{fileID: (-?\d+), guid: ([0-9a-f]{32}),?\s*type: \d+\}\s*"
    r"propertyPath: (\S+)\s*value: ?(.*)\n\s*"
    r"objectReference: \{fileID: -?\d+(?:, guid: ([0-9a-f]{32}))?"
)
_MATERIAL_SLOT = re.compile(r"m_Materials\.Array\.data\[(\d+)\]")

# (material name, texture hint or None for "Uses custom shader")
Slot = tuple[str, "str | None"]


def build_source_files(package_path: Path, dest: Path) -> dict[str, float]:
    """Write FBX/ and MaterialList.txt for an Asset Store package into dest.

    Args:
        package_path: The .unitypackage to read.
        dest: Directory to create; FBX files are flattened into dest/FBX/.

    Returns:
        Unity import scale per FBX file name, for files whose scale is not 1.
        Pass it to apply_fbx_scales() once the FBX files are in models/.

    Raises:
        tarfile.ReadError: If the package is not a valid gzip tar archive.
    """
    assets = _read_package(package_path)
    path = {guid: _first_line(files["pathname"]) for guid, files in assets.items()}

    fbx_dir = dest / "FBX"
    fbx_dir.mkdir(parents=True, exist_ok=True)

    mesh_ids: dict[str, dict[str, str]] = {}
    fbx_names: dict[str, set[str]] = {}
    scales: dict[str, float] = {}
    for guid, p in path.items():
        if not p.lower().endswith(".fbx") or "asset" not in assets[guid]:
            continue
        name = _safe_file_name(p)
        if name is None:
            logger.warning("Skipping FBX with unsafe path in package: %r", p)
            continue
        data = assets[guid]["asset"]
        (fbx_dir / name).write_bytes(data)
        meta = assets[guid].get("asset.meta", b"").decode(errors="ignore")
        mesh_ids[guid] = _mesh_ids_from_meta(meta)
        fbx_names[guid] = _fbx_node_names(data)
        # The first globalScale is ModelImporter's mesh scale; later ones belong
        # to animation and humanoid settings.
        scale = re.search(r"^\s*globalScale: ([\d.e-]+)", meta, re.M)
        if scale and float(scale.group(1)) != 1.0:
            scales[name] = float(scale.group(1))

    materials = {
        guid: _material_slot(p, assets[guid]["asset"], path)
        for guid, p in path.items()
        if p.endswith(".mat") and "asset" in assets[guid]
    }

    lines: list[str] = []
    mapped: set[str] = set()
    slot_counts: Counter[Slot] = Counter()
    for guid, p in sorted(path.items(), key=lambda item: item[1]):
        if not p.endswith(".prefab") or "asset" not in assets[guid]:
            continue
        entries = _prefab_entries(assets[guid]["asset"], path, mesh_ids, materials)
        if not entries:
            continue
        lines.append(f"Prefab Name: {PurePosixPath(p).stem}")
        for mesh, slots in entries:
            mapped.add(mesh)
            slot_counts.update(slots)
            lines += _mesh_lines(mesh, slots)
        lines.append("")

    fallback_count = 0
    if slot_counts:
        main_slot = slot_counts.most_common(1)[0][0]
        for guid in sorted(fbx_names, key=lambda g: path[g]):
            orphans = sorted(
                n for n in fbx_names[guid] if n not in mapped and not _NO_FALLBACK.search(n)
            )
            if not orphans:
                continue
            lines.append(f"Prefab Name: {PurePosixPath(path[guid]).stem}_Fallback")
            for name in orphans:
                mapped.add(name)
                lines += _mesh_lines(name, [main_slot])
            lines.append("")
            fallback_count += len(orphans)

    (dest / "MaterialList.txt").write_text("\n".join(lines), encoding="utf-8")
    logger.info(
        "Built source files from package: %d FBX, %d materials, %d fallback meshes, %d scaled FBX",
        len(fbx_names), len(materials), fallback_count, len(scales),
    )
    return scales


def apply_fbx_scales(models_dir: Path, scales: dict[str, float], project_dir: Path) -> int:
    """Set nodes/root_scale in each scaled FBX's .import file and force a reimport.

    Godot bakes root_scale into the mesh data when nodes/apply_root_scale is
    true, so the extracted meshes come out at Unity's size.

    Args:
        models_dir: The pack's models/ directory holding the copied FBX files.
        scales: Output of build_source_files().
        project_dir: Godot project root; stale entries in .godot/imported/
            are deleted so Godot reimports with the new scale.

    Returns:
        Number of .import files written.
    """
    imported_dir = project_dir / ".godot" / "imported"
    written = 0
    for fbx_name, scale in scales.items():
        fbx = next(models_dir.rglob(fbx_name), None)
        if fbx is None:
            continue
        import_file = fbx.with_name(f"{fbx.name}.import")
        if import_file.exists():
            text = import_file.read_text(encoding="utf-8")
            text = re.sub(r"^nodes/root_scale=.*$", f"nodes/root_scale={scale}", text, flags=re.M)
            text = re.sub(r"^nodes/apply_root_scale=.*$", "nodes/apply_root_scale=true", text, flags=re.M)
        else:
            # Godot fills in every other import option on first import. fbx/importer must be
            # explicit: an .import file without it is treated as a pre-4.3 project and
            # imported with FBX2glTF, which is usually not installed.
            text = (
                '[remap]\n\nimporter="scene"\n\n[params]\n\n'
                f"nodes/apply_root_scale=true\nnodes/root_scale={scale}\nfbx/importer=0\n"
            )
        import_file.write_text(text, encoding="utf-8")
        for md5 in imported_dir.glob(f"{fbx.name}-*.md5"):
            md5.unlink()
        written += 1
    logger.debug("Applied Unity import scale to %d FBX files", written)
    return written


def _read_package(package_path: Path) -> dict[str, dict[str, bytes]]:
    """GUID -> {entry name: bytes}, for entries that have a pathname."""
    data: dict[str, dict[str, bytes]] = defaultdict(dict)
    with tarfile.open(package_path, "r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            parts = PurePosixPath(member.name).parts
            if len(parts) != 2 or parts[1] == "preview.png":
                continue
            file_obj = tar.extractfile(member)
            if file_obj is not None:
                data[parts[0]][parts[1]] = file_obj.read()
    return {guid: files for guid, files in data.items() if "pathname" in files}


def _safe_file_name(asset_path: str) -> str | None:
    """Final path component, or None if it could escape the destination folder.

    Pathnames come from the package, so a crafted one may use Windows separators
    or drive letters that PurePosixPath would keep inside .name.
    """
    name = PurePosixPath(asset_path.replace("\\", "/")).name
    if not name or name in (".", "..") or ":" in name:
        return None
    return name


def _first_line(pathname: bytes) -> str:
    # Older packages append a second line (e.g. "00") after the asset path.
    text = pathname.decode("utf-8", errors="ignore").replace("\x00", "").strip()
    return text.splitlines()[0].strip() if text else ""


def _mesh_ids_from_meta(meta: str) -> dict[str, str]:
    """Mesh fileID -> mesh name, from internalIDToNameTable or legacy fileIDToRecycleName."""
    names = {}
    for file_id, name in re.findall(r"first:\s*\n\s*43: (-?\d+)\s*\n\s*second: (.+)", meta):
        names[file_id] = name.strip()
    for file_id, name in re.findall(r"^\s*(43\d{5}): (.+)$", meta, re.M):
        names.setdefault(file_id, name.strip())
    return names


def _fbx_node_names(data: bytes) -> set[str]:
    """Model and Geometry names in a binary ("Name\\x00\\x01Model") or ASCII FBX."""
    names = re.findall(rb"([\w.\- ]+)\x00\x01(?:Model|Geometry)", data)
    names += re.findall(rb'Model: \d+, "Model::([^"]+)", "Mesh"', data)
    return {n.decode(errors="ignore") for n in names}


def _material_slot(mat_path: str, content: bytes, path: dict[str, str]) -> Slot:
    """Material name plus MaterialList's hint: a texture name, or None for a custom shader."""
    text = content.decode(errors="ignore")
    shader = re.search(r"m_Shader: \{fileID: -?\d+(?:, guid: ([0-9a-f]{32}))?", text)
    if not shader or shader.group(1) not in (None, BUILTIN_SHADER_GUID):
        return PurePosixPath(mat_path).stem, None
    tex = re.search(r"- _MainTex:\s*\n\s*m_Texture: \{fileID: \d+, guid: ([0-9a-f]{32})", text)
    hint = PurePosixPath(path[tex.group(1)]).stem if tex and tex.group(1) in path else "Standard"
    return PurePosixPath(mat_path).stem, hint


def _prefab_entries(
    content: bytes,
    path: dict[str, str],
    mesh_ids: dict[str, dict[str, str]],
    materials: dict[str, Slot],
) -> list[tuple[str, list[Slot]]]:
    """(mesh name, material slots) pairs used by one prefab."""
    docs = dict(_split_yaml_docs(content.decode(errors="ignore")))
    go_names = {
        file_id: m.group(1).strip()
        for file_id, body in docs.items()
        if body.startswith("GameObject:") and (m := re.search(r"m_Name: (.+)", body))
    }

    by_object: dict[str, dict] = defaultdict(dict)
    entries: list[tuple[str, list[Slot]]] = []
    for body in docs.values():
        if body.startswith("PrefabInstance:"):
            entries += _fbx_instance_entries(body, path, mesh_ids, materials)
            continue
        go = re.search(r"m_GameObject: \{fileID: (\d+)", body)
        if not go:
            continue
        if body.startswith(("MeshFilter:", "SkinnedMeshRenderer:")):
            mesh = re.search(r"m_Mesh: \{fileID: (-?\d+), guid: ([0-9a-f]{32})", body)
            if mesh and mesh.group(2) in mesh_ids:
                name = mesh_ids[mesh.group(2)].get(mesh.group(1)) or go_names.get(go.group(1))
                if name:
                    by_object[go.group(1)]["mesh"] = name
        if body.startswith(("MeshRenderer:", "SkinnedMeshRenderer:")):
            block = re.search(r"m_Materials:\n((?:\s*- \{.*\}\n)+)", body)
            if block:
                by_object[go.group(1)]["slots"] = [
                    materials[g] for _, g in _REF.findall(block.group(1)) if g in materials
                ]

    entries += [(o["mesh"], o["slots"]) for o in by_object.values() if o.get("mesh") and o.get("slots")]
    return entries


def _fbx_instance_entries(
    body: str,
    path: dict[str, str],
    mesh_ids: dict[str, dict[str, str]],
    materials: dict[str, Slot],
) -> list[tuple[str, list[Slot]]]:
    """Entries for a PrefabInstance of an FBX that overrides its materials."""
    source = re.search(r"m_SourcePrefab: \{fileID: \d+, guid: ([0-9a-f]{32})", body)
    if not source or source.group(1) not in mesh_ids:
        return []
    overrides: dict[str, dict[int, Slot]] = defaultdict(dict)
    name = None
    for target, _, prop, value, ref in _MODIFICATION.findall(body):
        slot = _MATERIAL_SLOT.fullmatch(prop)
        if slot and ref in materials:
            overrides[target][int(slot.group(1))] = materials[ref]
        elif prop == "m_Name" and value.strip():
            name = value.strip()
    # Without internalIDToNameTable a renderer can't be tied to a mesh name, so
    # only single-renderer FBX files are mapped.
    if len(overrides) != 1:
        return []
    slots = next(iter(overrides.values()))
    mesh = name or PurePosixPath(path[source.group(1)]).stem
    return [(mesh, [slots[i] for i in sorted(slots)])]


def _split_yaml_docs(text: str):
    """Yield (fileID, body) for each document in a Unity YAML file."""
    for chunk in re.split(r"^--- !u!\d+ &", text, flags=re.M)[1:]:
        file_id, _, body = chunk.partition("\n")
        yield file_id.split()[0], body


def _godot_names(name: str) -> list[str]:
    """The name plus the form Godot's importer gives it after stripping a "_Wheel" hint."""
    stripped = re.sub(r"_wheel", "", name, flags=re.I)
    return [name] if stripped == name else [name, stripped]


def _mesh_lines(mesh: str, slots: list[Slot]) -> list[str]:
    lines = []
    for name in _godot_names(mesh):
        lines.append(f"    Mesh Name: {name}")
        lines += [f"        Slot: {m} ({hint or 'Uses custom shader'})" for m, hint in slots]
    return lines
