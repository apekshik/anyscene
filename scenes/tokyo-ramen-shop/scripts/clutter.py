"""Pass B (small clutter) and pass C (micro / life), direct-modelled. Design coordinates (pre-mirror).

Paper things carry real Japanese text objects (Yu Gothic) so they read up close without generated textures:
flyers, price strips, receipts, order slips on a rail, chopstick wrappers, stickers on the ticket machine.
Everything that sits on something is dropped with dress._drop or stuck to a surface with a raycast."""
import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

import dress
import shell as S
from lib import L, bsdf, m_simple, new_mat, noise, ramp, texcoord

FONT_B = "C:/Windows/Fonts/YuGothB.ttc"
FONT_R = "C:/Windows/Fonts/YuGothR.ttc"
rng = random.Random(11)
PLACED = []


# ------------------------------------------------------------------ helpers

def _link(o, c):
    for uc in list(o.users_collection):
        uc.objects.unlink(o)
    c.objects.link(o)
    return o


def m_paper(name, color, rough=0.85, grease=0.0):
    m, nt = new_mat(name)
    if nt:
        b = bsdf(nt)
        co = texcoord(nt)
        n = noise(nt, 18, 6, 0.6, co)
        col = ramp(nt, [(0.3, tuple(v * 0.86 for v in color)), (0.75, color)], n.outputs["Fac"])
        L(nt, col.outputs["Color"], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = rough
        b.inputs["Subsurface Weight"].default_value = 0.15
        b.inputs["Subsurface Radius"].default_value = (0.01, 0.01, 0.01)
        if grease:
            g = ramp(nt, [(0.55, (0, 0, 0)), (0.62, (1, 1, 1))], noise(nt, 6, 3, 0.5, co).outputs["Fac"])
            from lib import mix
            L(nt, mix(nt, g.outputs["Color"], col.outputs["Color"], (color[0] * 0.75, color[1] * 0.65, color[2] * 0.45, 1)), b.inputs["Base Color"])
    return m


INK = None


def ink(color=(0.02, 0.02, 0.025), name="ink"):
    return m_simple(name, color, 0.6)


def text(body, size, c, font=FONT_B, mat=None, align="CENTER"):
    cu = bpy.data.curves.new("txt", "FONT")
    cu.body = body
    cu.font = bpy.data.fonts.load(font, check_existing=True)
    cu.size = size
    cu.align_x = align
    cu.align_y = "CENTER"
    cu.space_line = 0.9
    o = bpy.data.objects.new("txt", cu)
    c.objects.link(o)
    cu.materials.append(mat or ink())
    return o


def paper(name, w, h, c, mat, curl=0.0, corner=(1, 1), sag=0.0, res=(10, 14)):
    """Flat sheet in local XY (normal +Z), origin at its centre. curl lifts one corner; sag bows it."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    nx, ny = res
    vs = [[None] * (ny + 1) for _ in range(nx + 1)]
    for i in range(nx + 1):
        for j in range(ny + 1):
            u, v = i / nx, j / ny
            du = u if corner[0] else 1 - u
            dv = v if corner[1] else 1 - v
            k = max(0.0, (du + dv - 1.2) / 0.8)
            z = curl * k * k + sag * math.sin(math.pi * u) * 0.5
            vs[i][j] = bm.verts.new(((u - 0.5) * w, (v - 0.5) * h, z))
    for i in range(nx):
        for j in range(ny):
            f = bm.faces.new((vs[i][j], vs[i + 1][j], vs[i + 1][j + 1], vs[i][j + 1]))
            for lp, (a, b) in zip(f.loops, ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))):
                lp[uvl].uv = (a / nx, b / ny)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    c.objects.link(o)
    me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = True
    o.modifiers.new("thick", "SOLIDIFY").thickness = 0.0004
    return o


def add_text(parent, body, size, x, y, c, font=FONT_B, mat=None, align="CENTER"):
    t = text(body, size, c, font, mat, align)
    t.parent = parent
    t.location = (x, y, 0.0009)
    return t


def stick(o, origin, direction, up=(0, 0, 1), offset=0.0012):
    """Raycast from origin along direction; put o's local +Z along the hit normal, local +Y toward `up`."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    # Volume boxes (room haze, kitchen vapor, steam domains) are meshes too: rays must pass through them.
    hidden = [o] + list(o.children) + [v for v in bpy.data.objects if v.name.startswith(("haze_volume", "kitchen_vapor", "steam_"))]
    for h in hidden:
        h.hide_set(True)
    dg.update()
    ok, loc, n, *_ = bpy.context.scene.ray_cast(dg, Vector(origin), Vector(direction).normalized())
    for h in hidden:
        h.hide_set(False)
    if not ok:
        print("STICK MISS", o.name, origin)
        return False
    z = n.normalized()
    y = (Vector(up) - Vector(up).dot(z) * z)
    if y.length < 1e-4:
        y = Vector((0, 1, 0)) - Vector((0, 1, 0)).dot(z) * z
    y.normalize()
    x = y.cross(z)
    o.matrix_world = Matrix.Translation(loc + z * offset) @ Matrix((x, y, z)).transposed().to_4x4()
    return True


def lay(o, x, y, yaw, start_z=1.3):
    """Flat item: yaw about Z, dropped onto whatever is below (counter, shelf, floor)."""
    o.rotation_euler = (0, 0, math.radians(yaw))
    o.location = (x, y, 0)
    dress._drop(o, start_z)
    PLACED.append(o)
    return o


def crumple(name, r, c, mat, squash=0.55, strength=0.35, seed=0):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=r)
    o = _link(bpy.context.object, c)
    o.name = name
    o.scale = (1.0, 0.85, squash)
    t = bpy.data.textures.new(name + "_tex", "VORONOI")
    t.noise_scale = r * 0.7
    d = o.modifiers.new("crumple", "DISPLACE")
    d.texture = t
    d.strength = r * strength
    d.texture_coords = "LOCAL"
    o.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    o.location = (0, 0, -20 - seed)
    return o


