"""Round 2 densify, coarse -> fine (the video's dressing passes), on top of dress.py's layout.

blender -b scenes/tokyo-electronics-repair/repair_dressed.blend --python scenes/tokyo-electronics-repair/scripts/dress2.py -- <A|B|C> [out.blend]
  A  mid props: boxed + binned repair jobs with tags on racks/shelves/floor, parts cart, second bench station extras,
     dressed sales counter (register, display case, ticket book, lamp, generic tissue box), generic spray cans and
     cup noodle (replacing branded generated ones), per-instance variation of repeated devices, street props outside.
  B  small clutter: screws, loose components, PCBs, braid, flux bottles, tweezers, screwdriver sets, cups and cans,
     ashtrays, receipts, tape rolls.
  C  micro / life: cables everywhere (curves with bevel, routed and dropped onto surfaces), ribbon cables, extension
     blocks, sticky notes, flyers, extra posters, price tags, peeling tape.
Each pass includes the previous ones. Everything is direct-modelled, so it runs while fal is unavailable.
Saves scenes/tokyo-electronics-repair/repair_dressed2.blend (or out.blend).
"""
import math
import os
import random
import sys

import bpy
import bmesh
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(__file__))
import lib  # noqa: E402
from lib import box, cylinder, plane  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:]
PASS = ARGS[0]
OUT = os.path.abspath(ARGS[1]) if len(ARGS) > 1 else os.path.join(lib.ROOT, "scenes", "tokyo-electronics-repair", "repair_dressed2.blend")
LEVEL = {"A": 1, "B": 2, "C": 3}[PASS]
TEX = os.path.join(lib.ROOT, "refs", "tokyo-electronics-repair", "tex")
W, D, H = 4.2, 6.5, 2.7
BZ = 0.88  # bench top
RX0, RX1 = W - 0.46, W - 0.01  # rack x span
RACK_Z = [0.1, 0.52, 0.94, 1.36, 1.78]  # rack shelf top surfaces
SHELF_Z = [1.705, 2.145]  # above-bench shelf tops, x 0..0.32
sc = bpy.context.scene
rnd = random.Random(11)


def coll(name):
    return lib.collection(name)


C_A, C_B, C_C, C_ST = (coll(n) for n in ("dress2_A_mid", "dress2_B_clutter", "dress2_C_micro", "street"))

# ---------------------------------------------------------------- materials
M = {
    "card": lib.grimy("cardboard", (0.42, 0.3, 0.17), (0.2, 0.13, 0.07), rough=(0.75, 0.9), amount=0.35, scale=4, bump=0.25),
    "card2": lib.grimy("cardboard_dark", (0.33, 0.23, 0.13), (0.15, 0.1, 0.05), rough=(0.75, 0.9), amount=0.4, scale=4, bump=0.25),
    "bin_blue": lib.grimy("bin_blue", (0.05, 0.16, 0.38), (0.05, 0.06, 0.06), rough=(0.4, 0.7), amount=0.3),
    "bin_grey": lib.grimy("bin_grey", (0.3, 0.31, 0.32), (0.1, 0.1, 0.09), rough=(0.4, 0.7), amount=0.3),
    "bin_red": lib.grimy("bin_red", (0.4, 0.04, 0.03), (0.1, 0.05, 0.04), rough=(0.4, 0.7), amount=0.3),
    "crate": lib.principled("crate_black", (0.02, 0.02, 0.02), 0.6),
    "steel": bpy.data.materials.get("shelf_steel"),
    "chrome": lib.principled("chrome_worn", (0.7, 0.7, 0.7), 0.25, 1.0),
    "rubber": lib.principled("rubber_black", (0.015, 0.015, 0.015), 0.55),
    "cable_w": lib.principled("cable_white", (0.6, 0.6, 0.56), 0.45),
    "cable_g": lib.principled("cable_grey", (0.18, 0.18, 0.18), 0.5),
    "beige": lib.grimy("beige_plastic", (0.55, 0.5, 0.4), (0.25, 0.2, 0.12), rough=(0.4, 0.6), amount=0.3),
    "dkplastic": lib.grimy("dark_plastic", (0.05, 0.05, 0.055), (0.12, 0.11, 0.1), rough=(0.35, 0.6), amount=0.3),
    "white_pl": lib.grimy("white_plastic", (0.7, 0.7, 0.66), (0.3, 0.27, 0.2), rough=(0.3, 0.5), amount=0.3),
    "wood": bpy.data.materials.get("door_wood"),
    "glass": lib.principled("case_glass", (0.95, 0.97, 0.96), 0.04, **{"Transmission Weight": 1.0}),
    "pcb": None,
    "copper": lib.principled("copper", (0.8, 0.45, 0.25), 0.35, 1.0),
    "solder": lib.principled("solder_tin", (0.6, 0.6, 0.62), 0.3, 1.0),
    "amber": lib.principled("amber_bottle", (0.55, 0.3, 0.05), 0.15, **{"Transmission Weight": 0.8}),
    "paper": lib.grimy("paper", (0.78, 0.76, 0.7), (0.4, 0.35, 0.25), rough=(0.7, 0.85), amount=0.2, bump=0.05),
    "tape_y": lib.principled("tape_yellowed", (0.75, 0.62, 0.35), 0.45, **{"Alpha": 0.85}),
    "tape_black": lib.principled("tape_black", (0.02, 0.02, 0.02), 0.35),
    "tape_kapton": lib.principled("tape_kapton", (0.75, 0.42, 0.05), 0.2, **{"Transmission Weight": 0.4}),
    "butt": lib.principled("cig_butt", (0.75, 0.55, 0.3), 0.8),
    "ash": lib.principled("ash", (0.25, 0.24, 0.23), 0.95),
    "coffee": lib.principled("coffee_can", (0.18, 0.09, 0.04), 0.35, 0.6),
    "green_shade": lib.principled("lamp_green_glass", (0.03, 0.22, 0.08), 0.15, **{"Coat Weight": 1.0}),
    "brass": lib.principled("brass", (0.7, 0.5, 0.2), 0.3, 1.0),
}
for k in ("cable_w", "cable_g", "rubber"):
    pass
