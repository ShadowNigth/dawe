extends Node3D

const Actor = preload("res://scripts/actor.gd")
const World = preload("res://scripts/world.gd")
const Viewmodel = preload("res://scripts/viewmodel.gd")
const Assets = preload("res://scripts/assets.gd")
const RadarMarker = preload("res://scripts/radar_marker.gd")
const TeamMenu = preload("res://scripts/team_menu.gd")
const DroppedWeapon = preload("res://scripts/dropped_weapon.gd")
const Soundscape = preload("res://scripts/soundscape.gd")
const DustCollision = preload("res://scripts/dust_collision.gd")
const WEAPON_SLOTS := ["ak-47", "usp-s", "bayonet", "m4a4"]

var actor := Actor.new()
var world := World.new()
var viewmodel := Viewmodel.new()
var team_menu := TeamMenu.new()
var soundscape := Soundscape.new()
var dropped: Dictionary = {}
var feedback := ""
var team_chosen := false
var status: Label
var hint: Label
var radar: TextureRect
var crosshair: Label
var spawn := Vector3.ZERO
var training_only := false
var mouse_ready_at := 0

func _ready() -> void:
	bindings()
	var args := OS.get_cmdline_user_args()
	training_only = "--training" in args
	add_child(world)
	world.build(training_only, "--collision-preview" in args, "--visual-preview" in args or "--require-preview" in args)
	spawn = World.LONG_SPAWN if world.dust2 else Vector3(0, 0.12, 2)
	actor.position = spawn
	add_child(actor)
	viewmodel.layer = 1
	add_child(viewmodel)
	add_child(soundscape)
	viewmodel.silencer_changed.connect(refresh_hud)
	viewmodel.clip_started.connect(on_clip_started)
	actor.stepped.connect(on_footstep)
	actor.took_off.connect(func(): soundscape.cue("jump", -15.0))
	actor.touched_down.connect(func(): soundscape.cue("land", -13.0))
	build_hud()
	add_child(team_menu)
	team_menu.chose.connect(choose_team)
	if DisplayServer.get_name() != "headless":
		open_team_menu()
	refresh_hud()

func capture_mouse() -> void:
	# Browser pointer lock can emit a large synthetic delta while it recenters.
	mouse_ready_at = Time.get_ticks_msec() + 120
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func bindings() -> void:
	var keys := {"forward": KEY_W, "back": KEY_S, "left": KEY_A, "right": KEY_D,
		"walk": KEY_SHIFT, "crouch": KEY_CTRL, "jump": KEY_SPACE, "team": KEY_M,
		"ak": KEY_1, "usp": KEY_2, "knife": KEY_3, "m4a4": KEY_4, "camera": KEY_V, "reload": KEY_R, "inspect": KEY_F,
		"drop": KEY_G, "pickup": KEY_E,
		"silencer": KEY_T, "reset": KEY_BACKSPACE, "radar": KEY_TAB}
	for action: String in keys:
		if InputMap.has_action(action):
			continue
		InputMap.add_action(action)
		var key := InputEventKey.new()
		key.physical_keycode = keys[action]
		InputMap.action_add_event(action, key)
	var right_click := InputEventMouseButton.new()
	right_click.button_index = MOUSE_BUTTON_RIGHT
	if not InputMap.action_has_event("silencer", right_click):
		InputMap.action_add_event("silencer", right_click)

func equip_weapon(id: String) -> void:
	if id == viewmodel.weapon_id or dropped.has(id):
		return
	actor.stance = "pistol" if id == "usp-s" else "rifle" if id in ["ak-47", "m4a4"] else "knife"
	actor.equipped_weapon = id
	viewmodel.select(id)

func cycle_weapon(step: int) -> void:
	var idx := WEAPON_SLOTS.find(viewmodel.weapon_id)
	if idx < 0:
		idx = -1 if step > 0 else WEAPON_SLOTS.size()
	for i in range(1, WEAPON_SLOTS.size() + 1):
		var id: String = WEAPON_SLOTS[posmod(idx + i * step, WEAPON_SLOTS.size())]
		if not dropped.has(id):
			equip_weapon(id)
			return

func open_team_menu() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	actor.set_physics_process(false)
	actor.reset_motion()
	radar.hide()
	team_menu.open()
	refresh_hud()

func choose_team(id: String) -> void:
	if id not in ["sas", "phoenix"]:
		return
	if actor.agent_id != id:
		actor.set_agent(id)
	team_chosen = true
	actor.set_physics_process(true)
	team_menu.hide()
	if DisplayServer.get_name() != "headless":
		capture_mouse()
	soundscape.begin_ambient()
	soundscape.cue("ui-confirm", -15.0)
	feedback = ""
	refresh_hud()

