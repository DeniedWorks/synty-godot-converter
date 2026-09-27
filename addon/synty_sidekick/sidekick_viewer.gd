extends Node3D
## Interactive viewer for converted Sidekick characters.
##
## Lets you swap any body slot, equip a gear set, drag the three proportion
## sliders, recolour, and play any converted Sidekick clip.
##
## The model is SidekickCharacter, driven off the shared parts library, so the
## viewer holds no assembly logic of its own - no grafting, no blend weights, no
## joint adjustment. Before the library existed this file duplicated all of it
## and sourced parts by instantiating a whole character scene to steal one mesh
## out of it, which limited the wardrobe to parts some shipped recipe happened
## to use.

const PACK_PREFIX := "SIDEKICK_"
const DEFAULT_CHARACTER := "FantasyKnights_05"

const SidekickCharacterScript := preload("res://addons/synty_sidekick/sidekick_character.gd")

## Readable names for the source families the parts index records.
##
## A family is what a Synty pack actually corresponds to - the output pack
## folders all share one part pool, so filtering by folder would filter nothing.
const FAMILY_NAMES := {
	"FANT_KNGT": "Fantasy Knights",
	"FANT_SKTN": "Fantasy Skeletons",
	"GOBL_FIGT": "Goblin Fighters",
	"GOBL_BASE": "Goblin (base)",
	"VIKG_WARR": "Viking Warriors",
	"HUMN_BASE": "Human (base)",
	"SKTN_BASE": "Skeleton (base)",
	"APOC_ZOMB": "Apocalypse Zombies",
	"ZOMB_BASE": "Zombie (base)",
	"SCFI_ROBO": "SciFi Robots",
	"ROBO_BASE": "Robot (base)",
	"SCFI_CIVL": "SciFi Civilian",
	"HORR_VILN": "Horror Villain",
	"SPEC_HUMN_BASE": "Human (spec)",
	"FUTR_APOC_OUTL": "Apocalypse Outlaws (futr)",
}

## Palette-picker entry meaning "give each part the palette of the character it
## was authored against".
##
## Synty authors a 32x32 palette per character, not per pack, and fills the
## slots that character does not use with pure red. A part whose UVs index an
## unused slot therefore renders bright red under a foreign palette - the
## texture loaded fine, it simply has no colour defined there.
const NATIVE_PALETTE := "(each part's own)"

## Palette-picker entry meaning the master map, which defines every colour slot
## and so can never render a part red.
const MASTER_PALETTE := "(master)"

var character: Node3D = null

# slot -> Array of {mesh, family, palette}
var slot_parts: Dictionary = {}
# "Pack / Character" -> {pack, name, recipe}
var characters: Dictionary = {}
# material name -> resource path
var palettes: Dictionary = {}
# part name -> the palette it was authored against
var part_palettes: Dictionary = {}
# family code -> whether its parts are offered
var family_enabled: Dictionary = {}
# family code -> number of distinct parts
var family_counts: Dictionary = {}
# slot -> Label showing the filtered count
var slot_labels: Dictionary = {}

var current_palette := NATIVE_PALETTE
var current_character := ""

var slider_boxes: Array = []
var animation_names: Array[String] = []
var filtered_animations: Array[String] = []

var camera: Camera3D
var camera_yaw := 0.0
var camera_pitch := -0.05
var camera_distance := 2.6
var camera_target := Vector3(0, 0.95, 0)
var dragging := false

var slot_options: Dictionary = {}
var animation_list: ItemList
var animation_filter: LineEdit
var status_label: Label
var character_picker: OptionButton
var palette_picker: OptionButton
var preset_picker: OptionButton
var set_pickers: Dictionary = {}
var loop_toggle: CheckBox
var family_checks: Dictionary = {}


