@tool
extends EditorPlugin

## The addon ships a runtime node and a viewer scene rather than editor UI, so
## enabling it needs only to make the scripts available - which having them in
## the project already does. Godot requires a plugin script regardless.


func _enter_tree() -> void:
	pass


func _exit_tree() -> void:
	pass
