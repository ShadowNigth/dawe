"""Fit the previously baked Silverhand/implant geometry to each Archi rig."""
import copy
from functools import lru_cache
import re

import numpy as np

from check_godot_assets import read


DIGITS = {'Thumb': '0', 'Index': '1', 'Middle': '2', 'Ring': '3', 'Pinky': '4'}


def anatomical_axes(points, side, part):
    def p(suffix):
        return points[side + suffix][:3, 3]
    palm_width = p('HandPinky1') - p('HandIndex1')
    if part == 'ForeArm':
        forward = p('Hand') - p('ForeArm')
    elif part == 'Hand':
        forward = (p('HandMiddle1') + p('HandRing1')) * .5 - p('Hand')
    else:
        prefix, level = part[:-1], int(part[-1])
        end = 2 if prefix == 'HandThumb' else 3
        forward = (p(prefix + str(level+1)) - p(part)) if level < end else (p(part) - p(prefix + str(level-1)))
    forward /= max(np.linalg.norm(forward), 1e-9)
    across = palm_width - np.dot(forward, palm_width) * forward
    if np.linalg.norm(across) < .01 * np.linalg.norm(palm_width):
        arm_down = p('HandMiddle1') - p('Hand')
        across = np.cross(forward, arm_down)
    across /= max(np.linalg.norm(across), 1e-9)
    return np.column_stack((forward, across, np.cross(forward, across)))


def target_names(model):
    mapping = {}
    for i, (name, _) in enumerate(model.names):
        match = re.search(r'Bip01_([LR])_(Forearm|Hand|Finger([0-4])([12])?)$', name, re.I)
        if not match:
            continue
        side = 'Left' if match[1].upper() == 'L' else 'Right'
        part = {'forearm': 'ForeArm', 'hand': 'Hand'}.get(match[2].lower())
        if part is None:
            digit = next(key for key, value in DIGITS.items() if value == match[3])
            level = int(match[4] or '0') + 1
            if digit == 'Thumb' and level > 2:
                continue
            part = 'Hand' + digit + str(level)
        mapping[side + part] = i
    return mapping


def collapse(name):
    if name in ('LeftArm', 'RightArm'):
        return name.replace('Arm', 'ForeArm')
    if re.fullmatch(r'(Left|Right)(ForeArm|Hand(?:Thumb[12]|(?:Index|Middle|Ring|Pinky)[123])?)', name):
        return name
    if 'InHand' in name:
        return name.split('InHand')[0] + 'Hand'
    if name.startswith(('l_', 'r_')):
        side = 'Left' if name.startswith('l_') else 'Right'
        n = name.lower()
        if any(word in n for word in ('bicep', 'tricep', 'elbow', 'shl', 'chest', 'latissimus', 'scapula', 'deltoid', 'butterfly')):
            return side + 'ForeArm'
        for pattern, digit in [('ind_knuckle', 'Index'), ('mid_knuckle', 'Middle'), ('ring_knuckle', 'Ring'), ('pinky_knuckle', 'Pinky')]:
            if pattern in n:
                return side + 'Hand' + digit + ('2' if '_b_top' in n else '1')
        if 'thumb_a' in n:
            return side + 'HandThumb1'
        return side + 'Hand'
    return 'LeftForeArm' if name == 'LeftShoulder' else None


@lru_cache(maxsize=1)
def reference(path):
    doc, glb = read(path)
    skin = doc['skins'][0]
    bones = [doc['nodes'][i]['name'] for i in skin['joints']]
    matrices = np.linalg.inv(glb.accessor(skin['inverseBindMatrices']).reshape(-1, 4, 4).transpose(0, 2, 1))
    return doc, glb, bones, dict(zip(bones, matrices))


def fit(export, reference_path, neutral):
    doc, glb, bones, source = reference(reference_path)
    names = target_names(export)
    # Some Source rigs provide only the first two thumb bones; the Cyberpunk
    # export also uses two, so no additional animated joints need to be made.
    points = {name: neutral[i] for name, i in names.items()}
    order = sorted(names)
    index = {name: i for i, name in enumerate(order)}
    binds = []
    for key in order:
        side = 'Left' if key.startswith('Left') else 'Right'
        part = key[len(side):]
        src_axes = anatomical_axes(source, side, part)
        tgt_axes = anatomical_axes(points, side, part)
        change = np.eye(4)
        change[:3, :3] = tgt_axes @ src_axes.T
        change[:3, 3] = points[key][:3, 3] - change[:3, :3] @ source[key][:3, 3]
        binds.append(np.linalg.inv(change) @ points[key])
    skin = export.skin([names[key] for key in order], np.array(binds))
    images = {}
    def material(mid):
        spec = copy.deepcopy(doc['materials'][mid])
        for owner in (spec, spec['pbrMetallicRoughness']):
            for key, slot in owner.items():
                if not key.endswith('Texture'):
                    continue
                original = doc['textures'][slot['index']]['source']
                if original not in images:
                    image = doc['images'][original]
                    dst = len(export.doc['images'])
                    export.doc['images'].append(dict(bufferView=export.w.view(bytes(glb.view(image['bufferView']))), mimeType=image['mimeType']))
                    images[original] = len(export.doc['textures'])
                    export.doc['textures'].append(dict(source=dst))
                slot['index'] = images[original]
        export.doc['materials'].append(spec)
        return len(export.doc['materials']) - 1

    primitives = []
    for mesh in doc['meshes']:
        for prim in mesh['primitives']:
            mid = prim['material']
            if doc['materials'][mid]['name'] not in ('silverhand', 'skin', 'grip-implant'):
                continue
            attrs = {key: glb.accessor(a) for key, a in prim['attributes'].items()}
            weights = np.zeros_like(attrs['WEIGHTS_0'])
            links = np.zeros_like(attrs['JOINTS_0'])
            for i, (js, ws) in enumerate(zip(attrs['JOINTS_0'], attrs['WEIGHTS_0'])):
                unique = {}
                for joint, weight in zip(js, ws):
                    if weight <= 0:
                        continue
                    logical = collapse(bones[joint])
                    if logical is None:
                        logical = min(('LeftForeArm', 'RightForeArm'),
                                      key=lambda k: np.linalg.norm(attrs['POSITION'][i] - source[k][:3, 3]))
                    if logical not in index:
                        raise ValueError(f'No se puede asignar {bones[joint]} ({logical}) al rig de Archi')
                    mapped = index[logical]
                    unique[mapped] = unique.get(mapped, 0.) + weight
                for k, (j, w) in enumerate(sorted(unique.items(), key=lambda item: -item[1])):
                    links[i, k], weights[i, k] = j, w
            primitives.append(export.primitive(attrs['POSITION'], attrs['NORMAL'], attrs['TEXCOORD_0'], links,
                                               weights, glb.accessor(prim['indices']).ravel(), material(mid)))
    export.mesh('CyberpunkArms', primitives, skin)
    export.doc['extras']['arms'] = 'Cyberpunk2077-MultiRig'
