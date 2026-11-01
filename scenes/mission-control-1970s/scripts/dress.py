"""Dressing passes, big -> small: furniture (consoles, racks, chairs, back aisle), heroes, mid props, clutter.

Props come from props/<id>.blend (prep.py + fixes.py output) as linked duplicates. Everything placed gets
ob["placed"] = True and ob["prop_id"], which the validator and the breakdown read. Instances are tinted through ob.color
(multiplied into albedo by grime.py) so repeats don't read as copies.
"""
import math
import os
import random

import bpy
from mathutils import Vector

import layout as L
import lib
from lib import box, collection

PROPS = os.path.join(lib.ROOT, "scenes", "mission-control-1970s", "props")
TEX = os.path.join(lib.ROOT, "refs", "mission-control-1970s", "tex")
rng = random.Random(1974)
_loaded = {}
PLACED = []
ORDER = 0


def have(pid):
    return os.path.exists(os.path.join(PROPS, pid + ".blend"))


def _load(pid):
    if pid in _loaded:
        return _loaded[pid]
    path = os.path.join(PROPS, pid + ".blend")
    if not os.path.exists(path):
        print("MISSING prop", pid)
        _loaded[pid] = None
        return None
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n == pid]
    _loaded[pid] = dst.objects[0]
    return _loaded[pid]


def instance(pid, coll):
    src = _load(pid)
    if src is None:
        return None
    if src.users_collection:
        o = src.copy()  # linked duplicate: shares mesh + materials
    else:
        o = src
    coll.objects.link(o)
    o.rotation_mode = "XYZ"
    return o


def bbox(o):
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))


