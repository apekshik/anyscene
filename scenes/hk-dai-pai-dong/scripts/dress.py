"""Dress the street with prepped props (scenes/hk-dai-pai-dong/props/<id>.blend). World coordinates.

Passes big -> small: furniture (cart, range, tables, stools), heroes (woks, pots, teapot, car, lamp), mid props, clutter.
place(): each prop rests on whatever is under its footprint (raycast drop from start_z, which must be BELOW anything
overhead: the awning, hanging tools, shelves), or snaps its back to a wall, or hangs at a fixed bottom height.
Facing: 0 = front toward -Y (the walk-in end), 90 = toward +X (the street), -90 = toward -X, 180 = toward +Y.
Repeats share mesh data (linked duplicates) and get a per-instance ob.color tint.
"""
import json
import math
import os
import random

import bpy
from mathutils import Vector

import shell as S
from lib import SCENE_DIR, coll

LIB = os.path.join(SCENE_DIR, "props")
_loaded = {}
PLACED = []   # (obj, mode) for the validator
rng = random.Random(23)
PICKS = json.load(open(os.path.join(SCENE_DIR, "picks.json"), encoding="utf-8")) if os.path.exists(os.path.join(SCENE_DIR, "picks.json")) else {}
# Branded originals: only their _nb regeneration may be placed (filled from picks.json "debranded_by").
NB = {k: v["debranded_by"] for k, v in PICKS.items() if v.get("debranded_by")}


def _load(pid):
    if pid in _loaded:
        return _loaded[pid]
    path = os.path.join(LIB, pid + ".blend")
    if not os.path.exists(path):
        print("MISSING prop", pid)
        _loaded[pid] = None
        return None
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = list(src.objects)
    objs = [o for o in dst.objects if o]
    root = next(o for o in objs if o.name.split(".")[0] == pid)
    _loaded[pid] = (root, [o for o in objs if o is not root])
    return _loaded[pid]


def _instance(pid, c):
    got = _load(pid)
    if not got:
        return None
    root, kids = got
    # The loaded root stays an unlinked template; every placement is a linked duplicate (shares mesh + materials),
    # so removing a placement (unplace) never invalidates the cache.
    o = root.copy()
    c.objects.link(o)
    for k in kids:
        kk = k.copy()
        c.objects.link(kk)
        kk.parent = o
    return o


