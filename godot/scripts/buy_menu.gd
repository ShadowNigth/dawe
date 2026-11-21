extends CanvasLayer

signal bought(id: String)
signal dismissed

const Arsenal = preload("res://scripts/arsenal.gd")
const Assets = preload("res://scripts/assets.gd")
const BASE_WEAPONS := ["ak-47", "m4a4", "awp", "usp-s", "glock", "deagle"]
var cards: Dictionary = {}
var pages: Dictionary = {}
var grids: Array[GridContainer] = []
var tabs := TabContainer.new()
var loadout_label: Label

func _ready() -> void:
	layer = 5
	var shade := ColorRect.new()
	shade.color = Color("111923f5")
	add_child(shade)
	shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var layout := VBoxContainer.new()
	shade.add_child(layout)
	layout.set_anchor(SIDE_LEFT, 0.06)
	layout.set_anchor(SIDE_RIGHT, 0.94)
	layout.set_anchor(SIDE_TOP, 0.04)
	layout.set_anchor(SIDE_BOTTOM, 0.96)
	layout.add_theme_constant_override("separation", 10)
	layout.add_child(make_label("DAWE / EQUIPAMIENTO", 16, Color("d9ac70")))
	layout.add_child(make_label("Menú de compra", 32, Color("f0f4f8")))
	layout.add_child(make_label("Compra de práctica · 1 primaria / 2 secundaria / 3 kukri", 15, Color("bac5d2")))
	tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	layout.add_child(tabs)
	make_page("Rifles", Arsenal.RIFLES)
	make_page("Subfusiles", Arsenal.SMGS)
	make_page("Pesadas", Arsenal.HEAVY)
	make_page("Secundarias", Arsenal.SECONDARY)
	loadout_label = make_label("", 16, Color("d7e4ed"))
	layout.add_child(loadout_label)
	var close := Button.new()
	close.text = "Volver al mapa   [ B / Esc ]"
	close.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	close.custom_minimum_size = Vector2(240, 38)
	close.pressed.connect(func(): dismissed.emit())
	layout.add_child(close)
	get_viewport().size_changed.connect(resize_grid)
	resize_grid()
	hide()

func resize_grid() -> void:
	var width := get_viewport().get_visible_rect().size.x
	for grid in grids:
		grid.columns = clampi(floori((width * 0.88 - 24.0) / 175.0), 2, 6)

func make_label(text: String, size: int, tint: Color) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", tint)
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return label

func make_page(heading: String, ids: Array) -> void:
	var page := ScrollContainer.new()
	page.name = heading
	page.follow_focus = true
	page.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	tabs.add_child(page)
	var grid := GridContainer.new()
	grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.add_theme_constant_override("h_separation", 8)
	grid.add_theme_constant_override("v_separation", 8)
	page.add_child(grid)
	grids.append(grid)
	for id: String in ids:
		var button := Button.new()
		button.custom_minimum_size = Vector2(148, 92)
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		button.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
		button.add_theme_constant_override("icon_max_width", 125)
		button.icon = Assets.load_texture("buy-" + id)
		button.vertical_icon_alignment = VERTICAL_ALIGNMENT_TOP
		button.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
		button.disabled = id not in BASE_WEAPONS and not Assets.has_asset(id)
		if button.disabled:
			button.tooltip_text = "Extraé el ZIP del arsenal para instalar esta arma."
		button.pressed.connect(func(): bought.emit(id))
		grid.add_child(button)
		cards[id] = button
		pages[id] = tabs.get_tab_count() - 1

func open(loadout: Array[String]) -> void:
	update_slots(loadout)
	show()
	var primary := loadout[0] if not loadout[0].is_empty() else Arsenal.PRIMARY[0]
	tabs.current_tab = pages[primary]
	cards[primary].grab_focus()

func update_slots(loadout: Array[String]) -> void:
	for id in cards:
		var selected := loadout.has(id)
		cards[id].text = Arsenal.label(id) + ("  ·  Equipada" if selected else "")
		cards[id].add_theme_color_override("font_color", Color("efc78d") if selected else Color("ecf0f4"))
	loadout_label.text = "1   %s     /     2   %s     /     3   Kukri" % [Arsenal.label(loadout[0]), Arsenal.label(loadout[1])]