func weapon_name(id: String) -> String:
	return "Bayoneta" if id == "bayonet" else id.to_upper()

func drop_weapon() -> void:
	var id := viewmodel.weapon_id
	if not WEAPON_SLOTS.has(id) or dropped.has(id):
		return
	var item := DroppedWeapon.new()
	item.configure(id, viewmodel.usp_attached)
	add_child(item)
	var start := actor.global_position + Vector3.UP * (0.61 if actor.crouched else 0.98)
	var forward := -actor.global_basis.z
	var target := start + forward * 0.64
	var trace := PhysicsRayQueryParameters3D.create(start, target, DustCollision.WORLD)
	var hit := get_world_3d().direct_space_state.intersect_ray(trace)
	if not hit.is_empty():
		target = start + forward * maxf(0.0, start.distance_to(hit.position) - 0.35)
	item.global_position = target
	item.rotation.y = actor.rotation.y
	item.linear_velocity = actor.velocity * 0.28 + forward * 1.65 + Vector3.UP * 1.05
	item.angular_velocity = actor.global_basis.x * 2.8
	dropped[id] = item
	cycle_weapon(1)
	if viewmodel.weapon_id == id:
		equip_weapon("")
	soundscape.cue("gear-3", -12.0)
	feedback = weapon_name(id) + " en el suelo · E recoge"

func pickup_weapon() -> void:
	var nearest: RigidBody3D = null
	var reach := 2.0
	var from := actor.global_position + Vector3.UP * 0.67
	for item in dropped.values():
		var distance: float = item.global_position.distance_to(from)
		if item.age < 0.22 or distance > reach:
			continue
		var trace := PhysicsRayQueryParameters3D.create(from, item.global_position + Vector3.UP * 0.025, DustCollision.WORLD)
		if not get_world_3d().direct_space_state.intersect_ray(trace).is_empty():
			continue
		nearest = item
		reach = distance
	if nearest == null:
		feedback = "No hay un arma a tu alcance."
		return
	var id: String = nearest.weapon_id
	if id == "usp-s":
		viewmodel.usp_attached = nearest.silenced
	dropped.erase(id)
	nearest.queue_free()
	equip_weapon(id)
	soundscape.cue("gear-1", -12.0)
	feedback = weapon_name(id) + " recuperada"

func on_clip_started(id: String, clip: String) -> void:
	soundscape.start_clip(id, clip, viewmodel.usp_attached)

func on_footstep() -> void:
	var feet := actor.global_position
	# The local demo approximates the sandy pit by location; no material ray map.
	soundscape.step(world.dust2 and feet.x > 30.0 and feet.y < -2.0 and feet.z > -22.0)

func _unhandled_input(event: InputEvent) -> void:
	if team_menu.visible:
		if team_chosen and (event.is_action_pressed("team") or event.is_action_pressed("ui_cancel")) and not event.is_echo():
			choose_team(actor.agent_id)
		return
	if event.is_action_pressed("team") and not event.is_echo():
		open_team_menu()
		return
	if event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
		return
	if event is InputEventMouseButton and event.pressed:
		match event.button_index:
			MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN:
				cycle_weapon(1 if event.button_index == MOUSE_BUTTON_WHEEL_UP else -1)
				refresh_hud()
				get_viewport().set_input_as_handled()
				return
			MOUSE_BUTTON_LEFT:
				if Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
					capture_mouse()
				else:
					viewmodel.primary_action()
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		if Time.get_ticks_msec() >= mouse_ready_at:
			actor.aim(event)
	if event.is_echo():
		return
	if event.is_action_pressed("drop"):
		drop_weapon()
	if event.is_action_pressed("pickup"):
		pickup_weapon()
	if event.is_action_pressed("usp"):
		equip_weapon("usp-s")
	if event.is_action_pressed("ak"):
		equip_weapon("ak-47")
	if event.is_action_pressed("knife"):
		equip_weapon("bayonet")
	if event.is_action_pressed("m4a4"):
		equip_weapon("m4a4")
	if event.is_action_pressed("camera"):
		actor.third_person = not actor.third_person
	if event.is_action_pressed("inspect"):
		viewmodel.inspect()
	if event.is_action_pressed("reload"):
		viewmodel.play("reload")
	if event.is_action_pressed("silencer"):
		if viewmodel.weapon_id == "bayonet" and event is InputEventMouseButton:
			viewmodel.play("heavy_miss1")
		elif viewmodel.toggle_silencer():
			actor.third_person = false
	if event.is_action_pressed("reset"):
		reset()
	if event.is_action_pressed("radar") and radar.texture != null:
		radar.visible = not radar.visible
	refresh_hud()

