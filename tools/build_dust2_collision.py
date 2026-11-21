#!/usr/bin/env python3
"""Bake the Dust II movement geometry into a renderer-independent Godot cache."""
import argparse
import struct
from pathlib import Path

import numpy as np

from build_agents import rotation
from check_godot_assets import read
from import_assets import ROOT

MAGIC = b'DAWCOL1\n'


def collision_parts(doc, glb):
    def visit(i, parent, flags):
        node = doc['nodes'][i]
        flags = set(node.get('extras', {}).get('InteractAs', [])) or flags
        if flags & {'sky', 'csgo_grenadeclip'}:
            return
        if 'matrix' in node:
            local = np.array(node['matrix']).reshape(4, 4).T
        else:
            local = np.eye(4)
            local[:3, :3] = rotation(node.get('rotation', [0, 0, 0, 1])) * node.get('scale', [1, 1, 1])
            local[:3, 3] = node.get('translation', [0, 0, 0])
        world = parent @ local
        for prim in doc['meshes'][node['mesh']]['primitives'] if 'mesh' in node else []:
            if prim.get('mode', 4) != 4:
                raise ValueError('Collision mesh must contain triangles')
            xyz = glb.accessor(prim['attributes']['POSITION'])
            pos = xyz @ world[:3, :3].T + world[:3, 3]
            indices = glb.accessor(prim['indices']).reshape(-1, 3) if 'indices' in prim else np.arange(len(pos)).reshape(-1, 3)
            # Godot rendering/physics uses clockwise front faces, glTF uses CCW.
            if np.linalg.det(world[:3, :3]) > 0:
                indices = indices[:, [0, 2, 1]]
            faces = pos[indices]
            assert np.isfinite(faces).all()
            keep = np.any(np.cross(faces[:, 1]-faces[:, 0], faces[:, 2]-faces[:, 0]) != 0, axis=1)
            if keep.any():
                yield bool(flags & {'npcclip', 'playerclip'}), faces[keep].astype('<f4')
        for child in node.get('children', []):
            yield from visit(child, world, flags)
    for root in doc['scenes'][doc.get('scene', 0)]['nodes']:
        yield from visit(root, np.eye(4), set())


def partition(parts, cell_size=12.0):
    """Keep whole triangles; split the AABBs for physics and diagnostic rendering."""
    for clip in (False, True):
        group = [triangle for is_clip, triangle in parts if is_clip == clip]
        if not group:
            continue
        triangles = np.concatenate(group, axis=0)
        cells = np.floor(triangles.mean(axis=1)[:, [0, 2]] / cell_size).astype(np.int32)
        order = np.lexsort(cells.T)
        edges = np.flatnonzero(np.any(cells[order[1:]] != cells[order[:-1]], axis=1)) + 1
        for indexes in np.split(order, edges):
            yield clip, triangles[indexes]


def build(glb, output):
    parts = list(partition(list(collision_parts(*read(glb)))))
    if not 0 < len(parts) <= 512:
        raise ValueError('Cantidad inválida de celdas de colisión')
    temp = output.with_suffix('.tmp')
    with temp.open('wb') as handle:
        handle.write(MAGIC + struct.pack('<I', len(parts)))
        for clip, triangles in parts:
            handle.write(struct.pack('<II', int(clip), triangles.size // 3))
            handle.write(triangles.tobytes())
    temp.replace(output)
    print(f'{output.name}: {len(parts)} partes, {sum(len(part) for _, part in parts):,} triángulos')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--assets', type=Path, default=ROOT/'godot/generated')
    args = p.parse_args()
    build(args.assets/'dust2-physics.glb', args.assets/'dust2-collision.bin')


if __name__ == '__main__':
    main()
