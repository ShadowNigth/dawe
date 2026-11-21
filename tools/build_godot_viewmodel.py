"""Blender 4.5+: bake a smooth, full-geometry MultiRig viewmodel for Godot."""
import argparse
import json
from pathlib import Path
import sys
import struct
import subprocess
import tempfile

import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_viewmodel import (ARM_UNITS, FPS, ROOT, STUDIO, WEAPONS, Weapon, arm_names, frame_pose,
                             bake_sequence, import_clip, import_gltf, rigid, write_smd)
from import_assets import GODOT_WEAPON_CLIPS
from bake_multirig_material import bake_material
from retarget_godot_arms import GripRetarget
from fit_godot_grip import RightGrip

# This mesh references an auxiliary joint absent from the distributed rig.
JOINT_ALIASES = {'LeftInHandThumb': 'LeftHand'}
M4A4 = Weapon('m4a4', 'rif_m4a1', ('weapon_offset', 'bolt', 'clip', 'trigger'))
BAYONET = Weapon('bayonet', 'Bayonet worn steel and olive grip', ('weapon_offset',))


def import_weapon_mesh(path):
    with path.open('rb') as source:
        source.seek(12)
        size, _ = struct.unpack('<II', source.read(8))
        doc = json.loads(source.read(size))
    if 'EXT_meshopt_compression' not in doc.get('extensionsUsed', []):
        return import_gltf(path)
    with tempfile.TemporaryDirectory(prefix='dawe-meshopt-') as temp:
        folder = Path(temp)
        layout, data = folder / 'mesh.json', folder / 'mesh.bin'
        decoder = ROOT / 'tools/agent_assets/decode_meshopt.mjs'
        subprocess.run(['node', str(decoder), str(path), str(layout), str(data)], check=True)
        doc = json.loads(layout.read_bytes())
        for key in ('extensionsUsed', 'extensionsRequired'):
            if 'EXT_meshopt_compression' in doc.get(key, []):
                doc[key].remove('EXT_meshopt_compression')
        json_chunk = json.dumps(doc, separators=(',', ':')).encode()
        json_chunk += b' ' * (-len(json_chunk) % 4)
        binary = data.read_bytes()
        glb = folder / path.name
        glb.write_bytes(struct.pack('<4sII', b'glTF', 2, 28 + len(json_chunk) + len(binary))
                        + struct.pack('<I4s', len(json_chunk), b'JSON') + json_chunk
                        + struct.pack('<I4s', len(binary), b'BIN\0') + binary)
        return import_gltf(glb)


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
        # One shared hinge at the wrist: blending two translated points pulls
        # the skin toward the axis of rotation, pinching the joint.
        pose[name].translation = pose[hand].translation + orient @ (arm_rest.translation - rest[hand].translation)
    return pose


def build(assets, output, weapon_name):
    if output.exists():
        raise FileExistsError(output)
    knife = weapon_name == 'bayonet'
    weapon = {**WEAPONS, 'bayonet': BAYONET, 'm4a4': M4A4}[weapon_name]
    cs2go = assets / 'cs2go'
    mesh_path = cs2go / ('bayonet.glb' if knife else f'viewmodels/{weapon_name}.glb')
    clips = cs2go / (f'animations/{weapon_name}' if knife else f'viewmodels/{weapon_name}')
    idle_name = 'idle1' if knife else 'idle'
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
    gun, = (obj for obj in import_weapon_mesh(mesh_path).values() if obj.type == 'MESH'
            and (knife or (obj.parent and obj.parent.type == 'ARMATURE')))
    idle = import_clip(clips / f'{idle_name}.glb')
    scene.frame_set(0)
    only_core = {name: parent for name, parent in parents.items() if name not in support}
    idle_pose = frame_pose(rig, idle, only_core, weapon.parts)
    rest.update({name: idle_pose[name] for name in ('root', *weapon.parts)})
    GripRetarget(rest, idle_pose).apply(idle_pose, 'idle')
    output.mkdir(parents=True)
    image_file(bpy.data.images['a0_000_ma__c_base_hq_d01'], output / 'skin.png')
    weapon_surface = {'metallic': 1., 'roughness': 1., 'orm': 'weapon-orm.webp'}
    if knife:
        image_file(bpy.data.images['Bayonet color'], output / 'weapon-color.webp')
        image_file(bpy.data.images['Bayonet occlusion roughness metalness'], output / 'weapon-orm.webp')
    else:
        for suffix, file in [('color', 'weapon-color.webp'), ('ORM', 'weapon-orm.webp'), ('normal', 'weapon-normal.webp')]:
            image_file(bpy.data.images[f'{weapon.material} {suffix}'], output / file)
        weapon_surface['normal'] = 'weapon-normal.webp'
    materials = {'skin.png': {'metallic': 0., 'roughness': .61}, 'weapon-color.webp': weapon_surface}
    arm_textures = {}
    for obj, name, size in ((silver, 'silverhand', 512), (grip, 'grip-implant', 256)):
        tex, spec = bake_material(obj, output, name, size)
        arm_textures[obj.name] = tex
        materials[tex] = spec
    (output / 'materials.json').write_text(json.dumps(materials), encoding='utf-8')
    if knife:
        # glTF extras store a column-major change to the clip's weapon space.
        columns = gun['meshToSource']
        mesh_to_source = Matrix([columns[i:i+4] for i in range(0, 16, 4)]).transposed()
        weapon_pose = rest['weapon_offset'] @ STUDIO.inverted() @ mesh_to_source @ STUDIO @ gun.matrix_world
    else:
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
    arm_geometry = {}
    for side, objects in arms.items():
        geometry = [tri for obj in objects for tri in triangles(obj, STUDIO @ ARM_UNITS @ obj.matrix_world,
                                                                  arm_textures.get(obj.name, 'skin.png'), ids, side + 'ForeArm')]
        arm_geometry[side] = geometry
        write_smd(output / f'{side.lower()}_mesh.smd', parents, [rest], geometry)
        print(f'{side}: {len(geometry)} tris originales', flush=True)
    grip_fit = RightGrip(weapons, arm_geometry['Right'], parents, rest)
    grip_fit.fit(idle_pose, lambda pose: pose_with_support(pose, rest, support))
    grip_fit.apply(idle_pose)
    write_smd(output / 'skin_bind.smd', parents, [rest])
    events = {}
    for name in GODOT_WEAPON_CLIPS[weapon_name]:
        path = clips / f'{name}.glb'
        nodes = idle if name == idle_name else import_clip(path)
        poses, visible = zip(*bake_sequence(path, rig, nodes, only_core, weapon.parts, allow_short_secondary=weapon_name in ('bayonet', 'm4a4')))
        retarget = GripRetarget(rest, idle_pose)
        def stable_poses():
            for i, pose in enumerate(poses):
                settle = max(0.0, 1.0 - (len(poses) - 1 - i) / 12) if len(poses) > 12 else 0.0
                settle = settle * settle * (3 - 2 * settle)
                retarget.apply(pose, 'idle' if name == idle_name else name, 0.0 if knife else settle, lock_right=not knife)
                if name != 'shoot1':  # Recoil already follows the corrected idle grip.
                    grip_fit.apply(pose)
                yield pose_with_support(pose, rest, support)

        write_smd(output / f'{name}.smd', parents, stable_poses())
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
    p.add_argument('--weapon', choices=GODOT_WEAPON_CLIPS, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    build(args.assets.resolve(), args.output.resolve(), args.weapon)


if __name__ == '__main__':
    main()
