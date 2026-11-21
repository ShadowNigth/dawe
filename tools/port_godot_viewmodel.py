#!/usr/bin/env python3
"""Convert the MultiRig bake to Godot GLBs, preserving smooth skins and PBR."""
import argparse
from collections import defaultdict
import io
import json
from pathlib import Path
import re
import shlex

import numpy as np
from PIL import Image

from build_godot_assets import Writer, animation, quaternion
from import_assets import ROOT, GODOT_WEAPON_CLIPS

# GoldSrc export to camera-local Godot, Y up and -Z forward. Both meshes
# and the local bind/animation transforms use the same change of basis.
Y_UP = np.array(((0., -1., 0.), (0., 0., 1.), (-1., 0., 0.)))


def euler(x, y, z):
    sx, sy, sz = np.sin((x, y, z))
    cx, cy, cz = np.cos((x, y, z))
    return np.array(((cy*cz, sx*sy*cz-cx*sz, cx*sy*cz+sx*sz),
                     (cy*sz, sx*sy*sz+cx*cz, cx*sy*sz-sx*cz), (-sy, sx*cy, cx*cy)))


def read_smd(path):
    lines = iter(path.read_text().splitlines())
    if next(lines) != 'version 1' or next(lines) != 'nodes':
        raise ValueError(f'Formato SMD inesperado: {path}')
    bones = []
    for line in iter(lambda: next(lines), 'end'):
        index, name, parent = shlex.split(line)
        assert int(index) == len(bones)
        bones.append((name, int(parent)))
    assert next(lines) == 'skeleton'
    frames = []
    for line in iter(lambda: next(lines), 'end'):
        if line.startswith('time '):
            assert int(line.split()[1]) == len(frames)
            frames.append([])
        else:
            bone, *values = line.split()
            assert int(bone) == len(frames[-1])
            x, y, z, rx, ry, rz = map(float, values)
            frames[-1].append((Y_UP @ (x, y, z) * .0254, Y_UP @ euler(rx, ry, rz) @ Y_UP.T))
    geometry = defaultdict(list)
    if next(lines, '') == 'triangles':
        for material in iter(lambda: next(lines), 'end'):
            for _ in range(3):
                bone, *values = next(lines).split()
                geom = tuple(map(float, values[:8]))
                if len(values) > 8:
                    count = int(values[8])
                    links = tuple((int(i), float(w)) for i, w in zip(values[9::2], values[10::2]))
                    if not 1 <= count == len(links) <= 4 or len(values) != 9 + 2*count:
                        raise ValueError(f'Pesos SMD inválidos: {path}')
                else:
                    links = ((int(bone), 1.0),)
                geometry[material].append((links, geom))
    return bones, frames, geometry


def tangent_frame(pos, uv, normals, indices):
    """Accumulate UV tangents across matching indexed corners, including sign."""
    tri = np.asarray(indices).reshape(-1, 3)
    e1, e2 = pos[tri[:, 1]] - pos[tri[:, 0]], pos[tri[:, 2]] - pos[tri[:, 0]]
    uv1, uv2 = uv[tri[:, 1]] - uv[tri[:, 0]], uv[tri[:, 2]] - uv[tri[:, 0]]
    det = uv1[:, 0]*uv2[:, 1] - uv1[:, 1]*uv2[:, 0]
    inv = np.divide(1, det, out=np.zeros_like(det), where=np.abs(det) > 1e-12)[:, None]
    t = (e1*uv2[:, 1, None] - e2*uv1[:, 1, None]) * inv
    b = (e2*uv1[:, 0, None] - e1*uv2[:, 0, None]) * inv
    tangent, bitangent = np.zeros_like(normals), np.zeros_like(normals)
    for idxs in tri.T:
        np.add.at(tangent, idxs, t)
        np.add.at(bitangent, idxs, b)
    tangent -= normals * np.sum(normals*tangent, axis=1, keepdims=True)
    norm = np.linalg.norm(tangent, axis=1, keepdims=True)
    axis = np.eye(3)[np.argmin(np.abs(normals), axis=1)]
    tangent = np.where(norm > 1e-10, tangent, np.cross(axis, normals))
    tangent /= np.maximum(1e-12, np.linalg.norm(tangent, axis=1, keepdims=True))
    sign = np.where(np.sum(np.cross(normals, tangent)*bitangent, axis=1) < 0, -1, 1)
    return np.column_stack((tangent, sign))


