extends RefCounted

# Loader for the renderer-ready packs produced by tools/build_godot_preview.py.
# Not a glTF parser: Godot's regular importer takes priority when available.
var file: FileAccess
var base := 0
var materials: Array[StandardMaterial3D] = []

func load_scene(path: String) -> PackedScene:
	file = FileAccess.open(path, FileAccess.READ)
	if file == null or file.get_buffer(8).get_string_from_ascii() != "DAWVIS1\n":
		return null
	var size := file.get_32()
	if size <= 0 or size > 2_000_000 or size > file.get_length() - 12:
		return null
	var header: Variant = JSON.parse_string(file.get_buffer(size).get_string_from_utf8())
	if not header is Dictionary or not header.has_all(["name", "textures", "materials", "meshes"]):
		return null
	base = file.get_position()
	load_materials(header)
	var root := Node3D.new()
	root.name = header.name
	if header.has("bounds"):
		root.set_meta("visual_bounds", header.bounds)
	var skins: Array[Skin] = []
	if header.has("bones"):
		skins = build_rig(root, header)
	for desc: Dictionary in header.meshes:
		var instance := MeshInstance3D.new()
		instance.name = desc.name
		instance.mesh = load_mesh(desc)
		if desc.skin >= 0:
			instance.skin = skins[int(desc.skin)]
			instance.skeleton = NodePath("../Rig")
		root.add_child(instance)
		instance.owner = root
	var packed := PackedScene.new()
	var err := packed.pack(root)
	root.free()
	file.close()
	return packed if err == OK else null

func bytes(ref: Array) -> PackedByteArray:
	var offset := int(ref[0])
	var count := int(ref[1])
	if offset < 0 or count < 0 or base + offset + count > file.get_length():
		return PackedByteArray()
	file.seek(base + offset)
	return file.get_buffer(count)

func vec3(a: Array) -> Vector3:
	return Vector3(a[0], a[1], a[2])

func read_vec3(ref: Array) -> PackedVector3Array:
	var values := bytes(ref).to_float32_array()
	var out := PackedVector3Array()
	@warning_ignore("integer_division")
	out.resize(values.size() / 3)
	for i in out.size():
		out[i] = Vector3(values[3*i], values[3*i+1], values[3*i+2])
	return out

func read_vec2(ref: Array) -> PackedVector2Array:
	var values := bytes(ref).to_float32_array()
	var out := PackedVector2Array()
	@warning_ignore("integer_division")
	out.resize(values.size() / 2)
	for i in out.size():
		out[i] = Vector2(values[2*i], values[2*i+1])
	return out

func load_materials(header: Dictionary) -> void:
	var textures: Array[ImageTexture] = []
	for ref: Array in header.textures:
		var image := Image.new()
		if image.load_png_from_buffer(bytes(ref)) != OK:
			textures.append(null)
			continue
		image.generate_mipmaps()
		textures.append(ImageTexture.create_from_image(image))
	for data: Dictionary in header.materials:
		var mat := StandardMaterial3D.new()
		var rgba: Array = data.color
		# glTF factors are linear; BaseMaterial3D stores its albedo color in sRGB.
		mat.albedo_color = Color(rgba[0], rgba[1], rgba[2], rgba[3]).linear_to_srgb()
		mat.roughness = 0.82
		if data.texture >= 0:
			mat.albedo_texture = textures[int(data.texture)]
		mat.texture_repeat = data.repeat
		if data.two_sided:
			mat.cull_mode = BaseMaterial3D.CULL_DISABLED
		if data.alpha == "MASK":
			mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
			mat.alpha_scissor_threshold = data.cutoff
		elif data.alpha == "BLEND":
			mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		materials.append(mat)

func load_mesh(desc: Dictionary) -> ArrayMesh:
	var mesh := ArrayMesh.new()
	for src: Dictionary in desc.surfaces:
		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = read_vec3(src.pos)
		arrays[Mesh.ARRAY_NORMAL] = read_vec3(src.normals)
		arrays[Mesh.ARRAY_TEX_UV] = read_vec2(src.uv)
		arrays[Mesh.ARRAY_INDEX] = bytes(src.idx).to_int32_array()
		if src.has("joints"):
			arrays[Mesh.ARRAY_BONES] = bytes(src.joints).to_int32_array()
			arrays[Mesh.ARRAY_WEIGHTS] = bytes(src.weights).to_float32_array()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		mesh.surface_set_material(mesh.get_surface_count() - 1, materials[int(src.mat)])
	return mesh

func build_rig(root: Node3D, header: Dictionary) -> Array[Skin]:
	var rig := Skeleton3D.new()
	rig.name = "Rig"
	root.add_child(rig)
	rig.owner = root
	for bone: Dictionary in header.bones:
		var i := rig.get_bone_count()
		rig.add_bone(bone.name)
		rig.set_bone_parent(i, int(bone.parent))
		var origin := vec3(bone.pos)
		var rot: Array = bone.rot
		var orient := Quaternion(rot[0], rot[1], rot[2], rot[3]).normalized()
		var scale := vec3(bone.scale)
		rig.set_bone_rest(i, Transform3D(Basis(orient).scaled_local(scale), origin))
		rig.set_bone_pose_position(i, origin)
		rig.set_bone_pose_rotation(i, orient)
		rig.set_bone_pose_scale(i, scale)
	var skins: Array[Skin] = []
	for desc: Dictionary in header.skins:
		var skin := Skin.new()
		var a := bytes(desc.inverse).to_float32_array()
		for bind: int in desc.bones.size():
			var i := bind * 16
			var columns := Basis(Vector3(a[i], a[i+1], a[i+2]), Vector3(a[i+4], a[i+5], a[i+6]), Vector3(a[i+8], a[i+9], a[i+10]))
			var offset := Vector3(a[i+12], a[i+13], a[i+14])
			skin.add_bind(int(desc.bones[bind]), Transform3D(columns, offset))
		skins.append(skin)
	var player := AnimationPlayer.new()
	player.name = "AnimationPlayer"
	root.add_child(player)
	player.owner = root
	var library := AnimationLibrary.new()
	for clip: Dictionary in header.clips:
		var anim := Animation.new()
		anim.length = float(clip.length)
		for track: Array in clip.tracks:
			var rot: bool = track[1]
			var id := anim.add_track(Animation.TYPE_ROTATION_3D if rot else Animation.TYPE_POSITION_3D)
			anim.track_set_path(id, NodePath("Rig:" + rig.get_bone_name(int(track[0]))))
			var times := bytes(track[2]).to_float32_array()
			var values := bytes(track[3]).to_float32_array()
			for key in times.size():
				if rot:
					var i := key * 4
					anim.rotation_track_insert_key(id, times[key], Quaternion(values[i], values[i+1], values[i+2], values[i+3]).normalized())
				else:
					var i := key * 3
					anim.position_track_insert_key(id, times[key], Vector3(values[i], values[i+1], values[i+2]))
		library.add_animation(clip.name, anim)
	player.add_animation_library("", library)
	return skins
