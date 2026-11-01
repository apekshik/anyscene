"""Atmosphere: wok/stockpot steam, street haze, drizzle, drips off the awning edge.

Steam is a procedural volume (4D noise advected upward inside a plume-shaped falloff), not Mantaflow: the walkthroughs
are long uncut takes (500+ frames), and a Mantaflow cache that long would need a bake far past the 10-minute GPU-queue
budget. Procedural plumes need no cache and no motion-blur special case. They roll out under the awning toward the street.
"""
import math

import bpy
from mathutils import Matrix

import shell as S
from lib import L, box, coll, cylinder, mathn, new_mat, noise, ramp, texcoord

END = 900  # long enough for the longest take


def _vol_box(name, lo, hi, c, mat):
    o = box(name, lo, hi, c, mat, 0)
    o.visible_shadow = False
    o.visible_glossy = False
    o["no_support"] = True
    o.cycles.use_motion_blur = False  # static volume: no velocity motion (the ramen 290 s/frame trap)
    return o


def m_plume(name, rise=0.05, strength=1.0, lean=0.35):
    """Plume in a box's generated space: narrow at the bottom (z=0), widening and drifting toward +X (the street) as it
    rises, flattened under the awning at the top. Density from upward-scrolling 4D noise."""
    m, nt = new_mat(name)
    if not nt:
        return m
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    gen = texcoord(nt, "Generated")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    L(nt, gen, sep.inputs[0])
    z = sep.outputs["Z"]
    # Plume centre leans toward +X with height (the cook's side is open, air drifts out to the street).
    cx = mathn(nt, "ADD", 0.3, mathn(nt, "MULTIPLY", mathn(nt, "POWER", z, 1.5), lean))
    dx = mathn(nt, "SUBTRACT", sep.outputs["X"], cx)
    dy = mathn(nt, "SUBTRACT", sep.outputs["Y"], 0.5)
    r = mathn(nt, "SQRT", mathn(nt, "ADD", mathn(nt, "MULTIPLY", dx, dx), mathn(nt, "MULTIPLY", dy, dy)))
    width = mathn(nt, "ADD", 0.08, mathn(nt, "MULTIPLY", z, 0.42))
    shape = mathn(nt, "SUBTRACT", 1.0, mathn(nt, "DIVIDE", r, width), clamp=True)
    shape = mathn(nt, "POWER", shape, 0.8)
    top = mathn(nt, "SUBTRACT", 1.0, mathn(nt, "POWER", z, 6.0), clamp=True)
    bottom = mathn(nt, "MINIMUM", mathn(nt, "MULTIPLY", z, 12.0), 1.0)
    co = texcoord(nt, "Object")
    mp = nt.nodes.new("ShaderNodeMapping")
    L(nt, co, mp.inputs["Vector"])
    mp.inputs["Location"].driver_add("default_value", 2).driver.expression = f"-frame * {rise}"
    mp.inputs["Location"].driver_add("default_value", 0).driver.expression = f"-frame * {rise * 0.3}"
    warp = noise(nt, 2.2, 3, 0.5, mp.outputs[0], dim="4D")
    warp.inputs["W"].driver_add("default_value").driver.expression = "frame * 0.02"
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "VECTOR"
    mix.inputs["Factor"].default_value = 0.35
    L(nt, mp.outputs[0], mix.inputs["A"])
    L(nt, warp.outputs["Color"], mix.inputs["B"])
    n = noise(nt, 5.5, 6, 0.62, mix.outputs["Result"], dim="4D")
    n.inputs["W"].driver_add("default_value").driver.expression = "frame * 0.035"
    wisp = ramp(nt, [(0.5, (0, 0, 0)), (0.78, (1, 1, 1))], n.outputs["Fac"]).outputs["Color"]
    d = mathn(nt, "MULTIPLY", mathn(nt, "MULTIPLY", mathn(nt, "MULTIPLY", shape, wisp), mathn(nt, "MULTIPLY", top, bottom)), 9.0 * strength)
    v = nt.nodes.new("ShaderNodeVolumePrincipled")
    v.inputs["Color"].default_value = (0.9, 0.9, 0.9, 1)
    v.inputs["Anisotropy"].default_value = 0.5
    L(nt, d, v.inputs["Density"])
    L(nt, v.outputs[0], nt.nodes["Material Output"].inputs["Volume"])
    return m


def steam(c):
    import dress
    out = []
    woks = dress.WOKS or [(-3.05, 2.81, 0.85), (-3.05, 3.55, 0.85)]
    for i, (x, y, z) in enumerate(woks):
        out.append(_vol_box(f"steam_wok_{i}", (x - 0.35, y - 0.55, z + 0.08), (x + 1.35, y + 0.55, S.AWN["z_wall"] - 0.15), c,
                            m_plume("steam_wok", rise=0.055, strength=0.22)))
    sp = bpy.data.objects.get("stockpot")
    if sp:
        lo, hi = dress.bounds(sp)
        x, y = (lo.x + hi.x) / 2, (lo.y + hi.y) / 2
        out.append(_vol_box("steam_stockpot", (x - 0.25, y - 0.4, hi.z - 0.02), (x + 0.95, y + 0.4, S.AWN["z_wall"] - 0.15), c,
                            m_plume("steam_pot", rise=0.03, strength=0.18, lean=0.5)))
    return out


