extends Control

const METRES_PER_UNIT := 0.0254
const OVERVIEW_PIXELS := 1024.0

var actor: Node3D
var overview: Dictionary

static func project(point: Vector3, data: Dictionary) -> Vector2:
	var units_per_pixel := float(data["scale"])
	var source := Vector2(point.x, point.z) / METRES_PER_UNIT
	return (source + Vector2(-float(data["pos_x"]), float(data["pos_y"]))) / (units_per_pixel * OVERVIEW_PIXELS)

func _process(_delta: float) -> void:
	if is_visible_in_tree():
		queue_redraw()

func _draw() -> void:
	if actor == null or not overview.has_all(["scale", "pos_x", "pos_y"]) or float(overview["scale"]) <= 0.0:
		return
	var location := project(actor.global_position, overview)
	if not Rect2(0, 0, 1, 1).has_point(location):
		return
	var edge := minf(size.x, size.y)
	var center := (size - Vector2.ONE * edge) * 0.5 + location * edge
	var facing := -actor.global_basis.z
	var arrow := Vector2(facing.x, facing.z).normalized()
	draw_line(center, center + arrow * 15.0, Color("10202d"), 5.0, true)
	draw_line(center, center + arrow * 15.0, Color("8debdc"), 2.0, true)
	draw_circle(center, 6.0, Color("10202d"), true, -1.0, true)
	draw_circle(center, 4.0, Color("8debdc"), true, -1.0, true)
