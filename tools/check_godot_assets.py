#!/usr/bin/env python3
"""Verify local Godot asset packs: GLB accessors, clip sets, and Outside Long floor."""
import argparse
import json
from pathlib import Path
import struct

import numpy as np

from build_agents import GLTF, rotation
from import_assets import AGENT_CLIPS, ROOT, WEAPON_CLIPS


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, default=ROOT / 'godot/generated')
    args = parser.parse_args()
    for name, clips in {**WEAPON_CLIPS, 'sas': AGENT_CLIPS, 'phoenix': AGENT_CLIPS}.items():
        doc, glb = read(args.assets / f'{name}.glb')
        assert {a['name'] for a in doc['animations']} == set(clips), name
        for clip in doc['animations']:
            assert clip['channels'] and clip['samplers']
            for sampler in clip['samplers']:
                t = glb.accessor(sampler['input']).ravel()
                assert t[0] == 0 and (np.diff(t) > 0).all()
                assert len(t) == len(glb.accessor(sampler['output']))
        print(f'{name}: {len(clips)} clips y {len(doc["skins"])} skin(s)')
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
