extends Node

const DIR := "res://generated/audio/"
const ACTIONS := {
	"usp-s/draw": [[0.10, "usp_draw"]],
	"usp-s/shoot1": [[0.0, "usp1"]],
	"usp-s/reload": [[0.21, "usp_clipout"], [0.52, "usp_clipin"], [0.72, "usp_slideback"], [0.84, "usp_sliderelease"]],
	"usp-s/silencer_attach": [[0.08, "gear-1"], [0.37, "gear-2"], [0.69, "gear-3"]],
	"usp-s/silencer_detach": [[0.11, "gear-1"], [0.40, "gear-2"], [0.79, "gear-3"]],
	"ak-47/draw": [[0.12, "ak47_draw"]],
	"ak-47/shoot1": [[0.0, "ak47-1"]],
	"ak-47/reload": [[0.19, "ak47_clipout"], [0.52, "ak47_clipin"], [0.80, "ak47_boltpull"]],
	"bayonet/draw": [[0.14, "knife-deploy"]],
	"bayonet/lookat01_draw": [[0.09, "knife-deploy"]],
	"bayonet/light_miss1": [[0.15, "knife-swing1"]],
	"bayonet/light_miss2": [[0.16, "knife-swing2"]],
	"bayonet/heavy_miss1": [[0.22, "knife-stab"]],
}

var sounds: Dictionary = {}
var voices: Array[AudioStreamPlayer] = []
var voice_cursor := 0
var step_index := 0
var ambience := AudioStreamPlayer.new()
var pending: Array = []
var next_cue := 0
var action_key := ""
var suppressed := false

func _ready() -> void:
	for i in 7:
		var voice := AudioStreamPlayer.new()
		voice.playback_type = AudioServer.PLAYBACK_TYPE_STREAM
		add_child(voice)
		voices.append(voice)
	ambience.playback_type = AudioServer.PLAYBACK_TYPE_STREAM
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

func cue(id: String, gain := -11.0, pitch := 1.0) -> void:
	var stream := get_sound(id)
	if stream == null:
		return
	var voice := voices[voice_cursor]
	voice_cursor = (voice_cursor + 1) % voices.size()
	voice.stream = stream
	voice.volume_db = gain
	voice.pitch_scale = pitch
	voice.play()

func step(sand: bool, quiet: bool) -> void:
	step_index = step_index % 4 + 1
	cue("step-%s-%d" % ["sand" if sand else "concrete", step_index], -22.0 if quiet else -14.0)

func start_clip(id: String, clip: String, with_silencer: bool) -> void:
	action_key = id + "/" + clip
	pending = ACTIONS.get(action_key, [])
	next_cue = 0
	suppressed = with_silencer
	follow_clip(id, clip, 0.0)

func follow_clip(id: String, clip: String, fraction: float) -> void:
	if action_key != id + "/" + clip:
		pending = []
		return
	while next_cue < pending.size() and fraction >= float(pending[next_cue][0]):
		var sample: String = pending[next_cue][1]
		var shot := clip == "shoot1"
		var quiet_shot := shot and id == "usp-s" and suppressed
		cue("usp1-muted" if quiet_shot else sample, -17.0 if quiet_shot else -9.0 if shot else -13.0, 0.88 if quiet_shot else 1.0)
		next_cue += 1
