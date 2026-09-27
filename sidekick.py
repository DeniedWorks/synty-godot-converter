"""Sidekick character recipes.

Synty's SIDEKICK packs are a modular character creator rather than a set of
finished characters. A character is not one FBX: it is a recipe naming one part
mesh per body slot - head, torso, each limb, each armour attachment - with every
part skinned to the same 88-bone rig.

That recipe ships with the pack as a plain-text ``.sk`` file. The character's
prefab is no use to us: its SkinnedMeshRenderer points at a mesh Unity baked at
author time (``FantasyKnights_01.asset``), which Godot cannot import. The recipe
plus the part FBX is the only route to rebuilding the character, and both ship.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# .sk files are CRLF. A pattern anchored with a bare \n matches nothing, reports
# zero parts and raises no error - so every pattern here tolerates \r?\n.
#
# The top-level keys are unindented, which is what separates them from the
# indented "Name:" and "Species:" inside the ColorSet block and from the
# "- Name:" part entries.
_NAME_PATTERN = re.compile(r"^Name:[ \t]*(\S[^\r\n]*?)[ \t]*\r?$", re.MULTILINE)
_SPECIES_PATTERN = re.compile(r"^Species:[ \t]*(\d+)[ \t]*\r?$", re.MULTILINE)
_PART_PATTERN = re.compile(
    r"^-[ \t]*Name:[ \t]*(\S+)[ \t]*\r?\n[ \t]*PartType:[ \t]*(\S+)[ \t]*\r?$",
    re.MULTILINE,
)


# The proportion block is the file's last section, its keys indented under an
# unindented "BlendShapes:". Scoping to the block keeps ColorRows' own indented
# keys - which precede it - out of the match.
_BLEND_BLOCK_PATTERN = re.compile(
    r"^BlendShapes:[ \t]*\r?$((?:\r?\n[ \t]+[^\r\n]*)*)", re.MULTILINE
)
_BLEND_VALUE_PATTERN = r"^[ \t]+{key}:[ \t]*(-?\d+(?:\.\d+)?)[ \t]*\r?$"


@dataclass
class SidekickBlendShapes:
    """A character's body proportions, as three slider values in -100..100.

    Defaults mirror Synty's SerializedBlendShapeValues, which is what the tool
    restores when a key is absent: its serializer omits a value equal to the
    default. Note these are not all zero - zero is a real, non-neutral setting.

    Attributes:
        body_type: Masculine to feminine.
        body_size: Skinny (negative) to heavy (positive).
        muscle: Musculature.
    """

    body_type: float = 50.0
    body_size: float = 0.0
    muscle: float = 50.0


@dataclass
class SidekickPart:
    """One mesh filling one body slot of a Sidekick character.

    Attributes:
        slot: The recipe's PartType, e.g. "Torso", "AttachmentShoulderLeft".
        mesh: Part name as written in the recipe, e.g.
            "SK_FANT_KNGT_17_10TORS_HU01". This is the FBX basename.
        fbx: Path to the part's FBX relative to the pack's models/ directory,
            without extension. Empty when no such FBX was found.
    """

    slot: str
    mesh: str
    fbx: str = ""


@dataclass
class SidekickRecipe:
    """One Sidekick character, as described by its .sk file.

    Attributes:
        name: Character name, e.g. "FantasyKnights_05".
        species: Species id from the recipe. Recorded, not interpreted.
        parts: One entry per body slot, in recipe order.
        color_map: Basename of the character's 32x32 palette texture, e.g.
            "T_FantasyKnights_05ColorMap". Empty when the pack ships none.
        blend_shapes: Body proportions the character was authored with.
        material: Name of the .tres the character's parts take. Usually the
            character name, but Synty sometimes gives a recipe a variant
            suffix its assets do not carry.
    """

    name: str
    species: int = 0
    parts: list[SidekickPart] = field(default_factory=list)
    color_map: str = ""
    blend_shapes: SidekickBlendShapes = field(default_factory=SidekickBlendShapes)
    material: str = ""


def _parse_blend_shapes(text: str) -> SidekickBlendShapes:
    """Read the BlendShapes block, falling back to Synty's own defaults.

    Args:
        text: Full .sk content.

    Returns:
        The character's proportions. An absent block or key keeps the default,
        which is what the Unity-side deserializer does.
    """
    shapes = SidekickBlendShapes()
    block_match = _BLEND_BLOCK_PATTERN.search(text)
    if not block_match:
        return shapes

    block = block_match.group(1)
    for key, attribute in (
        ("BodyTypeValue", "body_type"),
        ("BodySizeValue", "body_size"),
        ("MuscleValue", "muscle"),
    ):
        match = re.search(
            _BLEND_VALUE_PATTERN.format(key=key), block, re.MULTILINE
        )
        if match:
            setattr(shapes, attribute, float(match.group(1)))
    return shapes


def parse_sk_bytes(data: bytes) -> SidekickRecipe | None:
    """Parse one .sk recipe.

    Name, Species, the Parts list and the BlendShapes proportions are consumed.
    ColorSet and ColorRows describe a texture bake the pack already ships the
    result of.

    Args:
        data: Raw .sk file content.

    Returns:
        The recipe, or None when the file carries no name or no parts - either
        means it is not a character recipe we can build.
    """
    text = data.decode("utf-8", errors="replace")

    name_match = _NAME_PATTERN.search(text)
    if not name_match:
        return None

    parts = [
        SidekickPart(slot=slot, mesh=mesh)
        for mesh, slot in _PART_PATTERN.findall(text)
    ]
    if not parts:
        logger.debug("Recipe %s lists no parts; skipping", name_match.group(1))
        return None

    species_match = _SPECIES_PATTERN.search(text)
    return SidekickRecipe(
        name=name_match.group(1),
        species=int(species_match.group(1)) if species_match else 0,
        parts=parts,
        blend_shapes=_parse_blend_shapes(text),
    )


def _index_fbx(models_dir: Path) -> dict[str, str]:
    """Map every FBX basename under models_dir to its relative path.

    Resolution deliberately uses the pack's *output* models/ directory rather
    than the package's asset paths: copy_fbx_files() strips SourceFiles/FBX/
    Models prefixes, so the two layouts differ, and only this one is what the
    Godot side will join to models/.

    Args:
        models_dir: The pack's output models/ directory.

    Returns:
        Basename without extension to path relative to models_dir, also
        without extension, using forward slashes.
    """
    index: dict[str, str] = {}
    if not models_dir.is_dir():
        logger.debug("No models directory at %s", models_dir)
        return index

    # Sorted so a duplicate basename resolves the same way on every run.
    for path in sorted(models_dir.rglob("*.fbx")):
        stem = path.stem
        relative = path.relative_to(models_dir).with_suffix("").as_posix()
        if stem in index:
            logger.warning(
                "Duplicate part basename %s: keeping %s, ignoring %s",
                stem,
                index[stem],
                relative,
            )
            continue
        index[stem] = relative
    return index


def _resolve_asset_name(name: str, textures: set[str]) -> str:
    """Find the name under which a character's palette and material ship.

    Normally the character name, but Synty sometimes numbers a recipe with a
    variant suffix its assets do not carry - SIDEKICK_Starter ships
    "Starter_01b" as a recipe while its palette and material are both
    "Starter_01". An exact match is always preferred, so a character that does
    have its own palette can never borrow a neighbour's.

    Args:
        name: Character name from the recipe.
        textures: Texture basenames the pack ships, without extension.

    Returns:
        The asset name, or "" when the pack ships no palette for it.
    """
    if f"T_{name}ColorMap" in textures:
        return name

    # Only a letter appended to a numbered name reads as a variant suffix.
    trimmed = re.sub(r"(?<=\d)[A-Za-z]$", "", name)
    if trimmed != name and f"T_{trimmed}ColorMap" in textures:
        logger.debug("Character %s uses assets named %s", name, trimmed)
        return trimmed
    return ""


def build_sidekick_recipes(
    guid_map, source_dirs: list[Path], models_dir: Path
) -> dict[str, SidekickRecipe]:
    """Collect and resolve every Sidekick recipe available for a pack.

    Recipes come from the .unitypackage and from --source-files. The latter
    wins on a name collision: a recipe saved into the user's Unity project is
    a character they built with the Sidekick tool, which is the likelier edit.

    Args:
        guid_map: unity_package.GuidMap with guid_to_sk_content and
            texture_guid_to_name.
        source_dirs: Directories to search recursively for .sk files.
        models_dir: The pack's output models/ directory, already populated.

    Returns:
        Character name to SidekickRecipe, for recipes with at least one part
        resolved to an FBX.
    """
    recipes: dict[str, SidekickRecipe] = {}

    sk_content = getattr(guid_map, "guid_to_sk_content", None) or {}
    for data in sk_content.values():
        recipe = parse_sk_bytes(data)
        if recipe:
            recipes[recipe.name] = recipe

    for source_dir in source_dirs:
        directory = Path(source_dir)
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.sk")):
            try:
                recipe = parse_sk_bytes(path.read_bytes())
            except OSError as exc:
                logger.warning("Could not read %s: %s", path, exc)
                continue
            if recipe:
                recipes[recipe.name] = recipe

    index = _index_fbx(models_dir)
    textures = {
        Path(name).stem
        for name in (getattr(guid_map, "texture_guid_to_name", None) or {}).values()
    }

    resolved: dict[str, SidekickRecipe] = {}
    for name, recipe in recipes.items():
        for part in recipe.parts:
            part.fbx = index.get(part.mesh, "")

        found = sum(1 for part in recipe.parts if part.fbx)
        if not found:
            logger.warning(
                "Sidekick character %s: none of its %d part(s) matched an FBX "
                "in %s; skipping",
                name,
                len(recipe.parts),
                models_dir,
            )
            continue
        if found < len(recipe.parts):
            logger.debug(
                "Sidekick character %s: %d of %d parts resolved",
                name,
                found,
                len(recipe.parts),
            )

        asset_name = _resolve_asset_name(name, textures)
        recipe.color_map = f"T_{asset_name}ColorMap" if asset_name else ""
        recipe.material = asset_name or name
        resolved[name] = recipe

    logger.debug("Resolved %d Sidekick recipe(s)", len(resolved))
    return resolved


def write_sidekick_characters_json(
    recipes: dict[str, SidekickRecipe],
    output_path: Path,
    *,
    indent: int = 2,
) -> None:
    """Write sidekick_characters.json for godot_converter.gd.

    Args:
        recipes: Output of build_sidekick_recipes().
        output_path: Normally <pack_output_dir>/sidekick_characters.json.
        indent: JSON indentation level.
    """
    payload = {
        name: {
            "species": recipe.species,
            "color_map": recipe.color_map,
            "material": recipe.material or name,
            "blend_shapes": {
                "body_type": recipe.blend_shapes.body_type,
                "body_size": recipe.blend_shapes.body_size,
                "muscle": recipe.blend_shapes.muscle,
            },
            "parts": [
                {"slot": part.slot, "mesh": part.mesh, "fbx": part.fbx}
                for part in recipe.parts
            ],
        }
        for name, recipe in recipes.items()
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=indent, ensure_ascii=False), encoding="utf-8"
    )
    logger.debug("Wrote %d Sidekick recipe(s) to %s", len(payload), output_path)


# Synty's tool database, shipped in the user's Unity project rather than in the
# .unitypackage - so joint adjustments are available only when --source-files
# points at a project that has the Sidekick tool installed.
SIDEKICK_DATABASE_NAME = "Side_Kick_Data.db"

# CharacterPartType values for the only joints Synty adjusts, mapped to the bone
# each one drives (BlendshapeJointAdjustment.PART_TYPE_JOINT_MAP). These are the
# attachment points - where pouches, pads and back items hang - not body joints:
# the body itself is reshaped by blend shapes, and only its attachments need
# moving to keep up.
_PART_TYPE_JOINTS = {
    24: "backAttach",
    25: "hipAttachFront",
    26: "hipAttachBack",
    27: "hipAttach_l",
    28: "hipAttach_r",
    29: "shoulderAttach_l",
    30: "shoulderAttach_r",
    31: "elbowAttach_l",
    32: "elbowAttach_r",
    33: "kneeAttach_l",
    34: "kneeAttach_r",
}

# BlendShapeType, whose order the rotation accumulation depends on.
_BLEND_TYPE_NAMES = {0: "feminine", 1: "heavy", 2: "skinny", 3: "bulk"}


def find_sidekick_database(source_dirs: list[Path]) -> Path | None:
    """Locate Synty's Sidekick tool database.

    Args:
        source_dirs: Directories to search recursively.

    Returns:
        Path to the database, or None when no source directory carries one -
        the normal case for a pack converted straight from its .unitypackage.
    """
    for source_dir in source_dirs:
        directory = Path(source_dir)
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob(SIDEKICK_DATABASE_NAME)):
            return path
    return None


def _signed_degrees(angle: float) -> float:
    """Fold an angle into -180..180.

    The database stores rotations as positive Euler angles, so a small negative
    rotation appears as 356 degrees. Interpolating from rest toward that value
    would take the long way round - a near-full revolution instead of the four
    degrees intended.

    Args:
        angle: Angle in degrees.

    Returns:
        The equivalent angle in -180..180.
    """
    folded = angle % 360.0
    return folded - 360.0 if folded > 180.0 else folded


def load_rig_adjustments(db_path: Path) -> dict[str, dict[str, dict]]:
    """Read per-joint offsets and rotations from the Sidekick database.

    The values are maxima: each is scaled by the character's corresponding
    blend weight and accumulated, which the Godot side does because it already
    holds the weights. Scale columns exist but are zero throughout and Synty
    never applies them, so they are not read.

    Args:
        db_path: Path to Side_Kick_Data.db.

    Returns:
        Bone name to blend type name to {"offset": [x, y, z],
        "rotation": [x, y, z]} in degrees. Empty when the database cannot be
        read - a missing adjustment is cosmetic, never a reason to fail a pack.
    """
    adjustments: dict[str, dict[str, dict]] = {}
    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        logger.warning("Could not open Sidekick database %s: %s", db_path, exc)
        return adjustments

    try:
        rows = connection.execute(
            "SELECT part_type, blend_type, max_offset_x, max_offset_y, "
            "max_offset_z, max_rotation_x, max_rotation_y, max_rotation_z "
            "FROM sk_blend_shape_rig_movement"
        ).fetchall()
    except sqlite3.Error as exc:
        logger.warning("No rig movement data in %s: %s", db_path, exc)
        return adjustments
    finally:
        connection.close()

    for part_type, blend_type, off_x, off_y, off_z, rot_x, rot_y, rot_z in rows:
        joint = _PART_TYPE_JOINTS.get(part_type)
        blend_name = _BLEND_TYPE_NAMES.get(blend_type)
        if joint is None or blend_name is None:
            continue
        adjustments.setdefault(joint, {})[blend_name] = {
            "offset": [float(off_x), float(off_y), float(off_z)],
            "rotation": [
                _signed_degrees(float(rot_x)),
                _signed_degrees(float(rot_y)),
                _signed_degrees(float(rot_z)),
            ],
        }

    logger.debug("Loaded joint adjustments for %d bone(s)", len(adjustments))
    return adjustments


def write_sidekick_rig_adjustments_json(
    adjustments: dict[str, dict[str, dict]],
    output_path: Path,
    *,
    indent: int = 2,
) -> None:
    """Write sidekick_rig_adjustments.json for godot_converter.gd.

    The data is per-pack rather than per-character: every character in a pack
    shares these maxima and scales them by its own proportions.

    Args:
        adjustments: Output of load_rig_adjustments().
        output_path: Normally <pack_output_dir>/sidekick_rig_adjustments.json.
        indent: JSON indentation level.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(adjustments, indent=indent, ensure_ascii=False), encoding="utf-8"
    )
    logger.debug(
        "Wrote joint adjustments for %d bone(s) to %s", len(adjustments), output_path
    )


