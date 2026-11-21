extends SceneTree

const Arsenal = preload("res://scripts/arsenal.gd")
const Assets = preload("res://scripts/assets.gd")
const Movement = preload("res://scripts/source_movement.gd")

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
		bayonet_actions(sw)
		await jump_animation(sw)
		await presentation(sw)
		if "--require-arsenal" in OS.get_cmdline_user_args():
			await expanded_arsenal(sw)
	else:
		check(not sw.world.dust2, "training fixture")
		await locomotion(sw)
		await chase_camera(sw)
		movement_math()
		await movement_response(sw)
		await steps_and_ledge(sw)
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
			check(player.has_animation("jump/rise_pistol"), "%s has jump animations" % id)
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
	sw.loadout[0] = "ak-47"
	for id in ["usp-s", "ak-47", "m4a4", "glock", "deagle", "awp"]:
		sw.viewmodel.select(id, false)
		var player: AnimationPlayer = sw.viewmodel.animation_player
		check(player != null, "%s skinned viewmodel" % id)
		if player == null:
			continue
		check(has_texture(sw.viewmodel.model), "%s has textures on its first-person model" % id)
		check(pose_changes(sw.viewmodel.model, player, "reload"), "%s reload moves the rig" % id)
		if sw.soundscape.source_audio.is_empty():
			check(recoil_keeps_grip(sw.viewmodel.model, player, id == "awp"), "%s wrists follow recoil without twisting off the grip" % id)
		else:
			var arms := "CyberpunkArms" if FileAccess.file_exists("res://generated/cyberpunk-arms.vis") else "ArchiGloves"
			check(sw.viewmodel.model.find_child(arms, true, false) is MeshInstance3D, "%s loads the arm mesh" % id)
			check(pose_changes(sw.viewmodel.model, player, "shoot1"), "%s uses animated source recoil" % id)
			for clip: String in sw.soundscape.source_audio.source_sequences[id]:
				check(player.has_animation(clip), "%s imports Source sequence %s" % [id, clip])
			if id == "deagle":
				sw.viewmodel.play("idle", true)
				check(sw.viewmodel.inspect() and sw.viewmodel.active_clip == "lookat01", "Deagle first Archi inspection")
				player.advance(10.0)
				check(sw.viewmodel.inspect() and sw.viewmodel.active_clip == "lookat02", "Deagle second Archi inspection")
		for clip in ["idle", "draw", "shoot1", "reload", "lookat01"]:
			check(player.has_animation(clip), "%s %s" % [id, clip])
		if id == "usp-s":
			silencer_actions(sw)
	await ticks(2)

