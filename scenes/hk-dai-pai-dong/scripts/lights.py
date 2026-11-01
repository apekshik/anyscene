"""Night lighting: practicals first (bulbs, wok flames, enamel shade, fluorescent), then signage spill, street lamp,
lit shopfront security tubes, and last a weak sky/bounce fill. Each light gets ["cat"] and ["order"] so the
breakdown's lighting clip can switch them on in a sensible order.

Gotchas carried over: area lights shine along local -Z; fills are hidden from camera/glossy/transmission;
emission on dense generated meshes gets emission_sampling NONE (see emitters.run()).
"""
import math

import bpy
from mathutils import Vector

import shell as S
from lib import L, area, blackbody, bsdf, coll, mathn, new_mat, node, noise, point, ramp, spot, texcoord

ORDER = []
WARM = blackbody(2500)


def tag(o, cat):
    o["cat"] = cat
    o["order"] = len(ORDER)
    ORDER.append(o.name)
    return o


def awning_z(x):
    a = S.AWN
    u = (x - a["x0"]) / (a["x1"] - a["x0"])
    return a["z_wall"] + (a["z_edge"] - a["z_wall"]) * u - 0.05 * math.sin(math.pi * u)


def m_bulb():
    m, nt = new_mat("bulb_glow")
    if nt:
        b = bsdf(nt)
        b.inputs["Base Color"].default_value = (*WARM, 1)
        b.inputs["Emission Color"].default_value = (*WARM, 1)
        b.inputs["Emission Strength"].default_value = 18.0  # 60 burnt out to a white disc
    return m


def bulb(name, c, x, y, z_bottom, energy=30.0):
    """Bare bulb on a black cord from the awning: emissive glass + a point light."""
    from shell import rod
    top = awning_z(x) - 0.02
    cord = rod(name + "_cord", (x, y, top), (x, y, z_bottom + 0.1), 0.004, c, S.m_simple("cord", (0.01, 0.01, 0.01), 0.4))
    sock = rod(name + "_socket", (x, y, z_bottom + 0.1), (x, y, z_bottom + 0.06), 0.014, c, S.m_simple("socket", (0.03, 0.025, 0.02), 0.5, 0.3))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.03, segments=16, ring_count=10, location=(x, y, z_bottom + 0.03))
    g = bpy.context.object
    g.name = name + "_glass"
    for uc in list(g.users_collection):
        uc.objects.unlink(g)
    c.objects.link(g)
    g.scale.z = 1.25
    g.data.materials.append(m_bulb())
    bpy.ops.object.shade_smooth()
    p = point(name, c, (x, y, z_bottom + 0.035), energy, WARM, radius=0.025)
    p.data.use_soft_falloff = False
    return tag(p, "practical"), g