func _ready() -> void:
	_build_world()

	character = SidekickCharacterScript.new()
	add_child(character)
	if not character.load_library("res://"):
		_status("No sidekick_parts.json under res:// - convert a SIDEKICK_ pack first")
		return
	var skeleton: Skeleton3D = character.create_base_skeleton()
	if skeleton == null:
		_status("The parts library holds no usable rig")
		return
	character.add_child(skeleton)
	character.set_base_skeleton(skeleton)
	character.load_animations()

	_scan_library()
	animation_names.assign(character.animation_clips())
	animation_names.sort()
	_build_ui()

	var start := ""
	for key in characters:
		if characters[key].name == DEFAULT_CHARACTER:
			start = key
			break
	if start.is_empty() and not characters.is_empty():
		start = characters.keys()[0]
	if start.is_empty():
		_status("No recipes found; pick parts or a gear set to build a character")
		return
	_load_character(start)


# ---------------------------------------------------------------- world setup

func _build_world() -> void:
	var environment := Environment.new()
	environment.background_mode = Environment.BG_SKY
	environment.sky = Sky.new()
	environment.sky.sky_material = ProceduralSkyMaterial.new()
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	environment.ambient_light_energy = 0.6
	var world := WorldEnvironment.new()
	world.environment = environment
	add_child(world)

	var key_light := DirectionalLight3D.new()
	key_light.rotation_degrees = Vector3(-42, -38, 0)
	key_light.light_energy = 1.1
	key_light.shadow_enabled = true
	add_child(key_light)

	var fill_light := DirectionalLight3D.new()
	fill_light.rotation_degrees = Vector3(-20, 140, 0)
	fill_light.light_energy = 0.35
	add_child(fill_light)

	var floor_mesh := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(12, 12)
	floor_mesh.mesh = plane
	var floor_material := StandardMaterial3D.new()
	floor_material.albedo_color = Color(0.17, 0.16, 0.18)
	floor_mesh.material_override = floor_material
	add_child(floor_mesh)

	camera = Camera3D.new()
	add_child(camera)
	_update_camera()


func _update_camera() -> void:
	var offset := Vector3(
		sin(camera_yaw) * cos(camera_pitch),
		sin(camera_pitch),
		cos(camera_yaw) * cos(camera_pitch)
	) * camera_distance
	camera.position = camera_target + offset
	camera.look_at(camera_target, Vector3.UP)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT:
			dragging = event.pressed
		elif event.button_index == MOUSE_BUTTON_WHEEL_UP:
			camera_distance = max(0.8, camera_distance - 0.15)
			_update_camera()
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			camera_distance = min(8.0, camera_distance + 0.15)
			_update_camera()
	elif event is InputEventMouseMotion and dragging:
		camera_yaw -= event.relative.x * 0.008
		camera_pitch = clamp(camera_pitch + event.relative.y * 0.006, -1.2, 1.2)
		_update_camera()
	elif event is InputEventKey and event.pressed:
		if event.keycode == KEY_LEFT:
			_step_animation(-1)
		elif event.keycode == KEY_RIGHT:
			_step_animation(1)


# ------------------------------------------------------------ library scanning

## Indexes the parts library for the UI, and reads each pack's recipes and
## palettes.
##
## Parts come from sidekick_parts.json rather than from assembled scenes, so
## every part is offered - including those no shipped recipe uses.
func _scan_library() -> void:
	for part_name in character.parts:
		var entry: Dictionary = character.parts[part_name]
		var slot := String(entry.get("slot", ""))
		if slot.is_empty():
			continue
		var family := String(entry.get("family", ""))
		if not slot_parts.has(slot):
			slot_parts[slot] = []
		slot_parts[slot].append({"mesh": part_name, "family": family})
		family_counts[family] = int(family_counts.get(family, 0)) + 1
		family_enabled[family] = true
	for slot in slot_parts:
		slot_parts[slot].sort_custom(func(a, b): return a.mesh < b.mesh)

	var root := DirAccess.open("res://")
	if root == null:
		return
	for directory in root.get_directories():
		if directory.begins_with(PACK_PREFIX):
			_scan_pack(directory)


