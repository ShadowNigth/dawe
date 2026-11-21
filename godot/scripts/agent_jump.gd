extends RefCounted

# No jump GLB is provided by the locomotion bank. These in-place poses retain
# the equipped stance's upper body, and physics owns the player's translation.
# Column order: hips down, spine lean, left/right thigh lift, left/right knee.
const READY := [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
const TUCK := [-0.07, 9.0, -28.0, -17.0, 49.0, 36.0]
const EXTEND := [-0.025, 7.0, -11.0, -5.0, 19.0, 13.0]
const COMPRESS := [-0.12, 12.0, -26.0, -23.0, 49.0, 44.0]
const BONES := {"spine_0": 1, "leg_upper_L": 2, "leg_upper_R": 3, "leg_lower_L": 4, "leg_lower_R": 5}

static func find_skeleton(node: Node) -> Skeleton3D:
	if node is Skeleton3D:
		return node
	for child in node.get_children():
		var found := find_skeleton(child)
		if found != null:
			return found
	return null

static func install(model: Node, player: AnimationPlayer) -> void:
	var rig := find_skeleton(model)
	if rig == null or rig.find_bone("pelvis") < 0:
		return
	var base_path := player.get_node(player.root_node).get_path_to(rig)
	var library := AnimationLibrary.new()
	for stance in ["pistol", "rifle", "knife"]:
		var source: String = "walk_ne_" + stance
		if not player.has_animation(source):
			continue
		player.play(source, 0.0)
		player.seek(player.get_animation(source).length * 0.5, true)
		var phases := {
			"rise": [[0.0, READY], [0.10, EXTEND], [0.29, TUCK]],
			"fall": [[0.0, TUCK], [0.24, EXTEND]],
			"land": [[0.0, EXTEND], [0.075, COMPRESS], [0.23, READY]],
		}
		for phase: String in phases:
			var clip := Animation.new()
			var keys: Array = phases[phase]
			clip.length = keys.back()[0]
			for i in rig.get_bone_count():
				var bone := rig.get_bone_name(i)
				var path := NodePath("%s:%s" % [base_path, bone])
				var rot := clip.add_track(Animation.TYPE_ROTATION_3D)
				var pos := clip.add_track(Animation.TYPE_POSITION_3D)
				clip.track_set_path(rot, path)
				clip.track_set_path(pos, path)
				var parent := rig.get_bone_parent(i)
				var basis := rig.get_bone_global_pose(parent).basis.orthonormalized() if parent >= 0 else Basis.IDENTITY
				var right := (basis.inverse() * Vector3.RIGHT).normalized()
				var up := basis.inverse() * Vector3.UP
				var base_rot := rig.get_bone_pose_rotation(i)
				var base_pos := rig.get_bone_pose_position(i)
				for key: Array in keys:
					var pose: Array = key[1]
					var angle := deg_to_rad(float(pose[BONES[bone]])) if BONES.has(bone) else 0.0
					clip.rotation_track_insert_key(rot, key[0], Quaternion(right, angle) * base_rot)
					clip.position_track_insert_key(pos, key[0], base_pos + up * float(pose[0]) if bone == "pelvis" else base_pos)
			library.add_animation("%s_%s" % [phase, stance], clip)
	player.stop(true)
	player.add_animation_library("jump", library)