def m_flame(name):
    """Gas jet flame as a volume: blue core near the burner, orange licks up the wok, animated noise."""
    m, nt = new_mat(name)
    if not nt:
        return m
    nt.nodes.remove(bsdf(nt))
    gen = texcoord(nt, "Generated")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    L(nt, gen, sep.inputs[0])
    # Radial distance from the axis in generated space (0..1 box -> centre 0.5).
    dx = mathn(nt, "SUBTRACT", sep.outputs["X"], 0.5)
    dy = mathn(nt, "SUBTRACT", sep.outputs["Y"], 0.5)
    r = mathn(nt, "SQRT", mathn(nt, "ADD", mathn(nt, "MULTIPLY", dx, dx), mathn(nt, "MULTIPLY", dy, dy)))
    z = sep.outputs["Z"]
    # Tongues hug the outside of the wok bowl (generated space: box radius 0.36 m, 0.3 m tall; wok bottom at z 0.3,
    # well rim at 0.5, bowl radius ~0.19 m there and ~0.27 m at z 0.7), half-width ~4 cm. A wider ring stood off the
    # bowl as an orange curtain around the rim.
    ring_r = mathn(nt, "ADD", -0.025, mathn(nt, "MULTIPLY", z, 0.56))
    ring = mathn(nt, "SUBTRACT", 1.0, mathn(nt, "MULTIPLY", mathn(nt, "ABSOLUTE", mathn(nt, "SUBTRACT", r, ring_r)), 18.0), clamp=True)
    # Animated noise, stretched vertically into tongues, scrolling upward fast.
    co = texcoord(nt, "Object")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 1.0, 0.12)
    L(nt, co, mp.inputs["Vector"])
    mp.inputs["Location"].driver_add("default_value", 2).driver.expression = "-frame * 0.012"
    n = noise(nt, 34.0, 3, 0.55, mp.outputs[0], dim="4D")
    n.inputs["W"].driver_add("default_value").driver.expression = "frame * 0.16"
    lick = ramp(nt, [(0.55, (0, 0, 0)), (0.6, (1, 1, 1))], n.outputs["Fac"]).outputs["Color"]
    # Full strength under the wok, dying out ~5 cm above the well rim (z 0.68): tongues lick the lower bowl only.
    t = mathn(nt, "MULTIPLY", mathn(nt, "SUBTRACT", z, 0.42), 3.8, clamp=True)
    fall = mathn(nt, "POWER", mathn(nt, "SUBTRACT", 1.0, t, clamp=True), 1.5)
    # Blue jets at the well mouth, broken up by the same noise (a continuous band read as a ring sheet).
    base = mathn(nt, "SUBTRACT", 1.0, mathn(nt, "MULTIPLY", mathn(nt, "ABSOLUTE", mathn(nt, "SUBTRACT", z, 0.45)), 14.0), clamp=True)
    jets = ramp(nt, [(0.38, (0, 0, 0)), (0.55, (1, 1, 1))], n.outputs["Fac"]).outputs["Color"]
    dens = mathn(nt, "MULTIPLY", ring, mathn(nt, "MAXIMUM", mathn(nt, "MULTIPLY", lick, fall),
                                            mathn(nt, "MULTIPLY", mathn(nt, "MULTIPLY", base, jets), 0.6)))
    v = nt.nodes.new("ShaderNodeVolumePrincipled")
    v.inputs["Density"].default_value = 0.0
    col = ramp(nt, [(0.0, (0.1, 0.25, 1.0)), (0.44, (0.2, 0.35, 1.0)), (0.5, (1.0, 0.42, 0.06)), (1.0, (1.0, 0.22, 0.02))], z).outputs["Color"]
    L(nt, col, v.inputs["Emission Color"])
    L(nt, mathn(nt, "MULTIPLY", dens, 210.0), v.inputs["Emission Strength"])
    L(nt, v.outputs[0], nt.nodes["Material Output"].inputs["Volume"])
    return m


def flames(c, woks):
    out = []
    for i, (x, y, z) in enumerate(woks):
        # Volume box around the burner well and the lower wok bowl.
        bpy.ops.mesh.primitive_cylinder_add(radius=0.36, depth=0.3, vertices=32, location=(x, y, z))
        f = bpy.context.object
        f.name = f"wok_flame_{i}"
        for uc in list(f.users_collection):
            uc.objects.unlink(f)
        c.objects.link(f)
        f.data.materials.append(m_flame("flame_vol"))
        f.visible_shadow = False
        f["no_support"] = True
        # Orange lick light + blue core light, flickering.
        o = point(f"wok_fire_{i}", c, (x + 0.12, y, z - 0.02), 55, (1.0, 0.48, 0.15), radius=0.1)
        d = o.data.driver_add("energy").driver
        d.expression = f"55*(1+0.28*sin(frame*1.9+{i * 2.1})+0.17*sin(frame*5.3+{i})+0.1*sin(frame*11.7))"
        tag(o, "practical")
        b = point(f"wok_blue_{i}", c, (x + 0.1, y, z - 0.08), 12, (0.3, 0.45, 1.0), radius=0.08)
        tag(b, "practical")
        out += [f, o, b]
    return out


