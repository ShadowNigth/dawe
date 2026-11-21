#!/usr/bin/env python3
"""Exporta SAS/Phoenix y el banco de locomoción de cs2go a QC/SMD/BMP."""
import argparse
import io
import math
from pathlib import Path
import struct
import subprocess
import tempfile
import json

import numpy as np
from PIL import Image

from import_assets import AGENTS, AGENT_CLIPS, ROOT

FPS = 30
INCH = 0.0254
STUDIO = np.array(((0, 0, 1), (1, 0, 0), (0, 1, 0)))  # glTF Y arriba -> estudio Z arriba
MAX_COMPONENTS = 960  # El renderer software de Xash limita cada pieza a 1024.


class GLTF:
    def __init__(self, doc, binary):
        self.doc, self.binary = doc, binary
        self.nodes = doc['nodes']
        self.names = {node['name']: i for i, node in enumerate(self.nodes)}
        self.parents = {child: i for i, node in enumerate(self.nodes) for child in node.get('children', [])}
        if len(self.names) != len(self.nodes):
            raise ValueError('El esqueleto tiene nombres de nodo duplicados')

    @classmethod
    def animations(cls, path):
        data = path.read_bytes()
        magic, version, total, length, kind = struct.unpack_from('<4sIII4s', data)
        if (magic, version, total, kind) != (b'glTF', 2, len(data), b'JSON'):
            raise ValueError(f'GLB inválido: {path}')
        start = 20 + length
        size, kind = struct.unpack_from('<I4s', data, start)
        if kind != b'BIN\0' or start + 8 + size != len(data):
            raise ValueError(f'Bloque BIN inválido: {path}')
        return cls(json.loads(data[20:start]), data[start+8:])

    @classmethod
    def roster(cls, path, work, node):
        helper = ROOT / 'tools/agent_assets/decode_meshopt.mjs'
        doc, binary = work / 'mesh.json', work / 'mesh.bin'
        subprocess.run([node, str(helper), str(path), str(doc), str(binary)], check=True)
        return cls(json.loads(doc.read_text()), binary.read_bytes())

    def view(self, index):
        view = self.doc['bufferViews'][index]
        start = view.get('byteOffset', 0)
        end = start + view['byteLength']
        if view['buffer'] != 0 or not 0 <= start <= end <= len(self.binary):
            raise ValueError('Buffer view inválido')
        return memoryview(self.binary)[start:end]

    def accessor(self, index):
        a = self.doc['accessors'][index]
        if 'sparse' in a:
            raise ValueError('No se admiten accessors sparse')
        dtype = np.dtype({5120: 'i1', 5121: 'u1', 5122: '<i2', 5123: '<u2',
                          5125: '<u4', 5126: '<f4'}[a['componentType']])
        width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
        view = self.doc['bufferViews'][a['bufferView']]
        array = np.ndarray((a['count'], width), dtype=dtype, buffer=self.view(a['bufferView']),
                           offset=a.get('byteOffset', 0),
                           strides=(view.get('byteStride', width*dtype.itemsize), dtype.itemsize))
        if a.get('normalized'):
            return np.maximum(-1, array.astype(float) / np.iinfo(dtype).max)
        return array


def rotation(q):
    q = np.asarray(q, dtype=float)
    x, y, z, w = q / np.linalg.norm(q)
    return np.array(((1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)),
                     (2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)),
                     (2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y))))


def xyz_euler(r):
    """SMD XYZ: Rz @ Ry @ Rx."""
    cy = math.hypot(r[0, 0], r[1, 0])
    y = math.atan2(-r[2, 0], cy)
    if cy < 1e-7:
        return math.atan2(-r[1, 2], r[1, 1]), y, 0.
    return math.atan2(r[2, 1], r[2, 2]), y, math.atan2(r[1, 0], r[0, 0])


def sample(times, vals, t, quaternion):
    right = np.searchsorted(times, t, side='right')
    if right == 0 or right == len(times):
        return vals[0 if right == 0 else -1]
    left = right - 1
    f = (t - times[left]) / (times[right] - times[left])
    a, b = vals[left], vals[right]
    if quaternion:
        dot = float(a @ b)
        if dot < 0:
            b, dot = -b, -dot
        if dot < .9995:
            theta = math.acos(dot)
            return (math.sin((1-f)*theta)*a + math.sin(f*theta)*b) / math.sin(theta)
    return (1-f)*a + f*b


def rest(node):
    return (np.asarray(node.get('translation', (0, 0, 0)), dtype=float),
            rotation(node.get('rotation', (0, 0, 0, 1))))


