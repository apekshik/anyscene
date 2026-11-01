"""Low-angle check cameras for contact/grounding review (desk tops at eye level, chair feet, floor spill, back cabinets).

blender -b mc.blend --python gpu_prefs.py --python lowcams.py --python preview.py -- --cams low_desk_a,... --exposure 1.5
Adds cameras only; nothing is saved.
"""
import bpy
from mathutils import Vector

CAMS = {  # name: (position, aim, lens)
    "low_desk_a": ((2.6, 8.55, 0.80), (4.6, 9.4, 0.70), 28),
    "low_desk_b": ((6.8, 5.55, 1.15), (5.0, 6.3, 1.05), 28),
    "low_desk_c": ((3.4, 2.55, 1.50), (5.2, 3.3, 1.40), 28),
    "low_chairs_a": ((2.2, 7.7, 0.12), (4.5, 8.6, 0.25), 24),
    "low_chairs_b": ((8.0, 4.8, 0.47), (5.5, 5.6, 0.6), 24),
    "low_back_cabinets": ((3.0, 1.7, 2.1), (2.7, 0.35, 1.85), 28),
    "low_spill": ((8.6, 2.2, 0.85), (9.8, 2.3, 0.72), 28),
}

for name, (pos, aim, lens) in CAMS.items():
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.clip_start = 0.02
    o = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(o)
    o.location = pos
    d = Vector(aim) - Vector(pos)
    o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y = 1920, 1080
print("LOWCAMS", ",".join(CAMS), flush=True)
