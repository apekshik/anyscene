"""Material pass on generated props: per-instance tint, a shared grime layer (AO crevice dirt + top dust + nicotine film),
lamp glow on console/equipment indicator lamps, decals (coffee rings, cigarette burns).

grime_layer group: (Color, Factor) -> Color. Factor is 1 in the scene; the breakdown fades it 0 -> 1.
Lamp glow: emission = albedo where the albedo is a saturated bright lamp colour (HSV mask), switched per lamp by a
noise keyed on the object's random value, so linked duplicates don't light identical buttons. Dense generated meshes get
emission_sampling = NONE (texture emission would make every triangle a light).
"""
import os
import random

import bpy
from mathutils import Vector

import lib

TEX = os.path.join(lib.ROOT, "refs", "mission-control-1970s", "tex")
GLOW = {"mc_console_crt", "mc_console_twin", "mc_console_scope", "mc_console_lamps", "mc_console_comms", "mc_console_end",
        "mc_mainframe_rack", "mc_tape_drive", "mc_equipment_rack", "mc_line_printer", "mc_met_clock", "mc_calculator",
        "mc_desk_phone", "mc_strip_recorder", "mc_reel_recorder", "mc_coffee_maker", "mc_intercom"}
GLOW_K = {"mc_met_clock": 18.0, "mc_calculator": 6.0, "mc_coffee_maker": 4.0}
rng = random.Random(3)


def grime_group():
    g = bpy.data.node_groups.get("grime_layer")
    if g:
        return g
    g = bpy.data.node_groups.new("grime_layer", "ShaderNodeTree")
    g.interface.new_socket("Color", in_out="INPUT", socket_type="NodeSocketColor")
    g.interface.new_socket("Factor", in_out="INPUT", socket_type="NodeSocketFloat")
    g.interface.new_socket("Color", in_out="OUTPUT", socket_type="NodeSocketColor")
    nt = g
    gi = nt.nodes.new("NodeGroupInput")
    go = nt.nodes.new("NodeGroupOutput")
    tint = nt.nodes.new("ShaderNodeObjectInfo")
    c = lib._mix(nt, 1.0, gi.outputs[0], tint.outputs["Color"], "MULTIPLY")
    ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
    ao.samples = 8
    ao.inputs["Distance"].default_value = 0.04
    crev = lib._ramp(nt, ao.outputs["AO"], [(0.35, (1, 1, 1)), (0.9, (0, 0, 0))])
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = lib._noise(nt, 18.0, 6, tc.outputs["Object"])
    nzr = lib._ramp(nt, nz.outputs["Fac"], [(0.35, (0.3, 0.3, 0.3)), (0.7, (1, 1, 1))])
    dirt = lib._mix(nt, 1.0, crev.outputs["Color"], nzr.outputs["Color"], "MULTIPLY")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sz = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], sz.inputs["Vector"])
    top = lib._ramp(nt, sz.outputs["Z"], [(0.6, (0, 0, 0)), (0.95, (1, 1, 1))])
    dust = lib._mix(nt, 1.0, top.outputs["Color"], nzr.outputs["Color"], "MULTIPLY")
    f1 = nt.nodes.new("ShaderNodeMath")
    f1.operation = "MULTIPLY"
    nt.links.new(gi.outputs[1], f1.inputs[0])
    f1.inputs[1].default_value = 0.55
    sepd = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(dirt, sepd.inputs["Color"])
    fd = nt.nodes.new("ShaderNodeMath")
    fd.operation = "MULTIPLY"
    nt.links.new(sepd.outputs[0], fd.inputs[0])
    nt.links.new(f1.outputs[0], fd.inputs[1])
    c2 = lib._mix(nt, fd.outputs[0], c, (0.06, 0.05, 0.035))
    seps = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(dust, seps.inputs["Color"])
    fs = nt.nodes.new("ShaderNodeMath")
    fs.operation = "MULTIPLY"
    nt.links.new(seps.outputs[0], fs.inputs[0])
    fs2 = nt.nodes.new("ShaderNodeMath")
    fs2.operation = "MULTIPLY"
    nt.links.new(gi.outputs[1], fs2.inputs[0])
    fs2.inputs[1].default_value = 0.22
    fs3 = nt.nodes.new("ShaderNodeMath")
    fs3.operation = "MULTIPLY"
    nt.links.new(fs.outputs[0], fs3.inputs[0])
    nt.links.new(fs2.outputs[0], fs3.inputs[1])
    c3 = lib._mix(nt, fs3.outputs[0], c2, (0.42, 0.4, 0.36))
    # nicotine film: everything a touch warmer and darker
    fn = nt.nodes.new("ShaderNodeMath")
    fn.operation = "MULTIPLY"
    nt.links.new(gi.outputs[1], fn.inputs[0])
    fn.inputs[1].default_value = 0.12
    c4 = lib._mix(nt, fn.outputs[0], c3, (0.55, 0.45, 0.28), "MULTIPLY")
    nt.links.new(c4, go.inputs[0])
    return g


