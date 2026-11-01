"""Flame look-dev without a rebuild: replace the flame (and bulb) materials in an existing build with lights.py's current
ones and render the wok/flame cameras.
    bash scenes/hk-dai-pai-dong/scripts/blend.sh scenes/hk-dai-pai-dong/hk_ground.blend --python scenes/hk-dai-pai-dong/scripts/flame_try.py -- --tag _f5 [--frame 40] [--save]
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lights  # noqa: E402
from lib import SCENE_DIR  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
TAG = argv[argv.index("--tag") + 1] if "--tag" in argv else "_try"
sc = bpy.context.scene
sc.frame_set(int(argv[argv.index("--frame") + 1]) if "--frame" in argv else 40)

old = bpy.data.materials.get("flame_vol")
if old:
    old.name = "flame_vol_old"
m = lights.m_flame("flame_vol")
ob = bpy.data.materials.get("bulb_glow")
if ob:
    ob.name = "bulb_glow_old"
mb = lights.m_bulb()
for o in sc.objects:
    if o.type != "MESH":
        continue
    for s in o.material_slots:
        if s.material is old:
            s.material = m
        elif ob and s.material is ob:
            s.material = mb
if "--save" in argv:
    bpy.ops.wm.save_mainfile()
    print("FLAME saved", bpy.data.filepath, flush=True)
sc.cycles.samples = 48
sc.render.resolution_percentage = 50
sc.render.use_motion_blur = False
for n in ("flame", "wok", "table"):
    cam = bpy.data.objects.get("cam_" + n)
    if not cam:
        continue
    sc.camera = cam
    sc.render.filepath = os.path.join(SCENE_DIR, "out", "prev", f"{n}{TAG}.png")
    bpy.ops.render.render(write_still=True)
    print("FLAME", sc.render.filepath, flush=True)
