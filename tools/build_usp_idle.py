"""Blender 4.5+: convierte una pose USP-S/MultiRig en fuentes GoldSrc."""

import argparse
from collections import Counter
from pathlib import Path
import struct
import sys

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
UNITS = 1.0 / 0.0254  # Metros del MultiRig a unidades del clip de cs2go.
TO_STUDIO = Matrix(((1, 0, 0), (0, 0, 1), (0, -1, 0)))
SMD_HEADER = 'version 1\nnodes\n0 "root" -1\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\nend\n'
# El compilador clásico limita las posiciones y normales de cada submodelo.
MAX_COMPONENTS = 1800


def import_gltf(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return {obj.name: obj for obj in set(bpy.data.objects) - before}


def basis(forward, side):
    forward = forward.normalized()
    normal = forward.cross(side).normalized()
    return Matrix((forward, normal.cross(forward), normal)).transposed()


def retarget_arms(rig, nodes):
    # El rig original tiene ciclos de IK en 4.5. Trabajar con los huesos deformantes
    # directamente y hornear su resultado; no se modifica el .blend de origen.
    rig.animation_data_clear()
    # Los segmentos de los dos rigs no tienen exactamente la misma longitud.
    # Desconectar estas articulaciones permite colocar sus orígenes sin que
    # Blender fuerce la muñeca a la cola del hueso padre.
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    for prefix in ('Left', 'Right'):
        for name in ('Arm', 'ForeArm', 'Hand'):
            rig.data.edit_bones[prefix + name].use_connect = False
    bpy.ops.object.mode_set(mode='OBJECT')
    for bone in rig.pose.bones:
        for constraint in list(bone.constraints):
            bone.constraints.remove(constraint)
        bone.matrix_basis.identity()
    bpy.context.view_layer.update()

    def source(name):
        return nodes[name].matrix_world.translation / UNITS

    def rest(name):
        return rig.data.bones[name].head_local

    def place(name, rotation, head):
        target = (rotation @ rig.data.bones[name].matrix_local.to_3x3()).to_4x4()
        target.translation = head
        rig.pose.bones[name].matrix = target
        bpy.context.view_layer.update()

    for side, prefix in (("L", "Left"), ("R", "Right")):
        upper, lower, wrist = (prefix + name for name in ("Arm", "ForeArm", "Hand"))
        s0, s1, s2 = [source(f"{name}_{side}") for name in ("arm_upper", "arm_lower", "hand")]
        r0, r1, r2 = [rest(name) for name in (upper, lower, wrist)]
        # Orientar brazo y antebrazo con referencia al plano definido por el codo.
        for name, a, b, ra, rb, across, rest_across in (
            (upper, s0, s1, r0, r1, s2 - s1, r2 - r1),
            (lower, s1, s2, r1, r2, s1 - s0, r1 - r0),
        ):
            place(name, basis(b - a, across) @ basis(rb - ra, rest_across).transposed(), a)
        index, pinky = (source(f"finger_{name}_0_{side}") for name in ("index", "pinky"))
        ri, rp = (rest(wrist + name) for name in ("Index1", "Pinky1"))
        place(wrist, basis((index + pinky) / 2 - s2, index - pinky)
              @ basis((ri + rp) / 2 - r2, ri - rp).transposed(), s2)

        # Conservar las longitudes y los nudillos del MultiRig; transferir sólo
        # las direcciones de las falanges desde el clip, no sus traslaciones.
        for digit in ("Index", "Middle", "Ring", "Pinky", "Thumb"):
            for i in range(2 if digit == "Thumb" else 3):
                bone = rig.pose.bones[f"{wrist}{digit}{i + 1}"]
                joint = f"finger_{digit.lower()}_{i}_{side}"
                if i < 2:
                    direction = source(f"finger_{digit.lower()}_{i + 1}_{side}") - source(joint)
                else:
                    # Eje longitudinal del nodo terminal del clip (especular).
                    direction = nodes[joint].matrix_world.to_3x3().col[0] * (1 if side == "L" else -1)
                axis = (bone.tail - bone.head).normalized()
                matrix = (axis.rotation_difference(direction.normalized()).to_matrix()
                          @ bone.matrix.to_3x3()).to_4x4()
                matrix.translation = bone.head
                bone.matrix = matrix
                bpy.context.view_layer.update()


def indexed_colors(pixels):
    """Selecciona una paleta adaptada a los colores de cada textura."""
    hist = Counter(pixels)

    def stats(colors):
        count = sum(hist[c] for c in colors)
        ranges = [max(c[i] for c in colors) - min(c[i] for c in colors) for i in range(3)]
        channel = max(range(3), key=ranges.__getitem__)
        return ranges[channel] * count**0.5, channel, count, colors

    boxes = [stats(list(hist))]
    while len(boxes) < 256:
        largest = max(range(len(boxes)), key=lambda i: boxes[i][0])
        score, channel, count, colors = boxes[largest]
        if not score:
            break
        colors.sort(key=lambda c: c[channel])
        cumulative = 0
        for split in range(1, len(colors)):
            cumulative += hist[colors[split - 1]]
            if cumulative * 2 >= count:
                break
        boxes[largest] = stats(colors[:split])
        boxes.append(stats(colors[split:]))

    palette, lookup = bytearray(256 * 4), {}
    for i, (_, _, count, colors) in enumerate(boxes):
        for j, channel in enumerate((2, 1, 0)):
            palette[4 * i + j] = round(sum(c[channel] * hist[c] for c in colors) / count)
        lookup.update((c, i) for c in colors)
    return palette, bytes(lookup[c] for c in pixels)


def image_bmp(image, path, size=256):
    """BMP indexado de 8 bits, filas de abajo hacia arriba."""
    tmp = image.copy()
    try:
        tmp.scale(size, size)
        pixels = tuple(tmp.pixels)
    finally:
        bpy.data.images.remove(tmp)
    if len(pixels) != size * size * 4:
        raise ValueError(f"No se pudo leer {image.name}")
    # Blender conserva los canales de imágenes byte en sRGB.
    rgb = [tuple(round(min(1, max(0, v)) * 255) for v in pixels[i:i + 3])
           for i in range(0, len(pixels), 4)]
    palette, indices = indexed_colors(rgb)
    offset = 14 + 40 + len(palette)
    path.write_bytes(struct.pack('<2sIHHI', b'BM', offset + len(indices), 0, 0, offset)
                     + struct.pack('<IiiHHIIiiII', 40, size, size, 1, 8, 0, len(indices), 0, 0, 256, 0)
                     + palette + indices)


def triangles(obj, transform, texture, simplify, weight_bone=None, material_slot=None):
    # Obtener primero la pose deformada. Decimar una copia sin el armature
    # (y sin tocar las mallas originales); así no se pierden los pesos del .blend.
    deps = bpy.context.evaluated_depsgraph_get()
    copy = bpy.data.meshes.new_from_object(obj.evaluated_get(deps), depsgraph=deps)
    baked = bpy.data.objects.new("GoldSrc scratch", copy)
    bpy.context.scene.collection.objects.link(baked)
    try:
        if weight_bone:
            for group in obj.vertex_groups:
                baked.vertex_groups.new(name=group.name)
        decimate = baked.modifiers.new("GoldSrc polycount", 'DECIMATE')
        decimate.ratio = simplify
        geo = baked.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = geo.to_mesh()
        try:
            mesh.calc_loop_triangles()
            uv_layer = mesh.uv_layers.active.data
            normals = mesh.corner_normals
            normal_matrix = transform.to_3x3().inverted().transposed()
            bones = [weight_bone(v) for v in mesh.vertices] if weight_bone else None
            for tri in mesh.loop_triangles:
                if material_slot is not None and tri.material_index != material_slot:
                    continue
                corners = []
                for loop, vert in zip(tri.loops, tri.vertices):
                    pos = tuple(round(x, 6) for x in transform @ mesh.vertices[vert].co)
                    norm = tuple(round(x, 6) for x in (normal_matrix @ normals[loop].vector).normalized())
                    corner = (pos, norm, tuple(uv_layer[loop].uv))
                    corners.append((*corner, bones[vert]) if bones is not None else corner)
                yield texture, tuple(corners)
        finally:
            geo.to_mesh_clear()
    finally:
        bpy.data.objects.remove(baked, do_unlink=True)
        bpy.data.meshes.remove(copy)


def parts(tris):
    current, positions, normals = [], set(), set()
    for texture, corners in tris:
        p = {(corner[0], *corner[3:]) for corner in corners}
        n = {(texture, corner[1], *corner[3:]) for corner in corners}
        if len(positions | p) > MAX_COMPONENTS or len(normals | n) > MAX_COMPONENTS:
            yield current
            current, positions, normals = [], set(), set()
        current.append((texture, corners))
        positions.update(p)
        normals.update(n)
    if current:
        yield current


def write_smd(path, tris):
    with path.open('w', encoding='ascii', newline='\n') as stream:
        stream.write(SMD_HEADER + 'triangles\n')
        for texture, corners in tris:
            stream.write(texture + '\n')
            for pos, normal, uv in corners:
                stream.write('0 ' + ' '.join(f'{x:.6f}' for x in (*pos, *normal, *uv)) + '\n')
        stream.write('end\n')


def build(assets, output):
    bpy.ops.wm.open_mainfile(filepath=str(assets / 'multirig/Cyberpunk_Rig.blend'), use_scripts=False)
    rig = bpy.data.objects['Rig']
    gun_nodes = import_gltf(assets / 'cs2go/viewmodels/usp-s.glb')
    gun_mesh, = (o for o in gun_nodes.values() if o.type == 'MESH' and o.parent and o.parent.type == 'ARMATURE')
    clip = import_gltf(assets / 'cs2go/viewmodels/usp-s/idle.glb')
    bpy.context.scene.frame_set(0)
    retarget_arms(rig, clip)

    # El GLB de arma se importa en metros, pero sus vértices locales ya están
    # en unidades del clip. Centrarlo en el hueso weapon_offset y montarlo en wpn.
    gun_rig = gun_mesh.parent
    anchor = gun_mesh.matrix_world.inverted() @ gun_rig.matrix_world @ gun_rig.data.bones['weapon_offset'].head_local
    gun_transform = TO_STUDIO.to_4x4() @ clip['wpn'].matrix_world @ Matrix.Translation(-anchor)
    arms_transform = TO_STUDIO.to_4x4() @ Matrix.Diagonal((UNITS, UNITS, UNITS, 1))
    arm_tex, gun_tex = 'arms.bmp', 'usp.bmp'
    sources = {'usp': triangles(gun_mesh, gun_transform, gun_tex, 0.19)}
    for side in ('Left', 'Right'):
        # Sólo antebrazos y manos de la variante estándar: los hombros quedan
        # fuera de cámara y conservan pesos de torso que no usa esta prueba.
        objects = [o for o in bpy.data.collections[f'Arm {side}'].objects
                   if o.type == 'MESH' and o.name.startswith(('submesh_01_', 'submesh_02_'))]
        if len(objects) != 2:
            raise ValueError(f'Faltan las dos mallas de antebrazo y mano: {side}')
        sources[side.lower()] = (tri for o in objects for tri in
                                 triangles(o, arms_transform @ o.matrix_world, arm_tex, 0.37))

    output.mkdir(parents=True, exist_ok=False)
    image_bmp(bpy.data.images['a0_000_ma__c_base_hq_d01'], output / arm_tex)
    image_bmp(bpy.data.images['pist_223 color'], output / gun_tex)
    qc = ['$modelname "v_dawe_usp_idle.mdl"', '$cd "."', '$cdtexture "."', '$scale 1', '$origin 0 0 0 270']
    count = 0
    for name, tris in sources.items():
        for i, chunk in enumerate(parts(tris), 1):
            part = f'{name}_{i}'
            write_smd(output / f'{part}.smd', chunk)
            count += len(chunk)
            qc.append(f'$body "{part}" "{part}"')
    if not count:
        raise ValueError('No se generaron triángulos')
    (output / 'idle.smd').write_text(SMD_HEADER, encoding='ascii')
    qc.append('$sequence "idle" "idle" fps 30 loop')
    (output / 'usp_idle.qc').write_text('\n'.join(qc) + '\n', encoding='ascii')
    print(f'{count} triángulos de exportación. QC: {output / "usp_idle.qc"}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, default=ROOT / 'third_party_assets')
    parser.add_argument('--output', type=Path, default=ROOT / 'third_party_assets' / 'usp_idle_goldsrc')
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    args = parser.parse_args(argv)
    build(args.assets.resolve(), args.output.resolve())


if __name__ == '__main__':
    main()
