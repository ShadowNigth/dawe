#!/usr/bin/env python3
"""Verify local Godot asset packs: GLB accessors, clip sets, and Outside Long floor."""
import argparse
import json
from pathlib import Path
import struct

import numpy as np

from build_agents import GLTF, rotation
from import_assets import AGENT_CLIPS, ROOT, GODOT_WEAPON_CLIPS


def read(path):
    with path.open('rb') as f:
        magic, version, total, n, kind = struct.unpack('<4sIII4s', f.read(20))
        assert (magic, version, total, kind) == (b'glTF', 2, path.stat().st_size, b'JSON')
        doc = json.loads(f.read(n))
        size, kind = struct.unpack('<I4s', f.read(8))
        assert kind == b'BIN\0' and size + n + 28 == total
        data = f.read(size)
    reader = GLTF(dict(doc, nodes=[]), data)
    for image in doc.get('images', []):
        assert image['mimeType'] == 'image/png' and bytes(reader.view(image['bufferView'])[:8]) == b'\x89PNG\r\n\x1a\n'
    for collection in ('extensionsUsed', 'extensionsRequired'):
        assert not ({'KHR_mesh_quantization', 'EXT_meshopt_compression', 'KHR_texture_basisu'} & set(doc.get(collection, [])))
    for m in doc['meshes']:
        for prim in m['primitives']:
            assert reader.accessor(prim['attributes']['POSITION']).dtype == np.dtype('<f4')
    return doc, reader


def surfaces(doc, reader):
    def node_tree(i, parent):
        node = doc['nodes'][i]
        if 'matrix' in node:
            transform = np.array(node['matrix']).reshape(4, 4).T
        else:
            transform = np.eye(4)
            transform[:3, :3] = rotation(node.get('rotation', [0, 0, 0, 1])) * node.get('scale', [1, 1, 1])
            transform[:3, 3] = node.get('translation', [0, 0, 0])
        transform = parent @ transform
        if 'mesh' in node:
            for p in doc['meshes'][node['mesh']]['primitives']:
                pos = reader.accessor(p['attributes']['POSITION'])
                xyz = pos @ transform[:3, :3].T + transform[:3, 3]
                indexes = reader.accessor(p['indices']).ravel() if 'indices' in p else np.arange(len(xyz))
                yield xyz[indexes.reshape(-1, 3)]
        for child in node.get('children', []):
            yield from node_tree(child, transform)
    for i in doc['scenes'][doc.get('scene', 0)]['nodes']:
        yield from node_tree(i, np.eye(4))


def floor_height(meshes, position):
    y = -np.inf
    point = np.array(position)[[0, 2]]
    for xyz in meshes:
        a, b, c = xyz[:, :, [0, 2]].transpose(1, 0, 2)
        ab, ac, off = b-a, c-a, point-a
        def cross(u, v):
            return u[:, 0]*v[:, 1] - u[:, 1]*v[:, 0]
        denom = cross(ab, ac)
        denom[abs(denom) < 1e-9] = np.nan
        u, v = cross(off, ac)/denom, cross(ab, off)/denom
        hit = xyz[:, 0, 1] + u * (xyz[:, 1, 1]-xyz[:, 0, 1]) + v * (xyz[:, 2, 1]-xyz[:, 0, 1])
        eligible = hit[(u >= 0) & (v >= 0) & (u+v <= 1) & (hit < position[1])]
        if len(eligible):
            y = max(y, eligible.max())
    return y


def verify_quality(doc, model, bayonet=False):
    assert len(doc['skins'][0]['joints']) > 90
    assert {'silverhand', 'grip-implant', 'skin', 'weapon-color'} <= {mat['name'] for mat in doc['materials']}
    skinned_hands = 0
    original_tris = 0
    for mesh in doc['meshes']:
        for surf in mesh['primitives']:
            original_tris += len(model.accessor(surf['indices'])) // 3
            weights = model.accessor(surf['attributes']['WEIGHTS_0'])
            assert np.allclose(weights.sum(axis=1), 1.0, atol=1e-5)
            mat = doc['materials'][surf['material']]
            if not mat['name'].startswith('weapon-'):
                skinned_hands += np.count_nonzero((weights > 0.00001).sum(axis=1) > 1)
            if mat['name'] != 'skin':
                assert 'occlusionTexture' in mat
                if not (bayonet and mat['name'] == 'weapon-color'):
                    assert 'normalTexture' in mat and 'TANGENT' in surf['attributes']
                assert 'metallicRoughnessTexture' in mat['pbrMetallicRoughness']
    assert skinned_hands > 1000 and original_tris > 25000
    print(f'  {original_tris:,} triángulos y {skinned_hands:,} vértices de brazo con múltiples pesos')

