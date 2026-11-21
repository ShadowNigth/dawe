extends SceneTree

var failures: PackedStringArray = []

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, what: String) -> void:
	if not condition:
		failures.append(what)
		printerr("FAIL: ", what)
	else:
		print("OK: ", what)

func ticks(n: int) -> void:
	for frame in n:
		await physics_frame

func run() -> void:
	var sw := preload("res://main.tscn").instantiate()
	root.add_child(sw)
	await ticks(42)
	check(sw.actor.is_on_floor(), "spawn settle on floor")
	var require_preview := "--require-preview" in OS.get_cmdline_user_args()
	var imported := require_preview or "--require-assets" in OS.get_cmdline_user_args()
	if imported:
		check(sw.world.dust2 and sw.world.collision_count >= 30, "Dust II visual and separate collision")
		check(sw.radar.texture != null, "Dust II radar")
		check(sw.actor.global_position.y > -1.0 and sw.actor.global_position.y < 1.0, "spawn resolves near Outside Long")
		if require_preview:
			check(sw.world.textured_sector and has_texture(sw.world), "textured Long sector on the real map")
		agents(sw)
		await weapons(sw)
	else:
		check(not sw.world.dust2, "training fixture")
		await locomotion(sw)
		await chase_camera(sw)
	print("Dawe: ", failures.size(), " failures")
	sw.queue_free()
	await process_frame
	quit(1 if not failures.is_empty() else 0)

func agents(sw: Node) -> void:
	for id in ["sas", "phoenix"]:
		sw.actor.set_agent(id)
		var player: AnimationPlayer = sw.actor.animation_player
		check(player != null, "%s skinned scene" % id)
		if player != null:
			check(player.has_animation("idle"), "%s idle" % id)
			var clips := 0
			for gait in ["walk", "run", "crouch"]:
				for direction in ["ne", "nw", "se", "sw"]:
					for hold in ["knife", "pistol", "rifle"]:
						if player.has_animation("%s_%s_%s" % [gait, direction, hold]):
							clips += 1
			check(clips == 36, "%s all 36 locomotion clips" % id)
			check(has_texture(sw.actor.avatar), "%s has an albedo texture on the visible mesh" % id)
			check(pose_changes(sw.actor.avatar, player, "run_ne_pistol"), "%s locomotion moves the rig" % id)

func weapons(sw: Node) -> void:
	for id in ["usp-s", "ak-47"]:
		sw.viewmodel.select(id, false)
		var player: AnimationPlayer = sw.viewmodel.animation_player
		check(player != null, "%s skinned viewmodel" % id)
		if player == null:
			continue
		check(has_texture(sw.viewmodel.model), "%s has textures on its first-person model" % id)
		check(pose_changes(sw.viewmodel.model, player, "reload"), "%s reload moves the rig" % id)
		for clip in ["idle", "draw", "shoot1", "reload", "lookat01"]:
			check(player.has_animation(clip), "%s %s" % [id, clip])
		if id == "usp-s":
			check(sw.viewmodel.silencer != null, "USP-S separate silencer mesh")
			if sw.viewmodel.silencer != null:
				sw.viewmodel.play("silencer_detach", true)
				sw.viewmodel.update_silencer(4.1)
				check(sw.viewmodel.active_clip == "silencer_detach" and not sw.viewmodel.silencer.visible, "detach event")
				sw.viewmodel.play("silencer_attach", true)
				sw.viewmodel.update_silencer(0.5)
				check(sw.viewmodel.active_clip == "silencer_attach" and sw.viewmodel.silencer.visible, "attach event")
	await ticks(2)

func has_texture(node: Node) -> bool:
	if node is MeshInstance3D and node.mesh != null:
		for surface in node.mesh.get_surface_count():
			var mat := node.get_active_material(surface) as StandardMaterial3D
			if mat != null and mat.albedo_texture != null:
				return true
	for child in node.get_children():
		if has_texture(child):
			return true
	return false

func first_skeleton(node: Node) -> Skeleton3D:
	if node is Skeleton3D:
		return node
	for child in node.get_children():
		var rig := first_skeleton(child)
		if rig != null:
			return rig
	return null

func pose_changes(model: Node, player: AnimationPlayer, clip: String) -> bool:
	var rig := first_skeleton(model)
	if rig == null or not player.has_animation(clip):
		return false
	player.play(clip, 0.0)
	player.seek(0.0, true)
	var initial: Array[Quaternion] = []
	for i in rig.get_bone_count():
		initial.append(rig.get_bone_pose_rotation(i))
	player.seek(player.get_animation(clip).length * 0.47, true)
	for i in rig.get_bone_count():
		if absf(initial[i].dot(rig.get_bone_pose_rotation(i))) < 0.999:
			return true
	return false

func locomotion(sw: Node) -> void:
	Input.action_press("forward")
	Input.action_press("run")
	await ticks(162)
	var top: Vector3 = sw.actor.global_position
	check(top.z < -10.8 and top.y > 1.35 and sw.actor.is_on_floor(), "cross doors and climb 1.5 m ramp")
	await ticks(120)
	check(sw.actor.global_position.z > -14.6 and sw.actor.global_position.z < -13.9, "wall blocks movement")
	Input.action_release("forward")
	Input.action_press("back")
	await ticks(150)
	check(sw.actor.global_position.y < 0.20 and sw.actor.is_on_floor(), "descend and snap to floor")
	Input.action_release("run")
	Input.action_release("back")
	Input.action_press("crouch")
	await ticks(18)
	check(sw.actor.crouched and sw.actor.capsule.height < 1.0, "crouch collider")
	Input.action_release("crouch")
	await ticks(6)
	check(not sw.actor.crouched and sw.actor.capsule.height > 1.7, "recover standing collider")
	sw.reset()
	await ticks(20)
	Input.action_press("jump")
	await ticks(11)
	check(sw.actor.global_position.y > 0.35 and not sw.actor.is_on_floor(), "jump leaves floor")
	Input.action_release("jump")
	await ticks(42)
	check(sw.actor.is_on_floor(), "lands after jump")
	Input.action_press("crouch")
	await ticks(2)
	sw.world.block(Vector3(0, 1.35, 2), Vector3(2, 0.30, 2), Color.WHITE)
	await ticks(2)
	Input.action_release("crouch")
	await ticks(3)
	check(sw.actor.crouched, "ceiling blocks standing up")
	Input.action_press("back")
	await ticks(75)
	Input.action_release("back")
	check(not sw.actor.crouched, "stands after leaving the ceiling")

func chase_camera(sw: Node) -> void:
	# The boom's center misses the thin edge; its sphere must still retract.
	sw.world.block(Vector3(0.47, 2.10, 3.25), Vector3(0.42, 3.6, 0.30), Color.WHITE)
	sw.reset()
	await ticks(28)
	var eye: Vector3 = sw.actor.global_position + Vector3.UP * 1.62
	var arm: Vector3 = sw.actor.camera.global_position - eye
	check(arm.length() > 0.75 and arm.length() < 1.65, "camera retracts at the edge, not just on a ray")
	sw.actor.third_person = false
	await ticks(2)
	check(sw.actor.camera.global_position.distance_to(eye) < 0.08, "first person camera stays at eye height")
