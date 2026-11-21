#!/usr/bin/env python3
"""Prepare standard glTF assets for Godot 4 (local third-party files only)."""
import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

import numpy as np
from PIL import Image

from build_agents import GLTF, FPS, skeleton, take_clip
from build_dust2_collision import build as build_collision
from import_assets import AGENTS, AGENT_CLIPS, ROOT


class Writer:
    def __init__(self, doc, binary=b''):
        self.doc = doc
        self.bin = bytearray(binary)

    def view(self, data, target=None):
        self.bin.extend(b'\0' * (-len(self.bin) % 4))
        views = self.doc.setdefault('bufferViews', [])
        view = dict(buffer=0, byteOffset=len(self.bin), byteLength=len(data))
        if target:
            view['target'] = target
        views.append(view)
        self.bin.extend(data)
        return len(views) - 1

    def accessor(self, data, shape, component=5126, *, bounds=False, target=None):
        dtype = {5126: '<f4', 5123: '<u2', 5125: '<u4'}[component]
        data = np.array(data, dtype=dtype)
        accessors = self.doc.setdefault('accessors', [])
        item = dict(bufferView=self.view(data.tobytes(), target), componentType=component,
                    count=len(data), type=shape)
        if bounds:
            arr = data.reshape(len(data), -1)
            item.update(min=arr.min(axis=0).tolist(), max=arr.max(axis=0).tolist())
        accessors.append(item)
        return len(accessors) - 1

    def save(self, path):
        self.bin.extend(b'\0' * (-len(self.bin) % 4))
        self.doc['buffers'] = [dict(byteLength=len(self.bin))]
        head = json.dumps(self.doc, separators=(',', ':'), allow_nan=False).encode()
        head += b' ' * (-len(head) % 4)
        with path.open('wb') as f:
            f.write(struct.pack('<4sIII4s', b'glTF', 2, 28 + len(head) + len(self.bin), len(head), b'JSON'))
            f.write(head)
            f.write(struct.pack('<I4s', len(self.bin), b'BIN\0'))
            f.write(self.bin)


def decode(path, node, decoder, work):
    doc, buf = work / 'data.json', work / 'data.bin'
    subprocess.run([node, str(decoder), str(path), str(doc), str(buf)], check=True)
    result = json.loads(doc.read_text())
    # Only skeletons require unique names. Static exports can have anonymous nodes.
    for i, value in enumerate(result['nodes']):
        value.setdefault('name', f'node_{i}')
    binary = buf.read_bytes()
    return result, binary


def quaternion(r):
    """Rotation matrix to unit glTF quaternion (x,y,z,w)."""
    squares = np.array([1+2*r[i, i]-np.trace(r) for i in range(3)] + [1+np.trace(r)])
    k = np.argmax(squares)
    v = np.empty(4)
    v[k] = np.sqrt(squares[k]) / 2
    if k == 3:
        v[:3] = [r[2, 1]-r[1, 2], r[0, 2]-r[2, 0], r[1, 0]-r[0, 1]]
        v[:3] /= 4*v[k]
    else:
        j, l = (k+1) % 3, (k+2) % 3
        v[j] = (r[j, k]+r[k, j]) / (4*v[k])
        v[l] = (r[l, k]+r[k, l]) / (4*v[k])
        v[3] = (r[l, j]-r[j, l]) / (4*v[k])
    return v / np.linalg.norm(v)


def animation(writer, name, ids, frames):
    positions = np.array([[pair[0] for pair in frame] for frame in frames])
    rotations = np.array([[quaternion(pair[1]) for pair in frame] for frame in frames])
    t = writer.accessor(np.arange(len(frames))/FPS, 'SCALAR', bounds=True)
    clip = dict(name=name, samplers=[], channels=[])
    for path, pose in [('translation', positions), ('rotation', rotations)]:
        for k, joint in enumerate(ids):
            track = pose[:, k].copy()
            if path == 'rotation':
                for i in range(1, len(track)):
                    if track[i-1] @ track[i] < 0:
                        track[i] *= -1
            acc = writer.accessor(track, 'VEC3' if path == 'translation' else 'VEC4')
            clip['channels'].append(dict(sampler=len(clip['samplers']), target=dict(node=joint, path=path)))
            clip['samplers'].append(dict(input=t, output=acc, interpolation='LINEAR'))
    writer.doc.setdefault('animations', []).append(clip)


