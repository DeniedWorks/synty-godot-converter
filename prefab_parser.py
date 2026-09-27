"""Derive mesh-to-material mappings from Unity .prefab files.

Fallback for packs that ship without ``MaterialList*.txt``. That file is only
included in Synty's separate SourceFiles download, never in the
``.unitypackage`` - but the package does contain every prefab, and prefabs
carry the same information in a more authoritative form.

A Synty prefab is a flat YAML document stream. Each object is introduced by an
anchor line and linked by fileID rather than nesting::

    --- !u!1 &123292
    GameObject:
      m_Name: SM_Prop_Barrel_01
    --- !u!23 &2325676
    MeshRenderer:
      m_GameObject: {fileID: 123292}
      m_Materials:
      - {fileID: 2100000, guid: 42b64fdb315e3054ea757d8d1c4bcfa7, type: 2}

So the mesh name comes from joining a renderer's ``m_GameObject`` back to the
GameObject that owns it, and the materials come from resolving each
``m_Materials`` GUID through the package's GUID map.

This module emits the same ``PrefabMaterials`` structures as
:mod:`material_list`, so every downstream consumer - ``build_shader_cache``,
``get_mesh_to_materials_map``, ``generate_mesh_material_mapping_json`` - works
against it unchanged.

Parsing uses regex rather than a YAML parser for the same reason
:mod:`unity_parser` does: Unity's ``!u!`` tags are not standard YAML 1.1 and
break PyYAML and ruamel.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from material_list import MaterialSlot, MeshMaterials, PrefabMaterials

logger = logging.getLogger(__name__)

# Unity class IDs for the components we care about.
_CLASS_GAME_OBJECT = "1"
_CLASS_MESH_RENDERER = "23"
_CLASS_SKINNED_MESH_RENDERER = "137"

_RENDERER_CLASSES = frozenset({_CLASS_MESH_RENDERER, _CLASS_SKINNED_MESH_RENDERER})

# Splits the document stream: "--- !u!<classId> &<anchor>"
_DOCUMENT_PATTERN = re.compile(
    r"^---\s+!u!(\d+)\s+&(\d+)", re.MULTILINE
)

_NAME_PATTERN = re.compile(r"^\s*m_Name:\s*(.+?)\s*$", re.MULTILINE)
_GAME_OBJECT_REF_PATTERN = re.compile(
    r"^\s*m_GameObject:\s*\{fileID:\s*(\d+)", re.MULTILINE
)

# The m_Materials block, stopped at the first line that is not a list entry.
# Unity writes entries as "  - {fileID: ..., guid: ..., type: N}".
_MATERIALS_BLOCK_PATTERN = re.compile(
    r"^\s*m_Materials:\s*$\n((?:\s*-\s*\{[^}]*\}\s*$\n?)*)",
    re.MULTILINE,
)
_MATERIAL_GUID_PATTERN = re.compile(r"guid:\s*([a-f0-9]{32})")

_IS_ACTIVE_PATTERN = re.compile(r"^\s*m_IsActive:\s*(\d+)\s*$", re.MULTILINE)

_MESH_REF_PATTERN = re.compile(
    r"^\s*m_Mesh:\s*\{fileID:\s*-?\d+,\s*guid:\s*([a-f0-9]{32})", re.MULTILINE
)

# A prefab *variant* carries no renderer document. Its materials are property
# modifications on the source FBX, inside the PrefabInstance's m_Modifications
# list::
#
#     - target: {fileID: -7511558181221131132, guid: <fbx guid>, type: 3}
#       propertyPath: m_Materials.Array.data[0]
#       value:
#       objectReference: {fileID: 2100000, guid: <material guid>, type: 2}
#
# so the mesh comes from the target's GUID and the material from the
# objectReference's. Unity wraps long mappings across lines, so each entry is
# whitespace-normalised before matching rather than read line by line.
_MODIFICATIONS_KEY_PATTERN = re.compile(r"^(\s*)m_Modifications:\s*$", re.MULTILINE)
_MODIFICATION_SPLIT_PATTERN = re.compile(r"^\s*-\s+(?=target:)", re.MULTILINE)
_MODIFICATION_TARGET_PATTERN = re.compile(
    r"target:\s*\{fileID:\s*(-?\d+),\s*guid:\s*([a-f0-9]{32})"
)
_MODIFICATION_SLOT_PATTERN = re.compile(
    r"propertyPath:\s*m_Materials\.Array\.data\[(\d+)\]"
)
_MODIFICATION_OBJECT_PATTERN = re.compile(
    r"objectReference:\s*\{fileID:\s*-?\d+,\s*guid:\s*([a-f0-9]{32})"
)

# A SkinnedMeshRenderer's bone list, stopped at the first non-entry line.
_BONES_BLOCK_PATTERN = re.compile(
    r"^\s*m_Bones:\s*$\n((?:\s*-\s*\{fileID:[^}]*\}\s*$\n?)*)",
    re.MULTILINE,
)

# One bone reference inside that block.
_BONE_FILE_ID_PATTERN = re.compile(r"fileID:\s*(-?\d+)")

# Smallest bone count that counts as a character rig.
#
# "Has an active SkinnedMeshRenderer" alone does not mean "is a character":
# Synty skins cloth so it can move in the wind. On POLYGON_Dungeon_Realms that
# over-match turns 33 tents, flag lines and FX light rays into character
# definitions, which then fail in Godot and produce a wall of spurious errors.
#
# The count is the union of the bones every active skinned renderer names, not
# the largest single renderer. A modular character - POLYGON_Modular_Fantasy_Hero
# builds each of its 126 presets out of ~17 separate parts - skins each part only
# to the bones it needs, so a forearm binds 12 and no single renderer reaches the
# threshold. Its parts together cover 49-58.
#
# Bone count separates the two cleanly, with a wide empty gap on every pack
# measured: FX light rays use 2 bones and every tent or flag line uses 5, while
# the smallest real character rig uses 49. Anything in between does not occur, so
# the exact threshold matters little - this one sits in the gap with room for a
# leaner character rig on some future pack.
MIN_CHARACTER_BONES = 16

# Trailing _LOD<n> used to order meshes so LOD0 leads.
_LOD_SUFFIX_PATTERN = re.compile(r"_LOD(\d+)\s*$", re.IGNORECASE)


def _split_documents(text: str) -> list[tuple[str, str, str]]:
    """Split a prefab's YAML stream into (class_id, anchor, body) triples."""
    matches = list(_DOCUMENT_PATTERN.finditer(text))
    documents: list[tuple[str, str, str]] = []

    for i, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        documents.append((match.group(1), match.group(2), text[body_start:body_end]))

    return documents