# Every Sidekick part name embeds its slot: SK_<FAMILY>_<NN>_<CODE>_<SPECIES>.
# The database's sk_part_preset_row.part_type uses the same codes, so this one
# table serves both. Derived from every recipe in every converted pack: all 38
# codes map to exactly one slot name, with no ambiguity.
SIDEKICK_SLOT_CODES = {
    "01HEAD": "Head",
    "02HAIR": "Hair",
    "03EBRL": "EyebrowLeft",
    "04EBRR": "EyebrowRight",
    "05EYEL": "EyeLeft",
    "06EYER": "EyeRight",
    "07EARL": "EarLeft",
    "08EARR": "EarRight",
    "09FCHR": "FacialHair",
    "10TORS": "Torso",
    "11AUPL": "ArmUpperLeft",
    "12AUPR": "ArmUpperRight",
    "13ALWL": "ArmLowerLeft",
    "14ALWR": "ArmLowerRight",
    "15HNDL": "HandLeft",
    "16HNDR": "HandRight",
    "17HIPS": "Hips",
    "18LEGL": "LegLeft",
    "19LEGR": "LegRight",
    "20FOTL": "FootLeft",
    "21FOTR": "FootRight",
    "22AHED": "AttachmentHead",
    "23AFAC": "AttachmentFace",
    "24ABAC": "AttachmentBack",
    "25AHPF": "AttachmentHipsFront",
    "26AHPB": "AttachmentHipsBack",
    "27AHPL": "AttachmentHipsLeft",
    "28AHPR": "AttachmentHipsRight",
    "29ASHL": "AttachmentShoulderLeft",
    "30ASHR": "AttachmentShoulderRight",
    "31AEBL": "AttachmentElbowLeft",
    "32AEBR": "AttachmentElbowRight",
    "33AKNL": "AttachmentKneeLeft",
    "34AKNR": "AttachmentKneeRight",
    "35NOSE": "Nose",
    "36TETH": "Teeth",
    "37TONG": "Tongue",
    "38WRAP": "Wrap",
}

