"""Cigarette haze: two homogeneous room layers, thin up to head height and denser under the ceiling (smoke pools there),
plus thin rising smoke curls above the hero ashtrays, animated by drifting their noise.

A noise-driven room volume made Cycles ray-march the whole 11 x 13 m box: ~22 s/frame against ~4 s without haze.
Homogeneous volumes are sampled analytically, so the room layers carry no texture; only the small curls are
heterogeneous.

Object motion blur is off on every volume object (a moving or deforming volume domain makes Cycles rebuild velocity
per frame; on the ramen scene's Mantaflow domain that cost ~290 s/frame). These are static objects with animated
textures, so there is nothing to blur anyway.
"""
import bpy
from mathutils import Vector

import layout as L
import lib

DENSITY = 0.014
CEILING_DENSITY = 0.032
LAYER_Z = 2.35


def flat_material(name, density):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    v = nt.nodes.new("ShaderNodeVolumePrincipled")
    v.inputs["Color"].default_value = (0.82, 0.8, 0.76, 1)
    v.inputs["Anisotropy"].default_value = 0.35
    k = nt.nodes.new("ShaderNodeMath")  # a plain multiply so the breakdown can key the density in
    k.operation = "MULTIPLY"
    k.inputs[0].default_value = 1.0
    k.inputs[1].default_value = density
    nt.links.new(k.outputs[0], v.inputs["Density"])
    nt.links.new(v.outputs[0], out.inputs["Volume"])
    return m


def haze_material(name, density, height_lo, height_hi, scale=0.35, curl=False):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    v = nt.nodes.new("ShaderNodeVolumePrincipled")
    v.inputs["Color"].default_value = (0.82, 0.8, 0.76, 1)
    v.inputs["Anisotropy"].default_value = 0.35
    nt.links.new(v.outputs[0], out.inputs["Volume"])
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    nt.links.new(tc.outputs["Object" if curl else "Generated"], mp.inputs["Vector"])
    # drift with time (driver on the mapping's location)
    fc = mp.inputs["Location"].driver_add("default_value", 2 if curl else 0)
    fc.driver.expression = ("frame * -0.012" if curl else "frame * 0.0006")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = scale
    nz.inputs["Detail"].default_value = 4.0
    nz.inputs["Distortion"].default_value = 0.6 if not curl else 2.5
    nt.links.new(mp.outputs[0], nz.inputs["Vector"])
    r = lib._ramp(nt, nz.outputs["Fac"], [(0.38, (0.25, 0.25, 0.25)), (0.7, (1, 1, 1))] if not curl
                  else [(0.52, (0, 0, 0)), (0.56, (1, 1, 1))])
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])
    hr = lib._ramp(nt, sep.outputs["Z"], [(height_lo, (0.35, 0.35, 0.35)), (height_hi, (1, 1, 1))] if not curl
                   else [(0.0, (1, 1, 1)), (1.0, (0, 0, 0))])
    f = lib._mix(nt, 1.0, r.outputs["Color"], hr.outputs["Color"], "MULTIPLY")
    k = nt.nodes.new("ShaderNodeMath")
    k.operation = "MULTIPLY"
    k.inputs[1].default_value = density
    sp = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(f, sp.inputs["Color"])
    nt.links.new(sp.outputs[0], k.inputs[0])
    nt.links.new(k.outputs[0], v.inputs["Density"])
    return m


def build(density=DENSITY):
    C = lib.collection("haze")
    for name, z0, z1, dn in (("haze_room", 0.0, LAYER_Z, density), ("haze_ceiling", LAYER_Z, L.H - 0.06, CEILING_DENSITY)):
        hz = lib.box(name, (0.02, 0.02, z0), (L.W - 0.02, L.D - 0.02, z1), flat_material(name, dn), C, bevel=0)
        hz.visible_shadow = False
        hz.cycles.use_motion_blur = False
    # smoke curls over the ashtrays of the composed bays
    n = 0
    for o in bpy.context.scene.objects:
        if o.get("prop_id") not in ("mc_ashtray_glass",) or n >= 3:
            continue
        lo = o.matrix_world @ Vector(o.bound_box[0])
        hi = o.matrix_world @ Vector(o.bound_box[6])
        c = (lo + hi) / 2
        b = lib.box(f"smoke_curl_{n}", (c.x - 0.09, c.y - 0.09, hi.z), (c.x + 0.09, c.y + 0.09, hi.z + 0.75),
                    haze_material(f"smoke_curl_{n}", 6.0, 0, 1, scale=9.0, curl=True), C, bevel=0)
        b.visible_shadow = False
        b.cycles.use_motion_blur = False
        n += 1
    sc = bpy.context.scene
    sc.cycles.volume_step_rate = 4.0
    sc.cycles.volume_max_steps = 256
    print("HAZE", density, "curls", n, flush=True)
