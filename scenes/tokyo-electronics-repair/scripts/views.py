"""Orthographic, bbox-fitted views of prepped props, used to locate brand marks for debranding.

blender -b --factory-startup --python scenes/tokyo-electronics-repair/scripts/views.py -- <id,id,...> [views=front,right,left,top,back]
-> scenes/tokyo-electronics-repair/debrand/<id>_<view>.png (512 px square). The image spans the prop's bbox in that view, centred:
pixel (0,0) top-left. debrand.py maps rectangles given in these images' normalised coordinates back to texels.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

ROOT = os.environ.get("ANYSCENE_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PROPS = os.path.join(ROOT, "scenes", "tokyo-electronics-repair", "props")
OUT = os.environ.get("VIEWS_OUT", os.path.join(ROOT, "scenes", "tokyo-electronics-repair", "debrand"))

# view -> (camera direction it looks along, horizontal world axis, vertical world axis)
VIEWS = {
    "front": (Vector((0, 1, 0)), Vector((1, 0, 0)), Vector((0, 0, 1))),
    "back": (Vector((0, -1, 0)), Vector((-1, 0, 0)), Vector((0, 0, 1))),
    "right": (Vector((-1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))),
    "left": (Vector((1, 0, 0)), Vector((0, -1, 0)), Vector((0, 0, 1))),
    "top": (Vector((0, 0, -1)), Vector((1, 0, 0)), Vector((0, 1, 0))),
}


def frame(ob, view):
    d, h, v = VIEWS[view]
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    hs = [p.dot(h) for p in pts]
    vs = [p.dot(v) for p in pts]
    c = sum(pts, Vector()) / 8
    span = max(max(hs) - min(hs), max(vs) - min(vs)) * 1.02
    return c, span, d, h, v


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:]
    ids = a[0].split(",")
    views = a[1].split(",") if len(a) > 1 else ["front", "right", "left", "top", "back"]
    os.makedirs(OUT, exist_ok=True)
    for pid in ids:
        bpy.ops.wm.open_mainfile(filepath=os.path.join(PROPS, f"{pid}.blend"))
        sc = bpy.context.scene
        ob = bpy.data.objects[pid]
        sc.render.engine = "BLENDER_EEVEE"
        sc.render.resolution_x = sc.render.resolution_y = 512
        sc.view_settings.view_transform = "Standard"
        w = bpy.data.worlds.new("w")
        sc.world = w
        w.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.6
        cd = bpy.data.cameras.new("c")
        cd.type = "ORTHO"
        cam = bpy.data.objects.new("c", cd)
        sc.collection.objects.link(cam)
        sc.camera = cam
        for view in views:
            c, span, d, h, v = frame(ob, view)
            cam.location = c - d * 5
            cam.rotation_euler = d.to_track_quat("-Z", "Y" if view != "top" else "Y").to_euler()
            if view == "top":
                cam.rotation_euler = (0, 0, 0)
            cd.ortho_scale = span
            cd.clip_end = 20
            sc.render.filepath = os.path.join(OUT, f"{pid}_{view}.png")
            bpy.ops.render.render(write_still=True)
        print("VIEWS", pid)
