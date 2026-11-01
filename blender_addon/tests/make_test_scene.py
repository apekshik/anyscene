"""Build the add-on's test scene: a few animated objects, an external image texture (to exercise packing), a sun and
an area light, a moving camera, 48 frames at 640x360, Cycles at 32 spp with a fixed seed and no denoiser.

    blender -b --factory-startup --python make_test_scene.py -- <dir>

Writes <dir>/test_scene.blend and <dir>/tex/checker.png; output path is //renders/test_#### (relative on purpose).
"""

import math
import os
import sys

import bpy

out_dir = os.path.abspath(sys.argv[sys.argv.index("--") + 1])
os.makedirs(os.path.join(out_dir, "tex"), exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.name = "FarmTest"

# external texture, saved next to the .blend and referenced relatively -> must be packed for the farm
tex_path = os.path.join(out_dir, "tex", "checker.png")
img = bpy.data.images.new("checker", 256, 256)
px = []
for y in range(256):
    for x in range(256):
        c = 0.9 if ((x // 32) + (y // 32)) % 2 else 0.1
        px += [c, 0.35 + 0.5 * (x / 255), 1.0 - c * 0.6, 1.0]
img.pixels = px
img.filepath_raw = tex_path
img.file_format = "PNG"
img.save()


def material(name, color=None, image=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    if image:
        t = m.node_tree.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(tex_path)
        m.node_tree.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = 0.35
    return m


bpy.data.images.remove(img)  # the material loads it back from disk, as a normal external image

bpy.ops.mesh.primitive_plane_add(size=20)
bpy.context.object.data.materials.append(material("floor", image=True))

bpy.ops.mesh.primitive_cube_add(size=1.5, location=(-2, 0, 0.75))
cube = bpy.context.object
cube.data.materials.append(material("red", (0.8, 0.1, 0.08)))
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.9, location=(0.5, 1.5, 0.9))
sphere = bpy.context.object
bpy.ops.object.shade_smooth()
sphere.data.materials.append(material("blue", (0.1, 0.3, 0.9)))
bpy.ops.mesh.primitive_monkey_add(size=1.4, location=(2.2, -0.8, 1.0))
monkey = bpy.context.object
bpy.ops.object.shade_smooth()
monkey.data.materials.append(material("gold", (0.9, 0.65, 0.2)))

for f, z_rot, sz in ((1, 0, 0.9), (48, 2 * math.pi, 2.6)):
    scene.frame_set(f)
    cube.rotation_euler.z = z_rot
    cube.keyframe_insert("rotation_euler", index=2)
    sphere.location.z = sz
    sphere.keyframe_insert("location", index=2)
    monkey.rotation_euler.z = -z_rot / 2
    monkey.keyframe_insert("rotation_euler", index=2)

bpy.ops.object.light_add(type="SUN", rotation=(math.radians(50), 0, math.radians(30)))
bpy.context.object.data.energy = 3
bpy.ops.object.light_add(type="AREA", location=(-3, -4, 4))
bpy.context.object.data.energy = 400
bpy.context.object.data.size = 3

bpy.ops.object.camera_add(location=(0, -9, 4))
cam = bpy.context.object
scene.camera = cam
for f, x in ((1, -2.0), (48, 2.0)):
    cam.location.x = x
    cam.keyframe_insert("location", index=0, frame=f)
con = cam.constraints.new("TRACK_TO")
bpy.ops.object.empty_add(location=(0, 0, 0.8))
con.target = bpy.context.object

world = bpy.data.worlds.new("World")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.07, 0.1, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
scene.world = world

r = scene.render
r.engine = "CYCLES"
scene.cycles.samples = 32
scene.cycles.use_adaptive_sampling = False
scene.cycles.use_denoising = False
scene.cycles.seed = 0
r.resolution_x, r.resolution_y, r.resolution_percentage = 640, 360, 100
r.fps = 24
scene.frame_start, scene.frame_end = 1, 48
r.image_settings.file_format = "PNG"
r.image_settings.color_mode = "RGBA"
r.filepath = "//renders/test_####"
scene.frame_set(1)

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, "test_scene.blend"), relative_remap=True)
bpy.ops.file.make_paths_relative()  # the texture becomes //tex/checker.png, like a real project
bpy.ops.wm.save_mainfile()
print("TEST-SCENE:", os.path.join(out_dir, "test_scene.blend"))
