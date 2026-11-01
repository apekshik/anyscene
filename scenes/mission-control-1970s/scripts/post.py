"""Render settings, hero cameras and the optional clay override."""
import math

import bpy
from mathutils import Vector

import lib

# hero cameras: name -> (position, aim, lens)
CAMS = {
    "cam_back_wide": ((8.6, 1.2, 2.25), (4.6, 12.5, 1.7), 24),   # from the back aisle, down the rows to the display
    "cam_row_a": ((5.3, 8.2, 1.45), (5.2, 10.0, 1.15), 32),      # behind the ORBITAL ANALYSIS chair
    "cam_windows": ((1.0, 11.6, 1.6), (4.0, 2.0, 1.5), 24),      # front-left corner looking back up the tiers
    "cam_printer": ((8.2, 3.0, 1.9), (10.6, 0.8, 1.0), 30),      # the right-wall printer corner
    "cam_display": ((5.6, 4.2, 2.1), (5.8, 13.0, 2.1), 35),      # flight director's view
}


def camera(name, pos, aim, lens):
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        lib.collection("cameras").objects.link(cam)
    cam.location = pos
    cam.rotation_euler = (Vector(aim) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = lens
    cam.data.sensor_width = 24.89
    cam.data.clip_start = 0.05
    cam.data.clip_end = 200
    return cam


def make_clay():
    m = lib.principled("clay", (0.6, 0.6, 0.6), 0.6)
    for o in bpy.context.scene.objects:
        if o.type in ("MESH", "CURVE", "FONT") and not o.name.startswith(("backdrop", "outside")):
            o.data.materials.clear()
            o.data.materials.append(m)
            for s in o.material_slots:
                s.link = "OBJECT"
                s.material = m


def build(clay=False):
    sc = bpy.context.scene
    for n, (p, a, l) in CAMS.items():
        camera(n, p, a, l)
    sc.camera = bpy.data.objects["cam_back_wide"]
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPTIX"  # ~2 s/frame faster than OIDN here
    sc.render.use_persistent_data = False  # measured slower here (29 vs 24 s/frame)
    sc.cycles.max_bounces = 6
    sc.cycles.volume_bounces = 1
    sc.cycles.transparent_max_bounces = 8
    sc.cycles.light_sampling_threshold = 0.01
    sc.render.resolution_x, sc.render.resolution_y = 1920, 804
    sc.render.resolution_percentage = 100
    sc.render.fps = 24
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = 0.0
    if bpy.context.scene.world is None:
        w = bpy.data.worlds.new("night")
        w.use_nodes = True
        w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.004, 0.005, 0.008, 1)
        w.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
        sc.world = w
    if clay:
        make_clay()
