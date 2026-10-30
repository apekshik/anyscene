"""Render a frame range of the handheld clip (run in chunks through pipeline/gpu_run.sh so the GPU is shared).

blender -b scenes/tokyo-electronics-repair/repair_final.blend --python scenes/tokyo-electronics-repair/scripts/render_frames.py -- <first> <last> [samples=96] [pct=100]
-> scenes/tokyo-electronics-repair/out/clip_frames/f####.png (existing frames are skipped)
"""
import os
import sys

import bpy

a = sys.argv[sys.argv.index("--") + 1:]
first, last = int(a[0]), int(a[1])
samples = int(a[2]) if len(a) > 2 else 96
pct = int(a[3]) if len(a) > 3 else 100
out = r"$ROOT_ABS\scenes\repair\out\clip_frames"
os.makedirs(out, exist_ok=True)
sc = bpy.context.scene
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "OPTIX"
prefs.get_devices()
for d in prefs.devices:
    d.use = d.type == "OPTIX"
sc.cycles.device = "GPU"
sc.cycles.samples = samples
sc.cycles.use_adaptive_sampling = True
sc.cycles.adaptive_threshold = 0.02
sc.render.resolution_percentage = pct
sc.camera = bpy.data.objects["cam_handheld"]
sc.render.use_persistent_data = True  # keep BVH + textures between frames
for f in range(first, last + 1):
    path = os.path.join(out, f"f{f:04d}.png")
    if os.path.exists(path):
        continue
    sc.frame_set(f)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("frame", f, flush=True)