func silencer_actions(sw: Node) -> void:
	var vm = sw.viewmodel
	vm.select("usp-s", false)
	check(vm.silencer != null and vm.silencer.visible, "USP-S starts with the separate silencer attached")
	if vm.silencer == null:
		return
	sw.actor.third_person = true
	var right_click := InputEventMouseButton.new()
	right_click.button_index = MOUSE_BUTTON_RIGHT
	right_click.pressed = true
	sw._unhandled_input(right_click)
	check(vm.active_clip == "silencer_detach" and not sw.actor.third_person, "right-click starts detach in first person")
	vm.animation_player.advance(0.10)
	var position: float = vm.animation_player.current_animation_position
	sw._unhandled_input(right_click)
	check(vm.active_clip == "silencer_detach" and is_equal_approx(vm.animation_player.current_animation_position, position), "another press cannot interrupt the clip")
	var detach_time: float = vm.events.silencer_detach[1][0]
	vm.animation_player.advance(detach_time - 0.05 - position)
	vm.update_silencer(vm.animation_player.current_animation_position)
	check(vm.silencer.visible, "detach keeps the part visible until the authored key")
	vm.animation_player.advance(0.10)
	vm.update_silencer(vm.animation_player.current_animation_position)
	check(not vm.silencer.visible, "detach hides the part after the authored key")
	vm.animation_player.advance(2.0)
	check(vm.active_clip == "idle" and not vm.silencer.visible, "detach returns to idle, still off")
	var key := InputEventKey.new()
	key.physical_keycode = KEY_V
	key.pressed = true
	sw._unhandled_input(key)
	sw._unhandled_input(key)
	check(not sw.actor.third_person and not vm.silencer.visible, "changing camera preserves the detached state")
	var wheel := InputEventMouseButton.new()
	wheel.pressed = true
	wheel.button_index = MOUSE_BUTTON_WHEEL_DOWN
	sw._unhandled_input(wheel)
	check(vm.weapon_id == "ak-47" and sw.actor.stance == "rifle" and vm.active_clip == "draw", "scroll down equips the AK-47 and plays draw")
	wheel.pressed = false
	sw._unhandled_input(wheel)
	check(vm.weapon_id == "ak-47", "wheel release does not switch slots")
	vm.animation_player.advance(5.0)
	sw._unhandled_input(right_click)
	check(vm.active_clip == "idle", "right-click does not start a silencer action on the AK-47")
	wheel.pressed = true
	wheel.button_index = MOUSE_BUTTON_WHEEL_UP
	sw._unhandled_input(wheel)
	check(vm.weapon_id == "usp-s" and sw.actor.stance == "pistol" and vm.active_clip == "draw", "scroll up equips the USP-S and plays draw")
	check(not vm.silencer.visible and not vm.attached, "USP-S remembers the detached state after scrolling")
	vm.animation_player.advance(5.0)
	right_click.pressed = false
	sw._unhandled_input(right_click)
	check(vm.active_clip == "idle", "mouse release does not trigger the action")
	right_click.pressed = true
	sw._unhandled_input(right_click)
	check(vm.active_clip == "silencer_attach", "right-click plays attach when detached")
	var attach_time: float = vm.events.silencer_attach[1][0]
	vm.animation_player.advance(attach_time - 0.05)
	vm.update_silencer(vm.animation_player.current_animation_position)
	check(not vm.silencer.visible, "attach keeps the part hidden before the authored key")
	vm.animation_player.advance(0.10)
	vm.update_silencer(vm.animation_player.current_animation_position)
	check(vm.silencer.visible, "attach shows the part after the authored key")
	vm.animation_player.advance(5.0)
	check(vm.active_clip == "idle" and vm.silencer.visible, "attach returns to idle, still on")

func bayonet_actions(sw: Node) -> void:
	var vm = sw.viewmodel
	vm.select("usp-s", false)
	var wheel := InputEventMouseButton.new()
	wheel.button_index = MOUSE_BUTTON_WHEEL_UP
	wheel.pressed = true
	sw._unhandled_input(wheel)
	check(vm.weapon_id == "bayonet" and sw.actor.stance == "knife", "wheel equips the bayonet and selects knife locomotion")
	if vm.animation_player == null:
		check(false, "bayonet scene loaded")
		return
	for clip in ["draw", "idle1", "idle2", "light_miss1", "light_miss2", "heavy_miss1", "lookat01", "lookat01_draw"]:
		check(vm.animation_player.has_animation(clip), "bayonet " + clip)
	check(has_texture(vm.model), "knife has textured materials")
	if not sw.soundscape.source_audio.is_empty():
		var arms := "CyberpunkArms" if FileAccess.file_exists("res://generated/cyberpunk-arms.vis") else "ArchiGloves"
		check(vm.model.find_child(arms, true, false) is MeshInstance3D, "kukri loads the arm mesh")
		for clip: String in sw.soundscape.source_audio.source_sequences.bayonet:
			check(vm.animation_player.has_animation(clip), "kukri imports Source sequence " + clip)
	check(vm.inspect() and vm.active_clip == "lookat01_draw", "inspect during draw plays its authored variant")
	vm.animation_player.advance(8.0)
	check(vm.active_clip == "idle1", "draw inspection returns to idle")
	vm.animation_player.advance(vm.animation_player.current_animation_length + 0.01)
	check(vm.active_clip == "idle2", "both idle variants play in sequence")
	check(vm.primary_action() and vm.active_clip == "light_miss1", "bayonet first light clip")
	check(not vm.primary_action(), "light clip cannot be restarted during its action")
	vm.animation_player.advance(2.0)
	check(vm.primary_action() and vm.active_clip == "light_miss2", "bayonet second light clip alternates")
	vm.animation_player.advance(2.0)
	var stab := InputEventMouseButton.new()
	stab.button_index = MOUSE_BUTTON_RIGHT
	stab.pressed = true
	sw._unhandled_input(stab)
	check(vm.active_clip == "heavy_miss1", "right click plays the bayonet's heavy clip")
	vm.animation_player.advance(2.0)
	check(vm.inspect() and vm.active_clip == "lookat01", "normal bayonet inspection")
	sw._unhandled_input(wheel)
	check(vm.weapon_id == "ak-47", "weapon wheel wraps from knife to owned primary")


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
	var initial: Array[Transform3D] = []
	for i in rig.get_bone_count():
		initial.append(rig.get_bone_pose(i))
	for phase in [0.08, 0.22, 0.47]:
		player.seek(player.get_animation(clip).length * phase, true)
		for i in rig.get_bone_count():
			var current := rig.get_bone_pose(i)
			if current.origin.distance_to(initial[i].origin) > 0.002:
				return true
			if absf(initial[i].basis.get_rotation_quaternion().dot(current.basis.get_rotation_quaternion())) < 0.999:
				return true
	return false

