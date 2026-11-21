"""Fit the right fingers of the MultiRig to a viewmodel's grip at bake time."""
import math

from mathutils import Quaternion, Vector
from mathutils.bvhtree import BVHTree

from build_viewmodel import DIGITS


def pivot_matrix(rotation, origin):
    matrix = rotation.to_matrix().to_4x4()
    matrix.translation = origin - rotation @ origin
    return matrix


def correct_finger(pose, chain, angles):
    width = pose['RightHandPinky1'].translation - pose['RightHandIndex1'].translation
    for index, (bone, angle) in enumerate(zip(chain, angles)):
        if not angle:
            continue
        origin = pose[bone].translation
        forward = pose[chain[index + 1]].translation - origin if index + 1 < len(chain) else pose[bone].to_3x3().col[1]
        axis = width - forward.normalized() * width.dot(forward.normalized())
        if axis.length_squared < 1e-5:
            continue
        turn = pivot_matrix(Quaternion(axis.normalized(), angle), origin)
        for child in chain[index:]:
            pose[child] = turn @ pose[child]


class RightGrip:
    def __init__(self, weapon, hands, names, rest):
        self.names = tuple(names)
        self.inverse = tuple(rest[name].inverted() for name in self.names)
        self.chains = {d: [f'RightHand{d}{i+1}' for i in range(2 if d == 'Thumb' else 3)] for d in DIGITS}
        vertices = [Vector(pos) for _, tri in weapon for pos, _, _, _ in tri]
        self.surface = BVHTree.FromPolygons(vertices, [tuple(range(i, i+3)) for i in range(0, len(vertices), 3)], all_triangles=True)
        self.samples = {}
        for digit, chain in self.chains.items():
            # Deduplicate mesh/UV seams and retain the actual weighted surface,
            # not just the bone centers, as the fingertip has nonzero thickness.
            points = {(pos, links) for _, tri in hands for pos, _, _, links in tri if self.names[links[0][0]] in chain}
            sorted_points = sorted(points)
            stride = max(1, len(sorted_points) // 190)
            self.samples[digit] = [(Vector(pos), links) for pos, links in sorted_points[::stride]]
        self.angles = {}

    def cost(self, digit, pose):
        transforms = {i: pose[self.names[i]] @ self.inverse[i] for _, links in self.samples[digit] for i, _ in links}
        total = 0.0
        for point, links in self.samples[digit]:
            posed = sum((transforms[i] @ point * weight for i, weight in links), Vector((0, 0, 0)))
            nearest, normal, _, depth = self.surface.find_nearest(posed, 0.75)
            if nearest is not None and normal.dot(posed - nearest) < 0:
                total += depth * depth
        return total / max(1, len(self.samples[digit]))

    def fit(self, idle, complete):
        before = after = 0.0
        for digit, chain in self.chains.items():
            def score(angles):
                candidate = dict(idle)
                correct_finger(candidate, chain, angles)
                return self.cost(digit, complete(candidate))

            angles = [0.0] * len(chain)
            before += score(angles)
            best = score(angles)
            bounds = tuple(map(math.radians, (27, 42, 30)))
            for step_deg in (15, 8, 4, 2):
                for axis in range(len(chain)):
                    step = math.radians(step_deg)
                    trials = (angles[axis] + k * step for k in (-2, -1, 1, 2))
                    for value in trials:
                        test = list(angles)
                        test[axis] = max(-bounds[axis], min(bounds[axis], value))
                        loss = score(test) + 0.018 * sum(v*v for v in test)
                        if loss + 1e-8 < best:
                            best, angles = loss, test
            self.angles[digit] = angles
            after += score(angles)
        print(f'Right grip surface cost: {before:.4f} -> {after:.4f}', flush=True)

    def apply(self, pose):
        for digit, chain in self.chains.items():
            correct_finger(pose, chain, self.angles[digit])
        return pose
