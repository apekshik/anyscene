"""Imperfections pass, adapted from the repair scene's grime_layer for a wet street:
per-instance tint (Object Info > Color, so linked duplicates don't read as copies), AO crevice dirt, soot/grease
blotches, and rain-wet up-facing surfaces outside the awning (darker albedo, lower roughness).

The group's global strength lives in the node "grime_master" (a Value node inside the group), so the breakdown's
materials clip can fade all grime in with one key.
"""
import bpy

import shell as S

SKIP = ("glass", "haze", "drizzle", "drip", "skyline", "decal", "fluoro", "bulb", "neon", "lightbox", "clay", "flame",
        "steam", "water", "posters", "menu_strips", "stall_sign", "paint_", "sign_ink", "cord", "BTS")


def _mix(g, fac, a, b, blend="MIX"):
    m = g.nodes.new("ShaderNodeMix")
    m.data_type = "RGBA"
    m.blend_type = blend
    for sock, val in (("Factor", fac), ("A", a), ("B", b)):
        if isinstance(val, bpy.types.NodeSocket):
            g.links.new(val, m.inputs[sock])
        else:
            m.inputs[sock].default_value = val if not isinstance(val, tuple) or len(val) == 4 else (*val, 1)
    return m.outputs["Result"]


def _math(g, op, a, b=0.0, clamp=False):
    m = g.nodes.new("ShaderNodeMath")
    m.operation = op
    m.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if isinstance(v, bpy.types.NodeSocket):
            g.links.new(v, m.inputs[i])
        else:
            m.inputs[i].default_value = v
    return m.outputs[0]


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
    n = g.nodes
    gi, go = n.new("NodeGroupInput"), n.new("NodeGroupOutput")
    master = n.new("ShaderNodeValue")
    master.name = master.label = "grime_master"
    master.outputs[0].default_value = 1.0
    amt = _math(g, "MULTIPLY", gi.outputs["Amount"], master.outputs[0])
    oi = n.new("ShaderNodeObjectInfo")
    tint = _mix(g, master.outputs[0], (1, 1, 1, 1), oi.outputs["Color"])
    col = _mix(g, 1.0, gi.outputs["Color"], tint, "MULTIPLY")
    # AO crevice dirt.
    ao = n.new("ShaderNodeAmbientOcclusion")
    ao.samples = 8
    ao.inputs["Distance"].default_value = 0.05
    crev = _math(g, "SUBTRACT", 1.0, _math(g, "MULTIPLY", _math(g, "SUBTRACT", 1.0, ao.outputs["AO"]), amt), clamp=True)
    col = _mix(g, 1.0, col, _mix(g, crev, (0.18, 0.15, 0.11, 1), (1, 1, 1, 1)), "MULTIPLY")
    # Soot / grease blotches.
    geo = n.new("ShaderNodeNewGeometry")
    nz = n.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 6.0
    nz.inputs["Detail"].default_value = 8
    g.links.new(geo.outputs["Position"], nz.inputs["Vector"])
    rm = n.new("ShaderNodeMapRange")
    rm.inputs["From Min"].default_value, rm.inputs["From Max"].default_value = 0.55, 0.8
    g.links.new(nz.outputs["Fac"], rm.inputs["Value"])
    blot = _math(g, "MULTIPLY", _math(g, "MULTIPLY", rm.outputs["Result"], amt), 0.45, clamp=True)
    col = _mix(g, blot, col, (0.05, 0.04, 0.03, 1))
    # Rain-wet: up-facing surfaces outside the awning (world x > awning edge or y outside it).
    sep = n.new("ShaderNodeSeparateXYZ")
    g.links.new(geo.outputs["Normal"], sep.inputs[0])
    up = n.new("ShaderNodeMapRange")
    up.inputs["From Min"].default_value, up.inputs["From Max"].default_value = 0.3, 0.8
    g.links.new(sep.outputs["Z"], up.inputs["Value"])
    pos = n.new("ShaderNodeSeparateXYZ")
    g.links.new(geo.outputs["Position"], pos.inputs[0])
    a = S.AWN
    out_x = _math(g, "GREATER_THAN", pos.outputs["X"], a["x1"])
    out_y = _math(g, "MAXIMUM", _math(g, "LESS_THAN", pos.outputs["Y"], a["y0"]), _math(g, "GREATER_THAN", pos.outputs["Y"], a["y1"]))
    outside = _math(g, "MAXIMUM", out_x, out_y)
    wet = _math(g, "MULTIPLY", _math(g, "MULTIPLY", up.outputs["Result"], outside), master.outputs[0])
    col = _mix(g, _math(g, "MULTIPLY", wet, 0.35), col, (0, 0, 0, 1))
    g.links.new(col, go.inputs["Color"])
    rough = _math(g, "ADD", gi.outputs["Roughness"], _math(g, "MULTIPLY", blot, 0.25))
    rough = _math(g, "SUBTRACT", rough, _math(g, "MULTIPLY", wet, 0.55), clamp=True)
    g.links.new(rough, go.inputs["Roughness"])
    return g


def amount_for(name):
    n = name.lower()
    if any(k in n for k in ("stall_", "shelf", "prep", "kitchen", "awn", "hk_wok", "hk_kitchen", "hk_stockpot", "range")):
        return 1.3
    if any(k in n for k in ("pavement", "road", "kerb", "bldg", "far_", "fascia")):
        return 0.6
    return 0.9


def add_grime(m):
    nt = m.node_tree
    if nt is None or m.name.startswith(SKIP) or any(k in m.name for k in ("glass", "facemat", "lightbox")):
        return False
    if any(nd.type == "GROUP" and nd.node_tree and nd.node_tree.name == "grime_layer" for nd in nt.nodes):
        return False
    b = next((nd for nd in nt.nodes if nd.type == "BSDF_PRINCIPLED"), None)
    if b is None or b.inputs["Emission Strength"].is_linked or b.inputs["Emission Strength"].default_value > 0:
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


def build():
    n = sum(add_grime(m) for m in list(bpy.data.materials))
    print("GRIME on", n, "materials", flush=True)
