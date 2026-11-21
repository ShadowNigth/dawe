"""Stabilize first-person arm rotations without modifying the authored weapon tracks."""
import math

from mathutils import Quaternion

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


class WristContinuity:
    """Rate-limit only pathological wrist snaps, retaining the authored positions."""

    def __init__(self):
        self.previous = {}

    def apply(self, pose):
        for side in ('Left', 'Right'):
            _, fore, hand, *fingers = arm_names(side)
            fore_rotation = pose[fore].to_quaternion()
            local = fore_rotation.inverted() @ pose[hand].to_quaternion()
            old = self.previous.get(hand)
            if old is not None:
                angle = 2.0 * math.acos(min(1.0, abs(old.dot(local))))
                limit = math.radians(42)
                if angle > limit:
                    local = old.slerp(local, limit / angle)
                    target = transform(fore_rotation @ local, pose[hand].translation)
                    correction = target @ pose[hand].inverted()
                    pose[hand] = target
                    for finger in fingers:
                        pose[finger] = correction @ pose[finger]
            self.previous[hand] = local
