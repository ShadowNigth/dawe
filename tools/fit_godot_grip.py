"""Fit weighted finger surfaces to each viewmodel at bake time."""
import math

from mathutils import Quaternion, Vector
from mathutils.bvhtree import BVHTree

from build_viewmodel import DIGITS


def pivot_matrix(rotation, origin):
    matrix = rotation.to_matrix().to_4x4()
    matrix.translation = origin - rotation @ origin
    return matrix


def correct_finger(pose, chain, angles, hand):
    width = pose[hand+'Pinky1'].translation - pose[hand+'Index1'].translation
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


class SurfaceGrip:
    def __init__(self, weapon, hands, names, rest, side):
        self.hand = side + 'Hand'
        self.names = tuple(names)
        self.inverse = tuple(rest[name].inverted() for name in self.names)
        self.chains = {d: [f'{self.hand}{d}{i+1}' for i in range(2 if d == 'Thumb' else 3)] for d in DIGITS}
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

    def clearances(self, digit, pose):
        transforms = {i: pose[self.names[i]] @ self.inverse[i] for _, links in self.samples[digit] for i, _ in links}
        for point, links in self.samples[digit]:
            posed = sum((transforms[i] @ point * weight for i, weight in links), Vector((0, 0, 0)))
            nearest, normal, _, depth = self.surface.find_nearest(posed, 0.85)
            yield (depth if normal.dot(posed - nearest) >= 0 else -depth) if nearest is not None else 0.85

    def loss(self, digit, pose, anchors):
        values = list(self.clearances(digit, pose))
        intersect = sum(max(0.0, -d)**2 for d in values) / max(1, len(values))
        # Keep the pad within ~1 mm of the existing contact patch; penalize
        # hovering without dragging an intentionally free index to the trigger.
        contact = sum(max(0.0, values[i]-.045)**2 for i in anchors) / max(1, len(anchors))
        return intersect + .10 * contact

    def fit(self, idle, complete):
        before = after = 0.0
        for digit, chain in self.chains.items():
            clearance = list(self.clearances(digit, complete(dict(idle))))
            distal = set(chain[1:])
            candidates = [i for i, (_, links) in enumerate(self.samples[digit])
                          if self.names[links[0][0]] in distal and -.40 <= clearance[i] < .48]
            anchors = sorted(candidates, key=lambda i: abs(clearance[i]))[:12] if digit != 'Index' else []

            def score(angles):
                candidate = dict(idle)
                correct_finger(candidate, chain, angles, self.hand)
                return self.loss(digit, complete(candidate), anchors)

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
                        loss = score(test) + 0.007 * sum(v*v for v in test)
                        if loss + 1e-8 < best:
                            best, angles = loss, test
            self.angles[digit] = angles
            after += score(angles)
        print(f'{self.hand} grip contact cost: {before:.4f} -> {after:.4f}', flush=True)

    def apply(self, pose, strength=1.0):
        for digit, chain in self.chains.items():
            correct_finger(pose, chain, [angle * strength for angle in self.angles[digit]], self.hand)
        return pose
