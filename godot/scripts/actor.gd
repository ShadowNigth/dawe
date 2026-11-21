extends CharacterBody3D

const Assets = preload("res://scripts/assets.gd")
const DustCollision = preload("res://scripts/dust_collision.gd")
const WALK := 2.8
const RUN := 5.6
const CROUCH := 1.92
const STAND_H := 1.82
const DUCK_H := 0.94
const GRAVITY := 19.5

var avatar := Node3D.new()
var camera := Camera3D.new()
var capsule := CapsuleShape3D.new()
var camera_probe := SphereShape3D.new()
var camera_query := PhysicsShapeQueryParameters3D.new()
var collision := CollisionShape3D.new()
var agent_id := "sas"
var animation_player: AnimationPlayer
var crouched := false
var third_person := true
var pitch := -0.13
var arm_fraction := 0.0
var move_direction := Vector2.ZERO
var current_clip := ""
var frozen_pose := false
var stance := "pistol"
var fallback: MeshInstance3D

func _ready() -> void:
	collision_layer = DustCollision.PLAYER
	collision_mask = DustCollision.SOLIDS
	floor_snap_length = 0.35
	floor_constant_speed = true
	floor_max_angle = deg_to_rad(48.0)
	capsule.radius = 0.29
	capsule.height = STAND_H
	collision.shape = capsule
	collision.position.y = STAND_H * 0.5
	add_child(collision)
	add_child(avatar)
	camera_probe.radius = 0.16
	camera_query.shape = camera_probe
	camera_query.collision_mask = DustCollision.WORLD
	camera.near = 0.025
	camera.far = 260.0
	camera.fov = 78.0
	camera.current = true
	add_child(camera)
	set_agent(agent_id)

func set_agent(id: String) -> void:
	agent_id = id
	current_clip = ""
	frozen_pose = false
	animation_player = null
	fallback = null
	for child in avatar.get_children():
		avatar.remove_child(child)
		child.queue_free()
	var model: Node3D = Assets.instantiate_asset(id)
	if model != null:
		# The source roster looks along +Z; Godot's camera looks toward -Z.
		model.rotation.y = PI
		avatar.add_child(model)
		animation_player = find_animation_player(model)
	else:
		fallback = MeshInstance3D.new()
		var mesh := CapsuleMesh.new()
		mesh.radius = 0.29
		mesh.height = STAND_H
		var mat := StandardMaterial3D.new()
		mat.albedo_color = Color("313e52") if id == "sas" else Color("706345")
		mesh.material = mat
		fallback.mesh = mesh
		fallback.position.y = STAND_H * 0.5
		avatar.add_child(fallback)

static func find_animation_player(root: Node) -> AnimationPlayer:
	if root is AnimationPlayer:
		return root as AnimationPlayer
	for child in root.get_children():
		var found := find_animation_player(child)
		if found != null:
			return found
	return null

func aim(event: InputEventMouseMotion) -> void:
	rotate_y(-event.relative.x * 0.0025)
	pitch = clampf(pitch - event.relative.y * 0.0025, -1.24, 1.24)

func set_crouch(requested: bool) -> void:
	if requested == crouched:
		return
	if not requested:
		var test_shape := CapsuleShape3D.new()
		test_shape.radius = capsule.radius - 0.012
		test_shape.height = STAND_H - 0.035
		var query := PhysicsShapeQueryParameters3D.new()
		query.shape = test_shape
		query.transform.origin = global_position + Vector3.UP * (STAND_H * 0.5 + 0.04)
		query.collision_mask = DustCollision.SOLIDS
		if not get_world_3d().direct_space_state.intersect_shape(query, 1).is_empty():
			return
	crouched = requested
	capsule.height = DUCK_H if crouched else STAND_H
	collision.position.y = capsule.height * 0.5
	if fallback != null:
		fallback.scale.y = capsule.height / STAND_H
		fallback.position.y = collision.position.y

func _physics_process(delta: float) -> void:
	set_crouch(Input.is_action_pressed("crouch"))
	move_direction = Input.get_vector("left", "right", "forward", "back")
	var desired := transform.basis * Vector3(move_direction.x, 0, move_direction.y)
	var running := Input.is_action_pressed("run")
	var speed := CROUCH if crouched else RUN if running else WALK
	var horizontal := Vector2(velocity.x, velocity.z)
	var grounded := is_on_floor()
	var accel := (22.0 if move_direction.is_zero_approx() else 26.0) if grounded else 4.5
	horizontal = horizontal.move_toward(Vector2(desired.x, desired.z) * speed, accel * delta)
	velocity.x = horizontal.x
	velocity.z = horizontal.y
	if grounded and Input.is_action_just_pressed("jump") and not crouched:
		velocity.y = 5.0
	elif not grounded:
		velocity.y -= GRAVITY * delta
	move_and_slide()
	update_avatar(running)
	update_camera(delta)

func update_avatar(running: bool) -> void:
	avatar.visible = third_person
	if animation_player == null:
		return
	var moving := (
		move_direction.length_squared() > 0.01
		and Vector2(get_real_velocity().x, get_real_velocity().z).length() > 0.15
	)
	var gait := "crouch" if crouched else "run" if moving and running else "walk"
	var direction := "ne"
	if moving:
		direction = "n" if move_direction.y <= 0 else "s"
		direction += "e" if move_direction.x >= 0 else "w"
	var clip := "%s_%s_%s" % [gait, direction, stance]
	if not animation_player.has_animation(clip):
		return
	var freeze_next := not moving
	if clip != current_clip or frozen_pose != freeze_next:
		current_clip = clip
		frozen_pose = freeze_next
		var motion := animation_player.get_animation(clip)
		motion.loop_mode = Animation.LOOP_LINEAR
		animation_player.play(clip, 0.12 if moving else 0.0)
		if frozen_pose:
			# There is no authored weapon-ready idle in this bank. Use a stable
			# sample once, leaving the reference pose available for inspection.
			animation_player.seek(motion.length * 0.5, true)
			animation_player.pause()

func update_camera(delta: float) -> void:
	var eye := global_position + Vector3.UP * (0.79 if crouched else 1.62)
	camera.rotation.x = pitch
	if not third_person:
		arm_fraction = 0
		camera.global_position = eye
		return
	var arm := camera.global_basis.z * 3.05 + global_basis.x * 0.27
	var space := get_world_3d().direct_space_state
	camera_query.transform.origin = eye
	camera_query.motion = arm
	var cast := space.cast_motion(camera_query)
	var fraction := cast[0] if cast.size() == 2 else 1.0
	# A sweep skips a collider if it already intersects the probe at the eye.
	# The center ray keeps walls between the eye and the camera from being skipped.
	var ray := PhysicsRayQueryParameters3D.create(eye, eye + arm, DustCollision.WORLD)
	var hit := space.intersect_ray(ray)
	if not hit.is_empty():
		fraction = minf(fraction, (eye.distance_to(hit.position) - camera_probe.radius) / arm.length())
	fraction = clampf(fraction, 0.0, 1.0)
	# Ease out only. A shorter boom is applied immediately, always on this ray.
	arm_fraction = minf(fraction, lerpf(arm_fraction, fraction, 1.0 - exp(-17.0*delta)))
	camera.global_position = eye + arm * arm_fraction