func _scan_pack(pack: String) -> void:
	var materials := DirAccess.open("res://%s/materials" % pack)
	if materials != null:
		for file in materials.get_files():
			if file.ends_with(".tres"):
				palettes[file.get_basename()] = "res://%s/materials/%s" % [pack, file]

	var recipes_path := "res://%s/sidekick_characters.json" % pack
	if not FileAccess.file_exists(recipes_path):
		return
	var recipes = JSON.parse_string(FileAccess.get_file_as_string(recipes_path))
	if not recipes is Dictionary:
		return
	for name in recipes:
		var recipe: Dictionary = recipes[name]
		characters["%s / %s" % [pack.trim_prefix(PACK_PREFIX), name]] = {
			"pack": pack, "name": name, "recipe": recipe,
		}
		# A part's native palette is the one of the character that uses it.
		var palette := String(recipe.get("material", name))
		for entry in recipe.get("parts", []):
			var mesh := String(entry.get("mesh", ""))
			if not mesh.is_empty() and not part_palettes.has(mesh):
				part_palettes[mesh] = palette


# ----------------------------------------------------------- character loading

## Rebuilds the character from a recipe, one set_part per slot.
func _load_character(key: String) -> void:
	if not characters.has(key):
		return
	var entry: Dictionary = characters[key]
	current_character = key
	var recipe: Dictionary = entry.recipe

	var wanted := {}
	for part in recipe.get("parts", []):
		var slot := String(part.get("slot", ""))
		var mesh := String(part.get("mesh", ""))
		if slot.is_empty() or mesh.is_empty():
			continue
		wanted[slot] = mesh
	for slot in character.worn.keys():
		if not wanted.has(slot):
			character.clear_slot(slot)
	var placed := 0
	for slot in wanted:
		if character.set_part(slot, String(wanted[slot])):
			placed += 1

	var shapes: Dictionary = recipe.get("blend_shapes", {})
	character.set_proportions(
		float(shapes.get("body_type", 50.0)),
		float(shapes.get("body_size", 0.0)),
		float(shapes.get("muscle", 50.0)))
	# This is what "unequipped" means for clear_slot from here on.
	character.set_base_loadout()

	current_palette = NATIVE_PALETTE
	_apply_palette()
	_refresh_slot_choices()
	_sync_ui_to_character()
	_status("%s - %d bones, %d parts" % [
		entry.name, character.skeleton.get_bone_count(), character.worn.size()])


# --------------------------------------------------------------- part swapping

func _set_part(slot: String, mesh_name: String) -> void:
	if mesh_name.is_empty():
		character.clear_slot(slot)
		_status("Cleared %s" % slot)
		return
	if not character.set_part(slot, mesh_name):
		_status("Could not place %s" % mesh_name)
		return
	_apply_palette_to(slot)
	_select_in_slot_picker(slot, mesh_name)
	_status("%s -> %s" % [slot, mesh_name])


func _equip_set(set_id: String) -> void:
	if set_id.is_empty():
		return
	var filled: int = character.equip_set(set_id)
	_apply_palette()
	_sync_ui_to_character()
	var entry: Dictionary = character.gear_sets.get(set_id, {})
	_status("%s: filled %d of %d slots" % [
		entry.get("name", set_id), filled, entry.get("parts", {}).size()])


func _select_in_slot_picker(slot: String, mesh_name: String) -> void:
	if not slot_options.has(slot):
		return
	var picker: OptionButton = slot_options[slot]
	for i in range(picker.item_count):
		if String(picker.get_item_metadata(i)) == mesh_name:
			picker.select(i)
			return


## Lists the parts a slot may offer under the current source filter.
##
## The worn part is always included even when its family is filtered out, so the
## dropdown never misrepresents what the character is actually wearing.
func _filtered_parts(slot: String) -> Array:
	var worn := String(character.worn_names.get(slot, ""))
	var out := []
	for part in slot_parts.get(slot, []):
		if family_enabled.get(part.family, true) or part.mesh == worn:
			out.append(part)
	return out


