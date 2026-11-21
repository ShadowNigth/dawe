extends CanvasLayer

signal chose(agent: String)

var overlay: ColorRect
var ct_button: Button

func _ready() -> void:
	layer = 5
	overlay = ColorRect.new()
	overlay.color = Color("101923e8")
	overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(overlay)
	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	overlay.add_child(center)
	var layout := VBoxContainer.new()
	layout.add_theme_constant_override("separation", 18)
	center.add_child(layout)
	layout.add_child(label("DAWE  /  DUST II", 15, Color("e8bc77")))
	layout.add_child(label("Elegí tu equipo", 38, Color("f2f3ef")))
	var cards := HBoxContainer.new()
	cards.add_theme_constant_override("separation", 16)
	layout.add_child(cards)
	ct_button = team_card(cards, "ct", "SAS", "Antiterroristas", "sas", Color("8bc4f5"))
	team_card(cards, "t", "Phoenix", "Terroristas", "phoenix", Color("efb36a"))
	layout.add_child(label("Podés volver a abrir este menú con M", 15, Color("b1bdc8")))
	hide()

func open() -> void:
	show()
	ct_button.grab_focus()

func label(text: String, size: int, tint: Color) -> Label:
	var out := Label.new()
	out.text = text
	out.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	out.add_theme_font_size_override("font_size", size)
	out.add_theme_color_override("font_color", tint)
	out.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return out

func card_style(fill: Color, edge: Color, width: int) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = fill
	style.border_color = edge
	style.set_border_width_all(width)
	style.set_corner_radius_all(12)
	return style

func team_card(row: HBoxContainer, id: String, name_text: String, side: String, agent: String, tint: Color) -> Button:
	var button := Button.new()
	button.custom_minimum_size = Vector2(263, 225)
	button.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	button.tooltip_text = "Elegir " + side
	button.add_theme_stylebox_override("normal", card_style(Color("1e2b38"), tint.darkened(0.48), 1))
	button.add_theme_stylebox_override("hover", card_style(Color("2c3c4b"), tint, 2))
	button.add_theme_stylebox_override("pressed", card_style(Color("394d5e"), tint, 2))
	button.add_theme_stylebox_override("focus", card_style(Color.TRANSPARENT, tint, 2))
	row.add_child(button)
	var column := VBoxContainer.new()
	column.alignment = BoxContainer.ALIGNMENT_CENTER
	column.add_theme_constant_override("separation", 7)
	column.mouse_filter = Control.MOUSE_FILTER_IGNORE
	column.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	button.add_child(column)
	var logo := TextureRect.new()
	logo.texture = load_logo(id)
	if logo.texture != null:
		logo.mouse_filter = Control.MOUSE_FILTER_IGNORE
		logo.custom_minimum_size = Vector2(90, 90)
		logo.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		logo.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		column.add_child(logo)
	column.add_child(label(id.to_upper() + "  /  " + name_text, 24, tint))
	column.add_child(label(side, 16, Color("d5dde6")))
	button.pressed.connect(func(): chose.emit(agent))
	return button

static func load_logo(id: String) -> Texture2D:
	var path := "res://generated/team-" + id + ".png"
	if ResourceLoader.exists(path, "Texture2D"):
		return load(path) as Texture2D
	if FileAccess.file_exists(path):
		var image := Image.load_from_file(path)
		if image != null and not image.is_empty():
			return ImageTexture.create_from_image(image)
	return null