# PCB: green solder mask with copper-ish traces (voronoi edges) and silkscreen speckle
pm = bpy.data.materials.get("pcb_green") or bpy.data.materials.new("pcb_green")
if not pm.get("built"):
    nt = pm.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    vo = nt.nodes.new("ShaderNodeTexVoronoi")
    vo.feature = "DISTANCE_TO_EDGE"
    vo.inputs["Scale"].default_value = 60
    nt.links.new(tc.outputs["Object"], vo.inputs["Vector"])
    tr = lib._ramp(nt, vo.outputs["Distance"], [(0.0, (0.35, 0.42, 0.12)), (0.04, (0.02, 0.16, 0.05))])
    nt.links.new(tr.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.35
    nt.links.new(lib._bump(nt, vo.outputs["Distance"], 0.15), b.inputs["Normal"])
    pm["built"] = True
M["pcb"] = pm


def img_mat(name, path, rough=0.75, alpha=False):
    return lib.image_mat(name, os.path.join(TEX, path), rough=rough, alpha=alpha)


M["tags"] = img_mat("repair_tags", "tags_0.png", 0.8)
M["labels"] = bpy.data.materials.get("drawer_labels")


def tinted_paper(name, col):
    """Coloured paper whose 'ink' comes from the labels sheet (handwriting), for sticky notes / flyers."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(os.path.join(TEX, "labels_0.png"), check_existing=True)
    col_out = lib._mix(nt, 1.0, t.outputs["Color"], col, "MULTIPLY")
    nt.links.new(col_out, b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.8
    return m


M["sticky_y"] = tinted_paper("sticky_yellow", (1.0, 0.85, 0.25))
M["sticky_p"] = tinted_paper("sticky_pink", (1.0, 0.55, 0.65))
M["sticky_b"] = tinted_paper("sticky_blue", (0.55, 0.8, 1.0))
M["flyer_y"] = tinted_paper("flyer_yellow", (0.95, 0.9, 0.55))
M["flyer_w"] = tinted_paper("flyer_white", (0.9, 0.88, 0.82))
M["price_o"] = tinted_paper("price_orange", (1.0, 0.45, 0.05))

# ---------------------------------------------------------------- helpers


def apply_mods(ob):
    for m in list(ob.modifiers):
        with bpy.context.temp_override(object=ob, active_object=ob):
            bpy.ops.object.modifier_apply(modifier=m.name)


def join(objs, name, c):
    objs = [o for o in objs if o]
    for o in objs:
        apply_mods(o)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    ob = objs[0]
    ob.name = name
    lib.link(ob, c)
    bottom_origin(ob)
    return ob


def ray_down(x, y, start, ignore=()):
    """Highest surface under (x, y) below start, ignoring objects in `ignore` (moved out of the way)."""
    moved = []
    for o in ignore:
        moved.append((o, o.location.z))
        o.location.z -= 100
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    hit, loc, n, i, ob, m = sc.ray_cast(dg, Vector((x, y, start)), Vector((0, 0, -1)))
    for o, z in moved:
        o.location.z = z
    if moved:
        bpy.context.view_layer.update()
    return (loc.z, ob) if hit else (0.0, None)


def settle(ob, z):
    """Shift ob so its lowest world-space point sits at z (works whatever the origin)."""
    bpy.context.view_layer.update()
    pts = [ob.matrix_world @ Vector(cn) for cn in ob.bound_box]
    ob.location.z += z - min(p.z for p in pts)
    bpy.context.view_layer.update()


def put(ob, x, y, start, yaw=0.0, lift=0.0):
    """Place an object on the surface under (x, y)."""
    ob.location = (x, y, -50)
    ob.rotation_euler = (ob.rotation_euler.x, ob.rotation_euler.y, math.radians(yaw))
    z, _ = ray_down(x, y, start)
    settle(ob, z + lift)
    return ob


def bottom_origin(ob):
    """Move a mesh's origin to its bottom centre (in place)."""
    me = ob.data
    vs = [v.co for v in me.vertices]
    lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    off = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    me.transform(Matrix.Translation(-off))
    bpy.context.view_layer.update()
    ob.location = ob.matrix_world @ off
    return ob


def local_box(name, sx, sy, sz, mat, c, bevel=0.002, z0=0.0, ox=0.0, oy=0.0):
    """Box centred at (ox, oy) in local space, sitting on z0; world placement comes later via join + put."""
    return box(name, (ox - sx / 2, oy - sy / 2, z0), (ox + sx / 2, oy + sy / 2, z0 + sz), mat, c, bevel=bevel)


def local_cyl(name, r, h, mat, c, x=0.0, y=0.0, z0=0.0, axis="Z", verts=16):
    if axis == "Z":
        return cylinder(name, (x, y, z0 + h / 2), r, h, mat, c, verts=verts)
    return cylinder(name, (x, y, z0), r, h, mat, c, axis=axis, verts=verts)


def tag_plane(name, centre, normal, c, w=0.06, h=0.09, rot=0.0):
    """Paper repair tag from the tags sheet (random ticket)."""
    t = plane(name, centre, w, h, normal, M["tags"], c)
    cell = rnd.randrange(8)
    u, v = cell % 4, cell // 4
    lib.set_uv_rect(t, u / 4 + 0.01, 1 - (v + 1) / 2 + 0.01, (u + 1) / 4 - 0.01, 1 - v / 2 - 0.01)
    if normal in ("-Y", "Y"):
        t.rotation_euler.y = rot
    elif normal in ("-X", "X"):
        t.rotation_euler.x = rot
    else:
        t.rotation_euler.z = rot
    return t


def cardboard_box(name, sx, sy, sz, c, open_top=False, tag_side=None):
    parts = []
    mat = M["card"] if rnd.random() < 0.6 else M["card2"]
    if open_top:
        th = 0.004
        parts += [local_box("b", sx, sy, th, mat, c, 0),
                  local_box("w1", th, sy, sz, mat, c, 0, ox=-sx / 2 + th / 2), local_box("w2", th, sy, sz, mat, c, 0, ox=sx / 2 - th / 2),
                  local_box("w3", sx, th, sz, mat, c, 0, oy=-sy / 2 + th / 2), local_box("w4", sx, th, sz, mat, c, 0, oy=sy / 2 - th / 2)]
        for s in (-1, 1):  # flaps folded outwards
            f = local_box("flap", sx * 0.96, th, sy * 0.45, mat, c, 0)
            f.location = (0, s * sy / 2, sz)
            f.rotation_euler.x = s * math.radians(rnd.uniform(100, 135))
            parts.append(f)
    else:
        parts.append(local_box("box", sx, sy, sz, mat, c, 0.004))
        tape = local_box("tape", sx * 1.002, 0.05, 0.001, M["tape_y"], c, 0, z0=sz)
        parts.append(tape)
    ob = join(parts, name, c)
    if tag_side:
        t = tag_plane(name + "_tag", (0, 0, sz * 0.5), tag_side, c)
        t.location = ({"-Y": (rnd.uniform(-sx / 4, sx / 4), -sy / 2 - 0.0015, sz * rnd.uniform(0.35, 0.65)),
                       "X": (sx / 2 + 0.0015, rnd.uniform(-sy / 4, sy / 4), sz * rnd.uniform(0.35, 0.65)),
                       "-X": (-sx / 2 - 0.0015, rnd.uniform(-sy / 4, sy / 4), sz * rnd.uniform(0.35, 0.65))}[tag_side])
        t.parent = ob
    return ob


def plastic_bin(name, sx, sy, sz, mat, c):
    th = 0.004
    parts = [local_box("b", sx, sy, th, mat, c, 0),
             local_box("w1", th, sy, sz, mat, c, 0, ox=-sx / 2 + th / 2), local_box("w2", th, sy, sz, mat, c, 0, ox=sx / 2 - th / 2),
             local_box("w3", sx, th, sz, mat, c, 0, oy=-sy / 2 + th / 2), local_box("w4", sx, th, sz * 0.7, mat, c, 0, oy=sy / 2 - th / 2)]
    return join(parts, name, c)


def instance(src_name, name, c, scale=1.0):
    src = bpy.data.objects.get(f"src_{src_name}") or bpy.data.objects.get(f"src_{src_name}_nb") or bpy.data.objects.get(src_name)
    if src is None:
        return None
    ob = src.copy()
    ob.animation_data_clear()
    ob.name = name
    c.objects.link(ob)
    ob.rotation_mode = "XYZ"
    ob.rotation_euler = (0, 0, 0)
    ob.scale = (scale, scale, scale)
    ob.hide_render = False
    ob.hide_viewport = False
    for k in ("placed", "prop_id", "wall"):
        if k in ob:
            del ob[k]
    ob["tv_on"] = 0.0
    return ob


def tint(ob, kind=None):
    """Per-instance colour variation read by the grime layer through Object Info > Color."""
    k = kind or rnd.choice(["yellowed", "dark", "cool", "plain"])
    ob.color = {"yellowed": (1.0, 0.93, 0.78, 1), "dark": (0.78, 0.76, 0.74, 1), "cool": (0.9, 0.95, 1.0, 1), "plain": (1, 1, 1, 1)}[k]


# =================================================================== PASS A: mid props
def pass_a():
    c = C_A
    # --- remove nothing; vary repeated generated devices (tint + a tag) -----------------------------------
    seen = {}
    for o in [o for o in sc.objects if o.get("placed")]:
        pid = o.get("prop_id")
        seen[pid] = seen.get(pid, 0) + 1
        if seen[pid] > 1 or pid in ("repair_crt_tv", "repair_receiver", "repair_vcr_open"):
            tint(o)
    # --- racks: boxed and binned repair jobs in the gaps ----------------------------------------------------
    rack_slots = [  # (y, shelf index) gaps measured from the pass-4 layout
        (1.32, 1), (2.42, 1), (3.62, 1), (1.95, 3), (2.55, 3), (4.05, 3), (4.62, 2), (1.35, 2), (3.4, 0), (4.4, 0),
        (2.9, 2), (3.75, 2), (2.25, 3), (4.75, 3), (3.25, 3),
    ]
    for i, (y, s) in enumerate(rack_slots):
        z_cap = (RACK_Z[s + 1] if s + 1 < len(RACK_Z) else 2.3) - RACK_Z[s] - 0.03
        if rnd.random() < 0.55:
            sx, sy, sz = rnd.uniform(0.28, 0.4), rnd.uniform(0.22, 0.34), min(z_cap, rnd.uniform(0.18, 0.34))
            ob = cardboard_box(f"rack_box_{i}", sx, sy, sz, c, open_top=rnd.random() < 0.35, tag_side="-X")
        else:
            mat = rnd.choice([M["bin_blue"], M["bin_grey"], M["bin_red"]])
            sx, sy, sz = 0.36, 0.28, min(z_cap, 0.16)
            ob = plastic_bin(f"rack_bin_{i}", sx, sy, sz, mat, c)
            t = tag_plane(f"rack_bin_{i}_tag", (0, 0, 0), "-X", c)
            t.location = (-sx / 2 - 0.002, rnd.uniform(-0.08, 0.08), sz * 0.6)
            t.parent = ob
            inner = instance(rnd.choice(["repair_vintage_radio", "repair_multimeter_red", "repair_vcr_open", "repair_receiver"]), f"rack_bin_{i}_job", c, 0.62)
            if inner:
                inner.parent = ob
                inner.location = (0, 0, 0.005)
                inner.rotation_euler.z = math.radians(rnd.uniform(-20, 20) - 90)
                tint(inner)
        ob.location = (rnd.uniform(RX0 + 0.2, RX1 - 0.22), y, 0)
        put(ob, ob.location.x, y, RACK_Z[s] + 0.2, yaw=rnd.uniform(-6, 6))
    # rack tops: stacked boxes up to near the ceiling
    for i, y in enumerate([1.35, 1.8, 2.5, 3.05, 3.7, 4.3, 4.75]):
        h = 0
        for k in range(rnd.randint(1, 3)):
            sz = rnd.uniform(0.15, 0.26)
            ob = cardboard_box(f"rack_top_{i}_{k}", rnd.uniform(0.3, 0.42), rnd.uniform(0.28, 0.38), sz, c, tag_side="-X" if k == 0 else None)
            put(ob, RX0 + 0.22 + rnd.uniform(-0.02, 0.02), y, 2.55, yaw=rnd.uniform(-8, 8))
            h += sz
            if h > 0.5:
                break
    # --- above-bench shelves --------------------------------------------------------------------------------
    for i, (y, s) in enumerate([(1.35, 1), (2.05, 1), (2.55, 1), (3.3, 1), (3.95, 1), (5.05, 0), (5.2, 1), (2.6, 0), (3.35, 0)]):
        if rnd.random() < 0.5:
            ob = cardboard_box(f"shelf_box_{i}", rnd.uniform(0.2, 0.3), rnd.uniform(0.22, 0.32), rnd.uniform(0.14, 0.24) if s == 0 else rnd.uniform(0.16, 0.3), c, tag_side="X")
        else:
            ob = plastic_bin(f"shelf_bin_{i}", 0.28, 0.24, 0.13, rnd.choice([M["bin_blue"], M["bin_grey"]]), c)
        put(ob, 0.16, y, SHELF_Z[s] + (0.4 if s == 0 else 0.5), yaw=rnd.uniform(-5, 5))
    # --- under-bench: cable crate, boxes --------------------------------------------------------------------
    for i, y in enumerate([2.05, 3.45, 4.35]):
        ob = cardboard_box(f"under_box_{i}", 0.4, 0.34, rnd.uniform(0.22, 0.32), c, open_top=True, tag_side="X")
        put(ob, 0.32, y, 0.6, yaw=rnd.uniform(-10, 10))
    crate = plastic_bin("cable_crate", 0.42, 0.32, 0.26, M["crate"], c)
    put(crate, 0.33, 5.0, 0.6, yaw=88)
    # --- floor: boxes under the windows, job bins by the racks, umbrella stand by the door ---------------------
    for i, (x, y, yaw) in enumerate([(0.35, 0.35, 5), (0.75, 0.32, -4), (3.2, 0.3, 3), (3.75, 0.95, 80), (2.1, 6.2, 2)]):
        for k in range(rnd.randint(1, 3)):
            ob = cardboard_box(f"floor_box_{i}_{k}", rnd.uniform(0.35, 0.5), rnd.uniform(0.3, 0.42), rnd.uniform(0.2, 0.32), c, tag_side=("-X" if x > 2.1 else "X") if k == 0 else None)
            put(ob, x + rnd.uniform(-0.03, 0.03), y + rnd.uniform(-0.03, 0.03), 1.5, yaw=yaw + rnd.uniform(-8, 8))
    for i, (x, y) in enumerate([(3.45, 2.6), (3.5, 4.2)]):
        ob = plastic_bin(f"floor_bin_{i}", 0.42, 0.32, 0.2, rnd.choice([M["bin_blue"], M["bin_grey"]]), c)
        put(ob, x, y, 0.5, yaw=rnd.uniform(-10, 10))
        inner = instance(rnd.choice(["repair_receiver", "repair_vcr_open"]), f"floor_bin_{i}_job", c, 0.8)
        if inner:
            inner.parent = ob
            inner.location = (0, 0, 0.005)
            inner.rotation_euler.z = math.radians(-90)
            tint(inner)
    stand = local_cyl("umb_stand", 0.12, 0.45, M["steel"], c)
    parts = [stand]
    for k, (dx, dy, col) in enumerate([(0.03, 0.02, (0.85, 0.9, 0.95)), (-0.03, 0.03, (0.85, 0.9, 0.95)), (0.0, -0.04, (0.02, 0.02, 0.02))]):
        um = lib.principled(f"umbrella_{k}", col, 0.2, **({"Transmission Weight": 0.7} if col[0] > 0.5 else {}))
        bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=0.06, radius2=0.015, depth=0.72, location=(dx, dy, 0.6))
        u = bpy.context.object
        u.rotation_euler = (rnd.uniform(-0.12, 0.12), rnd.uniform(-0.12, 0.12), 0)
        u.data.materials.append(um)
        lib.link(u, c)
        h = local_cyl("umb_handle", 0.008, 0.25, M["dkplastic"], c, dx, dy, 0.96)
        parts += [u, h]
    st = join(parts, "umbrella_stand", c)
    put(st, 2.9, 0.25, 1.0)
    puddle = plane("umbrella_puddle", (2.55, 0.3, 0.0015), 0.5, 0.4, "Z", lib.principled("puddle", (0.05, 0.05, 0.05), 0.02), c)
    puddle.rotation_euler.z = 0.4
    # --- parts cart ----------------------------------------------------------------------------------------
    parts = []
    for z in (0.12, 0.45, 0.78):
        parts.append(local_box(f"cart_shelf_{z}", 0.62, 0.42, 0.02, M["steel"], c, 0.001, z0=z))
        parts.append(local_box(f"cart_lip_{z}", 0.62, 0.42, 0.035, M["steel"], c, 0.001, z0=z))
    for sx_ in (-1, 1):
        for sy_ in (-1, 1):
            parts.append(local_cyl("post", 0.012, 0.75, M["steel"], c, sx_ * 0.3, sy_ * 0.2, 0.08))
            parts.append(local_cyl("caster", 0.035, 0.03, M["rubber"], c, sx_ * 0.29, sy_ * 0.19, 0.035, axis="X"))
    # hollow out the lips: replace the 0.035 boxes by thin rims
    parts = [p for p in parts if not p.name.startswith("cart_lip")]
    cart = join(parts, "parts_cart", c)
    put(cart, 1.55, 5.55, 1.5, yaw=12)
    for k, (src, dz) in enumerate([("boombox_open", 0.8), ("repair_vcr_open", 0.47)]):
        it = instance(src, f"cart_load_{k}", c, 0.62 if src == "boombox_open" else 0.9)
        if it:
            put(it, 1.55, 5.55, cart.location.z + dz + 0.25, yaw=12 + rnd.uniform(-10, 10))
            tint(it)
    cb = cardboard_box("cart_box", 0.35, 0.3, 0.22, c, open_top=True)
    put(cb, 1.52, 5.55, cart.location.z + 0.4, yaw=8)
    # --- sales counter -------------------------------------------------------------------------------------
    CZ = 0.95
    # cash register (faces the clerk, +Y)
    parts = [local_box("reg_base", 0.36, 0.38, 0.09, M["beige"], c, 0.006),
             local_box("reg_keys", 0.3, 0.17, 0.05, M["beige"], c, 0.006, z0=0.09, oy=0.06),
             local_box("reg_disp", 0.14, 0.05, 0.06, M["dkplastic"], c, 0.004, z0=0.12, oy=-0.12),
             local_box("reg_printer", 0.1, 0.12, 0.04, M["beige"], c, 0.004, z0=0.09, ox=0.11, oy=-0.07)]
    for kx in range(6):
        for ky in range(4):
            parts.append(local_box("key", 0.034, 0.03, 0.012, M["white_pl"] if (kx + ky) % 3 else M["dkplastic"], c, 0.002,
                                   z0=0.14, ox=-0.11 + kx * 0.044, oy=0.0 + ky * 0.037))
    reg = join(parts, "cash_register", c)
    put(reg, 3.3, 1.82, 1.5, yaw=180 + 4)
    disp = plane("register_display", (0, 0, 0), 0.12, 0.035, "Y", lib.emissive("register_vfd", (0.2, 1.0, 0.7), 1.5), c)
    disp.parent = reg
    disp.location = (0, -0.146, 0.15)  # register origin is its bottom centre (join)
    # display case at the customer end of the counter
    parts = [local_box("case_base", 0.48, 0.42, 0.06, M["wood"], c, 0.003)]
    for sx_ in (-1, 1):
        for sy_ in (-1, 1):
            parts.append(local_box("case_post", 0.02, 0.02, 0.32, M["wood"], c, 0.001, z0=0.06, ox=sx_ * 0.23, oy=sy_ * 0.2))
    parts.append(local_box("case_top_frame", 0.48, 0.42, 0.02, M["wood"], c, 0.002, z0=0.38))
    case = join(parts, "display_case", c)
    glass = [local_box("cg_f", 0.44, 0.004, 0.32, M["glass"], c, 0, z0=0.06, oy=-0.2), local_box("cg_b", 0.44, 0.004, 0.32, M["glass"], c, 0, z0=0.06, oy=0.2),
             local_box("cg_l", 0.004, 0.38, 0.32, M["glass"], c, 0, z0=0.06, ox=-0.23), local_box("cg_r", 0.004, 0.38, 0.32, M["glass"], c, 0, z0=0.06, ox=0.23),
             local_box("cg_t", 0.44, 0.38, 0.004, M["glass"], c, 0, z0=0.395), local_box("cg_shelf", 0.44, 0.38, 0.005, M["glass"], c, 0, z0=0.22)]
    cg = join(glass, "display_case_glass", c)
    cg.visible_shadow = False
    put(case, 2.17, 1.83, 1.5, yaw=-3)
    cg.location = case.location + Vector((0, 0, 0.06))
    cg.rotation_euler = case.rotation_euler.copy()
    for k, (src, sc_, lx, ly, lz) in enumerate([("repair_multimeter_yellow", 0.7, -0.12, 0.0, 0.065), ("repair_multimeter_red", 0.6, 0.1, 0.02, 0.065),
                                                 ("repair_vintage_radio", 0.42, -0.06, 0.02, 0.227), ("repair_mug", 0.0, 0, 0, 0)]):
        if sc_ == 0:
            continue
        it = instance(src, f"case_item_{k}", c, sc_)
        if it:
            it.parent = case
            it.location = (lx, ly, lz)
            it.rotation_euler.z = math.radians(180 + rnd.uniform(-20, 20))
            pt = plane(f"case_price_{k}", (0, 0, 0), 0.03, 0.02, "Y", M["price_o"], c)
            pt.parent = case
            pt.location = (lx, ly - 0.07, lz + 0.03)
    # ticket book + pen
    tb = join([local_box("tb", 0.1, 0.17, 0.02, M["paper"], c, 0.001), local_box("tb_cover", 0.102, 0.172, 0.002, M["bin_blue"], c, 0)], "ticket_book", c)
    put(tb, 2.6, 2.04, 1.5, yaw=-8)
    top = plane("ticket_book_top", (0, 0, 0.0205), 0.095, 0.165, "Z", M["tags"], c)
    lib.set_uv_rect(top, 0.0, 0.5, 0.25, 1.0)
    top.parent = tb
    top.location = (0, 0, 0.0205)
    pen = local_cyl("pen", 0.004, 0.14, M["bin_blue"], c, axis="X")
    pen.location = (2.66, 2.05, CZ + 0.026)
    pen.rotation_euler.z = 0.5
    # counter lamp (green banker lamp) at the clerk end
    parts = [local_cyl("lamp_base", 0.075, 0.02, M["brass"], c, verts=24), local_cyl("lamp_stem", 0.008, 0.3, M["brass"], c, z0=0.02)]
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.06, depth=0.24, location=(0, 0.05, 0.33))
    sh = bpy.context.object
    sh.rotation_euler = (0, math.pi / 2, 0)
    bm = bmesh.new()
    bm.from_mesh(sh.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.x > 0.005 and False], context="VERTS")
    bm.to_mesh(sh.data)
    bm.free()
    sh.scale = (1, 1, 0.6)
    sh.data.materials.append(M["green_shade"])
    lib.link(sh, c)
    parts.append(sh)
    lamp = join(parts, "counter_lamp", c)
    put(lamp, 3.4, 2.07, 1.5, yaw=180)
    # generic tissue box on the counter, cup noodle + spray cans replacements on the bench / shelf
    tbx = local_box("tissue", 0.24, 0.12, 0.09, tinted_paper("tissue_print", (0.85, 0.88, 0.95)), c, 0.004)
    tis = plane("tissue_puff", (0, 0, 0.1), 0.12, 0.08, "Y", M["paper"], c)
    tis.rotation_euler.z = 0.3
    tis_ob = join([tbx, tis], "tissue_box_generic", c)
    put(tis_ob, 0.16, 5.25, 1.2, yaw=95)
    cup = cylinder("cupnoodle", (0, 0, 0.055), 0.045, 0.11, lib.principled("cup_white", (0.85, 0.83, 0.78), 0.6), c, verts=24)
    bm = bmesh.new()
    bm.from_mesh(cup.data)
    for v in bm.verts:
        if v.co.z < 0:
            v.co.x *= 0.78
            v.co.y *= 0.78
    bm.to_mesh(cup.data)
    bm.free()
    band = cylinder("cup_band", (0, 0, 0.07), 0.0445, 0.03, lib.principled("cup_band_red", (0.55, 0.04, 0.03), 0.5), c, verts=24)
    lid = plane("cup_lid", (0.015, 0.0, 0.111), 0.07, 0.07, "Z", lib.principled("lid_foil", (0.75, 0.74, 0.7), 0.35, 0.7), c)
    lid.rotation_euler = (0.0, -0.5, 0.2)
    sticks = [local_box(f"chop_{k}", 0.2, 0.006, 0.005, lib.principled("chopstick", (0.75, 0.6, 0.4), 0.7), c, 0, z0=0.112, oy=k * 0.012) for k in (0, 1)]
    cn = join([cup, band, lid] + sticks, "cup_noodle_generic", c)
    put(cn, 0.62, 5.28, 1.2, yaw=30)
    can_cols = [(0.05, 0.25, 0.08), (0.75, 0.75, 0.78), (0.08, 0.12, 0.45)]
    for g, (gx, gy, gz, gname) in enumerate([(0.15, 2.65, SHELF_Z[0] + 0.3, "shelf"), (RX0 + 0.12, 1.3, RACK_Z[3] + 0.3, "rack")]):
        cans = []
        for k, col in enumerate(can_cols):
            cm = lib.grimy(f"can_paint_{k}", col, (0.15, 0.13, 0.1), rough=(0.25, 0.5), metal=0.6, amount=0.3)
            body = cylinder(f"can_{k}", (0, k * 0.07, 0.085), 0.03, 0.17, cm, c, verts=20)
            label = cylinder(f"can_label_{k}", (0, k * 0.07, 0.08), 0.0305, 0.09, lib.principled(f"can_label_{k}", (0.85, 0.82, 0.7) if k != 1 else (0.2, 0.3, 0.6), 0.5), c, verts=20)
            cap = cylinder(f"can_cap_{k}", (0, k * 0.07, 0.185), 0.026, 0.03, lib.principled(f"can_cap_{k}", ((0.6, 0.05, 0.03), (0.9, 0.9, 0.9), (0.02, 0.02, 0.02))[k], 0.4), c, verts=16)
            cans += [body, label, cap]
        straw = local_box("straw", 0.004, 0.004, 0.16, lib.principled("straw_red", (0.7, 0.02, 0.02), 0.4), c, 0, ox=0.02, oy=0.07, z0=0.2)
        straw.rotation_euler.x = 0.9
        ob = join(cans + [straw], f"spray_cans_generic_{gname}", c)
        bottom_origin(ob)
        put(ob, gx, gy, gz, yaw=rnd.uniform(-20, 20))
    # PCB vise + ring magnifier lamp at the second station
    vise = join([local_box("vise_base", 0.14, 0.1, 0.025, M["dkplastic"], c, 0.004),
                 local_cyl("vise_post_l", 0.006, 0.08, M["chrome"], c, -0.06, 0, 0.025), local_cyl("vise_post_r", 0.006, 0.08, M["chrome"], c, 0.06, 0, 0.025),
                 local_box("vise_jaw_l", 0.012, 0.02, 0.03, M["dkplastic"], c, 0.002, z0=0.09, ox=-0.06), local_box("vise_jaw_r", 0.012, 0.02, 0.03, M["dkplastic"], c, 0.002, z0=0.09, ox=0.06),
                 local_box("vise_pcb", 0.11, 0.075, 0.0016, M["pcb"], c, 0, z0=0.105)], "pcb_vise", c)
    vise.rotation_euler.x = 0
    put(vise, 0.55, 4.72, 1.2, yaw=95)
    for k in range(10):  # components on the vise board
        cc = local_cyl(f"vise_cap_{k}", rnd.uniform(0.002, 0.004), rnd.uniform(0.004, 0.01), rnd.choice([M["bin_blue"], M["dkplastic"]]), c, verts=8)
        cc.parent = vise
        cc.location = (rnd.uniform(-0.045, 0.045), rnd.uniform(-0.03, 0.03), 0.107)
    ring = [local_box("ring_base", 0.16, 0.16, 0.025, M["white_pl"], c, 0.006), local_cyl("ring_arm1", 0.008, 0.36, M["white_pl"], c, 0, 0, 0.025)]
    bpy.ops.mesh.primitive_torus_add(major_radius=0.075, minor_radius=0.018, location=(0.18, 0, 0.42))
    tor = bpy.context.object
    tor.rotation_euler = (0, math.radians(-25), 0)
    tor.data.materials.append(M["white_pl"])
    lib.link(tor, c)
    arm2 = local_box("ring_arm2", 0.2, 0.014, 0.014, M["white_pl"], c, 0.002, z0=0.38, ox=0.09)
    ring += [tor, arm2]
    rl = join(ring, "ring_lamp", c)
    lens = cylinder("ring_lamp_lens", (0, 0, 0), 0.06, 0.006, M["glass"], c, verts=32)
    lens.parent = rl
    ox = rl.location.x  # join moved the origin to the bbox centre; children are given in the design frame
    lens.location = (0.18 - ox, 0, 0.42)
    lens.rotation_euler = (0, math.radians(65), 0)
    lens.visible_shadow = False
    led = lib.emissive("ring_led", (0.85, 0.92, 1.0), 6.0)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.066, minor_radius=0.004, location=(0, 0, 0))
    lr = bpy.context.object
    lr.name = "ring_lamp_led"
    lr.data.materials.append(led)
    lib.link(lr, c)
    lr.parent = rl
    lr.location = (0.18 - ox, 0, 0.405)
    lr.rotation_euler = (0, math.radians(-25), 0)
    lz, _ = ray_down(0.12, 4.42, 1.2)
    rl.location = (0.12 + ox, 4.42, lz)
    # a spare fluorescent fixture over the racks, one tube left on (lights.py adds its light)
    fx = box("fixture_racks", (3.6, 2.4, H - 0.06), (4.0, 3.7, H), bpy.data.materials.get("fixture_white"), c)
    for dx in (-0.08, 0.08):
        t = cylinder(f"tube_racks_{dx}", (3.8 + dx, 3.05, H - 0.08), 0.013, 1.2, bpy.data.materials.get("fluoro_tube_off"), c, axis="Y")
        if dx > 0:
            t.name = "tube_on"
            t.data.materials.clear()
            t.data.materials.append(lib.emissive("fluoro_on", (0.82, 0.92, 1.0), 4.0))
    # clip lamp clamped to the top of the middle rack post, shade tipped down into the aisle and the rack shelves
    cx, cy, cz = RX0 + 0.02, 3.68, 1.97
    parts = [box("clip_clamp", (cx - 0.02, cy - 0.025, cz - 0.05), (cx + 0.04, cy + 0.025, cz + 0.01), M["dkplastic"], c, bevel=0.003),
             cylinder("clip_arm", (cx - 0.06, cy, cz + 0.08), 0.006, 0.2, M["chrome"], c, verts=8)]
    parts[1].rotation_euler.y = -0.6
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=0.075, radius2=0.025, depth=0.12, end_fill_type="NOTHING", location=(cx - 0.14, cy, cz + 0.13))
    shade = bpy.context.object
    shade.rotation_euler = (0, math.radians(-50), 0)
    shade.data.materials.append(lib.principled("clip_shade_black", (0.03, 0.03, 0.03), 0.4, 0.6))
    shade.modifiers.new("solid", "SOLIDIFY").thickness = 0.002
    lib.link(shade, c)
    parts.append(shade)
    join(parts, "rack_clip_lamp", c)
    bulb = cylinder("rack_clip_bulb", (cx - 0.165, cy, cz + 0.105), 0.022, 0.03, lib.emissive("clip_bulb", (1.0, 0.82, 0.6), 25.0), c, verts=16)
    bulb.rotation_euler = (0, math.radians(-50), 0)
    cable("clip_lamp_cord", [(cx, cy, cz - 0.04), (cx + 0.02, cy + 0.05, cz - 0.3), (cx + 0.03, cy + 0.1, 1.2), (cx + 0.05, cy + 0.15, 0.5), (RX1 - 0.02, 3.4, 0.02)], 0.0025, M["rubber"], c)
    # TVs left on for glow on the racks and the counter side
    for n in ("crt_rack", "fill_crt_2"):
        o = sc.objects.get(n)
        if o:
            o["tv_on"] = 1.0
    street_props()