# -------------------------------------------------------------------- palette

## Names the palette a slot should render with.
func _palette_for(slot: String) -> String:
	if current_palette == MASTER_PALETTE:
		return ""
	if current_palette == NATIVE_PALETTE:
		return String(part_palettes.get(String(character.worn_names.get(slot, "")), ""))
	return current_palette


func _apply_palette() -> void:
	for slot in character.worn:
		_apply_palette_to(slot)


func _apply_palette_to(slot: String) -> void:
	var wanted := _palette_for(slot)
	if wanted.is_empty() or not palettes.has(wanted):
		# Nothing better to offer, so fall back to the master palette, which
		# defines every colour slot and so can never render a part red.
		character.apply_palette_to_slot(slot)
		return
	var material := load(palettes[wanted]) as Material
	if material == null:
		return
	var mesh_instance: MeshInstance3D = character.worn[slot]
	for surface in range(mesh_instance.mesh.get_surface_count()):
		mesh_instance.set_surface_override_material(surface, material)


# ------------------------------------------------------------------ animation

func _play_animation(name: String) -> void:
	if name.is_empty():
		return
	if character.play(name, loop_toggle.button_pressed):
		_status("Playing %s" % name)
	else:
		_status("No library holds %s" % name)


func _step_animation(direction: int) -> void:
	if filtered_animations.is_empty():
		return
	var current := animation_list.get_selected_items()
	var index := (current[0] if not current.is_empty() else -1) + direction
	index = clamp(index, 0, filtered_animations.size() - 1)
	animation_list.select(index)
	animation_list.ensure_current_is_visible()
	_play_animation(filtered_animations[index])


# ------------------------------------------------------------------------- UI