def haze(c):
    """Low-density haze over the stall and the near street, slightly thicker low down and under the awning."""
    m, nt = new_mat("street_haze")
    if nt:
        nt.nodes.remove(nt.nodes["Principled BSDF"])
        co = texcoord(nt, "Object")
        n = noise(nt, 0.35, 3, 0.5, co, dim="4D")
        n.inputs["W"].driver_add("default_value").driver.expression = "frame * 0.004"
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        L(nt, texcoord(nt, "Generated"), sep.inputs[0])
        low = mathn(nt, "ADD", 0.6, mathn(nt, "MULTIPLY", mathn(nt, "SUBTRACT", 1.0, sep.outputs["Z"]), 0.8))
        d = mathn(nt, "MULTIPLY", mathn(nt, "MULTIPLY", mathn(nt, "ADD", n.outputs["Fac"], 0.3), low), 0.0055)
        v = nt.nodes.new("ShaderNodeVolumePrincipled")
        v.inputs["Color"].default_value = (0.8, 0.82, 0.9, 1)
        v.inputs["Anisotropy"].default_value = 0.65
        L(nt, d, v.inputs["Density"])
        L(nt, v.outputs[0], nt.nodes["Material Output"].inputs["Volume"])
    return _vol_box("haze", (S.FX0 + 0.02, -16, S.ROAD_Z - 0.02), (S.FX1 - 0.02, 24, 9.0), c, m)


def _drop_mat():
    m, nt = new_mat("drizzle")
    if nt:
        b = nt.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (0.8, 0.85, 0.9, 1)
        b.inputs["Roughness"].default_value = 0.05
        b.inputs["Emission Color"].default_value = (0.8, 0.86, 1.0, 1)
        b.inputs["Emission Strength"].default_value = 0.5
        b.inputs["Alpha"].default_value = 0.35
    return m


def _drop_obj(name, c, length, radius):
    o = cylinder(name, radius, length, c, None, loc=(0, 0, -60), verts=6)
    # Particle VEL rotation aligns the instance's +X with velocity: lay the drop's long axis along X.
    o.data.transform(Matrix.Rotation(math.radians(90), 4, "Y") @ Matrix.Translation((0, 0, -length / 2)))
    o.data.materials.append(_drop_mat())
    o["no_support"] = True
    return o


def _emitter(name, c, lo, hi, drop, count, speed, lifetime, gravity=0.0, start=-80):
    em = box(name, (lo[0], lo[1], hi[2]), (hi[0], hi[1], hi[2] + 0.02), c, None, 0)
    em["no_support"] = True
    ps = em.modifiers.new("p", "PARTICLE_SYSTEM").particle_system.settings
    ps.count = count
    ps.frame_start = start
    ps.frame_end = END
    ps.lifetime = lifetime
    ps.emit_from = "VOLUME"
    ps.normal_factor = 0.0
    ps.object_align_factor = (0.25, 0.1, -speed)  # slight wind toward the street end
    ps.factor_random = 0.15
    ps.effector_weights.gravity = gravity
    ps.render_type = "OBJECT"
    ps.instance_object = drop
    ps.particle_size = 1.0
    ps.size_random = 0.5
    ps.use_rotations = True
    ps.rotation_mode = "VEL"
    ps.use_dynamic_rotation = False
    ps.physics_type = "NEWTON"
    em.show_instancer_for_render = False
    em.show_instancer_for_viewport = False
    return em


def drizzle(c):
    d = _drop_obj("drizzle_drop", c, 0.05, 0.0009)
    span = END + 80
    out = []
    # Near street (where the cameras are), open sky only: from the awning edge out into the road.
    out.append(_emitter("drizzle_near", c, (-0.1, -12.0, 0), (6.8, 12.0, 6.5), d, int(9000 * span / 40), 5.0, 40))
    # Beyond the awning to the far side and down the street: sparser.
    out.append(_emitter("drizzle_far", c, (-3.9, 7.2, 0), (9.5, 30.0, 9.0), d, int(5000 * span / 50), 5.0, 50))
    out.append(_emitter("drizzle_back", c, (-3.9, -16.0, 0), (-0.2, -1.2, 9.0), d, int(1500 * span / 50), 5.0, 50))
    # Drips off the awning's front edge: slow, heavier, under gravity.
    dd = _drop_obj("drip_drop", c, 0.02, 0.0018)
    a = S.AWN
    em = _emitter("awning_drips", c, (a["x1"] - 0.03, a["y0"], 0), (a["x1"] + 0.01, a["y1"], a["z_edge"] - 0.02), dd, int(span * 2.5), 0.2, 30, gravity=1.0)
    out.append(em)
    return out


def build():
    c = coll("fx")
    steam(c)
    haze(c)
    drizzle(c)
    print("FX done", flush=True)
