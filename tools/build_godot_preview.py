#!/usr/bin/env python3
"""Bake small, renderer-ready packs for the Godot Web demo (local assets)."""
import argparse
import json
from pathlib import Path
import struct

import numpy as np

from build_agents import rotation
from check_godot_assets import read
from import_assets import ROOT

# X/Z metres, including Outside Long, the tunnel, exit and edge of Pit.
SECTOR = [1.0, -29.0, 44.0, 10.0]


class Pack:
    def __init__(self, name):
        self.info = dict(name=name, textures=[], materials=[], meshes=[])
        self.payload = bytearray()

    def put(self, array, dtype='<f4'):
        if not isinstance(array, bytes):
            array = np.ascontiguousarray(array, dtype=dtype).tobytes()
        offset = len(self.payload)
        self.payload.extend(array)
        return [offset, len(array)]

    def save(self, path):
        header = json.dumps(self.info, separators=(',', ':'), allow_nan=False).encode()
        tmp = path.with_suffix('.tmp')
        with tmp.open('wb') as file:
            file.write(b'DAWVIS1\n' + struct.pack('<I', len(header)))
            file.write(header)
            file.write(self.payload)
        tmp.replace(path)
        print(f'{path.name}: {len(self.info["meshes"])} meshes, {len(self.info["textures"])} textures, '
              f'{path.stat().st_size/2**20:.2f} MiB')


def matrix(node):
    if 'matrix' in node:
        return np.array(node['matrix']).reshape(4, 4).T
    result = np.eye(4)
    result[:3, :3] = rotation(node.get('rotation', [0, 0, 0, 1])) * node.get('scale', [1, 1, 1])
    result[:3, 3] = node.get('translation', [0, 0, 0])
    return result


def uv_map(uv, spec):
    uv = uv * spec.get('scale', [1, 1])
    angle = spec.get('rotation', 0)
    if angle:
        c, s = np.cos(angle), np.sin(angle)
        uv = uv @ np.array(((c, s), (-s, c)))
    return uv + spec.get('offset', [0, 0])


def bake(source, output, name):
    doc, glb = read(source)
    pack = Pack(name)
    image_ids, material_ids = {}, {}
    map_sector = name == 'dust2-long'
    if map_sector:
        pack.info['bounds'] = SECTOR
    skins = doc.get('skins', [])
    if skins:
        bake_rig(pack, doc, glb)

    def material(i):
        if i in material_ids:
            return material_ids[i]
        value = doc['materials'][i]
        pbr = value.get('pbrMetallicRoughness', {})
        tex = pbr.get('baseColorTexture')
        img = -1
        repeat = True
        if tex:
            texture = doc['textures'][tex['index']]
            img = texture['source']
            if img not in image_ids:
                image_ids[img] = len(pack.info['textures'])
                pack.info['textures'].append(pack.put(bytes(glb.view(doc['images'][img]['bufferView']))))
            repeat = doc.get('samplers', [{}])[texture.get('sampler', 0)].get('wrapS', 10497) != 33071
            img = image_ids[img]
        idx = len(pack.info['materials'])
        material_ids[i] = idx
        pack.info['materials'].append(dict(texture=img, alpha=value.get('alphaMode', 'OPAQUE'),
                                           cutoff=value.get('alphaCutoff', .5), repeat=repeat,
                                           two_sided=value.get('doubleSided', False),
                                           color=pbr.get('baseColorFactor', [1]*4)))
        return idx

    def visit(i, ancestor):
        node = doc['nodes'][i]
        pose = ancestor @ matrix(node)
        if 'mesh' in node:
            mesh = dict(name=node['name'], skin=node.get('skin', -1), surfaces=[])
            if mesh['skin'] >= 0 and not np.allclose(pose, np.eye(4), atol=1e-5):
                raise ValueError('Se esperaba la malla skinned en el origen')
            for prim in doc['meshes'][node['mesh']]['primitives']:
                if prim.get('mode', 4) != 4:
                    raise ValueError('Se requieren triángulos')
                attrs = prim['attributes']
                pos = glb.accessor(attrs['POSITION']) @ pose[:3, :3].T + pose[:3, 3]
                tris = (glb.accessor(prim['indices']).ravel() if 'indices' in prim else np.arange(len(pos))).reshape(-1, 3)
                if map_sector:
                    lo_x, lo_z, hi_x, hi_z = SECTOR
                    xyz = pos[tris]
                    low, high = xyz.min(axis=1), xyz.max(axis=1)
                    tris = tris[(high[:, 0] >= lo_x) & (low[:, 0] <= hi_x) &
                                (high[:, 2] >= lo_z) & (low[:, 2] <= hi_z)]
                    if not len(tris):
                        continue
                if np.linalg.det(pose[:3, :3]) > 0:
                    tris = tris[:, [0, 2, 1]]  # glTF CCW -> Godot CW
                selected, indices = np.unique(tris, return_inverse=True)
                normal = glb.accessor(attrs['NORMAL'])[selected] @ np.linalg.inv(pose[:3, :3])
                normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-8)
                tex = doc['materials'][prim['material']].get('pbrMetallicRoughness', {}).get('baseColorTexture', {})
                uv_spec = tex.get('extensions', {}).get('KHR_texture_transform', {})
                uv_id = attrs.get(f'TEXCOORD_{uv_spec.get("texCoord", tex.get("texCoord", 0))}')
                uv = uv_map(glb.accessor(uv_id)[selected], uv_spec) if uv_id is not None else np.zeros((len(selected), 2))
                surface = dict(mat=material(prim['material']), pos=pack.put(pos[selected]),
                               normals=pack.put(normal), uv=pack.put(uv), idx=pack.put(indices, '<i4'))
                if mesh['skin'] >= 0:
                    if 'JOINTS_1' in attrs:
                        raise ValueError('La previsualización admite cuatro influencias por vértice')
                    surface.update(joints=pack.put(glb.accessor(attrs['JOINTS_0'])[selected], '<i4'),
                                   weights=pack.put(glb.accessor(attrs['WEIGHTS_0'])[selected]))
                mesh['surfaces'].append(surface)
            if mesh['surfaces']:
                pack.info['meshes'].append(mesh)
        if map_sector:
            for child in node.get('children', []):
                visit(child, pose)

    for root in doc['scenes'][doc.get('scene', 0)]['nodes']:
        visit(root, np.eye(4))
    pack.save(output)


