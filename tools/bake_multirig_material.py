"""Flatten a MultiRig Cycles material to the texture channels used by Godot."""
import bpy


def bake_material(source, output, stem, size):
    window = bpy.context.window
    original = window.scene
    scene = bpy.data.scenes.new('Dawe material bake')
    window.scene = scene
    mesh = source.data.copy()
    obj = bpy.data.objects.new('Bake mesh', mesh)
    mat = source.data.materials[0].copy()
    images = []
    try:
        scene.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        mesh.materials[0] = mat
        scene.render.engine = 'CYCLES'
        scene.cycles.device = 'CPU'
        scene.cycles.samples = 1
        scene.render.threads_mode = 'FIXED'
        scene.render.threads = 4
        tree = mat.node_tree
        bsdf = tree.nodes['Principled BSDF']
        surface = tree.nodes['Material Output'].inputs['Surface']
        emission = tree.nodes.new('ShaderNodeEmission')
        rgb = tree.nodes.new('ShaderNodeCombineColor')
        target = tree.nodes.new('ShaderNodeTexImage')

        def connect(source, dest):
            for link in list(dest.links):
                tree.links.remove(link)
            if source.is_linked:
                tree.links.new(source.links[0].from_socket, dest)
            else:
                dest.default_value = source.default_value

        def bake(suffix, kind, colorspace):
            name = f'{stem}{suffix}.png'
            img = bpy.data.images.new(name, width=size, height=size, alpha=False)
            images.append(img)
            img.colorspace_settings.name = colorspace
            target.image = img
            tree.nodes.active = target
            result = bpy.ops.object.bake(type=kind, margin=8, margin_type='EXTEND')
            if 'FINISHED' not in result:
                raise RuntimeError(f'No se pudo hornear {name}')
            img.file_format = 'PNG'
            img.filepath_raw = str(output / name)
            img.save()
            return name

        tree.links.new(emission.outputs[0], surface)
        connect(bsdf.inputs['Base Color'], emission.inputs['Color'])
        color = bake('', 'EMIT', 'sRGB')
        rgb.inputs[0].default_value = 1.0  # No occlusion channel in the layered source.
        connect(bsdf.inputs['Roughness'], rgb.inputs[1])
        connect(bsdf.inputs['Metallic'], rgb.inputs[2])
        tree.links.new(rgb.outputs[0], emission.inputs['Color'])
        orm = bake('-orm', 'EMIT', 'Non-Color')
        tree.links.new(bsdf.outputs[0], surface)
        normal = bake('-normal', 'NORMAL', 'Non-Color')
        return color, {'metallic': 1.0, 'roughness': 1.0, 'orm': orm, 'normal': normal}
    finally:
        window.scene = original
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)
        bpy.data.materials.remove(mat)
        for img in images:
            bpy.data.images.remove(img)
        bpy.data.scenes.remove(scene)