func recoil_keeps_grip(model: Node, player: AnimationPlayer, bolt_cycle := false) -> bool:
	var rig := first_skeleton(model)
	if rig == null or not player.has_animation("shoot1"):
		return false
	var gun := rig.find_bone("weapon_offset")
	var limbs: Array[int] = []
	for bone in ["LeftForeArm", "LeftHand", "RightForeArm", "RightHand"]:
		limbs.append(rig.find_bone(bone))
	if gun < 0 or limbs.has(-1):
		return false
	player.play("shoot1", 0.0)
	player.seek(0.0, true)
	var start := rig.get_bone_global_pose(gun)
	var grips: Array[Transform3D] = []
	for limb in limbs:
		grips.append(start.affine_inverse() * rig.get_bone_global_pose(limb))
	var moved := false
	for step in range(1, 13):
		player.seek((0.19 if bolt_cycle else player.get_animation("shoot1").length) * step / 13.0, true)
		var gun_pose := rig.get_bone_global_pose(gun)
		moved = moved or not start.is_equal_approx(gun_pose)
		for i in limbs.size():
			var grip := gun_pose.affine_inverse() * rig.get_bone_global_pose(limbs[i])
			if grip.origin.distance_to(grips[i].origin) > 0.002:
				return false
			if absf(grip.basis.get_rotation_quaternion().dot(grips[i].basis.get_rotation_quaternion())) < 0.9995:
				return false
	if bolt_cycle:
		var moved_to_bolt := false
		for step in range(4, 11):
			player.seek(player.get_animation("shoot1").length * step / 13.0, true)
			var wrist := rig.get_bone_global_pose(gun).affine_inverse() * rig.get_bone_global_pose(limbs[3])
			moved_to_bolt = moved_to_bolt or wrist.origin.distance_to(grips[3].origin) > 0.02
		return moved and moved_to_bolt
	return moved

func locomotion(sw: Node) -> void:
	Input.action_press("forward")
	await ticks(162)
	var top: Vector3 = sw.actor.global_position
	check(top.z < -10.8 and top.y > 1.35 and sw.actor.is_on_floor(), "cross doors and climb 1.5 m ramp")
	await ticks(120)
	check(sw.actor.global_position.z > -14.6 and sw.actor.global_position.z < -13.9, "wall blocks movement")
	Input.action_release("forward")
	Input.action_press("back")
	await ticks(143)
	check(sw.actor.global_position.y < 0.20 and sw.actor.is_on_floor(), "descend and snap to floor")
	Input.action_release("back")
	Input.action_press("crouch")
	await ticks(18)
	check(sw.actor.crouched and is_equal_approx(sw.actor.capsule.height, 54.0 * Movement.METERS), "crouch collider")
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
	sw.world.block(Vector3(0, 1.58, 2), Vector3(2, 0.30, 2), Color.WHITE)
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