def curve_obj(name, pts, c, mat, radius, res=8):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = 3
    cu.resolution_u = res
    sp = cu.splines.new("NURBS")
    sp.points.add(len(pts) - 1)
    for p, co in zip(sp.points, pts):
        p.co = (*co, 1)
    sp.use_endpoint_u = True
    sp.order_u = min(4, len(pts))
    o = bpy.data.objects.new(name, cu)
    c.objects.link(o)
    cu.materials.append(mat)
    return o


def catenary(a, b, sag, n=12):
    a, b = Vector(a), Vector(b)
    return [tuple(a.lerp(b, t) - Vector((0, 0, sag * 4 * t * (1 - t)))) for t in (i / (n - 1) for i in range(n))]


# ------------------------------------------------------------------ pass B: small clutter

def coin(kind, c):
    spec = {"100": (0.0113, (0.75, 0.75, 0.74)), "500": (0.0132, (0.8, 0.68, 0.42)),
            "10": (0.0118, (0.6, 0.33, 0.18)), "1": (0.01, (0.82, 0.82, 0.82))}[kind]
    bpy.ops.mesh.primitive_cylinder_add(radius=spec[0], depth=0.0017, vertices=28)
    o = _link(bpy.context.object, c)
    o.name = "coin_" + kind
    o.data.materials.append(m_simple("coin_" + kind, spec[1], 0.32, 1.0))
    bpy.ops.object.shade_smooth()
    return o


def noodle(c, x, y, z, seed):
    r = random.Random(seed)
    pts, p, a = [], Vector((x, y, z + 0.0012)), r.uniform(0, 6.28)
    for i in range(26):
        a += r.uniform(-0.7, 0.7)
        p = p + Vector((math.cos(a), math.sin(a), 0)) * 0.009
        pts.append(tuple(p))
    return curve_obj("dropped_noodle", pts, c, m_simple("noodle", (0.78, 0.62, 0.3), 0.35), 0.0011)


