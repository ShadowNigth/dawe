"""Stabilize first-person grips and guide the Desert Eagle presentation."""
import math

from mathutils import Quaternion, Vector

from build_viewmodel import arm_names


def align(rotation, bind_axis, animated_axis):
    """Swing a reference orientation onto the new limb direction, preserving roll."""
    return (rotation @ bind_axis).rotation_difference(animated_axis) @ rotation


def transform(rotation, origin):
    matrix = rotation.to_matrix().to_4x4()
    matrix.translation = origin
    return matrix


class GripRetarget:
    def __init__(self, bind, idle):
        self.bind, self.idle = bind, idle
        self.weapon_inverse = idle['weapon_offset'].inverted()
        self.arm_chains = tuple(arm_names(side) for side in ('Left', 'Right'))
        self.axes = {bone: (bind[child].translation - bind[bone].translation).normalized()
                     for upper, fore, hand, *_ in self.arm_chains
                     for bone, child in ((upper, fore), (fore, hand))}
        self.bind_rotation = {bone: bind[bone].to_quaternion() for bone in self.axes}
        self.previous = {}

    def solve_limb(self, name, child, pose, reference, limit, gun_delta, settle):
        axis = self.axes[name]
        direction = (pose[child].translation - pose[name].translation).normalized()
        prev = self.previous.get(name)
        if prev is None:
            rotation = align(reference, axis, direction)
        else:
            old_rotation, old_direction = prev
            # Parallel transport doesn't flip when the shoulder, elbow and wrist
            # become collinear. Only the remaining twist is steered toward the grip.
            rotation = old_direction.rotation_difference(direction) @ old_rotation
            # Swing-twist projection about the animated limb axis is independent
            # of the chosen swing solution, including near an antiparallel pose.
            relative = reference @ rotation.inverted()
            projected = relative.x * direction.x + relative.y * direction.y + relative.z * direction.z
            real = relative.w
            if abs(projected) + abs(real) > .1:
                twist = math.remainder(2.0 * math.atan2(projected, real), math.tau)
                rotation = Quaternion(direction, max(-limit, min(limit, twist))) @ rotation
        if settle:
            # A clip can come back to the idle pose before a rate-limited twist
            # has caught up. Match the idle roll before handing control back.
            idle_skin = (gun_delta @ self.idle[name] @ self.bind[name].inverted()).to_quaternion()
            rotation = rotation.slerp(align(idle_skin, axis, direction), settle)
        self.previous[name] = rotation, direction
        pose[name] = transform(rotation @ self.bind_rotation[name], pose[name].translation)
        return rotation

    def apply(self, pose, clip, settle=0.0, lock_right=True, recoil_mix=1.0):
        gun_delta = pose['weapon_offset'] @ self.weapon_inverse
        if clip == 'shoot1':
            # Both grips stay fixed in weapon space during recoil. Weapon parts
            # (slide/bolt/etc.) still use their own animation tracks.
            for chain in self.arm_chains:
                for name in chain:
                    target = gun_delta @ self.idle[name]
                    pose[name] = target if recoil_mix == 1.0 else pose[name].lerp(target, recoil_mix)
            if recoil_mix == 1.0:
                return pose
        for upper, fore, hand, *fingers in self.arm_chains:
            if lock_right and clip != 'idle' and hand == 'RightHand':
                target = gun_delta @ self.idle[hand]
                correction = target @ pose[hand].inverted()
                pose[hand] = target
                for finger in fingers:
                    pose[finger] = correction @ pose[finger]
            hand_skin = (pose[hand] @ self.bind[hand].inverted()).to_quaternion()
            fore_skin = self.solve_limb(fore, hand, pose, hand_skin, math.radians(7), gun_delta, settle)
            self.solve_limb(upper, fore, pose, fore_skin, math.radians(6), gun_delta, settle)
        return pose


def angle_between(a, b):
    return math.acos(max(-1.0, min(1.0, a.dot(b))))