# part_group in sk_part_preset. The three groups partition the 38 body slots
# into regions, not into layers: a complete character is one set from each, and
# an armoured torso replaces the bare one rather than covering it.
_PART_GROUP_NAMES = {1: "head", 2: "upper", 3: "lower"}

# The same partition, keyed by slot. Which region a slot belongs to is a property
# of the slot, so it can be stated here and used by packs converted straight from
# a .unitypackage, which ship no database. Read off the database: 14 / 13 / 11,
# with no slot in two regions.
SLOT_GROUPS = {
    # head - the face and everything worn on it
    "Head": "head",
    "Hair": "head",
    "FacialHair": "head",
    "EyebrowLeft": "head",
    "EyebrowRight": "head",
    "EyeLeft": "head",
    "EyeRight": "head",
    "EarLeft": "head",
    "EarRight": "head",
    "Nose": "head",
    "Teeth": "head",
    "Tongue": "head",
    "AttachmentHead": "head",
    "AttachmentFace": "head",
    # upper - the whole upper body, armoured or bare
    "Torso": "upper",
    "ArmUpperLeft": "upper",
    "ArmUpperRight": "upper",
    "ArmLowerLeft": "upper",
    "ArmLowerRight": "upper",
    "HandLeft": "upper",
    "HandRight": "upper",
    "AttachmentBack": "upper",
    "AttachmentShoulderLeft": "upper",
    "AttachmentShoulderRight": "upper",
    "AttachmentElbowLeft": "upper",
    "AttachmentElbowRight": "upper",
    "Wrap": "upper",
    # lower - hips down
    "Hips": "lower",
    "LegLeft": "lower",
    "LegRight": "lower",
    "FootLeft": "lower",
    "FootRight": "lower",
    "AttachmentHipsFront": "lower",
    "AttachmentHipsBack": "lower",
    "AttachmentHipsLeft": "lower",
    "AttachmentHipsRight": "lower",
    "AttachmentKneeLeft": "lower",
    "AttachmentKneeRight": "lower",
}

