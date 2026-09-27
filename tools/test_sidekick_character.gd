extends SceneTree

## Exercises SidekickCharacter against the real converted library.
##
## Usage: copy this file into a project with a converted SIDEKICK pack, then
##
##     godot --headless --path <your project> --script res://test_sidekick_character.gd
##
## Headless is fine here: this one asserts rather than renders.
##
## The palette check is the important one: it samples every worn part's UV
## texels against the baked palette and fails on a pure red one, which is
## Synty's "this colour slot is undefined" sentinel showing through. That is the
## exact failure the shared library exists to prevent, across the whole wardrobe
## rather than the one character someone happened to look at.

## Preloaded rather than referenced by class_name: a --script run does not
## rescan the project, so the global class list may not yet know the type.
const SidekickCharacterScript := preload("res://addons/synty_sidekick/sidekick_character.gd")


func _init():
	var character: Node3D = SidekickCharacterScript.new()
	root.add_child(character)
	if not character.load_library("res://"):
		print("FAIL no parts library")
		quit(1)
		return
	print("LIBRARY parts=%d sets=%d properties=%d presets=%d" % [
		character.parts.size(), character.gear_sets.size(),
		character.color_properties.size(), character.color_presets.size()])

	# A core skeleton taken from any one part: every part carries the full rig.
	var seed_name: String = character.parts.keys()[0]
	var seed := (load(String(character.parts[seed_name]["path"])) as PackedScene).instantiate() as Skeleton3D
	character.add_child(seed)
	character.set_base_skeleton(seed)

	# The database describes Synty's whole Sidekick catalogue, but a converted
	# library only holds the packs actually installed. A set naming no part we
	# have is therefore expected; a set naming parts we DO have and filling
	# nothing is a real failure, and only that is counted as one.
	var unavailable := 0
	var failed := 0
	var equipped := 0
	var started := Time.get_ticks_msec()
	for set_id in character.gear_sets:
		var wanted: Dictionary = character.gear_sets[set_id].get("parts", {})
		var available := 0
		for slot in wanted:
			if character.parts.has(String(wanted[slot])):
				available += 1
		var filled: int = character.equip_set(String(set_id))
		if available == 0:
			unavailable += 1
		elif filled < available:
			failed += 1
			print("  set %s filled %d of %d available" % [set_id, filled, available])
		equipped += 1
	var elapsed := Time.get_ticks_msec() - started
	print("EQUIP sets=%d unavailable=%d failed=%d total_ms=%d mean_ms=%.1f" % [
		equipped, unavailable, failed, elapsed, float(elapsed) / maxf(equipped, 1)])

	var unresolved := 0
	for slot in character.worn:
		var node: MeshInstance3D = character.worn[slot]
		for b in range(node.skin.get_bind_count()):
			if character.skeleton.find_bone(node.skin.get_bind_name(b)) == -1:
				unresolved += 1
	print("BINDS unresolved=%d bones=%d worn=%d" % [
		unresolved, character.skeleton.get_bone_count(), character.worn.size()])

	var joints_ok := _check_joint_adjustments(character)
	var anim_ok := await _check_animation(character)
	var red := _count_red_texels(character)
	print("PALETTE red_texels_sampled=%d" % red)

	if failed > 0 or unresolved > 0 or red > 0 or not joints_ok or not anim_ok:
		print("FAIL")
		quit(1)
	else:
		print("PASS")
		quit(0)


## Samples every worn part's UV texels against the baked palette.
##
## @param character The assembled character.
## @returns int Count of distinct sampled texels that are pure red.
func _count_red_texels(character: Node3D) -> int:
	if character.palette_image == null:
		return 0
	var size: int = character.palette_image.get_width()
	var red := 0
	for slot in character.worn:
		var node: MeshInstance3D = character.worn[slot]
		var arrays: Array = node.mesh.surface_get_arrays(0)
		var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
		var seen := {}
		for uv in uvs:
			var texel := Vector2i(
				clampi(int(floor(uv.x * size)), 0, size - 1),
				clampi(int(floor(uv.y * size)), 0, size - 1))
			if seen.has(texel):
				continue
			seen[texel] = true
			var c: Color = character.palette_image.get_pixelv(texel)
			if c.r > 0.98 and c.g < 0.02 and c.b < 0.02:
				red += 1
	return red


