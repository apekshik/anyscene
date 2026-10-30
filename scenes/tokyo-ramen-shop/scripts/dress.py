"""Dress the ramen shop with prepped props (scenes/tokyo-ramen-shop/lib/<id>.blend). Design coordinates (pre-mirror).

place(): big props first, small last. Each prop rests on whatever is under its footprint (raycast drop),
or snaps its back against a wall, or hangs at a fixed height. Repeats share mesh data (linked duplicates).
Facing: 0 = front toward the street (-Y), 90 = toward +X, -90 = toward -X, 180 = toward the back.
"""
import math
import os
import random

import bpy
from mathutils import Vector

import shell as S
from lib import SCENE_DIR

LIB = os.path.join(SCENE_DIR, "lib")
_loaded = {}
PLACED = []   # (obj, mode) for the validator
BRANDED = {"ramen_shelf_jars", "ramen_spice_tins", "ramen_cardboard_boxes", "ramen_flour_sacks", "ramen_beer_bottle_glass",
           "ramen_lighter_cigs", "ramen_vending_machine", "ramen_radio", "ramen_tape_roll", "ramen_hook_items", "ramen_coat_hooks"}
MIRROR = False  # set by patch scripts that dress the saved (already mirrored) .blend
rng = random.Random(7)


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
    if root.users_collection:
        o = root.copy()  # linked duplicate: shares mesh + materials
        c.objects.link(o)
        for k in kids:
            kk = k.copy()
            c.objects.link(kk)
            kk.parent = o
    else:
        o = root
        c.objects.link(o)
        for k in kids:
            c.objects.link(k)
    return o


def _footprint_world(o):
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(cc) for cc in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def _drop(o, start_z=3.0):
    """Lower the object onto the highest surface under its footprint (5x5 grid of downward rays)."""
    lo, hi = _footprint_world(o)
    dg = bpy.context.evaluated_depsgraph_get()
    hide = o.hide_get()
    o.hide_set(True)
    for ch in o.children:
        ch.hide_set(True)
    dg.update()
    top = None
    for i in range(5):
        for j in range(5):
            x = lo.x + (hi.x - lo.x) * (0.1 + 0.8 * i / 4)
            y = lo.y + (hi.y - lo.y) * (0.1 + 0.8 * j / 4)
            ok, loc, _n, _idx, hit, _m = bpy.context.scene.ray_cast(dg, Vector((x, y, start_z)), Vector((0, 0, -1)))
            if ok and hit is not o and (top is None or loc.z > top):
                top = loc.z
    o.hide_set(hide)
    for ch in o.children:
        ch.hide_set(False)
    if top is not None:
        o.location.z += top - lo.z + 0.0005


def place(pid, c, x, y, z=None, facing=0.0, jitter=0.0, against=None, gap=0.01, mode="rest", scale=1.0, start_z=None):
    """mode: rest (drop onto support), hang (fixed z = bottom height). against: 'x-','x+','y-','y+' wall plane
    value is taken from x or y (the wall coordinate); the prop's back is pushed to it."""
    if pid in BRANDED:
        # Generated with real brands on the labels: only the de-branded regeneration may be placed.
        pid = pid + "_nb" if _have(pid + "_nb") else None
        if pid is None:
            return None
    if MIRROR:
        # Patching an already-mirrored scene: same design coordinates, converted the way build.mirror_x would.
        x = S.W - x
        facing = -facing
        against = {"x-": "x+", "x+": "x-"}.get(against, against)
    o = _instance(pid, c)
    if o is None:
        return None
    o.rotation_mode = "XYZ"  # glTF-imported props come in quaternion mode
    o.rotation_euler = (0, 0, math.radians(facing + rng.uniform(-jitter, jitter)))
    o.scale = (scale, scale, scale)
    o.location = (x, y, 0 if z is None else z)
    if against:
        lo, hi = _footprint_world(o)
        if against == "x-":
            o.location.x += (x + gap) - lo.x
        elif against == "x+":
            o.location.x += (x - gap) - hi.x
        elif against == "y+":
            o.location.y += (y - gap) - hi.y
        elif against == "y-":
            o.location.y += (y + gap) - lo.y
    if mode == "rest":
        _drop(o, start_z if start_z is not None else 1.3)  # below the hood and wall shelves
    PLACED.append((o, mode))
    return o


