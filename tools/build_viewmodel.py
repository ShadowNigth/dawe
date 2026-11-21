"""Porta los clips de primera persona de cs2go a un MDL clásico."""

import argparse
from collections import defaultdict
from dataclasses import dataclass
import json
import math
from pathlib import Path
import struct
import sys

import bpy
from mathutils import Matrix

# Blender no siempre pone el directorio del script en sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_usp_idle import ROOT, TO_STUDIO, UNITS, basis, image_bmp, import_gltf, parts, retarget_arms, triangles
from import_assets import WEAPON_CLIPS

FPS = 30
ARM_UNITS = Matrix.Diagonal((UNITS, UNITS, UNITS, 1))
STUDIO = TO_STUDIO.to_4x4()
DIGITS = ('Index', 'Middle', 'Ring', 'Pinky', 'Thumb')
@dataclass(frozen=True)
class Weapon:
    tag: str
    material: str
    parts: tuple[str, ...]
    stabilize_wrist: bool = False

    @property
    def mdl(self):
        return f'v_dawe_{self.tag}.mdl'


WEAPONS = {
    'usp-s': Weapon('usp', 'pist_223', ('weapon_offset', 'slide', 'clip', 'hammer', 'trigger', 'silencer')),
    'ak-47': Weapon('ak47', 'ak47', ('weapon_offset', 'bolt', 'clip', 'cliprelease', 'trigger'),
                     stabilize_wrist=True),
}


def arm_names(prefix):
    hand = prefix + 'Hand'
    return [prefix + 'Arm', prefix + 'ForeArm', hand] + [
        f'{hand}{digit}{i + 1}' for digit in DIGITS for i in range(2 if digit == 'Thumb' else 3)
    ]


def rigid(matrix):
    """Quita escalas (GoldSrc clásico sólo almacena traslación y rotación)."""
    location, rotation, _ = matrix.decompose()
    result = rotation.to_matrix().to_4x4()
    result.translation = location
    return result


def arm_pose(bones, nodes, parents):
    """Pose de los huesos reducidos en el espacio del MultiRig (metros)."""
    pose = {}
    for side, prefix in (('L', 'Left'), ('R', 'Right')):
        def point(name):
            return nodes[f'{name}_{side}'].matrix_world.translation / UNITS

        def rest(name):
            return bones[name].head_local

        def place(name, rotation, head):
            matrix = (rotation @ bones[name].matrix_local.to_3x3()).to_4x4()
            matrix.translation = head
            pose[name] = matrix

        upper, fore, hand, *fingers = arm_names(prefix)
        s0, s1, s2 = map(point, ('arm_upper', 'arm_lower', 'hand'))
        r0, r1, r2 = map(rest, (upper, fore, hand))
        for name, a, b, ra, rb, across, rest_across in (
            (upper, s0, s1, r0, r1, s2 - s1, r2 - r1),
            (fore, s1, s2, r1, r2, s1 - s0, r1 - r0),
        ):
            place(name, basis(b - a, across) @ basis(rb - ra, rest_across).transposed(), a)
        index, pinky = map(point, ('finger_index_0', 'finger_pinky_0'))
        ri, rp = map(rest, (hand + 'Index1', hand + 'Pinky1'))
        place(hand, basis((index + pinky) / 2 - s2, index - pinky)
              @ basis((ri + rp) / 2 - r2, ri - rp).transposed(), s2)
        seam = prefix + 'WristSeam'
        if seam in parents:
            # Carry the split between the two meshes with one rigid joint.
            # The original MultiRig has additional wrist bones at this seam.
            projected = pose[fore] @ bones[fore].matrix_local.inverted() @ bones[hand].matrix_local
            q = projected.to_quaternion().slerp(pose[hand].to_quaternion(), .55)
            pose[seam] = q.to_matrix().to_4x4()
            pose[seam].translation = s2 - (s2 - s1).normalized() * .032
        for digit in DIGITS:
            for i in range(2 if digit == 'Thumb' else 3):
                name = f'{hand}{digit}{i + 1}'
                parent = parents[name]
                inherited = pose[parent] @ bones[parent].matrix_local.inverted() @ bones[name].matrix_local
                joint = f'finger_{digit.lower()}_{i}'
                if i < 2:
                    direction = point(f'finger_{digit.lower()}_{i + 1}') - point(joint)
                else:
                    direction = nodes[f'{joint}_{side}'].matrix_world.to_3x3().col[0] * (1 if side == 'L' else -1)
                axis = inherited.to_3x3().col[1].normalized()
                matrix = (axis.rotation_difference(direction.normalized()).to_matrix()
                          @ inherited.to_3x3()).to_4x4()
                matrix.translation = inherited.translation
                pose[name] = matrix
    return pose