def _extract_material_guids(body: str) -> list[str]:
    """Return material GUIDs from a renderer body, in slot order.

    Entries with ``{fileID: 0}`` (no material assigned) carry no GUID and are
    dropped. Reading stops at the end of the ``m_Materials`` list so unrelated
    GUID-bearing keys further down the renderer are not picked up.
    """
    block_match = _MATERIALS_BLOCK_PATTERN.search(body)
    if not block_match:
        return []

    return _MATERIAL_GUID_PATTERN.findall(block_match.group(1))


def _is_game_object_active(body: str) -> bool:
    """Whether a GameObject document is enabled.

    Synty ships one prefab per character containing every character in the
    pack, with all but one disabled, so this flag is what distinguishes a
    character's own meshes from its 26 disabled siblings.

    A missing or unparseable flag counts as active: dropping meshes because a
    field was absent would silently empty the prefab.
    """
    match = _IS_ACTIVE_PATTERN.search(body)
    if match is None:
        return True
    return match.group(1) != "0"


def _lod_sort_key(index_and_mesh: tuple[int, MeshMaterials]) -> tuple[int, int]:
    """Order meshes so LOD0 comes first, preserving document order otherwise.

    ``build_shader_cache()`` treats ``meshes[0]`` as LOD0 and propagates its
    per-slot shader decision to every later mesh, so a prefab whose LOD2 mesh
    happens to be serialized first would otherwise poison the whole chain.
    Meshes with no LOD suffix sort as level 0 and keep their relative order.
    """
    index, mesh = index_and_mesh
    lod_match = _LOD_SUFFIX_PATTERN.search(mesh.mesh_name)
    lod_level = int(lod_match.group(1)) if lod_match else 0
    return (lod_level, index)


