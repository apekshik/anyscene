"""Dress the repair shop: append prepped props and place them, big props first, then small (the video's "Dressing the Room").

blender -b scenes/tokyo-electronics-repair/repair_shell.blend --python scenes/tokyo-electronics-repair/scripts/dress.py -- <pass>
pass 1 = furniture-scale props, 2 = + bench/shelf props, 3 = + small clutter. Saves scenes/tokyo-electronics-repair/repair_dressed.blend.
Placement: x, y in metres; yaw in degrees (library props face -Y; 90 faces +X = into the room from the bench wall);
"from" is the height the drop ray starts at (just under whatever is above the support); "z" pins the height instead.
"""
import json
import math
import os
import random
import sys

import bpy
from mathutils import Vector

ROOT = os.environ.get("ANYSCENE_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SCN = os.path.join(ROOT, "scenes", "tokyo-electronics-repair")
PASS = int(sys.argv[sys.argv.index("--") + 1]) if "--" in sys.argv else 4
random.seed(3)

BENCH, SHELF1, SHELF2 = 1.12, 2.05, 2.6  # ray start heights for the bench top, lower shelf, upper shelf
RX = 3.965  # centre x of the right-wall racks
RACK = [0.49, 0.91, 1.33, 1.75, 2.6]  # RACK[i]: ray start for an item standing on rack shelf i (just under shelf i+1)

# (pass, id, x, y, yaw, kw)
LAYOUT = [
    # pass 1: big floor props
    (1, "repair_tool_chest", 1.05, 6.2, 0, {}),
    (1, "repair_crt_stack", 3.72, 5.95, -20, {"back": "x1"}),
    (1, "repair_kerosene_heater", 0.45, 5.85, 60, {}),
    (1, "repair_stool", 1.1, 2.75, 20, {}),
    (1, "repair_boxes_a", RX, 1.75, -90, {"from": 2.65}),
    (1, "repair_boxes_b", RX, 4.35, -95, {"from": 2.65}),
    (1, "repair_boxes_b", 0.55, 0.55, 160, {"name": "boxes_b_front"}),
    (1, "repair_boxes_a", 2.0, 6.17, 5, {"name": "boxes_a_back"}),
    (1, "repair_trash_bin", 0.95, 5.45, 0, {}),
    # pass 2: bench heroes
    (2, "oscilloscope", 0.32, 2.2, 108, {"from": BENCH}),
    (2, "repair_bench_psu", 0.24, 1.6, 85, {"from": BENCH}),
    (2, "helping_hands", 0.5, 2.68, 115, {"from": BENCH}),
    (2, "repair_work_lamp", 0.5, 2.86, 27, {"z": 0.88}),  # clamp on the front edge right of the scope, arm reaching back-left over the helping hands, clear of the drawer cabinets
    (2, "solder_station", 0.27, 3.1, 100, {"from": BENCH}),
    (2, "boombox_open", 0.32, 3.7, 92, {"from": BENCH}),
    (2, "repair_vcr_open", 0.3, 4.3, 88, {"from": BENCH}),
    # pass 2: shelves above the bench + racks
    (2, "repair_vintage_radio", 0.16, 1.85, 90, {"from": SHELF1}),
    (2, "repair_receiver", 0.17, 2.3, 90, {"from": SHELF1}),
    (2, "repair_rice_cooker", 0.16, 3.0, 75, {"from": SHELF1}),
    (2, "repair_crt_tv", 0.17, 3.65, 85, {"from": SHELF1}),
    (2, "repair_turntable", 0.17, 4.5, 90, {"from": SHELF1}),
    (2, "repair_desk_fan", 0.16, 1.7, 110, {"from": SHELF2}),
    (2, "repair_crt_tv", 0.17, 4.75, 95, {"from": SHELF2, "name": "crt_tv_shelf2"}),
    (2, "repair_receiver", RX, 1.42, -90, {"from": RACK[0], "name": "receiver_rack"}),
    (2, "repair_vcr_open", RX, 2.0, -88, {"from": RACK[1], "name": "vcr_rack"}),
    (2, "repair_vintage_radio", RX, 3.05, -95, {"from": RACK[0], "name": "radio_rack"}),
    (2, "repair_rice_cooker", RX, 2.75, -80, {"from": RACK[2], "name": "rice_rack"}),
    (2, "repair_turntable", RX, 3.1, -90, {"from": RACK[1], "name": "turntable_rack"}),
    (2, "repair_crt_tv", RX, 4.25, -100, {"from": RACK[0], "name": "crt_rack"}),
    (2, "repair_desk_fan", RX, 1.6, -70, {"from": RACK[2], "name": "fan_rack", "scale": 0.88}),
    (2, "repair_kerosene_heater", RX, 3.45, -90, {"from": RACK[0], "name": "heater_rack", "scale": 0.84}),
    (2, "repair_cable_coils", 0.06, 5.65, 90, {"z": 1.25}),
    (2, "repair_wall_clock", 1.9, 6.47, 0, {"z": 2.08}),
    # pass 3: small clutter
    (3, "repair_multimeter_red", 0.58, 1.78, 125, {"from": BENCH}),
    (3, "repair_multimeter_yellow", 0.68, 3.42, 60, {"from": BENCH}),
    (3, "repair_parts_tray", 0.62, 4.55, 95, {"from": BENCH}),
    (3, "repair_solder_junk", 0.62, 2.3, 30, {"from": BENCH}),
    (3, "repair_mug", 0.66, 5.12, 200, {"from": BENCH}),
    (3, "repair_tool_block", 0.12, 4.7, 90, {"from": BENCH}),
    (3, "repair_mug", 0.15, 5.0, 120, {"from": SHELF1, "name": "mug_shelf"}),
    (3, "repair_parts_tray", RX, 3.4, -80, {"from": RACK[3], "name": "tray_rack"}),
    (3, "repair_multimeter_yellow", RX, 2.2, -120, {"from": RACK[3], "name": "dmm_rack"}),
    # pass 4: fill. Instances (linked duplicates) of devices waiting on every rack shelf, under the bench, on the counter
    (4, "repair_cassette_deck", RX, 1.55, -88, {"from": RACK[1], "name": "fill_receiver_1", "alt": "repair_receiver"}),
    (4, "repair_amp_black", RX, 1.95, -92, {"from": RACK[2], "name": "fill_vcr_1", "alt": "repair_vcr_open"}),
    (4, "repair_crt_monitor_beige", RX, 2.12, -85, {"from": RACK[0], "name": "fill_crt_1", "alt": "repair_crt_tv"}),
    (4, "repair_radio_cassette", RX, 1.78, -95, {"from": RACK[3], "name": "fill_radio_1", "alt": "repair_vintage_radio"}),
    (4, "repair_electric_kettle", RX, 2.66, -100, {"from": RACK[1], "name": "fill_rice_1", "alt": "repair_rice_cooker"}),
    (4, "repair_dotmatrix_printer", RX, 3.2, -90, {"from": RACK[2], "name": "fill_receiver_2", "alt": "repair_receiver"}),
    (4, "repair_crt_tv", RX, 2.85, -92, {"from": RACK[3], "name": "fill_crt_2"}),
    (4, "repair_portable_tv", RX, 2.62, -60, {"from": RACK[0], "name": "fill_fan_1", "alt": "repair_desk_fan", "scale": 0.88}),
    (4, "repair_fax_phone", RX, 4.1, -90, {"from": RACK[1], "name": "fill_vcr_2", "alt": "repair_vcr_open"}),
    (4, "repair_speaker_pair", RX, 4.35, -95, {"from": RACK[2], "name": "fill_turntable_1", "alt": "repair_turntable", "scale": 0.85}),
    (4, "repair_camcorder", RX, 4.6, -85, {"from": RACK[3], "name": "fill_radio_2", "alt": "repair_vintage_radio"}),
    (4, "repair_microwave", RX, 4.7, -90, {"from": RACK[0], "name": "fill_heater_1", "alt": "repair_kerosene_heater", "scale": 0.84}),
    (4, "repair_boxes_b", RX, 3.05, -88, {"from": 2.65, "name": "fill_boxes_rack2"}),
    (4, "repair_tv_wood", 0.3, 1.75, 95, {"from": 0.8, "name": "fill_crt_under", "alt": "repair_crt_tv"}),
    (4, "repair_karaoke_machine", 0.3, 2.5, 90, {"from": 0.8, "name": "fill_receiver_under", "alt": "repair_receiver"}),
    (4, "repair_rice_cooker", 0.3, 3.1, 70, {"from": 0.8, "name": "fill_rice_under"}),
    (4, "repair_boxes_b", 0.35, 3.85, 92, {"from": 0.8, "name": "fill_boxes_under", "scale": 0.7}),
    (4, "repair_pc_tower", 0.3, 4.75, 85, {"from": 0.8, "name": "fill_vcr_under", "alt": "repair_vcr_open"}),
    (4, "repair_multimeter_yellow", 2.98, 1.68, 150, {"from": 1.4, "name": "counter_dmm"}),
    (4, "repair_laptop_broken", 2.66, 1.78, 175, {"from": 1.4, "name": "counter_laptop"}),
    (4, "repair_parts_tray", 3.0, 2.0, 185, {"from": 1.4, "name": "counter_tray"}),
    (4, "solder_station", 0.25, 5.0, 100, {"from": BENCH, "name": "solder_station_2"}),
    (4, "repair_bench_psu", 0.2, 4.15, 92, {"from": SHELF1, "name": "psu_shelf"}),
    (4, "repair_multimeter_red", 0.55, 4.88, 140, {"from": BENCH, "name": "dmm_station2"}),
    (4, "repair_boxes_a", 1.3, 0.75, 170, {"name": "fill_boxes_front"}),
    (4, "repair_tv_wood", 3.55, 0.45, 205, {"name": "fill_crt_floor", "alt": "repair_crt_tv"}),
    (4, "repair_floor_fan", 2.75, 5.0, 30, {"name": "fill_heater_floor", "alt": "repair_kerosene_heater"}),
    (4, "repair_stool", 2.85, 2.62, -20, {"name": "counter_stool"}),
]


def append_prop(pid):
    """Append the prop object once; later uses become linked duplicates sharing mesh + materials."""
    src = bpy.data.objects.get(f"src_{pid}")
    if src:
        return src
    path = os.path.join(SCN, "props", f"{pid}.blend")
    with bpy.data.libraries.load(path, link=False) as (fr, to):
        to.objects = [pid]
    src = to.objects[0]
    src.name = f"src_{pid}"
    lib = bpy.data.collections.get("_prop_sources") or bpy.data.collections.new("_prop_sources")
    if lib.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(lib)
    lib.objects.link(src)
    lib.hide_render = True
    bpy.context.view_layer.layer_collection.children[lib.name].exclude = True  # keep sources out of rays + renders
    return src


def drop(ob, start_z):
    """Rest the object on the highest support under its footprint (5 rays), ignoring itself."""
    dg = bpy.context.evaluated_depsgraph_get()
    sc = bpy.context.scene
    bb = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    cx, cy = ob.location.x, ob.location.y
    ob.location.z = -100  # out of the way of its own rays
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    hx = (max(p.x for p in bb) - min(p.x for p in bb)) * 0.35
    hy = (max(p.y for p in bb) - min(p.y for p in bb)) * 0.35
    best = None
    for dx, dy in ((0, 0), (hx, hy), (-hx, hy), (hx, -hy), (-hx, -hy)):
        hit, loc, *_ = sc.ray_cast(dg, Vector((cx + dx, cy + dy, start_z)), Vector((0, 0, -1)))
        if hit and (best is None or loc.z > best):
            best = loc.z
    ob.location.z = best if best is not None else 0.0
    return best


def place(pid, x, y, yaw, kw):
    src = append_prop(pid)
    ob = src.copy()
    ob.name = kw.get("name", pid)
    coll = bpy.data.collections.get("props") or bpy.data.collections.new("props")
    if coll.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(coll)
    coll.objects.link(ob)
    s = kw.get("scale", 1.0) * random.uniform(0.97, 1.03)
    ob.scale = (s, s, s)
    ob.rotation_mode = "XYZ"  # glTF imports come in as QUATERNION, which would silently ignore rotation_euler
    ob.rotation_euler = (math.radians(kw.get("pitch", 0)), 0, math.radians(yaw + random.uniform(-3, 3)))
    ob.location = (x, y, kw.get("z", 0))
    ob["placed"] = True
    ob["prop_id"] = pid
    ob["wall"] = "z" in kw
    ob["scaled"] = "scale" in kw
    bpy.context.view_layer.update()
    # snap the back against the wall it stands by: shelf props to the bench wall, rack props to the right wall
    back = kw.get("back") or ("x0" if x < 0.4 and (kw.get("from") in (SHELF1, SHELF2) or "z" in kw) else "x1" if abs(x - RX) < 0.01 else None)
    if back:
        pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
        if back == "x0":
            ob.location.x += 0.012 - min(p.x for p in pts)
        elif back == "x1":
            ob.location.x += (4.2 - 0.012) - max(p.x for p in pts)
        bpy.context.view_layer.update()
    if "z" not in kw:
        drop(ob, kw.get("from", 2.4))  # default start stays under the ceiling conduit (2.65) and fixtures
    return ob


TV_ON = {"repair_crt_tv", "crt_tv_shelf2"}  # only these sets are left on (blue no-signal screens)

# round 2: regenerated brand-free versions that won their pick replace the texture-painted originals (object names unchanged)
_nb_path = os.path.join(SCN, "nb_swap.json")
NB_SWAP = json.load(open(_nb_path)) if os.path.exists(_nb_path) else {}

for p, pid, x, y, yaw, kw in LAYOUT:
    if p > PASS:
        continue
    if pid in NB_SWAP and os.path.exists(os.path.join(SCN, "props", f"{NB_SWAP[pid]}.blend")):
        kw = dict(kw, name=kw.get("name", pid))
        pid = NB_SWAP[pid]
    if not os.path.exists(os.path.join(SCN, "props", f"{pid}.blend")):
        if kw.get("alt") and os.path.exists(os.path.join(SCN, "props", f"{kw['alt']}.blend")):
            pid = kw["alt"]  # round-2 generated prop not available (yet): fall back to the round-1 one
        else:
            print("MISSING prop", pid)
            continue
    ob = place(pid, x, y, yaw, kw)
    ob["tv_on"] = 1.0 if ob.name in TV_ON else 0.0
    print(f"PLACED {ob.name} at {tuple(round(v, 3) for v in ob.location)}")

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(SCN, "repair_dressed.blend"))
print("saved dressed pass", PASS)
