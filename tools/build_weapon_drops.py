#!/usr/bin/env python3
"""Bake small static pickup models from the viewmodels without their arms or rigs."""
import argparse
import io
from pathlib import Path
import tempfile

import numpy as np
from PIL import Image
from build_godot_assets import Writer
from build_godot_preview import bake
from check_godot_assets import read
from import_assets import GODOT_WEAPON_CLIPS, ROOT


def build(source, output):
    original, model = read(source)
    surfaces = [(mesh['name'], p) for mesh in original['meshes'] for p in mesh['primitives']
                if original['materials'][p['material']]['name'].startswith('weapon-')]
    vertices = [model.accessor(p['attributes']['POSITION']) for _, p in surfaces]
    points = np.concatenate(vertices)
    offset = (points.max(axis=0) + points.min(axis=0))*0.5
    doc = dict(asset=dict(version='2.0'), scene=0, scenes=[dict(nodes=[])], nodes=[], meshes=[], materials=[])
    writer = Writer(doc)
    doc['images'], doc['textures'] = [], []
    materials = {}
    for _, prim in surfaces:
        material_id = prim['material']
        if material_id in materials:
            continue
        material = original['materials'][material_id]
        texture = original['textures'][material['pbrMetallicRoughness']['baseColorTexture']['index']]
        image = original['images'][texture['source']]
        with Image.open(io.BytesIO(model.view(image['bufferView']))) as paint:
            paint.thumbnail((256, 256), Image.Resampling.LANCZOS)
            png = io.BytesIO()
            paint.convert('RGB').save(png, 'PNG', optimize=True)
        loc = len(doc['images'])
        doc['images'].append(dict(bufferView=writer.view(png.getvalue()), mimeType='image/png'))
        doc['textures'].append(dict(source=loc))
        doc['materials'].append(dict(pbrMetallicRoughness=dict(baseColorTexture=dict(index=loc))))
        materials[material_id] = loc
    for (name, prim), pos in zip(surfaces, vertices):
        attrs = {}
        for semantic, kind in [('POSITION','VEC3'), ('NORMAL','VEC3'), ('TEXCOORD_0','VEC2')]:
            values = pos-offset if semantic == 'POSITION' else model.accessor(prim['attributes'][semantic])
            attrs[semantic] = writer.accessor(values, kind, bounds=semantic=='POSITION', target=34962)
        indices = writer.accessor(model.accessor(prim['indices']).ravel(), 'SCALAR', 5125, target=34963)
        idx = len(doc['nodes'])
        doc['meshes'].append(dict(name=name, primitives=[dict(attributes=attrs, indices=indices, material=materials[prim['material']])]))
        doc['nodes'].append(dict(name=name, mesh=idx))
        doc['scenes'][0]['nodes'].append(idx)
    with tempfile.TemporaryDirectory(prefix='dawe-drop-') as tmp:
        glb = Path(tmp)/'drop.glb'
        writer.save(glb)
        bake(glb, output, output.stem)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--assets', type=Path, default=ROOT/'godot/generated')
    args = p.parse_args()
    for name in GODOT_WEAPON_CLIPS:
        build(args.assets/f'{name}.glb', args.assets/f'{name}-drop.vis')


if __name__ == '__main__':
    main()