def bounds(o):
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(cc) for cc in o.bound_box]
    for ch in o.children:
        pts += [ch.matrix_world @ Vector(cc) for cc in ch.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def _ray_down(dg, p, skip=()):
    """Downward scene ray that passes through hanging things (no_support) and the given objects."""
    for _ in range(64):
        ok, loc, _n, _idx, hit, _m = bpy.context.scene.ray_cast(dg, p, Vector((0, 0, -1)))
        if not ok:
            return None, None
        if hit.get("no_support") or hit in skip:
            p = loc - Vector((0, 0, 1e-5))   # a 1 mm step skipped supports closer than that
            continue
        return loc.z, hit
    return None, None


def contacts(o, n=40, every=False):
    """World-space contact candidates: the lowest vertices (feet, legs, base rings), at most n of them
    (every=True: a spread of all vertices)."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    vs = []
    for ob in [o, *o.children_recursive]:
        if ob.type != "MESH":
            continue
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        vs += [ob.matrix_world @ v.co for v in me.vertices]
        ev.to_mesh_clear()
    if every:
        return vs[:: max(1, len(vs) // n)]
    zmin = min(v.z for v in vs)
    band = max(0.015, 0.03 * (max(v.z for v in vs) - zmin))
    feet = [v for v in vs if v.z <= zmin + band]
    return feet[:: max(1, len(feet) // n)]


def contact_gap(o, pts=None):
    """Smallest drop from the contact points to whatever is below them: > 0 means the prop floats
    (a footprint drop rests the bbox on the highest thing under it, which may not be under any foot)."""
    dg = bpy.context.evaluated_depsgraph_get()
    own = {o, *o.children_recursive}
    gaps = []
    for f in pts or contacts(o):
        z, hit = _ray_down(dg, f + Vector((0, 0, 0.002)), own)
        if z is not None:
            gaps.append((f.z - z, hit.name))
    return min(gaps) if gaps else (None, None)


def _drop(o, start_z):
    """Lower the object onto the highest surface under its footprint (5x5 grid of downward rays from start_z), then
    settle it until its actual contact points touch something."""
    lo, hi = bounds(o)
    dg = bpy.context.evaluated_depsgraph_get()
    own = {o, *o.children_recursive}
    top = None
    for i in range(5):
        for j in range(5):
            x = lo.x + (hi.x - lo.x) * (0.1 + 0.8 * i / 4)
            y = lo.y + (hi.y - lo.y) * (0.1 + 0.8 * j / 4)
            z, _hit = _ray_down(dg, Vector((x, y, start_z)), own)
            if z is not None and (top is None or z > top):
                top = z
    if top is not None:
        o.location.z += top - lo.z + 0.0005
    settle(o)


def settle(o):
    """Move down by the smallest clearance (never up) of the feet and a spread of all vertices, so the first point to
    touch stops it: by the feet alone, a plate over a table's raised rim sank into the rim."""
    g, _on = contact_gap(o, contacts(o) + contacts(o, 400, every=True))
    if g is not None and g > 0.002:
        o.location.z -= g - 0.0005
        bpy.context.view_layer.update()


def _newspaper(c):
    """Folded racing paper: a thin slab with the reference photo's printed page on top (both generators turned the
    printed horses into 3D figurines)."""
    from lib import m_image
    ref = os.path.join(SCENE_DIR, "..", "..", "refs", "hk-dai-pai-dong", "props", "hk_newspaper_0.png")
    w, d, t = 0.31, 0.4, 0.008
    verts = [(-w / 2, -d / 2, 0), (w / 2, -d / 2, 0), (w / 2, d / 2, 0), (-w / 2, d / 2, 0),
             (-w / 2, -d / 2, t), (w / 2, -d / 2, t), (w / 2, d / 2, t), (-w / 2, d / 2, t)]
    faces = [(4, 5, 6, 7), (0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    me = bpy.data.meshes.new("newspaper_direct")
    me.from_pydata(verts, [], faces)
    uv = me.uv_layers.new(name="UVMap")
    # top face gets the page (crop of the ref photo), the edges a sliver of paper
    crop = [(0.08, 0.1), (0.9, 0.1), (0.9, 0.94), (0.08, 0.94)]
    for li, poly in enumerate(me.polygons):
        for k, l in enumerate(poly.loop_indices):
            uv.data[l].uv = crop[k] if li == 0 else (0.5, 0.05)
    me.materials.append(m_image("newspaper_page", os.path.abspath(ref), rough=0.8))
    o = bpy.data.objects.new("hk_newspaper", me)
    c.objects.link(o)
    return o


DIRECT = {"hk_newspaper": _newspaper}

TINTS = [(1, 1, 1), (0.93, 0.9, 0.86), (1.0, 0.96, 0.9), (0.86, 0.86, 0.88), (0.97, 0.93, 0.92)]


def place(pid, x, y, z=None, facing=0.0, jitter=0.0, against=None, gap=0.01, mode="rest", scale=1.0, start_z=1.5,
          c=None, tint=None, name=None):
    """mode: rest (drop onto support), hang (z = bottom height). against: 'x-','x+','y-','y+': push the prop's
    back to that plane (x or y is the wall coordinate)."""
    pid = NB.get(pid, pid)
    c = c or coll("props")
    if PICKS and pid in PICKS and PICKS[pid].get("model") in (None, "retired"):
        if pid not in DIRECT:
            return None
        o = DIRECT[pid](c)   # retired generated prop replaced by a direct-modelled one
    else:
        o = _instance(pid, c)
    if o is None:
        return None
    if name:
        o.name = name
    o.rotation_mode = "XYZ"  # glTF-imported props come in quaternion mode
    o.rotation_euler = (0, 0, math.radians(facing + rng.uniform(-jitter, jitter)))
    o.scale = (scale, scale, scale)
    o.location = (x, y, 0 if z is None else z)
    if against:
        lo, hi = bounds(o)
        if against == "x-":
            o.location.x += (x + gap) - lo.x
        elif against == "x+":
            o.location.x += (x - gap) - hi.x
        elif against == "y+":
            o.location.y += (y - gap) - hi.y
        elif against == "y-":
            o.location.y += (y + gap) - lo.y
    if mode == "rest":
        _drop(o, start_z)
    else:
        o["no_support"] = True   # hanging things (bag, cage, tool rail) are never something to rest on
    o.color = (*(tint or rng.choice(TINTS)), 1)
    o["placed"] = True
    o["prop_id"] = pid
    o["mode"] = mode
    o["start_z"] = start_z
    PLACED.append((o, mode))
    return o


def unplace(o):
    PLACED[:] = [(q, m) for q, m in PLACED if q is not o]
    for ch in list(o.children):
        bpy.data.objects.remove(ch)
    bpy.data.objects.remove(o)


def top_of(o):
    return bounds(o)[1].z


# ---------------------------------------------------------------- layout data (also used by lights/fx/shots)

TABLES = [  # id, x, y, kind
    ("t1", -0.95, 0.25, "hk_table_round"),
    ("t2", -0.95, 5.05, "hk_table_square"),
    ("t3", 1.65, -0.35, "hk_table_round"),
    ("t4", 1.75, 4.55, "hk_table_round"),
    ("t5", 3.95, 2.45, "hk_table_round"),
]
LANE = ((-2.2, 1.35), (0.6, 3.75))  # (x0, y0), (x1, y1): kept clear for the walk-in (no stools)
WOKS = []  # (x, y, z) of the burner wells, filled by furniture()


def burner_wells(o):
    """The two wok wells of the picked range: at 25% / 75% of its width, 45% of its depth from the back (read off a
    top-down ortho render; a lowest-point search found the front gutter instead). Rim height = highest raycast hit in a 16 cm
    ring around each well centre. Returns [(x, y, z_rim)]."""
    lo, hi = bounds(o)
    dg = bpy.context.evaluated_depsgraph_get()
    wells = []
    for fy in (0.247, 0.753):
        cx, cy = lo.x + (hi.x - lo.x) * 0.45, lo.y + (hi.y - lo.y) * fy
        zs = []
        for k in range(16):
            a = k * math.pi / 8
            ok, loc, _n, _i, hit, _m = bpy.context.scene.ray_cast(dg, Vector((cx + 0.17 * math.cos(a), cy + 0.17 * math.sin(a), hi.z + 0.3)), Vector((0, 0, -1)))
            if ok and hit is o:
                zs.append(loc.z)
        zs.sort()
        wells.append((cx, cy, zs[len(zs) // 2] if zs else hi.z - 0.1))
    return wells


def seat_wok(o, well):
    """A round-bottomed wok rests in the well ring: its bowl bottom (mean of the lowest vertices, not the bbox centre,
    which a long handle drags ~20 cm sideways) goes over the well, 6 cm below the rim (validator: accepted clip)."""
    bpy.context.view_layer.update()
    mw = o.matrix_world
    vs = [mw @ v.co for v in o.data.vertices]
    zmin = min(v.z for v in vs)
    low = [v for v in vs if v.z < zmin + 0.025]
    bx = sum(v.x for v in low) / len(low)
    by = sum(v.y for v in low) / len(low)
    o.location.x += well[0] - bx
    o.location.y += well[1] - by
    o.location.z += (well[2] - 0.06) - zmin


def _in_lane(x, y):
    (x0, y0), (x1, y1) = LANE
    return x0 < x < x1 and y0 < y < y1


def furniture():
    k = coll("props_furniture")
    cart = place("hk_kitchen_cart", -3.55, 1.2, facing=90, against="x-", gap=0.02, c=k, tint=(1, 1, 1), name="kitchen_cart")
    rng_ = place("hk_wok_range", -3.55, 3.18, facing=90, against="x-", gap=0.02, c=k, tint=(1, 1, 1), name="wok_range")
    if rng_:
        WOKS.extend(burner_wells(rng_))
        print("burner wells", [tuple(round(v, 3) for v in w) for w in WOKS], flush=True)
    for tid, x, y, kind in TABLES:
        t = place(kind, x, y, facing=rng.uniform(0, 90), c=k, start_z=2.0, name=f"table_{tid}")
        if not t:
            continue
        r = 0.66 if kind == "hk_table_round" else 0.6
        n = 0
        for a in (20, 110, 200, 290) if kind == "hk_table_round" else (0, 90, 180, 270):
            a = math.radians(a + rng.uniform(-25, 25))
            sx, sy = x + r * math.cos(a), y + r * math.sin(a)
            if _in_lane(sx, sy):
                continue
            pid = "hk_stool_blue" if rng.random() < 0.12 else "hk_stool_red"
            # drop from below the table top, measured from the table's own base: road tables stand 15 cm lower,
            # and a fixed 0.6 m start put their stools on the table top
            place(pid, sx, sy, facing=rng.uniform(0, 360), c=k, start_z=bounds(t)[0].z + 0.5, name=f"stool_{tid}_{n}")
            n += 1
    # Spare stools: a stack by the walk-in pole and two loose ones in the road.
    place("hk_stool_stack", -0.85, -1.35, facing=20, c=k, start_z=2.0)
    place("hk_stool_stack", -2.05, 6.55, facing=-30, c=k, start_z=2.0)
    place("hk_stool_red", 3.4, 7.2, facing=40, c=k, start_z=2.0)


def kitchen():
    k = coll("props_kitchen")
    cart = bpy.data.objects.get("kitchen_cart")
    ct = top_of(cart) if cart else 1.0
    woks = WOKS or [(-3.05, 2.8, 0.85), (-3.05, 3.55, 0.85)]
    for pid, w, f, nm in (("hk_wok_rice", woks[0], 100, "wok_rice"), ("hk_wok_a", woks[1], 70, "wok_back")):
        o = place(pid, w[0], w[1], z=w[2], facing=f, mode="hang", c=k, name=nm)
        if o:
            seat_wok(o, w)
            o["mode"] = "seated"
    place("hk_stockpot", -3.2, 0.55, facing=90, c=k, start_z=1.6, name="stockpot")
    place("hk_stockpot_small", -3.25, 1.1, facing=60, c=k, start_z=1.6)
    place("hk_cleaver_block", -2.98, 1.55, facing=90, c=k, start_z=1.6)
    place("hk_aromatics_bowls", -2.95, 2.0, facing=95, c=k, start_z=1.6)
    place("hk_wok_tools", -2.85, 0.9, facing=90, c=k, start_z=1.6)
    place("hk_prawn_tray", -2.95, 4.4, facing=90, c=k, start_z=1.6)
    place("hk_veg_basket", -3.2, 4.85, facing=80, c=k, start_z=1.6)
    place("hk_steamer_stack", -3.25, 5.45, facing=90, c=k, start_z=1.6)
    place("hk_spider_strainer", -2.95, 5.35, facing=10, c=k, start_z=1.6)
    # Under the prep table.
    place("hk_rice_sack", -3.15, 5.25, facing=90, c=k, start_z=0.8)
    place("hk_tub_blue", -3.1, 4.5, facing=90, c=k, start_z=0.8)
    # Back shelves (x -3.98..-3.58, sections y -0.3..1.6 / 1.7..3.6 / 3.7..5.8, tiers z 1.25 / 1.7 / 2.15).
    # Packed along y by each prop's real footprint, back to the wall; tall things (>0.4 m) only on the top tier.
    SECTIONS = [(-0.27, 1.57), (1.73, 3.57), (3.73, 5.77)]
    TIERS = (1.25, 1.7, 2.15)
    rows = {
        (0, 0): ["hk_bowl_stack", "hk_plate_stack", "hk_claypot"],
        (1, 0): ["hk_sauce_shelf", "hk_jars_preserved"],
        (2, 0): ["hk_rice_cooker", "hk_plate_stack"],
        (0, 1): ["hk_thermos", "hk_oil_tin", "hk_takeaway_boxes"],
        (1, 1): ["hk_claypot", "hk_steamer_stack", "hk_stockpot_small"],
        (2, 1): ["hk_bowl_stack", "hk_radio"],
        (0, 2): ["hk_tea_urn", "hk_styrofoam_box"],
        (1, 2): ["hk_menu_board_b", "hk_cardboard_boxes"],
        (2, 2): ["hk_fan", "hk_dish_rack"],
    }
    for (sec, tier), pids in rows.items():
        y = SECTIONS[sec][0] + 0.02
        start = (TIERS[tier + 1] - 0.03) if tier < 2 else 2.95
        for pid in pids:
            o = place(pid, S.FX0 + 0.02, y + 0.3, z=TIERS[tier] + 0.3, facing=90 + rng.uniform(-6, 6), against="x-", c=k,
                      mode="hang", start_z=start, name="menu_board_shelf" if pid == "hk_menu_board_b" else None)
            if not o:
                continue
            lo, hi = bounds(o)
            o.location.y += y - lo.y   # pack first, then drop onto the tier
            _drop(o, start)
            o["mode"] = "rest"
            o["no_support"] = False
            PLACED[:] = [(q, "rest" if q is o else m) for q, m in PLACED]
            lo, hi = bounds(o)
            if hi.y > SECTIONS[sec][1] - 0.01:  # doesn't fit: drop it rather than clip a post
                print("SHELF no room for", pid, flush=True)
                unplace(o)
                continue
            y = hi.y + rng.uniform(0.02, 0.06)
    # Hanging: tool rail over the cart, enamel shade over the woks, fluorescent batten on the wall.
    place("hk_hanging_utensils", -2.8, 1.25, z=1.72, facing=90, mode="hang", c=k, name="hanging_utensils")
    place("hk_enamel_shade", woks[0][0] + 0.15, (woks[0][1] + woks[1][1]) / 2, z=2.12, facing=90, mode="hang", c=k, name="wok_shade")
    place("hk_fluoro_fitting", S.FX0 + 0.08, 2.6, z=2.8, facing=90, mode="hang", against="x-", c=k, name="fluoro")
    # Both menu boards came back with easel stands: board B stands on the top shelf, A-frame A on the pavement at the
    # walk-in end with its (mirrored-text) back to the stall.
    place("hk_menu_board_a", -2.25, -1.2, facing=0, c=k, start_z=1.2, name="menu_board_aframe")
    # Gas: two cylinders at the walk-in end of the cart, hose to the range.
    place("hk_lpg_cylinder", -3.25, -0.2, facing=60, c=k, start_z=1.2, name="lpg_a")
    place("hk_lpg_cylinder", -2.8, -0.55, facing=130, c=k, start_z=1.2, name="lpg_b")
    # Floor clutter in and behind the stall.
    place("hk_wash_basin", -2.05, 4.7, facing=0, c=k, start_z=2.0)
    place("hk_water_bucket", -2.0, 5.35, facing=0, c=k, start_z=2.0)
    place("hk_crate_stack", -3.3, 6.45, facing=90, c=k, start_z=2.0)
    place("hk_beer_crate", -2.6, 6.55, facing=20, c=k, start_z=2.0)
    place("hk_styrofoam_box", -2.5, 6.0, facing=70, c=k, start_z=2.0)
    place("hk_veg_basket", -2.05, 6.05, facing=10, c=k, start_z=2.0)
    place("hk_fire_extinguisher", S.FX0, 6.2, facing=90, against="x-", c=k, start_z=2.0)
    place("hk_mop_bucket", -3.65, 7.1, facing=40, c=k, start_z=2.0)
    place("hk_bird_cage", -1.2, -0.75, z=1.95, facing=0, mode="hang", c=k, name="bird_cage")
    place("hk_plastic_bag_hang", -2.3, 5.85, z=1.65, facing=90, mode="hang", c=k)
    place("hk_umbrella", S.POLE_X - 0.15, 3.05, facing=30, c=k, start_z=1.2)


def tables():
    k = coll("props_table")
    T = {tid: (x, y) for tid, x, y, _ in TABLES}
    sets = {
        # newspapers first: whatever lands on them later rests on the paper
        "t1": [("hk_newspaper", -0.2, -0.16, 70), ("hk_enamel_teapot", -0.16, 0.19, 200), ("hk_tea_cups", 0.21, 0.02, 0),
               ("hk_condiment_caddy", 0.0, -0.27, 30), ("hk_chopstick_cup", 0.26, -0.24, 0)],  # fried rice: 54 cm platter, no room
        "t2": [("hk_radio", -0.12, -0.1, -20), ("hk_thermos", 0.22, 0.22, 0), ("hk_milk_tea", 0.2, -0.2, 0),
               ("hk_ashtray", -0.22, 0.2, 0)],
        "t3": [("hk_dish_clams", -0.12, 0.08, 0), ("hk_dish_beef_hofun", 0.18, -0.12, 120), ("hk_beer_bottles", 0.05, 0.3, 40),
               ("hk_soy_bottles", -0.25, -0.18, 0), ("hk_chopstick_cup", 0.28, 0.12, 0), ("hk_lemon_tea", -0.3, 0.2, 0)],
        "t4": [("hk_dish_greens", 0.1, 0.12, 0), ("hk_dish_salt_squid", -0.18, -0.08, 60), ("hk_bowl_congee", 0.22, -0.2, 0),
               ("hk_enamel_teapot", -0.25, 0.22, 140), ("hk_toilet_roll", 0.3, 0.25, 0), ("hk_condiment_caddy", -0.05, -0.32, 0)],
        "t5": [("hk_beer_bottles", 0.0, 0.0, 0), ("hk_ashtray", 0.25, 0.1, 0), ("hk_tea_cups", -0.2, -0.15, 0)],
    }
    for tid, items in sets.items():
        x, y = T[tid]
        for pid, dx, dy, f in items:
            nm = {("t1", "hk_enamel_teapot"): "teapot_t1", ("t1", "hk_condiment_caddy"): "caddy_t1",
                  ("t3", "hk_dish_clams"): "clams_t3", ("t4", "hk_enamel_teapot"): "teapot_t4"}.get((tid, pid))
            place(pid, x + dx, y + dy, facing=f, jitter=12, c=k, start_z=1.6, name=nm)


def street():
    k = coll("props_street")
    # The lamp mesh is centred on its bbox, so the pole is at one end: find the pole base (mean of the lowest
    # vertices), pick the facing that puts the arm toward -X (over the road), then move the base onto the far kerb.
    for f in (90, -90, 180, 0):
        lamp = place("hk_street_lamp", S.KERB1 + 0.45, 1.8, facing=f, c=k, start_z=2.0, name="street_lamp")
        bpy.context.view_layer.update()
        mw = lamp.matrix_world
        vs = [mw @ v.co for v in lamp.data.vertices]
        zmin = min(v.z for v in vs)
        base = [v for v in vs if v.z < zmin + 0.05]
        bx = sum(v.x for v in base) / len(base)
        by = sum(v.y for v in base) / len(base)
        lo, hi = bounds(lamp)
        if bx > (lo.x + hi.x) / 2 + 0.5:   # base on the +X end: arm reaches toward -X
            lamp.location.x += (S.KERB1 + 0.45) - bx
            lamp.location.y += 1.8 - by
            print("street lamp facing", f, "arm reach", round(bx - lo.x, 2), flush=True)
            break
        unplace(lamp)
    for y in (-7.4, -5.35):
        place("hk_guard_railing", -0.32, y, facing=90, c=k, start_z=2.0)
    for y in (-3.0, 12.5, 14.55):
        place("hk_guard_railing", S.KERB1 + 0.32, y, facing=-90, c=k, start_z=2.0)
    place("hk_water_barrier", 5.05, -0.6, facing=90, c=k, start_z=2.0, name="barrier_a")
    place("hk_water_barrier", 5.05, 0.75, facing=90, jitter=4, c=k, start_z=2.0, name="barrier_b")
    place("hk_water_barrier", 5.1, 4.6, facing=90, jitter=4, c=k, start_z=2.0, name="barrier_c")
    place("hk_traffic_cone", 5.0, 2.6, facing=0, c=k, start_z=2.0)
    place("hk_traffic_cone", 4.9, 6.4, facing=30, c=k, start_z=2.0)
    place("hk_parked_car", 6.35, 9.5, facing=180, c=k, start_z=3.0, name="parked_car")
    place("hk_scooter", 0.75, -3.4, facing=200, c=k, start_z=3.0, name="scooter")
    place("hk_hand_trolley", -3.55, -1.6, facing=80, c=k, start_z=2.0)
    place("hk_shrine", S.FX0, -2.15, facing=90, against="x-", c=k, start_z=2.0, name="shrine")
    place("hk_trash_bin", -3.55, 7.7, facing=90, c=k, start_z=2.0)
    place("hk_bin_bags", -2.85, 7.85, facing=10, c=k, start_z=2.0)
    place("hk_bin_bags", S.KERB1 + 0.7, -1.5, facing=200, c=k, start_z=2.0)
    place("hk_cardboard_boxes", S.KERB1 + 0.8, 5.0, facing=-90, c=k, start_z=2.0)
    place("hk_electric_box", S.FX0, -3.9, z=1.3, facing=90, mode="hang", against="x-", c=k)
    place("hk_electric_box", S.FX1, 7.4, z=1.5, facing=-90, mode="hang", against="x+", c=k)
    # Window air-conditioners up the facades (hang, back to the facade plane).
    n = 0
    for side, xf, f, ag in ((-1, S.FX0 + 0.16, 90, "x-"), (1, S.FX1 - 0.16, -90, "x+")):
        for y in range(-14, 30, 3):
            for zf in (5.2, 8.1, 11.0, 13.9):
                if rng.random() < 0.45:
                    continue
                o = place("hk_aircon_unit", xf, y + rng.uniform(-0.8, 0.8), z=zf + rng.uniform(-0.3, 0.3), facing=f, mode="hang",
                          against=ag, c=k, tint=rng.choice(TINTS))
                if o and hits_fixed(o):
                    unplace(o)
                    continue
                n += 1
    print("aircon units", n)


FIXED = ("shell", "stall", "signs", "street_detail")


def hits_fixed(o, pad=0.01):
    """Bounding-box overlap with fixed geometry other than the building mass/face it is mounted on."""
    lo, hi = bounds(o)
    for c in FIXED:
        cc = bpy.data.collections.get(c)
        for f in (cc.all_objects if cc else []):
            if f.type not in ("MESH", "FONT", "CURVE") or f.name.endswith(("_mass", "_face")) or f.name.startswith(("cable_", "pavement", "road", "kerb")):
                continue
            pts = [f.matrix_world @ Vector(v) for v in f.bound_box]
            flo = Vector([min(q[i] for q in pts) for i in range(3)])
            fhi = Vector([max(q[i] for q in pts) for i in range(3)])
            if all(lo[i] + pad < fhi[i] and flo[i] < hi[i] - pad for i in range(3)):
                return True
    return False


def run():
    furniture()
    kitchen()
    tables()
    street()
    bpy.context.view_layer.update()
    print("DRESS placed", len(PLACED), flush=True)
