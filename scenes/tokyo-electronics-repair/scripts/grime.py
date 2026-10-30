"""Imperfections pass: grime and wear across every surface (the video's "realism lives in the imperfections").

blender -b <in.blend> --python scenes/tokyo-electronics-repair/scripts/grime.py -- <out.blend>
- grime_layer node group inserted before Base Color / Roughness of every surface material:
  per-instance tint (Object Info > Color), dust on up-facing surfaces broken up by noise, AO crevice dirt,
  dust raises roughness. Amount per material family.
- floor: trodden paths (door -> counter, the bench aisle, behind the counter), scuffs, dust along the walls.
- bench mat: flux burns, rosin stains. Storefront glass + CRT faces: fingerprint / smudge roughness.
- ceiling: water-stain rings. Idempotent (skips materials already carrying the group).
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(__file__))
import lib  # noqa: E402

out = os.path.abspath(sys.argv[sys.argv.index("--") + 1])
SKIP = ("glass", "haze", "rain", "street_backdrop", "decal", "fluoro", "crt", "vending", "lens", "clay", "puddle", "led", "vfd",
        "bulb", "tube", "backroom", "wire", "umbrella", "amber", "chrome", "copper", "solder", "brass", "aframe_bulb")


def group():
    g = bpy.data.node_groups.get("grime_layer")
    if g:
        return g
    g = bpy.data.node_groups.new("grime_layer", "ShaderNodeTree")
    g.interface.new_socket("Color", in_out="INPUT", socket_type="NodeSocketColor")
    g.interface.new_socket("Roughness", in_out="INPUT", socket_type="NodeSocketFloat")
    g.interface.new_socket("Amount", in_out="INPUT", socket_type="NodeSocketFloat")
    g.interface.new_socket("Color", in_out="OUTPUT", socket_type="NodeSocketColor")
    g.interface.new_socket("Roughness", in_out="OUTPUT", socket_type="NodeSocketFloat")
    n, L = g.nodes, g.links
    gi, go = n.new("NodeGroupInput"), n.new("NodeGroupOutput")
    oi = n.new("ShaderNodeObjectInfo")
    tinted = lib._mix(g, 1.0, gi.outputs[0], oi.outputs["Color"], "MULTIPLY")
    geo = n.new("ShaderNodeNewGeometry")
    sep = n.new("ShaderNodeSeparateXYZ")
    L.new(geo.outputs["Normal"], sep.inputs["Vector"])
    up = n.new("ShaderNodeMapRange")
    up.inputs["From Min"].default_value, up.inputs["From Max"].default_value = 0.55, 0.95
    L.new(sep.outputs["Z"], up.inputs["Value"])
    nz = n.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 9.0
    nz.inputs["Detail"].default_value = 8
    L.new(geo.outputs["Position"], nz.inputs["Vector"])
    nr = lib._ramp(g, nz.outputs["Fac"], [(0.35, (0.25, 0.25, 0.25)), (0.7, (1, 1, 1))])
    dust = n.new("ShaderNodeMath")
    dust.operation = "MULTIPLY"
    L.new(up.outputs["Result"], dust.inputs[0])
    L.new(nr.outputs["Color"], dust.inputs[1])
    dust2 = n.new("ShaderNodeMath")
    dust2.operation = "MULTIPLY"
    L.new(dust.outputs[0], dust2.inputs[0])
    L.new(gi.outputs[2], dust2.inputs[1])
    dust3 = n.new("ShaderNodeMath")
    dust3.operation = "MULTIPLY"
    dust3.use_clamp = True
    dust3.inputs[1].default_value = 0.55
    L.new(dust2.outputs[0], dust3.inputs[0])
    dusty = lib._mix(g, dust3.outputs[0], tinted, (0.4, 0.38, 0.34))
    ao = n.new("ShaderNodeAmbientOcclusion")
    ao.samples = 8
    ao.inputs["Distance"].default_value = 0.06
    crev = n.new("ShaderNodeMapRange")  # AO 1 -> 1, AO 0 -> 1 - 0.55 * amount
    L.new(ao.outputs["AO"], crev.inputs["Value"])
    lo = n.new("ShaderNodeMath")
    lo.operation = "MULTIPLY_ADD"
    lo.inputs[1].default_value = -0.55
    lo.inputs[2].default_value = 1.0
    L.new(gi.outputs[2], lo.inputs[0])
    L.new(lo.outputs[0], crev.inputs["To Min"])
    crev.inputs["To Max"].default_value = 1.0
    dirty = lib._mix(g, 1.0, dusty, crev.outputs["Result"], "MULTIPLY")
    L.new(dirty, go.inputs[0])
    rr = n.new("ShaderNodeMapRange")
    L.new(dust3.outputs[0], rr.inputs["Value"])
    rr.inputs["From Max"].default_value = 0.55
    L.new(gi.outputs[1], rr.inputs["To Min"])
    rr.inputs["To Max"].default_value = 0.9
    L.new(rr.outputs["Result"], go.inputs[1])
    return g


def amount_for(name):
    n = name.lower()
    if any(k in n for k in ("shelf_steel", "fixture", "conduit", "cabinet", "drawer")):
        return 1.3
    if any(k in n for k in ("card", "bin_", "crate", "paper", "tags", "sticky", "flyer", "price", "poster", "calendar", "label")):
        return 0.45
    if any(k in n for k in ("bench_wood", "esd", "floor", "wall", "ceiling", "pegboard", "door")):
        return 0.5
    return 1.0


def add_grime(m):
    nt = m.node_tree
    if nt is None or any(nd.type == "GROUP" and nd.node_tree and nd.node_tree.name == "grime_layer" for nd in nt.nodes):
        return False
    b = next((nd for nd in nt.nodes if nd.type == "BSDF_PRINCIPLED"), None)
    if b is None:
        return False
    if b.inputs["Emission Strength"].default_value > 0 or b.inputs["Emission Strength"].is_linked:
        return False
    if b.inputs["Transmission Weight"].default_value > 0.5:
        return False
    gn = nt.nodes.new("ShaderNodeGroup")
    gn.node_tree = group()
    gn.inputs["Amount"].default_value = amount_for(m.name)
    for sock, gi, go in (("Base Color", "Color", 0), ("Roughness", "Roughness", 1)):
        s = b.inputs[sock]
        if s.is_linked:
            nt.links.new(s.links[0].from_socket, gn.inputs[gi])
        else:
            gn.inputs[gi].default_value = s.default_value
        nt.links.new(gn.outputs[go], s)
    return True


def wrap_base(m, build):
    """Insert extra colour/roughness logic for one specific material: build(nt, color_socket, rough_socket) -> (color, rough)."""
    nt = m.node_tree
    if m.get("wear"):
        return
    b = next(nd for nd in nt.nodes if nd.type == "BSDF_PRINCIPLED")
    cs = b.inputs["Base Color"].links[0].from_socket if b.inputs["Base Color"].is_linked else None
    rs = b.inputs["Roughness"].links[0].from_socket if b.inputs["Roughness"].is_linked else None
    if cs is None:
        rgb = nt.nodes.new("ShaderNodeRGB")
        rgb.outputs[0].default_value = b.inputs["Base Color"].default_value
        cs = rgb.outputs[0]
    if rs is None:
        v = nt.nodes.new("ShaderNodeValue")
        v.outputs[0].default_value = b.inputs["Roughness"].default_value
        rs = v.outputs[0]
    col, rough = build(nt, cs, rs)
    if col is not None:
        nt.links.new(col, b.inputs["Base Color"])
    if rough is not None:
        nt.links.new(rough, b.inputs["Roughness"])
    m["wear"] = True


def band(nt, sep_x, lo, hi, soft=0.15):
    """1 inside [lo, hi] along one coordinate, soft edges."""
    a = nt.nodes.new("ShaderNodeMapRange")
    a.inputs["From Min"].default_value, a.inputs["From Max"].default_value = lo - soft, lo + soft
    nt.links.new(sep_x, a.inputs["Value"])
    b = nt.nodes.new("ShaderNodeMapRange")
    b.inputs["From Min"].default_value, b.inputs["From Max"].default_value = hi + soft, hi - soft
    nt.links.new(sep_x, b.inputs["Value"])
    m = nt.nodes.new("ShaderNodeMath")
    m.operation = "MULTIPLY"
    nt.links.new(a.outputs["Result"], m.inputs[0])
    nt.links.new(b.outputs["Result"], m.inputs[1])
    return m.outputs[0]


def math(nt, op, a, b=None):
    m = nt.nodes.new("ShaderNodeMath")
    m.operation = op
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            m.inputs[i].default_value = v
        else:
            nt.links.new(v, m.inputs[i])
    return m.outputs[0]


def floor_build(nt, cs, rs):
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sep.inputs["Vector"])
    X, Y = sep.outputs["X"], sep.outputs["Y"]
    p1 = math(nt, "MULTIPLY", band(nt, X, 1.55, 2.7), band(nt, Y, -0.5, 2.4))        # door -> counter
    p2 = math(nt, "MULTIPLY", band(nt, X, 0.85, 1.55), band(nt, Y, 1.2, 5.9))        # along the bench
    p3 = math(nt, "MULTIPLY", band(nt, X, 0.9, 3.6), band(nt, Y, 2.25, 2.95))        # behind the counter
    p4 = math(nt, "MULTIPLY", band(nt, X, 2.3, 3.4), band(nt, Y, 4.5, 6.5))          # to the back door
    path = math(nt, "MAXIMUM", math(nt, "MAXIMUM", p1, p2), math(nt, "MAXIMUM", p3, p4))
    nz = lib._noise(nt, 2.5, 6, geo.outputs["Position"])
    pn = math(nt, "MULTIPLY", path, math(nt, "MULTIPLY_ADD", nz.outputs["Fac"], 1.2) if False else nz.outputs["Fac"])
    pn = math(nt, "MULTIPLY", pn, 1.4)
    # scuffs: thin dark streaks, stretched along y
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (30, 3, 1)
    nt.links.new(geo.outputs["Position"], mp.inputs["Vector"])
    sn = lib._noise(nt, 1.0, 3, mp.outputs["Vector"])
    scuff = lib._ramp(nt, sn.outputs["Fac"], [(0.62, (0, 0, 0)), (0.7, (1, 1, 1))])
    scuff = math(nt, "MULTIPLY", scuff.outputs["Color"], math(nt, "ADD", path, 0.25))
    # dust along the walls
    wall = math(nt, "MAXIMUM", math(nt, "MAXIMUM", band(nt, X, -1, 0.15, 0.1), band(nt, X, 4.05, 5, 0.1)), band(nt, Y, 6.3, 8, 0.12))
    col = lib._mix(nt, math(nt, "MULTIPLY", pn, 0.55), cs, (0.06, 0.055, 0.05), "MULTIPLY")
    col = lib._mix(nt, math(nt, "MULTIPLY", scuff, 0.6), col, (0.03, 0.03, 0.03))
    col = lib._mix(nt, math(nt, "MULTIPLY", wall, 0.45), col, (0.42, 0.4, 0.36))
    rough = math(nt, "SUBTRACT", rs, math(nt, "MULTIPLY", pn, 0.3))
    rough = math(nt, "ADD", rough, math(nt, "MULTIPLY", wall, 0.3))
    return col, rough


def mat_burns(nt, cs, rs):
    tc = nt.nodes.new("ShaderNodeTexCoord")
    vo = nt.nodes.new("ShaderNodeTexVoronoi")
    vo.inputs["Scale"].default_value = 30
    nt.links.new(tc.outputs["Object"], vo.inputs["Vector"])
    burn = lib._ramp(nt, vo.outputs["Distance"], [(0.0, (1, 1, 1)), (0.09, (0, 0, 0))])
    keep = lib._noise(nt, 4, 3, tc.outputs["Object"])
    km = lib._ramp(nt, keep.outputs["Fac"], [(0.55, (0, 0, 0)), (0.6, (1, 1, 1))])
    b = math(nt, "MULTIPLY", burn.outputs["Color"], km.outputs["Color"])
    st = lib._noise(nt, 6, 6, tc.outputs["Object"])
    stain = lib._ramp(nt, st.outputs["Fac"], [(0.58, (0, 0, 0)), (0.68, (1, 1, 1))])
    col = lib._mix(nt, math(nt, "MULTIPLY", stain.outputs["Color"], 0.6), cs, (0.22, 0.12, 0.04))
    col = lib._mix(nt, b, col, (0.015, 0.01, 0.005))
    rough = math(nt, "SUBTRACT", rs, math(nt, "MULTIPLY", stain.outputs["Color"], 0.25))
    return col, rough


def smudge_rough(base_lo, base_hi, scale=5.0):
    def build(nt, cs, rs):
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        nz = lib._noise(nt, scale, 10, geo.outputs["Position"])
        r = lib._ramp(nt, nz.outputs["Fac"], [(0.45, (0, 0, 0)), (0.75, (1, 1, 1))])
        vo = nt.nodes.new("ShaderNodeTexVoronoi")  # fingerprint-sized blobs
        vo.inputs["Scale"].default_value = scale * 18
        nt.links.new(geo.outputs["Position"], vo.inputs["Vector"])
        fp = lib._ramp(nt, vo.outputs["Distance"], [(0.0, (1, 1, 1)), (0.25, (0, 0, 0))])
        mask = math(nt, "MAXIMUM", r.outputs["Color"], math(nt, "MULTIPLY", fp.outputs["Color"], r.outputs["Color"]))
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = base_lo, base_hi
        nt.links.new(mask, mr.inputs["Value"])
        return None, mr.outputs["Result"]
    return build


def ceiling_stains(nt, cs, rs):
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    nz = lib._noise(nt, 0.55, 4, geo.outputs["Position"])
    ring = lib._ramp(nt, nz.outputs["Fac"], [(0.655, (1, 1, 1)), (0.665, (0.45, 0.33, 0.2)), (0.675, (0.8, 0.68, 0.5)), (0.75, (0.88, 0.8, 0.66)), (0.8, (1, 1, 1))])
    return lib._mix(nt, 1.0, cs, ring.outputs["Color"], "MULTIPLY"), None


n = 0
for m in bpy.data.materials:
    name = m.name.lower()
    if any(k in name for k in SKIP):
        continue
    if add_grime(m):
        n += 1
for name, fn in (("floor_vinyl", floor_build), ("esd_mat", mat_burns), ("ceiling_tile", ceiling_stains),
                 ("rain_glass", smudge_rough(0.02, 0.22, 4.0)), ("scope_crt", smudge_rough(0.06, 0.4, 25.0)),
                 ("tv_crt", smudge_rough(0.06, 0.4, 20.0)), ("case_glass", smudge_rough(0.03, 0.25, 12.0))):
    m = bpy.data.materials.get(name)
    if m:
        wrap_base(m, fn)
# CRT TVs: scanlines + a slow rolling bar on the no-signal glow (an evenly lit blue rectangle reads as a flat card)
tv = bpy.data.materials.get("tv_crt")
if tv and not tv.get("scan"):
    nt = tv.node_tree
    b = next(nd for nd in nt.nodes if nd.type == "BSDF_PRINCIPLED")
    src = b.inputs["Emission Strength"].links[0].from_socket
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs["Vector"])
    lines = math(nt, "MULTIPLY_ADD", math(nt, "SINE", math(nt, "MULTIPLY", sep.outputs["Y"], 900.0)), 0.25)
    lines.node.inputs[1].default_value, lines.node.inputs[2].default_value = 0.25, 0.75
    fr = nt.nodes.new("ShaderNodeValue")  # rolling bar position, keyed below
    roll = math(nt, "FRACT", math(nt, "ADD", sep.outputs["Y"], fr.outputs[0]))
    bar = lib._ramp(nt, roll, [(0.0, (1.35, 1.35, 1.35)), (0.12, (1, 1, 1)), (1.0, (1, 1, 1))])
    # soft vignette: sin(pi x) * sin(pi y) (a product of triangle waves shows diamond-shaped bands)
    edge = math(nt, "MULTIPLY", math(nt, "SINE", math(nt, "MULTIPLY", sep.outputs["X"], 3.14159)), math(nt, "SINE", math(nt, "MULTIPLY", sep.outputs["Y"], 3.14159)))
    vign = math(nt, "POWER", math(nt, "MAXIMUM", edge, 0.0), 0.3)
    k = math(nt, "MULTIPLY", math(nt, "MULTIPLY", lines, bar.outputs["Color"]), vign)
    nt.links.new(math(nt, "MULTIPLY", src, k), b.inputs["Emission Strength"])
    fr.outputs[0].default_value = 0.0
    fr.outputs[0].keyframe_insert("default_value", frame=1)
    fr.outputs[0].default_value = -1.0
    fr.outputs[0].keyframe_insert("default_value", frame=97)
    tv["scan"] = True
print("grime on", n, "materials")
bpy.ops.wm.save_as_mainfile(filepath=out)
