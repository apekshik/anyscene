"""Renders from the saved (steam-baked) scenes/tokyo-ramen-shop/ramen.blend.

blender -b scenes/tokyo-ramen-shop/ramen.blend --python scenes/tokyo-ramen-shop/scripts/render.py -- stills wide,counter [--samples 256]
blender -b scenes/tokyo-ramen-shop/ramen.blend --python scenes/tokyo-ramen-shop/scripts/render.py -- prev wide,counter,kitchen --tag _x [--samples 32] [--res 960] [--frame 1] [--clay]
blender -b scenes/tokyo-ramen-shop/ramen.blend --python scenes/tokyo-ramen-shop/scripts/render.py -- clip 1 30 [--samples 96]
"""
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
mode = argv[0]


def opt(k, d=None, f=str):
    return f(argv[argv.index(k) + 1]) if k in argv else d


samples = opt("--samples", None, int)
sc = bpy.context.scene
OUT = os.path.join(os.path.dirname(bpy.data.filepath), "out")
if samples:
    sc.cycles.samples = samples
if mode in ("stills", "prev"):
    sc.frame_set(opt("--frame", 1, int))
    if mode == "prev":
        res = opt("--res", 960, int)
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = res, res * 9 // 16, 100
        sc.render.image_settings.color_depth = "8"
        if "--clay" in argv:
            m = bpy.data.materials.get("CLAY") or bpy.data.materials.new("CLAY")
            bpy.context.view_layer.material_override = m
    for k in argv[1].split(","):
        sc.camera = bpy.data.objects["cam_" + k]
        if mode == "prev":
            sc.render.filepath = os.path.join(OUT, "prev", f"{k}{opt('--tag', '')}.png")
        else:
            sc.render.filepath = os.path.join(OUT, "raw", f"hero_{k}.png")
        bpy.ops.render.render(write_still=True)
        print("STILL", sc.render.filepath, flush=True)
else:
    a, b = int(argv[1]), int(argv[2])
    sc.camera = bpy.data.objects["cam_clip"]
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    sc.render.use_persistent_data = True  # keep BVH + textures between frames
    sc.render.image_settings.color_depth = "8"
    for f in range(a, b + 1):
        p = os.path.join(OUT, "frames", f"{f:04d}.png")
        if os.path.exists(p):
            continue
        sc.frame_set(f)
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        print("FRAME", f, flush=True)