def _material_modifications(text: str) -> list[tuple[str, str, int, str]]:
    """Material assignments carried as PrefabInstance modifications.

    Returns:
        ``(target_guid, target_file_id, slot_index, material_guid)`` per
        ``m_Materials`` entry, in document order. ``target_guid`` identifies
        the source FBX, ``target_file_id`` the renderer within it, and
        ``slot_index`` the surface the material belongs to.
    """
    found: list[tuple[str, str, int, str]] = []

    for key in _MODIFICATIONS_KEY_PATTERN.finditer(text):
        indent = len(key.group(1))

        # The list runs until the first line that is neither indented further
        # than the key nor one of its own sequence entries - Unity writes those
        # at the key's own indentation.
        lines: list[str] = []
        for line in text[key.end() :].splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            line_indent = len(line) - len(line.lstrip())
            if line_indent < indent:
                break
            if line_indent == indent and not stripped.startswith("- "):
                break
            lines.append(line)

        for chunk in _MODIFICATION_SPLIT_PATTERN.split("\n".join(lines)):
            if not chunk.startswith("target:"):
                continue
            entry = " ".join(chunk.split())

            slot_match = _MODIFICATION_SLOT_PATTERN.search(entry)
            if not slot_match:
                continue
            target_match = _MODIFICATION_TARGET_PATTERN.search(entry)
            object_match = _MODIFICATION_OBJECT_PATTERN.search(entry)
            if not target_match or not object_match:
                continue

            found.append(
                (
                    target_match.group(2),
                    target_match.group(1),
                    int(slot_match.group(1)),
                    object_match.group(1),
                )
            )

    return found


def _renderers_by_fbx(
    text: str,
    prefab_name: str,
    guid_to_material_name: dict[str, str],
    guid_to_mesh_name: dict[str, str],
) -> dict[str, list[list[str]]]:
    """Per-renderer material slots for a prefab variant, keyed by source FBX.

    One FBX often holds several renderers - a wall body and its glass pane, a
    hand cart and its two wheels - and every one of them modifies the same FBX
    GUID. Only the target's fileID separates them, so grouping on the GUID
    alone lets one renderer's slot 0 overwrite another's.

    Returns:
        FBX name to one ordered slot list per renderer, largest renderer first.
        The FBX's own name belongs to its body mesh, which carries the most
        surfaces, and Godot falls back to the first entry when it cannot match
        a mesh by surface count.
    """
    by_renderer: dict[tuple[str, str], dict[int, str]] = {}
    order: list[tuple[str, str]] = []

    for target_guid, file_id, slot_index, material_guid in _material_modifications(text):
        mesh_name = guid_to_mesh_name.get(target_guid)
        if not mesh_name:
            logger.debug(
                "Prefab %s: modification targets unknown mesh GUID %s",
                prefab_name,
                target_guid,
            )
            continue

        material_name = guid_to_material_name.get(material_guid)
        if not material_name:
            logger.debug(
                "Prefab %s: unresolved material GUID %s on %s",
                prefab_name,
                material_guid,
                mesh_name,
            )
            continue

        key = (target_guid, file_id)
        if key not in by_renderer:
            by_renderer[key] = {}
            order.append(key)
        by_renderer[key][slot_index] = material_name

    renderers: dict[str, list[list[str]]] = {}
    for target_guid, file_id in order:
        slots_by_index = by_renderer[(target_guid, file_id)]
        renderers.setdefault(guid_to_mesh_name[target_guid], []).append(
            [slots_by_index[index] for index in sorted(slots_by_index)]
        )

    # Stable, so renderers of equal size keep their document order.
    for slot_lists in renderers.values():
        slot_lists.sort(key=len, reverse=True)

    return renderers