def bake_rig(pack, doc, glb):
    nodes = doc['nodes']
    skins = doc['skins']
    joints = {j for skin in skins for j in skin['joints']}
    parents = {child: i for i, item in enumerate(nodes) for child in item.get('children', [])}
    order = []

    def visit(i):
        if i in joints:
            order.append(i)
        for child in nodes[i].get('children', []):
            visit(child)

    for root in doc['scenes'][doc.get('scene', 0)]['nodes']:
        visit(root)
    idxs = {j: i for i, j in enumerate(order)}
    if set(order) != joints or len(order) != len(joints):
        raise ValueError('Jerarquía de huesos inválida')
    pack.info['bones'] = []
    for i in order:
        item = nodes[i]
        parent = parents.get(i)
        if parent is not None and parent not in joints:
            if parent in parents or not np.allclose(matrix(nodes[parent]), np.eye(4), atol=1e-5):
                raise ValueError('El padre externo al skin debe ser identidad')
        pack.info['bones'].append(dict(name=item['name'], parent=idxs.get(parent, -1),
                                       pos=item.get('translation', [0, 0, 0]),
                                       rot=item.get('rotation', [0, 0, 0, 1]),
                                       scale=item.get('scale', [1, 1, 1])))
    pack.info['skins'] = [dict(bones=[idxs[j] for j in skin['joints']],
                               inverse=pack.put(glb.accessor(skin['inverseBindMatrices']))) for skin in skins]
    pack.info['clips'] = []
    time_cache = {}
    for anim in doc['animations']:
        clip = dict(name=anim['name'], length=.01, tracks=[])
        for channel in anim['channels']:
            node, path = channel['target']['node'], channel['target']['path']
            track = anim['samplers'][channel['sampler']]
            assert path in ('translation', 'rotation') and track.get('interpolation', 'LINEAR') == 'LINEAR'
            ts = glb.accessor(track['input'])
            key = glb.accessor(track['output'])
            clip['length'] = max(clip['length'], float(ts[-1, 0]))
            if np.allclose(key, key[0], atol=1e-6):
                ts, key = ts[:1], key[:1]
            time_key = (track['input'], len(ts))
            if time_key not in time_cache:
                time_cache[time_key] = pack.put(ts)
            clip['tracks'].append([idxs[node], path == 'rotation', time_cache[time_key], pack.put(key)])
        pack.info['clips'].append(clip)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--assets', type=Path, default=ROOT / 'godot/generated')
    args = p.parse_args()
    for name in ('dust2-long', 'sas', 'phoenix', 'usp-s', 'ak-47'):
        filename = 'dust2' if name == 'dust2-long' else name
        bake(args.assets / f'{filename}.glb', args.assets / f'{name}.vis', name)


if __name__ == '__main__':
    main()
