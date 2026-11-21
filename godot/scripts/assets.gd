extends RefCounted

const DIR := "res://generated/"

static func instantiate_asset(name: String) -> Node3D:
	var path := DIR + name + ".glb"
	if ResourceLoader.exists(path, "PackedScene"):
		var packed := load(path) as PackedScene
		if packed != null:
			return packed.instantiate() as Node3D
	return null

static func read_json(name: String) -> Dictionary:
	var file := FileAccess.open(DIR + name + ".json", FileAccess.READ)
	if file != null:
		var data: Variant = JSON.parse_string(file.get_as_text())
		if data is Dictionary:
			return data
	return {}