def build(c):
    PLACED.clear()
    KX_TOP = 0.88
    # ---- big props
    t = place("ticket_machine", c, 0.0, 0.0, facing=180, against="x-")
    t.location.y += 0.03 - _footprint_world(t)[0].y  # back against the front wall, face toward the shop
    place("ramen_drink_fridge", c, 0.0, S.D, facing=90, against="x-")
    PLACED[-1][0].location.y += (S.D - 0.03) - _footprint_world(PLACED[-1][0])[1].y  # back-left corner, behind the wide camera
    place("ramen_noodle_boiler", c, S.W, 3.78, facing=-90, against="x+")
    place("ramen_gas_range", c, S.W, 4.82, facing=-90, against="x+")
    for i, y in enumerate(S.STOOL_Y):
        place("ramen_stool", c, 0.93, y, facing=rng.uniform(0, 360))
    # ---- kitchen: pots on the range, shelves, counters, floor
    place("stockpot", c, S.W - 0.36, 4.6, facing=rng.uniform(0, 360))
    place("stockpot", c, S.W - 0.36, 5.05, facing=rng.uniform(0, 360), scale=0.88)
    place("stockpot", c, S.W - 0.32, 5.75, facing=rng.uniform(0, 360), scale=0.8)
    place("ramen_ladle_rail", c, S.W, 4.75, z=1.42, facing=-90, against="x+", mode="hang")
    place("ramen_dish_rack", c, S.W, 2.55, facing=-90, against="x+")
    place("ramen_rice_cooker", c, S.W, 6.45, facing=-90, against="x+")
    place("ramen_kettle_pot", c, S.W, 1.35, facing=-80, against="x+")
    place("ramen_cash_register", c, S.W, 1.95, facing=-90, against="x+", start_z=1.5)
    for y in (1.15, 1.5):
        place("ramen_bowl_stack", c, S.W, y, facing=rng.uniform(0, 360), against="x+", start_z=1.9)
    place("ramen_bowl_stack", c, S.W, 5.75, facing=rng.uniform(0, 360), against="x+", start_z=1.9)
    place("ramen_soy_bottles", c, S.W, 2.95, facing=-90, against="x+", start_z=1.9)
    place("ramen_square_cans", c, 2.72, 5.72, facing=-90)
    place("ramen_noodle_crates", c, 2.72, S.D, facing=-90, against="y+")
    place("ramen_trash_bin", c, 2.75, 1.05, facing=-60)
    place("ramen_apron_hook", c, 2.62, S.D, z=0.95, facing=0, against="y+", mode="hang")
    # Prep counter behind the pass.
    place("ramen_cutting_board", c, 2.2, 3.0, facing=-90, jitter=8)
    place("ramen_tare_containers", c, 2.2, 3.85, facing=-90, jitter=10)
    place("ramen_bowl_stack", c, 2.22, 2.35, facing=rng.uniform(0, 360))
    place("ramen_hand_towel", c, 2.2, 4.6, facing=-90, jitter=25)
    # ---- customer counter (top at CH) and pass
    cx = S.CX + 0.3
    for y in (2.85, 4.65):
        place("condiment_caddy", c, cx, y, facing=-90, jitter=12)
    for y in (2.25, 4.05, 5.25):
        place("ramen_chopstick_cup", c, cx + 0.04, y, facing=rng.uniform(0, 360))
    place("ramen_tissue_box", c, cx, 3.84, facing=-90, jitter=6)
    place("ramen_bowl_unfinished", c, S.CX + 0.2, 3.3, facing=-60, jitter=5)
    place("ramen_water_glass", c, S.CX + 0.14, 3.6, facing=0)
    place("ramen_water_pitcher", c, cx, 5.75, facing=-120)
    place("ramen_water_glass", c, S.CX + 0.14, 5.0, facing=0)
    place("ramen_maneki_neko", c, S.PASS_X + 0.11, S.Y0 + 0.12, facing=-150, start_z=1.5)
    # ---- walls and ceiling
    place("ramen_wall_fan", c, 0.0, 3.85, z=1.8, facing=90, against="x-", mode="hang")
    place("ramen_crt_tv_bracket", c, S.W, 0.45, z=2.08, facing=180 + 35, against="x+", mode="hang")
    place("ramen_umbrella_stand", c, 1.95, 0.0, facing=20, against="y-", start_z=1.2)
    place("ramen_beer_crate", c, 0.0, 0.9, facing=90, against="x-")
    # ---- outside
    lx, ly, lz = S.LANTERN
    place("lantern", c, lx, ly, z=lz, facing=0, mode="hang")
    return PLACED