def _meshes_from_modifications(
    text: str,
    prefab_name: str,
    guid_to_material_name: dict[str, str],
    guid_to_mesh_name: dict[str, str],
) -> list[MeshMaterials]:
    """The body mesh of each FBX a prefab variant assigns materials to.

    Only one entry per FBX: ``mesh_material_mapping.json`` is keyed by mesh
    name, so a second entry under the same name would overwrite the first. The
    remaining renderers reach Godot through
    :func:`build_fbx_material_fallback` instead.
    """
    meshes: list[MeshMaterials] = []

    for mesh_name, slot_lists in _renderers_by_fbx(
        text, prefab_name, guid_to_material_name, guid_to_mesh_name
    ).items():
        meshes.append(
            MeshMaterials(
                mesh_name=mesh_name,
                slots=[
                    MaterialSlot(
                        material_name=material_name,
                        texture_name=None,
                        uses_custom_shader=True,
                    )
                    for material_name in slot_lists[0]
                ],
            )
        )

    return meshes


def parse_prefab_bytes(
    data: bytes,
    prefab_name: str,
    guid_to_material_name: dict[str, str],
    guid_to_mesh_name: dict[str, str] | None = None,
) -> PrefabMaterials | None:
    """Extract mesh-to-material assignments from one prefab's raw bytes.

    Args:
        data: Raw ``.prefab`` file content.
        prefab_name: Name for the resulting prefab (normally the filename
            without extension).
        guid_to_material_name: Material GUID to material name, as resolved
            from the package's GUID map.
        guid_to_mesh_name: FBX GUID to mesh name. Needed only to read prefab
            variants, which name their mesh by GUID rather than by carrying a
            renderer. Omitting it skips that path.

    Returns:
        A ``PrefabMaterials`` with one ``MeshMaterials`` per renderer that
        resolved to both a name and at least one material, ordered LOD0-first.
        Variants, which hold no renderer, contribute one entry per source FBX
        named in their modifications. ``None`` if the prefab yielded nothing
        usable - no renderers, no resolvable materials, or unparseable
        content.

    Example:
        >>> prefab = parse_prefab_bytes(data, "SM_Prop_Barrel_01", guids)
        >>> prefab.meshes[0].mesh_name
        'SM_Prop_Barrel_01'
    """
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception as e:  # pragma: no cover - decode with errors= rarely raises
        logger.debug("Could not decode prefab %s: %s", prefab_name, e)
        return None

    documents = _split_documents(text)
    if not documents:
        return None

    # Pass 1: anchor -> GameObject name.
    game_object_names: dict[str, str] = {}
    for class_id, anchor, body in documents:
        if class_id != _CLASS_GAME_OBJECT:
            continue
        name_match = _NAME_PATTERN.search(body)
        if name_match:
            game_object_names[anchor] = name_match.group(1)

    # Pass 2: renderers -> (mesh name, material slots).
    meshes: list[MeshMaterials] = []
    for class_id, _anchor, body in documents:
        if class_id not in _RENDERER_CLASSES:
            continue

        ref_match = _GAME_OBJECT_REF_PATTERN.search(body)
        if not ref_match:
            continue

        mesh_name = game_object_names.get(ref_match.group(1))
        if not mesh_name:
            logger.debug(
                "Prefab %s: renderer references unknown GameObject %s",
                prefab_name,
                ref_match.group(1),
            )
            continue

        slots: list[MaterialSlot] = []
        for guid in _extract_material_guids(body):
            material_name = guid_to_material_name.get(guid)
            if not material_name:
                logger.debug(
                    "Prefab %s: unresolved material GUID %s on %s",
                    prefab_name,
                    guid,
                    mesh_name,
                )
                continue
            # Prefabs carry no "(Uses custom shader)" marker. Setting this True
            # routes the material through determine_shader() - GUID lookup,
            # then name patterns - instead of build_shader_cache()'s
            # short-circuit straight to polygon.gdshader.
            slots.append(
                MaterialSlot(
                    material_name=material_name,
                    texture_name=None,
                    uses_custom_shader=True,
                )
            )

        if slots:
            meshes.append(MeshMaterials(mesh_name=mesh_name, slots=slots))

    # Variants carry no renderer at all, so pass 2 finds nothing for them.
    if not meshes and guid_to_mesh_name:
        meshes = _meshes_from_modifications(
            text, prefab_name, guid_to_material_name, guid_to_mesh_name
        )

    if not meshes:
        return None

    ordered = [mesh for _, mesh in sorted(enumerate(meshes), key=_lod_sort_key)]
    return PrefabMaterials(prefab_name=prefab_name, meshes=ordered)


