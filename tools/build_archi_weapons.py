#!/usr/bin/env python3
"""Convert the pinned Archi Source 1 viewmodels to standalone Godot assets.

Set PYTHONPATH to the parent of a SourceIO checkout (see docs/archi-weapons.md).
The input directory is a checkout/extraction of ShadowNigth/archi.
"""
import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import re

import numpy as np
from PIL import Image
from SourceIO.library.models.mdl.structs.ani_file import read_anim_block_table
from SourceIO.library.models.mdl.structs.compressed_vectors import Quat48, Quat48S
from SourceIO.library.models.mdl.structs.local_animation import AnimDescFlags, AniBoneFlags
from SourceIO.library.models.mdl.v49.mdl_file import MdlV49
from SourceIO.library.models.vtx import open_vtx
from SourceIO.library.models.vvd import Vvd
from SourceIO.library.source1.vtf import load_vtf_texture
from SourceIO.library.utils import MemoryBuffer

from archi_catalog import EXTRA_MODELS, SILENCERS, TUBE_SHOTGUNS
from archi_cyberpunk import fit as fit_cyberpunk
from build_godot_assets import Writer, quaternion
from build_weapon_drops import build as build_drop
from build_godot_preview import bake
from build_agents import rotation
from port_godot_viewmodel import Y_UP, read_smd, tangent_frame

MODELS = {
    'usp-s': ('usp', 'v_pist_223', {'silencer_attach': 'attach', 'silencer_detach': 'detach'}),
    'glock': ('glock', 'v_pist_glock18', {'idle': 'glock_idle', 'shoot1': 'glock_firesingle',
                                        'draw': 'glock_draw', 'reload': 'glock_reload'}),
    'deagle': ('deagle', 'v_pist_deagle', {'idle': 'idle1'}),
    'ak-47': ('ak47', 'v_rif_ak47', {'idle': 'ak47_idle', 'shoot1': 'ak47_fire1', 'shoot2': 'ak47_fire2',
                                   'shoot3': 'ak47_fire3', 'draw': 'ak47_draw', 'reload': 'ak47_reload'}),
    'm4a4': ('m4a4', 'v_rif_m4a1', {}),
    'awp': ('awp', 'v_snip_awp', {'idle': 'awp_idle', 'shoot1': 'awp_fire', 'draw': 'awp_draw', 'reload': 'awp_reload'}),
    'bayonet': ('knife_kukri', 'v_knife_kukri', {'lookat01_draw': 'lookat01'}),
}
MODELS.update(EXTRA_MODELS)


def buffer(path):
    return MemoryBuffer(path.read_bytes())


def read_model(path):
    data = buffer(path)
    # SourceIO's convenience parser attempts an inline-only animation read. The
    # compressed frame/ANI decoder below is authoritative and checks every clip.
    with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
        model = MdlV49.from_buffer(data)
    return model, data


def decode_frame_block(data, count, pos, quat):
    base = data.tell()
    constants, frames, stride = data.read_fmt('3i')
    data.skip(12)
    flags = [AniBoneFlags(data.read_uint8()) for _ in range(pos.shape[1])]
    if constants:
        data.seek(base + constants)
        for j, flag in enumerate(flags):
            if flag & AniBoneFlags.CONST_ROT2:
                quat[:, j] = Quat48S.read(data)
            if flag & AniBoneFlags.RAW_ROT:
                quat[:, j] = Quat48.read(data)
            if flag & AniBoneFlags.RAW_POS:
                pos[:, j] = data.read_fmt('3e')
            if flag & AniBoneFlags.CONST_POS2:
                pos[:, j] = data.read_fmt('3f')
        if frames and data.tell() > base + frames:
            raise ValueError('Los datos constantes invaden las claves de animación')
    if frames and stride:
        if stride <= 0 or base + frames + count * stride > data.size():
            raise ValueError('Bloque FRAMEANIM truncado')
        for i in range(count):
            data.seek(base + frames + i * stride)
            for j, flag in enumerate(flags):
                if flag & AniBoneFlags.ANIM_ROT2:
                    quat[i, j] = Quat48S.read(data)
                if flag & AniBoneFlags.ANIM_ROT:
                    quat[i, j] = Quat48.read(data)
                if flag & AniBoneFlags.ANIM_POS:
                    pos[i, j] = data.read_fmt('3e')
                if flag & AniBoneFlags.FULL_ANIM_POS:
                    pos[i, j] = data.read_fmt('3f')
            if data.tell() != base + frames + (i+1) * stride:
                raise ValueError('El tamaño de fotograma MDL no coincide con sus canales')


