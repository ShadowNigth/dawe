extends Node

const DIR := "res://generated/audio/"
const Assets = preload("res://scripts/assets.gd")
const SHOTS := {"usp-s": "usp1", "ak-47": "ak47-1", "m4a4": "m4a1-1", "glock": "glock18-1",
	"deagle": "deagle-1", "awp": "awp1"}

var sounds: Dictionary = {}
var voices: Array[AudioStreamPlayer] = []
var voice_cursor := 0
var step_index := 0
var ambience := AudioStreamPlayer.new()
var pending: Array = []
var next_cue := 0
var action_key := ""
var action_cues: Dictionary = {}
var usp_sample := 0
var source_audio: Dictionary
var next_sample: Dictionary

func _ready() -> void:
	action_cues = Assets.read_json("weapon-sound-cues")
	source_audio = Assets.read_json("archi-weapon-pack")
	# Browser builds use Web Audio samples; Dummy/headless has no sample backend.
	var playback := AudioServer.PLAYBACK_TYPE_STREAM
	if OS.has_feature("web") and DisplayServer.get_name() != "headless":
		playback = AudioServer.PLAYBACK_TYPE_SAMPLE
	for i in 7:
		var voice := AudioStreamPlayer.new()
		voice.playback_type = playback
		add_child(voice)
		voices.append(voice)
	ambience.playback_type = playback
	add_child(ambience)
	ambience.volume_db = -18.0

func begin_ambient() -> void:
	if ambience.playing:
		return
	var path := DIR + "desert-wind.wav"
	var wind: AudioStreamWAV = null
	if ResourceLoader.exists(path, "AudioStreamWAV"):
		wind = load(path) as AudioStreamWAV
	elif FileAccess.file_exists(path):
		wind = AudioStreamWAV.load_from_file(path)
	if wind != null:
		wind.loop_mode = AudioStreamWAV.LOOP_FORWARD
		wind.loop_end = roundi(wind.get_length() * wind.mix_rate)
		ambience.stream = wind
		ambience.play()

func get_sound(id: String) -> AudioStreamWAV:
	if not sounds.has(id):
		var path := DIR + id + ".wav"
		var stream: AudioStreamWAV = null
		if ResourceLoader.exists(path, "AudioStreamWAV"):
			stream = load(path) as AudioStreamWAV
		elif FileAccess.file_exists(path):
			stream = AudioStreamWAV.load_from_file(path)
		sounds[id] = stream
	return sounds[id]

func cue(id: String, gain := -11.0) -> void:
	var stream := get_sound(id)
	if stream == null:
		return
	var voice := voices[voice_cursor]
	voice_cursor = (voice_cursor + 1) % voices.size()
	voice.stream = stream
	voice.volume_db = gain
	voice.play()

func step(sand: bool) -> void:
	step_index = step_index % 4 + 1
	cue("step-%s-%d" % ["sand" if sand else "concrete", step_index], -14.0)

func zoom_sound(zoomed: bool) -> void:
	var zoom_cues: Dictionary = source_audio.get("zoom", {})
	cue(zoom_cues.get("in" if zoomed else "out", "zoom"), -13.0)

func shot_sample(id: String, with_silencer: bool) -> String:
	var bank := "usp-s-open" if id == "usp-s" and not with_silencer else id
	var choices: Array = source_audio.get("shots", {}).get(bank, [])
	if not choices.is_empty():
		var index: int = next_sample.get(bank, 0)
		next_sample[bank] = (index + 1) % choices.size()
		return String(choices[index])
	if id == "usp-s" and not with_silencer:
		usp_sample = usp_sample % 3 + 1
		return "usp-unsuppressed-%02d" % usp_sample
	return SHOTS.get(id, "")

func start_clip(id: String, clip: String, with_silencer: bool) -> void:
	action_key = id + "/" + clip
	pending = action_cues.get(action_key, [])
	if clip in ["shoot1", "shoot2", "shoot3"]:
		var shot := shot_sample(id, with_silencer)
		var level := -18.0 if id == "usp-s" and with_silencer else -9.0
		if not shot.is_empty():
			pending = [[0.0, shot, level]] + pending
	next_cue = 0
	follow_clip(id, clip, 0.0)

func follow_clip(id: String, clip: String, fraction: float) -> void:
	if action_key != id + "/" + clip:
		pending = []
		return
	while next_cue < pending.size() and fraction >= float(pending[next_cue][0]):
		var event: Array = pending[next_cue]
		cue(String(event[1]), float(event[2]))
		next_cue += 1