def steam_spots():
    """(x, y, z, r) above each stockpot rim, for lighting.steam volumes."""
    out = []
    for o, _ in PLACED:
        if o.name.split(".")[0] == "stockpot":
            lo, hi = _footprint_world(o)
            out.append(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, hi.z, (hi.x - lo.x) * 0.42))
    return out


def steam_sources():
    """Rim points for steam.build: stockpots, the noodle boiler top and the unfinished bowl (design coords)."""
    pots, boiler, bowl = steam_spots(), None, None
    for o, _ in PLACED:
        base = o.name.split(".")[0]
        if base in ("ramen_stockpot_tall", "ramen_stockpot_small"):
            lo, hi = _footprint_world(o)
            pots.append(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, hi.z, (hi.x - lo.x) * 0.42))
        elif base == "ramen_noodle_boiler":
            lo, hi = _footprint_world(o)
            boiler = ((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z + 0.86, hi.x - lo.x, hi.y - lo.y)
        elif base == "ramen_bowl_unfinished" and bowl is None:
            lo, hi = _footprint_world(o)
            bowl = ((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z + 0.09, 0.09)
    return pots, boiler, bowl


def pass_a(c):
    """Densify pass A (mid props): more pots, bowl stacks, crates, a cluttered back shelf, more on the counter.
    Reuses the picked props with variation; round-2 generated props are placed by pass_a_gen when they exist."""
    # Kitchen floor / range zone.
    place("stockpot", c, 2.76, 1.75, facing=rng.uniform(0, 360))
    place("ramen_square_cans", c, 2.74, 2.4, facing=-80)
    place("ramen_beer_crate", c, 0.0, 0.9, facing=95, against="x-", start_z=1.0)        # stacked on the first crate
    place("ramen_beer_crate", c, 0.0, 5.95, facing=88, against="x-")
    place("ramen_beer_crate", c, 0.0, 5.95, facing=92, against="x-", start_z=1.0)
    # Back counter A (x W-0.62..W, y 0.9..3.4): add tare containers; shelves above get crowded.
    place("ramen_tare_containers", c, S.W, 3.1, facing=-90, jitter=12, against="x+")
    for y in (1.2, 1.58, 1.95):
        place("ramen_bowl_stack", c, S.W, y, facing=rng.uniform(0, 360), against="x+", start_z=2.55)   # upper shelf
    place("ramen_tare_containers", c, S.W, 2.35, facing=-90, against="x+", start_z=1.9)
    place("ramen_tissue_box", c, S.W, 3.25, facing=-95, against="x+", start_z=1.9)
    place("ramen_chopstick_cup", c, S.W - 0.05, 1.85, facing=0, against="x+", start_z=1.9)
    # Back counter B shelves (y 5.35..7).
    place("ramen_soy_bottles", c, S.W, 6.2, facing=-90, against="x+", start_z=1.9)
    place("ramen_tare_containers", c, S.W, 6.7, facing=-90, against="x+", start_z=1.9)
    place("stockpot", c, S.W, 6.6, facing=rng.uniform(0, 360), against="x+", start_z=2.55, scale=0.62)
    place("ramen_dish_rack", c, S.W, 5.85, facing=-90, against="x+", start_z=2.55)
    for y in (6.2, 6.33):
        place("ramen_chopstick_cup", c, S.W - 0.04, y, facing=rng.uniform(0, 360), against="x+", start_z=2.55)
    # Prep counter: small plates (scaled bowl stacks), second cutting board, a pot of tare.
    place("ramen_bowl_stack", c, 2.22, 2.65, facing=rng.uniform(0, 360), scale=0.55)
    place("ramen_bowl_stack", c, 2.3, 5.5, facing=rng.uniform(0, 360))
    place("ramen_kettle_pot", c, 2.22, 5.1, facing=-90)
    place("stockpot", c, 2.25, 6.0, facing=rng.uniform(0, 360), scale=0.58)
    # Pass top: a stack of bowls waiting, the next caddy.
    place("ramen_bowl_stack", c, S.PASS_X + 0.11, 2.1, facing=rng.uniform(0, 360), start_z=1.5)
    place("ramen_bowl_stack", c, S.PASS_X + 0.11, 2.42, facing=rng.uniform(0, 360), start_z=1.5, scale=0.85)
    # Customer counter: more condiment sets and glasses, one per seat or so.
    cx = S.CX + 0.3
    for y in (1.78, 5.48):
        place("condiment_caddy", c, cx, y, facing=-90, jitter=12)
    for y in (2.05, 4.35, 5.62):
        place("ramen_water_glass", c, S.CX + 0.13 + rng.uniform(-0.03, 0.03), y, facing=0)
    place("ramen_bowl_unfinished", c, S.CX + 0.19, 5.0 + 0.32, facing=40, jitter=10)
    # Coat hooks on the customer wall near the back: aprons/jackets hanging, a towel.
    for y in (5.55, 5.88):
        place("ramen_apron_hook", c, 0.0, y, z=0.88, facing=90, against="x-", mode="hang")
    place("ramen_hand_towel", c, 0.93, 4.9, facing=rng.uniform(0, 360), start_z=1.3)   # left on a stool


def _have(pid):
    if pid in BRANDED:
        pid = pid + "_nb"
    return os.path.exists(os.path.join(LIB, pid + ".blend"))


def pick(pid, fallback=None):
    """Round-2 prop if it was generated and prepped, else the round-1 fallback (or skip)."""
    return pid if _have(pid) else fallback


def pass_a2(c):
    """Pass A with round-2 picks: variety instead of copies. Same design coordinates as pass_a; steam sources
    (range pots, boiler, first bowl) are untouched so baked caches stay valid."""
    P = lambda pid, fb, *a, **k: place(pick(pid, fb), c, *a, **k) if pick(pid, fb) else None  # noqa: E731
    # Kitchen floor.
    P("ramen_stockpot_tall", "stockpot", 2.76, 1.75, facing=rng.uniform(0, 360))
    place("ramen_square_cans", c, 2.74, 2.4, facing=-80)
    P("ramen_mop_bucket", None, 2.75, 6.1, facing=30)
    P("ramen_rubber_boots", None, 2.85, 0.42, facing=-20)
    P("ramen_fire_extinguisher", None, 3.5, 0.0, facing=0, against="y-")
    # Customer side floor: crates by the door, supply boxes and a rice sack by the fridge.
    place("ramen_beer_crate", c, 0.0, 0.9, facing=95, against="x-", start_z=1.0)
    P("ramen_cardboard_boxes", "ramen_beer_crate", 0.0, 5.95, facing=88, against="x-")
    P("ramen_flour_sacks", None, 0.0, 5.3, facing=90, against="x-")
    P("ramen_rice_sack", None, 0.0, 5.95, facing=75, against="x-", start_z=1.0)   # on the supply boxes
    # Back counter A and its shelves.
    P("ramen_chashu_tray", "ramen_tare_containers", S.W, 3.05, facing=-90, against="x+")
    P("ramen_plate_stack", "ramen_bowl_stack", S.W, 1.2, facing=-90, against="x+", start_z=2.55)
    place("ramen_bowl_stack", c, S.W, 1.58, facing=rng.uniform(0, 360), against="x+", start_z=2.55)
    P("ramen_colander", "ramen_bowl_stack", S.W, 1.98, facing=-90, against="x+", start_z=2.55)
    P("ramen_shelf_jars", "ramen_tare_containers", S.W, 2.4, facing=-90, against="x+", start_z=1.9, scale=0.72)  # fits the 0.36 m shelf gap
    P("ramen_spice_tins", "ramen_tissue_box", S.W, 3.2, facing=-95, against="x+", start_z=1.9)
    P("ramen_radio", "ramen_chopstick_cup", S.W, 1.85, facing=-90, against="x+", start_z=1.9)
    # Back counter B shelves.
    P("ramen_beni_shoga_pot", "ramen_soy_bottles", S.W, 6.2, facing=-90, against="x+", start_z=1.9)
    place("ramen_tare_containers", c, S.W, 6.7, facing=-90, against="x+", start_z=1.9)
    P("ramen_stockpot_small", "stockpot", S.W, 6.6, facing=rng.uniform(0, 360), against="x+", start_z=2.55)
    place("ramen_dish_rack", c, S.W, 5.85, facing=-90, against="x+", start_z=2.55)
    P("ramen_daruma", "ramen_chopstick_cup", S.W - 0.04, 6.25, facing=-90, against="x+", start_z=2.55)
    # Prep counter.
    P("ramen_plate_stack", "ramen_bowl_stack", 2.22, 2.65, facing=rng.uniform(0, 360))
    P("ramen_egg_container", "ramen_bowl_stack", 2.3, 5.5, facing=-90)
    P("ramen_cleaver_board", "ramen_kettle_pot", 2.2, 5.1, facing=-70)
    P("ramen_beni_shoga_pot", "stockpot", 2.25, 6.0, facing=-90)
    P("ramen_bucket_strainer", None, 2.2, 6.35, facing=30)
    P("ramen_garlic_press", None, 2.05, 3.55, facing=-60)
    # Pass top: a stack of bowls waiting, the meal tickets.
    place("ramen_bowl_stack", c, S.PASS_X + 0.11, 2.1, facing=rng.uniform(0, 360), start_z=1.5)
    P("ramen_ticket_tray", "ramen_bowl_stack", S.PASS_X + 0.11, 2.45, facing=-90, start_z=1.5)
    P("ramen_towel_crumpled", None, S.PASS_X + 0.1, 3.3, facing=20, start_z=1.5)
    # Customer counter: one more caddy of each kind, glasses, a menu per few seats, the last customer's things.
    cx = S.CX + 0.3
    place("condiment_caddy", c, cx, 1.78, facing=-90, jitter=12)
    P("ramen_condiment_tray2", "condiment_caddy", cx, 5.48, facing=-90, jitter=8)
    for y in (2.05, 4.35, 5.62):
        place("ramen_water_glass", c, S.CX + 0.13 + rng.uniform(-0.03, 0.03), y, facing=0)
    P("ramen_beer_bottle_glass", "ramen_bowl_unfinished", S.CX + 0.17, 5.25, facing=40)
    for y in (2.6, 4.55):
        P("ramen_menu_stand", None, cx + 0.02, y, facing=-90, jitter=10)
    P("ramen_smartphone", None, S.CX + 0.08, 4.62, facing=20)
    P("ramen_ashtray", None, S.CX + 0.25, 6.05, facing=0)
    P("ramen_lighter_cigs", None, S.CX + 0.13, 5.95, facing=55)
    P("ramen_tea_cup", None, S.CX + 0.08, 2.35, facing=0)
    P("ramen_napkins_used", None, S.CX + 0.08, 5.45, facing=30)
    # Walls.
    P("ramen_coat_hooks", "ramen_apron_hook", 0.0, 5.72, z=1.05, facing=90, against="x-", mode="hang")
    P("ramen_wall_clock", None, 0.0, 2.7, z=1.9, facing=90, against="x-", mode="hang")
    P("ramen_kamidana", None, 1.0, S.D, z=1.95, facing=180, against="y+", mode="hang")
    P("ramen_hook_items", None, 2.36, S.D, z=1.22, facing=180, against="y+", mode="hang")
    place("ramen_hand_towel", c, 0.93, 4.9, facing=rng.uniform(0, 360), start_z=1.3)


def pass_bc_gen(c):
    """Generated pass B/C pieces that replace direct-modelled ones (see r2gen.props for what is removed)."""
    P = lambda pid, *a, **k: place(pid, c, *a, **k) if _have(pid) else None  # noqa: E731
    P("ramen_tongs", 2.12, 4.3, facing=-60)
    P("ramen_coins", S.CX + 0.27, 3.05, facing=10)
    P("ramen_tape_roll", S.W - 0.45, 2.25, facing=-30)
    P("ramen_ladle_pair", 2.0, 5.55, facing=-90)
    P("ramen_power_strip", 0.35, 6.25, facing=80, start_z=0.6)
    P("ramen_cat_dish", 1.0, 0.55, facing=8, start_z=0.6)
    P("ramen_vending_machine", 2.025, -3.0, facing=180, start_z=0.6)