def base_color_source(m):
    b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if b is None:
        return None, None
    s = b.inputs["Base Color"]
    return b, (s.links[0].from_socket if s.links else None)


def add_grime(m, factor=1.0):
    if m.get("grimed"):
        return
    b, src = base_color_source(m)
    if b is None:
        return
    nt = m.node_tree
    g = nt.nodes.new("ShaderNodeGroup")
    g.node_tree = grime_group()
    g.name = g.label = "grime"
    if src is not None:
        nt.links.new(src, g.inputs["Color"])
    else:
        g.inputs["Color"].default_value = b.inputs["Base Color"].default_value
    g.inputs["Factor"].default_value = factor
    nt.links.new(g.outputs[0], b.inputs["Base Color"])
    m["grimed"] = True


def add_glow(m, k=3.0):
    if m.get("glow"):
        return
    b, src = base_color_source(m)
    if b is None or src is None:
        return
    nt = m.node_tree
    hsv = nt.nodes.new("ShaderNodeSeparateColor")
    hsv.mode = "HSV"
    nt.links.new(src, hsv.inputs["Color"])
    sm = lib._ramp(nt, hsv.outputs[1], [(0.42, (0, 0, 0)), (0.62, (1, 1, 1))])
    vm = lib._ramp(nt, hsv.outputs[2], [(0.5, (0, 0, 0)), (0.75, (1, 1, 1))])
    mask = lib._mix(nt, 1.0, sm.outputs["Color"], vm.outputs["Color"], "MULTIPLY")
    # per-lamp on/off: cellular noise in UV space, offset by the object's random value
    oi = nt.nodes.new("ShaderNodeObjectInfo")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    add = nt.nodes.new("ShaderNodeVectorMath")
    add.operation = "ADD"
    nt.links.new(tc.outputs["UV"], add.inputs[0])
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = 97.0
    nt.links.new(oi.outputs["Random"], mul.inputs[0])
    nt.links.new(mul.outputs[0], comb.inputs["X"])
    nt.links.new(comb.outputs[0], add.inputs[1])
    vo = nt.nodes.new("ShaderNodeTexVoronoi")
    vo.inputs["Scale"].default_value = 140.0
    vo.feature = "F1"
    nt.links.new(add.outputs[0], vo.inputs["Vector"])
    sw = lib._ramp(nt, vo.outputs["Color"], [(0.3, (0.08, 0.08, 0.08)), (0.32, (1, 1, 1))])
    mask = lib._mix(nt, 1.0, mask, sw.outputs["Color"], "MULTIPLY")
    em = lib._mix(nt, 1.0, src, mask, "MULTIPLY")
    nt.links.new(em, b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = k
    m.cycles.emission_sampling = "NONE"
    m["glow"] = True


GLASS_MASK = {"mc_ashtray_glass"}  # generators bake glass as opaque grey (not the cooler: its cream enamel would match too)


def add_glass(m):
    """Glass from an opaque generated texture: low-saturation light texels (the glass body) become transmissive, the
    butts/ash/metal (saturated or dark) stay opaque."""
    if m.get("glass"):
        return
    b, src = base_color_source(m)
    if b is None or src is None:
        return
    nt = m.node_tree
    hsv = nt.nodes.new("ShaderNodeSeparateColor")
    hsv.mode = "HSV"
    nt.links.new(src, hsv.inputs["Color"])
    s = lib._ramp(nt, hsv.outputs[1], [(0.12, (1, 1, 1)), (0.22, (0, 0, 0))])
    v = lib._ramp(nt, hsv.outputs[2], [(0.4, (0, 0, 0)), (0.55, (1, 1, 1))])
    mask = lib._mix(nt, 1.0, s.outputs["Color"], v.outputs["Color"], "MULTIPLY")
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(mask, sep.inputs["Color"])
    nt.links.new(sep.outputs[0], b.inputs["Transmission Weight"])
    rr = nt.nodes.new("ShaderNodeMapRange")
    rr.inputs["To Min"].default_value = 0.5
    rr.inputs["To Max"].default_value = 0.06
    nt.links.new(sep.outputs[0], rr.inputs["Value"])
    nt.links.new(rr.outputs["Result"], b.inputs["Roughness"])
    b.inputs["IOR"].default_value = 1.5
    m["glass"] = True


def decal_material(name, path):
    """White-background stain image: colour from the image, alpha = 1 - luminance."""
    m, nt = lib._new(name)
    if nt is None:
        return m
    b = nt.nodes["Principled BSDF"]
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(path, check_existing=True)
    t.extension = "CLIP"
    nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
    inv = nt.nodes.new("ShaderNodeInvert")
    bw = nt.nodes.new("ShaderNodeRGBToBW")
    nt.links.new(t.outputs["Color"], bw.inputs["Color"])
    nt.links.new(bw.outputs[0], inv.inputs["Color"])
    r = lib._ramp(nt, inv.outputs["Color"], [(0.05, (0, 0, 0)), (0.5, (1, 1, 1))])
    a = nt.nodes.new("ShaderNodeMath")
    a.operation = "MULTIPLY"
    nt.links.new(r.outputs["Color"], a.inputs[0])
    a.inputs[1].default_value = 0.85
    a.name = "decal_alpha"
    nt.links.new(a.outputs[0], b.inputs["Alpha"])
    b.inputs["Roughness"].default_value = 0.6
    m.surface_render_method = "DITHERED"
    return m


def decals():
    C = lib.collection("decals")
    mats = [decal_material("decal_coffee", os.path.join(TEX, "decal_coffee_0.png")),
            decal_material("decal_burns", os.path.join(TEX, "decal_burns_0.png"))]
    dg = bpy.context.evaluated_depsgraph_get()
    targets = [o for o in bpy.context.scene.objects if o.get("prop_id", "").startswith("mc_console") and o.get("bay")]
    n = 0
    for o in targets:
        lo = Vector(o.bound_box[0])
        mw = o.matrix_world
        bb = [mw @ Vector(c) for c in o.bound_box]
        x0, x1 = min(p.x for p in bb), max(p.x for p in bb)
        y0 = min(p.y for p in bb)
        for k in range(rng.randint(1, 3)):
            x, y = rng.uniform(x0 + 0.15, x1 - 0.15), y0 + rng.uniform(0.05, 0.3)
            ok, loc, nrm, _i, hit, _m = bpy.context.scene.ray_cast(dg, Vector((x, y, min(p.z for p in bb) + 0.95)), Vector((0, 0, -1)))
            if not ok or hit is not o or nrm.z < 0.9:
                continue
            s = rng.uniform(0.12, 0.22)
            p = lib.plane(f"decal_{n}", (x, y, loc.z + 0.0006), s, s, "Z", rng.choice(mats), C)
            p.rotation_euler = (0, 0, rng.uniform(0, 6.28))
            p.visible_shadow = False
            n += 1
    # cigarette burns on the carpet near the chairs
    for k in range(10):
        x, y = rng.uniform(1.8, 9.3), rng.choice([8.9, 6.0, 3.0]) + rng.uniform(-0.6, 0.4)
        ok, loc, nrm, _i, hit, _m = bpy.context.scene.ray_cast(dg, Vector((x, y, 1.0)), Vector((0, 0, -1)))
        if ok and hit.name.startswith("floor_t"):
            s = rng.uniform(0.25, 0.4)
            p = lib.plane(f"decal_floor_{k}", (x, y, loc.z + 0.0008), s, s, "Z", mats[1], C)
            p.rotation_euler = (0, 0, rng.uniform(0, 6.28))
            p.visible_shadow = False
    print("DECALS", n, flush=True)


def build(factor=1.0):
    seen = set()
    for o in bpy.context.scene.objects:
        pid = o.get("prop_id")
        if not pid or o.type != "MESH":
            continue
        for s in o.material_slots:
            m = s.material
            if not m or m.name in seen or m.name.startswith("CRT_SLOT_") or m.name.startswith("crt_"):
                continue
            seen.add(m.name)
            add_grime(m, factor)
            if pid in GLASS_MASK:
                add_glass(m)
            if pid in GLOW:
                add_glow(m, GLOW_K.get(pid, 3.0))
            elif len(o.data.polygons) > 20000:
                m.cycles.emission_sampling = "NONE"
    decals()
    print("GRIME", len(seen), "materials", flush=True)
