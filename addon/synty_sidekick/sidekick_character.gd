class_name SidekickCharacter extends Node3D

## A Sidekick character assembled at runtime from the shared parts library.
##
## Gear in Sidekick is body-mesh replacement, not attachment: a knight's
## breastplate IS the torso mesh, and one gear set spans up to 27 slots. So
## equipping means swapping meshes, which is what this node does.
##
## Three orderings matter and fail quietly if changed:
##   - skin is assigned AFTER add_child(), or the part stays in bind pose;
##   - missing bones are grafted BEFORE the mesh is added, or its skin binds
##     resolve to nothing and the geometry renders detached;
##   - the outgoing node is remove_child()'d, not just queue_free()'d, or the
##     deferred free still holds the name and Godot renames the replacement.

const PARTS_DIRNAME := "sidekick_parts"
const MASTER_COLOR_MAP := "T_SidekickMaster_ColorMap.png"
const ANIMATION_DIRNAME := "animations"

## Sidekick clips are converted into libraries with this suffix, one per pack.
const SIDEKICK_LIBRARY_SUFFIX := "_Sidekick.res"


func _ready() -> void:
	# The AnimationPlayer runs at the default priority of 0, and the joint
	# offsets have to land after it - a clip rewrites those bones every frame.
	process_priority = 100

var skeleton: Skeleton3D = null

var parts: Dictionary = {}          # part name -> index entry
var gear_sets: Dictionary = {}      # set id -> {name, group, species, parts}
var color_properties: Dictionary = {}
var color_presets: Dictionary = {}

var worn: Dictionary = {}           # slot -> MeshInstance3D
var worn_names: Dictionary = {}     # slot -> part name
var base_loadout: Dictionary = {}   # slot -> part name to revert to

## Bone name -> blend type -> {offset, rotation}, from the tool database.
##
## Applied to bone POSES, never to rests: a clip overwrites these joints every
## frame, so an offset folded into the rest is discarded as soon as one plays.
var rig_adjustments: Dictionary = {}

var animation_player: AnimationPlayer = null

## Bone names the playing clip drives, per channel.
##
## Offsets are added on top of the pose, so the base must be whatever supplies
## that channel this frame: the clip's value where it drives one, the bone's rest
## where it does not. Get it wrong and an undriven channel compounds every frame
## until the joint leaves the scene. Which channels a clip drives varies per clip.
var _driven_positions: Dictionary = {}
var _driven_rotations: Dictionary = {}

var body_type := 50.0
var body_size := 0.0
var muscle := 50.0

var palette_image: Image = null
var _palette_texture: ImageTexture = null
var _material: ShaderMaterial = null
var _library_root := "res://"


## Reads the library indexes written by the converter.
##
## @param root Output root holding sidekick_parts.json and its siblings.
## @returns bool True when at least one part is known.
func load_library(root: String = "res://") -> bool:
	_library_root = root.trim_suffix("/") + "/"
	parts = _read_json(_library_root + "sidekick_parts.json")
	gear_sets = _read_json(_library_root + "sidekick_gear_sets.json")
	var colors := _read_json(_library_root + "sidekick_colors.json")
	color_properties = colors.get("properties", {})
	color_presets = colors.get("presets", {})
	rig_adjustments = _read_json(_library_root + "sidekick_rig_adjustments.json")
	_load_palette()
	return not parts.is_empty()