def build_prefabs_from_package(guid_map) -> list[PrefabMaterials]:
    """Build prefab material data from an extracted Unity package.

    Args:
        guid_map: ``unity_package.GuidMap`` carrying ``guid_to_pathname`` and
            ``guid_to_prefab_content``.

    Returns:
        One ``PrefabMaterials`` per prefab that yielded usable meshes. Safe to
        pass anywhere ``parse_material_list()`` output is accepted.

    Example:
        >>> prefabs = build_prefabs_from_package(guid_map)
        >>> generate_mesh_material_mapping_json(prefabs, out_path)
    """
    prefab_content = getattr(guid_map, "guid_to_prefab_content", None) or {}
    if not prefab_content:
        logger.debug("Package contains no prefabs")
        return []

    # Material GUID -> material name, from the package's asset paths.
    guid_to_material_name: dict[str, str] = {}
    for guid, pathname in guid_map.guid_to_pathname.items():
        if pathname.lower().endswith(".mat"):
            guid_to_material_name[guid] = pathname.rsplit("/", 1)[-1][: -len(".mat")]

    # FBX GUID -> mesh name, for prefab variants that name their mesh by GUID.
    guid_to_mesh_name: dict[str, str] = {}
    for guid, pathname in guid_map.guid_to_pathname.items():
        if pathname.lower().endswith(".fbx"):
            guid_to_mesh_name[guid] = pathname.rsplit("/", 1)[-1][: -len(".fbx")]

    prefabs: list[PrefabMaterials] = []
    skipped = 0

    for guid, content in prefab_content.items():
        pathname = guid_map.guid_to_pathname.get(guid, "")
        prefab_name = pathname.rsplit("/", 1)[-1]
        if prefab_name.lower().endswith(".prefab"):
            prefab_name = prefab_name[: -len(".prefab")]
        if not prefab_name:
            prefab_name = guid

        prefab = parse_prefab_bytes(
            content, prefab_name, guid_to_material_name, guid_to_mesh_name
        )
        if prefab is None:
            skipped += 1
            continue
        prefabs.append(prefab)

    logger.debug(
        "Derived %d prefab(s) from package (%d skipped, %d material GUIDs known)",
        len(prefabs),
        skipped,
        len(guid_to_material_name),
    )
    return prefabs


def build_fbx_material_fallback(guid_map) -> dict[str, list[list[str]]]:
    """Materials per FBX, for meshes that have no mapping of their own.

    A prefab variant names its mesh by the source FBX, so when one FBX holds
    several meshes only the one sharing the FBX's name is mapped - a hand cart
    is painted while its two wheels stay untextured. Godot knows which FBX each
    mesh came from and falls back to this table, choosing between an FBX's
    renderers by surface count.

    Args:
        guid_map: ``unity_package.GuidMap`` carrying ``guid_to_pathname`` and
            ``guid_to_prefab_content``.

    Returns:
        FBX name to one ordered material-name list per renderer, largest
        first. Empty for packs whose prefabs all carry renderers of their own.

    Example:
        >>> build_fbx_material_fallback(guid_map)["SM_Prop_HandCart_01"]
        [['PolygonNatureBiomesMeadow_Mat_01']]
    """
    prefab_content = getattr(guid_map, "guid_to_prefab_content", None) or {}
    if not prefab_content:
        return {}

    guid_to_material_name: dict[str, str] = {}
    guid_to_mesh_name: dict[str, str] = {}
    for guid, pathname in guid_map.guid_to_pathname.items():
        lowered = pathname.lower()
        basename = pathname.rsplit("/", 1)[-1]
        if lowered.endswith(".mat"):
            guid_to_material_name[guid] = basename[: -len(".mat")]
        elif lowered.endswith(".fbx"):
            guid_to_mesh_name[guid] = basename[: -len(".fbx")]

    fallback: dict[str, list[list[str]]] = {}

    for guid, content in prefab_content.items():
        pathname = guid_map.guid_to_pathname.get(guid, "")
        prefab_name = pathname.rsplit("/", 1)[-1]
        if prefab_name.lower().endswith(".prefab"):
            prefab_name = prefab_name[: -len(".prefab")]

        # Prefabs that carry renderers name their meshes directly, so every
        # mesh in them is already mapped and none needs a fallback.
        if parse_prefab_bytes(content, prefab_name, guid_to_material_name) is not None:
            continue

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover - decode with errors= rarely raises
            continue

        for mesh_name, slot_lists in _renderers_by_fbx(
            text, prefab_name, guid_to_material_name, guid_to_mesh_name
        ).items():
            for slots in slot_lists:
                if slots not in fallback.setdefault(mesh_name, []):
                    fallback[mesh_name].append(slots)

    for slot_lists in fallback.values():
        slot_lists.sort(key=len, reverse=True)

    logger.debug("Built FBX material fallback for %d FBX file(s)", len(fallback))
    return fallback