func movement_math() -> void:
	var dt := 1.0 / 60.0
	var max_run := Movement.max_speed("ak-47")
	check(is_equal_approx(max_run, 5.461) and Movement.max_speed("m4a4") > max_run
		and Movement.max_speed("bayonet") > Movement.max_speed("usp-s"), "CS2 speed depends on weapon")
	var initial := Vector2(0.0, -max_run)
	var glide := Movement.accelerate(initial, Vector2.ZERO, 0.0, max_run, 1.0, dt, true)
	var counter := Movement.accelerate(initial, Vector2.DOWN, 1.0, max_run, 1.0, dt, true)
	check(counter.length() < glide.length(), "counter-strafe brakes faster than releasing the key")
	var airborne := initial
	for i in 30:
		airborne = Movement.accelerate(airborne, Vector2.RIGHT, 1.0, max_run, 1.0, dt, false)
	check(is_equal_approx(airborne.x, 0.762) and is_equal_approx(airborne.y, initial.y), "air strafe only caps projected speed")

func movement_response(sw: Node) -> void:
	var player = sw.actor
	sw.world.block(Vector3(60, -0.3, 0), Vector3(16, 0.6, 24), Color.WHITE)
	player.global_position = Vector3(60, 0.1, 4)
	player.rotation.y = 0.0
	player.reset_motion()
	await ticks(20)
	Input.action_press("crouch")
	await ticks(2)
	check(player.crouched and player.eye_height < 1.62 and player.eye_height > 46.0 * Movement.METERS, "camera eases into crouching while the capsule shrinks")
	await ticks(20)
	check(absf(player.eye_height - 46.0 * Movement.METERS) < 0.006, "camera reaches crouch eye height")
	Input.action_release("crouch")
	await ticks(14)
	Input.action_press("forward")
	await ticks(18)
	var launch_speed: float = absf(player.velocity.z)
	check(launch_speed > 5.0, "WASD runs without holding Shift")
	Input.action_press("walk")
	await ticks(20)
	check(absf(absf(player.velocity.z) - Movement.max_speed(player.equipped_weapon) * 0.52) < 0.15, "Shift limits speed to walk pace")
	Input.action_release("walk")
	await ticks(18)
	launch_speed = absf(player.velocity.z)
	Input.action_press("jump")
	await ticks(2)
	Input.action_release("jump")
	Input.action_release("forward")
	await ticks(6)
	check(not player.is_on_floor() and absf(absf(player.velocity.z) - launch_speed) < 0.15, "airborne release keeps takeoff momentum")
	Input.action_press("right")
	await ticks(8)
	check(player.velocity.x > 0.65 and absf(player.velocity.z) > 4.5, "air strafe steers while preserving forward momentum")
	Input.action_release("right")
	for frame in 60:
		if player.is_on_floor():
			break
		await ticks(1)
	await ticks(34)
	check(player.velocity.length() < 0.15, "ground friction stops the player after landing")

	# Default profile does not queue a jump held before touching ground.
	Input.action_press("jump")
	await ticks(2)
	Input.action_release("jump")
	for frame in 48:
		if player.velocity.y < 0.0 and player.global_position.y < 0.40:
			break
		await ticks(1)
	Input.action_press("jump")
	await ticks(14)
	check(player.is_on_floor(), "holding jump through landing does not auto-hop")
	Input.action_release("jump")

	# Run off an isolated raised edge and then jump after the floor flag clears.
	sw.world.block(Vector3(90, 0.7, 0), Vector3(4, 0.6, 3), Color.WHITE)
	player.global_position = Vector3(90, 1.08, 0)
	player.reset_motion()
	await ticks(20)
	Input.action_press("forward")
	for frame in 60:
		await ticks(1)
		if not player.is_on_floor():
			break
	check(not player.is_on_floor(), "walked off the edge of the raised platform")
	Input.action_press("jump")
	await ticks(2)
	Input.action_release("jump")
	Input.action_release("forward")
	check(player.velocity.y < 1.0, "jump requires ground contact")