func _read_json(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed if parsed is Dictionary else {}


## Adopts a skeleton to build on, and records its rests.
##
## @param new_skeleton Normally the result of create_base_skeleton().
func set_base_skeleton(new_skeleton: Skeleton3D) -> void:
	skeleton = new_skeleton


## Builds a skeleton carrying the core rig.
##
## Part rigs run from 1 bone to 117, so neither the first nor the largest is a
## safe seed - the largest is a shoulder pad carrying its own cloth simulation.
## The core rig is the modal one, preferring a Torso among those as a canonical
## body part rather than an attachment that happens to match.
##
## @returns A new Skeleton3D, or null when the library holds no parts.
func create_base_skeleton() -> Skeleton3D:
	var frequency := {}
	for part_name in parts:
		var count: int = parts[part_name].get("bones", []).size()
		frequency[count] = int(frequency.get(count, 0)) + 1
	var core_size := 0
	var most := 0
	for size in frequency:
		if frequency[size] > most:
			most = frequency[size]
			core_size = size

	var best := ""
	for part_name in parts:
		var entry: Dictionary = parts[part_name]
		if entry.get("bones", []).size() != core_size:
			continue
		best = part_name
		if String(entry.get("slot", "")) == "Torso":
			break
	if best.is_empty():
		return null
	var scene := load(String(parts[best].get("path", ""))) as PackedScene
	if scene == null:
		return null
	var donor := scene.instantiate() as Skeleton3D
	if donor == null:
		return null
	# The donor's mesh is not wanted, only its rig.
	for child in donor.get_children():
		donor.remove_child(child)
		child.queue_free()
	return donor


## Swaps every slot a gear set covers, then rebakes the palette once.
##
## @param set_id Key into gear_sets.
## @returns int Slots actually filled.
func equip_set(set_id: String) -> int:
	if not gear_sets.has(set_id):
		return 0
	var entry: Dictionary = gear_sets[set_id]
	var filled := 0
	for slot in entry.get("parts", {}):
		if set_part(String(slot), String(entry["parts"][slot])):
			filled += 1
	# Grafting may have added an attachment joint that was not there before.
	apply_joint_adjustments()
	return filled


## Fills one slot.
##
## @param slot Body slot, e.g. "Torso".
## @param part_name Key into parts.
## @returns bool True when the part loaded and was placed.
func set_part(slot: String, part_name: String) -> bool:
	if skeleton == null or not parts.has(part_name):
		return false
	var scene := load(String(parts[part_name].get("path", ""))) as PackedScene
	if scene == null:
		return false
	var donor := scene.instantiate() as Skeleton3D
	if donor == null:
		return false

	# Grafting first: skin binds resolve by bone name, so a part whose dynamic
	# bones are absent renders detached.
	graft_missing_bones(donor)

	var source := donor.get_child(0) as MeshInstance3D
	if source == null:
		donor.free()
		return false

	var replacement := MeshInstance3D.new()
	replacement.name = "%s_%s" % [slot, part_name]
	replacement.mesh = source.mesh
	var donor_skin := source.skin

	if worn.has(slot) and is_instance_valid(worn[slot]):
		skeleton.remove_child(worn[slot])
		worn[slot].queue_free()
	skeleton.add_child(replacement)
	replacement.skeleton = replacement.get_path_to(skeleton)
	replacement.skin = donor_skin
	worn[slot] = replacement
	worn_names[slot] = part_name
	donor.free()

	_apply_shapes_to(replacement)
	_apply_palette_to(replacement)
	return true


## Snapshots what is currently worn as the loadout clear_slot() reverts to.
##
## Sidekick has no naked body under the armour: an armoured torso replaces the
## bare one outright, so "take the chest piece off" only means anything against
## a loadout you nominate as the default. Equip the unarmoured character, call
## this, then layer gear on.
func set_base_loadout() -> void:
	base_loadout = worn_names.duplicate()


## Reverts one slot to the base loadout, so removing armour exposes the body.
##
## With no base loadout set the slot simply empties.
func clear_slot(slot: String) -> void:
	if base_loadout.has(slot):
		set_part(slot, String(base_loadout[slot]))
		return
	if worn.has(slot) and is_instance_valid(worn[slot]):
		skeleton.remove_child(worn[slot])
		worn[slot].queue_free()
	worn.erase(slot)
	worn_names.erase(slot)


## Adds bones the current skeleton lacks, taking rests and parentage from the
## part's own skeleton.
##
## Bones are appended, so existing indices - and the skins already bound to
## them - are unaffected.
##
## @param donor The part's skeleton.
## @returns int Number of bones added.
func graft_missing_bones(donor: Skeleton3D) -> int:
	var added := 0
	# Godot orders bones parents-first, so a parent is always already present by
	# the time its child is considered.
	for i in range(donor.get_bone_count()):
		var bone_name := donor.get_bone_name(i)
		if skeleton.find_bone(bone_name) != -1:
			continue
		var parent := donor.get_bone_parent(i)
		if parent < 0:
			continue
		var parent_index := skeleton.find_bone(donor.get_bone_name(parent))
		if parent_index == -1:
			continue
		skeleton.add_bone(bone_name)
		var index := skeleton.get_bone_count() - 1
		skeleton.set_bone_parent(index, parent_index)
		skeleton.set_bone_rest(index, donor.get_bone_rest(i))
		skeleton.reset_bone_pose(index)
		added += 1
	return added


## Sets the three proportion sliders, each running -100..100.
func set_proportions(new_type: float, new_size: float, new_muscle: float) -> void:
	body_type = new_type
	body_size = new_size
	muscle = new_muscle
	for slot in worn:
		_apply_shapes_to(worn[slot])
	# Blend shapes reshape the body mesh but leave the attachment joints where
	# they were, so gear would float off a heavy character without this.
	apply_joint_adjustments()


## Drives a part's four proportion blend shapes.
##
## Mirrors SidekickRuntime.UpdateBlendShapes. Zero is not neutral: the defaults
## are 50/0/50, so leaving the shapes unset renders every character fully
## masculine and unmuscled. Unity weights run 0..100 and Godot's 0..1, hence the
## final division.
func _apply_shapes_to(mesh_instance: MeshInstance3D) -> void:
	if mesh_instance == null or mesh_instance.mesh == null:
		return
	for i in range(mesh_instance.mesh.get_blend_shape_count()):
		# Names are prefixed per part, e.g. "HIPSBlends.defaultHeavy".
		var shape_name := String(mesh_instance.mesh.get_blend_shape_name(i))
		var weight := -1.0
		if shape_name.ends_with("masculineFeminine"):
			weight = (body_type + 100.0) / 2.0
		elif shape_name.ends_with("defaultSkinny"):
			weight = -body_size if body_size < 0.0 else 0.0
		elif shape_name.ends_with("defaultHeavy"):
			weight = body_size if body_size > 0.0 else 0.0
		elif shape_name.ends_with("Buff"):
			weight = (muscle + 100.0) / 2.0
		if weight >= 0.0:
			mesh_instance.set_blend_shape_value(i, weight / 100.0)


## Blend order matters: the quaternion product below is not commutative.
const BLEND_ORDER := ["feminine", "heavy", "skinny", "bulk"]


## Converts the three proportion sliders into the four blend weights.
##
## Mirrors SidekickRuntime. The sliders run -100..100 and the weights 0..1.
##
## @returns Blend type name to weight.
func _blend_weights() -> Dictionary:
	return {
		"feminine": (body_type + 100.0) / 200.0,
		"heavy": body_size / 100.0 if body_size > 0.0 else 0.0,
		"skinny": -body_size / 100.0 if body_size < 0.0 else 0.0,
		"bulk": (muscle + 100.0) / 200.0,
	}


## Moves the 11 attachment joints to follow the body's proportions.
##
## Synty keeps the per-joint maxima in its tool database; each is scaled by the
## character's corresponding blend weight and accumulated. Without this, blend
## shapes reshape the body while the gear stays put, so a back banner or a hip
## pouch floats off a heavy character.
##
## Offsets go onto the POSE, since a playing clip rewrites these bones every
## frame and would discard anything folded into the rest. What keeps it
## idempotent is the base: the current pose while a clip re-supplies it each
## frame, the bone's rest while stopped.
func apply_joint_adjustments() -> void:
	if rig_adjustments.is_empty() or skeleton == null:
		return
	var animating := animation_player != null and animation_player.is_playing()
	var weights := _blend_weights()

	for bone_name in rig_adjustments:
		var index := skeleton.find_bone(String(bone_name))
		if index == -1:
			continue
		var rest := skeleton.get_bone_rest(index)
		var origin: Vector3 = (
			skeleton.get_bone_pose_position(index)
			if animating and _driven_positions.has(bone_name)
			else rest.origin)
		var rotation: Quaternion = (
			skeleton.get_bone_pose_rotation(index)
			if animating and _driven_rotations.has(bone_name)
			else rest.basis.get_rotation_quaternion())

		var per_blend: Dictionary = rig_adjustments[bone_name]
		# BlendShapeType order - the quaternion product is not commutative.
		for blend_name in BLEND_ORDER:
			if not per_blend.has(blend_name):
				continue
			var weight: float = weights[blend_name]
			var entry: Dictionary = per_blend[blend_name]
			origin += _to_vector3(entry.get("offset", [])) * weight
			var degrees := _to_vector3(entry.get("rotation", []))
			if degrees != Vector3.ZERO:
				var target := Quaternion.from_euler(Vector3(
					deg_to_rad(degrees.x), deg_to_rad(degrees.y), deg_to_rad(degrees.z)))
				rotation = rotation * Quaternion.IDENTITY.slerp(target, weight)

		skeleton.set_bone_pose_position(index, origin)
		skeleton.set_bone_pose_rotation(index, rotation)


## Re-applies the joint offsets after the AnimationPlayer has advanced.
##
## process_priority puts this after the player, whose default priority is 0.
func _process(_delta: float) -> void:
	apply_joint_adjustments()


## Reads a three-element JSON array as a Vector3.
##
## @param values Array of three numbers; anything else yields zero.
## @returns The converted vector.
func _to_vector3(values) -> Vector3:
	if not values is Array or values.size() != 3:
		return Vector3.ZERO
	return Vector3(float(values[0]), float(values[1]), float(values[2]))



# ----------------------------------------------------------------- animation

## Loads every converted Sidekick animation library.
##
## Clip tracks are addressed as "Skeleton3D:<bone>", relative to the player's
## root_node - so the player is rooted at this node and the skeleton must be
## named Skeleton3D, which is what the converter writes and what
## create_base_skeleton() returns.
##
## @param directory Where the converter wrote animations/, default the library root.
## @returns int Number of libraries added.
func load_animations(directory: String = "") -> int:
	if directory.is_empty():
		directory = _library_root + ANIMATION_DIRNAME
	if animation_player == null:
		animation_player = AnimationPlayer.new()
		add_child(animation_player)
	animation_player.root_node = animation_player.get_path_to(self)
	for existing in animation_player.get_animation_library_list():
		animation_player.remove_animation_library(existing)

	var handle := DirAccess.open(directory)
	if handle == null:
		push_warning("No animations at %s" % directory)
		return 0
	var added := 0
	for file in handle.get_files():
		if not file.ends_with(SIDEKICK_LIBRARY_SUFFIX):
			continue
		var library := load("%s/%s" % [directory, file]) as AnimationLibrary
		if library == null:
			continue
		animation_player.add_animation_library(file.get_basename(), library)
		added += 1
	return added


## Lists every clip name across the loaded libraries, without library prefixes.
func animation_clips() -> PackedStringArray:
	var names := PackedStringArray()
	if animation_player == null:
		return names
	for library_name in animation_player.get_animation_library_list():
		var library := animation_player.get_animation_library(library_name)
		for clip in library.get_animation_list():
			names.append(String(clip))
	return names


## Plays a clip by its bare name, searching each loaded library.
##
## @param clip Clip name without a library prefix.
## @param loop Whether to loop it.
## @returns bool True when a library held the clip.
func play(clip: String, loop: bool = true) -> bool:
	if animation_player == null or clip.is_empty():
		return false
	for library_name in animation_player.get_animation_library_list():
		var full := "%s/%s" % [library_name, clip] if not String(library_name).is_empty() else clip
		if not animation_player.has_animation(full):
			continue
		var animation := animation_player.get_animation(full)
		animation.loop_mode = Animation.LOOP_LINEAR if loop else Animation.LOOP_NONE
		_record_driven_channels(animation)
		animation_player.play(full)
		return true
	return false


## Notes which bones a clip drives, so apply_joint_adjustments() knows which
## channels are re-supplied each frame and which it must base on the rest.
func _record_driven_channels(animation: Animation) -> void:
	_driven_positions.clear()
	_driven_rotations.clear()
	for i in range(animation.get_track_count()):
		var bone := String(animation.track_get_path(i)).get_slice(":", 1)
		match animation.track_get_type(i):
			Animation.TYPE_POSITION_3D:
				_driven_positions[bone] = true
			Animation.TYPE_ROTATION_3D:
				_driven_rotations[bone] = true


## Stops playback, leaving the character in its rest pose plus joint offsets.
func stop() -> void:
	if animation_player != null:
		animation_player.stop()
	_driven_positions.clear()
	_driven_rotations.clear()
	for i in range(skeleton.get_bone_count() if skeleton != null else 0):
		skeleton.reset_bone_pose(i)
	apply_joint_adjustments()


# ------------------------------------------------------------------- palette

func _load_palette() -> void:
	var path := _library_root + PARTS_DIRNAME + "/" + MASTER_COLOR_MAP
	var texture := load(path) as Texture2D
	if texture == null:
		push_warning("No master Sidekick palette at %s; recolouring disabled" % path)
		return
	palette_image = texture.get_image().duplicate()
	palette_image.convert(Image.FORMAT_RGBA8)
	_palette_texture = ImageTexture.create_from_image(palette_image)

	# Clone a converted pack material rather than naming a shader path. The
	# converter writes shaders wherever the project already keeps them, so a
	# hard-coded path would silently load nothing and every part would render
	# with no material at all.
	var template := _find_material_template()
	if template == null:
		push_warning("No Sidekick pack material to clone; parts render untinted")
		return
	_material = template.duplicate()
	_material.set_shader_parameter("base_texture", _palette_texture)


## Finds any converted Sidekick pack material to use as a shader template.
##
## @returns A ShaderMaterial, or null when no Sidekick pack is present.
func _find_material_template() -> ShaderMaterial:
	var root := DirAccess.open(_library_root)
	if root == null:
		return null
	for directory in root.get_directories():
		if not directory.begins_with("SIDEKICK_"):
			continue
		var materials := DirAccess.open(_library_root + directory + "/materials")
		if materials == null:
			continue
		for file in materials.get_files():
			if not file.ends_with(".tres"):
				continue
			var loaded := load(
				"%s%s/materials/%s" % [_library_root, directory, file]) as ShaderMaterial
			if loaded != null:
				return loaded
	return null


## Writes every colour a preset defines, then pushes one texture update.
##
## @param preset_id Key into color_presets.
## @returns bool True when the preset was applied.
func apply_color_preset(preset_id: String) -> bool:
	if palette_image == null or not color_presets.has(preset_id):
		return false
	var colors: Dictionary = color_presets[preset_id].get("colors", {})
	for property_name in colors:
		_write_property(String(property_name), Color.html(String(colors[property_name])))
	_palette_texture.update(palette_image)
	return true


## Recolours one named slot, e.g. "Metal 01" for a rarity tint.
##
## @param property_name A key of color_properties.
## @param color The colour to write.
## @returns bool True when the property exists and was written.
func recolour(property_name: String, color: Color) -> bool:
	if palette_image == null or not _write_property(property_name, color):
		return false
	_palette_texture.update(palette_image)
	return true


func _write_property(property_name: String, color: Color) -> bool:
	if not color_properties.has(property_name):
		return false
	var entry: Dictionary = color_properties[property_name]
	palette_image.set_pixel(int(entry["u"]), int(entry["v"]), color)
	return true


## Repaints one worn slot with the character's palette material.
##
## Public so a tool can override a slot's material and then put it back.
##
## @param slot Body slot.
func apply_palette_to_slot(slot: String) -> void:
	if worn.has(slot) and is_instance_valid(worn[slot]):
		_apply_palette_to(worn[slot])


func _apply_palette_to(mesh_instance: MeshInstance3D) -> void:
	if _material == null or mesh_instance == null or mesh_instance.mesh == null:
		return
	for surface in range(mesh_instance.mesh.get_surface_count()):
		mesh_instance.set_surface_override_material(surface, _material)