def build():
    c = coll("lights")
    import dress
    woks = dress.WOKS or [(-3.05, 2.81, 0.85), (-3.05, 3.55, 0.85)]
    # Bare bulbs under the awning (over the cart, the range end, the prep table, and each pavement table).
    B = [(-2.35, -0.25, 2.1, 28), (-2.35, 1.5, 2.15, 32), (-2.45, 4.6, 2.1, 30), (-1.05, 0.3, 1.95, 34),
         (-1.05, 2.75, 2.0, 30), (-1.05, 5.1, 1.95, 30), (-1.8, 6.6, 2.05, 22)]
    for i, (x, y, z, e) in enumerate(B):
        bulb(f"bulb_{i}", c, x, y, z, e * 1.6)
    # Enamel shade over the woks: a spot just under the rim and a glowing bulb inside it.
    shade = bpy.data.objects.get("wok_shade")
    if shade:
        lo, hi = dress.bounds(shade)
        cx, cy = (lo.x + hi.x) / 2, (lo.y + hi.y) / 2
        s = spot("wok_shade_spot", c, (cx, cy, lo.z - 0.02), (0, 0, 0), 45, WARM, angle=115, blend=0.5, radius=0.05)
        tag(s, "practical")
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.032, segments=16, ring_count=10, location=(cx, cy, lo.z + 0.035))
        g = bpy.context.object
        g.name = "wok_shade_bulb"
        for uc in list(g.users_collection):
            uc.objects.unlink(g)
        c.objects.link(g)
        g.data.materials.append(m_bulb())
    flames(coll("flames"), woks)
    # Fluorescent batten on the wall over the back shelves: cool, slightly green.
    fl = bpy.data.objects.get("fluoro")
    if fl:
        lo, hi = dress.bounds(fl)
        a = area("fluoro_tube", c, ((lo.x + hi.x) / 2 + 0.05, (lo.y + hi.y) / 2, lo.z - 0.01), (0, math.radians(35), 0),
                 0.06, 45, (0.82, 1.0, 0.86), size_y=1.15)
        a.visible_camera = False
        tag(a, "practical")
        bpy.ops.mesh.primitive_cylinder_add(radius=0.013, depth=1.15, vertices=12, location=((lo.x + hi.x) / 2 + 0.03, (lo.y + hi.y) / 2, lo.z + 0.015),
                                            rotation=(math.radians(90), 0, 0))
        t = bpy.context.object
        t.name = "fluoro_tube_glow"
        for uc in list(t.users_collection):
            uc.objects.unlink(t)
        c.objects.link(t)
        t.data.materials.append(S.m_emit("fluoro_glow", (0.85, 1.0, 0.9), 12))
    # Signage spill: a soft point light just in front of each neon box / lightbox, in its colour.
    for o in list(bpy.data.objects):
        if o.name.startswith("neon_box_") or (o.name.startswith("lightbox_") and o.type == "MESH" and o.name.count("_") == 1):
            lo, hi = dress.bounds(o)
            ctr = (lo + hi) / 2
            if o.name.startswith("neon_box_"):
                k = o.name.split("_")[-1]
                mat = bpy.data.materials.get(f"neon_{k}")
                col = tuple(mat.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value[:3]) if mat else (1, 0.2, 0.3)
                e = 220
            else:
                col, e = (1.0, 0.92, 0.8), 90
            for sy in (-1, 1):
                p = point(f"spill_{o.name}_{'f' if sy < 0 else 'b'}", c, (ctr.x, ctr.y + sy * 0.45, ctr.z), e, col, radius=0.35)
                p.visible_glossy = True
                tag(p, "signage")
    # Street lamp: spot at the lamp head, cool LED-white, plus a faint glow.
    lamp = bpy.data.objects.get("street_lamp")
    if lamp:
        lo, hi = dress.bounds(lamp)
        # The head is at the end of the arm: the bbox corner farthest from the pole base, at the top.
        base = Vector((lamp.location.x, lamp.location.y))
        cand = [Vector((lo.x, lo.y)), Vector((lo.x, hi.y)), Vector((hi.x, lo.y)), Vector((hi.x, hi.y))]
        far = max(cand, key=lambda v: (v - base).length)
        hx, hy = (far.x + base.x * 0.25) / 1.25, (far.y + base.y * 0.25) / 1.25
        sp = spot("street_lamp_light", c, (hx, hy, hi.z - 0.25), (0, 0, 0), 2200, (0.86, 0.92, 1.0), angle=125, blend=0.6, radius=0.18)
        tag(sp, "street")
    # Shopfront security tubes on the far side (closed shops keep one tube on).
    for i, y in enumerate((-6.0, 4.0, 13.5, 21.0)):
        x = S.FX1 - 0.35
        bpy.ops.mesh.primitive_cylinder_add(radius=0.014, depth=1.2, vertices=10, location=(x, y, 2.95), rotation=(math.radians(90), 0, 0))
        t = bpy.context.object
        t.name = f"security_tube_{i}"
        for uc in list(t.users_collection):
            uc.objects.unlink(t)
        c.objects.link(t)
        t.data.materials.append(S.m_emit("fluoro_glow", (0.85, 1.0, 0.9), 12))
        a = area(f"security_light_{i}", c, (x - 0.05, y, 2.93), (0, math.radians(-30), 0), 0.08, 30, (0.82, 1.0, 0.88), size_y=1.2)
        tag(a, "street")
    # Fills last and weak: cool sky bounce over the street, a warm under-awning bounce off the wet ground.
    f1 = area("fill_sky", c, (2.5, 2.5, 9.0), (0, 0, 0), 12, 160, (0.55, 0.62, 0.9), size_y=24)
    f1.visible_glossy = False
    tag(f1, "fill")
    f2 = area("fill_awning_bounce", c, (-1.6, 2.8, 0.25), (math.radians(180), 0, 0), 3.0, 12, WARM, size_y=7)
    f2.visible_glossy = False
    tag(f2, "fill")
    bpy.context.scene.view_settings.exposure = 0.4
    print("LIGHTS", len(ORDER), flush=True)