def decode_animation(desc, model, data, ani, blocks):
    count, bones = desc.frame_count, model.bones
    if count < 1 or not np.isfinite(desc.fps) or desc.fps <= 0:
        raise ValueError(f'Animación vacía: {desc.name}')
    # Two authored slide layers advertise DELTA on the sequence instead
    # of the descriptor. Their zero translations are offsets, not wrist joints.
    delta = bool(desc.flags & AnimDescFlags.DELTA) or desc.name.endswith('_additive')
    pos = np.tile([b.position for b in bones], (count, 1, 1))
    quat = np.tile([b.quat for b in bones], (count, 1, 1))
    if delta:
        pos.fill(0)
        quat[:] = (0, 0, 0, 1)
    sections = desc.get_sections(data)
    step = desc.section_frame_count if sections else count
    for start in range(0, count, step):
        end = min(start + step, count)
        if sections:
            section = sections[start // step]
            block, offset = section.anim_block, section.anim_offset
        else:
            block, offset = desc.animblock_id, desc.animblock_offset
        if block:
            if ani is None or block >= len(blocks):
                raise ValueError(f'Archivo .ani faltante: {desc.name}')
            src = ani
            src.seek(blocks[block].data_offset + offset)
        elif offset:
            src = data
            src.seek(desc._entry_offset + offset)
        else:
            continue
        if desc.flags & AnimDescFlags.FRAMEANIM:
            decode_frame_block(src, end-start, pos[start:end], quat[start:end])
        else:
            tracks = desc._read_mdl_animations(src, bones, end-start)
            for i, bone in enumerate(bones):
                if bone.name in tracks:
                    pos[start:end, i], quat[start:end, i] = tracks[bone.name]['pos'], tracks[bone.name]['rot']
    if not np.isfinite(pos).all() or not np.isfinite(quat).all() or np.any(np.linalg.norm(quat, axis=-1) < .9):
        raise ValueError(f'Claves de animación inválidas: {desc.name}')
    if delta:
        pos += [b.position for b in bones]
        # Additive engine clips are exported as standalone poses on the bind rig.
        for i, bone in enumerate(bones):
            quat[:, i] = [quaternion(rotation(bone.quat) @ rotation(q)) for q in quat[:, i]]
    pos = pos @ Y_UP.T * .0254
    quat[:, :, :3] = quat[:, :, :3] @ Y_UP.T
    quat /= np.linalg.norm(quat, axis=-1, keepdims=True)
    return pos, quat


def globals_from_frames(names, local):
    matrices = []
    for (_, parent), (position, r) in zip(names, local):
        m = np.eye(4)
        m[:3, :3], m[:3, 3] = r, position
        matrices.append(m if parent < 0 else matrices[parent] @ m)
    return np.array(matrices)


def vtf(path, limit=768):
    raw = path.read_bytes()
    # Decode the first mip within the export budget, not the full 4096² atlas.
    width, height = int.from_bytes(raw[16:18], 'little'), int.from_bytes(raw[18:20], 'little')
    mip = 0
    while max(width, height) >> mip > limit and mip + 1 < raw[56]:
        mip += 1
    pixels, width, height, is_float = load_vtf_texture(raw, 0, 0, mip)
    if is_float:
        pixels = (np.frombuffer(pixels, dtype='<f4').clip(0, 1)*255).astype('uint8').tobytes()
    image = Image.frombytes('RGBA', (width, height), bytes(pixels)).convert('RGB')
    image.thumbnail((limit, limit), Image.Resampling.LANCZOS)
    return image


class Export:
    def __init__(self, model):
        self.names = [(b.name, b.parent_id) for b in model.bones]
        self.ids = {name: i for i, (name, _) in enumerate(self.names)}
        base = [(Y_UP @ b.position * .0254, Y_UP @ rotation(b.quat) @ Y_UP.T) for b in model.bones]
        self.world = globals_from_frames(self.names, base)
        nodes = [dict(name=name, translation=pos.tolist(), rotation=quaternion(rot).tolist())
                 for (name, _), (pos, rot) in zip(self.names, base)]
        roots = []
        for i, (_, parent) in enumerate(self.names):
            if parent < 0:
                roots.append(i)
            else:
                nodes[parent].setdefault('children', []).append(i)
        self.root = len(nodes)
        nodes.append(dict(name='ArchiSkeleton', children=roots))
        self.doc = dict(asset=dict(version='2.0', generator='Dawe Archi Source converter'), scene=0,
                        scenes=[dict(nodes=[self.root])], nodes=nodes, meshes=[], skins=[], animations=[],
                        textures=[], images=[], materials=[], extras={'source': 'ShadowNigth/archi'})
        self.w = Writer(self.doc)
        self.skin(list(range(self.root)), self.world)

    def skin(self, nodes, matrices):
        idx = len(self.doc['skins'])
        accessor = self.w.accessor(np.linalg.inv(matrices).transpose(0, 2, 1), 'MAT4')
        self.doc['skins'].append(dict(joints=nodes, inverseBindMatrices=accessor, skeleton=self.root))
        return idx

    def material(self, name, image, normal=None, metallic=0.0):
        def tex(img):
            payload = io.BytesIO()
            img.save(payload, 'PNG', optimize=True)
            idx = len(self.doc['textures'])
            self.doc['textures'].append(dict(source=idx))
            self.doc['images'].append(dict(bufferView=self.w.view(payload.getvalue()), mimeType='image/png'))
            return dict(index=idx)
        info = dict(name=name, pbrMetallicRoughness=dict(baseColorTexture=tex(image), metallicFactor=metallic,
                                                        roughnessFactor=.56 if metallic else .9))
        if normal is not None:
            info['normalTexture'] = tex(normal)
        self.doc['materials'].append(info)
        return len(self.doc['materials']) - 1

    def primitive(self, positions, normals, uv, links, weights, indices, material):
        # Remove zero-area padding emitted by Source's rig bodygroup/meshes.
        tri = indices.reshape(-1, 3)
        xyz = positions[tri]
        good = np.linalg.norm(np.cross(xyz[:, 1]-xyz[:, 0], xyz[:, 2]-xyz[:, 0]), axis=1) > 1e-12
        if not good.any():
            return None
        tri = tri[good]
        xyz = positions[tri]
        # Choose winding using the source vertex normals; SMD and VTX have
        # different winding conventions, but share this geometric invariant.
        opposite = np.median(np.sum(np.cross(xyz[:, 1]-xyz[:, 0], xyz[:, 2]-xyz[:, 0]) * normals[tri].mean(axis=1), axis=1)) < 0
        if opposite:
            tri = tri[:, [0, 2, 1]]
        used, indices = np.unique(tri, return_inverse=True)
        positions, normals, uv = positions[used], normals[used].copy(), uv[used]
        weights, links = weights[used].copy(), links[used].copy()
        weights /= weights.sum(axis=1, keepdims=True)
        links[weights == 0] = 0
        sizes = np.linalg.norm(normals, axis=1)
        normals[sizes < 1e-8] = (0, 1, 0)
        normals /= np.linalg.norm(normals, axis=1, keepdims=True)
        def attr(values, dims, component=5126, bounds=False):
            return self.w.accessor(values, dims, component, bounds=bounds, target=34962)
        attrs = dict(POSITION=attr(positions, 'VEC3', bounds=True), NORMAL=attr(normals, 'VEC3'),
                     TEXCOORD_0=attr(uv, 'VEC2'), JOINTS_0=attr(links, 'VEC4', 5123), WEIGHTS_0=attr(weights, 'VEC4'))
        if 'normalTexture' in self.doc['materials'][material]:
            attrs['TANGENT'] = attr(tangent_frame(positions, uv, normals, indices), 'VEC4')
        return dict(attributes=attrs, indices=self.w.accessor(indices.ravel(), 'SCALAR', 5125, target=34963), material=material)

    def mesh(self, name, primitives, skin):
        primitives = [p for p in primitives if p is not None]
        if not primitives:
            return
        self.doc['scenes'][0]['nodes'].append(len(self.doc['nodes']))
        self.doc['nodes'].append(dict(name=name, mesh=len(self.doc['meshes']), skin=skin))
        self.doc['meshes'].append(dict(name=name, primitives=primitives))

    def animation(self, name, fps, pos, quat):
        clip = dict(name=name, samplers=[], channels=[])
        # Shared frame grid, including constant tracks, for stable clip switches.
        time = self.w.accessor(np.arange(len(pos))/fps, 'SCALAR', bounds=True)
        for j in range(len(self.names)):
            track = quat[:, j].copy()
            for i in range(1, len(track)):
                if track[i-1] @ track[i] < 0:
                    track[i] *= -1
            for path, data, dims in [('translation', pos[:, j], 'VEC3'), ('rotation', track, 'VEC4')]:
                clip['channels'].append(dict(sampler=len(clip['samplers']), target=dict(node=j, path=path)))
                clip['samplers'].append(dict(input=time, output=self.w.accessor(data, dims), interpolation='LINEAR'))
        self.doc['animations'].append(clip)


def weapon_mesh(export, mdl, path, materials, weapon):
    vtx = open_vtx(buffer(path.with_suffix('.dx90.vtx')))
    vvd = Vvd.from_buffer(buffer(path.with_suffix('.vvd'))).lod_data[0]
    gun, silencer = [], []
    silencer_ids = [i for i, (name, _) in enumerate(export.names) if 'silencer' in name.lower()]
    for body, layout in zip(mdl.body_parts, vtx.body_parts, strict=True):
        if body.name.lower() in ('rig',) or not body.models[0].vertex_count:
            continue
        model, lod = body.models[0], layout.models[0].model_lods[0]
        data = vvd[model.vertex_offset:model.vertex_offset + model.vertex_count]
        for mesh, topology in zip(model.meshes, lod.meshes, strict=True):
            if not topology.strip_groups:
                continue
            m = mdl.materials[mesh.material_index].name.lower()
            entry = materials[m]
            for strip in topology.strip_groups:
                if any(not (s.flags & 1) for s in strip.strips):
                    raise ValueError('La topología no es una lista de triángulos')
                inds = strip.vertexes['original_mesh_vertex_index'].ravel().astype('int64')
                tri = (inds[strip.indices] + mesh.vertex_index_start).reshape(-1, 3)
                d = data
                links = np.pad(d['bone_id'], ((0, 0), (0, 1)))
                weights = np.pad(d['weight'], ((0, 0), (0, 1)))
                # VVD stores the influence count in the byte following its IDs.
                weights[np.arange(4)[None, :] >= d['pad'][:, None]] = 0
                dedicated = np.isin(links, silencer_ids) & (weights > 0)
                is_silencer = dedicated.any(axis=1)[tri].all(axis=1) if silencer_ids else np.zeros(len(tri), bool)
                for target, selected in ((gun, tri[~is_silencer]), (silencer, tri[is_silencer])):
                    if len(selected):
                        target.append(export.primitive(d['vertex'] @ Y_UP.T * .0254, d['normal'] @ Y_UP.T,
                                                       d['uv'], links, weights, selected, entry))
    export.mesh('ArmsAndWeapon', gun, 0)
    if weapon in SILENCERS and not any(silencer):
        raise ValueError('No se encontró la malla móvil del silenciador')
    export.mesh('Silencer', silencer, 0)


def weapon_materials(export, mdl, folder):
    materials = {}
    for i, mat in enumerate(mdl.materials):
        name = mat.name.lower()
        paths = list((folder/'materials').rglob(Path(name).name + '.vmt'))
        if not paths:
            raise ValueError(f'Material faltante: {name}')
        spec = paths[0].read_text(encoding='latin1')
        def image(key):
            match = re.search(r'"\$' + key + r'"\s+"([^"]+)"', spec, re.I)
            if not match:
                return None
            if match[1].replace("\\", "/") == "dev/flat_normal":
                return None
            return vtf(folder/'materials'/(match[1].replace('\\', '/')+'.vtf'))
        materials[name] = export.material('weapon-color' if i == 0 else f'weapon-material-{i}',
                                          image('basetexture'), image('bumpmap'), .48)
    return materials


def smooth_glove_weights(surfaces, names):
    """Weld the five SMD chunks by position and soften their rigid finger seams."""
    vertices, adjacency = {}, []
    # Accumulate across both material/UV seams and file boundaries.
    samples = []
    for corners in surfaces.values():
        indices = []
        for skin, geom in corners:
            key = tuple(round(x, 4) for x in geom[:3])
            idx = vertices.setdefault(key, len(vertices))
            indices.append(idx)
            if idx == len(adjacency):
                adjacency.append(set())
                samples.append(np.zeros(len(names)))
            for bone, value in skin:
                samples[idx][bone] += value
        for a, b, c in np.array(indices).reshape(-1, 3):
            adjacency[a].update((b, c))
            adjacency[b].update((a, c))
            adjacency[c].update((a, b))
    weight = np.asarray(samples)
    weight /= weight.sum(axis=1, keepdims=True)
    for _ in range(2):
        result = weight.copy()
        for j, neighbors in enumerate(adjacency):
            if neighbors:
                result[j] = .55 * weight[j] + .45 * weight[sorted(neighbors)].mean(axis=0)
        weight = result
    links = []
    for row in weight:
        top = np.argsort(row)[-4:][::-1]
        total = row[top].sum()
        links.append(tuple((int(n), float(row[n]/total)) for n in top if row[n] > 0))
    return {mat: [(links[vertices[tuple(round(x, 4) for x in geom[:3])]], geom) for _, geom in corners]
            for mat, corners in surfaces.items()}


def gloves(export, root, rig):
    arms = root / rig / 'Ct Arms'
    paints = root / 'Sport Gloves Vice' / 'Sport Gloves Vice FT'
    sleeve = root / 'Ct Arms Textures/sleeve_sas/sleeve_sas.bmp'
    materials = {}
    for is_glove, paths in ((False, sorted(arms.glob('ct_*.smd'))), (True, sorted(arms.glob('g*.smd')))):
        all_surfaces = {}
        names, poses, _ = read_smd(paths[0])
        by_name = {name: i for i, (name, _) in enumerate(names)}
        for path in paths:
            equivalent, rest, surfaces = read_smd(path)
            if equivalent != names or any(not np.allclose(a, b) for x, y in zip(poses[0], rest[0]) for a, b in zip(x, y)):
                raise ValueError(f'Pose de referencia de guantes incompatible: {path}')
            for material, corners in surfaces.items():
                all_surfaces.setdefault(material, []).extend(corners)
        if is_glove:
            cuff = {i: by_name[name.replace('ForeTwist', 'Hand')] for i, (name, _) in enumerate(names) if name.endswith('ForeTwist')}
            all_surfaces = {key: [(tuple((cuff.get(i, i), w) for i, w in weights), geom) for weights, geom in corners]
                            for key, corners in all_surfaces.items()}
            all_surfaces = smooth_glove_weights(all_surfaces, names)
        bind = globals_from_frames(names, poses[0])
        if not is_glove:
            cuff = {i: by_name[name.replace('ForeTwist', 'Hand')] for i, (name, _) in enumerate(names) if name.endswith('ForeTwist')}
            fore_local = np.linalg.inv(bind)
            def blend_wrist(weights, geom):
                point = np.append(np.array(geom[:3]) @ Y_UP.T * .0254, 1.)
                result = []
                for bone, value in weights:
                    if bone in cuff:
                        # Blend only the sleeve seam next to the cuff. The rest
                        # follows the pack's forearm twist as authored.
                        along = (fore_local[bone] @ point)[2]
                        t = float(np.clip((along - .20) / .06, 0., 1.))
                        t = t*t*(3.-2.*t)
                        if t > 0.:
                            result.append((cuff[bone], value*t))
                        value *= 1.-t
                    if value > 0.:
                        result.append((bone, value))
                return tuple(result)
            all_surfaces = {mat: [(blend_wrist(weights, geom), geom) for weights, geom in corners]
                            for mat, corners in all_surfaces.items()}
        used = sorted({bone for corners in all_surfaces.values() for links, _ in corners for bone, weight in links if weight > 0})
        joints = [export.ids.get(names[i][0]) for i in used]
        if any(joint is None for joint in joints):
            raise ValueError(f'El rig de guantes no coincide: {[names[i][0] for i, j in zip(used, joints) if j is None]}')
        # SMD forearms/phalanges run along -X; the compiled viewmodels run
        # along +X. Keep the bind Z axis so fingerprints and palms stay put.
        reorient = np.diag((-1., 1., -1., 1.))  # 180° about Studio Z / Godot Y
        skin = export.skin(joints, bind[used] @ reorient)
        lookup = {bone: j for j, bone in enumerate(used)}
        primitives = []
        for material, corners in all_surfaces.items():
            key = material.strip()
            if key not in materials:
                image = sleeve if key == 'sleeve.bmp' else paints/key
                with Image.open(image) as im:
                    materials[key] = export.material('archi-' + image.stem, im.convert('RGB'))
            unique, indices = {}, []
            for corner in corners:
                indices.append(unique.setdefault(corner, len(unique)))
            positions = np.array([value for _, value in unique])
            links = np.zeros((len(unique), 4), np.uint16)
            weights = np.zeros((len(unique), 4), np.float32)
            for i, (weights_and_bones, _) in enumerate(unique):
                for j, (bone, weight) in enumerate(weights_and_bones):
                    links[i, j], weights[i, j] = lookup.get(bone, 0), weight
            uv = positions[:, 6:].copy()
            uv[:, 1] = 1 - uv[:, 1]
            primitives.append(export.primitive(positions[:, :3] @ Y_UP.T * .0254, positions[:, 3:6] @ Y_UP.T,
                                               uv, links, weights, np.array(indices), materials[key]))
        export.mesh('ArchiGloves' if is_glove else 'ArchiSleeves', primitives, skin)


def apply_slide_layer(base, layer, names):
    """Bake Source's short slide animation on top of the longer pistol shot."""
    fps, positions, rotations = base
    layer_fps, lp, lr = layer
    indices = np.minimum(len(lp) - 1, np.rint(np.arange(len(positions)) * layer_fps / fps).astype(int))
    positions, rotations = positions.copy(), rotations.copy()
    for j, (name, _) in enumerate(names):
        if not name.endswith('_slide'):
            continue
        positions[:, j] += lp[indices, j] - lp[0, j]
        inverse = rotation(lr[0, j]).T
        rotations[:, j] = [quaternion(rotation(q) @ inverse @ rotation(lr[i, j]))
                           for i, q in zip(indices, rotations[:, j])]
    return fps, positions, rotations


def restore_famas_wrist(export, positions, rotations):
    """Source retracts the left wrist bone into its elbow during the mag grab.

    The Cyberpunk forearm is weighted across both bones; reconstruct its span
    while keeping the authored hand transform (and magazine) in place.
    """
    forearm = export.ids['v_weapon.Bip01_L_Forearm']
    hand = export.ids['v_weapon.Bip01_L_Hand']
    assert export.names[forearm][1] < 0 and export.names[hand][1] == forearm
    track = positions[:, hand]
    length = np.linalg.norm(track, axis=1)
    span = float(np.linalg.norm(export.world[hand, :3, 3] - export.world[forearm, :3, 3]))
    good = np.flatnonzero(length >= span * .98)
    if not len(good):
        return positions
    positions = positions.copy()
    for frame in np.flatnonzero(length < span * .98):
        axes = np.array([np.interp(frame, good, track[good, axis]) for axis in range(3)])
        corrected = axes * span / np.linalg.norm(axes)
        positions[frame, forearm] += rotation(rotations[frame, forearm]) @ (track[frame] - corrected)
        positions[frame, hand] = corrected
    return positions


def assemble(root, output, weapon, arms=None, drop=True):
    key, name, alias = MODELS[weapon]
    source, = (p for p in root.rglob(f'{name}.mdl') if any(piece == f'm_cs2_{key}' for piece in p.parts))
    folder = next(parent for parent in source.parents if parent.name == f'm_cs2_{key}')
    model, data = read_model(source)
    export = Export(model)
    weapon_mesh(export, model, source, weapon_materials(export, model, folder), weapon)
    ani_path = source.with_suffix('.ani')
    ani = buffer(ani_path) if ani_path.exists() else None
    blocks = read_anim_block_table(data, model.header.anim_block_offset, model.header.anim_block_count)
    clips = [(desc.fps, *decode_animation(desc, model, data, ani, blocks)) for desc in model.anim_descs]
    sequences = {seq.name: seq for seq in model.sequences}
    if arms:
        if weapon == 'famas':
            reload_id = sequences['reload'].anim_desc_indices[0]
            fps, pos, quat = clips[reload_id]
            clips[reload_id] = (fps, restore_famas_wrist(export, pos, quat), quat)
        rest = sequences[alias.get('idle', 'idle1' if weapon == 'bayonet' else 'idle')]
        _, positions, rotations = clips[rest.anim_desc_indices[0]]
        neutral = globals_from_frames(export.names, [(p, rotation(q)) for p, q in zip(positions[0], rotations[0])])
        fit_cyberpunk(export, arms, neutral)
    else:
        rig = 'Knife Rig' if weapon == 'bayonet' else ('Saseky Rig' if weapon in ('glock', 'usp-s') else 'Rootns Rig')
        gloves(export, root/'Sport_gloves', rig)
    cues = {}
    for name, seq in {**sequences, **{new: sequences[old] for new, old in alias.items()}}.items():
        variants = list(dict.fromkeys(i for i in seq.anim_desc_indices if 0 <= i < len(clips)))
        if not variants:
            continue
        for i, index in enumerate(variants):
            clip = name if i == 0 else f'{name}_variant{i+1}'
            pose = clips[index]
            overlay = None
            if weapon == 'usp-s' and seq.name.startswith('shoot') and not seq.name.endswith('additive'):
                overlay = 'shoot_silenced_additive'
            elif weapon == 'glock' and seq.name in ('glock_firesingle', 'glock_firelast'):
                overlay = 'shoot_additive'
            if overlay:
                pose = apply_slide_layer(pose, clips[sequences[overlay].anim_desc_indices[0]], export.names)
            export.animation(clip, *pose)
            cues[clip] = [(e.cycle, e.options) for e in seq.events if e.event == 5004 and np.isfinite(e.cycle)]
    linked = {i for seq in model.sequences for i in seq.anim_desc_indices}
    for i, desc in enumerate(model.anim_descs):
        if i not in linked:
            export.animation(f'source_{desc.name.lstrip("@")}', *clips[i])
    if weapon == 'bayonet':
        # This companion model is the pose the Source inspect menu displays.
        inspect, = folder.rglob('v_knife_kukri_inspect.mdl')
        mdl, d = read_model(inspect)
        if [(b.name, b.parent_id) for b in mdl.bones] != export.names:
            raise ValueError('Rig incompatible en el .mdl de inspección del kukri')
        desc = mdl.anim_descs[0]
        export.animation('inspect_menu_pose', desc.fps, *decode_animation(desc, mdl, d, None, []))
    if weapon in TUBE_SHOTGUNS:
        names = ('start_reload', 'insert', 'insert', 'insert', 'after_reload')
        parts = [clips[sequences[n].anim_desc_indices[0]] for n in names]
        fps = max(f for f, _, _ in parts)
        resampled = []
        for source_fps, pos, rot in parts:
            times = np.linspace(0, len(pos)-1, round((len(pos)-1)*fps/source_fps)+1)
            lo = np.floor(times).astype(int)
            hi = np.minimum(lo+1, len(pos)-1)
            ratio = (times-lo)[:, None, None]
            blend = np.where(np.sum(rot[lo]*rot[hi], axis=-1, keepdims=True) < 0, -rot[hi], rot[hi])
            q = rot[lo]*(1-ratio)+blend*ratio
            q /= np.linalg.norm(q, axis=-1, keepdims=True)
            resampled.append((fps, pos[lo]*(1-ratio)+pos[hi]*ratio, q))
        parts = resampled
        positions = np.concatenate([p[:-1] if i < len(parts)-1 else p for i, (_, p, _) in enumerate(parts)])
        rotations = np.concatenate([q[:-1] if i < len(parts)-1 else q for i, (_, _, q) in enumerate(parts)])
        export.animation('reload', fps, positions, rotations)
        duration = len(positions) - 1
        start = 0
        cues['reload'] = []
        for n, (_, p, _) in zip(names, parts):
            cues['reload'].extend(((start + t*(len(p)-1))/duration, cue) for t, cue in cues[n])
            start += len(p)-1
    if weapon in SILENCERS:
        events = {}
        for name, initially, transition in [('silencer_attach', False, .109589), ('silencer_detach', True, .794521)]:
            if weapon != 'usp-s':
                # Model bodygroup event for M4A1-S is resolved from the source.
                seq = sequences[alias[name]]
                options = [e.cycle for e in seq.events if e.event == 5001 and 0 < e.cycle < 1]
                transition = options[0] if options else (.12 if not initially else .79)
            fps, pos, _ = clips[sequences[alias[name]].anim_desc_indices[0]]
            events[name] = [[0, initially], [round(transition*(len(pos)-1))/fps, not initially]]
        (output/f'{weapon}.json').write_text(json.dumps(events, indent=2)+'\n')
    path = output/f'{weapon}.glb'
    export.w.save(path)
    bake(path, path.with_suffix('.vis'), weapon)
    if weapon != 'bayonet':
        if drop:
            build_drop(path, output/f'{weapon}-drop.vis')
        icons = sorted(folder.glob('**/base_weapons/*.png'))
        if not icons:
            icons = sorted(folder.glob('**/preview.png'))
        if not icons:
            raise ValueError(f'Icono ausente en el pack: {weapon}')
        with Image.open(icons[0]) as original:
            image = original.convert('RGBA')
            image = image.crop(image.getbbox())
            image.thumbnail((320, 128), Image.Resampling.LANCZOS)
            image.save(output/f'buy-{weapon}.png', optimize=True)
    print(f'{weapon}: {len(export.names)} huesos, {len(export.doc["animations"])} clips', flush=True)
    return cues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--weapon', choices=MODELS, action='append')
    parser.add_argument('--arms', type=Path, help='GLB anterior con los brazos de Cyberpunk')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for weapon in args.weapon or MODELS:
        cues = assemble(args.source, args.output, weapon, args.arms)
        (args.output/f'{weapon}-source-events.json').write_text(json.dumps(cues, indent=2)+'\n')


if __name__ == '__main__':
    main()