def street_props():
    """3D layer between the storefront and the backdrop so moving cameras get parallax."""
    c = C_ST
    pole = cylinder("utility_pole", (3.9, -2.6, 3.0), 0.13, 6.0, lib.grimy("pole_concrete", (0.4, 0.4, 0.38), (0.15, 0.15, 0.14), amount=0.4), c, verts=16)
    for k, z in enumerate((2.0, 2.6)):
        box(f"pole_sign_{k}", (3.76, -2.62, z), (4.04, -2.6, z + 0.35), lib.principled(f"pole_sign_{k}", ((0.85, 0.75, 0.1), (0.85, 0.85, 0.85))[k], 0.5), c, bevel=0)
    # vending machine across the street: lit front panel
    vm = box("vending_machine", (-0.6, -3.6, 0.0), (0.4, -2.9, 1.83), lib.principled("vending_body", (0.75, 0.1, 0.08), 0.3), c, bevel=0.01)
    vmp = lib.emissive("vending_panel", (0.95, 0.97, 1.0), 1.2)
    vf = plane("vending_panel", (-0.1, -2.895, 1.15), 0.84, 0.95, "Y", vmp, c)
    for r in range(3):
        for k in range(6):
            bx = box(f"vm_bottle_{r}_{k}", (-0.45 + k * 0.14, -2.9, 0.82 + r * 0.32), (-0.39 + k * 0.14, -2.88, 0.98 + r * 0.32),
                     lib.principled(f"vm_bottle_{(r + k) % 4}", ((0.8, 0.2, 0.1), (0.1, 0.4, 0.8), (0.9, 0.8, 0.2), (0.2, 0.6, 0.3))[(r + k) % 4], 0.3), c, bevel=0)
    # A-frame sign with a small lamp
    sign_m = lib.grimy("chalkboard", (0.03, 0.05, 0.04), (0.3, 0.3, 0.3), amount=0.5, scale=6)
    for s in (-1, 1):
        p = box(f"aframe_{s}", (1.0, -1.25, 0.0), (1.55, -1.23, 0.85), sign_m, c, bevel=0)
        p.rotation_euler.x = s * 0.18
    box("aframe_lamp", (1.24, -1.28, 0.85), (1.31, -1.2, 0.92), lib.emissive("aframe_bulb", (1.0, 0.75, 0.4), 6), c, bevel=0)
    # bicycle: two wheels + frame tubes
    bk = []
    for k, y in enumerate((-1.95, -2.95)):
        bpy.ops.mesh.primitive_torus_add(major_radius=0.33, minor_radius=0.018, location=(2.7, y, 0.35))
        wh = bpy.context.object
        wh.name = f"bike_wheel_{k}"
        wh.rotation_euler = (0, math.pi / 2, 0)
        wh.data.materials.append(M["rubber"])
        lib.link(wh, c)
        bk.append(wh)
    for a_, b_ in [((2.7, -1.95, 0.35), (2.7, -2.45, 0.85)), ((2.7, -2.95, 0.35), (2.7, -2.45, 0.85)), ((2.7, -2.45, 0.85), (2.7, -2.05, 0.95)),
                   ((2.7, -2.05, 0.95), (2.7, -1.95, 0.35)), ((2.7, -2.45, 0.85), (2.7, -2.75, 0.9))]:
        av, bv = Vector(a_), Vector(b_)
        t = cylinder("bike_tube", (av + bv) / 2, 0.014, (bv - av).length, lib.principled("bike_black", (0.02, 0.02, 0.025), 0.3, 0.5), c, verts=8)
        t.rotation_mode = "QUATERNION"
        t.rotation_quaternion = (bv - av).to_track_quat("Z", "Y")
        bk.append(t)
    # (a solid basket box read as a floating crate from the street camera; dropped)
    # overhead wires
    for k, (z0, z1) in enumerate([(5.4, 5.1), (5.6, 5.3), (5.2, 4.9)]):
        cv = bpy.data.curves.new(f"wire_{k}", "CURVE")
        cv.dimensions = "3D"
        cv.bevel_depth = 0.008
        sp = cv.splines.new("BEZIER")
        sp.bezier_points.add(2)
        for i, p in enumerate([(-3, -2.6, z0), (1.0, -2.65, z0 - 0.5), (3.9, -2.6, z1)]):
            sp.bezier_points[i].co = p
            sp.bezier_points[i].handle_left_type = sp.bezier_points[i].handle_right_type = "AUTO"
        ob = bpy.data.objects.new(f"wire_{k}", cv)
        ob.data.materials.append(M["rubber"])
        c.objects.link(ob)
    # rain: thin streak quads in slabs that fall and loop (cyclic), motion blur turns them into streaks
    rain_m = bpy.data.materials.new("rain")
    nt = rain_m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.8, 0.85, 0.9, 1)
    b.inputs["Emission Color"].default_value = (0.6, 0.7, 0.9, 1)
    b.inputs["Emission Strength"].default_value = 0.6
    b.inputs["Alpha"].default_value = 0.35
    me = bpy.data.meshes.new("rain")
    bm = bmesh.new()
    r2 = random.Random(5)
    for i in range(1800):
        x, y, z = r2.uniform(-1.5, 5.7), r2.uniform(-4.2, -0.35), r2.uniform(0, 4.5)
        L = r2.uniform(0.12, 0.25)
        vs = [bm.verts.new((x - 0.0008, y, z)), bm.verts.new((x + 0.0008, y, z)), bm.verts.new((x + 0.0008, y, z + L)), bm.verts.new((x - 0.0008, y, z + L))]
        bm.faces.new(vs)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(rain_m)
    for k in range(2):
        ro = bpy.data.objects.new(f"rain_{k}", me)
        c.objects.link(ro)
        ro.visible_shadow = False
        ro.location = (0, 0, 4.5 * k)
        ro.keyframe_insert("location", index=2, frame=1)
        ro.location.z = 4.5 * k - 4.5
        ro.keyframe_insert("location", index=2, frame=13)
        act = ro.animation_data.action
        fcs = act.layers[0].strips[0].channelbag(act.slots[0]).fcurves
        for fc in fcs:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
            fc.modifiers.new("CYCLES")