def frame_pose(rig, clip, parents, weapon_parts):
    pose = {'root': Matrix.Identity(4)}
    for name, matrix in arm_pose(rig.data.bones, clip, parents).items():
        pose[name] = rigid(STUDIO @ ARM_UNITS @ matrix)
    for name in weapon_parts:
        pose[name] = rigid(STUDIO @ clip['wpn'].matrix_world @ clip[name].matrix_world)
    return pose


def read_duration(path, allow_short_secondary=False):
    with path.open('rb') as file:
        file.seek(12)
        size, kind = struct.unpack('<I4s', file.read(8))
        if kind != b'JSON':
            raise ValueError(f'GLB sin JSON: {path}')
        data = json.loads(file.read(size))
    durations = [max(data['accessors'][s['input']]['max'][0] for s in a['samplers'])
                 for a in data['animations']]
    if len(durations) != 2 or (not allow_short_secondary and abs(durations[0] - durations[1]) > 1.1 / FPS):
        raise ValueError(f'Se esperaban dos pistas sincronizadas: {path}')
    # Algunos clips de AK terminan un fotograma antes en la pista secundaria.
    # En la bayoneta la pista de la hoja puede incluso ser estática durante un idle.
    # Mantener la duración completa; Blender retiene la última pose de cada pista.
    return max(durations)


def weight_selector(obj, group_map, ids, fallback):
    groups = {g.index: group_map.get(g.name, fallback) for g in obj.vertex_groups}

    def select(vert):
        scores = defaultdict(float)
        for weight in vert.groups:
            scores[groups[weight.group]] += weight.weight
        return ids[max(scores, key=scores.get)] if scores else ids[fallback]
    return select


def write_smd(path, parents, poses, tris=()):
    ids = {name: i for i, name in enumerate(parents)}
    with path.open('w', encoding='ascii', newline='\n') as out:
        out.write('version 1\nnodes\n')
        for name, parent in parents.items():
            out.write(f'{ids[name]} "{name}" {ids.get(parent, -1)}\n')
        out.write('end\nskeleton\n')
        previous = {}
        for frame, pose in enumerate(poses):
            out.write(f'time {frame}\n')
            for name, parent in parents.items():
                local = pose[parent].inverted() @ pose[name] if parent else pose[name]
                rotation = local.to_euler('XYZ', previous[name]) if name in previous else local.to_euler('XYZ')
                previous[name] = rotation
                out.write(f'{ids[name]} ' + ' '.join(f'{v:.7f}' for v in (*local.translation, *rotation)) + '\n')
        out.write('end\n')
        if tris:
            out.write('triangles\n')
            for texture, corners in tris:
                out.write(texture + '\n')
                for pos, norm, uv, bone in corners:
                    links = bone if isinstance(bone, tuple) else ()
                    primary = links[0][0] if links else bone
                    line = f'{primary} ' + ' '.join(f'{v:.7f}' for v in (*pos, *norm, *uv))
                    if links:
                        line += f' {len(links)}' + ''.join(f' {idx} {weight:.8f}' for idx, weight in links)
                    out.write(line + '\n')
            out.write('end\n')


