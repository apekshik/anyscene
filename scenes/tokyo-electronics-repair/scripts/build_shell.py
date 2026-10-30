"""Repair shop: scripted room shell, storefront, furniture and fixtures (the video's "Building the Room" step).

blender -b --factory-startup --python scenes/tokyo-electronics-repair/scripts/build_shell.py
-> scenes/tokyo-electronics-repair/repair_shell.blend
Coordinates: x across the shop (0 = bench wall), y from the storefront (0) to the back wall (6.5), z up. Metres.
"""
import math
import os
import random
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(__file__))
import lib  # noqa: E402
from lib import box, collection, cylinder, plane  # noqa: E402

W, D, H = 4.2, 6.5, 2.7
T = 0.12  # wall thickness
SCN = os.path.join(lib.ROOT, "scenes", "tokyo-electronics-repair")
TEX = os.path.join(lib.ROOT, "refs", "tokyo-electronics-repair", "tex")
random.seed(7)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.unit_settings.system = "METRIC"

# ---------------------------------------------------------------- materials
M = {
    "floor": lib.floor_tiles("floor_vinyl", a=(0.4, 0.385, 0.34), b2=(0.24, 0.24, 0.23)),
    "wall": lib.wall_paint("wall_paint"),
    "ceiling": lib.grimy("ceiling_tile", (0.7, 0.69, 0.64), (0.4, 0.37, 0.3), amount=0.2, scale=2),
    "wood": lib.wood("bench_wood", light=(0.3, 0.19, 0.1), dark=(0.16, 0.09, 0.045), worn=0.6),
    "shelfwood": lib.wood("shelf_wood", light=(0.5, 0.36, 0.22), dark=(0.3, 0.2, 0.11), worn=0.2),
    "steel": lib.grimy("painted_steel", (0.32, 0.34, 0.33), (0.12, 0.1, 0.08), rough=(0.4, 0.7), metal=0.3, amount=0.3),
    "shelfsteel": lib.grimy("shelf_steel", (0.55, 0.56, 0.54), (0.2, 0.18, 0.15), rough=(0.35, 0.6), metal=0.4, amount=0.25),
    "alu": lib.grimy("aluminium", (0.62, 0.63, 0.64), (0.25, 0.24, 0.22), rough=(0.3, 0.5), metal=1.0, amount=0.2, bump=0.05),
    "glass": lib.rain_glass("rain_glass"),
    "doorglass": lib.principled("plain_glass", (0.9, 0.95, 0.95), 0.02, **{"Transmission Weight": 1.0}),
    "pegboard": None,
    "plastic_drawer": lib.principled("drawer_plastic", (0.75, 0.78, 0.8), 0.3, **{"Transmission Weight": 0.6, "IOR": 1.45}),
    "cabinet": lib.grimy("drawer_cabinet", (0.42, 0.44, 0.43), (0.15, 0.13, 0.1), amount=0.25),
    "door": lib.wood("door_wood", light=(0.32, 0.2, 0.12), dark=(0.18, 0.1, 0.06), scale=1.0, worn=0.15),
    "baseboard": lib.principled("baseboard", (0.12, 0.11, 0.1), 0.6),
    "tube": lib.principled("fluoro_tube_off", (0.85, 0.85, 0.82), 0.25, **{"Transmission Weight": 0.3}),
    "fixture": lib.grimy("fixture_white", (0.75, 0.74, 0.7), (0.35, 0.3, 0.22), amount=0.25),
    "conduit": lib.grimy("conduit", (0.6, 0.6, 0.58), (0.25, 0.22, 0.18), metal=0.6, amount=0.25),
    "black_plastic": lib.principled("black_plastic", (0.03, 0.03, 0.03), 0.45),
    "outlet": lib.principled("outlet_white", (0.8, 0.79, 0.74), 0.4),
}

