"""Blender 4.5+: bake a smooth, full-geometry MultiRig viewmodel for Godot."""
import argparse
import json
from pathlib import Path
import sys

import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_viewmodel import (ARM_UNITS, FPS, ROOT, STUDIO, WEAPONS, arm_names, frame_pose,
                             bake_sequence, import_clip, import_gltf, rigid, write_smd)
from import_assets import WEAPON_CLIPS
from bake_multirig_material import bake_material

# This mesh references an auxiliary joint absent from the distributed rig.
JOINT_ALIASES = {'LeftInHandThumb': 'LeftHand'}


def linked_weights(vertex, names, ids, default):
    combined = {}
    for weight in vertex.groups:
        joint = ids.get(JOINT_ALIASES.get(names[weight.group], names[weight.group]), default)
        combined[joint] = combined.get(joint, 0.0) + weight.weight
    weights = sorted(((i, v) for i, v in combined.items() if v > 0.00001),
                     key=lambda pair: (-pair[1], pair[0]))[:4]
    total = sum(v for _, v in weights)
    return tuple((i, v / total) for i, v in weights) if total else ((default, 1.0),)


def triangles(obj, transform, texture, ids, fallback, material_index=None):
    # The original rest mesh gives the true inverse bind and avoids baking
    # any collapsed triangles from a warped idle pose or destructive decimation.
    mesh = obj.data
    mesh.calc_loop_triangles()
    names = [group.name for group in obj.vertex_groups]
    normals = mesh.corner_normals
    uv = mesh.uv_layers.active.data
    normal_matrix = transform.to_3x3().inverted().transposed()
    links = [linked_weights(v, names, ids, ids[fallback]) for v in mesh.vertices]
    for tri in mesh.loop_triangles:
        if material_index is not None and tri.material_index != material_index:
            continue
        yield texture, tuple((tuple(transform @ mesh.vertices[vert].co),
                             tuple((normal_matrix @ normals[loop].vector).normalized()),
                             tuple(uv[loop].uv), links[vert])
                            for loop, vert in zip(tri.loops, tri.vertices))


def image_file(image, path):
    if image.packed_file:
        path.write_bytes(image.packed_file.data)
        return
    copy = image.copy()
    try:
        copy.file_format = 'PNG'
        copy.filepath_raw = str(path)
        copy.save()
    finally:
        bpy.data.images.remove(copy)


def add_deformers(rig, arms, parents):
    """Preserve every bone that influences the two visible source arm meshes."""
    support = {}
    for side, objects in arms.items():
        wanted = set()
        for obj in objects:
            names = [g.name for g in obj.vertex_groups]
            wanted.update(JOINT_ALIASES.get(names[w.group], names[w.group])
                          for v in obj.data.vertices for w in v.groups if w.weight > 0.00001)
        core = set(arm_names(side))
        for name in sorted(wanted - core):
            bone = rig.data.bones[name]
            nearest = bone.parent
            while nearest and nearest.name not in core:
                nearest = nearest.parent
            follows = nearest.name if nearest else side + 'Arm'
            wrist = 'wrist' in name.lower()
            if wrist:
                follows = side + 'ForeArm'
            parents[name] = follows
            support[name] = (side, follows, wrist)
    return support


def pose_with_support(pose, rest, support):
    for name, (side, parent, wrist) in support.items():
        arm_rest = rest[name]
        first = pose[parent] @ rest[parent].inverted()
        if not wrist:
            pose[name] = first @ arm_rest
            continue
        hand, fore = side + 'Hand', side + 'ForeArm'
        second = pose[hand] @ rest[hand].inverted()
        axis = rest[hand].translation - rest[fore].translation
        amount = ((arm_rest.translation - rest[fore].translation).dot(axis) / axis.length_squared - .60) / .48
        amount = max(0.0, min(1.0, amount))
        amount = amount * amount * (3 - 2 * amount)
        orient = first.to_quaternion().slerp(second.to_quaternion(), amount)
        pose[name] = orient.to_matrix().to_4x4() @ arm_rest
        pose[name].translation = (first @ arm_rest.translation).lerp(second @ arm_rest.translation, amount)
    return pose


