"""Cycles reference frames for the Unreal comparison: scene cameras at one frame, plus an optional push-in clip that
matches build_level.py's ANYSCENE_DOLLY="cam>fwdN:frames" (camera moved N cm along its view axis, linearly).
    blender -b <copy.blend> --python render_cycles_refs.py -- --out <dir> --cams a,b,c [--frame 60] [--res 1920x804]
            [--spp 128] [--dolly cam:150:96] [--dolly-res 960x402] [--dolly-spp 32] [--dolly-from F] [--gpu]
Writes <out>/<cam>.png (the scene's view transform, e.g. AgX) and <out>/dolly/<frame>.png. Never saves the .blend.
"""
import os
import sys
import time

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]


def arg(n, d=None):
    return argv[argv.index(n) + 1] if n in argv else d


OUT = arg("--out")
CAMS = [c for c in arg("--cams", "").split(",") if c]
FRAME = int(arg("--frame", "60"))
W, H = (int(x) for x in arg("--res", "1920x804").split("x"))
SPP = int(arg("--spp", "128"))
sc = bpy.context.scene
sc.render.engine = "CYCLES"
if "--gpu" in argv:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == "OPTIX"
    sc.cycles.device = "GPU"
sc.cycles.samples = SPP
sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, H, 100
sc.render.image_settings.file_format = "PNG"
os.makedirs(OUT, exist_ok=True)
sc.frame_set(FRAME)
for c in CAMS:
    t = time.time()
    sc.camera = bpy.data.objects[c]
    sc.render.filepath = os.path.join(OUT, c + ".png")
    bpy.ops.render.render(write_still=True)
    print("REF", c, FRAME, f"{time.time() - t:.1f}s", flush=True)
if arg("--dolly"):
    cam, dist, n = arg("--dolly").split(":")
    src = bpy.data.objects[cam]
    o = src.copy()
    o.data = src.data.copy()
    o.data.dof.use_dof = False  # the Unreal dolly camera has DOF off
    o.animation_data_clear()
    sc.collection.objects.link(o)
    mw = src.matrix_world.copy()
    fwd = (mw.to_3x3() @ __import__("mathutils").Vector((0, 0, -1))).normalized()
    p0 = mw.translation.copy()
    dw, dh = (int(x) for x in arg("--dolly-res", "960x402").split("x"))
    sc.render.resolution_x, sc.render.resolution_y = dw, dh
    sc.cycles.samples = int(arg("--dolly-spp", "32"))
    sc.camera = o
    d = os.path.join(OUT, "dolly")
    os.makedirs(d, exist_ok=True)
    n = int(n)
    step = int(arg("--dolly-step", "1"))
    for f in range(int(arg("--dolly-from", "0")), n + 1, step):
        sc.frame_set(FRAME + f)
        m = mw.copy()
        m.translation = p0 + fwd * (float(dist) / 100.0) * f / n
        o.matrix_world = m
        sc.render.filepath = os.path.join(d, f"{f:04d}.png")
        t = time.time()
        bpy.ops.render.render(write_still=True)
        print("DOLLY", f, f"{time.time() - t:.1f}s", flush=True)