func steps_and_ledge(sw: Node) -> void:
	var player = sw.actor
	var sand := Color("bda17e")
	sw.world.block(Vector3(120, -0.25, 0), Vector3(10, 0.5, 22), sand)
	for i in 5:
		var h := 0.2 * (i + 1)
		sw.world.block(Vector3(120, h * 0.5, -i * 0.64), Vector3(3.0, h, 0.64), sand)
	sw.world.block(Vector3(120, 0.50, -4.0), Vector3(3.0, 1.0, 2.4), sand)
	sw.world.block(Vector3(120, 1.9, -5.1), Vector3(3.0, 1.8, 0.20), sand)
	player.global_position = Vector3(120, 0.1, 1.8)
	player.rotation.y = 0.0
	player.reset_motion()
	await ticks(20)
	Input.action_press("forward")
	await ticks(170)
	Input.action_release("forward")
	check(player.is_on_floor() and player.global_position.y > 0.96 and player.global_position.z < -3.1, "walks up five risers without jumping")
	check(player.global_position.z > -4.95, "step assist does not climb the tall wall")
	Input.action_press("back")
	Input.action_press("walk")
	await ticks(140)
	Input.action_release("back")
	Input.action_release("walk")
	check(player.is_on_floor() and player.global_position.y < 0.08 and player.global_position.z > 0.45, "walks down the steps without getting stuck")

	# This obstacle is higher than the old 0.68 m jump, but below the new apex.
	sw.world.block(Vector3(124, 0.47, -1.2), Vector3(1.4, 0.94, 1.4), sand)
	player.global_position = Vector3(124, 0.08, 0.075)
	player.reset_motion()
	await ticks(20)
	Input.action_press("jump")
	Input.action_press("forward")
	await ticks(46)
	Input.action_release("jump")
	Input.action_release("forward")
	check(player.is_on_floor() and absf(player.global_position.y - 0.94) < 0.05, "longer jump reaches a 94 cm ledge")

func jump_animation(sw: Node) -> void:
	var player = sw.actor
	player.set_agent("sas")
	player.stance = "knife"
	var animator: AnimationPlayer = player.animation_player
	if animator == null:
		check(false, "SAS jump rig")
		return
	for phase in ["rise", "fall", "land"]:
		for stance in ["pistol", "rifle", "knife"]:
			check(animator.has_animation("jump/%s_%s" % [phase, stance]), "jump animation %s %s" % [phase, stance])
	check(pose_changes(player.avatar, animator, "jump/rise_knife"), "jump bends the legs on the agent skeleton")
	Input.action_press("jump")
	await ticks(3)
	Input.action_release("jump")
	check(player.current_clip == "jump/rise_knife", "jump pose follows actual takeoff")
	await ticks(24)
	check(player.current_clip == "jump/fall_knife", "jump uses a distinct descending pose")
	for i in 40:
		if player.is_on_floor():
			break
		await ticks(1)
	check(player.current_clip == "jump/land_knife", "landing uses the contact pose")
	await ticks(20)
	check(not player.current_clip.begins_with("jump/"), "landing returns to ground locomotion")

func key_press(sw: Node, code: Key) -> void:
	var key := InputEventKey.new()
	key.physical_keycode = code
	key.pressed = true
	sw._unhandled_input(key)

