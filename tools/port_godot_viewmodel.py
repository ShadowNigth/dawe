#!/usr/bin/env python3
"""Convert the baked MultiRig SMD sources (not MDL) to skinned Godot GLBs."""
import argparse
from collections import defaultdict
import io
from pathlib import Path
import re
import shlex

import numpy as np
from PIL import Image

from build_godot_assets import Writer, animation, quaternion
from import_assets import ROOT, WEAPON_CLIPS

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
                geometry[material].append((int(bone), [float(s) for s in values]))
    return bones, frames, geometry


def build(folder, weapon, output):
    names, frames, _ = read_smd(folder / 'idle.smd')
    bind = frames[0]
    nodes, global_rest = [], []
    doc = dict(asset=dict(version='2.0', generator='Dawe viewmodel bridge'), scene=0,
               scenes=[dict(nodes=[0])], nodes=nodes, meshes=[], materials=[], textures=[], images=[])
    writer = Writer(doc)
    for i, (name, parent) in enumerate(names):
        p, r = bind[i]
        nodes.append(dict(name=name, translation=p.tolist(), rotation=quaternion(r).tolist()))
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
    by_piece = defaultdict(lambda: defaultdict(list))
    clips = set(WEAPON_CLIPS[weapon])
    for path in sorted(folder.glob('*.smd')):
        if path.stem in clips:
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
        for texture, vertices in groups.items():
            if texture not in materials:
                mat = len(materials)
                materials[texture] = mat
                png = io.BytesIO()
                with Image.open(folder / texture) as img:
                    img.convert('RGB').save(png, 'PNG')
                doc['images'].append(dict(bufferView=writer.view(png.getvalue()), mimeType='image/png'))
                doc['textures'].append(dict(source=mat))
                doc['materials'].append(dict(name=Path(texture).stem, pbrMetallicRoughness=dict(
                    baseColorTexture=dict(index=mat), metallicFactor=0, roughnessFactor=.85)))
            joints = np.zeros((len(vertices), 4), dtype=np.uint16)
            joints[:, 0] = [item[0] for item in vertices]
            weights = np.zeros((len(vertices), 4), dtype=np.float32)
            weights[:, 0] = 1
            data = np.array([item[1] for item in vertices])
            normals = data[:, 3:6] @ Y_UP.T
            normals /= np.maximum(1e-8, np.linalg.norm(normals, axis=1, keepdims=True))
            uv = data[:, 6:8].copy()
            uv[:, 1] = 1-uv[:, 1]
            attr = dict(POSITION=writer.accessor(data[:, :3] @ Y_UP.T * .0254, 'VEC3', bounds=True, target=34962),
                        NORMAL=writer.accessor(normals, 'VEC3', target=34962),
                        TEXCOORD_0=writer.accessor(uv, 'VEC2', target=34962),
                        JOINTS_0=writer.accessor(joints, 'VEC4', 5123, target=34962),
                        WEIGHTS_0=writer.accessor(weights, 'VEC4', target=34962))
            surfaces.append(dict(attributes=attr, material=materials[texture]))
        doc['scenes'][0]['nodes'].append(len(nodes))
        nodes.append(dict(name=piece, mesh=len(doc['meshes']), skin=0))
        doc['meshes'].append(dict(name=piece, primitives=surfaces))
    if not doc['meshes'] or ('Silencer' in by_piece) != (weapon == 'usp-s'):
        raise ValueError(f'Falta geometría de {weapon}')
    events = {}
    for clip in WEAPON_CLIPS[weapon]:
        other, frames, _ = read_smd(folder / f'{clip}.smd')
        if other != names or not frames:
            raise ValueError(f'Clip incompatible: {clip}')
        animation(writer, clip, list(range(len(names))), frames)
    if weapon == 'usp-s':
        qc = (folder / 'usp.qc').read_text()
        for name in ('silencer_attach', 'silencer_detach'):
            block = re.search(rf'\$sequence "{name}"[^{{]+{{([^}}]+)}}', qc)[1]
            events[name] = [(int(i) / 30, v == '0') for i, v in re.findall(r'event 5001 (\d+) "([01])"', block)]
            if len(events[name]) != 2:
                raise ValueError(f'Faltan los eventos del silenciador: {name}')
    # Use a boolean custom track in gameplay; preserve event timing in the sidecar.
    writer.save(output)
    if events:
        import json
        output.with_suffix('.json').write_text(json.dumps(events, indent=2) + '\n')
    print(f'{output.name}: {len(names)} huesos, {len(clips)} animaciones, {len(by_piece)} piezas')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--smd', type=Path, required=True)
    p.add_argument('--weapon', choices=WEAPON_CLIPS, required=True)
    p.add_argument('--output', type=Path, default=ROOT / 'godot/generated')
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / f'{args.weapon}.glb'
    if path.exists() or path.with_suffix('.json').exists():
        p.error(f'No se sobrescribe {path}')
    build(args.smd, args.weapon, path)


if __name__ == '__main__':
    main()