def animation_poses(doc, model, clip):
    # Generated weapon tracks share one frame grid. Compose their local TR keys
    # in hierarchy order to measure grip stability in weapon space.
    sample = clip['samplers'][0]['input']
    joints = doc['skins'][0]['joints']
    count = len(model.accessor(sample))
    poses = {joint: np.tile(np.eye(4), (count, 1, 1)) for joint in joints}
    for channel in clip['channels']:
        track = clip['samplers'][channel['sampler']]
        assert track['input'] == sample
        target = channel['target']
        values = model.accessor(track['output'])
        if target['path'] == 'rotation':
            poses[target['node']][:, :3, :3] = [rotation(q) for q in values]
        elif target['path'] == 'translation':
            poses[target['node']][:, :3, 3] = values
    for joint in joints:
        for child in doc['nodes'][joint].get('children', []):
            if child in poses:
                poses[child] = poses[joint] @ poses[child]
    return {doc['nodes'][i]['name']: pose for i, pose in poses.items()}


def angular_distance(a, b):
    # trace(transpose(a) @ b) for rotation matrices.
    inner = np.sum(a[..., :3, :3] * b[..., :3, :3], axis=(-2, -1))
    return np.degrees(np.arccos(np.clip((inner - 1) / 2, -1, 1)))


def verify_grips(doc, model, bolt_cycle=False):
    clips = {clip['name']: clip for clip in doc['animations']}
    idle = animation_poses(doc, model, clips['idle'])
    idle_gun_inverse = np.linalg.inv(idle['weapon_offset'])
    wrist_delta = 0.0
    for name, clip in clips.items():
        pose = animation_poses(doc, model, clip)
        gun_inverse = np.linalg.inv(pose['weapon_offset'])
        for side in ('Left', 'Right'):
            hand, fore = side+'Hand', side+'ForeArm'
            if name != 'idle':
                local = np.linalg.inv(pose[fore]) @ pose[hand]
                step = float(angular_distance(local[1:], local[:-1]).max())
                wrist_delta = max(step, wrist_delta)
                assert step < 50., (name, side, 'wrist discontinuity', step)
                for limb in (side+'Arm', fore, hand):
                    end_in_gun = gun_inverse[-1] @ pose[limb][-1]
                    rest_in_gun = idle_gun_inverse[0] @ idle[limb][0]
                    end_angle = float(angular_distance(end_in_gun, rest_in_gun))
                    assert end_angle < 12., (name, limb, 'idle transition', end_angle)
            if name == 'shoot1':
                for limb in (side+'Arm', fore, hand):
                    relative = gun_inverse @ pose[limb]
                    recoil = relative[:7] if bolt_cycle else relative
                    assert np.max(angular_distance(recoil, idle_gun_inverse @ idle[limb])) < .2, limb
                    assert np.allclose(recoil[:, :3, 3], (idle_gun_inverse @ idle[limb])[:, :3, 3], atol=1e-4), limb
                    if bolt_cycle and limb == 'RightHand':
                        assert np.max(np.linalg.norm(relative[7:, :3, 3] - recoil[0, :3, 3], axis=1)) > .02
    print(f'  Giro máximo de muñeca por fotograma: {wrist_delta:.1f}°; agarres fijos durante el disparo')