# Pegboard: hardboard with a regular hole grid (Voronoi with zero randomness).
pm = bpy.data.materials.new("pegboard")
nt = pm.node_tree
bs = nt.nodes["Principled BSDF"]
tc = nt.nodes.new("ShaderNodeTexCoord")
vo = nt.nodes.new("ShaderNodeTexVoronoi")
vo.inputs["Scale"].default_value = 40
vo.inputs["Randomness"].default_value = 0.0
nt.links.new(tc.outputs["Object"], vo.inputs["Vector"])
hole = lib._ramp(nt, vo.outputs["Distance"], [(0.12, (0.015, 0.01, 0.008)), (0.16, (0.17, 0.11, 0.065))])
nt.links.new(hole.outputs["Color"], bs.inputs["Base Color"])
bs.inputs["Roughness"].default_value = 0.8
nt.links.new(lib._bump(nt, vo.outputs["Distance"], 0.6), bs.inputs["Normal"])
M["pegboard"] = pm

# ---------------------------------------------------------------- shell
C_SHELL = collection("shell")
box("floor", (-T, -0.5, -0.05), (W + T, D + T, 0), M["floor"], C_SHELL, bevel=0)
box("ceiling", (-T, -0.2, H), (W + T, D + T, H + 0.05), M["ceiling"], C_SHELL, bevel=0)
box("wall_left", (-T, 0, 0), (0, D, H), M["wall"], C_SHELL, bevel=0)
box("wall_right", (W, 0, 0), (W + T, D, H), M["wall"], C_SHELL, bevel=0)
# back wall with a door opening at x 2.4..3.3
DX0, DX1, DH = 2.4, 3.3, 2.05
box("wall_back_a", (-T, D, 0), (DX0, D + T, H), M["wall"], C_SHELL, bevel=0)
box("wall_back_b", (DX1, D, 0), (W + T, D + T, H), M["wall"], C_SHELL, bevel=0)
box("wall_back_c", (DX0, D, DH), (DX1, D + T, H), M["wall"], C_SHELL, bevel=0)
for name, lo, hi in (("baseboard_l", (0, 0.05, 0), (0.012, D, 0.08)), ("baseboard_r", (W - 0.012, 0.05, 0), (W, D, 0.08)),
                     ("baseboard_b1", (0, D - 0.012, 0), (DX0, D, 0.08)), ("baseboard_b2", (DX1, D - 0.012, 0), (W, D, 0.08))):
    box(name, lo, hi, M["baseboard"], C_SHELL)
# door: frame + slab, slightly ajar into the dark back room
box("door_frame_l", (DX0, D - 0.02, 0), (DX0 + 0.05, D + T, DH + 0.05), M["door"], C_SHELL)
box("door_frame_r", (DX1 - 0.05, D - 0.02, 0), (DX1, D + T, DH + 0.05), M["door"], C_SHELL)
box("door_frame_t", (DX0, D - 0.02, DH), (DX1, D + T, DH + 0.05), M["door"], C_SHELL)
slab = box("door_slab", (DX0 + 0.05, D + 0.02, 0.01), (DX1 - 0.05, D + 0.06, DH - 0.005), M["door"], C_SHELL)
cylinder("door_handle", (DX1 - 0.13, D - 0.0, 1.0), 0.012, 0.12, M["alu"], C_SHELL, axis="X")
box("backroom_dark", (DX0 - 0.5, D + 1.5, 0), (DX1 + 0.5, D + 1.6, 2.4), lib.principled("backroom", (0.02, 0.02, 0.02), 0.9), C_SHELL, bevel=0)

# ---------------------------------------------------------------- storefront (y = 0)
C_FRONT = collection("storefront")
KNEE, TOP = 0.5, 2.3
A = M["alu"]
F = 0.05  # frame member size
box("front_knee_l", (0, -T, 0), (1.5, 0, KNEE), M["wall"], C_FRONT, bevel=0)
box("front_knee_r", (2.74, -T, 0), (W, 0, KNEE), M["wall"], C_FRONT, bevel=0)
box("front_header", (0, -T, TOP + F), (W, 0, H), M["wall"], C_FRONT, bevel=0)
for x in (0.0, 1.47, 2.72, W - F):
    box(f"front_post_{x:.2f}", (x, -0.07, 0), (x + F, 0.0, TOP + F), A, C_FRONT)