# =================================================================== PASS B: small clutter
def scatter(name, n, area, maker, c, start, yaw_any=True):
    """Make n small parts with maker(i) and drop each onto whatever is under a random point in area=(x0,x1,y0,y1)."""
    objs = []
    for i in range(n):
        o = maker(i)
        x, y = rnd.uniform(area[0], area[1]), rnd.uniform(area[2], area[3])
        o.location = (x, y, -50)
        bpy.context.view_layer.update()
        o.rotation_euler.z = rnd.uniform(0, 6.28) if yaw_any else o.rotation_euler.z
        z, _ = ray_down(x, y, start)
        settle(o, z)
        objs.append(o)
    return objs


def pass_b():
    c = C_B
    S = BZ + 0.35
    mats_cap = [M["bin_blue"], M["dkplastic"], lib.principled("cap_tan", (0.55, 0.45, 0.3), 0.5)]

    def screw(i):
        o = local_cyl(f"screw_{i}", 0.0012, rnd.uniform(0.005, 0.012), M["chrome"], c, axis="X", verts=6)
        o.location.z = 0.0012
        return o

    def comp(i):
        k = rnd.random()
        if k < 0.4:
            o = local_cyl(f"cap_{i}", rnd.uniform(0.002, 0.005), rnd.uniform(0.006, 0.014), rnd.choice(mats_cap), c, verts=8)
            if rnd.random() < 0.6:
                o.rotation_euler.y = math.pi / 2
                o.location.z = 0.003
        elif k < 0.75:
            o = local_cyl(f"res_{i}", 0.0012, 0.006, mats_cap[2], c, axis="X", verts=6)
            o.location.z = 0.0012
        else:
            o = local_box(f"ic_{i}", 0.009, 0.006, 0.002, M["dkplastic"], c, 0)
        return o

    # screws + components on the bench mat, around the scope/helping hands, on the second station and on the counter
    for nm, area in [("bench_a", (0.35, 0.72, 2.05, 2.95)), ("bench_b", (0.45, 0.72, 3.9, 4.9)), ("counter", (2.4, 3.2, 1.65, 2.05))]:
        objs = scatter(nm, 40, area, screw, c, S if nm != "counter" else 1.4) + scatter(nm, 45, area, comp, c, S if nm != "counter" else 1.4)
        join(objs, f"smalls_{nm}", c)
    # loose PCBs
    for i, (x, y, z0) in enumerate([(0.58, 2.88, S), (0.5, 4.45, S), (1.55, 5.62, 1.5), (2.75, 1.98, 1.4), (0.18, 3.45, SHELF_Z[0] + 0.3)]):
        pcb = local_box(f"pcb_{i}", rnd.uniform(0.08, 0.16), rnd.uniform(0.06, 0.11), 0.0016, M["pcb"], c, 0)
        parts = [pcb]
        for k in range(rnd.randint(8, 18)):
            parts.append(local_cyl("pc", rnd.uniform(0.002, 0.005), rnd.uniform(0.004, 0.012), rnd.choice(mats_cap), c, rnd.uniform(-0.035, 0.035), rnd.uniform(-0.025, 0.025), 0.0016, verts=8))
        for k in range(rnd.randint(1, 4)):
            parts.append(local_box("pic", 0.014, 0.007, 0.003, M["dkplastic"], c, 0, z0=0.0016, ox=rnd.uniform(-0.03, 0.03), oy=rnd.uniform(-0.02, 0.02)))
        ob = join(parts, f"pcb_{i}", c)
        put(ob, x, y, z0, yaw=rnd.uniform(0, 360))
        if rnd.random() < 0.5:
            ob.rotation_euler.x = rnd.uniform(-0.05, 0.05)
    # desoldering braid, flux bottles, tweezers, screwdriver set, solder spool
    braid = join([local_cyl("braid_spool", 0.022, 0.012, lib.principled("spool_green", (0.1, 0.4, 0.15), 0.5), c, verts=20),
                  local_cyl("braid_copper", 0.012, 0.0125, M["copper"], c, verts=20)], "desolder_braid", c)
    put(braid, 0.45, 2.98, S)
    for i, (x, y) in enumerate([(0.52, 3.32), (0.67, 4.32)]):
        fb = join([local_cyl("flux", 0.018, 0.07, M["amber"], c, verts=16), local_cyl("flux_cap", 0.008, 0.02, M["white_pl"], c, z0=0.07, verts=12),
                   local_cyl("flux_needle", 0.0012, 0.03, M["chrome"], c, z0=0.09, verts=6)], f"flux_bottle_{i}", c)
        put(fb, x, y, S)
    for i, (x, y, yaw) in enumerate([(0.68, 2.62, 30), (0.7, 2.68, 38), (0.6, 4.6, -20)]):
        tw = join([local_box("tw_a", 0.12, 0.004, 0.0015, M["chrome"], c, 0, oy=0.002), local_box("tw_b", 0.12, 0.004, 0.0015, M["chrome"], c, 0, z0=0.0016, oy=-0.002)], f"tweezers_{i}", c)
        put(tw, x, y, S, yaw=yaw)
    sd = []
    for k in range(7):
        col = [(0.7, 0.05, 0.03), (0.05, 0.2, 0.6), (0.9, 0.7, 0.05), (0.02, 0.02, 0.02)][k % 4]
        sd.append(local_cyl(f"sd_h{k}", 0.008, 0.06, lib.principled(f"sd_handle_{k % 4}", col, 0.35), c, -0.07, k * 0.022 - 0.066, 0.008, axis="X", verts=10))
        sd.append(local_cyl(f"sd_s{k}", 0.0018, 0.07, M["chrome"], c, 0.0, k * 0.022 - 0.066, 0.008, axis="X", verts=6))
    case = local_box("sd_case", 0.2, 0.17, 0.006, M["dkplastic"], c, 0.002)
    sdo = join([case] + sd, "screwdriver_set", c)
    put(sdo, 0.6, 3.75, S, yaw=-12)
    spool = join([local_cyl("sp_a", 0.035, 0.008, M["dkplastic"], c, z0=0.0, verts=24), local_cyl("sp_wire", 0.026, 0.044, M["solder"], c, z0=0.008, verts=24),
                  local_cyl("sp_b", 0.035, 0.008, M["dkplastic"], c, z0=0.052, verts=24)], "solder_spool", c)
    put(spool, 0.2, 3.38, S)
    # cups, canned coffee, ashtrays, tape rolls
    for i, (x, y, z0) in enumerate([(0.68, 3.55, S), (2.8, 2.07, 1.4), (1.7, 5.45, 1.5), (0.2, 1.95, SHELF_Z[0] + 0.3)]):
        m = instance("repair_mug", f"mug_extra_{i}", c)
        if m:
            put(m, x, y, z0, yaw=rnd.uniform(0, 360))
    for i, (x, y, z0) in enumerate([(0.7, 2.0, S), (0.66, 4.98, S), (3.35, 2.08, 1.4), (1.3, 5.5, 0.6)]):
        cn = local_cyl(f"canned_coffee_{i}", 0.026, 0.11, M["coffee"], c, verts=16)
        put(cn, x, y, z0)
        if i == 3:
            cn.rotation_euler = (math.pi / 2, 0, rnd.uniform(0, 6))
            cn.location.z += 0.026
    for i, (x, y, z0) in enumerate([(0.68, 5.35, S), (3.05, 2.06, 1.4)]):
        tray = local_cyl("ashtray", 0.06, 0.025, lib.principled("ashtray_glass", (0.6, 0.65, 0.6), 0.05, **{"Transmission Weight": 0.9}), c, verts=24)
        parts = [tray, local_cyl("ash", 0.05, 0.004, M["ash"], c, z0=0.008, verts=16)]
        for k in range(rnd.randint(4, 8)):
            b = local_cyl("butt", 0.0038, rnd.uniform(0.018, 0.03), M["butt"], c, rnd.uniform(-0.03, 0.03), rnd.uniform(-0.03, 0.03), 0.014, axis="X", verts=6)
            b.rotation_euler.z = rnd.uniform(0, 6)
            parts.append(b)
        a = join(parts, f"ashtray_{i}", c)
        put(a, x, y, z0)
    for i, (x, y, z0, m) in enumerate([(0.12, 2.95, S, M["tape_black"]), (0.6, 3.15, S, M["tape_kapton"]), (2.48, 2.08, 1.4, M["tape_y"]), (0.18, 4.6, SHELF_Z[0] + 0.3, M["tape_black"])]):
        bpy.ops.mesh.primitive_torus_add(major_radius=0.026, minor_radius=0.009, location=(0, 0, 0.009))
        t = bpy.context.object
        t.name = f"tape_roll_{i}"
        t.data.materials.append(m)
        lib.link(t, c)
        put(t, x, y, z0)
    # receipts / repair slips: slightly curled paper planes in piles
    for i, (x, y, z0, n) in enumerate([(2.85, 1.72, 1.4, 6), (0.62, 1.42, S, 4), (0.55, 5.25, S, 3), (0.16, 2.3, SHELF_Z[0] + 0.3, 3)]):
        for k in range(n):
            p = plane(f"receipt_{i}_{k}", (0, 0, 0), rnd.uniform(0.07, 0.1), rnd.uniform(0.12, 0.2), "Z", M["tags"], c)
            cell = rnd.randrange(8)
            lib.set_uv_rect(p, (cell % 4) / 4, 0.5 * (1 - cell // 4), (cell % 4 + 1) / 4, 0.5 * (2 - cell // 4))
            put(p, x + rnd.uniform(-0.03, 0.03), y + rnd.uniform(-0.03, 0.03), z0, yaw=rnd.uniform(-40, 40), lift=0.0008 * (k + 1))
            p.rotation_euler.x = rnd.uniform(-0.04, 0.04)


# =================================================================== PASS C: cables, paper, life
def cable(name, pts, r, mat, c, drop_ids=(), sag=()):
    """Bezier cable through pts. Indices in drop_ids are dropped onto the surface below (+r); indices in sag are lowered
    by the given amount to hang between neighbours."""
    pts = [Vector(p) for p in pts]
    for i in drop_ids:
        z, _ = ray_down(pts[i].x, pts[i].y, pts[i].z + 0.05)
        pts[i].z = z + r
    for i, s in sag:
        pts[i].z -= s
    cv = bpy.data.curves.new(name, "CURVE")
    cv.dimensions = "3D"
    cv.bevel_depth = r
    cv.bevel_resolution = 2
    cv.resolution_u = 10
    sp = cv.splines.new("BEZIER")
    sp.bezier_points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        bp = sp.bezier_points[i]
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    ob = bpy.data.objects.new(name, cv)
    cv.materials.append(mat)
    c.objects.link(ob)
    return ob


def ribbon(name, pts, width, c):
    ob = cable(name, pts, 0.0004, lib.grimy("ribbon_grey", (0.55, 0.56, 0.58), (0.2, 0.2, 0.2), amount=0.2), c)
    ob.data.bevel_depth = 0.0
    ob.data.extrude = width / 2
    for bp in ob.data.splines[0].bezier_points:
        bp.tilt = math.pi / 2
    return ob


def ext_block(name, x, y, z0, yaw, c, n=6):
    parts = [local_box("eb", 0.05, 0.06 * n / 2 + 0.06, 0.035, M["white_pl"], c, 0.006)]
    for k in range(n):
        parts.append(local_box("sock", 0.022, 0.026, 0.002, M["dkplastic"], c, 0, z0=0.035, oy=-0.06 * n / 4 + k * 0.03 + 0.015))
        if rnd.random() < 0.65:
            parts.append(local_box("plug", 0.03, 0.022, 0.03, rnd.choice([M["dkplastic"], M["white_pl"]]), c, 0.004, z0=0.035, oy=-0.06 * n / 4 + k * 0.03 + 0.015))
    ob = join(parts, name, c)
    put(ob, x, y, z0, yaw=yaw)
    return ob


def bounds(name):
    o = sc.objects.get(name)
    if not o:
        return None
    pts = [o.matrix_world @ Vector(cn) for cn in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi, (lo + hi) / 2


def pass_c():
    c = C_C
    blk, wht, gry = M["rubber"], M["cable_w"], M["cable_g"]
    # extension blocks: on the bench back edge, under the bench, on the floor by the racks and the counter
    ext_block("ext_bench", 0.05, 3.85, BZ + 0.3, 0, c)
    ext_block("ext_under", 0.15, 2.6, 0.6, 5, c)
    ext_block("ext_floor_rack", 3.6, 3.0, 0.4, 85, c, 4)
    ext_block("ext_counter", 3.0, 2.3, 0.4, 20, c, 4)
    # power leads: every bench device -> back edge -> down the wall gap -> under-bench extension block
    devices = ["oscilloscope", "repair_bench_psu", "solder_station", "boombox_open", "repair_vcr_open", "solder_station_2", "repair_work_lamp", "ring_lamp", "dmm_station2"]
    for i, n in enumerate(devices):
        b = bounds(n)
        if not b:
            continue
        lo, hi, ce = b
        start = Vector((lo.x + 0.02, ce.y + rnd.uniform(-0.05, 0.05), lo.z + 0.03))
        mid_y = ce.y + rnd.uniform(-0.15, 0.15)
        pts = [start, (0.03, mid_y, BZ + 0.012), (0.012, mid_y + 0.05, BZ - 0.1), (0.015, 2.6 + rnd.uniform(-0.6, 0.6), 0.55), (0.12, 2.6 + (i - 4) * 0.03, 0.2)]
        cable(f"lead_{n}", pts, 0.0035, blk if i % 3 else gry, c, drop_ids=(1,), sag=((3, 0.0),))
    # soldering-iron cables across the mat (from the second station to a loose iron lying on the mat)
    iron = join([local_cyl("iron_grip", 0.01, 0.1, M["dkplastic"], c, axis="X"), local_cyl("iron_tip", 0.003, 0.06, M["chrome"], c, 0.08, 0, 0, axis="X")], "loose_iron", c)
    put(iron, 0.55, 4.55, BZ + 0.3, yaw=200, lift=0.01)
    s2 = bounds("solder_station_2")
    if s2:
        cable("iron_cable_2", [(s2[1].x - 0.02, s2[2].y - 0.06, s2[0].z + 0.04), (0.55, 4.85, BZ + 0.05), (0.7, 4.7, BZ + 0.05), (0.6, 4.6, BZ + 0.02)], 0.0028, M["rubber"], c, drop_ids=(1, 2))
    # test leads from the PSU and multimeters snaking across the bench
    for k, (pts, col) in enumerate([([(0.3, 1.55, 0.95), (0.5, 1.7, BZ), (0.62, 1.9, BZ), (0.55, 2.05, BZ)], (0.6, 0.03, 0.02)),
                                     ([(0.3, 1.62, 0.95), (0.48, 1.8, BZ), (0.66, 1.98, BZ), (0.68, 2.15, BZ)], (0.02, 0.02, 0.02)),
                                     ([(0.58, 5.0, BZ + 0.02), (0.7, 4.85, BZ), (0.66, 4.65, BZ)], (0.6, 0.03, 0.02))]):
        cable(f"test_lead_{k}", pts, 0.002, lib.principled(f"lead_col_{k % 2}", col, 0.4), c, drop_ids=tuple(range(1, len(pts))))
    # ribbon cables by the counter laptop and the PC side of the racks
    ribbon("ribbon_counter", [(2.5, 1.95, 1.0), (2.45, 2.02, 0.955), (2.38, 2.05, 0.955)], 0.03, c)
    ribbon("ribbon_bench", [(0.5, 4.4, BZ + 0.05), (0.62, 4.5, BZ + 0.004), (0.7, 4.42, BZ + 0.004)], 0.025, c)
    # rack devices: leads hanging off the shelf fronts
    for i, y in enumerate([1.6, 2.3, 3.1, 3.9, 4.5]):
        z = RACK_Z[i % 4] + 0.05
        cable(f"rack_hang_{i}", [(RX0 + 0.1, y, z), (RX0 - 0.01, y + 0.03, z + 0.01), (RX0 - 0.02, y + 0.06, z - 0.25 - i * 0.03), (RX0 + 0.02, y + 0.1, z + 0.01)],
              0.003, blk if i % 2 else wht, c)
    # floor runs: rack extension block -> wall outlet; counter block -> along the floor to the bench wall
    cable("floor_run_rack", [(3.6, 3.0, 0.05), (3.4, 2.6, 0.0), (3.6, 1.8, 0.0), (4.15, 1.2, 0.0), (4.18, 1.15, 0.35)], 0.004, gry, c, drop_ids=(1, 2, 3))
    cable("floor_run_counter", [(3.0, 2.3, 0.05), (2.4, 2.6, 0.0), (1.6, 2.8, 0.0), (0.9, 2.65, 0.0), (0.15, 2.6, 0.05)], 0.004, blk, c, drop_ids=(1, 2, 3))
    cable("lamp_cord_counter", [(3.4, 2.07, 0.97), (3.48, 2.12, 0.955), (3.52, 2.15, 0.7), (3.3, 2.25, 0.0), (3.0, 2.3, 0.04)], 0.0025, blk, c, drop_ids=(1, 3))
    # cable coil drooping from the pegboard + a hanging bundle on the back wall
    for i, y in enumerate([3.6, 4.2, 4.8]):
        cable(f"peg_loop_{i}", [(0.02, y, 1.45), (0.06, y + 0.05, 1.25 - i * 0.04), (0.04, y + 0.12, 1.15), (0.02, y + 0.16, 1.45)], 0.003, [blk, wht, gry][i], c)
    # paper life: sticky notes on drawer cabinets, shelf edges, monitors; flyers on the glass; extra posters; peeling tape
    notes = [((0.177, 1.5, 1.3), "X"), ((0.177, 2.1, 1.55), "X"), ((0.177, 2.75, 1.25), "X"), ((0.325, 3.4, 1.66), "X"), ((0.325, 4.4, 2.1), "X"),
             ((0.013, 3.4, 1.4), "X"), ((0.013, 4.9, 1.3), "X"), ((W - 0.013, 5.3, 1.35), "-X")]
    for i, (p, n) in enumerate(notes):
        s = plane(f"sticky_{i}", p, 0.065, 0.065, n, rnd.choice([M["sticky_y"], M["sticky_p"], M["sticky_b"]]), c)
        cell = rnd.randrange(36)
        lib.set_uv_rect(s, (cell % 6) / 6, 1 - (cell // 6 + 1) / 6, (cell % 6 + 1) / 6, 1 - (cell // 6) / 6)
        s.rotation_euler.x += rnd.uniform(-0.15, 0.15)
    for i, (x, z, m) in enumerate([(0.35, 1.55, M["flyer_w"]), (0.9, 1.2, M["flyer_y"]), (3.0, 1.9, M["flyer_w"]), (3.7, 1.05, M["flyer_y"])]):
        f = plane(f"flyer_glass_{i}", (x, 0.004 - 0.04 + 0.009, z), 0.21, 0.3, "Y", m, c)  # stuck on the inside of the glass
        cell = rnd.randrange(36)
        lib.set_uv_rect(f, (cell % 6) / 6, 1 - (cell // 6 + 1) / 6, (cell % 6 + 1) / 6, 1 - (cell // 6) / 6)
        f.rotation_euler.y = rnd.uniform(-0.06, 0.06)
        for k, (dx, dz) in enumerate([(-0.1, 0.14), (0.1, 0.14)]):
            t = plane(f"flyer_tape_{i}_{k}", (x + dx, f.location.y + 0.0006, z + dz), 0.05, 0.02, "Y", M["tape_y"], c)
            t.rotation_euler.y = rnd.uniform(-0.6, 0.6)
    pm = bpy.data.materials.get("poster_parts")
    for i, (p, n, w_, h_) in enumerate([((0.002, 6.05, 1.7), "X", 0.45, 0.6), ((0.5, D - 0.002, 1.6), "-Y", 0.42, 0.56)]):
        pp = plane(f"poster_extra_{i}", p, w_, h_, n, pm if i == 0 else M["flyer_y"], c)
        pp.rotation_euler[1 if n in ("-Y", "Y") else 0] += rnd.uniform(-0.03, 0.03)
        for k, (du, dv) in enumerate([(-1, 1), (1, 1), (1, -1)]):
            off = Vector((du * w_ / 2, 0, dv * h_ / 2)) if n in ("-Y", "Y") else Vector((0, du * w_ / 2, dv * h_ / 2))
            t = plane(f"poster_tape_{i}_{k}", Vector(p) + off + (Vector((0, -0.0008, 0)) if n == "-Y" else Vector((0.0008, 0, 0))), 0.06, 0.022, n, M["tape_y"], c)
            t.rotation_euler[1 if n in ("-Y", "Y") else 0] += du * dv * 0.7
            if k == 2:  # one corner peeling away from the wall
                t.rotation_euler[2] += 0.5
    # price tags hanging off rack devices
    for i, o in enumerate([o for o in sc.objects if o.get("placed") and o.location.x > 3.5][:10]):
        lo, hi, ce = bounds(o.name)
        t = tag_plane(f"price_tag_{i}", (lo.x - 0.002, ce.y + rnd.uniform(-0.05, 0.05), lo.z + (hi.z - lo.z) * 0.6), "-X", c, 0.045, 0.07, rnd.uniform(-0.3, 0.3))


# =================================================================== generated swaps (round-2 picks)
PROPS_DIR = os.path.join(lib.ROOT, "scenes", "tokyo-electronics-repair", "props")


def gen_instance(pid, name, c):
    """Instance of a prepped generated prop (appended once into _prop_sources), or None if it isn't prepped."""
    src = bpy.data.objects.get(f"src_{pid}")
    if src is None:
        path = os.path.join(PROPS_DIR, f"{pid}.blend")
        if not os.path.exists(path):
            return None
        with bpy.data.libraries.load(path, link=False) as (fr, to):
            to.objects = [pid]
        src = to.objects[0]
        src.name = f"src_{pid}"
        lc = bpy.data.collections.get("_prop_sources")
        lc.objects.link(src)
    ob = src.copy()
    ob.name = name
    c.objects.link(ob)
    ob.rotation_mode = "XYZ"
    ob.rotation_euler = (0, 0, 0)
    ob.scale = (1, 1, 1)
    ob["placed"] = True
    ob["prop_id"] = pid
    ob["wall"] = False
    ob["tv_on"] = 0.0
    return ob


def remove_tree(o):
    for ch in list(o.children):
        remove_tree(ch)
    bpy.data.objects.remove(o)


# direct object (by name) -> generated prop; extra = other direct objects that go with it (exact names or "prefix*")
SWAPS = {
    "A": [
        ("cash_register", "repair_cash_register", 180, ()),
        ("counter_lamp", "repair_counter_lamp", 180, ()),
        ("display_case", "repair_display_case", 0, ("display_case_glass",)),
        ("parts_cart", "repair_parts_cart", 12, ("cart_load_0", "cart_load_1", "cart_box")),
        ("pcb_vise", "repair_pcb_vise", 95, ()),
        ("cable_crate", "repair_cable_crate", 90, ()),
        ("floor_bin_0", "repair_job_bin", -90, ()),
        ("floor_bin_1", "repair_job_bin", -95, ()),
        ("umbrella_stand", "repair_umbrella_stand", 0, ()),  # stand moved with SWAP_POS
        ("spray_cans_generic_shelf", "repair_spray_cans_nb", 90, ()),
        ("spray_cans_generic_rack", "repair_spray_cans_nb", -90, ()),
        ("cup_noodle_generic", "repair_cup_noodle_nb", 30, ()),
        ("tissue_box_generic", "repair_tissue_box_nb", 95, ()),
        ("floor_box_2_0", "repair_storage_boxes_flat", 0, ("floor_box_2_*", "floor_box_3_*", "floor_box_4_*")),
        ("vending_machine", "repair_vending_machine", 180, ("vending_panel", "vm_bottle_*")),
        ("bike_wheel_0", "repair_bicycle", 0, ("bike_*",)),  # moved: parked along the facade, clear of the street camera
        ("aframe_1", "repair_aframe_sign", 0, ("aframe_*",)),
    ],
    "B": [
        ("screwdriver_set", "repair_screwdriver_case", -12, ()),
        ("ashtray_1", "repair_ashtray", 0, ()),
        ("canned_coffee_2", "repair_canned_coffee", 20, ()),
        ("canned_coffee_3", "repair_canned_coffee", 70, ()),
        ("tape_roll_2", "repair_tape_rolls", 0, ()),
        ("flux_bottle_1", "repair_flux_bottles", 0, ()),
        ("pcb_2", "repair_pcbs_loose", 15, ()),
        ("pcb_3", "repair_pcbs_loose", -30, ()),
    ],
}
# new generated props with no direct counterpart: (pass, id, name, x, y, ray start, yaw)
ADDS = [
    ("A", "repair_desk_phone", "tool_chest_phone", 0.92, 6.2, 1.6, 10),
    ("A", "repair_hot_air_station", "hot_air_station", 1.25, 6.15, 1.6, -15),
    ("A", "repair_shop_vac", "shop_vac", 3.48, 5.22, 1.2, -30),
    ("A", "repair_step_stool", "step_stool", 2.3, 5.62, 1.2, 25),
    ("A", "repair_fume_extractor", "fume_extractor", 0.42, 5.2, BZ + 0.4, 100),
    ("B", "repair_screw_jar", "screw_jar", 0.7, 3.98, BZ + 0.35, 0),
    ("B", "repair_component_bag", "component_bag", 0.66, 4.12, BZ + 0.35, 40),
    ("B", "repair_desolder_pump", "desolder_pump", 0.7, 4.52, BZ + 0.35, 70),
    ("B", "repair_remote_controls", "remote_controls", 2.55, 1.66, 1.4, 160),
    ("B", "repair_cable_bundle", "cable_bundle", 0.4, 1.55, 0.6, 30),
    ("B", "repair_receipts", "receipts_gen", 2.86, 1.72, 1.4, 10),
    ("B", "repair_sticky_notes", "sticky_pad", 0.6, 5.42, BZ + 0.35, -20),
]


SWAP_SCALE = {"display_case": 0.8, "floor_box_2_0": 0.75}
SWAP_POS = {"umbrella_stand": (2.55, 0.3), "floor_box_2_0": (3.05, 0.45), "bike_wheel_0": (3.15, -1.65)}


def match(name, pats):
    return any(name == p or (p.endswith("*") and name.startswith(p[:-1])) for p in pats)


def swap_pass(p):
    c = {"A": C_A, "B": C_B}[p]
    for direct, pid, yaw_off, extra in SWAPS[p]:
        o = sc.objects.get(direct)
        if o is None or not os.path.exists(os.path.join(PROPS_DIR, f"{pid}.blend")):
            continue
        x, y, yaw = o.location.x, o.location.y, math.degrees(o.rotation_euler.z)
        pts = [o.matrix_world @ Vector(cn) for cn in o.bound_box]
        top = max(pt.z for pt in pts)
        cx, cy = sum(pt.x for pt in pts) / 8, sum(pt.y for pt in pts) / 8
        cx, cy = SWAP_POS.get(direct, (cx, cy))
        name = o.name
        for nm in [e.name for e in sc.objects if e is not o and match(e.name, extra)]:
            e = sc.objects.get(nm)  # may already be gone with a removed parent
            if e:
                remove_tree(e)
        remove_tree(o)
        g = gen_instance(pid, name, c)
        g.scale = (SWAP_SCALE.get(direct, 1.0),) * 3
        if direct in ("vending_machine", "bike_wheel_0", "aframe_1"):
            del g["placed"]  # outside the room: not part of the interior validator checks
        put(g, cx, cy, top + 0.3, yaw=(yaw if direct not in ("bike_wheel_0", "aframe_1", "vending_machine") else 0) + yaw_off)
        print("SWAP", name, "->", pid)
    for q, pid, name, x, y, start, yaw in ADDS:
        if q != p:
            continue
        g = gen_instance(pid, name, c)
        if g:
            put(g, x, y, start, yaw=yaw)
            print("ADD", name, pid)


# =================================================================== clash resolver (after swaps)
from mathutils.bvhtree import BVHTree  # noqa: E402

FURN = ("shell", "bench", "drawers", "shelving", "storefront", "counter", "ceiling")


def world_tree(o):
    dg = bpy.context.evaluated_depsgraph_get()
    eo = o.evaluated_get(dg)
    me = eo.to_mesh()
    me.transform(o.matrix_world)
    t = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
    eo.to_mesh_clear()
    return t


def wbb(o):
    pts = [o.matrix_world @ Vector(cn) for cn in o.bound_box]
    return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))


def bb_hit(a, b):
    return not any(a[1][k] < b[0][k] or b[1][k] < a[0][k] for k in range(3))


def resolve_clashes():
    """Move the smaller prop of every interpenetrating pair (spiral search, re-dropped) until it is clear; drop it if nothing fits."""
    props = [o for o in sc.objects if o.get("placed") and o.type == "MESH" and o.visible_get()]
    furn = [o for o in sc.objects if o.type == "MESH" and o.visible_get() and any(c.name in FURN for c in o.users_collection)
            and not o.name.startswith(("floor", "backroom", "pavement", "street", "glass", "door_leaf", "decal"))]
    trees = {o.name: (world_tree(o), wbb(o)) for o in props + furn}
    vol = lambda o: (lambda b: (b[1] - b[0]).x * (b[1] - b[0]).y * (b[1] - b[0]).z)(trees[o.name][1])
    lift = Matrix.Translation((0, 0, 0.003))

    furn_names = {f.name for f in furn}

    def clashes(o):
        """Same rules as validate.py: props vs props unlifted (> 40 pairs), props vs furniture lifted 3 mm (> 20),
        plus the float rule (support under the centre within 1 cm)."""
        t0, b0 = trees[o.name]
        dg = bpy.context.evaluated_depsgraph_get()
        eo = o.evaluated_get(dg)
        me = eo.to_mesh()
        me.transform(lift @ o.matrix_world)
        tl = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
        eo.to_mesh_clear()
        out = []
        for n, (ot, ob) in trees.items():
            if n == o.name or not bb_hit(b0, ob):
                continue
            if n in furn_names:
                if len(tl.overlap(ot)) > 20:
                    out.append(n)
            elif len(t0.overlap(ot)) > 40:
                out.append(n)
        z, sup = ray_down(o.location.x, o.location.y, b0[0].z + 0.02, ignore=(o,))
        if b0[0].z - z > 0.01:
            out.append("FLOAT")
        return out

    moved = removed = 0
    for _ in range(3):
        changed = False
        for o in sorted(props, key=vol):
            if o.name not in trees:
                continue
            hit = [n for n in clashes(o) if n == "FLOAT" or n not in [p.name for p in props] or vol(sc.objects[n]) >= vol(o)]
            if not hit:
                continue
            x0, y0 = o.location.x, o.location.y
            top = trees[o.name][1][1].z + 0.25
            ok = False
            for r in (0.04, 0.08, 0.12, 0.18, 0.25, 0.33, 0.42):
                for k in range(12):
                    a = k / 12 * 6.283 + r * 7
                    x, y = x0 + r * math.cos(a), y0 + r * math.sin(a)
                    if not (0.02 < x < W - 0.02 and 0.05 < y < D - 0.02):
                        continue
                    put(o, x, y, top, yaw=math.degrees(o.rotation_euler.z))
                    trees[o.name] = (world_tree(o), wbb(o))
                    lo, hi = trees[o.name][1]
                    if lo.x < 0 or hi.x > W or lo.y < 0 or hi.y > D or lo.z < -0.01:
                        continue
                    if not clashes(o):
                        ok = True
                        break
                if ok:
                    break
            if ok:
                moved += 1
                print("RESOLVE moved", o.name, f"{math.hypot(o.location.x - x0, o.location.y - y0):.2f} m")
            else:
                print("RESOLVE removed", o.name, "clashing with", hit)
                del trees[o.name]
                remove_tree(o)
                removed += 1
            changed = True
            props = [p for p in sc.objects if p.get("placed") and p.type == "MESH" and p.visible_get()]
        if not changed:
            break
    print(f"RESOLVE {moved} moved, {removed} removed")


# ------------------------------------------------------------------- run
pass_a()
swap_pass("A")
if LEVEL >= 2:
    pass_b()
    swap_pass("B")
if LEVEL >= 3:
    pass_c()
resolve_clashes()
n_obj = sum(1 for o in sc.objects if o.type in ("MESH", "CURVE") and not o.hide_render)
print(f"dress2 pass {PASS}: {n_obj} renderable objects")
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("saved", OUT)