def pass_b(c):
    PLACED.clear()
    white_paper = m_paper("paper_white", (0.86, 0.85, 0.8))
    thermal = m_paper("paper_thermal", (0.9, 0.9, 0.87), 0.5)
    cx = S.CX + 0.3
    # Chopstick wrappers (red おてもと paper), some flat, one crumpled, by the seats.
    wrap = m_paper("wrapper_red", (0.38, 0.035, 0.03), 0.6)
    white_ink = ink((0.85, 0.82, 0.75), "ink_white")
    for i, (x, y, yaw) in enumerate([(S.CX + 0.1, 3.42, 70), (S.CX + 0.22, 5.12, 100), (S.CX + 0.08, 2.18, 12)]):
        w = paper("chopstick_wrapper", 0.032, 0.2, c, wrap, curl=0.004, sag=0.003)
        add_text(w, "お\nて\nも\nと", 0.012, 0, 0.02, c, mat=white_ink)
        lay(w, x, y, yaw)
    cw = crumple("wrapper_crumpled", 0.012, c, wrap, squash=0.6, seed=1)
    lay(cw, S.CX + 0.24, 3.55, 0)
    # Used napkins.
    for i, (x, y) in enumerate([(S.CX + 0.06, 2.93), (S.CX + 0.13, 2.86), (S.CX + 0.07, 5.0), (S.CX + 0.28, 2.0)]):
        n = crumple("napkin_used", rng.uniform(0.022, 0.032), c, m_paper("napkin", (0.88, 0.86, 0.8), 0.95), seed=i + 3)
        lay(n, x, y, rng.uniform(0, 360))
    # Receipts: curled thermal paper with printed lines, one on the counter, one on the pass, one on the floor.
    for i, (x, y, yaw, z0) in enumerate([(S.CX + 0.3, 4.15, 15, 1.3), (S.PASS_X + 0.1, 2.75, -30, 1.5), (0.7, 2.9, 60, 0.6)]):
        r = paper("receipt", 0.058, 0.17, c, thermal, curl=0.02, corner=(0, 1), sag=0.012)
        add_text(r, "ラーメン一番\n─────────\n醤油ラーメン  ¥800\n味玉        ¥150\n生ビール    ¥500\n─────────\n合計      ¥1,450\nお預り    ¥2,000\nお釣り      ¥550", 0.0052, 0, 0.0, c, FONT_R, ink((0.15, 0.15, 0.16), "ink_thermal"))
        lay(r, x, y, yaw, z0)
    # Coins left on the counter by the bowl.
    for i, k in enumerate(["100", "100", "10", "500", "1", "10"]):
        co = coin(k, c)
        lay(co, S.CX + 0.27 + rng.uniform(-0.03, 0.03), 3.05 + rng.uniform(-0.03, 0.03), rng.uniform(0, 360))
        co.rotation_euler.x = math.radians(rng.uniform(-4, 4))
    # A dropped noodle by the unfinished bowl, another on the prep counter.
    noodle(c, S.CX + 0.12, 3.12, S.CH, 1)
    noodle(c, 2.05, 3.25, 0.88, 2)
    # Order slips clipped to a rail on the hood front (faces the customers).
    hx = S.W - 0.75
    from lib import box
    box("order_rail", (hx - 0.03, 3.6, 1.98), (hx, 4.9, 2.01), c, m_simple("rail_steel", (0.6, 0.6, 0.6), 0.25, 1.0), 0.003)
    slips = ["醤油 2\n味玉 1\n大盛", "味噌 1\n餃子 2", "塩 1\nライス", "つけ麺 1\n生 2", "チャーシュー 1\n替玉"]
    for i, body in enumerate(slips):
        s = paper("order_slip", 0.075, 0.11, c, m_paper("slip", (0.93, 0.92, 0.86), grease=0.4), curl=0.008, corner=(i % 2, 0))
        add_text(s, body, 0.012, 0, 0.005, c, FONT_R, ink((0.05, 0.06, 0.2), "ink_pen"))
        # Hang from the rail: sheet faces -X (customers) with text upright.
        s.matrix_world = Matrix.Translation((hx - 0.035, 3.72 + i * 0.25 + rng.uniform(-0.03, 0.03), 1.94)) @ \
            Matrix.Rotation(math.radians(-90), 4, "Z") @ Matrix.Rotation(math.radians(90), 4, "X") @ Matrix.Rotation(math.radians(rng.uniform(-6, 6)), 4, "Z")
        PLACED.append(s)
    # Spice tins and jars on the pass and back shelf.
    tin_cols = [(0.6, 0.08, 0.05), (0.75, 0.55, 0.1), (0.1, 0.25, 0.12)]
    labels = ["七味", "胡椒", "山椒"]
    for i, (x, y, z0) in enumerate([(S.PASS_X + 0.08, 3.95, 1.5), (S.PASS_X + 0.13, 4.0, 1.5), (S.W - 0.08, 2.15, 1.9), (S.W - 0.1, 6.45, 1.9)]):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.022, depth=0.07, vertices=24)
        t = _link(bpy.context.object, c)
        t.name = "spice_tin"
        t.data.materials.append(m_simple("tin_" + labels[i % 3], tin_cols[i % 3], 0.35, 0.6))
        bpy.ops.object.shade_smooth()
        lay(t, x, y, rng.uniform(0, 360), z0)
        lab = text(labels[i % 3], 0.014, c, mat=ink((0.95, 0.9, 0.75), "ink_cream"))
        lab.parent = t
        lab.location = (0, -0.0225, 0.0)
        lab.rotation_euler = (math.radians(90), 0, 0)
    glass = m_simple("jar_glass", (0.95, 0.97, 0.96), 0.03, trans=1.0)
    for i, (x, y, z0, col) in enumerate([(S.W - 0.12, 2.55, 2.55, (0.75, 0.55, 0.3)), (S.W - 0.1, 6.95, 2.55, (0.55, 0.1, 0.05)), (2.3, 4.25, 1.2, (0.9, 0.85, 0.7))]):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.045, depth=0.12, vertices=32)
        j = _link(bpy.context.object, c)
        j.name = "jar"
        j.data.materials.append(glass)
        bpy.ops.object.shade_smooth()
        lay(j, x, y, 0, z0)
        bpy.ops.mesh.primitive_cylinder_add(radius=0.041, depth=0.08, vertices=32)
        f = _link(bpy.context.object, c)
        f.name = "jar_fill"
        f.data.materials.append(m_simple(f"jar_fill_{i}", col, 0.7))
        f.parent = j
        f.location = (0, 0, -0.018)
        bpy.ops.mesh.primitive_cylinder_add(radius=0.047, depth=0.018, vertices=32)
        l = _link(bpy.context.object, c)
        l.name = "jar_lid"
        l.data.materials.append(m_simple("jar_lid", (0.6, 0.05, 0.04), 0.4, 0.5))
        l.parent = j
        l.location = (0, 0, 0.068)
    # Tape roll and marker by the register.
    bpy.ops.mesh.primitive_torus_add(major_radius=0.034, minor_radius=0.013, major_segments=32, minor_segments=12)
    tp = _link(bpy.context.object, c)
    tp.name = "tape_roll"
    tp.scale = (1, 1, 1.4)
    tp.data.materials.append(m_simple("packing_tape", (0.55, 0.36, 0.15), 0.25, trans=0.3))
    lay(tp, S.W - 0.45, 2.25, 0)
    # Towel folded over the pass edge: the picked hand-towel prop, laid on the pass top.
    t = dress._instance("ramen_hand_towel", c)
    if t:
        t.rotation_mode = "XYZ"
        lay(t, S.PASS_X + 0.1, 4.95, 80, 1.5)
    # Ladle and tongs on the prep counter: thin steel bars / bowls.
    steel = m_simple("utensil_steel", (0.65, 0.65, 0.66), 0.22, 1.0)
    for i, (x, y, yaw) in enumerate([(2.1, 4.25, 20), (2.15, 4.35, 35)]):
        bpy.ops.mesh.primitive_cube_add(size=1)
        tg = _link(bpy.context.object, c)
        tg.name = "tongs"
        tg.scale = (0.012, 0.26, 0.004)
        tg.data.materials.append(steel)
        lay(tg, x, y, yaw)
    return PLACED


