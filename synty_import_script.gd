@tool
extends EditorScenePostImport
## Automatically generates trimesh collision for Synty prefabs on import.
## Only processes FBX files in paths containing "synty".

# Path pattern to detect Synty assets
const SYNTY_PATH_PATTERN = "synty"

# LOD meshes to skip (only LOD0 gets collision)
const LOD_SKIP_PATTERNS = ["_LOD1", "_LOD2", "_LOD3", "_LOD4", "_LOD5"]

# Mesh types that should not have collision
const COLLISION_SKIP_PATTERNS = ["FX_", "Particle", "_Glass", "_Water", "_Decal"]


func _post_import(scene: Node) -> Object:
	var source_file := get_source_file()

	# Only process Synty assets (path-based detection)
	if not SYNTY_PATH_PATTERN in source_file.to_lower():
		return scene

	print("[SyntyImport] Processing: ", source_file)

	var collision_count := _add_collision_recursive(scene)

	if collision_count > 0:
		print("[SyntyImport] Added trimesh collision to ", collision_count, " mesh(es)")

	return scene


func _add_collision_recursive(node: Node) -> int:
	if node == null:
		return 0

	var count := 0

	if node is MeshInstance3D:
		var mesh_instance := node as MeshInstance3D
		if _should_process(mesh_instance):
			mesh_instance.create_trimesh_collision()
			count += 1

	# Recurse into children
	for child in node.get_children():
		count += _add_collision_recursive(child)

	return count


func _should_process(mesh: MeshInstance3D) -> bool:
	# Skip if mesh is null or empty
	if mesh.mesh == null:
		return false

	var node_name := mesh.name as String

	# Skip LOD meshes (only use LOD0 for collision)
	for pattern in LOD_SKIP_PATTERNS:
		if pattern in node_name:
			return false

	# Skip FX/glass/water meshes that shouldn't have collision
	for pattern in COLLISION_SKIP_PATTERNS:
		if pattern in node_name:
			return false

	# Skip if collision already exists (has StaticBody3D child)
	for child in mesh.get_children():
		if child is StaticBody3D:
			return false

	return true