def texture_png(data, mime, basis, work, limit):
    key = hashlib.sha256(data).hexdigest()
    with tempfile.TemporaryDirectory(prefix='basis-', dir=work) as temp:
        temp = Path(temp)
        if mime == 'image/ktx2':
            (temp / 'source.ktx2').write_bytes(data)
            # BC3/ETC2 exports a combined RGBA PNG when the source has alpha.
            env = dict(os.environ, OMP_NUM_THREADS='1')
            res = subprocess.run([basis, '-unpack', '-file', 'source.ktx2', '-format_only', '1',
                                  '-no_ktx'], cwd=temp, env=env, capture_output=True, text=True)
            paths = list(temp.glob('*_unpacked_rgba_*_0_0_0000.png'))
            paths = paths or list(temp.glob('*_unpacked_rgb_*_0_0_0000.png'))
            if res.returncode or not paths:
                raise RuntimeError(f'Basis no pudo decodificar {key[:12]}: {res.stdout[-800:]} {res.stderr[-800:]}')
            data = paths[0].read_bytes()
        with Image.open(io.BytesIO(data)) as image:
            image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
            image.thumbnail((limit, limit), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            image.save(out, 'PNG', compress_level=2)
            return out.getvalue()


def normalize(src, target, args, work, kind, bank=None):
    original, blob = decode(src, args.node, args.decoder, work)
    # Accessors don't depend on node names when converting static meshes.
    source = GLTF(original if kind == 'agent' else dict(original, nodes=[]), blob)
    doc = copy.deepcopy(original)
    doc['asset']['generator'] = 'Dawe Godot asset builder'
    writer = Writer(doc, blob)
    for view in doc['bufferViews']:
        if not view.get('extensions'):
            view.pop('extensions', None)
    for keyword in ('extensionsUsed', 'extensionsRequired'):
        supported = [x for x in doc.get(keyword, [])
                     if x not in ('EXT_meshopt_compression', 'KHR_texture_basisu', 'KHR_mesh_quantization')]
        if supported:
            doc[keyword] = supported
        else:
            doc.pop(keyword, None)
    converted = {}
    for mesh in doc['meshes']:
        for prim in mesh['primitives']:
            # Source-specific per-vertex lighting channels are not consumed by
            # Godot's glTF material importer. COLOR_0 remains intact.
            if kind == 'map':
                for attr in ('COLOR_1', 'COLOR_2', 'COLOR_3', 'COLOR_4'):
                    prim['attributes'].pop(attr, None)
            for attributes in [prim['attributes'], *prim.get('targets', [])]:
                for attr, index in attributes.items():
                    a = doc['accessors'][index]
                    if a['componentType'] == 5126:
                        # Lossy Meshopt filters can change extrema after decoding.
                        if index not in converted and (attr == 'POSITION' or 'min' in a or 'max' in a):
                            values = source.accessor(index)
                            a.update(min=values.min(axis=0).tolist(), max=values.max(axis=0).tolist())
                            converted[index] = index
                        continue
                    if attr.startswith('JOINTS'):
                        continue
                    if index not in converted:
                        converted[index] = writer.accessor(source.accessor(index), a['type'],
                                                           bounds=attr == 'POSITION', target=34962)
                    attributes[attr] = converted[index]
    if kind == 'map':
        # Split the map's hundreds of primitives into separate ArrayMeshes.
        mesh, = doc['meshes']
        root, = doc['nodes']
        scene = doc['scenes'][doc.get('scene', 0)]
        root.pop('mesh')
        root['children'] = []
        doc['meshes'] = []
        for i in range(0, len(mesh['primitives']), 48):
            n = len(doc['meshes'])
            doc['meshes'].append(dict(name=f'Dust II {n+1}', primitives=mesh['primitives'][i:i+48]))
            root['children'].append(len(doc['nodes']))
            doc['nodes'].append(dict(mesh=n, name=f'Dust2_{n+1:02}'))
        assert scene['nodes'] == [0]
    elif kind == 'agent':
        ids, _, pose, mapping = skeleton(source, bank)
        animation(writer, 'idle', list(ids), [pose])
        for clip in bank.doc['animations']:
            animation(writer, clip['name'], list(ids), list(take_clip(bank, clip, pose, mapping)))
        assert {clip['name'] for clip in doc['animations']} == set(AGENT_CLIPS)
    images = doc.get('images', [])
    if images:
        limit = args.texture_size if kind == 'map' else max(args.texture_size, 512)
        def convert(img):
            return texture_png(bytes(source.view(img['bufferView'])), img['mimeType'], args.basisu, work, limit)
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for img, pixels in zip(images, pool.map(convert, images)):
                img.update(bufferView=writer.view(pixels), mimeType='image/png')
        for tex in doc['textures']:
            ext = tex.get('extensions', {}).pop('KHR_texture_basisu', None)
            if ext:
                tex['source'] = ext['source']
            if not tex.get('extensions'):
                tex.pop('extensions', None)
        print(f'{src.name}: {len(images)} imágenes PNG', flush=True)
    # Retain only referenced accessors, then pack the referenced buffer views.
    refs = []
    for mesh in doc['meshes']:
        for primitive in mesh['primitives']:
            refs.extend((primitive['attributes'], attr) for attr in primitive['attributes'])
            if 'indices' in primitive:
                refs.append((primitive, 'indices'))
            for target_attrs in primitive.get('targets', []):
                refs.extend((target_attrs, attr) for attr in target_attrs)
    refs.extend((skin, 'inverseBindMatrices') for skin in doc.get('skins', []) if 'inverseBindMatrices' in skin)
    refs.extend((sampler, key) for clip in doc.get('animations', []) for sampler in clip['samplers']
                for key in ('input', 'output'))
    referenced = sorted({obj[key] for obj, key in refs})
    remap_accessors = {idx: j for j, idx in enumerate(referenced)}
    doc['accessors'] = [doc['accessors'][idx] for idx in referenced]
    for obj, key in refs:
        obj[key] = remap_accessors[obj[key]]
    live = {a['bufferView'] for a in doc['accessors'] if 'bufferView' in a}
    live.update(i['bufferView'] for i in images)
    compact = Writer(dict(doc, bufferViews=[]))
    remap = {}
    for i in sorted(live):
        view = doc['bufferViews'][i]
        start = view.get('byteOffset', 0)
        j = compact.view(writer.bin[start:start+view['byteLength']], view.get('target'))
        if 'byteStride' in view:
            compact.doc['bufferViews'][j]['byteStride'] = view['byteStride']
        remap[i] = j
    for a in [*doc['accessors'], *images]:
        if 'bufferView' in a:
            a['bufferView'] = remap[a['bufferView']]
    compact.save(target)
    print(f'{target.name}: {target.stat().st_size/2**20:.1f} MiB', flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--assets', type=Path, default=ROOT / 'third_party_assets')
    p.add_argument('--output', type=Path, default=ROOT / 'godot/generated')
    p.add_argument('--basisu', default='basisu')
    p.add_argument('--node', default='node')
    p.add_argument('--texture-size', type=int, default=256, help='máximo por lado para Dust II')
    p.add_argument('--jobs', type=int, default=2)
    p.add_argument('--only', choices=['map', 'agents'], help='genera sólo ese grupo en un destino nuevo')
    args = p.parse_args()
    args.decoder = ROOT / 'tools/agent_assets/decode_meshopt.mjs'
    args.output = args.output.resolve()
    args.basisu = shutil.which(args.basisu)
    if args.output.exists() or not args.basisu or args.jobs < 1 or args.texture_size < 64:
        p.error('Se requiere destino nuevo, Basis Universal, jobs >= 1 y textura >= 64')
    cs = args.assets.resolve() / 'cs2go'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.godot-assets-', dir=args.output.parent) as tmp:
        work = Path(tmp)
        out = work / 'assets'
        out.mkdir()
        if args.only != 'agents':
            for name, kind in [('dust2', 'map'), ('dust2-physics', 'physics')]:
                normalize(cs / f'maps/{name}.glb', out / f'{name}.glb', args, work, kind)
            build_collision(out / 'dust2-physics.glb', out / 'dust2-collision.bin')
            for file in ('dust2-radar.png', 'dust2-nav.json', 'dust2-overview.json', 'dust2-places.json'):
                shutil.copyfile(cs / 'maps' / file, out / file)
        if args.only != 'map':
            bank = GLTF.animations(cs / 'animations/locomotion/diagonal.glb')
            for key, model in AGENTS.items():
                normalize(cs / f'agents/roster/{model}.glb', out / f'{key}.glb', args, work, 'agent', bank)
        out.rename(args.output)


if __name__ == '__main__':
    main()