func presentation(sw: Node) -> void:
	var vm = sw.viewmodel
	key_press(sw, KEY_M)
	check(sw.team_menu.visible and not sw.actor.is_physics_processing(), "M opens and pauses the team selector")
	check(sw.team_menu.load_logo("ct") != null and sw.team_menu.load_logo("t") != null, "both team logos load")
	var previous: String = vm.weapon_id
	key_press(sw, KEY_2)
	check(vm.weapon_id == previous, "team modal blocks weapon hotkeys")
	sw.team_menu.chose.emit("phoenix")
	check(sw.actor.agent_id == "phoenix" and not sw.team_menu.visible and sw.actor.is_physics_processing(), "T selection loads Phoenix and resumes movement")
	key_press(sw, KEY_M)
	sw.team_menu.chose.emit("sas")
	check(sw.actor.agent_id == "sas", "CT selection loads SAS")
	check(sw.soundscape.ambience.stream != null, "wind ambience loads")
	for cue in ["ak47-1", "usp1", "usp-unsuppressed-01", "usp-unsuppressed-02", "usp-unsuppressed-03",
		"awp1", "awp_boltforward", "glock18-1", "deagle-1", "m4a1-1", "knife-stab", "step-sand-4"]:
		var stream: AudioStream = sw.soundscape.get_sound(cue)
		check(stream != null and stream.get_length() > 0.03, "sound loads: " + cue)
	check(sw.loadout == ["ak-47", "glock", "bayonet"], "first T selection provides two weapons and knife")
	key_press(sw, KEY_B)
	check(sw.buy_menu.visible and not sw.actor.is_physics_processing(), "B opens and pauses the buy menu")
	var before: String = vm.weapon_id
	key_press(sw, KEY_3)
	check(vm.weapon_id == before, "buy modal blocks weapon hotkeys")
	for id in ["awp", "m4a4", "ak-47", "usp-s", "glock", "deagle"]:
		check(sw.buy_menu.cards[id].icon != null, "shop icon " + id)
	var from_archi: bool = not sw.soundscape.source_audio.is_empty()
	var shot_assets := {"m4a4": "m4a1_unsil-1" if from_archi else "m4a1-1", "glock": "glock18-1", "deagle": "deagle-1", "awp": "awp1", "usp-s": "usp1"}
	for id in shot_assets:
		sw.buy_menu.bought.emit(id)
		check(vm.weapon_id == id and sw.loadout.size() == 3 and sw.loadout[2] == "bayonet", "buy replaces same slot with " + id)
		vm.animation_player.advance(2.0)
		vm.primary_action()
		check(sw.soundscape.pending[0][1] == shot_assets[id], "shot uses correct sample: " + id)
		if id == "awp":
			check(sw.soundscape.pending[1][1] == "awp_boltback" and sw.soundscape.pending[2][1] == "awp_boltforward", "AWP shot retains timed bolt audio")
	key_press(sw, KEY_B)
	check(not sw.buy_menu.visible and sw.actor.is_physics_processing(), "B closes shop and resumes control")
	key_press(sw, KEY_1)
	check(vm.weapon_id == "awp", "1 equips the purchased primary")
	vm.animation_player.advance(2.0)
	var right_click := InputEventMouseButton.new()
	right_click.button_index = MOUSE_BUTTON_RIGHT
	right_click.pressed = true
	sw._unhandled_input(right_click)
	check(sw.zoom == 1 and sw.actor.scoped and sw.scope.visible, "AWP right-click engages scope")
	sw._unhandled_input(right_click)
	check(sw.zoom == 2, "AWP offers second zoom level")
	key_press(sw, KEY_3)
	check(vm.weapon_id == "bayonet" and sw.zoom == 0, "3 equips fixed knife and resets scope")
	key_press(sw, KEY_G)
	check(vm.weapon_id == "bayonet" and not sw.dropped.has("bayonet"), "G keeps the fixed knife")
	key_press(sw, KEY_2)
	check(vm.weapon_id == "usp-s", "2 equips the purchased secondary")
	vm.animation_player.advance(2.0)
	vm.primary_action()
	check(sw.soundscape.pending[0][1] == ("usp2" if from_archi else "usp1"), "attached USP-S uses the native silenced shot")
	vm.animation_player.advance(2.0)
	vm.toggle_silencer()
	vm.animation_player.advance(6.0)
	vm.primary_action()
	check(sw.soundscape.pending[0][1] == ("usp_unsil-1" if from_archi else "usp-unsuppressed-01"), "detached USP-S uses an original open shot")
	vm.animation_player.advance(2.0)
	vm.primary_action()
	check(sw.soundscape.pending[0][1] == ("usp_unsil-1" if from_archi else "usp-unsuppressed-02"), "detached USP-S uses the selected pack's open shot")
	var sand := Color("bda17e")
	sw.world.block(Vector3(120, -0.3, 120), Vector3(12, 0.6, 12), sand)
	sw.actor.global_position = Vector3(120, 0.05, 120)
	sw.actor.rotation.y = 0.0
	sw.actor.reset_motion()
	await ticks(12)
	var steps_before: int = sw.soundscape.step_index
	Input.action_press("walk")
	Input.action_press("forward")
	await ticks(32)
	check(sw.soundscape.step_index == steps_before, "Shift walking does not trigger footsteps")
	Input.action_release("walk")
	await ticks(27)
	Input.action_release("forward")
	check(sw.soundscape.step_index != steps_before, "actual running distance triggers a footstep")
	key_press(sw, KEY_G)
	check(sw.dropped.has("usp-s") and vm.weapon_id != "usp-s", "G leaves the selected gun on the ground and equips another slot")
	key_press(sw, KEY_2)
	check(vm.weapon_id != "usp-s", "a dropped slot cannot be equipped")
	if not sw.dropped.has("usp-s"):
		return
	var item: RigidBody3D = sw.dropped["usp-s"]
	check(item.find_child("ArmsAndWeapon", true, false) != null, "dropped gun has a static textured mesh without arms")
	var start: Vector3 = item.global_position
	await ticks(36)
	check(item.global_position.distance_to(start) > 0.4 and item.global_position.y > -0.35, "dropped gun moves physically without falling through floor")
	key_press(sw, KEY_B)
	sw.buy_menu.bought.emit("deagle")
	key_press(sw, KEY_B)
	check(sw.loadout[1] == "deagle" and sw.dropped.has("usp-s"), "buying a different sidearm does not remove the dropped USP")
	sw.actor.global_position = Vector3(item.global_position.x, 0.05, item.global_position.z + 0.46)
	await ticks(4)
	key_press(sw, KEY_E)
	check(not sw.dropped.has("usp-s") and vm.weapon_id == "usp-s" and not vm.attached, "E recovers the nearby gun and its silencer state")
	check(sw.dropped.has("deagle") and sw.loadout[1] == "usp-s", "pickup exchanges the occupied category without adding a slot")
	key_press(sw, KEY_G)
	key_press(sw, KEY_1)
	key_press(sw, KEY_G)
	check(vm.weapon_id == "bayonet" and sw.loadout == ["", "", "bayonet"] and sw.dropped.size() == 3,
		"dropping both guns leaves only the knife")

