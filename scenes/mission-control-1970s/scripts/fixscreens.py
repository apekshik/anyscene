"""Screens: CRT phosphor shader on every CRT_SLOT_* patch (from fixes.py), the ceiling TVs' b/w pad feed, and the
three emissive wall-display panels. Pages come from screens.py (refs/mission-control-1970s/tex/screens/).

CRT page per instance = (ob["screen_idx"] + 3 * slot) mod 8, read through an OBJECT attribute, so linked duplicates of
one console mesh still show different pages. Scanlines, a soft edge falloff and a faint phosphor floor are procedural.
"""
import os

import bpy

import layout as L
import lib
from lib import sock

SCR = os.path.join(lib.ROOT, "refs", "mission-control-1970s", "tex", "screens")
PAGES = ["crt_telemetry", "crt_trajectory", "crt_events", "crt_guidance", "crt_power", "crt_comms", "crt_orbit", "crt_amber_status"]
CRT_STRENGTH = 3.0
WALL_STRENGTH = 2.2


def _math(nt, op, a, b=None, c=None):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    for i, v in enumerate((a, b, c)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def _edge(nt, uvsep, power=8.0):
    """1 in the middle, falling off at the edges of the 0..1 UV square (a CRT's darker corners)."""
    out = None
    for ax in ("X", "Y"):
        c = _math(nt, "MULTIPLY_ADD", uvsep.outputs[ax], 2.0, -1.0)
        p = _math(nt, "POWER", _math(nt, "ABSOLUTE", c), power)
        e = _math(nt, "SUBTRACT", 1.0, p)
        out = e if out is None else _math(nt, "MULTIPLY", out, e)
    return _math(nt, "MAXIMUM", out, 0.0)


def crt_material(name, slot=0, tv=False, strength=CRT_STRENGTH):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(b.outputs[0], out.inputs[0])
    b.inputs["Base Color"].default_value = (0.012, 0.016, 0.014, 1)
    b.inputs["Roughness"].default_value = 0.3
    b.inputs["Coat Weight"].default_value = 1.0
    b.inputs["Coat Roughness"].default_value = 0.06
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs["Vector"])
    if tv:  # black-and-white pad camera feed: the launch-pad backdrop, desaturated and blue-ish
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(os.path.join(lib.ROOT, "refs", "mission-control-1970s", "tex", "launch_pad_0.png"), check_existing=True)
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Location"].default_value = (0.3, 0.1, 0)
        mp.inputs["Scale"].default_value = (0.4, 0.75, 1)
        nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
        nt.links.new(mp.outputs[0], t.inputs["Vector"])
        hsv = nt.nodes.new("ShaderNodeHueSaturation")
        hsv.inputs["Saturation"].default_value = 0.0
        hsv.inputs["Value"].default_value = 2.2
        nt.links.new(t.outputs["Color"], hsv.inputs["Color"])
        col = lib._mix(nt, 1.0, hsv.outputs["Color"], (0.75, 0.85, 1.0), "MULTIPLY")
        col = lib._mix(nt, 1.0, col, (0.03, 0.035, 0.04), "ADD")
    else:
        at = nt.nodes.new("ShaderNodeAttribute")
        at.attribute_type = "OBJECT"
        at.attribute_name = "screen_idx"
        idx = _math(nt, "FLOORED_MODULO", _math(nt, "ADD", at.outputs["Fac"], 3 * slot), len(PAGES))
        col = None
        for i, page in enumerate(PAGES):
            t = nt.nodes.new("ShaderNodeTexImage")
            t.image = bpy.data.images.load(os.path.join(SCR, page + ".png"), check_existing=True)
            t.extension = "EXTEND"
            nt.links.new(tc.outputs["UV"], t.inputs["Vector"])
            if col is None:
                col = t.outputs["Color"]
                continue
            hit = _math(nt, "COMPARE", idx, float(i), 0.5)
            col = lib._mix(nt, hit, col, t.outputs["Color"])
        col = lib._mix(nt, 1.0, col, (0.006, 0.03, 0.012), "ADD")  # phosphor never quite black
    # scanlines (~240 visible lines) and the darker edges of the tube
    sl = _math(nt, "SINE", _math(nt, "MULTIPLY", sep.outputs["Y"], 2 * 3.14159 * 240))
    sl = _math(nt, "MULTIPLY_ADD", sl, 0.14, 0.86)
    k = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", sl, _edge(nt, sep, 6.0)), strength)
    nt.links.new(col, b.inputs["Emission Color"])
    nt.links.new(k, b.inputs["Emission Strength"])
    return m


def wall_material(name, page, strength=WALL_STRENGTH):
    """Rear-projection panel: the page, a slight hotspot falloff, a matte dark screen surface."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(b.outputs[0], out.inputs[0])
    b.inputs["Base Color"].default_value = (0.02, 0.022, 0.024, 1)
    b.inputs["Roughness"].default_value = 0.55
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs["Vector"])
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(os.path.join(SCR, page + ".png"), check_existing=True)
    t.extension = "EXTEND"
    nt.links.new(tc.outputs["UV"], t.inputs["Vector"])
    col = lib._mix(nt, 1.0, t.outputs["Color"], (0.004, 0.012, 0.01), "ADD")
    k = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY_ADD", _edge(nt, sep, 2.0), 0.25, 0.75), strength)
    nt.links.new(col, b.inputs["Emission Color"])
    nt.links.new(k, b.inputs["Emission Strength"])
    return m


def build():
    done = {}
    for o in bpy.context.scene.objects:
        if o.type != "MESH":
            continue
        pid = o.get("prop_id", "")
        for s in o.material_slots:
            mt = s.material
            if not mt or not mt.name.startswith("CRT_SLOT_"):
                continue
            if mt.name in done:
                continue
            slot = int(mt.name.split(".")[0].rsplit("_", 1)[1])
            crt_material(mt.name, slot, tv=pid == "mc_tv_ceiling", strength=1.6 if pid == "mc_tv_ceiling" else CRT_STRENGTH)
            done[mt.name] = pid
    for name, *_ in L.DISP_PANELS:
        p = bpy.data.objects.get(f"disp_{name}")
        if p:
            p.data.materials.clear()
            p.data.materials.append(wall_material(f"wall_{name}", name))
    print("SCREENS", len(done), "CRT materials:", done, flush=True)