def build(folder, weapon, output):
    names, frames, _ = read_smd(folder / ('idle1.smd' if weapon == 'bayonet' else 'idle.smd'))
    initial = frames[0]
    bind_path = folder / 'skin_bind.smd'
    if bind_path.exists():
        bind_names, bind_frames, _ = read_smd(bind_path)
        if names != bind_names:
            raise ValueError('Esqueleto de referencia incompatible')
        bind = bind_frames[0]
    else:
        bind = initial
    mat_path = folder / 'materials.json'
    mat_specs = json.loads(mat_path.read_text()) if mat_path.exists() else {}
    nodes, global_rest = [], []
    doc = dict(asset=dict(version='2.0', generator='Dawe viewmodel bridge'), scene=0,
               scenes=[dict(nodes=[0])], nodes=nodes, meshes=[], materials=[], textures=[], images=[])
    writer = Writer(doc)
    for i, (name, parent) in enumerate(names):
        p, r = bind[i]
        ip, ir = initial[i]
        nodes.append(dict(name=name, translation=ip.tolist(), rotation=quaternion(ir).tolist()))
        local = np.eye(4)
        local[:3, :3], local[:3, 3] = r, p
        if parent >= 0:
            nodes[parent].setdefault('children', []).append(i)
            local = global_rest[parent] @ local
        global_rest.append(local)
    inv = np.linalg.inv(np.array(global_rest)).transpose(0, 2, 1)
    doc['skins'] = [dict(joints=list(range(len(names))), skeleton=0,
                         inverseBindMatrices=writer.accessor(inv, 'MAT4'))]
    materials = {}
    textures = {}

    def texture(file):
        if file not in textures:
            png = io.BytesIO()
            with Image.open(folder / file) as img:
                img.convert('RGB').save(png, 'PNG')
            texture_id = len(doc['textures'])
            textures[file] = texture_id
            doc['images'].append(dict(bufferView=writer.view(png.getvalue()), mimeType='image/png'))
            doc['textures'].append(dict(source=texture_id))
        return dict(index=textures[file])
    by_piece = defaultdict(lambda: defaultdict(list))
    clips = set(GODOT_WEAPON_CLIPS[weapon])
    for path in sorted(folder.glob('*.smd')):
        if path.stem in clips or path == bind_path:
            continue
        mesh_names, mesh_bind, geometry = read_smd(path)
        if names != mesh_names or any(not np.allclose(p1, p2) or not np.allclose(r1, r2)
                                      for (p1, r1), (p2, r2) in zip(bind, mesh_bind[0])):
            raise ValueError(f'Esqueleto o bind inesperado: {path}')
        piece = 'Silencer' if path.stem == 'silencer_mesh' else 'ArmsAndWeapon'
        for tex, vertices in geometry.items():
            by_piece[piece][tex].extend(vertices)
    for piece, groups in by_piece.items():
        surfaces = []
        for texture_file, vertices in groups.items():
            if texture_file not in materials:
                mat = len(materials)
                materials[texture_file] = mat
                spec = mat_specs.get(texture_file, {})
                pbr = dict(baseColorTexture=texture(texture_file), metallicFactor=spec.get('metallic', 0),
                           roughnessFactor=spec.get('roughness', .85))
                mat_info = dict(name=Path(texture_file).stem, pbrMetallicRoughness=pbr)
                if spec.get('orm'):
                    pbr['metallicRoughnessTexture'] = texture(spec['orm'])
                    mat_info['occlusionTexture'] = texture(spec['orm'])
                if spec.get('normal'):
                    mat_info['normalTexture'] = texture(spec['normal'])
                doc['materials'].append(mat_info)
            # Keep indexed vertices; don't collapse UV, normal or weight seams.
            unique = {}
            indexes = []
            for vertex in vertices:
                indexes.append(unique.setdefault(vertex, len(unique)))
            vertices = list(unique)
            joints = np.zeros((len(vertices), 4), dtype=np.uint16)
            weights = np.zeros((len(vertices), 4), dtype=np.float32)
            for i, (links, _) in enumerate(vertices):
                for k, (bone, weight) in enumerate(links):
                    if not 0 <= bone < len(names) or not 0 < weight <= 1:
                        raise ValueError(f'Influencia inválida del hueso {bone}')
                    joints[i, k], weights[i, k] = bone, weight
            weights /= weights.sum(axis=1, keepdims=True)
            data = np.array([item[1] for item in vertices])
            normals = data[:, 3:6] @ Y_UP.T
            normals /= np.maximum(1e-8, np.linalg.norm(normals, axis=1, keepdims=True))
            uv = data[:, 6:8].copy()
            uv[:, 1] = 1-uv[:, 1]
            positions = data[:, :3] @ Y_UP.T * .0254
            attr = dict(POSITION=writer.accessor(positions, 'VEC3', bounds=True, target=34962),
                        NORMAL=writer.accessor(normals, 'VEC3', target=34962),
                        TEXCOORD_0=writer.accessor(uv, 'VEC2', target=34962),
                        JOINTS_0=writer.accessor(joints, 'VEC4', 5123, target=34962),
                        WEIGHTS_0=writer.accessor(weights, 'VEC4', target=34962))
            if mat_specs.get(texture_file, {}).get('normal'):
                attr['TANGENT'] = writer.accessor(tangent_frame(positions, uv, normals, indexes), 'VEC4', target=34962)
            surfaces.append(dict(attributes=attr, material=materials[texture_file],
                                 indices=writer.accessor(indexes, 'SCALAR', 5125, target=34963)))
        doc['scenes'][0]['nodes'].append(len(nodes))
        nodes.append(dict(name=piece, mesh=len(doc['meshes']), skin=0))
        doc['meshes'].append(dict(name=piece, primitives=surfaces))
    if not doc['meshes'] or ('Silencer' in by_piece) != (weapon == 'usp-s'):
        raise ValueError(f'Falta geometría de {weapon}')
    events = {}
    for clip in GODOT_WEAPON_CLIPS[weapon]:
        other, frames, _ = read_smd(folder / f'{clip}.smd')
        if other != names or not frames:
            raise ValueError(f'Clip incompatible: {clip}')
        animation(writer, clip, list(range(len(names))), frames)
    if weapon == 'usp-s':
        event_path = folder / 'silencer-events.json'
        if event_path.exists():
            events = json.loads(event_path.read_text())
        else:
            qc = (folder / 'usp.qc').read_text()
            for name in ('silencer_attach', 'silencer_detach'):
                block = re.search(rf'\$sequence "{name}"[^{{]+{{([^}}]+)}}', qc)[1]
                events[name] = [(int(i) / 30, v == '0') for i, v in re.findall(r'event 5001 (\d+) "([01])"', block)]
        for clip, initial_visible in (('silencer_attach', False), ('silencer_detach', True)):
            sequence = events.get(clip, [])
            if (len(sequence) != 2 or sequence[0][0] != 0 or sequence[1][0] <= 0
                    or sequence[0][1] != initial_visible or sequence[1][1] == initial_visible):
                raise ValueError(f'Eventos inesperados del silenciador: {clip}')
    # Use a boolean custom track in gameplay; preserve event timing in the sidecar.
    writer.save(output)
    if events:
        output.with_suffix('.json').write_text(json.dumps(events, indent=2) + '\n')
    print(f'{output.name}: {len(names)} huesos, {len(clips)} animaciones, {len(by_piece)} piezas')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--smd', type=Path, required=True)
    p.add_argument('--weapon', choices=GODOT_WEAPON_CLIPS, required=True)
    p.add_argument('--output', type=Path, default=ROOT / 'godot/generated')
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / f'{args.weapon}.glb'
    if path.exists() or path.with_suffix('.json').exists():
        p.error(f'No se sobrescribe {path}')
    build(args.smd, args.weapon, path)


if __name__ == '__main__':
    main()
