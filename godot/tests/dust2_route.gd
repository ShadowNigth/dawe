extends SceneTree

# Surveyed against the cs2go navigation polygons. We drive the same character
# controller as the player; waypoints don't teleport or override the physics.
const Assets = preload("res://scripts/assets.gd")
const RadarMarker = preload("res://scripts/radar_marker.gd")

const DOORS := [
	Vector2(15.67, -5.45), Vector2(15.40, -6.62), Vector2(16.55, -7.80),
	Vector2(17.13, -8.57), Vector2(17.05, -10.00), Vector2(15.55, -12.23),
	Vector2(15.52, -14.46), Vector2(14.92, -15.20), Vector2(14.96, -17.66),
	Vector2(15.37, -18.22), Vector2(16.01, -18.70), Vector2(17.10, -19.57),
	Vector2(17.21, -20.59), Vector2(17.74, -22.47), Vector2(18.40, -24.05),
]
const TO_PIT := [
	Vector2(20.70, -24.95), Vector2(22.92, -25.80), Vector2(25.76, -25.89),
	Vector2(27.31, -26.70), Vector2(30.95, -27.31), Vector2(32.28, -24.12),
	Vector2(32.50, -21.40), Vector2(33.92, -21.53), Vector2(35.14, -19.65),
	Vector2(36.64, -18.69), Vector2(38.24, -18.35), Vector2(38.21, -14.63),
	Vector2(38.66, -12.80), Vector2(38.63, -8.61), Vector2(38.63, -6.32),
]

# Long A, finishing on the grade below the site rather than jumping onto boxes.
const A_RAMP := [
	Vector2(33.17, -23.32), Vector2(33.73, -26.82), Vector2(33.67, -30.82),
	Vector2(33.01, -32.71), Vector2(33.25, -34.30), Vector2(34.06, -35.93),
	Vector2(33.17, -37.55), Vector2(34.06, -40.64), Vector2(33.25, -42.27),
	Vector2(33.07, -45.45), Vector2(34.14, -47.14), Vector2(34.07, -49.70),
	Vector2(34.90, -51.90), Vector2(33.83, -54.74), Vector2(34.06, -57.08),
	Vector2(36.40, -57.76), Vector2(34.42, -58.90), Vector2(34.73, -60.87),
	Vector2(34.60, -62.50), Vector2(33.77, -64.29),
]

var game: Node3D
var actor: CharacterBody3D

func _initialize() -> void:
	call_deferred("run")

func ticks(n: int) -> void:
	for i in n:
		await physics_frame

func feet() -> Vector2:
	var p := actor.global_position
	return Vector2(p.x, p.z)

func visit(waypoints: Array) -> bool:
	for goal: Vector2 in waypoints:
		var deadline := 180 + ceili(feet().distance_to(goal) * 35.0)
		for frame in deadline:
			var offset := goal - feet()
			if offset.length() < 0.16:
				break
			actor.rotation.y = atan2(-offset.x, -offset.y)
			Input.action_press("forward", clampf(offset.length() * 1.75, 0.35, 1.0))
			await physics_frame
		Input.action_release("forward")
		await ticks(9)
		if feet().distance_to(goal) > 0.29:
			printerr("FAIL waypoint ", goal, " feet ", actor.global_position)
			return false
	return true

func finish(ok: bool) -> void:
	game.queue_free()
	await process_frame
	quit(0 if ok else 1)

func run() -> void:
	game = preload("res://main.tscn").instantiate()
	root.add_child(game)
	actor = game.actor
	await ticks(25)
	if not game.world.dust2 or not actor.is_on_floor():
		printerr("FAIL missing Dust II collision or spawn floor. Use -- --collision-preview with the baked cache.")
		await finish(false)
		return
	var overview := Assets.read_json("dust2-overview")
	if overview.is_empty() or RadarMarker.project(Vector3(28.245, 3.658, -62.992), overview).distance_to(Vector2(0.80, 0.17)) > 0.015:
		printerr("FAIL Dust II native radar projection")
		await finish(false)
		return
	print("OK radar projection")
	print("OK Outside Long ", actor.global_position, " parts=", game.world.collision_count)
	if not await visit(DOORS):
		await finish(false)
		return
	print("OK both doorways ", actor.global_position)
	if not await visit(TO_PIT):
		await finish(false)
		return
	var low := actor.global_position.y
	if low > -4.0 or not actor.is_on_floor():
		printerr("FAIL didn't reach the pit floor ", actor.global_position)
		await finish(false)
		return
	print("OK pit floor ", actor.global_position)
	var up := TO_PIT.slice(7, TO_PIT.size() - 1)
	up.reverse()
	if not await visit(up):
		await finish(false)
		return
	var ok := actor.global_position.y - low > 3.75 and actor.is_on_floor()
	print("OK pit return " if ok else "FAIL pit return ", actor.global_position)
	if not ok or not await visit(A_RAMP):
		await finish(false)
		return
	ok = actor.global_position.y > 1.35 and actor.is_on_floor()
	print("OK A ramp " if ok else "FAIL A ramp ", actor.global_position)
	await finish(ok)