@dataclass
class CharacterDefinition:
    """One character assembled from a Synty character prefab.

    Attributes:
        name: Prefab name, e.g. "Character_Goblin_WarChief".
        source_fbx: Basename of the FBX holding the rig and meshes, e.g.
            "Characters". Empty when the mesh GUID could not be resolved.
        skinned: Names of active skinned meshes (the character body).
        attachments: Names of active non-skinned meshes (equipment). Whether
            each is bone-attached is left to Godot, which has already built a
            BoneAttachment3D for it during FBX import.
        bone_count: Distinct bones named across every active skinned renderer.
            Recorded for diagnostics; the gate that uses it is
            MIN_CHARACTER_BONES.
    """

    name: str
    source_fbx: str = ""
    skinned: list[str] = field(default_factory=list)
    attachments: list[str] = field(default_factory=list)
    bone_count: int = 0


def _models_relative_name(pathname: str) -> str:
    """Path of an FBX relative to the pack's Models root, without extension.

    Basenames are not unique: Synty packs ship both ``Models/Characters.fbx``
    and ``Models/FixedScale/Characters.fbx``. Matching on the basename alone
    would make every character definition match both files, building each
    character twice and half of them from the wrong source. ``copy_fbx_files()``
    mirrors the structure below ``Models/`` into the output ``models/``
    directory, so that relative path is the stable identifier.

    Args:
        pathname: Unity asset path, e.g.
            "Assets/PolygonDungeon/Models/FixedScale/Characters.fbx".

    Returns:
        "FixedScale/Characters" for the example above, "Characters" for a
        top-level FBX, or "" when the path is empty or unresolvable.
    """
    if not pathname:
        return ""

    normalised = pathname.replace("\\", "/")
    lowered = normalised.lower()

    marker = "/models/"
    index = lowered.rfind(marker)
    if index >= 0:
        relative = normalised[index + len(marker) :]
    else:
        relative = normalised.rsplit("/", 1)[-1]

    if relative.lower().endswith(".fbx"):
        relative = relative[: -len(".fbx")]
    return relative


def _bone_ids(body: str) -> set[str]:
    """fileIDs of the bones in a SkinnedMeshRenderer's m_Bones list."""
    match = _BONES_BLOCK_PATTERN.search(body)
    if not match:
        return set()
    return set(_BONE_FILE_ID_PATTERN.findall(match.group(1)))


