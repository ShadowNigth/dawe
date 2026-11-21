#!/usr/bin/env python3
"""Publish the Cyberpunk arm mesh once; keep each weapon's own skin and clips."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import struct

from build_godot_preview import Pack


def load(path):
    raw = path.read_bytes()
    if raw[:8] != b'DAWVIS1\n':
        raise ValueError(f'Archivo visual inválido: {path}')
    size, = struct.unpack_from('<I', raw, 8)
    return json.loads(raw[12:12+size]), memoryview(raw)[12+size:]


def partition(doc, source, box, is_arm):
    # The visual format can reuse ranges across animation tracks. Preserve that
    # sharing when relocating the binary data to another file.
    ranges, materials, textures = {}, {}, {}
    def move(where):
        offset, size = where
        if (offset, size) not in ranges:
            ranges[offset, size] = box.put(bytes(source[offset:offset+size]))
        return ranges[offset, size]

    def move_tex(idx):
        if idx not in textures:
            textures[idx] = len(box.info['textures'])
            box.info['textures'].append(move(doc['textures'][idx]))
        return textures[idx]

    def move_material(idx):
        if idx not in materials:
            value = deepcopy(doc['materials'][idx])
            for key in ('texture', 'normal', 'orm'):
                if value.get(key, -1) >= 0:
                    value[key] = move_tex(value[key])
            materials[idx] = len(box.info['materials'])
            box.info['materials'].append(value)
        return materials[idx]

    arms = [m for m in doc['meshes'] if m['name'] == 'CyberpunkArms']
    if len(arms) != 1:
        raise ValueError(f'{doc["name"]}: se esperaba una sola malla compartida')
    for mesh in (arms if is_arm else [m for m in doc['meshes'] if m not in arms]):
        surfaces = [{k: move_material(v) if k == 'mat' else move(v) for k, v in surf.items()} for surf in mesh['surfaces']]
        box.info['meshes'].append(dict(name=mesh['name'], skin=-1 if is_arm else mesh['skin'], surfaces=surfaces))
    if not is_arm:
        box.info['shared_arms_skin'] = arms[0]['skin']
        box.info['bones'] = doc['bones']
        box.info['skins'] = [dict(bones=s['bones'], inverse=move(s['inverse'])) for s in doc['skins']]
        box.info['clips'] = [dict(name=c['name'], length=c['length'], tracks=[[n, r, move(t), move(v)] for n, r, t, v in c['tracks']])
                             for c in doc['clips']]


def build(source, output):
    output.mkdir(parents=True, exist_ok=True)
    shared = None
    for path in sorted(source.glob('*.vis')):
        if path.stem.endswith('-drop') or path.stem == 'cyberpunk-arms':
            continue
        doc, data = load(path)
        arms = Pack('CyberpunkArms')
        partition(doc, data, arms, True)
        if shared is None:
            shared = arms
            arms.save(output/'cyberpunk-arms.vis')
        elif shared.info != arms.info or shared.payload != arms.payload:
            raise ValueError(f'La geometría de los brazos no coincide: {path.name}')
        part = Pack(doc['name'])
        partition(doc, data, part, False)
        part.save(output/path.name)
    if shared is None:
        raise ValueError('No hay armas para compartir')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('Se necesitan carpetas separadas')
    build(args.source, args.output)