def skeleton(model, bank):
    root = model.names['root_motion']
    if not np.allclose(model.nodes[root].get('scale', (1,)*3), INCH):
        raise ValueError('El esqueleto del agente no está en pulgadas')
    ids, parents = {}, []

    def visit(i, parent):
        ids[i] = len(parents)
        parents.append(parent)
        for child in model.nodes[i].get('children', []):
            visit(child, ids[i])

    visit(root, -1)
    pose, channel_map = [], {}
    for i, parent in zip(ids, parents):
        n = model.nodes[i]
        if 'matrix' in n or (i != root and not np.allclose(n.get('scale', (1,)*3), 1)):
            raise ValueError(f'Transformación inesperada en {n["name"]}')
        pose.append(rest(n))
        if n['name'] not in bank.names:
            continue  # Huesos accesorios propios del agente: mantienen su pose local.
        j = bank.names[n['name']]
        if parent != -1 and model.nodes[model.parents[i]]['name'] != bank.nodes[bank.parents[j]]['name']:
            raise ValueError(f'Jerarquía incompatible: {n["name"]}')
        channel_map[j] = ids[i]
    if len(channel_map) < 60:
        raise ValueError('No se encontró el esqueleto común de locomoción')
    return ids, parents, pose, channel_map


def take_clip(bank, anim, pose, channel_map):
    duration = 0.
    tracks = []
    for channel in anim['channels']:
        sampler = anim['samplers'][channel['sampler']]
        if sampler.get('interpolation', 'LINEAR') != 'LINEAR':
            raise ValueError('Se esperaba interpolación lineal de cs2go')
        target = channel['target']
        j, path = target['node'], target['path']
        ts = bank.accessor(sampler['input']).ravel().astype(float)
        duration = max(duration, ts[-1])
        if j not in channel_map or target['node'] == bank.names['root_motion']:
            continue  # Reproducción in situ; se omiten nodos de cámara y anclajes no presentes.
        if path not in ('translation', 'rotation'):
            raise ValueError(f'Canal no soportado: {path}')
        values = bank.accessor(sampler['output']).astype(float)
        pos, rot = rest(bank.nodes[j])
        k = channel_map[j]
        tracks.append((k, path == 'rotation', ts, values, pos, rot))
    intervals = round(duration * FPS)
    if not intervals or not tracks:
        raise ValueError(f'Clip sin movimiento: {anim["name"]}')
    for t in np.linspace(0., duration, intervals + 1):
        frame = list(pose)
        for k, is_rot, ts, values, source_pos, source_rot in tracks:
            value = sample(ts, values, t, is_rot)
            pos, rot = frame[k]
            if is_rot:
                rot = pose[k][1] @ source_rot.T @ rotation(value)
            else:
                pos = pose[k][0] + (value - source_pos) / INCH
            frame[k] = (pos, rot)
        yield frame


def write_smd(path, names, parents, frames, lift, triangles=()):
    with path.open('w', encoding='ascii') as stream:
        stream.write('version 1\nnodes\n')
        for i, (name, parent) in enumerate(zip(names, parents)):
            stream.write(f'{i} "{name}" {parent}\n')
        stream.write('end\nskeleton\n')
        previous = None
        for frame, pose in enumerate(frames):
            stream.write(f'time {frame}\n')
            angles = []
            for i, (p, r) in enumerate(pose):
                if i == 0:
                    p, r = STUDIO @ p + (0, 0, lift), STUDIO @ r
                euler = np.array(xyz_euler(r))
                if previous is not None:
                    # El compilador interpola valores Euler, no cuaterniones.
                    candidates = np.array([euler, (euler[0]+math.pi, math.pi-euler[1], euler[2]+math.pi)])
                    diff = (candidates - previous[i] + math.pi) % (2*math.pi) - math.pi
                    euler = previous[i] + min(diff, key=lambda d: d @ d)
                angles.append(euler)
                stream.write(f'{i} ' + ' '.join(f'{v:.7f}' for v in (*p, *euler)) + '\n')
            previous = angles
        stream.write('end\n')
        if triangles:
            stream.write('triangles\n')
            for texture, corners in triangles:
                stream.write(texture + '\n')
                for bone, pos, norm, uv in corners:
                    stream.write(f'{bone} ' + ' '.join(f'{v:.6f}' for v in (*pos, *norm, *uv)) + '\n')
            stream.write('end\n')


