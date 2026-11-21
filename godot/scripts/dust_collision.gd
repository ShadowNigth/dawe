extends RefCounted

const CACHE := "res://generated/dust2-collision.bin"
const MAGIC := "DAWCOL1\n"
const WORLD := 1
const PLAYER_CLIP := 2
const PLAYER := 4
const SOLIDS := WORLD | PLAYER_CLIP

static func read_cache() -> Array[Dictionary]:
	var file := FileAccess.open(CACHE, FileAccess.READ)
	if file == null:
		return []
	if file.get_buffer(8).get_string_from_ascii() != MAGIC:
		return []
	var parts := file.get_32()
	if parts <= 0 or parts > 512:
		return []
	var scene: Array[Dictionary] = []
	for i in parts:
		var layer := file.get_32()
		var n := file.get_32()
		if layer > 1 or n <= 0 or n % 3 != 0 or n * 12 > file.get_length() - file.get_position():
			return []
		var xyz := file.get_buffer(n * 12).to_float32_array()
		var positions := PackedVector3Array()
		positions.resize(n)
		for v in n:
			positions[v] = Vector3(xyz[3*v], xyz[3*v+1], xyz[3*v+2])
		scene.append({"layer": WORLD if layer == 0 else PLAYER_CLIP, "faces": positions})
	return scene if file.get_position() == file.get_length() else []