def drop(o, start_z, n=5):
    """Lower o so its lowest vertices rest on whatever is under them (rays from those vertices' xy). Lamps and chairs
    have big overhangs; a bounding-box footprint would land them on the console instead of the desk."""
    bpy.context.view_layer.update()
    mw = o.matrix_world
    if o.type == "MESH" and len(o.data.vertices):
        vs = [mw @ v.co for v in o.data.vertices]
        zmin = min(v.z for v in vs)
        base = [v for v in vs if v.z < zmin + 0.015]
        if len(base) > 4:
            step = max(1, len(base) // 40)
            o.hide_set(True)
            dg = bpy.context.evaluated_depsgraph_get()
            top = None
            for v in base[::step]:
                ok, loc, nrm, _i, hit, _m = bpy.context.scene.ray_cast(dg, Vector((v.x, v.y, start_z)), Vector((0, 0, -1)))
                if ok and (top is None or loc.z > top):
                    top = loc.z
            o.hide_set(False)
            if top is not None:
                o.location.z += top - zmin + 0.0005
            return top
    return drop_bbox(o, start_z, n)


def drop_bbox(o, start_z, n=5):
    """Lower o onto the highest surface under its footprint. Rays start at start_z, which must be below anything
    overhead (shelves above, console upper panels) or the prop lands on top of it."""
    lo, hi = bbox(o)
    o.hide_set(True)
    dg = bpy.context.evaluated_depsgraph_get()
    top = None
    for i in range(n):
        for j in range(n):
            x = lo.x + (hi.x - lo.x) * (0.12 + 0.76 * i / (n - 1))
            y = lo.y + (hi.y - lo.y) * (0.12 + 0.76 * j / (n - 1))
            ok, loc, nrm, _i, hit, _m = bpy.context.scene.ray_cast(dg, Vector((x, y, start_z)), Vector((0, 0, -1)))
            if ok and (top is None or loc.z > top):
                top = loc.z
    o.hide_set(False)
    if top is not None:
        o.location.z += top - lo.z + 0.0005
    return top


def place(pid, coll, x, y, yaw=0.0, z=None, start_z=None, against=None, gap=0.005, tint=None, jitter=0.0, label=None):
    """Put a prop with its bottom-centre at (x, y). yaw in degrees (0 = front faces -Y, 90 = front faces +X... see
    rotation: front -Y rotated by yaw counter-clockwise). against: 'x+'/'x-'/'y+'/'y-' pushes its back to that wall
    coordinate (taken from x or y). z fixes the bottom height; otherwise it is dropped from start_z."""
    global ORDER
    o = instance(pid, coll)
    if o is None:
        return None
    o.rotation_euler = (0, 0, math.radians(yaw + rng.uniform(-jitter, jitter)))
    o.location = (x, y, z if z is not None else L.tier_z(y))
    if against:
        lo, hi = bbox(o)
        if against == "x+":
            o.location.x += (x - gap) - hi.x
        elif against == "x-":
            o.location.x += (x + gap) - lo.x
        elif against == "y+":
            o.location.y += (y - gap) - hi.y
        elif against == "y-":
            o.location.y += (y + gap) - lo.y
    if z is None:
        drop(o, start_z if start_z is not None else L.tier_z(o.location.y) + 0.3)
    o["placed"] = True
    o["prop_id"] = pid
    o["order"] = ORDER
    ORDER += 1
    if tint:
        o.color = (*tint, 1)
    if label:
        o.name = label
    PLACED.append(o)
    return o


def tint(spread=0.08, warm=0.0):
    k = 1 + rng.uniform(-spread, spread)
    return (k * (1 + warm), k, k * (1 - warm))


# ---------------------------------------------------------------- furniture

DESK_D, DESK_H = 0.46, 0.70  # writing desk in front of each console row (the generated consoles' own shelf is ~20 cm)


def desks():
    top = lib.grimy("desk_formica", (0.16, 0.17, 0.165), (0.07, 0.065, 0.06), rough=(0.35, 0.6), amount=0.3, scale=4)
    edge = lib.grimy("desk_edge", (0.55, 0.56, 0.57), (0.2, 0.19, 0.17), rough=(0.25, 0.45), metal=1.0, amount=0.2, bump=0.05)
    dark = lib.principled("desk_under", (0.05, 0.05, 0.05), 0.7)
    C = collection("furniture")
    for row in L.ROWS:
        name, z, yf = row[0], row[1], row[2]
        b = list(L.bays(row))
        x0, x1 = b[0][3], b[-1][4]
        box(f"desk_{name}", (x0, yf - DESK_D, z + DESK_H - 0.035), (x1, yf - 0.006, z + DESK_H), top, C, bevel=0.004)
        box(f"desk_edge_{name}", (x0, yf - DESK_D - 0.008, z + DESK_H - 0.04), (x1, yf - DESK_D + 0.002, z + DESK_H + 0.002), edge, C, bevel=0.002)
        box(f"desk_apron_{name}", (x0 + 0.02, yf - DESK_D + 0.03, z + DESK_H - 0.12), (x1 - 0.02, yf - DESK_D + 0.05, z + DESK_H - 0.035), dark, C, bevel=0.002)
        for i, bb in enumerate(b):  # a bracket under every bay joint
            xb = min(max(bb[3], x0 + 0.03), x1 - 0.03)
            box(f"desk_bracket_{name}{i}", (xb - 0.012, yf - DESK_D + 0.06, z + DESK_H - 0.25), (xb + 0.012, yf - 0.01, z + DESK_H - 0.035), dark, C, bevel=0.002)


def consoles():
    C = collection("consoles")
    bays = []
    desks()
    for row in L.ROWS:
        name, z, yf = row[0], row[1], row[2]
        for i, (pid, lab, xc, x0, x1) in enumerate(L.bays(row)):
            o = place(pid, C, xc, yf + L.CONSOLE_D / 2, z=z, tint=tint(0.05, rng.uniform(-0.02, 0.04)), label=f"console_{name}{i}")
            if o is None:
                continue
            o["bay"] = f"{name}{i}"
            o["screen_idx"] = rng.randrange(8)
            bays.append((o, pid, lab, xc, x0, x1, z, yf, name))
    # the hero bay: row A ORBITAL ANALYSIS shows the ground track, its neighbours the telemetry pages
    for o, pid, lab, *_ in bays:
        if lab == "ORBITAL ANALYSIS":
            o["screen_idx"] = 6
        elif lab == "TELEMETRY":
            o["screen_idx"] = 0
        elif lab == "FLIGHT DIRECTOR":
            o["screen_idx"] = 2
    return bays


def placards(bays):
    C = collection("placards")
    font = bpy.data.fonts.load("C:/Windows/Fonts/arialbd.ttf", check_existing=True)
    m_box = lib.principled("placard_black", (0.012, 0.012, 0.012), 0.35)
    m_txt = lib.principled("placard_text", (0.8, 0.8, 0.76), 0.5)
    for o, pid, lab, xc, x0, x1, z, yf, row in bays:
        if not lab:
            continue
        lo, hi = bbox(o)
        w = min(0.8, 0.042 * len(lab) + 0.1)
        # sit on the highest point of the console top (the upper housing), probed along the bay centre line
        dg = bpy.context.evaluated_depsgraph_get()
        best = None
        for k in range(24):
            y = lo.y + (hi.y - lo.y) * (k + 0.5) / 24
            ok, loc, nrm, _i, ob, _m = bpy.context.scene.ray_cast(dg, Vector((xc, y, hi.z + 0.5)), Vector((0, 0, -1)))
            if ok and (best is None or loc.z > best[1] + 0.005):
                best = (y, loc.z)
        y0, zt = (best[0] - 0.025, best[1]) if best else (lo.y + 0.5, hi.z)
        b = box(f"placard_{row}_{lab.lower().replace(' ', '_')}", (xc - w / 2, y0, zt), (xc + w / 2, y0 + 0.04, zt + 0.075), m_box, C, bevel=0.004)
        cu = bpy.data.curves.new("placard_text", "FONT")
        cu.body = lab
        cu.font = font
        cu.size = 0.04
        cu.align_x = "CENTER"
        cu.align_y = "CENTER"
        cu.extrude = 0.0008
        cu.materials.append(m_txt)
        t = bpy.data.objects.new(f"placard_text_{row}_{lab.lower().replace(' ', '_')}", cu)
        t.location = (xc, y0 - 0.001, zt + 0.0375)
        t.rotation_euler = (math.radians(90), 0, 0)
        C.objects.link(t)
        b["settle"] = True  # validate.settle() lowers it with its console; the text rides along
        t["follows"] = b.name


def chairs(bays):
    C = collection("chairs")
    kinds = ["mc_chair_a", "mc_chair_b", "mc_chair_c", "mc_chair_b", "mc_chair_a"]
    for k, (o, pid, lab, xc, x0, x1, z, yf, row) in enumerate(bays):
        if pid == "mc_console_end":
            continue
        back = DESK_D + (rng.uniform(0.42, 0.62) if k % 5 else 0.95)  # one in five pushed well back
        yaw = 180 + rng.uniform(-30, 30) + (rng.choice([-1, 1]) * 50 if k % 7 == 3 else 0)
        dx = rng.uniform(-0.2, 0.2)
        if lab == "ORBITAL ANALYSIS":  # the push-in passes through here: chair swung out to the left
            dx, back, yaw = -1.0, DESK_D + 0.9, 235
        place(rng.choice(kinds), C, xc + dx, yf - back, yaw=yaw, z=z, tint=tint(0.06))


def table(name, x0, y0, x1, y1, z0, h=0.74, coll=None):
    """Grey steel folding table with a wood-grain laminate top."""
    top = lib.wood("laminate_top", light=(0.42, 0.33, 0.24), dark=(0.3, 0.22, 0.15), worn=0.4)
    leg = lib.grimy("table_steel", (0.3, 0.31, 0.3), (0.12, 0.11, 0.1), metal=0.6, amount=0.3)
    coll = coll or collection("furniture")
    box(f"{name}_top", (x0, y0, z0 + h - 0.03), (x1, y1, z0 + h), top, coll, bevel=0.003)
    box(f"{name}_apron", (x0 + 0.03, y0 + 0.03, z0 + h - 0.1), (x1 - 0.03, y1 - 0.03, z0 + h - 0.03), leg, coll, bevel=0.002)
    for i, (x, y) in enumerate(((x0 + 0.05, y0 + 0.05), (x1 - 0.05, y0 + 0.05), (x0 + 0.05, y1 - 0.05), (x1 - 0.05, y1 - 0.05))):
        box(f"{name}_leg{i}", (x - 0.018, y - 0.018, z0), (x + 0.018, y + 0.018, z0 + h - 0.1), leg, coll, bevel=0.002)


def room_furniture():
    C = collection("furniture")
    W, D = L.W, L.D
    # right wall machines, fronts facing -X (yaw -90)
    right = [("mc_line_printer", 1.75), ("mc_teleprinter", 2.95), ("mc_tape_drive", 3.95),
             ("mc_mainframe_rack", 5.1), ("mc_tape_drive", 6.0), ("mc_equipment_rack", 6.85),
             ("mc_mainframe_rack", 8.2), ("mc_equipment_rack", 9.0), ("mc_tape_drive", 9.75), ("mc_filing_cabinet", 11.6),
             ("mc_filing_cabinet", 12.1)]
    for pid, y in right:
        o = place(pid, C, W, y, yaw=-90, against="x+", gap=0.04 if pid != "mc_teleprinter" else 0.12, tint=tint(0.05))
        if o and pid in ("mc_teleprinter", "mc_line_printer"):
            o.name = pid[3:]
    # back aisle (tier 2): coffee table back-left, filing cabinets, water cooler, coat rack
    z2 = L.TIERS[2][0]
    table("coffee_table", 0.35, 0.25, 2.15, 0.95, z2)
    for i, x in enumerate((2.55, 3.05, 3.55)):
        place("mc_filing_cabinet", C, x, 0.0, yaw=180, against="y-", gap=0.03, tint=tint(0.06))
    place("mc_water_cooler", C, 6.75, 0.0, yaw=180, against="y-", gap=0.04)
    place("mc_coat_rack", C, 7.5, 0.45, yaw=160)
    place("mc_paper_box", C, 9.2, 0.0, yaw=175, against="y-", gap=0.05)
    place("mc_paper_box", C, 9.25, 0.42, yaw=190)
    place("mc_rolling_cart", C, 0.55, 11.2, yaw=95, tint=tint(0.05))
    place("mc_overhead_projector", C, 0.55, 12.3, yaw=80)
    place("mc_paper_box", C, 0.42, 10.1, yaw=80)
    # floor ashtrays and waste baskets at row ends and in the lanes
    for x, y in ((1.65, 9.2), (9.3, 6.2), (2.45, 3.3)):
        place("mc_floor_ashtray", C, x, y)
    for x, y in ((1.7, 8.85), (8.75, 7.1), (3.0, 4.3), (9.45, 10.4), (8.2, 3.95)):
        place("mc_wastebasket", C, x, y, yaw=rng.uniform(0, 360), tint=tint(0.06))


def wall_items():
    C = collection("wall_items")
    W, D, H = L.W, L.D, L.H
    place("mc_met_clock", C, 5.75, D - 0.16, z=L.DISP_Z1 + 0.15, against="y+", gap=0.0)
    place("mc_wall_clock", C, W - 0.03, 11.4, yaw=-90, z=2.55, against="x+", gap=0.002)
    place("mc_fire_extinguisher", C, 0.0, 10.15, yaw=90, z=0.55, against="x-", gap=0.0)
    place("mc_fire_extinguisher", C, 8.0, 0.03, yaw=180, z=0.7 + 0.5, against="y-", gap=0.002)
    for x, y, yaw, ag in ((W - 0.03, 2.0, -90, "x+"), (W - 0.03, 10.4, -90, "x+"), (0.0, 12.4, 90, "x-")):
        place("mc_speaker_wall", C, x, y, yaw=yaw, z=2.85, against=ag, gap=0.0)
    for x in (2.2, 9.0):  # ceiling TVs over the tier-1 aisle, screens toward the back rows
        place("mc_tv_ceiling", C, x, 5.2, yaw=0, z=H - 0.706)
    # motto poster between the last window and the front wall, exit sign text
    pm = os.path.join(TEX, "poster_motto_0.png")
    if os.path.exists(pm):
        mat = lib.image_mat("poster_motto", pm, rough=0.35)
        p = lib.plane("poster_motto", (0.012, 11.3, 2.05), 0.9, 1.2, "X", mat, C)
        frame = lib.principled("poster_frame", (0.05, 0.045, 0.04), 0.4, Metallic=0.6)
        box("poster_frame", (0.0, 11.3 - 0.47, 2.05 - 0.62), (0.01, 11.3 + 0.47, 2.05 + 0.62), frame, C, bevel=0.002)
    cu = bpy.data.curves.new("exit_text", "FONT")
    cu.body = "EXIT"
    cu.font = bpy.data.fonts.load("C:/Windows/Fonts/arialbd.ttf", check_existing=True)
    cu.size = 0.12
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.materials.append(lib.emissive("exit_red", (1.0, 0.08, 0.04), 12.0))
    t = bpy.data.objects.new("exit_text", cu)
    t.location = (5.5, 0.092, L.DOOR_Z1 + 0.22)
    t.rotation_euler = (math.radians(90), 0, 0)
    C.objects.link(t)
    for o in C.objects:
        o["wall"] = True


# ---------------------------------------------------------------- desk dressing

DESK_SETS = {
    # bay label -> extra props that bay must have (the hero bays are composed, the rest random)
    "ORBITAL ANALYSIS": ["mc_ashtray_glass", "mc_mug_white", "mc_binder_open", "mc_printout_stack", "mc_headset", "mc_cigarette_pack", "mc_lighter"],
    "TELEMETRY": ["mc_ashtray_square", "mc_paper_cup", "mc_logbook", "mc_desk_phone", "mc_pencil_cup"],
    "FLIGHT DIRECTOR": ["mc_ashtray_glass", "mc_mug_brown", "mc_clipboard", "mc_rotary_phone", "mc_binder_stack", "mc_reading_glasses"],
    "TRAJECTORY": ["mc_ashtray_tin", "mc_mug_green", "mc_slide_rule", "mc_printout_stack", "mc_calculator"],
    "COMMS": ["mc_ashtray_tin", "mc_desk_mic", "mc_headset", "mc_intercom", "mc_paper_cup"],
    "GUIDANCE": ["mc_ashtray_square", "mc_binder_open", "mc_mug_white", "mc_thermos"],
}
SMALL_POOL = ["mc_mug_white", "mc_mug_brown", "mc_paper_cup", "mc_binder_closed", "mc_printout_stack", "mc_clipboard",
              "mc_pencil_cup", "mc_headset", "mc_ashtray_tin", "mc_ashtray_square", "mc_soda_can", "mc_paper_crumpled",
              "mc_stapler", "mc_desk_tray", "mc_rolodex", "mc_manuals_stack", "mc_flashlight", "mc_sandwich", "mc_card_tray"]
LAMP_BAYS = {"ORBITAL ANALYSIS": "mc_lamp_goose", "FLIGHT DIRECTOR": "mc_lamp_arm", "LIFE SUPPORT": "mc_lamp_goose",
             "NETWORK": "mc_lamp_arm", "GUIDANCE": "mc_lamp_goose"}


def shelf_band(o):
    """Find the console's front writing shelf: probe down the bay centre line from the front edge back, keep the run of
    hits that are flat and at desk height. Returns (y0, y1, z) in world space or None."""
    lo, hi = bbox(o)
    xc = (lo.x + hi.x) / 2
    o_hide = []
    dg = bpy.context.evaluated_depsgraph_get()
    hits = []
    for k in range(40):
        y = lo.y + (hi.y - lo.y) * k / 39
        ok, loc, nrm, _i, ob, _m = bpy.context.scene.ray_cast(dg, Vector((xc, y, lo.z + 0.95)), Vector((0, 0, -1)))
        if ok and ob is o and nrm.z > 0.93 and 0.6 < loc.z - lo.z < 0.9:
            hits.append((y, loc.z))
        elif hits:
            break
    if len(hits) < 3:
        return None
    return hits[0][0], hits[-1][0], sum(z for _, z in hits) / len(hits)


def dress_desks(bays, tiers=("hero", "mid", "clutter")):
    C = collection("desk_props")
    placed_xy = []

    def free(x, y, r):
        return all((x - a) ** 2 + (y - b) ** 2 > (r + c) ** 2 for a, b, c in placed_xy)

    def put(pid, x0, x1, y0, y1, zs, yaw=None, tries=30):
        a = _load(pid)
        if a is None:
            return None
        r = max(a.dimensions.x, a.dimensions.y) * 0.5
        for _ in range(tries):
            x = rng.uniform(x0 + r, x1 - r) if x1 - x0 > 2 * r else (x0 + x1) / 2
            y = rng.uniform(y0 + r * 0.8, y1 - r * 0.8) if y1 - y0 > 1.6 * r else (y0 + y1) / 2
            if free(x, y, r * 0.85):
                o = place(pid, C, x, y, yaw=rng.uniform(150, 210) if yaw is None else yaw, start_z=zs, tint=tint(0.07))
                placed_xy.append((x, y, r * 0.85))
                return o
        print("NO ROOM", pid)
        return None

    for o, pid, lab, xc, x0, x1, z, yf, row in bays:
        sy0, sy1, sz = yf - DESK_D + 0.03, yf - 0.02, z + DESK_H
        zs = sz + 0.45  # nothing overhead at the desk except lamp shades
        items = list(DESK_SETS.get(lab, []))
        if pid != "mc_console_end" and not items:
            items = [rng.choice(["mc_ashtray_tin", "mc_ashtray_square", "mc_ashtray_glass"])] + rng.sample(SMALL_POOL, rng.randint(2, 4))
        elif pid == "mc_console_end":
            items = rng.sample(["mc_mug_white", "mc_binder_closed", "mc_manuals_stack", "mc_paper_cup", "mc_printout_stack"], rng.randint(0, 2))
        if lab in LAMP_BAYS:
            if lab == "ORBITAL ANALYSIS":  # right corner: the left of this desk belongs to the hero ashtray
                lamp = put(LAMP_BAYS[lab], x1 - 0.3, x1 - 0.06, sy0 + 0.15, sy1, zs, yaw=rng.uniform(-70, -50))
            else:  # bay corner, shade toward the operator
                lamp = put(LAMP_BAYS[lab], x0 + 0.06, x0 + 0.3, sy0 + 0.15, sy1, zs, yaw=rng.uniform(15, 40))
            if lamp:
                lamp["desk_lamp"] = True
        for it in items:
            if lab == "ORBITAL ANALYSIS" and it == "mc_ashtray_glass":  # hero ashtray: front centre-left, in the push-in
                a = put(it, xc - 0.42, xc - 0.12, sy0 + 0.01, sy0 + 0.22, zs)
                if a:
                    a.name = "hero_ashtray"
                continue
            put(it, x0 + 0.04, x1 - 0.04, sy0 + 0.01, sy1 - 0.01, zs)
    # back-aisle coffee table and console tops
    z2 = L.TIERS[2][0] + 0.75
    for pid in ("mc_coffee_urn", "mc_coffee_maker", "mc_donut_box", "mc_paper_cup", "mc_mug_brown", "mc_thermos"):
        put(pid, 0.4, 2.1, 0.3, 0.9, z2 + 0.4)
    tops = [b for b in bays if b[1] != "mc_console_end"]
    for o, *_ in rng.sample(tops, 4):
        lo, hi = bbox(o)
        put(rng.choice(["mc_binders_row", "mc_manuals_stack", "mc_binder_stack"]), lo.x + 0.1, hi.x - 0.1, lo.y + 0.05, lo.y + 0.45, hi.z + 0.5)
    # floor spill by the line printer and the teleprinter, a briefcase by a chair, a hard hat on the filing cabinet
    place("mc_printout_spill", C, L.W - 1.25, 1.6, yaw=-60, tint=tint(0.03))
    place("mc_printout_spill", C, L.W - 1.05, 3.05, yaw=-110, tint=tint(0.03))
    place("mc_briefcase", C, 4.3, 2.75, yaw=200)
    place("mc_strip_recorder", C, L.W - 0.45, 9.0, yaw=-90, start_z=2.5)
    place("mc_reel_recorder", C, L.W - 0.42, 8.2, yaw=-90, start_z=2.5)
    place("mc_desk_fan", C, 3.55, 0.35, yaw=200, start_z=2.5)
    place("mc_typewriter", C, 3.05, 0.35, yaw=180, start_z=2.5)
    # terminal before the hat: dropped after it, the terminal landed on the hat's crown (2 cm up once resolve moved the hat)
    place("mc_crt_terminal", C, 2.55, 0.4, yaw=185, start_z=2.6)
    place("mc_hard_hat", C, 2.55, 0.35, yaw=30, start_z=2.5)
    place("mc_tape_reel", C, L.W - 0.4, 6.0, yaw=-80, start_z=2.5)
    place("mc_card_tray", C, L.W - 0.45, 5.1, yaw=-95, start_z=2.5)


def build(passes):
    bays = consoles()
    if "furniture" in passes:
        placards(bays)
        chairs(bays)
        room_furniture()
        wall_items()
    if any(p in passes for p in ("heroes", "mid", "clutter")):
        dress_desks(bays)
    bpy.context.view_layer.update()
    print(f"DRESS placed {len(PLACED)} props", flush=True)
