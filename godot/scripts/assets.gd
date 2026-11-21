extends RefCounted

const VisualPack = preload("res://scripts/visual_pack.gd")
const DIR := "res://generated/"

static var preview_cache: Dictionary = {}

static func instantiate_asset(name: String) -> Node3D:
	var path := DIR + name + ".glb"
	if ResourceLoader.exists(path, "PackedScene"):
		var packed := load(path) as PackedScene
		if packed != null:
			return packed.instantiate() as Node3D
	var preview_path := DIR + name + ".vis"
	if not preview_cache.has(name) and FileAccess.file_exists(preview_path):
		var preview := VisualPack.new().load_scene(preview_path)
		if preview != null:
			preview_cache[name] = preview
	if preview_cache.has(name):
		return preview_cache[name].instantiate() as Node3D
	return null

static func read_json(name: String) -> Dictionary:
	var file := FileAccess.open(DIR + name + ".json", FileAccess.READ)
	if file != null:
		var data: Variant = JSON.parse_string(file.get_as_text())
		if data is Dictionary:
			return data
	return {}

static func load_texture(id: String) -> Texture2D:
	var path := DIR + id + ".png"
	if ResourceLoader.exists(path, "Texture2D"):
		return load(path) as Texture2D
	if FileAccess.file_exists(path):
		var image := Image.load_from_file(path)
		if image != null and not image.is_empty():
			return ImageTexture.create_from_image(image)
	return null
