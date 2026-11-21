extends CanvasLayer

signal bought(id: String)
signal dismissed

const Arsenal = preload("res://scripts/arsenal.gd")
const Assets = preload("res://scripts/assets.gd")
var cards: Dictionary = {}
var loadout_label: Label

func _ready() -> void:
	layer = 5
	var shade := ColorRect.new()
	shade.color = Color("111923ef")
	add_child(shade)
	shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var center := CenterContainer.new()
	shade.add_child(center)
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var layout := VBoxContainer.new()
	layout.add_theme_constant_override("separation", 10)
	center.add_child(layout)
	layout.add_child(make_label("DAWE / EQUIPAMIENTO", 16, Color("d9ac70")))
	layout.add_child(make_label("Menú de compra", 36, Color("f0f4f8")))
	layout.add_child(make_label("Compra de práctica gratis · Elegí un arma por categoría", 16, Color("bac5d2")))
	make_row(layout, "01   PRIMARIA", Arsenal.PRIMARY)
	make_row(layout, "02   SECUNDARIA", Arsenal.SECONDARY)
	loadout_label = make_label("", 16, Color("d7e4ed"))
	layout.add_child(loadout_label)
	var close := Button.new()
	close.text = "Volver al mapa   [ B / Esc ]"
	close.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	close.custom_minimum_size = Vector2(240, 38)
	close.pressed.connect(func(): dismissed.emit())
	layout.add_child(close)
	hide()

func make_label(text: String, size: int, tint: Color) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", tint)
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return label

func make_row(parent: VBoxContainer, heading: String, ids: Array) -> void:
	parent.add_child(make_label(heading, 16, Color("d9ac70")))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	parent.add_child(row)
	for id: String in ids:
		var button := Button.new()
		button.custom_minimum_size = Vector2(206, 105)
		button.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
		button.add_theme_constant_override("icon_max_width", 124)
		button.icon = Assets.load_texture("buy-" + id)
		button.vertical_icon_alignment = VERTICAL_ALIGNMENT_TOP
		button.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
		button.pressed.connect(func(): bought.emit(id))
		row.add_child(button)
		cards[id] = button

func open(loadout: Array[String]) -> void:
	update_slots(loadout)
	show()
	cards[loadout[0] if not loadout[0].is_empty() else Arsenal.PRIMARY[0]].grab_focus()

func update_slots(loadout: Array[String]) -> void:
	for id in cards:
		var selected := loadout.has(id)
		cards[id].text = Arsenal.label(id) + ("  ·  Equipada" if selected else "")
		cards[id].add_theme_color_override("font_color", Color("efc78d") if selected else Color("ecf0f4"))
	loadout_label.text = "1   %s     /     2   %s     /     3   Bayoneta" % [Arsenal.label(loadout[0]), Arsenal.label(loadout[1])]
