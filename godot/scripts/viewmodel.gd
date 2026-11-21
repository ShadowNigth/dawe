extends CanvasLayer

signal silencer_changed

const Assets = preload("res://scripts/assets.gd")
const Actor = preload("res://scripts/actor.gd")

var weapon_id := "usp-s"
var next_light := "light_miss1"
var model: Node3D
var animation_player: AnimationPlayer
var silencer: Node3D
var attached := true
var usp_attached := true
var events: Dictionary
var active_clip := ""
var viewport_3d := SubViewport.new()
var picture := TextureRect.new()

func _ready() -> void:
	viewport_3d.own_world_3d = true
	viewport_3d.transparent_bg = true
	viewport_3d.render_target_update_mode = SubViewport.UPDATE_WHEN_VISIBLE
	add_child(viewport_3d)
	var camera := Camera3D.new()
	camera.near = 0.025
	camera.fov = 67
	camera.current = true
	viewport_3d.add_child(camera)
	var world := WorldEnvironment.new()
	var env := Environment.new()
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color("e7ecf2")
	env.ambient_light_energy = 0.50
	var sky_fill := ProceduralSkyMaterial.new()
	sky_fill.sky_top_color = Color("8092a2")
	sky_fill.sky_horizon_color = Color("a2a1a0")
	sky_fill.ground_horizon_color = Color("55514e")
	sky_fill.ground_bottom_color = Color("3c3936")
	var reflections := Sky.new()
	reflections.sky_material = sky_fill
	env.sky = reflections
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	world.environment = env
	viewport_3d.add_child(world)
	var lamp := DirectionalLight3D.new()
	lamp.rotation_degrees = Vector3(-44, -31, 0)
	lamp.light_energy = 0.78
	viewport_3d.add_child(lamp)
	picture.texture = viewport_3d.get_texture()
	picture.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	picture.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(picture)
	picture.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	get_viewport().size_changed.connect(resize)
	resize()
	select(weapon_id, false)

func resize() -> void:
	viewport_3d.size = Vector2i(get_viewport().get_visible_rect().size).max(Vector2i(2, 2))

func select(id: String, draw := true) -> void:
	weapon_id = id
	next_light = "light_miss1"
	if model != null:
		viewport_3d.remove_child(model)
		model.queue_free()
	model = Assets.instantiate_asset(id)
	silencer = null
	animation_player = null
	active_clip = ""
	attached = usp_attached if id == "usp-s" else true
	events = Assets.read_json(id)
	if model != null:
		viewport_3d.add_child(model)
		silencer = model.find_child("Silencer", true, false) as Node3D
		animation_player = Actor.find_animation_player(model)
		if animation_player != null:
			animation_player.animation_finished.connect(on_finished)
			play("draw" if draw else idle_clip(), true)

func idle_clip() -> String:
	return "idle1" if weapon_id == "bayonet" else "idle"

func is_idle(clip: String) -> bool:
	return clip in ["idle", "idle1", "idle2"]

func primary_action() -> bool:
	if weapon_id != "bayonet":
		return play("shoot1")
	if not play(next_light):
		return false
	next_light = "light_miss2" if next_light == "light_miss1" else "light_miss1"
	return true

func inspect() -> bool:
	if weapon_id == "bayonet" and active_clip == "draw":
		return play("lookat01_draw", true)
	return play("lookat01")

func play(clip: String, force := false) -> bool:
	if animation_player == null or not animation_player.has_animation(clip):
		return false
	if not force and not (active_clip.is_empty() or is_idle(active_clip)) and animation_player.is_playing():
		return false
	active_clip = clip
	# Godot glTF import may infer looping from a clip name; actions always finish.
	animation_player.get_animation(clip).loop_mode = Animation.LOOP_LINEAR if clip == "idle" else Animation.LOOP_NONE
	animation_player.play(clip, 0.05)
	animation_player.advance(0.0)
	update_silencer(0.0)
	if clip.begins_with("silencer_"):
		silencer_changed.emit()
	return true

func toggle_silencer() -> bool:
	return silencer != null and play("silencer_detach" if attached else "silencer_attach")

func silencer_hint() -> String:
	match active_clip:
		"silencer_attach":
			return "Colocando silenciador…"
		"silencer_detach":
			return "Quitando silenciador…"
	return "Silenciador puesto · Clic derecho quitar" if attached else "Silenciador quitado · Clic derecho colocar"

func on_finished(clip: StringName) -> void:
	if active_clip != String(clip):
		return
	update_silencer(INF)
	if weapon_id == "bayonet" and clip == &"idle1":
		play("idle2", true)
	elif clip != &"idle":
		play(idle_clip(), true)
	if String(clip).begins_with("silencer_"):
		silencer_changed.emit()

func update_silencer(time: float) -> void:
	if silencer == null:
		return
	for event in events.get(active_clip, []):
		if time >= float(event[0]):
			attached = bool(event[1])
	usp_attached = attached
	silencer.visible = attached

func _process(_delta: float) -> void:
	if animation_player != null and animation_player.is_playing():
		update_silencer(animation_player.current_animation_position)
