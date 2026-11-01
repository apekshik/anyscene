"""Night lighting: practicals first (CRT faces and the wall display are emissive already), then desk lamps, the few
troffers that are on, the display spill, the launch-pad spill through the windows, small accents; weak fills last.

Every light lives in collection "lights" with ob["light_order"] (the breakdown's switch-on order) and
ob["base_energy"]. Area lights shine along local -Z. Fills are hidden from camera, glossy and transmission rays so
they never show through the window glass as bright discs.
"""
import math

import bpy
from mathutils import Vector

import layout as L
import lib

EXPOSURE = -0.35  # the haze lifts the blacks
WARM = (1.0, 0.68, 0.38)
COOL_TUBE = (0.82, 0.93, 1.0)
PHOSPHOR = (0.35, 1.0, 0.55)
_order = [0]


def light(name, kind, loc, energy, color, size=0.1, aim=None, rot=None, spot=None, fill=False, order_group=0):
    d = bpy.data.lights.new(name, kind)
    d.energy = energy
    d.color = color
    if kind == "AREA":
        if isinstance(size, tuple):
            d.shape = "RECTANGLE"
            d.size, d.size_y = size
        else:
            d.size = size
    elif kind in ("POINT", "SPOT"):
        d.shadow_soft_size = size
    if spot:
        d.spot_size, d.spot_blend = math.radians(spot[0]), spot[1]
    o = bpy.data.objects.new(name, d)
    lib.collection("lights").objects.link(o)
    o.location = loc
    if aim is not None:
        o.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    elif rot is not None:
        o.rotation_euler = rot
    if fill:
        o.visible_camera = False
        o.visible_glossy = False
        o.visible_transmission = False
    o["light_order"] = order_group * 100 + _order[0]
    o["base_energy"] = energy
    _order[0] += 1
    return o


def lamp_head(o):
    """World-space centre of a desk lamp's shade: the mean of the highest 25 % of vertices, pushed to the shade's rim."""
    mw = o.matrix_world
    vs = [mw @ v.co for v in o.data.vertices]
    zmax = max(v.z for v in vs)
    zmin = min(v.z for v in vs)
    top = [v for v in vs if v.z > zmin + 0.72 * (zmax - zmin)]
    c = sum(top, Vector()) / len(top)
    low = min(v.z for v in top)
    return Vector((c.x, c.y, low - 0.01))


def build():
    sc = bpy.context.scene
    sc.view_settings.exposure = EXPOSURE
    # group 1: desk lamps (warm pools)
    for o in [o for o in sc.objects if o.get("desk_lamp")]:
        h = lamp_head(o)
        light(f"lamp_{o.name}", "SPOT", h, 28.0, WARM, size=0.025, aim=h + Vector((0, 0.15, -1)), spot=(105, 0.55), order_group=1)
        light(f"lampglow_{o.name}", "POINT", h + Vector((0, 0, 0.03)), 1.2, WARM, size=0.02, order_group=1)
    # group 2: troffers that are on (area light just under each lit lens)
    for o in sc.objects:
        st = o.get("state")
        if st in ("tr_on", "tr_dim"):
            lo = o.matrix_world @ Vector(o.bound_box[0])
            hi = o.matrix_world @ Vector(o.bound_box[6])
            c = (lo + hi) / 2
            e = 70.0 if st == "tr_on" else 14.0
            lt = light(f"tube_{o.name}", "AREA", (c.x, c.y, lo.z - 0.005), e, COOL_TUBE, size=(0.54, 1.12), rot=(0, 0, 0), order_group=2)
            lt.visible_camera = False
    # group 3: the wall display spill (the panels are emissive; these add the soft directional throw into the room)
    for name, x0, x1 in L.DISP_PANELS:
        col = (0.35, 1.0, 0.85) if name == "wall_map" else (0.45, 1.0, 0.6)
        light(f"disp_{name}", "AREA", ((x0 + x1) / 2, L.D - 0.3, (L.DISP_Z0 + L.DISP_Z1) / 2), 60.0 if name == "wall_map" else 25.0, col,
              size=(x1 - x0, L.DISP_Z1 - L.DISP_Z0), rot=(math.radians(-90), 0, 0), fill=True, order_group=3)
    # group 4: launch-pad spill through the windows (cold xenon from high up, a little sodium low)
    light("pad_spill", "AREA", (-2.5, 5.4, 3.4), 140.0, (0.72, 0.82, 1.0), size=(1.8, 8.4), aim=(3.5, 5.4, 0.0), fill=True, order_group=4)
    light("pad_sodium", "AREA", (-2.5, 5.4, 1.6), 30.0, (1.0, 0.6, 0.25), size=(1.0, 8.4), aim=(3.0, 5.4, 1.0), fill=True, order_group=4)
    # group 5: accents (exit sign glow, the coffee maker's warmer, CRT bounce for the hero console)
    light("exit_glow", "POINT", (5.5, 0.25, L.DOOR_Z1 + 0.2), 3.0, (1.0, 0.1, 0.05), size=0.05, order_group=5)
    cm = next((o for o in sc.objects if o.get("prop_id") == "mc_coffee_maker"), None)
    if cm:
        lo = cm.matrix_world @ Vector(cm.bound_box[0])
        hi = cm.matrix_world @ Vector(cm.bound_box[6])
        light("warmer_glow", "POINT", ((lo.x + hi.x) / 2, lo.y - 0.05, lo.z + 0.06), 0.6, (1.0, 0.2, 0.05), size=0.02, order_group=5)
    # group 6: weak fills last: a cool bounce from the display end over the rows, a whisper of warm from the back
    light("fill_rows", "AREA", (5.6, 9.0, 3.4), 18.0, (0.6, 0.9, 0.85), size=(6.0, 3.0), rot=(0, 0, 0), fill=True, order_group=6)
    light("fill_back", "AREA", (5.5, 1.6, 3.4), 6.0, (1.0, 0.8, 0.6), size=(6.0, 2.0), rot=(0, 0, 0), fill=True, order_group=6)
    w = sc.world
    if w and w.use_nodes:
        w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.003, 0.004, 0.007, 1)
    print("LIGHTS", len(lib.collection("lights").objects), flush=True)