# ------------------------------------------------------------------ pass C: micro / life

def flyer(c, name, w, h, color, body, size, origin, direction, up=(0, 0, 1), curl=0.025, ink_col=(0.03, 0.03, 0.04), extra=None):
    f = paper(name, w, h, c, m_paper(name + "_paper", color, grease=0.4), curl=curl, corner=(rng.random() > 0.5, 1))
    add_text(f, body, size, 0, h * 0.12, c, mat=ink(ink_col, name + "_ink"))
    if extra:
        extra(f)
    stick(f, origin, direction, up)
    # Tape or pins at the top corners.
    for sx in (-1, 1):
        if rng.random() < 0.5:
            bpy.ops.mesh.primitive_uv_sphere_add(radius=0.005, segments=12, ring_count=8)
            p = _link(bpy.context.object, c)
            p.data.materials.append(m_simple("pushpin_" + str(sx), (0.8, 0.1, 0.08) if sx > 0 else (0.1, 0.3, 0.8), 0.3))
        else:
            bpy.ops.mesh.primitive_plane_add(size=1)
            p = _link(bpy.context.object, c)
            p.scale = (0.045, 0.02, 1)
            p.data.materials.append(m_simple("tape_clear", (0.85, 0.8, 0.6), 0.35, alpha=0.5))
        p.parent = f
        p.location = (sx * w * 0.42, h * 0.47, 0.0015)
        p.rotation_euler = (0, 0, math.radians(rng.uniform(-25, 25)))
    PLACED.append(f)
    return f