func _build_ui() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)

	var left := PanelContainer.new()
	left.set_anchors_and_offsets_preset(Control.PRESET_LEFT_WIDE)
	left.offset_right = 344
	layer.add_child(left)

	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	left.add_child(scroll)
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.custom_minimum_size = Vector2(310, 0)
	scroll.add_child(column)

	column.add_child(_heading("Character"))
	character_picker = OptionButton.new()
	character_picker.fit_to_longest_item = false
	var keys := characters.keys()
	keys.sort()
	for key in keys:
		character_picker.add_item(key)
	character_picker.item_selected.connect(func(i): _load_character(character_picker.get_item_text(i)))
	column.add_child(character_picker)

	var randomise := Button.new()
	randomise.text = "Randomise parts"
	randomise.pressed.connect(_randomise_parts)
	column.add_child(randomise)

	# Gear sets, split the way Synty's database splits them: three body regions
	# that between them cover all 38 slots.
	column.add_child(_heading("Gear sets"))
	for group in ["head", "upper", "lower"]:
		var label := Label.new()
		label.add_theme_font_size_override("font_size", 11)
		var picker := OptionButton.new()
		picker.fit_to_longest_item = false
		picker.custom_minimum_size = Vector2(300, 0)
		picker.add_item("(pick a %s set)" % group)
		picker.set_item_metadata(0, "")
		var available := 0
		var ids: Array = character.gear_sets.keys()
		ids.sort_custom(func(a, b):
			return _set_label(a) < _set_label(b))
		for set_id in ids:
			var entry: Dictionary = character.gear_sets[set_id]
			if String(entry.get("group", "")) != group:
				continue
			var have := 0
			for slot in entry.get("parts", {}):
				if character.parts.has(String(entry["parts"][slot])):
					have += 1
			if have == 0:
				continue
			available += 1
			picker.add_item("%s  (%d)" % [entry.get("name", set_id), have])
			picker.set_item_metadata(picker.item_count - 1, String(set_id))
		picker.item_selected.connect(func(i): _equip_set(String(picker.get_item_metadata(i))))
		label.text = "%s  (%d available)" % [group.capitalize(), available]
		set_pickers[group] = picker
		column.add_child(label)
		column.add_child(picker)

	column.add_child(_heading("Palette"))
	palette_picker = OptionButton.new()
	var palette_names := palettes.keys()
	palette_names.sort()
	palette_picker.add_item(NATIVE_PALETTE)
	palette_picker.add_item(MASTER_PALETTE)
	for name in palette_names:
		palette_picker.add_item(name)
	palette_picker.item_selected.connect(func(i):
		current_palette = palette_picker.get_item_text(i)
		_apply_palette())
	column.add_child(palette_picker)

	# Colour presets recolour named slots of the master palette, so they show
	# only where the master is in use.
	preset_picker = OptionButton.new()
	preset_picker.fit_to_longest_item = false
	preset_picker.custom_minimum_size = Vector2(300, 0)
	preset_picker.add_item("(colour preset)")
	preset_picker.set_item_metadata(0, "")
	var preset_ids: Array = character.color_presets.keys()
	preset_ids.sort_custom(func(a, b):
		return _preset_label(a) < _preset_label(b))
	for preset_id in preset_ids:
		var preset: Dictionary = character.color_presets[preset_id]
		preset_picker.add_item("%s  (%d)" % [
			preset.get("name", preset_id), preset.get("colors", {}).size()])
		preset_picker.set_item_metadata(preset_picker.item_count - 1, String(preset_id))
	preset_picker.item_selected.connect(func(i):
		var id := String(preset_picker.get_item_metadata(i))
		if id.is_empty():
			return
		if character.apply_color_preset(id):
			_status("Applied preset %s" % character.color_presets[id].get("name", id))
		else:
			_status("No master palette loaded; recolouring unavailable"))
	column.add_child(preset_picker)

	column.add_child(_heading("Proportions"))
	var type_box := _slider("Body type  (masc <-> fem)", -100, 100, character.body_type, func(v):
		character.set_proportions(v, character.body_size, character.muscle))
	var size_box := _slider("Body size  (skinny <-> heavy)", -100, 100, character.body_size, func(v):
		character.set_proportions(character.body_type, v, character.muscle))
	var muscle_box := _slider("Muscle", -100, 100, character.muscle, func(v):
		character.set_proportions(character.body_type, character.body_size, v))
	column.add_child(type_box)
	column.add_child(size_box)
	column.add_child(muscle_box)
	slider_boxes = [
		{"node": type_box, "label": type_box.get_meta("label"), "property": "body_type",
			"text": "Body type  (masc <-> fem)"},
		{"node": size_box, "label": size_box.get_meta("label"), "property": "body_size",
			"text": "Body size  (skinny <-> heavy)"},
		{"node": muscle_box, "label": muscle_box.get_meta("label"), "property": "muscle",
			"text": "Muscle"},
	]

	column.add_child(_heading("Sources"))
	var source_buttons := HBoxContainer.new()
	column.add_child(source_buttons)
	var all_button := Button.new()
	all_button.text = "All"
	all_button.pressed.connect(func(): _set_all_families(true))
	source_buttons.add_child(all_button)
	var none_button := Button.new()
	none_button.text = "None"
	none_button.pressed.connect(func(): _set_all_families(false))
	source_buttons.add_child(none_button)

	var family_codes := family_counts.keys()
	family_codes.sort_custom(func(a, b): return _family_label(a) < _family_label(b))
	for code in family_codes:
		var check := CheckBox.new()
		check.text = "%s  (%d)" % [_family_label(code), family_counts[code]]
		check.button_pressed = true
		check.add_theme_font_size_override("font_size", 12)
		check.toggled.connect(func(pressed):
			family_enabled[code] = pressed
			_refresh_slot_choices())
		family_checks[code] = check
		column.add_child(check)

	column.add_child(_heading("Parts"))
	var slots := slot_parts.keys()
	slots.sort()
	for slot in slots:
		var label := Label.new()
		label.add_theme_font_size_override("font_size", 11)
		column.add_child(label)
		slot_labels[slot] = label

		var row := HBoxContainer.new()
		column.add_child(row)

		var previous_button := Button.new()
		previous_button.text = "<"
		previous_button.custom_minimum_size = Vector2(28, 0)
		previous_button.pressed.connect(func(): _cycle_slot(slot, -1))
		row.add_child(previous_button)

		var picker := OptionButton.new()
		picker.fit_to_longest_item = false
		picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		picker.item_selected.connect(func(i): _set_part(slot, String(picker.get_item_metadata(i))))
		slot_options[slot] = picker
		row.add_child(picker)

		var next_button := Button.new()
		next_button.text = ">"
		next_button.custom_minimum_size = Vector2(28, 0)
		next_button.pressed.connect(func(): _cycle_slot(slot, 1))
		row.add_child(next_button)

		_repopulate_slot(slot)

	# Animation panel, kept on the right so the part list stays readable.
	var right := PanelContainer.new()
	right.set_anchors_and_offsets_preset(Control.PRESET_RIGHT_WIDE)
	right.offset_left = -330
	layer.add_child(right)
	var right_column := VBoxContainer.new()
	right_column.size_flags_vertical = Control.SIZE_EXPAND_FILL
	right.add_child(right_column)

	right_column.add_child(_heading("Animation  (%d clips)" % animation_names.size()))
	animation_filter = LineEdit.new()
	animation_filter.placeholder_text = "filter, e.g. idle / run / attack"
	animation_filter.text_changed.connect(func(_t): _refresh_animation_list())
	right_column.add_child(animation_filter)

	animation_list = ItemList.new()
	animation_list.custom_minimum_size = Vector2(280, 420)
	animation_list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	animation_list.item_selected.connect(func(i): _play_animation(filtered_animations[i]))
	right_column.add_child(animation_list)

	var buttons := HBoxContainer.new()
	right_column.add_child(buttons)
	var previous := Button.new()
	previous.text = "< Prev"
	previous.pressed.connect(func(): _step_animation(-1))
	buttons.add_child(previous)
	var next := Button.new()
	next.text = "Next >"
	next.pressed.connect(func(): _step_animation(1))
	buttons.add_child(next)
	var stop := Button.new()
	stop.text = "Stop"
	stop.pressed.connect(func():
		character.stop()
		_status("Stopped"))
	buttons.add_child(stop)

	loop_toggle = CheckBox.new()
	loop_toggle.text = "Loop"
	loop_toggle.button_pressed = true
	right_column.add_child(loop_toggle)

	status_label = Label.new()
	status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status_label.custom_minimum_size = Vector2(280, 44)
	right_column.add_child(status_label)

	var help := Label.new()
	help.text = "Drag to orbit, wheel to zoom, arrow keys cycle clips."
	help.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	help.add_theme_font_size_override("font_size", 11)
	right_column.add_child(help)

	_refresh_animation_list()


