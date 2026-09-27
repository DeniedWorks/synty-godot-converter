extends SceneTree

## Renders a converted character part-way through a bound animation clip.
##
## Structural-bone coverage decides whether a library binds, and every check
## behind that decision is numeric. On this branch numeric checks passed while
## gear silently drifted out of the scene, so a bind is not confirmed until a
## frame of it has been looked at.
##
## Usage: copy this file into your converted project, then
##
##     godot --path <your project> --script res://render_bound_character.gd
##
## Run WITHOUT --headless: a headless process renders nothing and saves a blank
## image. Three PNGs land beside the project - at rest, mid-clip, and later in
## the same clip.
##
## With no arguments it finds a rigged character for you. Set CHARACTER to check
## a particular one, and TAG to name the output files:
##
##     CHARACTER=res://POLYGON_Vikings/meshes/tscn_separate/SM_Chr_Viking_01.tscn
##     TAG=viking

## Empty means "find one", which is what a fresh conversion needs: naming a pack
## here would be naming one the user may not own.
var CHARACTER: String = ""
## Renders land in the project being checked, under res://.
const OUT_DIR := "res://"

## Frames to let the viewport settle before a capture. One frame renders black:
## the viewport has not drawn yet.
const SETTLE_FRAMES := 20


## Finds any converted character scene, so the script runs against whatever the
## user actually converted rather than a pack this repo happened to test with.
##
## @returns String A res:// path, or "" when the project holds no rigged
##                 character.
func _first_character(path: String = "res://") -> String:
	var dir := DirAccess.open(path)
	if dir == null:
		return ""
	for name in dir.get_files():
		# Synty names every character mesh SM_Chr_, but so are the attachments
		# that hang off one, and those carry no skeleton - so open it and look.
		if not name.begins_with("SM_Chr_") or not name.ends_with(".tscn"):
			continue
		var packed := load(path.path_join(name)) as PackedScene
		if packed == null:
			continue
		var node := packed.instantiate()
		var rigged: bool = (
			_find(node, "Skeleton3D") != null and _find(node, "AnimationPlayer") != null
		)
		node.free()
		if rigged:
			return path.path_join(name)
	for name in dir.get_directories():
		if name.begins_with("."):
			continue
		var found := _first_character(path.path_join(name))
		if not found.is_empty():
			return found
	return ""


func _find(node: Node, type: String) -> Node:
	if node.get_class() == type:
		return node
	for child in node.get_children():
		var found := _find(child, type)
		if found != null:
			return found
	return null


func _init():
	var override := OS.get_environment("CHARACTER")
	if not override.is_empty():
		CHARACTER = override
	elif CHARACTER.is_empty():
		CHARACTER = _first_character()
		if CHARACTER.is_empty():
			print("RENDER no rigged character found under res:// - convert a "
				+ "character pack first, or set CHARACTER=res://...")
			quit(1)
			return
		print("RENDER found %s" % CHARACTER)
	var suffix := OS.get_environment("TAG")
	if suffix.is_empty():
		suffix = "default"
	var scene := load(CHARACTER) as PackedScene
	if scene == null:
		print("RENDER no scene at %s" % CHARACTER)
		quit(1)
		return
	var character := scene.instantiate() as Node3D
	root.add_child(character)

	var player := _find(character, "AnimationPlayer") as AnimationPlayer
	var skeleton := _find(character, "Skeleton3D") as Skeleton3D
	if player == null or skeleton == null:
		print("RENDER missing player=%s skeleton=%s" % [player == null, skeleton == null])
		quit(1)
		return

	var clips: PackedStringArray = player.get_animation_list()
	print("RENDER bones=%d libraries=%s clips=%d" % [
		skeleton.get_bone_count(), str(player.get_animation_library_list()), clips.size()])

	# A plain walk shows a broken bind faster than anything stylised. Root-motion
	# clips drive the root itself and would confound a collapse with intended
	# travel, and an additive clip is a partial-body delta, not a pose.
	var chosen := ""
	var wanted_clip := OS.get_environment("CLIP")
	for name in clips:
		var text := String(name)
		if not wanted_clip.is_empty():
			if text.contains(wanted_clip):
				chosen = text
				break
			continue
		if text.contains("Walk") and not text.contains("Additive") 				and not text.contains("RootMotion"):
			chosen = text
			break
	if chosen.is_empty() and clips.size() > 0:
		chosen = String(clips[0])
	if chosen.is_empty():
		print("RENDER no clips bound")
		quit(1)
		return
	print("RENDER playing '%s'" % chosen)

	# Frame the character from its own bounds: a Polygon pack's characters are
	# not all one size, and a fixed camera makes a correct bind look wrong.
	var bounds := AABB()
	var first := true
	for node in _all_nodes(character):
		if node is VisualInstance3D:
			var box: AABB = (node as VisualInstance3D).get_aabb()
			box = (node as Node3D).global_transform * box
			bounds = box if first else bounds.merge(box)
			first = false
	var centre := bounds.get_center()
	var span: float = maxf(bounds.size.y, maxf(bounds.size.x, bounds.size.z))
	print("RENDER bounds centre=%.2f,%.2f,%.2f span=%.2f" % [
		centre.x, centre.y, centre.z, span])

	var camera := Camera3D.new()
	var distance: float = maxf(span * 2.0, 0.5)
	camera.look_at_from_position(
		centre + Vector3(distance * 0.7, distance * 0.35, distance * 0.7),
		centre, Vector3.UP)
	camera.current = true
	root.add_child(camera)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-45, -35, 0)
	root.add_child(light)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-20, 140, 0)
	fill.light_energy = 0.4
	root.add_child(fill)

	var hips := skeleton.find_bone("Hips")

	# The control. If the character is wrong here, the bind is not the cause.
	for i in SETTLE_FRAMES:
		await process_frame
	_report("rest", skeleton, hips)
	root.get_texture().get_image().save_png("%s/bound_%s_rest.png" % [OUT_DIR, suffix])

	player.play(chosen)
	for i in SETTLE_FRAMES:
		await process_frame
	_report("playing", skeleton, hips)
	root.get_texture().get_image().save_png("%s/bound_%s_playing.png" % [OUT_DIR, suffix])

	for i in SETTLE_FRAMES:
		await process_frame
	_report("playing_later", skeleton, hips)
	root.get_texture().get_image().save_png("%s/bound_%s_later.png" % [OUT_DIR, suffix])
	quit()


## Collects every node in a branch, so bounds cover all of a character's meshes.
func _all_nodes(node: Node) -> Array:
	var out := [node]
	for child in node.get_children():
		out.append_array(_all_nodes(child))
	return out


## Prints where the hips and the head sit, which is where a bad bind shows.
func _report(label: String, skeleton: Skeleton3D, hips: int) -> void:
	var hip_origin := Vector3.ZERO
	if hips >= 0:
		hip_origin = skeleton.get_bone_global_pose(hips).origin
	var head := skeleton.find_bone("Head")
	var head_origin := Vector3.ZERO
	if head >= 0:
		head_origin = skeleton.get_bone_global_pose(head).origin
	print("RENDER %-14s hips=%.3f,%.3f,%.3f head=%.3f,%.3f,%.3f" % [
		label, hip_origin.x, hip_origin.y, hip_origin.z,
		head_origin.x, head_origin.y, head_origin.z])