def sticker(c, shape, size, color, body, txt_col, origin, direction, up=(0, 0, 1), curl=0.0):
    if shape == "circle":
        bpy.ops.mesh.primitive_circle_add(vertices=32, radius=size / 2, fill_type="NGON")
        s = _link(bpy.context.object, c)
        s.modifiers.new("thick", "SOLIDIFY").thickness = 0.0003
    else:
        s = paper("sticker", size, size * 0.62, c, None, curl=curl, res=(6, 6))
        s.data.materials.clear()
    s.name = "sticker"
    s.data.materials.append(m_simple("sticker_" + body, color, 0.45, coat=0.4))
    add_text(s, body, size * 0.22, 0, 0, c, mat=ink(txt_col, "ink_" + body))
    stick(s, origin, direction, up, 0.0008)
    PLACED.append(s)
    return s


def pass_c(c):
    PLACED.clear()
    yellowed = (0.86, 0.8, 0.6)
    # Flyers on the customer wall (x=0, facing +X) and by the door.
    flyer(c, "flyer_parttime", 0.21, 0.297, yellowed, "アルバイト\n募集\n\n時給 1,200円〜\n深夜手当あり\n\n店主まで", 0.024,
          (0.5, 2.75, 1.42), (-1, 0, 0))
    flyer(c, "flyer_lostcat", 0.21, 0.297, (0.9, 0.9, 0.88), "迷い猫\n探しています\n\n\n\n\n茶トラ・オス\n090-XXXX-XXXX", 0.022,
          (0.5, 5.1, 1.38), (-1, 0, 0),
          extra=lambda f: _photo_block(f, c, 0.12, 0.08, 0.0, -0.005))
    flyer(c, "flyer_festival", 0.21, 0.297, (0.92, 0.55, 0.2), "夏祭り\n\n盆踊り・夜店\n8月 第一土曜\n商店街振興会", 0.026,
          (0.5, 1.62, 1.42), (-1, 0, 0), ink_col=(0.25, 0.04, 0.02))
    # Price strips (yellow paper, vertical text) on the customer wall above the wainscot rail.
    items = [("生ビール", "500円"), ("瓶ビール", "650円"), ("ハイボール", "450円"), ("日本酒", "550円"),
             ("ウーロン茶", "200円"), ("餃子", "400円"), ("チャーハン", "700円"), ("替玉", "150円")]
    for i, (name, price) in enumerate(items):
        s = paper("price_strip", 0.07, 0.36, c, m_paper("strip_yellow", (0.92, 0.78, 0.25), grease=0.5), curl=0.006, corner=(0, 0), res=(4, 12))
        add_text(s, "\n".join(name), 0.034, 0, 0.04, c)
        add_text(s, price, 0.016, 0, -0.15, c, mat=ink((0.7, 0.05, 0.03), "ink_red"))
        stick(s, (0.5, 4.12 + i * 0.085, 2.05), (-1, 0, 0))
        s.matrix_world = s.matrix_world @ Matrix.Rotation(math.radians(rng.uniform(-2, 2)), 4, "Z")
        PLACED.append(s)
    # Stickers on the ticket machine side and front (lower panel) — sticky, layered, one peeling.
    tm = bpy.data.objects.get("ticket_machine")
    if tm:
        lo, hi = dress._footprint_world(tm)
        side_x = hi.x + 0.3
        for (shape, size, col, body, tcol, y, z, curl) in [
            ("rect", 0.09, (0.85, 0.1, 0.08), "現金のみ", (1, 1, 1), lo.y + 0.12, 1.1, 0.0),
            ("circle", 0.07, (0.95, 0.8, 0.1), "千円札\nOK", (0.1, 0.1, 0.1), lo.y + 0.28, 1.05, 0.0),
            ("rect", 0.1, (0.1, 0.35, 0.75), "交通系IC\n使えません", (1, 1, 1), lo.y + 0.2, 0.85, 0.012),
            ("rect", 0.07, (0.95, 0.95, 0.92), "禁煙", (0.8, 0.05, 0.05), lo.y + 0.33, 0.7, 0.0),
        ]:
            sticker(c, shape, size, col, body, tcol, (side_x, y, z), (-1, 0, 0), curl=curl)
        front_y = hi.y + 0.3
        for (shape, size, col, body, tcol, x, z) in [
            ("rect", 0.08, (0.9, 0.9, 0.85), "食券を\nお買い求め\nください", (0.1, 0.1, 0.1), lo.x + 0.15, 0.45),
            ("circle", 0.06, (0.85, 0.15, 0.4), "PAY", (1, 1, 1), lo.x + 0.45, 0.5),
        ]:
            sticker(c, shape, size, col, body, tcol, (x, front_y, z), (0, -1, 0))
    # Conduit along the customer wall/ceiling corner and down to the ticket machine; cable to the CRT.
    pvc = m_simple("conduit_pvc", (0.55, 0.55, 0.52), 0.55)
    curve_obj("conduit_top", [(0.03, 0.3, 2.56), (0.03, 3.5, 2.56), (0.03, 6.9, 2.56)], c, pvc, 0.011)
    curve_obj("conduit_down", [(0.03, 0.3, 2.56), (0.03, 0.3, 2.0), (0.03, 0.3, 1.62)], c, pvc, 0.011)
    for y in (0.9, 1.9, 2.9, 3.9, 4.9, 5.9):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0.025, y, 2.56))
        k = _link(bpy.context.object, c)
        k.scale = (0.02, 0.025, 0.03)
        k.data.materials.append(pvc)
    black = m_simple("cable_black", (0.015, 0.015, 0.015), 0.45)
    white_cable = m_simple("cable_white", (0.7, 0.7, 0.66), 0.5)
    curve_obj("crt_cable", catenary((S.W - 0.02, 0.5, 2.5), (S.W - 0.18, 0.45, 2.15), 0.06), c, black, 0.003)
    # Cables sagging between the pendant cords (pendants are on the pass line).
    for i in range(len(S.PENDANT_Y) - 1):
        curve_obj("pendant_cable", catenary((S.CX + 0.22, S.PENDANT_Y[i], 2.58), (S.CX + 0.22, S.PENDANT_Y[i + 1], 2.58), 0.12), c, black, 0.0035)
    # Extension cord along the floor from the wall to the drink fridge, and a power strip by the rice cooker.
    curve_obj("ext_cord", [(0.03, 4.8, 0.32), (0.04, 4.9, 0.006), (0.25, 5.3, 0.006), (0.12, 5.9, 0.006), (0.3, 6.3, 0.006)], c, white_cable, 0.0035)
    bpy.ops.mesh.primitive_cube_add(size=1)
    ps = _link(bpy.context.object, c)
    ps.name = "power_strip"
    ps.scale = (0.26, 0.05, 0.03)
    ps.data.materials.append(m_simple("strip_plastic", (0.8, 0.79, 0.74), 0.5))
    lay(ps, 0.35, 6.25, 80, 0.6)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.012, 4.8, 0.35))
    ob = _link(bpy.context.object, c)
    ob.name = "wall_outlet"
    ob.scale = (0.02, 0.07, 0.11)
    ob.data.materials.append(m_simple("outlet", (0.82, 0.8, 0.74), 0.45))
    # Cat food dish and water bowl just inside the door, on a placemat.
    mat_o = paper("cat_placemat", 0.32, 0.22, c, m_simple("placemat", (0.35, 0.55, 0.7), 0.5), res=(4, 4))
    lay(mat_o, 1.0, 0.55, 8, 0.5)
    bowl_steel = m_simple("pet_bowl", (0.7, 0.7, 0.71), 0.18, 1.0)
    for i, (dx, fill) in enumerate([(-0.075, "kibble"), (0.075, "water")]):
        bpy.ops.mesh.primitive_cone_add(vertices=40, radius1=0.05, radius2=0.068, depth=0.04, end_fill_type="NOTHING")
        b = _link(bpy.context.object, c)
        b.name = "pet_bowl"
        b.data.materials.append(bowl_steel)
        b.modifiers.new("thick", "SOLIDIFY").thickness = 0.002
        bpy.ops.object.shade_smooth()
        lay(b, 1.0 + dx, 0.55, 0, 0.5)
        bpy.ops.mesh.primitive_circle_add(vertices=40, radius=0.05, fill_type="NGON", location=(0, 0, -0.019))
        bot = _link(bpy.context.object, c)
        bot.data.materials.append(bowl_steel)
        bot.parent = b
        bot.location = (0, 0, -0.019)
        if fill == "water":
            bpy.ops.mesh.primitive_circle_add(vertices=40, radius=0.058, fill_type="NGON")
            w = _link(bpy.context.object, c)
            w.data.materials.append(m_simple("pet_water", (0.9, 0.95, 0.95), 0.02, trans=1.0, ior=1.33))
            w.parent = b
            w.location = (0, 0, -0.002)
        else:
            me = bpy.data.meshes.new("kibble")
            bm = bmesh.new()
            r = random.Random(5)
            for k in range(70):
                a, rr = r.uniform(0, 6.28), 0.05 * math.sqrt(r.random())
                bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.0045,
                                           matrix=Matrix.Translation((rr * math.cos(a), rr * math.sin(a), -0.012 + r.uniform(0, 0.012))) @ Matrix.Diagonal((1, 0.8, 0.6, 1)))
            bm.to_mesh(me)
            bm.free()
            kb = bpy.data.objects.new("kibble", me)
            c.objects.link(kb)
            me.materials.append(m_simple("kibble", (0.32, 0.17, 0.07), 0.6))
            kb.parent = b
    # Keys and a plastic bag on a hook by the kitchen entrance; a calendar-side hook with a fly swatter.
    hook_mat = m_simple("hook_metal", (0.3, 0.3, 0.3), 0.4, 1.0)
    # Hooks on the back wall of the kitchen (y = D, facing -Y), next to the apron.
    for i, x in enumerate((2.3, 2.42)):
        curve_obj("wall_hook", [(x, S.D - 0.005, 1.5), (x, S.D - 0.045, 1.47), (x, S.D - 0.045, 1.52)], c, hook_mat, 0.003)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.014, minor_radius=0.0012, location=(2.3, S.D - 0.04, 1.45))
    kr = _link(bpy.context.object, c)
    kr.name = "key_ring"
    kr.rotation_euler = (math.radians(90), 0, 0)
    kr.data.materials.append(m_simple("key_metal", (0.75, 0.68, 0.45), 0.3, 1.0))
    for j in range(3):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(2.3 + (j - 1) * 0.008, S.D - 0.04, 1.415 - j * 0.004))
        k = _link(bpy.context.object, c)
        k.scale = (0.012, 0.002, 0.05)
        k.rotation_euler = (0, math.radians((j - 1) * 14), 0)
        k.data.materials.append(m_simple("key_metal", (0.75, 0.68, 0.45), 0.3, 1.0))
    bag = crumple("plastic_bag", 0.09, c, m_simple("bag_plastic", (0.9, 0.9, 0.88), 0.3, trans=0.4), squash=1.6, strength=0.25, seed=9)
    bag.location = (2.42, S.D - 0.07, 1.34)
    bag.scale = (0.9, 0.5, 1.4)
    return PLACED


def _photo_block(f, c, w, h, x, y):
    bpy.ops.mesh.primitive_plane_add(size=1)
    p = _link(bpy.context.object, c)
    p.scale = (w, h, 1)
    p.data.materials.append(m_simple("photo_grey", (0.35, 0.28, 0.2), 0.4))
    p.parent = f
    p.location = (x, y, 0.0008)
