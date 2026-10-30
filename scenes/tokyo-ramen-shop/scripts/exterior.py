"""Street outside the shop (design coordinates; front wall at y=0, street toward -Y).

Layers for parallax: 3D near elements (vending machine, street lamp, neon signs, curb, puddles, rain)
in front of the emissive photo backdrop from shell.exterior. Lights: lamp pool on the wet street,
vending machine glow, neon spill, and cool spill in through the door glass and noren."""
import math
import os

import bpy

import shell as S
from lib import L, area, box, bsdf, cylinder, m_simple, mathn, mix, new_mat, node, noise, point, ramp, spot, texcoord

FONT = "C:/Windows/Fonts/YuGothB.ttc"


def m_emit(name, color, strength):
    m, nt = new_mat(name)
    if nt:
        b = bsdf(nt)
        b.inputs["Base Color"].default_value = (*color, 1)
        b.inputs["Emission Color"].default_value = (*color, 1)
        b.inputs["Emission Strength"].default_value = strength
    return m


def m_vending_front():
    """Backlit display of drinks: a grid of cells, each a random-coloured can on a white backlight."""
    m, nt = new_mat("vending_front")
    if not nt:
        return m
    uv = texcoord(nt, "UV")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (8.0, 5.0, 1.0)
    L(nt, uv, mp.inputs["Vector"])
    cell = nt.nodes.new("ShaderNodeVectorMath")
    cell.operation = "FLOOR"
    L(nt, mp.outputs[0], cell.inputs[0])
    frac = nt.nodes.new("ShaderNodeVectorMath")
    frac.operation = "FRACTION"
    L(nt, mp.outputs[0], frac.inputs[0])
    wn = nt.nodes.new("ShaderNodeTexWhiteNoise")
    L(nt, cell.outputs[0], wn.inputs["Vector"])
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    L(nt, frac.outputs[0], sep.inputs[0])
    # Can silhouette: narrow in x, tall in y, inside each cell.
    cx = mathn(nt, "LESS_THAN", mathn(nt, "ABSOLUTE", mathn(nt, "SUBTRACT", sep.outputs["X"], 0.5)), 0.28)
    cy = mathn(nt, "MULTIPLY", mathn(nt, "GREATER_THAN", sep.outputs["Y"], 0.18), mathn(nt, "LESS_THAN", sep.outputs["Y"], 0.86))
    can = mathn(nt, "MULTIPLY", cx, cy)
    col = mix(nt, can, (1.0, 0.98, 0.94, 1), wn.outputs["Color"])
    b = bsdf(nt)
    L(nt, col, b.inputs["Base Color"])
    L(nt, col, b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = 3.5
    b.inputs["Roughness"].default_value = 0.1
    return m


def neon_text(name, text, c, loc, rot, size, color, strength, back=True):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = "\n".join(text)  # one glyph per line = vertical sign
    cu.font = bpy.data.fonts.load(FONT, check_existing=True)
    cu.size = size
    cu.space_line = 0.85
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.extrude = 0.006
    cu.bevel_depth = 0.002
    o = bpy.data.objects.new(name, cu)
    c.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    cu.materials.append(m_emit(name + "_mat", color, strength))
    if back:
        n = len(text)
        h = n * size * 0.85 + size * 0.5
        w = size * 1.35
        # Text faces +Y (toward the shop), so its box sits behind it on the -Y side.
        bx = box(name + "_box", (loc[0] - w / 2, loc[1] - 0.09, loc[2] - h / 2), (loc[0] + w / 2, loc[1] - 0.012, loc[2] + h / 2), c,
                 m_simple("sign_box", (0.03, 0.03, 0.035), 0.4, 0.6), 0.006)
    return o


def m_pavement():
    m, nt = new_mat("street_wet")
    if not nt:
        return m
    co = texcoord(nt)
    base = noise(nt, 9, 10, 0.65, co)
    col = ramp(nt, [(0.3, (0.02, 0.02, 0.021)), (0.75, (0.07, 0.068, 0.065))], base.outputs["Fac"])
    pud = ramp(nt, [(0.44, (0, 0, 0)), (0.5, (1, 1, 1))], noise(nt, 0.7, 4, 0.5, co).outputs["Fac"])
    b = bsdf(nt)
    L(nt, mix(nt, pud.outputs["Color"], col.outputs["Color"], (0.008, 0.008, 0.009, 1)), b.inputs["Base Color"])
    L(nt, mix(nt, pud.outputs["Color"], (0.35, 0.35, 0.35, 1), (0.02, 0.02, 0.02, 1)), b.inputs["Roughness"])
    # Rain ripples only in the puddles.
    rip = node(nt, "ShaderNodeTexVoronoi", Scale=55.0)
    L(nt, co, rip.inputs["Vector"])
    ring = ramp(nt, [(0.0, (0, 0, 0)), (0.12, (1, 1, 1)), (0.2, (0, 0, 0))], rip.outputs["Distance"])
    h = mathn(nt, "MULTIPLY", ring.outputs["Color"], pud.outputs["Color"])
    bm = nt.nodes.new("ShaderNodeBump")
    bm.inputs["Strength"].default_value = 0.08
    L(nt, h, bm.inputs["Height"])
    bm2 = nt.nodes.new("ShaderNodeBump")
    bm2.inputs["Strength"].default_value = 0.3
    L(nt, noise(nt, 70, 8, 0.7, co).outputs["Fac"], bm2.inputs["Height"])
    L(nt, bm2.outputs[0], bm.inputs["Normal"])
    L(nt, bm.outputs[0], b.inputs["Normal"])
    return m


def rain(c, lo=(-1.6, -2.2, 0.0), hi=(5.2, -0.25, 3.6), count=35000):  # strip in front of the shop only: drops at the lens smear white
    """Rain streaks: instanced thin drops falling at ~7 m/s; motion blur (and their length) makes the streaks."""
    drop = cylinder("rain_drop", 0.0012, 0.07, c, None, loc=(0, 0, -50), verts=6)
    # Particle VEL rotation aligns the instance's +X with the velocity, so lay the drop's long axis along X.
    from mathutils import Matrix
    drop.data.transform(Matrix.Rotation(math.radians(90), 4, "Y") @ Matrix.Translation((0, 0, -0.035)))
    drop.data.materials.append(_rain_mat())
    drop.hide_render = False
    em = box("rain_emitter", (lo[0], lo[1], hi[2]), (hi[0], hi[1], hi[2] + 0.02), c, None, 0)
    # Not hide_render: that also hides the particle instances. show_instancer_for_render=False hides only the box.
    ps_mod = em.modifiers.new("rain", "PARTICLE_SYSTEM")
    ps = ps_mod.particle_system.settings
    ps.count = count
    ps.frame_start = -60
    ps.frame_end = 200
    ps.lifetime = 30
    ps.emit_from = "VOLUME"
    ps.normal_factor = 0.0
    ps.object_align_factor = (0, 0, -7.0)
    ps.effector_weights.gravity = 0.0
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


def _rain_mat():
    m, nt = new_mat("rain")
    if nt:
        b = bsdf(nt)
        b.inputs["Base Color"].default_value = (0.8, 0.85, 0.9, 1)
        b.inputs["Roughness"].default_value = 0.05
        b.inputs["Transmission Weight"].default_value = 0.0  # transmissive drops vanished in Cycles
        b.inputs["Emission Color"].default_value = (0.75, 0.85, 1.0, 1)
        b.inputs["Emission Strength"].default_value = 1.1
        b.inputs["Alpha"].default_value = 0.3
    return m


def build(c):
    # Ground: wet street with puddles in front of the shop, a curb and a gutter.
    pav = bpy.data.objects.get("pavement")
    if pav:
        pav.data.materials.clear()
        pav.data.materials.append(m_pavement())
    box("curb", (-2.0, -1.45, -0.12), (S.W + 2.0, -1.3, 0.02), c, m_simple("curb", (0.13, 0.125, 0.12), 0.55), 0.01)
    box("gutter", (-2.0, -1.62, -0.14), (S.W + 2.0, -1.45, -0.115), c, m_simple("gutter", (0.05, 0.05, 0.05), 0.25, 0.8), 0.003)
    box("road", (-6.0, -5.0, -0.2), (S.W + 6.0, -1.62, -0.13), c, m_pavement(), 0)

    # Vending machine across the street, facing the shop (seen through the door; parallax against the photo).
    vx0, vx1, vy0, vy1 = 1.55, 2.5, -3.35, -2.65
    box("vending_body", (vx0, vy0, -0.13), (vx1, vy1, 1.75), c, m_simple("vending_body", (0.75, 0.74, 0.72), 0.35, coat=0.6), 0.02)
    from lib import plane
    flip = (0, 0, math.radians(180))  # planes face -Y by default; these face the shop (+Y)
    plane("vending_display", 0.8, 1.0, c, m_vending_front(), loc=((vx0 + vx1) / 2, vy1 + 0.004, 0.6), rot=flip)
    plane("vending_header", 0.8, 0.18, c, m_emit("vending_header", (0.95, 0.15, 0.12), 6.0), loc=((vx0 + vx1) / 2, vy1 + 0.004, 1.48), rot=flip)
    box("vending_slot", ((vx0 + vx1) / 2 - 0.3, vy1, 0.0), ((vx0 + vx1) / 2 + 0.3, vy1 + 0.05, 0.2), c, m_simple("slot", (0.02, 0.02, 0.02), 0.4), 0.01)
    area("vending_glow", c, ((vx0 + vx1) / 2, vy1 + 0.15, 0.85), (math.radians(90), 0, 0), 0.8, 60, (0.8, 0.92, 1.0), size_y=1.2)

    # Street lamp across the gutter: a cool LED pool on the wet street.
    lx, ly = 3.2, -1.85
    cylinder("lamp_pole", 0.05, 4.3, c, m_simple("pole_grey", (0.2, 0.2, 0.19), 0.5, 0.7), loc=(lx, ly, -0.13))
    arm = box("lamp_arm", (lx - 0.9, ly - 0.03, 4.08), (lx, ly + 0.03, 4.13), c, m_simple("pole_grey", (0.2, 0.2, 0.19), 0.5, 0.7), 0.01)
    box("lamp_head", (lx - 1.15, ly - 0.12, 4.0), (lx - 0.75, ly + 0.12, 4.12), c, m_simple("pole_grey", (0.2, 0.2, 0.19), 0.5, 0.7), 0.01)
    plane("lamp_lens", 0.38, 0.22, c, m_emit("lamp_lens", (0.85, 0.92, 1.0), 40), loc=(lx - 0.95, ly - 0.11, 3.995), rot=(math.radians(90), 0, 0))
    spot("street_lamp", c, (lx - 0.95, ly, 3.95), (0, 0, 0), 1400, (0.82, 0.9, 1.0), angle=120, blend=0.5, radius=0.15)

    # Neon across the street (behind the lamp, in front of the photo): pink izakaya tube text and a box sign.
    neon_text("neon_izakaya", "居酒屋", c, (0.95, -3.5, 2.45), (math.radians(-90), 0, 0), 0.32, (1.0, 0.18, 0.45), 18)
    point("neon_izakaya_spill", c, (0.95, -3.25, 2.4), 60, (1.0, 0.25, 0.5), radius=0.3)
    neon_text("neon_snack", "スナック", c, (3.0, -3.7, 2.6), (math.radians(-90), 0, 0), 0.26, (0.3, 0.85, 1.0), 14)
    point("neon_snack_spill", c, (3.0, -3.45, 2.5), 45, (0.3, 0.8, 1.0), radius=0.3)

    # Spill into the shop: cool street light through the door glass and noren, onto the floor just inside.
    spot("door_spill", c, ((S.DOOR[0] + S.DOOR[1]) / 2, -1.6, 2.3), (math.radians(62), 0, 0), 260, (0.7, 0.82, 1.0), angle=55, blend=0.7, radius=0.4)
    spot("window_spill", c, ((S.WIN[0] + S.WIN[1]) / 2, -1.6, 2.3), (math.radians(62), 0, 0), 160, (0.75, 0.6, 1.0), angle=55, blend=0.7, radius=0.4)

    bd = bpy.data.objects.get("street_backdrop")
    if bd:
        em = next(n for n in bd.data.materials[0].node_tree.nodes if n.type == "EMISSION")
        em.inputs["Strength"].default_value = 1.1
    rain(c)