# sk_part_preset_row.part_type is inconsistent: some rows hold the slot code
# ("10TORS"), others the slot name ("Head"). Reading only codes silently drops
# two thirds of the presets and every face slot of the rest.
_SLOT_NAMES = frozenset(SIDEKICK_SLOT_CODES.values())

def parse_part_name(part_name: str) -> dict[str, str] | None:
    """Split a Sidekick part name into its components.

    Names are not one fixed shape. Most read
    SK_<FAMILY>_<NN>_<CODE>_<SPECIES>, but some carry an extra prefix and no
    species - SK_SPEC_HUMN_BASE_01_10TORS, SK_FUTR_APOC_OUTL_06_28AHPR - and
    reading fixed positions drops those silently. So the slot code is located
    wherever it sits and everything else is read around it.

    Args:
        part_name: e.g. "SK_FANT_KNGT_01_10TORS_HU01".

    Returns:
        {"family", "set", "code", "slot", "species"}, or None when the name
        carries no slot code - demo and FX meshes share the SK_ prefix without
        being parts.
    """
    bits = part_name.split("_")
    if len(bits) < 4 or bits[0] != "SK":
        return None
    for index in range(2, len(bits)):
        slot = SIDEKICK_SLOT_CODES.get(bits[index], "")
        if not slot:
            continue
        return {
            "family": "_".join(bits[1 : index - 1]),
            "set": bits[index - 1],
            "code": bits[index],
            "slot": slot,
            "species": bits[index + 1] if index + 1 < len(bits) else "",
        }
    return None

