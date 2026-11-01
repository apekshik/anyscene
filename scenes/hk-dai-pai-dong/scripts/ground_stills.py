"""Low-angle stills of the tables and stools (knee height) to check every foot is on the ground. Lit, no rain/haze.
    bash scenes/hk-dai-pai-dong/scripts/blend.sh scenes/hk-dai-pai-dong/hk.blend --python scenes/hk-dai-pai-dong/scripts/ground_stills.py -- [--tag _v2]
"""
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import SCENE_DIR  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
TAG = argv[argv.index("--tag") + 1] if "--tag" in argv else ""

# name: (camera pos, aim) - 30-40 cm off the ground, 2-3 m out
VIEWS = {
    "t3": ((3.6, -1.6, 0.3), (1.65, -0.35, 0.35)),
    "t4": ((3.4, 6.4, 0.3), (1.75, 4.55, 0.35)),
    "t5": ((5.9, 1.2, 0.35), (3.95, 2.45, 0.35)),
    "t1t2": ((0.9, -1.7, 0.3), (-0.95, 2.4, 0.4)),
    "kitchen": ((-1.4, 4.6, 1.0), (-3.2, 4.9, 0.9)),
    "cart": ((-1.6, 1.2, 1.15), (-3.1, 1.5, 0.95)),
}


def add_camera(name, pos, aim, lens, c):  # as build.py (importing build would run the build)
    d = bpy.data.cameras.new(name)
    d.lens, d.sensor_width, d.clip_start = lens, 24.89, 0.05
    o = bpy.data.objects.new(name, d)
    c.objects.link(o)
    o.location = pos
    o.rotation_euler = (Vector(aim) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
    return o


sc = bpy.context.scene
for o in sc.objects:
    if o.name.startswith(("haze", "rain", "drizzle", "drip")):
        o.hide_render = True
sc.cycles.samples = 24
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1920, 804, 50
sc.render.use_motion_blur = False
sc.view_settings.exposure += 0.8  # knee-height views are in the stools' shadow
od = os.path.join(SCENE_DIR, "out", "prev")
os.makedirs(od, exist_ok=True)
for n, (pos, aim) in VIEWS.items():
    sc.camera = add_camera("cam_ground_" + n, pos, aim, 28, sc.collection)
    sc.render.filepath = os.path.join(od, f"ground_{n}{TAG}.png")
    bpy.ops.render.render(write_still=True)
    print("GROUND still", sc.render.filepath, flush=True)