def texture_bmp(data, basisu, work, destination):
    if bytes(data[:12]) == b'\xabKTX 20\xbb\r\n\x1a\n':
        (work / 'tex.ktx2').write_bytes(data)
        png = work / 'tex_unpacked_rgb_ETC1_RGB_0_0_0000.png'
        png.unlink(missing_ok=True)
        result = subprocess.run([basisu, '-unpack', '-file', 'tex.ktx2', '-format_only', '0', '-no_ktx'],
                                cwd=work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if result.returncode or not png.is_file():
            raise ValueError(f'No se pudo decodificar {destination.name}: {result.stdout[-1200:]}')
        image = Image.open(png)
    else:
        image = Image.open(io.BytesIO(data))
    with image:
        image.convert('RGB').resize((256, 256), Image.Resampling.LANCZOS).quantize(256).save(destination)


def mesh_parts(model, ids, basisu, work, output):
    lift = math.inf
    geometry = []
    for node in model.nodes:
        if 'mesh' not in node:
            continue
        if any(key in node for key in ('matrix', 'translation', 'rotation', 'scale')):
            raise ValueError('Se esperaba una malla colocada en el origen de estudio')
        joints = np.array([ids[i] for i in model.doc['skins'][node['skin']]['joints']])
        for p in model.doc['meshes'][node['mesh']]['primitives']:
            if p.get('mode', 4) != 4:
                raise ValueError('La malla no está triangulada')
            attrs = {k: model.accessor(v) for k, v in p['attributes'].items()}
            idx = model.accessor(p['indices']).reshape(-1, 3)
            pos = attrs['POSITION'] @ STUDIO.T / INCH
            norm = attrs['NORMAL'] @ STUDIO.T
            norm /= np.linalg.norm(norm, axis=1, keepdims=True).clip(1e-12)
            lift = min(lift, pos[:, 2].min())
            weights = attrs['WEIGHTS_0']
            bone = joints[np.take_along_axis(attrs['JOINTS_0'], weights.argmax(axis=1)[:, None], axis=1).ravel()]
            material = model.doc['materials'][p['material']]['pbrMetallicRoughness']['baseColorTexture']
            transform = material.get('extensions', {}).get('KHR_texture_transform', {})
            if transform.get('rotation', 0) or transform.get('texCoord', material.get('texCoord', 0)):
                raise ValueError('Transformación UV no soportada')
            uv = attrs['TEXCOORD_0'] * transform.get('scale', (1, 1)) + transform.get('offset', (0, 0))
            uv[:, 1] = 1. - uv[:, 1]
            tex = model.doc['textures'][material['index']]
            image = tex.get('extensions', {}).get('KHR_texture_basisu', tex)['source']
            texture = f'mat{p["material"]:02d}.bmp'
            if not (output / texture).exists():
                texture_bmp(model.view(model.doc['images'][image]['bufferView']), basisu, work, output / texture)
            geometry.append((texture, idx, bone, pos, norm, uv))
    parts, tri_count = [], 0
    for texture, idx, bone, pos, norm, uv in geometry:
        # Split each material into rigid submodels below the software-renderer limit.
        block, used = [], set()
        pos[:, 2] -= lift
        corners = list(zip(bone, map(tuple, pos), map(tuple, norm), map(tuple, uv)))
        for tri in idx:
            indices = set(tri)
            if len(used | indices) > MAX_COMPONENTS:
                parts.append(block)
                block, used = [], set()
            block.append((texture, tuple(corners[i] for i in tri)))
            used.update(indices)
            tri_count += 1
        if block:
            parts.append(block)
    if not parts or len(parts) > 32 or tri_count > 20000:
        raise ValueError(f'Malla demasiado compleja: {tri_count} tris, {len(parts)} piezas')
    return -lift, parts, tri_count


def export(assets, output, node, basisu):
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'Ya existe {output}; elegí otro --output')
    assets = assets / 'cs2go'
    bank = GLTF.animations(assets / 'animations/locomotion/diagonal.glb')
    clips = {anim['name']: anim for anim in bank.doc['animations']}
    if set(clips) != set(AGENT_CLIPS[1:]):
        raise ValueError('El banco no contiene los 36 clips esperados')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.agents-', dir=output.parent) as tmp:
        work = Path(tmp)
        stage = work / 'models'
        for tag, roster in AGENTS.items():
            out = stage / tag
            out.mkdir(parents=True)
            model = GLTF.roster(assets / 'agents/roster' / f'{roster}.glb', work, node)
            ids, parents, pose, channel_map = skeleton(model, bank)
            names = [model.nodes[i]['name'] for i in ids]
            lift, parts, count = mesh_parts(model, ids, basisu, work, out)
            qc = [f'$modelname "dawe_{tag}.mdl"', '$cd "."', '$cdtexture "."', '$origin 0 0 0 270']
            for i, tris in enumerate(parts):
                name = f'body{i:02d}'
                write_smd(out / f'{name}.smd', names, parents, [pose], lift, tris)
                qc.append(f'$body "{name}" "{name}"')
            write_smd(out / 'idle.smd', names, parents, [pose], lift)
            for label in AGENT_CLIPS:
                if label != 'idle':
                    write_smd(out / f'{label}.smd', names, parents, take_clip(bank, clips[label], pose, channel_map), lift)
                qc.append(f'$sequence "{label}" "{label}" fps {FPS} loop')
            (out / f'{tag}.qc').write_text('\n'.join(qc) + '\n', encoding='ascii')
            print(f'{tag}: {count} triángulos, {len(parts)} piezas, {len(ids)} huesos de origen, {len(channel_map)} compatibles')
        stage.rename(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, default=ROOT / 'third_party_assets')
    parser.add_argument('--output', type=Path, default=ROOT / 'third_party_assets/agents_goldsrc')
    parser.add_argument('--node', default='node')
    parser.add_argument('--basisu', default='basisu', help='ruta a Basis Universal 1.16 o posterior')
    args = parser.parse_args()
    try:
        basisu = str(Path(args.basisu).resolve()) if Path(args.basisu).is_file() else args.basisu
        export(args.assets, args.output.resolve(), args.node, basisu)
    except (OSError, ValueError, KeyError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(1, f'No se pudo exportar a los agentes: {error}\n')


if __name__ == '__main__':
    main()