# The parts library is shared across packs rather than living inside one,
# because Sidekick packs ship a common part pool - the same 1339 parts appear
# in four packs on average. It sits at the output root beside animations/.
SIDEKICK_PARTS_DIRNAME = "sidekick_parts"

# The database writes FF0000 into any colour column a row does not define.
# It is a sentinel, not a colour: Synty's per-character palettes carry it into
# the baked texture, which is why a part indexing an undefined slot renders
# bright red.
COLOR_UNSET = "FF0000"


def slot_for_part_name(part_name: str) -> str:
    """Read the body slot out of a Sidekick part name.

    Args:
        part_name: e.g. "SK_FANT_KNGT_01_10TORS_HU01".

    Returns:
        The slot name, or "" when the name does not parse or carries an
        unknown code - demo and FX meshes share the SK_ prefix without being
        parts.
    """
    parsed = parse_part_name(part_name)
    return parsed["slot"] if parsed else ""


def _slot_from_part_type(part_type: str) -> str:
    """Resolve a sk_part_preset_row.part_type, in either of its two forms.

    Args:
        part_type: Either a slot code ("10TORS") or a slot name ("Head").

    Returns:
        The slot name, or "" when the value is neither.
    """
    if part_type in _SLOT_NAMES:
        return part_type
    return SIDEKICK_SLOT_CODES.get(part_type, "")


