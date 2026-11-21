extends RefCounted

const RIFLES := ["ak-47", "m4a4", "m4a1-s", "famas", "galil", "aug", "sg-553", "awp", "ssg-08", "g3sg1", "scar-20"]
const SMGS := ["mac-10", "mp5-sd", "mp7", "mp9", "ump-45", "p90", "bizon"]
const HEAVY := ["nova", "xm1014", "mag-7", "sawed-off", "m249", "negev"]
const PRIMARY := RIFLES + SMGS + HEAVY
const SECONDARY := ["usp-s", "glock", "deagle", "p2000", "p250", "dual-berettas", "five-seven", "tec-9", "cz75", "r8", "zeus"]
const KNIFE := "bayonet"
const SILENCERS := ["usp-s", "m4a1-s"]
const SCOPE_LEVELS := {"awp": 2, "ssg-08": 2, "g3sg1": 2, "scar-20": 2, "aug": 1, "sg-553": 1}
const LABELS := {"ak-47": "AK-47", "m4a4": "M4A4", "m4a1-s": "M4A1-S", "awp": "AWP", "usp-s": "USP-S",
	"glock": "Glock-18", "deagle": "Desert Eagle", "bayonet": "Kukri", "p2000": "P2000", "p250": "P250",
	"dual-berettas": "Dual Berettas", "five-seven": "Five-SeveN", "tec-9": "Tec-9", "cz75": "CZ75-Auto", "r8": "Revólver R8", "zeus": "Zeus x27",
	"aug": "AUG", "famas": "FAMAS", "g3sg1": "G3SG1", "galil": "Galil AR", "scar-20": "SCAR-20", "sg-553": "SG 553", "ssg-08": "SSG 08",
	"bizon": "PP-Bizon", "mac-10": "MAC-10", "mp5-sd": "MP5-SD", "mp7": "MP7", "mp9": "MP9", "p90": "P90", "ump-45": "UMP-45",
	"m249": "M249", "negev": "Negev", "mag-7": "MAG-7", "nova": "Nova", "sawed-off": "Sawed-Off", "xm1014": "XM1014"}

static func slot(id: String) -> int:
	if id in PRIMARY:
		return 0
	if id in SECONDARY:
		return 1
	return 2 if id == KNIFE else -1

static func label(id: String) -> String:
	return LABELS.get(id, "Vacía")