func reset() -> void:
	actor.reset_motion()
	actor.global_position = spawn
	actor.rotation.y = 0
	actor.pitch = -0.13

func _physics_process(_delta: float) -> void:
	if actor.position.y < -22.0:
		reset()
	for item in dropped.values():
		if item.position.y < -22.0:
			item.position = spawn + Vector3.UP * 0.5
			item.linear_velocity = Vector3.ZERO
			item.angular_velocity = Vector3.ZERO

func _process(_delta: float) -> void:
	var player := viewmodel.animation_player
	if player != null and player.is_playing() and player.current_animation_length > 0.0:
		soundscape.follow_clip(viewmodel.weapon_id, viewmodel.active_clip,
			player.current_animation_position / player.current_animation_length)

func build_hud() -> void:
	var hud := CanvasLayer.new()
	hud.layer = 2
	add_child(hud)
	var panel := PanelContainer.new()
	panel.position = Vector2(16, 16)
	var frame := StyleBoxFlat.new()
	frame.bg_color = Color("17202cd9")
	frame.border_color = Color("d6af70")
	frame.border_width_left = 3
	frame.content_margin_left = 14
	frame.content_margin_right = 14
	frame.content_margin_top = 8
	frame.content_margin_bottom = 8
	panel.add_theme_stylebox_override("panel", frame)
	hud.add_child(panel)
	var labels := VBoxContainer.new()
	panel.add_child(labels)
	status = Label.new()
	status.add_theme_color_override("font_color", Color("fae2b5"))
	status.add_theme_font_size_override("font_size", 21)
	labels.add_child(status)
	hint = Label.new()
	hint.add_theme_font_size_override("font_size", 14)
	labels.add_child(hint)
	crosshair = Label.new()
	crosshair.text = "+"
	crosshair.add_theme_color_override("font_color", Color("e9dec5"))
	crosshair.add_theme_font_size_override("font_size", 24)
	crosshair.mouse_filter = Control.MOUSE_FILTER_IGNORE
	hud.add_child(crosshair)
	crosshair.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	crosshair.offset_left = -7
	crosshair.offset_top = -18
	radar = TextureRect.new()
	radar.position = Vector2(16, 116)
	radar.size = Vector2(360, 360)
	radar.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	radar.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	radar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var radar_path := Assets.DIR + "dust2-radar.png"
	if world.dust2:
		if ResourceLoader.exists(radar_path, "Texture2D"):
			radar.texture = load(radar_path) as Texture2D
		elif FileAccess.file_exists(radar_path):
			var image := Image.load_from_file(radar_path)
			if image != null and not image.is_empty():
				radar.texture = ImageTexture.create_from_image(image)
	radar.hide()
	hud.add_child(radar)
	if radar.texture != null:
		var marker := RadarMarker.new()
		marker.actor = actor
		marker.overview = Assets.read_json("dust2-overview")
		marker.mouse_filter = Control.MOUSE_FILTER_IGNORE
		radar.add_child(marker)
		marker.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)

func refresh_hud() -> void:
	if status == null:
		return
	var area := "DUST II" if world.dust2 else "PISTA LOCAL · Dust II sin importar"
	if world.collision_view:
		area = "DUST II · Malla física"
	elif world.textured_sector:
		area = "DUST II · Puertas Largas"
	var camera_mode := "3.ª persona" if actor.third_person else "1.ª persona"
	var weapon_label := "MANOS VACÍAS" if viewmodel.weapon_id.is_empty() else weapon_name(viewmodel.weapon_id).to_upper()
	status.text = "DAWE  /  %s  ·  %s  ·  %s  ·  %s" % [area, actor.agent_id.to_upper(), weapon_label, camera_mode]
	hint.text = "WASD mover  ·  Shift caminar  ·  Ctrl agachar  ·  Espacio saltar\n1/2/3/4 o rueda: arma  ·  M equipo  ·  G tirar  ·  E recoger\nV cámara  ·  F inspección  ·  Tab radar"
	if viewmodel.weapon_id == "bayonet":
		hint.text += "\nBayoneta · Clic izquierdo tajo · Clic derecho estocada"
	elif viewmodel.silencer != null:
		hint.text += "\nR recarga · " + viewmodel.silencer_hint()
	elif not viewmodel.weapon_id.is_empty():
		hint.text += "\nR recarga"
	if not feedback.is_empty():
		hint.text += "\n" + feedback
	if not actor.third_person and viewmodel.model == null and not viewmodel.weapon_id.is_empty():
		hint.text += "\nModelo de primera persona sin importar."
	viewmodel.visible = not actor.third_person and not team_menu.visible
	crosshair.visible = not actor.third_person and not team_menu.visible
	status.get_parent().visible = not team_menu.visible