def load_part_presets(db_path: Path) -> dict[str, dict]:
    """Read Synty's curated gear sets from the Sidekick database.

    Args:
        db_path: Path to Side_Kick_Data.db.

    Returns:
        Preset id (as a string, because it becomes a JSON key) to
        {"name", "group", "species", "parts": {slot: part_name}}. Empty when
        the database cannot be read - gear sets then come from part names.
    """
    presets: dict[str, dict] = {}
    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        logger.warning("Could not open Sidekick database %s: %s", db_path, exc)
        return presets

    try:
        rows = connection.execute(
            "SELECT p.id, p.name, p.part_group, p.ptr_species, "
            "r.part_type, r.part_name "
            "FROM sk_part_preset p "
            "JOIN sk_part_preset_row r ON r.ptr_part_preset = p.id"
        ).fetchall()
    except sqlite3.Error as exc:
        logger.warning("No part presets in %s: %s", db_path, exc)
        return presets
    finally:
        connection.close()

    for preset_id, name, part_group, species, part_type, part_name in rows:
        slot = _slot_from_part_type(str(part_type))
        if not slot:
            continue
        # A NULL part_name means the set leaves that slot empty - 418 of the
        # 5547 rows. str() would turn it into a part literally named "None".
        if part_name is None or not str(part_name).strip():
            continue
        entry = presets.setdefault(
            str(preset_id),
            {
                "name": str(name),
                "group": _PART_GROUP_NAMES.get(part_group, "unknown"),
                "species": int(species),
                "parts": {},
            },
        )
        entry["parts"][slot] = str(part_name)

    logger.debug("Loaded %d gear set(s)", len(presets))
    return presets


def derive_gear_sets_from_names(part_names: list[str]) -> dict[str, dict]:
    """Group parts into sets by the family and number in their names.

    The fallback for packs converted straight from a .unitypackage, which ships
    no tool database. Coarser than the database's presets - it cannot tell that
    two families share a bare torso - but it needs nothing beyond the part names
    themselves.

    Each family and number is split across the three body regions, so the parts
    can be mixed: a complete character is one set from each.

    Args:
        part_names: Part names, e.g. from a parts index.

    Returns:
        Set id to the same shape load_part_presets returns, with species 0.
        A slot with no known region is left out rather than pooled into a
        fourth group nothing would look in.
    """
    sets: dict[str, dict] = {}
    for part_name in part_names:
        parsed = parse_part_name(part_name)
        if parsed is None:
            continue
        group = SLOT_GROUPS.get(parsed["slot"])
        if group is None:
            continue
        family_set = f"{parsed['family']}_{parsed['set']}"
        set_id = f"{family_set}_{group}"
        entry = sets.setdefault(
            set_id,
            {
                "name": f"{family_set} ({group})",
                "group": group,
                "species": 0,
                "parts": {},
            },
        )
        entry["parts"][parsed["slot"]] = part_name
    return sets