## Checks that attachment joints follow the proportion sliders.
##
## Three things can go wrong and only the first is obvious: the joints never
## move, they move but accumulate a little further on every call, or they never
## come back when the sliders return to their defaults.
##
## @param character The assembled character.
## @returns bool True when all three hold.
func _check_joint_adjustments(character: Node3D) -> bool:
	if character.rig_adjustments.is_empty():
		print("JOINTS no rig adjustments in the library; skipped")
		return true
	var bone_name := String(character.rig_adjustments.keys()[0])
	var index: int = character.skeleton.find_bone(bone_name)
	if index == -1:
		print("JOINTS %s absent from the skeleton; skipped" % bone_name)
		return true

	# Poses, not rests: rests stay pristine so a playing clip cannot discard the
	# offset, and the adjustment is written to the pose instead.
	character.set_proportions(50.0, 0.0, 50.0)
	var neutral: Vector3 = character.skeleton.get_bone_pose_position(index)

	character.set_proportions(50.0, 100.0, 50.0)
	var heavy: Vector3 = character.skeleton.get_bone_pose_position(index)
	var moved := neutral.distance_to(heavy)

	# Applying the same proportions again must land in exactly the same place.
	# While stopped nothing re-supplies the pose, so the offset has to be
	# computed from the bone's rest rather than from its current pose - or each
	# call would fold into the next and the joint would drift.
	character.set_proportions(50.0, 100.0, 50.0)
	var again: Vector3 = character.skeleton.get_bone_pose_position(index)
	var drift := heavy.distance_to(again)

	character.set_proportions(50.0, 0.0, 50.0)
	var restored: Vector3 = character.skeleton.get_bone_pose_position(index)
	var residue := neutral.distance_to(restored)

	print("JOINTS %s moved=%.4f drift=%.6f residue=%.6f" % [
		bone_name, moved, drift, residue])
	return moved > 0.0001 and drift < 0.000001 and residue < 0.000001


## Checks that clips play and that joint offsets survive playback.
##
## This is the case rest-based adjustment cannot handle: 8 of the 11 attachment
## joints carry position tracks, so a playing clip rewrites their pose every
## frame and an offset folded into the rest is simply discarded. The assertion
## is that the same clip, at the same time, puts an animated joint in a
## different place for a heavy character than for a neutral one.
##
## @param character The assembled character.
## @returns bool True when a clip played and the offset held.
func _check_animation(character: Node3D) -> bool:
	var libraries: int = character.load_animations()
	var clips: PackedStringArray = character.animation_clips()
	print("ANIM libraries=%d clips=%d" % [libraries, clips.size()])
	if clips.is_empty():
		print("ANIM no Sidekick clips converted; skipped")
		return true

	var bone := "backAttach"
	var index: int = character.skeleton.find_bone(bone)
	if index == -1:
		print("ANIM %s absent; skipped" % bone)
		return true

	if not character.play(String(clips[0]), true):
		print("ANIM could not play %s" % clips[0])
		return false

	character.set_proportions(50.0, 0.0, 50.0)
	var neutral := await _sample_pose(character, index)
	character.set_proportions(50.0, 100.0, 50.0)
	var heavy := await _sample_pose(character, index)
	var moved := neutral.distance_to(heavy)

	# And still no accumulation: sampling again must land in the same place.
	var heavy_again := await _sample_pose(character, index)
	var drift := heavy.distance_to(heavy_again)

	# A joint the clip does not position-track is never reset by it, so the
	# per-frame offset would compound. Measured before this was handled: the hip
	# joints left the scene entirely, 10 units in 60 frames.
	var undriven := ""
	for candidate in character.rig_adjustments:
		if not character._driven_positions.has(String(candidate)):
			undriven = String(candidate)
			break
	var creep := 0.0
	if not undriven.is_empty():
		var undriven_index: int = character.skeleton.find_bone(undriven)
		var start := await _sample_pose(character, undriven_index)
		for i in range(60):
			await process_frame
		creep = start.distance_to(character.skeleton.get_bone_pose_position(undriven_index))

	character.stop()
	print("ANIM clip=%s moved_during_playback=%.4f drift=%.6f undriven=%s creep=%.6f" % [
		clips[0], moved, drift, undriven, creep])
	return moved > 0.0001 and drift < 0.001 and creep < 0.001


## Advances a few frames and reads a bone's animated pose.
func _sample_pose(character: Node3D, index: int) -> Vector3:
	for i in range(4):
		await process_frame
	return character.skeleton.get_bone_pose_position(index)
