"""Hero cameras + a handheld clip camera for the repair shop (the video's phone-footage camera).

blender -b scenes/tokyo-electronics-repair/repair_lit.blend --python scenes/tokyo-electronics-repair/scripts/cameras.py -- <out.blend>
cam_wide / cam_bench: stills with DOF. cam_handheld: 120 frames (5 s @ 24 fps): a slow drift from the back of the shop
toward the bench, noise-driven shake on location + rotation, a slight exposure drift (auto-exposure hunting).
"""
import math
import os
import sys

import bpy
from mathutils import Vector

out = os.path.abspath(sys.argv[sys.argv.index("--") + 1])
sc = bpy.context.scene


def aim(cam, loc, target):
    cam.location = loc
    cam.rotation_mode = "XYZ"
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()


def focus_empty(name, loc):
    e = bpy.data.objects.get(name) or bpy.data.objects.new(name, None)
    if e.name not in sc.collection.objects:
        sc.collection.objects.link(e)
    e.location = loc
    return e


def dof(cam, target, fstop):
    cam.data.dof.use_dof = True
    cam.data.dof.focus_object = target
    cam.data.dof.aperture_fstop = fstop
    cam.data.dof.aperture_blades = 6


osc = sc.objects.get("oscilloscope")
osc_p = osc.location + Vector((0, 0, 0.1)) if osc else Vector((0.32, 2.2, 1.0))

# wide: from the back right, bench wall on the right, storefront glowing at the far end
wide = bpy.data.objects["cam_wide"]
aim(wide, (3.45, 6.2, 1.5), (0.9, 1.0, 0.95))
wide.data.lens = 21
dof(wide, focus_empty("focus_wide", (0.6, 2.6, 1.0)), 4.0)

# bench close-up: low over the bench edge, lamp pool and scope
bench = bpy.data.objects["cam_bench"]
aim(bench, (1.25, 3.05, 1.2), (0.3, 2.35, 0.95))
bench.data.lens = 30
dof(bench, focus_empty("focus_bench", osc_p), 2.0)

# handheld clip
cd = bpy.data.cameras.get("cam_handheld") or bpy.data.cameras.new("cam_handheld")
hh = bpy.data.objects.get("cam_handheld") or bpy.data.objects.new("cam_handheld", cd)
if hh.name not in sc.collection.objects:
    sc.collection.objects.link(hh)
cd.lens = 24
cd.sensor_width = 36
dof(hh, focus_empty("focus_hh", osc_p), 2.8)
hh.animation_data_clear()
sc.frame_start, sc.frame_end = 1, 120
keys = [  # frame, location, look-at
    (1, (3.3, 5.6, 1.58), (1.2, 1.2, 1.0)),
    (60, (2.6, 4.4, 1.5), (0.7, 2.0, 0.98)),
    (120, (1.75, 3.45, 1.38), (0.35, 2.35, 0.95)),
]
for f, loc, tgt in keys:
    aim(hh, loc, tgt)
    hh.keyframe_insert("location", frame=f)
    hh.keyframe_insert("rotation_euler", frame=f)
for fc in hh.animation_data.action.layers[0].strips[0].channelbag(hh.animation_data.action.slots[0]).fcurves if hasattr(hh.animation_data.action, "layers") else hh.animation_data.action.fcurves:
    for k in fc.keyframe_points:
        k.interpolation = "BEZIER"
        k.easing = "EASE_IN_OUT"
    m = fc.modifiers.new("NOISE")
    if fc.data_path == "location":
        m.strength, m.scale, m.phase = 0.018, 22, fc.array_index * 7.3
    else:
        m.strength, m.scale, m.phase = 0.01, 14, 3 + fc.array_index * 5.1
    m2 = fc.modifiers.new("NOISE")  # fine jitter on top of the sway
    m2.strength, m2.scale, m2.phase = (0.004 if fc.data_path == "location" else 0.003), 3, 11 + fc.array_index

# exposure drift: a phone hunting for exposure as it moves toward the bright lamp
vs = sc.view_settings
base = vs.exposure
for f, d in ((1, 0.15), (40, 0.05), (85, -0.1), (120, -0.2)):
    vs.exposure = base + d
    vs.keyframe_insert("exposure", frame=f)
vs.exposure = base

sc.camera = wide
bpy.ops.wm.save_as_mainfile(filepath=out)
print("cameras ->", out)