box("front_head", (0, -0.07, TOP), (W, 0.0, TOP + F), A, C_FRONT)
box("front_sill_l", (F, -0.07, KNEE), (1.47, 0.02, KNEE + F * 0.6), A, C_FRONT)
box("front_sill_r", (2.72 + F, -0.07, KNEE), (W - F, 0.02, KNEE + F * 0.6), A, C_FRONT)
box("glass_l", (F, -0.04, KNEE + 0.03), (1.47, -0.032, TOP), M["glass"], C_FRONT, bevel=0)
box("glass_r", (2.72 + F, -0.04, KNEE + 0.03), (W - F, -0.032, TOP), M["glass"], C_FRONT, bevel=0)
# two sliding door leaves, the right one slightly behind the left
for i, (x0, x1, y) in enumerate(((1.52, 2.16, -0.03), (2.08, 2.72, -0.06))):
    for nm, lo, hi in (("l", (x0, y - 0.03, 0.02), (x0 + F, y, TOP - 0.02)), ("r", (x1 - F, y - 0.03, 0.02), (x1, y, TOP - 0.02)),
                       ("b", (x0, y - 0.03, 0.02), (x1, y, 0.14)), ("t", (x0, y - 0.03, TOP - 0.07), (x1, y, TOP - 0.02))):
        box(f"door_leaf{i}_{nm}", lo, hi, A, C_FRONT)
    box(f"door_leaf{i}_glass", (x0 + F, y - 0.018, 0.14), (x1 - F, y - 0.01, TOP - 0.07), M["glass"], C_FRONT, bevel=0)
    box(f"door_leaf{i}_pull", (x1 - 0.09 if i == 0 else x0 + 0.06, y + 0.0, 0.9), (x1 - 0.07 if i == 0 else x0 + 0.08, y + 0.03, 1.2), A, C_FRONT)
# window decal (reads mirrored from inside, as it should)
deco = lib.image_mat("decal_signage", os.path.join(TEX, "signage_0.png"), rough=0.4, alpha=True)
dp = plane("decal_signage", (3.43, -0.03, 1.55), 1.25, 0.7, "Y", deco, C_FRONT)
lib.set_uv_rect(dp, 0, 0, 1, 1)  # exterior lettering: reads mirrored from inside
# outside: wet pavement strip, then the street backdrop as an emissive plane
box("pavement", (-1, -2.5, -0.08), (W + 1, -0.12, -0.06), lib.grimy("wet_pavement", (0.08, 0.08, 0.085), (0.02, 0.02, 0.02), rough=(0.05, 0.3), amount=0.4), C_FRONT, bevel=0)
box("road", (-3, -5.2, -0.1), (W + 3, -2.5, -0.08), lib.grimy("wet_asphalt", (0.035, 0.035, 0.04), (0.01, 0.01, 0.012), rough=(0.04, 0.25), amount=0.5, scale=1.5), C_FRONT, bevel=0)
street = lib.image_mat("street_backdrop", os.path.join(TEX, "street_0.png"), emission=1.2)
plane("street_backdrop", (W / 2, -4.5, 1.4), 9.0, 5.06, "Y", street, C_FRONT)

# ---------------------------------------------------------------- workbench along the left wall
C_BENCH = collection("bench")
BY0, BY1, BZ, BD = 1.3, 5.3, 0.88, 0.75
box("bench_top", (0.0, BY0, BZ - 0.045), (BD, BY1, BZ), M["wood"], C_BENCH, bevel=0.004)
box("bench_apron", (BD - 0.03, BY0 + 0.05, BZ - 0.13), (BD - 0.01, BY1 - 0.05, BZ - 0.045), M["steel"], C_BENCH)
for y in (BY0 + 0.04, (BY0 + BY1) / 2, BY1 - 0.04):
    for x in (0.04, BD - 0.06):
        box(f"bench_leg_{x:.2f}_{y:.2f}", (x - 0.02, y - 0.02, 0), (x + 0.02, y + 0.02, BZ - 0.045), M["steel"], C_BENCH)
box("bench_shelf", (0.02, BY0 + 0.02, 0.14), (BD - 0.04, BY1 - 0.02, 0.165), M["shelfwood"], C_BENCH)
box("bench_rail", (BD - 0.08, BY0, 0.14), (BD - 0.04, BY1, 0.18), M["steel"], C_BENCH)
# antistatic mat on part of the bench
box("bench_mat", (0.12, 2.0, BZ), (0.62, 2.9, BZ + 0.003), lib.grimy("esd_mat", (0.08, 0.13, 0.12), (0.03, 0.03, 0.03), rough=(0.5, 0.8), amount=0.3), C_BENCH, bevel=0)