func _heading(text: String) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 15)
	return label


func _slider(text: String, low: float, high: float, value: float, on_change: Callable) -> VBoxContainer:
	var box := VBoxContainer.new()
	var label := Label.new()
	label.text = "%s: %.0f" % [text, value]
	label.add_theme_font_size_override("font_size", 11)
	box.add_child(label)
	var slider := HSlider.new()
	slider.min_value = low
	slider.max_value = high
	slider.step = 1
	slider.value = value
	slider.custom_minimum_size = Vector2(300, 0)
	slider.value_changed.connect(func(v):
		label.text = "%s: %.0f" % [text, v]
		on_change.call(v))
	box.add_child(slider)
	box.set_meta("slider", slider)
	box.set_meta("label", label)
	return box


func _set_label(set_id) -> String:
	return String(character.gear_sets[set_id].get("name", set_id))


func _preset_label(preset_id) -> String:
	return String(character.color_presets[preset_id].get("name", preset_id))


func _family_label(code: String) -> String:
	return FAMILY_NAMES.get(code, code)


func _short_name(mesh: String) -> String:
	# SK_FANT_KNGT_17_10TORS_HU01 reads better as FANT_KNGT_17 HU01.
	var parts := mesh.trim_prefix("SK_").split("_")
	if parts.size() >= 5:
		return "%s_%s_%s %s" % [parts[0], parts[1], parts[2], parts[4]]
	return mesh.trim_prefix("SK_")