def ease(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def pin_hand(pose, idle, side, strength=1.0):
    """Carry every finger with the wrist; never move the blade/receiver alone."""
    _, _, hand, *fingers = arm_names(side)
    target = pose['weapon_offset'] @ idle['weapon_offset'].inverted() @ idle[hand]
    wrist = pose[hand].lerp(target, strength)
    correction = wrist @ pose[hand].inverted()
    pose[hand] = wrist
    for finger in fingers:
        pose[finger] = correction @ pose[finger]


def seat_fingers(pose, idle, strength):
    """Keep the three wrap fingers seated; leave index/trigger and thumb authored."""
    hand = 'RightHand'
    frame = pose[hand] @ idle[hand].inverted()
    for digit in ('Middle', 'Ring', 'Pinky'):
        for index in range(1, 4):
            name = f'{hand}{digit}{index}'
            pose[name] = pose[name].lerp(frame @ idle[name], strength)


# Phase, yaw/pitch/roll in Studio space, grip offset in inches.
# Show both sides of the receiver without ever bringing the arm in from above.
DEAGLE_INSPECTION = (
    (0.00, (0, 0, 0), (0, 0, 0)),
    (0.15, (32, -22, -14), (0.6, 0.5, 0.5)),
    (0.32, (55, -29, -19), (0.9, 1.1, 1.1)),
    (0.43, (48, -33, -13), (0.8, 1.0, 1.0)),
    (0.63, (-44, -28, 17), (0.6, 0.6, 1.1)),
    (0.77, (-52, -24, 20), (0.6, 0.7, 1.2)),
    (0.94, (0, 0, 0), (0, 0, 0)),
    (1.00, (0, 0, 0), (0, 0, 0)),
)


def deagle_inspection(pose, idle, phase):
    """Guide two readable checks around the seated palm instead of flipping the gun."""
    def rotation(angles):
        yaw, pitch, roll = map(math.radians, angles)
        return (Quaternion((0, 0, 1), yaw) @ Quaternion((0, 1, 0), pitch)
                @ Quaternion((1, 0, 0), roll))

    for (start, angles, offset), (end, next_angles, next_offset) in zip(DEAGLE_INSPECTION, DEAGLE_INSPECTION[1:]):
        if phase <= end:
            weight = ease((phase - start) / (end - start))
            turn = rotation(angles).slerp(rotation(next_angles), weight)
            shift = Vector(offset).lerp(Vector(next_offset), weight)
            break
    pivot = idle['RightHand'].translation
    motion = transform(turn, pivot + shift - turn @ pivot)
    delta = motion @ idle['weapon_offset'] @ pose['weapon_offset'].inverted()
    for name in ('weapon_offset', 'slide', 'clip', 'hammer', 'trigger'):
        pose[name] = delta @ pose[name]
    for name in arm_names('Right'):
        # Keep the elbow behind the gun, not on the source clip's flip path.
        pose[name] = idle[name] if name in ('RightArm', 'RightForeArm') else motion @ idle[name]
    release = ease(phase / .16) * (1.0 - ease((phase - .76) / .16))
    offhand = Vector((-.8, 1.0, -2.2)) * release
    for name in arm_names('Left'):
        pose[name] = idle[name].copy()
        if name not in ('LeftArm', 'LeftForeArm'):
            pose[name].translation += offhand


class ArmGuide:
    """Swing the elbow off the hand's grip axis rather than twisting the wrist."""

    def __init__(self, idle, bind):
        self.idle, self.bind = idle, bind
        self.previous = {}

    def apply(self, pose, side, wrist_limit, limit_step=15):
        upper, fore, hand, *_ = arm_names(side)
        palm = pose[hand].translation
        current = palm - pose[fore].translation
        arm = pose[fore].translation - pose[upper].translation
        if current.length < 1e-5 or arm.length < 1e-5:
            return
        guided = pose[hand] @ self.idle[hand].inverted()
        fore_reference = guided @ self.idle[fore]
        axis = (palm - fore_reference.translation).normalized()
        authored = current.normalized()
        swing = angle_between(axis, authored)
        # A soft cone avoids a sharp change in velocity at the limit. Reduce
        # the source elbow influence near antiparallel to avoid a sign flip.
        knee, limit = math.radians(wrist_limit * .68), math.radians(wrist_limit)
        bounded = swing if swing <= knee else knee + (limit-knee) * (1-math.exp(-(swing-knee)/(limit-knee)))
        bounded *= 1.0 - ease((math.degrees(swing) - 118.0) / 53.0)
        adjustment = Quaternion().slerp(axis.rotation_difference(authored), bounded / max(swing, 1e-7))
        desired = adjustment @ fore_reference.to_quaternion()
        local = pose[hand].to_quaternion().inverted() @ desired
        old = self.previous.get(side)
        if old is not None:
            angle = 2.0 * math.acos(min(1.0, abs(old.dot(local))))
            if angle > math.radians(limit_step):
                local = old.slerp(local, math.radians(limit_step) / angle)
        self.previous[side] = local
        rotation = pose[hand].to_quaternion() @ local
        rest_axis = (self.bind[hand].translation - self.bind[fore].translation).normalized()
        local_axis = self.bind[fore].to_quaternion().inverted() @ rest_axis
        length = (self.idle[hand].translation - self.idle[fore].translation).length
        elbow = palm - (rotation @ local_axis) * length
        shoulder = pose[upper].translation
        toward_elbow = elbow - shoulder
        if toward_elbow.length < 1e-4:
            toward_elbow = arm
        # Keep the upper-arm length while following the authored shoulder line.
        length = (self.idle[fore].translation - self.idle[upper].translation).length
        shoulder = elbow - toward_elbow.normalized() * length
        upper_axis = (self.bind[fore].translation - self.bind[upper].translation).normalized()
        upper_skin = (pose[upper] @ self.bind[upper].inverted()).to_quaternion()
        upper_rotation = align(upper_skin, upper_axis, (elbow - shoulder).normalized()) @ self.bind[upper].to_quaternion()
        pose[fore] = transform(rotation, elbow)
        pose[upper] = transform(upper_rotation, shoulder)