def build_character_definitions(guid_map) -> dict[str, CharacterDefinition]:
    """Derive character definitions from the package's prefabs.

    A prefab is a character when its *active* SkinnedMeshRenderers name at
    least MIN_CHARACTER_BONES distinct bones between them. Synty ships one such
    prefab per character, each containing the whole shared hierarchy with every
    other character disabled, so the active set is exactly that character's body
    plus its equipment.

    The bone-count condition is not redundant. Synty also skins cloth - tent
    covers, flag lines, FX light rays - so an active SkinnedMeshRenderer on its
    own matches far more than characters.

    Args:
        guid_map: unity_package.GuidMap with guid_to_pathname and
            guid_to_prefab_content.

    Returns:
        Prefab name to CharacterDefinition, for character prefabs only.
    """
    prefab_content = getattr(guid_map, "guid_to_prefab_content", None) or {}
    definitions: dict[str, CharacterDefinition] = {}
    skipped_low_bone_count = 0
    skipped_non_fbx_mesh = 0

    for guid, content in prefab_content.items():
        pathname = guid_map.guid_to_pathname.get(guid, "")
        prefab_name = pathname.rsplit("/", 1)[-1]
        if prefab_name.lower().endswith(".prefab"):
            prefab_name = prefab_name[: -len(".prefab")]
        if not prefab_name:
            continue

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover - decode with errors= rarely raises
            continue

        documents = _split_documents(text)
        if not documents:
            continue

        active_names: dict[str, str] = {}
        for class_id, anchor, body in documents:
            if class_id != _CLASS_GAME_OBJECT:
                continue
            name_match = _NAME_PATTERN.search(body)
            if name_match and _is_game_object_active(body):
                active_names[anchor] = name_match.group(1)

        skinned: list[str] = []
        attachments: list[str] = []
        mesh_guid = ""
        bones: set[str] = set()

        for class_id, _anchor, body in documents:
            if class_id not in _RENDERER_CLASSES:
                continue
            ref = _GAME_OBJECT_REF_PATTERN.search(body)
            if not ref:
                continue
            name = active_names.get(ref.group(1))
            if not name:
                continue
            if class_id == _CLASS_SKINNED_MESH_RENDERER:
                skinned.append(name)
                bones |= _bone_ids(body)
                if not mesh_guid:
                    mesh_match = _MESH_REF_PATTERN.search(body)
                    if mesh_match:
                        mesh_guid = mesh_match.group(1)
            else:
                attachments.append(name)

        if not skinned:
            continue

        bone_count = len(bones)
        if bone_count < MIN_CHARACTER_BONES:
            logger.debug(
                "Skipping '%s': %d bone(s), below the %d needed for a character "
                "rig (skinned cloth or FX, not a character)",
                prefab_name,
                bone_count,
                MIN_CHARACTER_BONES,
            )
            skipped_low_bone_count += 1
            continue

        mesh_path = guid_map.guid_to_pathname.get(mesh_guid, "")
        if mesh_path and not mesh_path.lower().endswith(".fbx"):
            # Sidekick prefabs point at a Unity-baked .asset mesh, which Godot
            # cannot import. A definition naming it could never match a file,
            # so it would sit in the JSON claiming a character we never build.
            # Those characters come from .sk recipes instead - see sidekick.py.
            logger.debug(
                "Skipping '%s': mesh %s is not an FBX", prefab_name, mesh_path
            )
            skipped_non_fbx_mesh += 1
            continue

        source_fbx = _models_relative_name(mesh_path)

        definitions[prefab_name] = CharacterDefinition(
            name=prefab_name,
            source_fbx=source_fbx,
            skinned=skinned,
            attachments=attachments,
            bone_count=bone_count,
        )

    if skipped_low_bone_count:
        logger.debug(
            "Skipped %d skinned prefab(s) with fewer than %d bones (cloth/FX)",
            skipped_low_bone_count,
            MIN_CHARACTER_BONES,
        )
    if skipped_non_fbx_mesh:
        logger.debug(
            "Skipped %d prefab(s) whose mesh is not an FBX (Sidekick-style "
            "baked meshes; see sidekick.py)",
            skipped_non_fbx_mesh,
        )
    logger.debug("Derived %d character definition(s)", len(definitions))
    return definitions


def write_character_definitions_json(
    definitions: dict[str, CharacterDefinition],
    output_path: Path,
    *,
    indent: int = 2,
) -> None:
    """Write character_definitions.json for godot_converter.gd.

    Args:
        definitions: Output of build_character_definitions().
        output_path: Normally <pack_output_dir>/character_definitions.json.
        indent: JSON indentation level.
    """
    payload = {
        name: {
            "source_fbx": d.source_fbx,
            "skinned": d.skinned,
            "attachments": d.attachments,
            "bone_count": d.bone_count,
        }
        for name, d in definitions.items()
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=indent, ensure_ascii=False), encoding="utf-8"
    )
    logger.debug("Wrote %d character definition(s) to %s", len(payload), output_path)
