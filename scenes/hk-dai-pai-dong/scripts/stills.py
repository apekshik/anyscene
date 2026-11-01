"""Final hero stills from hk.blend (cameras cam_<name> from build.py): 1920x804, 64 spp, glare on, no motion blur.
blender -b scenes/hk-dai-pai-dong/hk.blend --python .../gpu_prefs.py --python .../stills.py -- street,wok,table,flame
"""
import os
import sys
import time

import bpy

names = sys.argv[sys.argv.index("--") + 1].split(",")
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1920, 804, 100
sc.cycles.samples = 64
sc.render.use_motion_blur = False
sc.frame_set(60)
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", "stills")
os.makedirs(out, exist_ok=True)
for n in names:
    cam = bpy.data.objects["cam_" + n]
    cam.data.dof.use_dof = True
    cam.data.dof.aperture_fstop = 2.8
    cam.data.dof.focus_distance = {"street": 9.5, "wok": 1.5, "table": 2.4, "flame": 0.95}.get(n, 3.0)
    sc.camera = cam
    sc.render.filepath = os.path.join(out, f"{n}.png")
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    print(f"STILL {n} {time.time() - t0:.0f}s", flush=True)
