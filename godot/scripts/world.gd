extends Node3D

const Assets = preload("res://scripts/assets.gd")
const DustCollision = preload("res://scripts/dust_collision.gd")
const DIAGNOSTIC_SHADER = preload("res://scripts/collision_view.gdshader")
const LONG_SPAWN := Vector3(15.67, 0.18, -3.19)
var dust2 := false
var collision_count := 0
var collision_view := false
var textured_sector := false
var diagnostic_material: ShaderMaterial

func build(force_training: bool, inspect_collision: bool, prefer_sector := false) -> void:
	if not force_training:
		var visual: Node3D = null if inspect_collision or prefer_sector else Assets.instantiate_asset("dust2")
		if visual == null and not inspect_collision:
			visual = Assets.instantiate_asset("dust2-long")
			textured_sector = visual != null
		if textured_sector:
			var b: Array = visual.get_meta("visual_bounds")
			diagnostic_material = ShaderMaterial.new()
			diagnostic_material.shader = DIAGNOSTIC_SHADER
			diagnostic_material.set_shader_parameter("textured_bounds", Vector4(b[0], b[1], b[2], b[3]))
		if visual != null or inspect_collision:
			var parts := DustCollision.read_cache()
			for part in parts:
				add_faces(part.faces, part.layer, inspect_collision or textured_sector)
			# Older local generated directories still work with Godot's glTF importer.
			if collision_count == 0 and visual != null:
				var physics: Node3D = Assets.instantiate_asset("dust2-physics")
				if physics != null:
					physics.hide()
					add_child(physics)
					add_collision(physics)
					physics.queue_free()
			if collision_count > 0:
				dust2 = true
				collision_view = inspect_collision
				if visual != null:
					add_child(visual)
			elif visual != null:
				visual.free()
	if not dust2:
		textured_sector = false
		training()
	lighting()

func add_faces(faces: PackedVector3Array, layer: int, visualize: bool) -> void:
	var shape := ConcavePolygonShape3D.new()
	shape.backface_collision = true
	shape.set_faces(faces)
	body(shape, Transform3D.IDENTITY, layer)
	collision_count += 1
	if visualize and layer == DustCollision.WORLD and DisplayServer.get_name() != "headless":
		var geometry := []
		geometry.resize(Mesh.ARRAY_MAX)
		geometry[Mesh.ARRAY_VERTEX] = faces
		var mesh := ArrayMesh.new()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, geometry)
		if diagnostic_material == null:
			diagnostic_material = ShaderMaterial.new()
			diagnostic_material.shader = DIAGNOSTIC_SHADER
		var instance := MeshInstance3D.new()
		instance.mesh = mesh
		instance.material_override = diagnostic_material
		instance.visibility_range_end = 42.0
		instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(instance)

func add_collision(parent: Node) -> void:
	if parent is MeshInstance3D:
		var instance := parent as MeshInstance3D
		if instance.mesh != null:
			var faces := instance.mesh.get_faces()
			if not faces.is_empty():
				# Bake the glTF scale and node transforms into the shape geometry.
				for i in faces.size():
					faces[i] = instance.global_transform * faces[i]
				add_faces(faces, DustCollision.WORLD, false)
	for child in parent.get_children():
		add_collision(child)

func body(shape: Shape3D, pose: Transform3D, layer := DustCollision.WORLD) -> void:
	var solid := StaticBody3D.new()
	solid.transform = pose
	solid.collision_layer = layer
	solid.collision_mask = 0
	var collider := CollisionShape3D.new()
	collider.shape = shape
	solid.add_child(collider)
	add_child(solid)

func block(at: Vector3, size: Vector3, color: Color, pitch := 0.0) -> void:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.95
	var mesh := BoxMesh.new()
	mesh.size = size
	mesh.material = material
	var visible_block := MeshInstance3D.new()
	visible_block.mesh = mesh
	visible_block.position = at
	visible_block.rotation.x = pitch
	add_child(visible_block)
	var shape := BoxShape3D.new()
	shape.size = size
	body(shape, visible_block.transform)

func training() -> void:
	var sand := Color("bda17e")
	var plaster := Color("dcc5a4")
	var wood := Color("725139")
	block(Vector3(0, -0.3, 1), Vector3(14, 0.6, 8), sand)
	# Ramp rises 1.5 m over 6 m; box coordinates offset for the top face.
	var pitch := atan2(1.5, 6.0)
	block(Vector3(0, 0.75 - cos(pitch)*0.2, -6 - sin(pitch)*0.2),
		Vector3(14, 0.4, Vector2(6, 1.5).length()), sand, pitch)
	block(Vector3(0, 1.2, -12), Vector3(14, 0.6, 6), sand)
	block(Vector3(0, 2.6, -15), Vector3(14, 3, 0.4), plaster)
	for side in [-1, 1]:
		block(Vector3(side*7, 1.7, -5), Vector3(0.4, 4.3, 20), plaster)
		block(Vector3(side*4, 1.3, -1), Vector3(5.6, 2.6, 0.6), plaster)
		block(Vector3(side*0.98, 0.9, -1), Vector3(0.65, 1.8, 0.16), wood)
		block(Vector3(side*3.1, 1.95, -11), Vector3(1.0, 0.9, 1.0), wood)
	block(Vector3(0, 2.32, -1), Vector3(2.4, 0.55, 0.6), plaster)

func lighting() -> void:
	var sky_material := ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color("5d91c0")
	sky_material.sky_horizon_color = Color("b8cddb")
	var sky := Sky.new()
	sky.sky_material = sky_material
	var environment := Environment.new()
	environment.background_mode = Environment.BG_SKY
	environment.sky = sky
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color("fff1dd")
	environment.ambient_light_energy = 0.55
	var world := WorldEnvironment.new()
	world.environment = environment
	add_child(world)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-63, -31, 0)
	sun.light_energy = 0.56
	sun.shadow_enabled = not collision_view and not textured_sector
	add_child(sun)