# shelves above the bench
for z in (1.68, 2.12):
    box(f"shelf_{z}", (0.0, BY0, z), (0.32, BY1, z + 0.025), M["shelfwood"], C_BENCH)
    for y in (BY0 + 0.1, (BY0 + BY1) / 2, BY1 - 0.1):
        box(f"shelf_bracket_{z}_{y:.2f}", (0.0, y - 0.01, z - 0.18), (0.25, y + 0.01, z), M["steel"], C_BENCH)

# pegboard behind the right half of the bench
box("pegboard", (0.0, 3.15, 0.95), (0.012, 5.25, 1.6), M["pegboard"], C_BENCH, bevel=0)

# ---------------------------------------------------------------- sales counter in the front half (customers hand devices over here)
C_COUNTER = collection("counter")
CX0, CX1, CY0, CY1, CZ = 1.9, 3.5, 1.55, 2.15, 0.95
box("counter_body", (CX0, CY0, 0.0), (CX1, CY1 - 0.04, CZ - 0.03), M["door"], C_COUNTER, bevel=0.004)
box("counter_kick", (CX0 + 0.03, CY0 - 0.005, 0.0), (CX1 - 0.03, CY0 + 0.02, 0.09), M["baseboard"], C_COUNTER)
box("counter_top", (CX0 - 0.03, CY0 - 0.04, CZ - 0.03), (CX1 + 0.03, CY1, CZ), M["wood"], C_COUNTER, bevel=0.003)
box("counter_mat", (CX0 + 0.1, CY0 + 0.08, CZ), (CX0 + 0.55, CY0 + 0.45, CZ + 0.003), lib.principled("rubber_mat", (0.05, 0.05, 0.055), 0.7), C_COUNTER, bevel=0)

# ---------------------------------------------------------------- parts drawer cabinets (wall-mounted, labelled)
C_DRAW = collection("drawers")
labels = lib.image_mat("drawer_labels", os.path.join(TEX, "labels_0.png"), rough=0.6)
COLS, ROWS, CW, CH, CDEP = 5, 7, 0.1, 0.072, 0.17
for k, y0 in enumerate((BY0 + 0.05, BY0 + 0.6, BY0 + 1.15)):
    z0 = 1.15  # tucked under the lower shelf (1.68) so the bench below stays usable
    parts = [box(f"drawer_cab{k}_body", (0.0, y0, z0), (CDEP, y0 + COLS * CW + 0.02, z0 + ROWS * CH + 0.02), M["cabinet"], C_DRAW)]
    for r in range(ROWS):
        for c in range(COLS):
            yy = y0 + 0.01 + c * CW
            zz = z0 + 0.01 + r * CH
            pull = random.uniform(0, 0.025) if random.random() < 0.15 else 0.0
            parts.append(box(f"d{k}_{r}_{c}", (CDEP - 0.005 + pull, yy + 0.004, zz + 0.004), (CDEP + 0.003 + pull, yy + CW - 0.004, zz + CH - 0.004), M["plastic_drawer"], C_DRAW, bevel=0.001))
            parts.append(box(f"h{k}_{r}_{c}", (CDEP + 0.003 + pull, yy + CW / 2 - 0.012, zz + 0.008), (CDEP + 0.012 + pull, yy + CW / 2 + 0.012, zz + 0.016), M["cabinet"], C_DRAW, bevel=0.001))
            lab = plane(f"l{k}_{r}_{c}", (CDEP + 0.0035 + pull, yy + CW / 2, zz + CH * 0.62), CW * 0.62, CH * 0.32, "X", labels, C_DRAW)
            cell = random.randrange(36)
            u, v = cell % 6, cell // 6
            lib.set_uv_rect(lab, u / 6 + 0.01, 1 - (v + 1) / 6 + 0.02, (u + 1) / 6 - 0.01, 1 - v / 6 - 0.02)
            parts.append(lab)
    # join per cabinet: one object instead of ~100
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        for mod in p.modifiers:
            bpy.context.view_layer.objects.active = p
            bpy.ops.object.modifier_apply(modifier=mod.name)
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    parts[0].name = f"drawer_cabinet_{k}"

