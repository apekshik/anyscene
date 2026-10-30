"""Render preview stills of a repair .blend from named cameras.

blender -b <file.blend> --python scenes/tokyo-electronics-repair/scripts/preview.py -- <out_dir> <cam1,cam2> [samples=32] [pct=50] [clay] [tag]
Run through pipeline/gpu_run.sh.
"""
import os
import sys

import bpy

args = sys.argv[sys.argv.index("--") + 1:]
out, cams = os.path.abspath(args[0]), args[1].split(",")
samples = int(args[2]) if len(args) > 2 else 32
pct = int(args[3]) if len(args) > 3 else 50
clay = len(args) > 4 and args[4] == "clay"
tag = args[5] if len(args) > 5 else ""

sc = bpy.context.scene
sc.render.engine = "CYCLES"
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "OPTIX"
prefs.get_devices()
for d in prefs.devices:
    d.use = d.type == "OPTIX"
sc.cycles.device = "GPU"
sc.cycles.samples = samples
sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
sc.render.resolution_percentage = pct
if clay:
    m = bpy.data.materials.new("clay_override")
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.6, 0.6, 0.6, 1)
    sc.view_layers[0].material_override = m
    if sc.world is None or not sc.world.node_tree:
        w = bpy.data.worlds.new("clayworld")
        sc.world = w
    bg = sc.world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Strength"].default_value = 1.0
    sc.view_settings.view_transform = "AgX"
    # light the clay with a sun so the shell reads even without the night rig
    if not bpy.data.objects.get("clay_fill"):
        ld = bpy.data.lights.new("clay_fill", "AREA")
        ld.shape = "RECTANGLE"
        ld.size, ld.size_y, ld.energy = 3.5, 5.5, 380
        o = bpy.data.objects.new("clay_fill", ld)
        sc.collection.objects.link(o)
        o.location = (2.1, 3.3, 2.55)
        for l in [x for x in bpy.data.objects if x.type == "LIGHT" and x is not o]:
            l.hide_render = True
    sc.render.use_compositing = False
os.makedirs(out, exist_ok=True)
for c in cams:
    sc.camera = bpy.data.objects[c]
    sc.render.filepath = os.path.join(out, f"{c}{'_clay' if clay else ''}{tag}.png")
    bpy.ops.render.render(write_still=True)
    print("wrote", sc.render.filepath)