func expanded_arsenal(sw: Node) -> void:
	var vm = sw.viewmodel
	var ids := Arsenal.PRIMARY + Arsenal.SECONDARY
	check(ids.size() == 35 and sw.loadout.size() == 3, "full catalogue with two weapon slots plus knife")
	for id: String in ids:
		check(sw.buy_menu.cards.has(id) and not sw.buy_menu.cards[id].disabled and sw.buy_menu.cards[id].icon != null,
			"purchasable with icon: " + id)
		sw.open_buy_menu()
		sw.buy_menu.cards[id].pressed.emit()
		check(sw.buy_menu.visible and sw.loadout[Arsenal.slot(id)] == id and vm.weapon_id == id, "purchased and equipped: " + id)
		sw.close_buy_menu()
		var player: AnimationPlayer = vm.animation_player
		check(player != null and vm.model.find_child("CyberpunkArms", true, false) is MeshInstance3D, id + " shared Cyberpunk rig")
		if player == null:
			continue
		for clip in ["idle", "draw", "shoot1", "lookat01"]:
			check(player.has_animation(clip), "%s ships %s" % [id, clip])
		if id != "zeus":
			check(player.has_animation("reload"), id + " ships reload")
		player.advance(12.0)
		check(vm.primary_action(), id + " fires after draw")
		var sample: String = sw.soundscape.pending[0][1] if not sw.soundscape.pending.is_empty() else ""
		check(not sample.is_empty() and sw.soundscape.get_sound(sample) != null, id + " uses its own shot sound")
		if id == "m4a1-s":
			player.advance(12.0)
			check(vm.toggle_silencer(), "M4A1-S can remove silencer")
			player.advance(12.0)
			check(not vm.attached and vm.silencer != null and not vm.silencer.visible, "rifle silencer is a separate part")
		Assets.preview_cache.erase(id)
		await process_frame
