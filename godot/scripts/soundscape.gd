extends Node

const DIR := "res://generated/audio/"
const Assets = preload("res://scripts/assets.gd")
const SHOTS := {"usp-s": "usp1", "ak-47": "ak47-1", "m4a4": "m4a1-1"}

var sounds: Dictionary = {}
var voices: Array[AudioStreamPlayer] = []
var voice_cursor := 0
var step_index := 0
var ambience := AudioStreamPlayer.new()
var pending: Array = []
var next_cue := 0
var action_key := ""
var action_cues: Dictionary = {}

func _ready() -> void:
	action_cues = Assets.read_json("weapon-sound-cues")
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

static func shot_sample(id: String, with_silencer: bool) -> String:
	if id == "usp-s" and not with_silencer:
		return "usp-unsuppressed"
	return SHOTS.get(id, "")

func start_clip(id: String, clip: String, with_silencer: bool) -> void:
	action_key = id + "/" + clip
	pending = action_cues.get(action_key, [])
	if clip == "shoot1":
		var shot := shot_sample(id, with_silencer)
		var level := -18.0 if id == "usp-s" and with_silencer else -9.0
		pending = [[0.0, shot, level]] if not shot.is_empty() else []
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
