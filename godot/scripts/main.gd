extends Node3D

const Actor = preload("res://scripts/actor.gd")
const World = preload("res://scripts/world.gd")
const Viewmodel = preload("res://scripts/viewmodel.gd")
const Assets = preload("res://scripts/assets.gd")
const RadarMarker = preload("res://scripts/radar_marker.gd")

var actor := Actor.new()
var world := World.new()
var viewmodel := Viewmodel.new()
var status: Label
var hint: Label
var radar: TextureRect
var crosshair: Label
var spawn := Vector3.ZERO
var training_only := false
var mouse_ready_at := 0

func _ready() -> void:
	bindings()
	training_only = "--training" in OS.get_cmdline_user_args()
	add_child(world)
	world.build(training_only, "--collision-preview" in OS.get_cmdline_user_args())
	spawn = World.LONG_SPAWN if world.dust2 else Vector3(0, 0.12, 2)
	actor.position = spawn
	add_child(actor)
	viewmodel.layer = 1
	add_child(viewmodel)
	build_hud()
	if DisplayServer.get_name() != "headless" and not OS.has_feature("web"):
		capture_mouse()
	refresh_hud()

func capture_mouse() -> void:
	# Browser pointer lock can emit a large synthetic delta while it recenters.
	mouse_ready_at = Time.get_ticks_msec() + 120
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func bindings() -> void:
	var keys := {"forward": KEY_W, "back": KEY_S, "left": KEY_A, "right": KEY_D,
		"run": KEY_SHIFT, "crouch": KEY_CTRL, "jump": KEY_SPACE, "sas": KEY_1, "phoenix": KEY_2,
		"usp": KEY_3, "ak": KEY_4, "camera": KEY_V, "reload": KEY_R, "inspect": KEY_F,
		"silencer": KEY_T, "reset": KEY_BACKSPACE, "radar": KEY_TAB}
	for action: String in keys:
		if InputMap.has_action(action):
			continue
		InputMap.add_action(action)
		var key := InputEventKey.new()
		key.physical_keycode = keys[action]
		InputMap.action_add_event(action, key)

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
		return
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		if Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
			capture_mouse()
		else:
			viewmodel.play("shoot1")
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		if Time.get_ticks_msec() >= mouse_ready_at:
			actor.aim(event)
	if event.is_echo():
		return
	if event.is_action_pressed("sas"):
		actor.set_agent("sas")
	if event.is_action_pressed("phoenix"):
		actor.set_agent("phoenix")
	if event.is_action_pressed("usp"):
		actor.stance = "pistol"
		viewmodel.select("usp-s")
	if event.is_action_pressed("ak"):
		actor.stance = "rifle"
		viewmodel.select("ak-47")
	if event.is_action_pressed("camera"):
		actor.third_person = not actor.third_person
	if event.is_action_pressed("inspect"):
		viewmodel.play("lookat01")
	if event.is_action_pressed("reload"):
		viewmodel.play("reload")
	if event.is_action_pressed("silencer"):
		viewmodel.toggle_silencer()
	if event.is_action_pressed("reset"):
		reset()
	if event.is_action_pressed("radar") and radar.texture != null:
		radar.visible = not radar.visible
	refresh_hud()

func reset() -> void:
	actor.velocity = Vector3.ZERO
	actor.global_position = spawn
	actor.rotation.y = 0
	actor.pitch = -0.13

func _physics_process(_delta: float) -> void:
	if actor.position.y < -22.0:
		reset()

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
	var camera_mode := "3.ª persona" if actor.third_person else "1.ª persona"
	status.text = "DAWE  /  %s  ·  %s  ·  %s  ·  %s" % [area, actor.agent_id.to_upper(), viewmodel.weapon_id.to_upper(), camera_mode]
	hint.text = "WASD mover  ·  Shift correr  ·  Ctrl agachar  ·  Espacio saltar\n1/2 agente  ·  3/4 arma  ·  V cámara  ·  R recarga  ·  F inspección  ·  T silenciador  ·  Tab radar"
	if not actor.third_person and viewmodel.model == null:
		hint.text += "\nModelo de primera persona sin importar."
	viewmodel.visible = not actor.third_person
	crosshair.visible = not actor.third_person
