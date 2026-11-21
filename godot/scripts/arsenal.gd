extends RefCounted

const PRIMARY := ["ak-47", "m4a4", "awp"]
const SECONDARY := ["usp-s", "glock", "deagle"]
const KNIFE := "bayonet"
const LABELS := {"ak-47": "AK-47", "m4a4": "M4A4", "awp": "AWP", "usp-s": "USP-S",
	"glock": "Glock-18", "deagle": "Desert Eagle", "bayonet": "Kukri"}

static func slot(id: String) -> int:
	if id in PRIMARY:
		return 0
	if id in SECONDARY:
		return 1
	return 2 if id == KNIFE else -1

static func label(id: String) -> String:
	return LABELS.get(id, "Vacía")