func _sync_ui_to_character() -> void:
	for slot in slot_options:
		var picker: OptionButton = slot_options[slot]
		var wanted := String(character.worn_names.get(slot, ""))
		var chosen := 0
		for i in range(picker.item_count):
			if String(picker.get_item_metadata(i)) == wanted:
				chosen = i
				break
		picker.select(chosen)

	for i in range(palette_picker.item_count):
		if palette_picker.get_item_text(i) == current_palette:
			palette_picker.select(i)
			break

	for i in range(character_picker.item_count):
		if character_picker.get_item_text(i) == current_character:
			character_picker.select(i)
			break

	for entry in slider_boxes:
		var slider: HSlider = entry.node.get_meta("slider")
		slider.set_value_no_signal(character.get(entry.property))
		entry.label.text = "%s: %.0f" % [entry.text, slider.value]


func _refresh_animation_list() -> void:
	var needle := animation_filter.text.to_lower()
	filtered_animations.clear()
	animation_list.clear()
	for name in animation_names:
		if needle.is_empty() or name.to_lower().contains(needle):
			filtered_animations.append(name)
			animation_list.add_item(name)


## Rebuilds every slot dropdown against the current source filter.
func _refresh_slot_choices() -> void:
	for slot in slot_options:
		_repopulate_slot(slot)


func _repopulate_slot(slot: String) -> void:
	var picker: OptionButton = slot_options[slot]
	var choices := _filtered_parts(slot)

	picker.clear()
	picker.add_item("(none)")
	picker.set_item_metadata(0, "")
	for part in choices:
		picker.add_item(_short_name(part.mesh))
		picker.set_item_metadata(picker.item_count - 1, part.mesh)

	if slot_labels.has(slot):
		slot_labels[slot].text = "%s  (%d)" % [slot, choices.size()]

	_select_in_slot_picker(slot, String(character.worn_names.get(slot, "")))


func _set_all_families(enabled: bool) -> void:
	for code in family_checks:
		family_enabled[code] = enabled
		family_checks[code].set_pressed_no_signal(enabled)
	_refresh_slot_choices()
	_status("%s all sources" % ("Enabled" if enabled else "Disabled"))


## Steps one slot through its filtered choices, wrapping at both ends.
##
## "(none)" is part of the cycle so an attachment can be stepped off as well as
## through.
func _cycle_slot(slot: String, direction: int) -> void:
	var picker: OptionButton = slot_options[slot]
	if picker.item_count <= 1:
		_status("%s has no parts under the current filter" % slot)
		return
	var index := picker.selected
	if index < 0:
		index = 0
	index = wrapi(index + direction, 0, picker.item_count)
	picker.select(index)
	_set_part(slot, String(picker.get_item_metadata(index)))


func _randomise_parts() -> void:
	var changed := 0
	var skipped := 0
	for slot in slot_options:
		# The worn part is kept out of the pool, or a filtered-out family could
		# be re-picked purely because the character already had it on.
		var pool := []
		for part in _filtered_parts(slot):
			if family_enabled.get(part.family, true):
				pool.append(part)
		if pool.is_empty():
			skipped += 1
			continue
		var pick: Dictionary = pool[randi() % pool.size()]
		_set_part(slot, pick.mesh)
		changed += 1
	_sync_ui_to_character()
	if skipped > 0:
		_status("Randomised %d slots, %d had nothing enabled" % [changed, skipped])
	else:
		_status("Randomised %d slots" % changed)


func _status(text: String) -> void:
	if status_label != null:
		status_label.text = text
	print(text)