def build(assets, output, weapon_name):
    if output.exists():
        raise FileExistsError(output)
    weapon = WEAPONS[weapon_name]
    directory = assets / 'cs2go/viewmodels'
    bpy.ops.wm.open_mainfile(filepath=str(assets / 'multirig/Cyberpunk_Rig.blend'), use_scripts=False)
    scene = bpy.context.scene
    scene.render.fps, scene.render.fps_base = FPS, 1
    rig = bpy.data.objects['Rig']
    parents = {'root': None}
    arms = {}
    for side in ('Left', 'Right'):
        upper, fore, hand, *fingers = arm_names(side)
        parents.update({upper: 'root', fore: upper, hand: fore})
        parents.update({name: hand if name.endswith('1') else name[:-1] + str(int(name[-1]) - 1)
                        for name in fingers})
        arms[side] = [obj for obj in bpy.data.collections[f'Arm {side}'].objects
                      if obj.type == 'MESH' and obj.name.startswith(('submesh_01_', 'submesh_02_'))]
    # The reference is the asymmetrical Silverhand look, not two bare arms.
    silver, = (obj for obj in bpy.data.collections['Silverhand Arm (DISABLE LEFT ARM!)'].objects
               if obj.type == 'MESH' and obj.data.materials[0].name == 'ml_a0_001_ma_arms__silverhand_masksset')
    grip, = (obj for obj in bpy.data.collections['a0_004__weapon_grip_device_male'].objects
             if obj.type == 'MESH')
    arms['Left'] = [silver]
    arms['Right'].append(grip)
    support = add_deformers(rig, arms, parents)
    rest = {name: rigid(STUDIO @ ARM_UNITS @ rig.data.bones[name].matrix_local)
            for name in parents if name != 'root'}
    parents.update({name: 'root' if name == 'weapon_offset' else 'weapon_offset' for name in weapon.parts})
    ids = {name: i for i, name in enumerate(parents)}
    gun, = (obj for obj in import_gltf(directory / f'{weapon_name}.glb').values()
            if obj.type == 'MESH' and obj.parent and obj.parent.type == 'ARMATURE')
    idle = import_clip(directory / weapon_name / 'idle.glb')
    scene.frame_set(0)
    only_core = {name: parent for name, parent in parents.items() if name not in support}
    idle_pose = frame_pose(rig, idle, only_core, weapon.parts)
    rest.update({name: idle_pose[name] for name in ('root', *weapon.parts)})
    output.mkdir(parents=True)
    image_file(bpy.data.images['a0_000_ma__c_base_hq_d01'], output / 'skin.png')
    for suffix, file in [('color', 'weapon-color.webp'), ('ORM', 'weapon-orm.webp'), ('normal', 'weapon-normal.webp')]:
        image_file(bpy.data.images[f'{weapon.material} {suffix}'], output / file)
    materials = {'skin.png': {'metallic': 0., 'roughness': .61}, 'weapon-color.webp': {
        'metallic': 1., 'roughness': 1., 'normal': 'weapon-normal.webp', 'orm': 'weapon-orm.webp'}}
    arm_textures = {}
    for obj, name, size in ((silver, 'silverhand', 512), (grip, 'grip-implant', 256)):
        tex, spec = bake_material(obj, output, name, size)
        arm_textures[obj.name] = tex
        materials[tex] = spec
    (output / 'materials.json').write_text(json.dumps(materials), encoding='utf-8')
    anchor = gun.matrix_world.inverted() @ gun.parent.matrix_world @ gun.parent.data.bones['weapon_offset'].head_local
    weapon_pose = STUDIO @ idle['wpn'].matrix_world @ Matrix.Translation(-anchor)
    slot = next(i for i, material in enumerate(gun.data.materials) if material.name == weapon.material)
    weapons = list(triangles(gun, weapon_pose, 'weapon-color.webp', ids, 'weapon_offset', slot))
    if 'silencer' in ids:
        def detachable(tri):
            return all(corner[3][0][0] == ids['silencer'] for corner in tri[1])
        write_smd(output / 'silencer_mesh.smd', parents, [rest], (tri for tri in weapons if detachable(tri)))
        weapons = [tri for tri in weapons if not detachable(tri)]
    write_smd(output / 'weapon_mesh.smd', parents, [rest], weapons)
    for side, objects in arms.items():
        geometry = [tri for obj in objects for tri in triangles(obj, STUDIO @ ARM_UNITS @ obj.matrix_world,
                                                                  arm_textures.get(obj.name, 'skin.png'), ids, side + 'ForeArm')]
        write_smd(output / f'{side.lower()}_mesh.smd', parents, [rest], geometry)
        print(f'{side}: {len(geometry)} tris originales', flush=True)
    write_smd(output / 'skin_bind.smd', parents, [rest])
    events = {}
    for name in WEAPON_CLIPS[weapon_name]:
        path = directory / weapon_name / f'{name}.glb'
        nodes = idle if name == 'idle' else import_clip(path)
        poses, visible = zip(*bake_sequence(path, rig, nodes, only_core, weapon.parts))
        write_smd(output / f'{name}.smd', parents, (pose_with_support(p, rest, support) for p in poses))
        if name.startswith('silencer_'):
            events[name] = [(i / FPS, value) for i, value in enumerate(visible) if i == 0 or value != visible[i-1]]
            if len(events[name]) != 2:
                raise ValueError(f'Transición del silenciador no encontrada: {name}')
        for node in nodes.values():
            bpy.data.objects.remove(node, do_unlink=True)
        print(f'{name}: {len(poses)} fotogramas', flush=True)
    if events:
        (output / 'silencer-events.json').write_text(json.dumps(events), encoding='utf-8')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--assets', type=Path, default=ROOT / 'third_party_assets')
    p.add_argument('--weapon', choices=WEAPONS, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    build(args.assets.resolve(), args.output.resolve(), args.weapon)


if __name__ == '__main__':
    main()
