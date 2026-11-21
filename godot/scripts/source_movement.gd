class_name DaweSourceMovement
extends RefCounted

# CS2/Source reference tuning, in meters. The Godot capsule and step solver
# remain map-specific rather than emulating Source's axis-aligned hull.
const METERS := 0.0254
const GROUND_ACCEL := 5.5
const GROUND_FRICTION := 5.2
const STOP_SPEED := 80.0 * METERS
const AIR_ACCEL := 12.0
const AIR_WISH_CAP := 30.0 * METERS
const GRAVITY := 800.0 * METERS
const JUMP_SPEED := 301.99338 * METERS
const JUMP_LIMIT := 1.1
const WALK_MODIFIER := 0.52
const DUCK_MODIFIER := 0.34
const TOP_SPEED := {"ak-47": 215.0, "m4a4": 225.0, "m4a1-s": 225.0, "usp-s": 240.0, "bayonet": 250.0,
	"glock": 240.0, "deagle": 230.0, "awp": 200.0, "p2000": 240.0, "p250": 240.0, "dual-berettas": 240.0,
	"five-seven": 240.0, "tec-9": 240.0, "cz75": 240.0, "r8": 220.0, "zeus": 220.0, "aug": 220.0,
	"famas": 220.0, "g3sg1": 215.0, "galil": 215.0, "scar-20": 215.0, "sg-553": 210.0, "ssg-08": 230.0,
	"bizon": 240.0, "mac-10": 240.0, "mp5-sd": 235.0, "mp7": 220.0, "mp9": 240.0, "p90": 230.0,
	"ump-45": 230.0, "m249": 195.0, "negev": 150.0, "mag-7": 225.0, "nova": 220.0, "sawed-off": 210.0, "xm1014": 215.0}

static func max_speed(weapon: String) -> float:
	return float(TOP_SPEED.get(weapon, 250.0)) * METERS

static func accelerate(horizontal: Vector2, wish: Vector2, input_fraction: float, max_run: float,
		modifier: float, delta: float, on_ground: bool) -> Vector2:
	if on_ground:
		var drop := maxf(horizontal.length(), STOP_SPEED) * GROUND_FRICTION * delta
		horizontal = horizontal.move_toward(Vector2.ZERO, drop)
	var desired := max_run * modifier * input_fraction
	var projected_limit := desired if on_ground else minf(desired, AIR_WISH_CAP)
	var remaining := projected_limit - horizontal.dot(wish)
	if remaining <= 0.0:
		return horizontal
	# The air cap applies to the projection, not the total speed or the push.
	var push := (GROUND_ACCEL * max_run if on_ground else AIR_ACCEL * desired) * delta
	return horizontal + wish * minf(remaining, push)
