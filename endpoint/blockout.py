"""Grey-box a Plan in Blender and render it: one view from the reference camera, one high three-quarter overview.

    blender -b --factory-startup --python endpoint/blockout.py -- plan.json out_dir [--samples 32] [--res 1280]

Walls (with their openings cut), a box per object at its real size and rotation, and a small glowing marker per light.
Objects seen in the reference are plain clay; invented ones get a faint warm tint, matching the floor plan's colours.
"""

import json
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
plan = json.load(open(argv[0], encoding="utf-8"))
out = os.path.abspath(argv[1])
samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 32
res = int(argv[argv.index("--res") + 1]) if "--res" in argv else 1280
os.makedirs(out, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.samples = samples
sc.cycles.use_denoising = True
sc.view_settings.view_transform = "AgX"
# GPU if there is one (OptiX, then CUDA); otherwise Cycles falls back to the CPU.
prefs = bpy.context.preferences.addons["cycles"].preferences
for kind in ("OPTIX", "CUDA"):
    try:
        prefs.compute_device_type = kind
        prefs.get_devices()
        if any(d.type == kind for d in prefs.devices):
            for d in prefs.devices:
                d.use = d.type == kind
            sc.cycles.device = "GPU"
            break
    except TypeError:
        continue

world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.58, 0.62, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.6
sc.world = world


def mat(name, rgb, emit=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = 0.8
    if emit:
        b.inputs["Emission Color"].default_value = (*rgb, 1)
        b.inputs["Emission Strength"].default_value = emit
    return m


M_WALL = mat("wall", (0.72, 0.71, 0.69))
M_FLOOR = mat("floor", (0.45, 0.45, 0.46))
M_REF = mat("seen", (0.80, 0.80, 0.80))
M_INV = mat("invented", (0.86, 0.74, 0.58))


def box(name, center, size, rot_deg=0.0, material=M_WALL):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    o = bpy.context.object
    o.name = name
    o.scale = size
    o.rotation_euler.z = math.radians(rot_deg)
    o.data.materials.append(material)
    return o


R = plan["room"]
W, D, H = R["width"], R["depth"], R["height"]
T = 0.12  # wall thickness
box("floor", (W / 2, D / 2, -0.05), (W + 2, D + 2, 0.1), material=M_FLOOR)

# Walls: each wall is split into solid pieces around its openings (below the sill, above the head, between them).
walls = {"front": ((0, 0), (1, 0), W), "back": ((0, D), (1, 0), W), "left": ((0, 0), (0, 1), D), "right": ((W, 0), (0, 1), D)}
# Open-air settings get no enclosing walls: their facades, awnings and railings come from the plan's structure objects.
if plan["setting"] != "interior":
    walls = {}
for wall, (origin, axis, length) in walls.items():
    ops = sorted((o for o in plan["openings"] if o["wall"] == wall), key=lambda o: o["center"])
    cuts, a = [], 0.0
    for o in ops:
        s, e = o["center"] - o["width"] / 2, o["center"] + o["width"] / 2
        cuts.append((a, s, 0, H))                       # full-height piece before the opening
        if o["sill"] > 0:
            cuts.append((s, e, 0, o["sill"]))           # below a window
        if o["sill"] + o["height"] < H:
            cuts.append((s, e, o["sill"] + o["height"], H))  # above the opening
        a = e
    cuts.append((a, length, 0, H))
    for i, (s, e, z0, z1) in enumerate(cuts):
        if e - s < 0.01 or z1 - z0 < 0.01:
            continue
        mid = (s + e) / 2
        cx, cy = origin[0] + axis[0] * mid, origin[1] + axis[1] * mid
        size = (e - s, T, z1 - z0) if axis[0] else (T, e - s, z1 - z0)
        box(f"wall_{wall}_{i}", (cx, cy, (z0 + z1) / 2), size)

for ob in (o for o in plan["objects"] if o["w"] > 0 and o["d"] > 0 and o["h"] > 0):
    if ob["category"] == "structure" and ob["z"] <= 0.01 and ob["h"] < 0.05:
        continue  # ground-level surfaces (street, puddles) are already the floor
    box(ob["id"], (ob["x"], ob["y"], ob["z"] + ob["h"] / 2), (ob["w"], ob["d"], ob["h"]), ob["rot"],
        M_REF if ob["source"] == "reference" else M_INV)

COLORS = {}
for li in plan["lights"]:
    hexc = li["color"].lstrip("#")
    rgb = tuple(int(hexc[i:i + 2], 16) / 255 for i in (0, 2, 4))
    power = {"low": 40, "medium": 120, "high": 300}[li["power"]]
    data = bpy.data.lights.new(li["id"], "POINT")
    data.energy, data.color, data.shadow_soft_size = power, rgb, 0.15
    lo = bpy.data.objects.new(li["id"], data)
    lo.location = (li["x"], li["y"], li["z"])
    sc.collection.objects.link(lo)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.05, location=(li["x"], li["y"], li["z"]))
    bpy.context.object.data.materials.append(mat(f"glow_{li['id']}", rgb, emit=8))


def camera(name, pos, look, lens):
    cd = bpy.data.cameras.new(name)
    cd.lens, cd.sensor_width = lens, 36
    co = bpy.data.objects.new(name, cd)
    sc.collection.objects.link(co)
    co.location = Vector(pos)
    co.rotation_euler = (Vector(look) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
    return co


def render(cam, path, w, h):
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("blockout: wrote", path)


rc = plan["reference_camera"]
render(camera("cam_reference", rc["position"], rc["look_at"], rc["lens_mm"]), os.path.join(out, "blockout_reference.png"),
       res, int(res * 9 / 16))
# Overview: high three-quarter from the front-left, aimed at the middle of the space; the front wall is hidden
# so the interior reads like a dollhouse.
for o in bpy.data.objects:
    if o.name.startswith("wall_front"):
        o.hide_render = True
span = max(W, D)
render(camera("cam_overview", (W / 2 + 0.15 * span, -0.55 * span, 1.35 * span + H), (W / 2, D / 2, 0.6), 30),
       os.path.join(out, "blockout_overview.png"), res, int(res * 9 / 16))