def import_clip(path):
    nodes = import_gltf(path)
    # Blender only activates the first animation in a GLB by default. In
    # cs2go the secondary action targets a separate set of nodes, so we can
    # activate both tracks simultaneously without blending competing keys.
    for node in nodes.values():
        data = node.animation_data
        if data and data.nla_tracks:
            track, = data.nla_tracks
            strip, = track.strips
            data.action = strip.action
            data.action_slot = strip.action_slot
    return nodes


def bake_sequence(path, rig, nodes, parents, weapon_parts, allow_short_secondary=False):
    duration = read_duration(path, allow_short_secondary)
    intervals = round(duration * FPS)
    scene = bpy.context.scene
    for i in range(intervals + 1):
        x = duration * FPS * i / intervals if intervals else 0
        scene.frame_set(math.floor(x), subframe=x % 1)
        silencer = nodes.get('silencer')
        yield frame_pose(rig, nodes, parents, weapon_parts), silencer is None or silencer.scale.x >= .5


def build(assets, output, weapon_name='usp-s'):
    weapon = WEAPONS[weapon_name]
    viewmodels = assets / 'cs2go/viewmodels'
    sequences = {name: viewmodels / weapon_name / f'{name}.glb' for name in WEAPON_CLIPS[weapon_name]}
    for path in sequences.values():
        if not path.is_file():
            raise FileNotFoundError(f'{path}: extraé el inventario actualizado con tools/import_assets.py')
    if output.exists():
        raise FileExistsError(f'Ya existe {output}. Usá --output para elegir otro directorio.')
    bpy.ops.wm.open_mainfile(filepath=str(assets / 'multirig/Cyberpunk_Rig.blend'), use_scripts=False)
    scene = bpy.context.scene
    scene.render.fps, scene.render.fps_base = FPS, 1
    rig = bpy.data.objects['Rig']
    gun, = (obj for obj in import_gltf(viewmodels / f'{weapon_name}.glb').values()
            if obj.type == 'MESH' and obj.parent and obj.parent.type == 'ARMATURE')
    idle = import_clip(sequences['idle'])
    scene.frame_set(0)
    retarget_arms(rig, idle)
    parents = {'root': None}
    for side in ('Left', 'Right'):
        upper, fore, hand, *fingers = arm_names(side)
        parents.update({upper: 'root', fore: upper, hand: fore})
        for name in fingers:
            parents[name] = hand if name.endswith('1') else name[:-1] + str(int(name[-1]) - 1)
        if weapon.stabilize_wrist:
            parents[side + 'WristSeam'] = fore
    parents.update({name: 'root' if name == 'weapon_offset' else 'weapon_offset' for name in weapon.parts})
    ids = {name: i for i, name in enumerate(parents)}
    bind = frame_pose(rig, idle, parents, weapon.parts)
    # La geometría de referencia de los brazos es la pose ponderada que se probó
    # en Studio. Cada vértice conserva luego su hueso dominante, como pide GoldSrc.
    for name in arm_names('Left') + arm_names('Right'):
        original = rig.pose.bones[name].matrix
        # La pose analítica conserva los mismos nudillos, incluso si el .blend
        # usa un hueso palmar intermedio. Verificar que la unión no se desplaza.
        if (bind[name].translation - (STUDIO @ ARM_UNITS @ original).translation).length > .1:
            raise ValueError(f'La pose de referencia no coincide en {name}')
    output.mkdir(parents=True)
    image_bmp(bpy.data.images['a0_000_ma__c_base_hq_d01'], output / 'arms.bmp')
    gun_texture = f'{weapon.tag}.bmp'
    image_bmp(bpy.data.images[f'{weapon.material} color'], output / gun_texture)
    gun_anchor = gun.matrix_world.inverted() @ gun.parent.matrix_world @ gun.parent.data.bones['weapon_offset'].head_local
    gun_transform = STUDIO @ idle['wpn'].matrix_world @ Matrix.Translation(-gun_anchor)
    group_map = {part: part for part in weapon.parts}
    texture_slot = next(i for i, material in enumerate(gun.data.materials) if material.name == weapon.material)
    gun_tris = list(triangles(gun, gun_transform, gun_texture, .19,
                              weight_selector(gun, group_map, ids, 'weapon_offset'), texture_slot))
    qc = [f'$modelname "{weapon.mdl}"', '$cd "."', '$cdtexture "."', '$scale 1', '$origin 0 0 0 270']
    if 'silencer' in ids:
        # Primer bodygroup: valores de body 0 (puesto) y 1 (quitado).
        silencer_id = ids['silencer']
        silencer = [tri for tri in gun_tris if all(c[3] == silencer_id for c in tri[1])]
        if not silencer:
            raise ValueError('La malla no trae triángulos ligados al silenciador')
        write_smd(output / 'silencer_mesh.smd', parents, [bind], silencer)
        qc += ['$bodygroup "silencer" {', ' studio "silencer_mesh"', ' blank', '}']
        gun_tris = [tri for tri in gun_tris if not all(c[3] == silencer_id for c in tri[1])]
    sources = {weapon.tag: gun_tris}
    for side in ('Left', 'Right'):
        group_map = {}
        for bone in rig.data.bones:
            current = bone
            while current and current.name not in parents:
                current = current.parent
            if current and current.name in arm_names(side):
                group_map[bone.name] = current.name
        if weapon.stabilize_wrist:
            group_map[f'{side[0].lower()}_Wrist_2_JNT'] = side + 'WristSeam'
        sources[side.lower()] = [tri for obj in bpy.data.collections[f'Arm {side}'].objects
                                 if obj.type == 'MESH' and obj.name.startswith(('submesh_01_', 'submesh_02_'))
                                 for tri in triangles(obj, STUDIO @ ARM_UNITS @ obj.matrix_world, 'arms.bmp', .37,
                                                      weight_selector(obj, group_map, ids, side + 'ForeArm'))]
    for name, source in sources.items():
        if not source:
            raise ValueError(f'La malla {name} está vacía')
        for i, chunk in enumerate(parts(source), 1):
            label = f'{name}_{i}'
            write_smd(output / f'{label}.smd', parents, [bind], chunk)
            qc.append(f'$body "{label}" "{label}"')
    for name, path in sequences.items():
        nodes = idle if name == 'idle' else import_clip(path)
        poses, visible = zip(*bake_sequence(path, rig, nodes, parents, weapon.parts))
        write_smd(output / f'{name}.smd', parents, poses)
        if name.startswith('silencer_'):
            events = [(i, 0 if enabled else 1) for i, enabled in enumerate(visible)
                      if i == 0 or visible[i - 1] != enabled]
            if len(events) != 2 or events[0][1] == events[1][1]:
                raise ValueError(f'No se encontró la transición del silenciador: {name}')
            qc += [f'$sequence "{name}" "{name}" fps {FPS} {{',
                   *(f' event 5001 {frame} "{body}"' for frame, body in events), '}']
        else:
            qc.append(f'$sequence "{name}" "{name}" fps {FPS}' + (' loop' if name == 'idle' else ''))
        for node in nodes.values():
            bpy.data.objects.remove(node, do_unlink=True)
        print(f'{name}: {len(poses)} fotogramas', flush=True)
    (output / f'{weapon.tag}.qc').write_text('\n'.join(qc) + '\n', encoding='ascii')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, default=ROOT / 'third_party_assets')
    parser.add_argument('--weapon', choices=WEAPONS, default='usp-s')
    parser.add_argument('--output', type=Path)
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    args = parser.parse_args(argv)
    output = args.output or ROOT / 'third_party_assets' / f'{WEAPONS[args.weapon].tag}_goldsrc'
    build(args.assets.resolve(), output.resolve(), args.weapon)


if __name__ == '__main__':
    main()
