extends CharacterBody3D

signal stepped
signal took_off
signal touched_down

const Assets = preload("res://scripts/assets.gd")
const AgentJump = preload("res://scripts/agent_jump.gd")
const DustCollision = preload("res://scripts/dust_collision.gd")
const Movement = preload("res://scripts/source_movement.gd")
const STAND_H := 72.0 * Movement.METERS
const DUCK_H := 54.0 * Movement.METERS
const MAX_STEP := 0.34
const STEP_SKIN := 0.015
const STAND_EYE := 64.0 * Movement.METERS
const DUCK_EYE := 46.0 * Movement.METERS

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
var equipped_weapon := "usp-s"
var scoped := false
var fallback: MeshInstance3D
var eye_height := STAND_EYE
var step_camera_offset := 0.0
var step_hit := KinematicCollision3D.new()
var landing_time := 0.0
var step_distance := 0.0

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
		if animation_player != null:
			AgentJump.install(model, animation_player)
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

func reset_motion() -> void:
	velocity = Vector3.ZERO
	eye_height = DUCK_EYE if crouched else STAND_EYE
	step_camera_offset = 0.0
	landing_time = 0.0
	step_distance = 0.0

func _physics_process(delta: float) -> void:
	set_crouch(Input.is_action_pressed("crouch"))
	move_direction = Input.get_vector("left", "right", "forward", "back")
	var desired := transform.basis * Vector3(move_direction.x, 0, move_direction.y)
	var wish := Vector2(desired.x, desired.z).normalized()
	var walking := Input.is_action_pressed("walk")
	var max_run := 100.0 * Movement.METERS if scoped else Movement.max_speed(equipped_weapon)
	var modifier := Movement.DUCK_MODIFIER if crouched else Movement.WALK_MODIFIER if walking else 1.0
	var horizontal := Vector2(velocity.x, velocity.z)
	var grounded := is_on_floor()
	# Default CS2 behavior: a new press while grounded, no automatic hops or
	# forgiving takeoffs after stepping off an edge.
	var jumping := grounded and Input.is_action_just_pressed("jump")
	if jumping:
		horizontal = horizontal.limit_length(max_run * Movement.JUMP_LIMIT)
		velocity.y = Movement.JUMP_SPEED
		step_distance = 0.0
		took_off.emit()
	horizontal = Movement.accelerate(horizontal, wish, move_direction.length(), max_run,
		modifier, delta, grounded and not jumping)
	velocity.x = horizontal.x
	velocity.z = horizontal.y
	var airborne := jumping or not grounded
	if airborne:
		velocity.y -= Movement.GRAVITY * delta * 0.5
	elif not wish.is_zero_approx():
		try_step_up(Vector3(horizontal.x, 0.0, horizontal.y) * delta)
	var before_slide_y := velocity.y
	move_and_slide()
	if airborne and not is_on_floor() and not is_on_ceiling():
		velocity.y -= Movement.GRAVITY * delta * 0.5
	landing_time = maxf(0.0, landing_time - delta)
	if not is_on_floor():
		landing_time = 0.0
	elif not grounded and before_slide_y < -2.1:
		landing_time = 0.23
		touched_down.emit()
	if walking or crouched:
		step_distance = 0.0
	elif grounded and is_on_floor() and not jumping and not wish.is_zero_approx():
		var travel := get_position_delta()
		step_distance += Vector2(travel.x, travel.z).length()
		var stride := 1.45
		if step_distance >= stride:
			step_distance = fmod(step_distance, stride)
			stepped.emit()
	update_avatar(not walking)
	update_camera(delta)

# Up, across, then down with the actual player capsule. Only lift when the
# horizontal motion meets a riser and the landing is walkable; no changes to
# the map triangles or invisible player bounds are necessary.
func try_step_up(motion: Vector3) -> void:
	if motion.length_squared() < 0.000025:
		return
	var start := global_transform
	var walkable := cos(floor_max_angle)
	if not test_move(start, motion, step_hit) or step_hit.get_normal().dot(Vector3.UP) >= walkable:
		return
	var obstacle := step_hit.get_collider() as CollisionObject3D
	if obstacle == null or not (obstacle.collision_layer & DustCollision.WORLD):
		return
	var lift := Vector3.UP * (MAX_STEP + STEP_SKIN)
	if test_move(start, lift, step_hit):
		# A low ceiling may still leave room for this particular riser.
		lift.y = step_hit.get_travel().y - STEP_SKIN
		if lift.y < 0.05:
			return
	var lifted := start.translated(lift)
	# Look past the rounded front of the capsule for a tread. A downward
	# sweep exactly above the first contact would hit the vertical riser again.
	var probe := motion + motion.normalized() * (capsule.radius + STEP_SKIN)
	if test_move(lifted, probe):
		return
	var down := -lift - Vector3.UP * STEP_SKIN
	if not test_move(lifted.translated(probe), down, step_hit):
		return
	var support := step_hit.get_collider() as CollisionObject3D
	if step_hit.get_normal().dot(Vector3.UP) < walkable or support == null or not (support.collision_layer & DustCollision.WORLD):
		return
	var rise := lift.y + step_hit.get_travel().y
	if rise < 0.025 or rise > MAX_STEP:
		return
	# Keep ordinary horizontal motion and floor snapping in move_and_slide().
	# Confirm that the smaller lift won't catch on the original riser again.
	var raise := Vector3.UP * (rise + STEP_SKIN)
	if raise.y > lift.y or test_move(start.translated(raise), motion):
		return
	global_position.y += raise.y
	step_camera_offset = maxf(-MAX_STEP, step_camera_offset - raise.y)

func update_avatar(running: bool) -> void:
	avatar.visible = third_person
	if animation_player == null:
		return
	var phase := ""
	if not is_on_floor():
		phase = "rise" if velocity.y > 0.0 else "fall"
	elif landing_time > 0.0:
		phase = "land"
	if not phase.is_empty():
		var air_clip := "jump/%s_%s" % [phase, stance]
		if animation_player.has_animation(air_clip):
			if current_clip != air_clip:
				current_clip = air_clip
				frozen_pose = false
				animation_player.play(air_clip, 0.055)
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
	eye_height = lerpf(eye_height, DUCK_EYE if crouched else STAND_EYE, 1.0 - exp(-15.0 * delta))
	step_camera_offset = move_toward(step_camera_offset, 0.0, delta * 3.5)
	var eye := global_position + Vector3.UP * (eye_height + step_camera_offset)
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