# ---------------------------------------------------------------- steel shelving on the right wall
C_SHELF = collection("shelving")
for u, (y0, y1) in enumerate(((1.15, 2.35), (2.45, 3.65), (3.75, 4.95))):
    x0, x1, h = W - 0.46, W - 0.01, 1.95
    for x in (x0, x1 - 0.035):
        for y in (y0, y1 - 0.035):
            box(f"rack{u}_post_{x:.2f}_{y:.2f}", (x, y, 0), (x + 0.035, y + 0.035, h), M["shelfsteel"], C_SHELF, bevel=0.001)
    for z in (0.08, 0.5, 0.92, 1.34, 1.76):
        box(f"rack{u}_shelf_{z}", (x0, y0, z), (x1, y1, z + 0.02), M["shelfsteel"], C_SHELF, bevel=0.001)

# ---------------------------------------------------------------- ceiling: fluorescent fixtures (off) + conduit
C_CEIL = collection("ceiling")
for y in (2.0, 4.6):
    box(f"fixture_{y}", (1.9, y - 0.65, H - 0.06), (2.3, y + 0.65, H), M["fixture"], C_CEIL)
    for dx in (-0.08, 0.08):
        cylinder(f"tube_{y}_{dx}", (2.1 + dx, y, H - 0.08), 0.013, 1.2, M["tube"], C_CEIL, axis="Y")
cylinder("conduit_long", (0.12, D / 2, H - 0.04), 0.012, D, M["conduit"], C_CEIL, axis="Y")
cylinder("conduit_cross", (W / 2, D - 0.1, H - 0.04), 0.012, W, M["conduit"], C_CEIL, axis="X")
cylinder("conduit_drop", (0.04, BY0 + 0.3, (H + 1.0) / 2), 0.012, H - 1.0, M["conduit"], C_CEIL)
for y in (2.2, 3.4, 4.6):
    box(f"outlet_{y}", (0.0, y - 0.035, 0.95), (0.012, y + 0.035, 1.05), M["outlet"], C_SHELL)

# ---------------------------------------------------------------- textured planes: poster, calendar, repair tags
C_DECO = collection("deco")
plane("poster_parts", (W - 0.002, 5.55, 1.55), 0.5, 0.67, "-X", lib.image_mat("poster_parts", os.path.join(TEX, "poster_parts_0.png"), 0.8), C_DECO)
plane("calendar", (1.2, D - 0.002, 1.5), 0.36, 0.48, "-Y", lib.image_mat("calendar", os.path.join(TEX, "calendar_0.png"), 0.8), C_DECO)
tags = lib.image_mat("repair_tags", os.path.join(TEX, "tags_0.png"), 0.8)
for i in range(6):  # tags pinned along the shelf edge
    t = plane(f"tag_{i}", (0.33, BY0 + 0.4 + i * 0.6, 1.62), 0.07, 0.11, "X", tags, C_DECO)
    t.rotation_euler = (random.uniform(-0.15, 0.15), 0, 0)
    cell = random.randrange(8)
    u, v = cell % 4, cell // 4
    lib.set_uv_rect(t, u / 4, 1 - (v + 1) / 2, (u + 1) / 4, 1 - v / 2)

# ---------------------------------------------------------------- cameras (refined after dressing)
def camera(name, loc, target, lens):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.sensor_width = 36
    cam = bpy.data.objects.new(name, cd)
    sc.collection.objects.link(cam)
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return cam


sc.camera = camera("cam_wide", (3.35, 6.15, 1.55), (0.55, 1.2, 0.95), 20)
camera("cam_bench", (1.55, 3.2, 1.32), (0.25, 2.2, 0.92), 32)
camera("cam_front", (2.1, 5.9, 1.6), (2.1, 0, 1.2), 24)

os.makedirs(SCN, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(SCN, "repair_shell.blend"))
print("saved shell", len(bpy.data.objects), "objects")

# Window glass must not block light: refractive caustics are off, so a shadow-casting pane would cut off all street light.
for o in bpy.data.objects:
    if "glass" in o.name:
        o.visible_shadow = False
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(SCN, "repair_shell.blend"))