def load_color_tables(db_path: Path) -> dict:
    """Read colour slots and palette presets from the Sidekick database.

    Each colour property names one texel of the 32x32 ColorMap, so a preset is
    a set of texel writes. Grouping keeps skin and gear apart: a preset
    recolouring armour never disturbs the character's skin.

    Args:
        db_path: Path to Side_Kick_Data.db.

    Returns:
        {"properties": {name: {"id", "group", "u", "v"}},
         "presets": {id: {"name", "group", "species", "colors": {name: hex}}}}.
        Both empty when the database cannot be read.
    """
    tables: dict = {"properties": {}, "presets": {}}
    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        logger.warning("Could not open Sidekick database %s: %s", db_path, exc)
        return tables

    try:
        property_rows = connection.execute(
            "SELECT id, name, color_group, u, v FROM sk_color_property"
        ).fetchall()
        preset_rows = connection.execute(
            "SELECT p.id, p.name, p.color_group, p.ptr_species, "
            "r.ptr_color_property, r.color "
            "FROM sk_color_preset p "
            "JOIN sk_color_preset_row r ON r.ptr_color_preset = p.id"
        ).fetchall()
    except sqlite3.Error as exc:
        logger.warning("No colour tables in %s: %s", db_path, exc)
        return tables
    finally:
        connection.close()

    by_id: dict[int, str] = {}
    for property_id, name, group, u, v in property_rows:
        tables["properties"][str(name)] = {
            "id": int(property_id),
            "group": int(group),
            "u": int(u),
            "v": int(v),
        }
        by_id[int(property_id)] = str(name)

    for preset_id, name, group, species, property_id, color in preset_rows:
        property_name = by_id.get(int(property_id), "")
        if not property_name:
            continue
        if color is None or str(color).upper() == COLOR_UNSET:
            continue
        entry = tables["presets"].setdefault(
            str(preset_id),
            {
                "name": str(name),
                "group": int(group),
                "species": int(species),
                "colors": {},
            },
        )
        entry["colors"][property_name] = str(color).upper()

    logger.debug(
        "Loaded %d colour propert(ies) and %d preset(s)",
        len(tables["properties"]),
        len(tables["presets"]),
    )
    return tables


def find_master_color_map(source_dirs: list[Path]) -> Path | None:
    """Locate Synty's master 32x32 ColorMap.

    Unlike the per-character palettes, this one defines every colour slot, so
    any combination of parts renders against it without a red texel. It ships
    in the Sidekick tool folder of a Unity project, never in a .unitypackage.

    A second copy lives under the tool's _Demos folder with different contents,
    so the enclosing Resources/Textures path is matched, not the filename.

    Args:
        source_dirs: Directories to search recursively.

    Returns:
        Path to the texture, or None when no source directory carries one.
    """
    for source_dir in source_dirs:
        directory = Path(source_dir)
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("T_ColorMap.png")):
            if path.parent.name == "Textures" and path.parent.parent.name == "Resources":
                return path
    return None


def write_sidekick_gear_sets_json(
    sets: dict[str, dict], output_path: Path, *, indent: int = 2
) -> None:
    """Write sidekick_gear_sets.json for the runtime.

    Args:
        sets: Output of load_part_presets() or derive_gear_sets_from_names().
        output_path: Normally <output_root>/sidekick_gear_sets.json.
        indent: JSON indentation level.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(sets, indent=indent, ensure_ascii=False), encoding="utf-8"
    )
    logger.debug("Wrote %d gear set(s) to %s", len(sets), output_path)


def write_sidekick_colors_json(
    tables: dict, output_path: Path, *, indent: int = 2
) -> None:
    """Write sidekick_colors.json for the runtime palette baker.

    Args:
        tables: Output of load_color_tables().
        output_path: Normally <output_root>/sidekick_colors.json.
        indent: JSON indentation level.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(tables, indent=indent, ensure_ascii=False), encoding="utf-8"
    )
    logger.debug(
        "Wrote %d colour propert(ies) to %s",
        len(tables.get("properties", {})),
        output_path,
    )