def verify_wrist_and_grip_limits(doc, model, weapon):
    """Check absolute wrist angles and limb lengths, not just frame-to-frame jitter."""
    clips = {clip['name']: clip for clip in doc['animations']}
    idle = animation_poses(doc, model, clips['idle1' if weapon == 'bayonet' else 'idle'])
    default_grip = np.linalg.inv(idle['weapon_offset'][0]) @ idle['RightHand'][0]
    worst = {"Right": 0.0, "Left": 0.0}
    for name, clip in clips.items():
        pose = animation_poses(doc, model, clip)
        for side in ('Right', 'Left'):
            upper, fore, hand = (side + part for part in ('Arm', 'ForeArm', 'Hand'))
            for parent, child in ((upper, fore), (fore, hand)):
                rest_length = np.linalg.norm(idle[parent][0, :3, 3] - idle[child][0, :3, 3])
                lengths = np.linalg.norm(pose[parent][:, :3, 3] - pose[child][:, :3, 3], axis=1)
                assert np.max(np.abs(lengths-rest_length)) < .002, (weapon, name, child, 'arm stretch')
            neutral = np.linalg.inv(idle[fore][0]) @ idle[hand][0]
            wrist = np.linalg.inv(pose[fore]) @ pose[hand]
            angle = float(angular_distance(neutral, wrist).max())
            limit = 33.0 if weapon == 'deagle' and name == 'lookat01' and side == 'Right' else 65.0
            assert angle <= limit, (weapon, name, side, 'wrist outside guide', angle)
            if len(wrist) > 1:
                step = float(angular_distance(wrist[1:], wrist[:-1]).max())
                assert step < 23.0, (weapon, name, side, 'wrist discontinuity', step)
            if name.startswith('lookat'):
                worst[side] = max(worst[side], angle)
        if weapon == 'deagle' and name == 'lookat01':
            palm = pose['RightHand'][:, :3, 3]
            elbow = pose['RightForeArm'][:, :3, 3]
            assert np.all(elbow[:, 1] < palm[:, 1]), 'Deagle elbow rises above the grip during inspection'
            assert np.all(elbow[:, 2] > palm[:, 2]), 'Deagle elbow extends in front of the grip'
        anchored = name in ('idle1', 'idle2', 'light_miss1', 'light_miss2') if weapon == 'bayonet' else name != 'idle'
        if anchored:
            held = np.linalg.inv(pose['weapon_offset']) @ pose['RightHand']
            if weapon == 'awp' and name == 'shoot1':
                held = held[:7] # The right hand releases to cycle the bolt after recoil.
            assert np.max(np.linalg.norm(held[:, :3, 3] - default_grip[:3, 3], axis=1)) < .001, (weapon, name, 'grip drift')
            assert np.max(angular_distance(held, default_grip)) < .25, (weapon, name, 'grip roll')
    print(f"  Inspección: muñeca derecha {worst['Right']:.1f}°, izquierda {worst['Left']:.1f}°; largo de brazo constante y agarre anclado")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--quality-viewmodels', action='store_true', help='exige las armas mejoradas con PBR y pesos múltiples')
    parser.add_argument('--assets', type=Path, default=ROOT / 'godot/generated')
    args = parser.parse_args()
    for name, clips in {**GODOT_WEAPON_CLIPS, 'sas': AGENT_CLIPS, 'phoenix': AGENT_CLIPS}.items():
        doc, glb = read(args.assets / f'{name}.glb')
        assert {a['name'] for a in doc['animations']} == set(clips), name
        for clip in doc['animations']:
            assert clip['channels'] and clip['samplers']
            for sampler in clip['samplers']:
                t = glb.accessor(sampler['input']).ravel()
                assert t[0] == 0 and (np.diff(t) > 0).all()
                assert len(t) == len(glb.accessor(sampler['output']))
        print(f'{name}: {len(clips)} clips y {len(doc["skins"])} skin(s)')
        if args.quality_viewmodels and name in GODOT_WEAPON_CLIPS:
            verify_quality(doc, glb, bayonet=name == 'bayonet')
            verify_wrist_and_grip_limits(doc, glb, name)
            if name != 'bayonet':
                verify_grips(doc, glb, bolt_cycle=name == 'awp')
        if name == 'm4a4':
            rifle, = (p for mesh in doc['meshes'] for p in mesh['primitives']
                      if doc['materials'][p['material']]['name'] == 'weapon-color')
            uv = glb.accessor(rifle['attributes']['TEXCOORD_0'])
            assert (np.ptp(uv, axis=0) > .9).all(), 'M4A4 atlas UVs were not expanded'
        if name == 'awp':
            assert 'weapon-scope-color' in {mat['name'] for mat in doc['materials']}
        if name == 'bayonet':
            blade, = (surf for mesh in doc['meshes'] for surf in mesh['primitives']
                      if doc['materials'][surf['material']]['name'] == 'weapon-color')
            assert len(glb.accessor(blade['indices'])) == 2202 * 3
            slot = next(i for i, n in enumerate(doc['nodes']) if n['name'] == 'weapon_offset')
            joints = glb.accessor(blade['attributes']['JOINTS_0'])
            assert np.all(joints[:, 0] == doc['skins'][0]['joints'].index(slot))
    doc, _ = read(args.assets / 'dust2.glb')
    assert sum(len(m['primitives']) for m in doc['meshes']) == 691
    assert len(doc['images']) == 564
    parts = list(surfaces(*read(args.assets / 'dust2-physics.glb')))
    assert len(parts) == 37
    h = floor_height(parts, (15.67, .18, -3.19))
    assert -0.15 < h < .16, h
    print(f'Dust II: 691 superficies, 564 imágenes, 37 mallas físicas; suelo de spawn a {h:.3f} m')
    events = json.loads((args.assets / 'usp-s.json').read_text())
    assert events['silencer_detach'][-1][1] is False and events['silencer_attach'][-1][1] is True


if __name__ == '__main__':
    main()
