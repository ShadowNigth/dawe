extends RigidBody3D

const Assets = preload("res://scripts/assets.gd")
const DustCollision = preload("res://scripts/dust_collision.gd")

var weapon_id := ""
var silenced := false
var age := 0.0

func configure(id: String, with_silencer: bool) -> void:
	weapon_id = id
	silenced = with_silencer
	collision_layer = 0
	collision_mask = DustCollision.WORLD
	continuous_cd = true
	mass = 0.7
	var physics := PhysicsMaterial.new()
	physics.bounce = 0.15
	physics.friction = 0.85
	physics_material_override = physics
	var model := Assets.instantiate_asset(id + "-drop")
	if model == null:
		var fallback := MeshInstance3D.new()
		var box := BoxMesh.new()
		box.size = Vector3(0.06, 0.095, 0.58 if id == "ak-47" else 0.28)
		var paint := StandardMaterial3D.new()
		paint.albedo_color = Color("474f54")
		box.material = paint
		fallback.mesh = box
		model = fallback
	add_child(model)
	var silencer := model.find_child("Silencer", true, false) as Node3D
	if silencer != null:
		silencer.visible = with_silencer
	var bounds := AABB()
	var found := false
	for part in model.find_children("*", "MeshInstance3D", true, false) + ([model] if model is MeshInstance3D else []):
		if part is MeshInstance3D and part.visible:
			var box: AABB = part.get_aabb()
			bounds = bounds.merge(box) if found else box
			found = true
	var collider := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = bounds.size.max(Vector3(0.035, 0.035, 0.035)) * 0.93
	collider.shape = shape
	collider.position = bounds.get_center()
	add_child(collider)

func _physics_process(delta: float) -> void:
	age += delta
