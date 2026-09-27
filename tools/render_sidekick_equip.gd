extends SceneTree

## Renders a character before and after equipping gear from another family.
##
## Usage: copy this file into a project with a converted SIDEKICK pack, then
##
##     godot --path <your project> --script res://render_sidekick_equip.gd
##
## Run WITHOUT --headless: a headless process renders nothing and saves a blank
## image. Two PNGs land beside the project, shot_body.png and shot_geared.png.
##
## Proves the wardrobe end to end: that parts assemble onto a shared skeleton,
## and that swapping a whole body region for another family's gear leaves a
## coherent character rather than a heap.

const SidekickCharacterScript := preload("res://addons/synty_sidekick/sidekick_character.gd")


func _init():
	var character: Node3D = SidekickCharacterScript.new()
	root.add_child(character)
	if not character.load_library("res://"):
		print("SHOTS no library")
		quit(1)
		return

	var camera := Camera3D.new()
	camera.position = Vector3(0, 1.0, 2.2)
	camera.look_at_from_position(Vector3(0, 1.0, 2.2), Vector3(0, 1.0, 0), Vector3.UP)
	camera.current = true
	root.add_child(camera)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-45, -30, 0)
	root.add_child(light)

	var seed_name: String = character.parts.keys()[0]
	var seed := (load(String(character.parts[seed_name]["path"])) as PackedScene).instantiate() as Skeleton3D
	character.add_child(seed)
	character.set_base_skeleton(seed)

	# A complete character is one set from each of the three regions.
	var head_id := _best_covered(character, "head")
	var upper_id := _best_covered(character, "upper")
	var lower_id := _best_covered(character, "lower")

	character.equip_set(head_id)
	character.equip_set(upper_id)
	character.equip_set(lower_id)
	character.set_base_loadout()
	for i in range(20): await process_frame
	root.get_texture().get_image().save_png("res://shot_body.png")

	# Now swap the upper region for gear from a different family.
	var other := _other_family_upper(character, upper_id)
	character.equip_set(other)
	for i in range(20): await process_frame
	root.get_texture().get_image().save_png("res://shot_geared.png")

	print("SHOTS head=%s upper=%s lower=%s swapped=%s worn=%d" % [
		head_id, upper_id, lower_id, other, character.worn.size()])
	quit()


## Finds the set of the given group that this library covers most completely.
##
## "Any set with at least one part present" is not enough: the database spans
## Synty's whole catalogue, so most sets resolve to a stray head and nothing
## else.
func _best_covered(character: Node3D, group: String) -> String:
	var best := ""
	var best_have := 0
	for set_id in character.gear_sets:
		var entry: Dictionary = character.gear_sets[set_id]
		if String(entry.get("group", "")) != group:
			continue
		var have := 0
		for slot in entry.get("parts", {}):
			if character.parts.has(String(entry["parts"][slot])):
				have += 1
		if have > best_have:
			best_have = have
			best = String(set_id)
	print("  %s set %s covers %d slots" % [group, best, best_have])
	return best


## Finds a fully-present upper set from a different family than the one worn.
func _other_family_upper(character: Node3D, worn_id: String) -> String:
	var worn_name := String(character.gear_sets[worn_id].get("name", "")).split(" ")[0]
	for set_id in character.gear_sets:
		var entry: Dictionary = character.gear_sets[set_id]
		if String(entry.get("group", "")) != "upper":
			continue
		if String(entry.get("name", "")).begins_with(worn_name):
			continue
		var all_present := true
		for slot in entry.get("parts", {}):
			if not character.parts.has(String(entry["parts"][slot])):
				all_present = false
				break
		if all_present and entry.get("parts", {}).size() >= 10:
			return String(set_id)
	return worn_id
