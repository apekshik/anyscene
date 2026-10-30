"""Direct-modelled ramen shop: room shell, L-counter, kitchen fixtures, door, pendants, textured planes.

Layout (metres): x 0..W left->right, y 0..D front(street)->back, z up.
Customer aisle x 0..CX along the left wall; counter top CX..CX+0.45; raised pass behind it; kitchen x KX..W.
"""
import math
import os

import bpy

from lib import (TEX, area, box, coll, cylinder, m_concrete_wet, m_glass_rain, m_image, m_plaster, m_simple,
                 m_stainless, m_tile, m_wood, mesh_obj, plane, uv_cube)

W, D, H = 3.6, 7.0, 2.6
CX = 1.25          # customer side edge of counter
CT = 0.45          # counter top depth
CH = 0.90          # counter top height
PASS_X = CX + CT   # raised pass ledge starts here
PASS_H = 1.0
KX = 1.95          # kitchen prep counter (inside the pass) starts
Y0, Y1 = 1.6, 6.15 # counter run along y
LEG_X0 = 0.85      # short L-leg at the back runs x LEG_X0..PASS_X
DOOR = (0.72, 1.72)  # door x range in the front wall (ticket machine sits in the corner left of it)
WIN = (2.05, 3.4)    # front window x range
LANTERN = (2.38, -0.36, 1.38)   # bottom-centre of the akachochin hanging outside, between door and window
STOOL_Y = [1.95, 2.55, 3.15, 3.75, 4.35, 4.95, 5.55]
PENDANT_Y = [2.25, 3.45, 4.65, 5.75]
WALL_T = 0.12


def build(c):
    mats = {
        "plaster": m_plaster("plaster", (0.42, 0.37, 0.29)),
        "ceiling": m_plaster("ceiling", (0.26, 0.23, 0.19)),
        "wainscot": m_wood("wainscot", (0.035, 0.018, 0.01), (0.11, 0.055, 0.025), along="Z", scale=1.2, gloss=0.5, wear=False),
        "counter": m_wood("counter_top", (0.045, 0.02, 0.009), (0.15, 0.075, 0.035), along="Y", scale=2.5, gloss=0.28, fine_mix=0.78, bump_k=0.035),
        "counter_base": m_wood("counter_base", (0.03, 0.015, 0.008), (0.09, 0.045, 0.02), along="Z", gloss=0.55, wear=False),
        "floor": m_concrete_wet(),
        "steel": m_stainless("stainless"),
        "steel_v": m_stainless("stainless_v", "Z", 0.9),
        "tile": m_tile(),
        "glass": m_glass_rain(),
        "frame": m_simple("alu_frame", (0.18, 0.17, 0.16), 0.45, 0.9),
        "door_wood": m_wood("door_wood", (0.05, 0.025, 0.012), (0.16, 0.08, 0.035), along="Z", gloss=0.6, wear=False),
        "black": m_simple("black_paint", (0.02, 0.02, 0.02), 0.5),
        "rubber": m_simple("rubber_mat", (0.012, 0.012, 0.012), 0.85),
    }

    # --- room
    box("floor", (0, 0, -0.1), (W, D, 0), c, mats["floor"], bevel=0)
    box("ceiling", (0, 0, H), (W, D, H + 0.1), c, mats["ceiling"], bevel=0)
    box("wall_L", (-WALL_T, 0, 0), (0, D, H), c, mats["plaster"], bevel=0)
    box("wall_back", (0, D, 0), (W, D + WALL_T, H), c, mats["plaster"], bevel=0)
    # Right wall is the kitchen wall: tile up to 1.6 m, plaster above.
    box("wall_R_tile", (W, 0, 0), (W + WALL_T, D, 1.6), c, mats["tile"], bevel=0)
    box("wall_R_up", (W, 0, 1.6), (W + WALL_T, D, H), c, mats["plaster"], bevel=0)
    # Front wall with door and window openings.
    fz = 0
    for name, x0, x1, z0, z1 in [
        ("front_a", 0, DOOR[0], 0, H), ("front_b", DOOR[1], WIN[0], 0, H), ("front_c", WIN[1], W, 0, H),
        ("front_door_head", DOOR[0], DOOR[1], 2.05, H), ("front_win_sill", WIN[0], WIN[1], 0, 0.95),
        ("front_win_head", WIN[0], WIN[1], 2.05, H),
    ]:
        box(name, (x0, -WALL_T, z0), (x1, fz, z1), c, mats["plaster"], bevel=0)
    # Wood wainscot on the customer walls.
    box("wainscot_L", (0, 0, 0), (0.02, D, 1.0), c, mats["wainscot"], bevel=0.002)
    box("wainscot_back", (0, D - 0.02, 0), (W, D, 1.0), c, mats["wainscot"], bevel=0.002)
    box("wainscot_rail_L", (0, 0, 1.0), (0.035, D, 1.04), c, mats["counter_base"], bevel=0.004)
    box("skirting_front", (0, 0, 0), (W, 0.02, 0.12), c, mats["counter_base"], bevel=0.002)

    # --- sliding door: two leaves of wood frame + rain glass
    leaf_w = (DOOR[1] - DOOR[0]) / 2 + 0.03
    # Leaf 0 slid into the wall pocket so the doorway is ~0.73 m open (the walkthrough shot passes through it).
    for i, (x0, yoff) in enumerate([(DOOR[0] - 0.5, -0.07), (DOOR[0] + leaf_w - 0.06 + 0.32, -0.035)]):
        x1 = x0 + leaf_w
        t = 0.04
        y0, y1 = yoff - t / 2, yoff + t / 2
        box(f"door{i}_stile_l", (x0, y0, 0), (x0 + 0.06, y1, 2.05), c, mats["door_wood"], 0.003)
        box(f"door{i}_stile_r", (x1 - 0.06, y0, 0), (x1, y1, 2.05), c, mats["door_wood"], 0.003)
        box(f"door{i}_rail_b", (x0, y0, 0), (x1, y1, 0.32), c, mats["door_wood"], 0.003)
        box(f"door{i}_rail_m", (x0, y0, 1.0), (x1, y1, 1.05), c, mats["door_wood"], 0.003)
        box(f"door{i}_rail_t", (x0, y0, 1.98), (x1, y1, 2.05), c, mats["door_wood"], 0.003)
        for z0, z1 in [(0.32, 1.0), (1.05, 1.98)]:
            box(f"door{i}_glass_{z0}", (x0 + 0.06, yoff - 0.004, z0), (x1 - 0.06, yoff + 0.004, z1), c, mats["glass"], 0)
    box("door_track", (DOOR[0] - 0.05, -0.12, 0), (DOOR[1] + 0.4, 0.0, 0.015), c, mats["frame"], 0.002)
    # Front window: aluminium frame + rain glass.
    box("win_glass", (WIN[0], -0.065, 0.95), (WIN[1], -0.057, 2.05), c, mats["glass"], 0)
    for name, lo, hi in [
        ("win_f_l", (WIN[0], -0.09, 0.95), (WIN[0] + 0.04, -0.03, 2.05)), ("win_f_r", (WIN[1] - 0.04, -0.09, 0.95), (WIN[1], -0.03, 2.05)),
        ("win_f_m", ((WIN[0] + WIN[1]) / 2 - 0.02, -0.09, 0.95), ((WIN[0] + WIN[1]) / 2 + 0.02, -0.03, 2.05)),
        ("win_f_b", (WIN[0], -0.09, 0.93), (WIN[1], -0.03, 0.97)), ("win_f_t", (WIN[0], -0.09, 2.03), (WIN[1], -0.03, 2.07)),
    ]:
        box(name, lo, hi, c, mats["frame"], 0.002)

    # --- L-counter (customer side): base panels + thick wood top + raised pass + footrest rail
    box("counter_base_long", (CX + 0.04, Y0, 0), (PASS_X, Y1, CH - 0.05), c, mats["counter_base"], 0.004)
    box("counter_top_long", (CX - 0.04, Y0 - 0.04, CH - 0.05), (PASS_X, Y1 + 0.04, CH), c, mats["counter"], 0.008)
    box("counter_base_leg", (LEG_X0, Y1 + 0.04, 0), (PASS_X, Y1 + 0.45, CH - 0.05), c, mats["counter_base"], 0.004)
    box("counter_top_leg", (LEG_X0 - 0.04, Y1 + 0.0, CH - 0.05), (PASS_X, Y1 + 0.49, CH), c, mats["counter"], 0.008)
    box("pass_long", (PASS_X, Y0 - 0.04, CH - 0.05), (PASS_X + 0.22, Y1 + 0.49, PASS_H), c, mats["counter_base"], 0.004)
    box("pass_top", (PASS_X - 0.02, Y0 - 0.06, PASS_H), (PASS_X + 0.24, Y1 + 0.51, PASS_H + 0.035), c, mats["counter"], 0.006)
    box("counter_end_front", (CX - 0.04, Y0 - 0.06, 0), (PASS_X + 0.22, Y0 - 0.0, CH - 0.05), c, mats["counter_base"], 0.004)
    rail = cylinder("foot_rail", 0.015, Y1 - Y0, c, mats["frame"], loc=(0, 0, 0), verts=16)
    rail.rotation_euler = (math.radians(-90), 0, 0)
    rail.location = (CX - 0.02, (Y0 + Y1) / 2, 0.22)  # cylinder origin is its centre (was Y0: rail poked 0.7 m out the front wall)

    # --- kitchen: prep counter behind the pass, back counters on the right wall, gap for range + boiler
    box("prep_counter", (PASS_X + 0.22, Y0 - 0.04, 0), (KX + 0.5, Y1 + 0.49, 0.86), c, mats["steel_v"], 0.003)
    box("prep_top", (PASS_X + 0.2, Y0 - 0.06, 0.86), (KX + 0.52, Y1 + 0.51, 0.88), c, mats["steel"], 0.003)
    RX = W - 0.62
    box("back_counter_a", (RX, 0.9, 0), (W, 3.4, 0.86), c, mats["steel_v"], 0.003)
    box("back_counter_a_top", (RX - 0.02, 0.9, 0.86), (W, 3.4, 0.88), c, mats["steel"], 0.003)
    box("back_counter_b", (RX, 5.35, 0), (W, D, 0.86), c, mats["steel_v"], 0.003)
    box("back_counter_b_top", (RX - 0.02, 5.35, 0.86), (W, D, 0.88), c, mats["steel"], 0.003)
    box("backsplash", (W - 0.012, 0.9, 0.88), (W, D, 1.6), c, mats["steel_v"], 0)
    for i, z in enumerate((1.6, 1.98)):
        box(f"shelf_{i}", (W - 0.32, 0.9, z), (W, 3.4, z + 0.02), c, mats["steel"], 0.002)
        box(f"shelf_b_{i}", (W - 0.32, 5.35, z), (W, D, z + 0.02), c, mats["steel"], 0.002)
    # Extractor hood over the range + boiler zone.
    hood = box("hood", (W - 0.75, 3.35, 1.85), (W, 5.45, 2.3), c, mats["steel"], 0.004)
    box("hood_duct", (W - 0.45, 4.2, 2.3), (W - 0.1, 4.6, H), c, mats["steel"], 0.003)
    box("kitchen_mat", (KX + 0.55, 1.0, 0), (RX - 0.02, D - 0.2, 0.012), c, mats["rubber"], 0.002)

    # --- menu plaques above the pass (generated image on a plane facing customers, -X)
    plaq = os.path.join(TEX, "menu_plaques_0.png")
    if os.path.exists(plaq):
        mat = m_image("menu_plaques", plaq, rough=0.65, bump_strength=0.15)
        p = plane("menu_plaques", 3.6, 0.5, c, mat, loc=(PASS_X + 0.12, 3.85, 1.95), rot=(0, 0, math.radians(-90)))
        box("plaque_beam", (PASS_X + 0.13, Y0, 2.45), (PASS_X + 0.23, Y1 + 0.5, 2.6), c, mats["counter_base"], 0.004)
    # Wall paper: poster, calendar, notice on the left wall (facing +X).
    for name, w, h, y, z in [("poster_beer", 0.42, 0.6, 3.2, 1.35), ("calendar", 0.36, 0.52, 4.6, 1.3), ("handwritten_notice", 0.21, 0.3, 2.3, 1.45)]:
        f = os.path.join(TEX, f"{name}_0.png")
        if os.path.exists(f):
            plane(name, w, h, c, m_image(name, f, rough=0.8), loc=(0.025, y, z), rot=(0, 0, math.radians(90)))

    # --- pendant lamps (shade + bulb mesh; lights are added in lighting.py)
    shade = m_simple("lamp_shade", (0.55, 0.5, 0.42), 0.4, 0.0, coat=0.3)
    cord = m_simple("lamp_cord", (0.01, 0.01, 0.01), 0.6)
    for i, y in enumerate(PENDANT_Y):
        z = 1.72
        bpy.ops.mesh.primitive_cone_add(vertices=40, radius1=0.17, radius2=0.04, depth=0.14, end_fill_type="NOTHING", location=(CX + 0.22, y, z + 0.07))
        s = bpy.context.object
        s.name = f"pendant_shade_{i}"
        for uc in list(s.users_collection):
            uc.objects.unlink(s)
        c.objects.link(s)
        s.data.materials.append(shade)
        sol = s.modifiers.new("thick", "SOLIDIFY")
        sol.thickness = 0.003
        bpy.ops.object.shade_smooth()
        cylinder(f"pendant_cord_{i}", 0.003, H - z - 0.14, c, cord, loc=(CX + 0.22, y, z + 0.14), verts=8)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.035, location=(CX + 0.22, y, z + 0.06))
        b = bpy.context.object
        b.name = f"pendant_bulb_{i}"
        for uc in list(b.users_collection):
            uc.objects.unlink(b)
        c.objects.link(b)
        b.data.materials.append(m_simple("bulb", (1, 0.8, 0.55), 0.3, emission=(1.0, 0.62, 0.3), estr=60))
    exterior(c)
    return mats


def exterior(c):
    """Street outside: generated rainy-street photo as an emissive backdrop, wet pavement strip, noren over the door."""
    import bmesh
    from lib import L, bsdf, new_mat, node
    f = os.path.join(TEX, "street_backdrop_0.png")
    if os.path.exists(f):
        m, nt = new_mat("street_backdrop")
        if nt:
            tex = nt.nodes.new("ShaderNodeTexImage")
            tex.image = bpy.data.images.load(f, check_existing=True)
            mp = nt.nodes.new("ShaderNodeMapping")
            uvn = nt.nodes.new("ShaderNodeTexCoord")
            L(nt, uvn.outputs["UV"], mp.inputs["Vector"])
            # Crop the door frames at the image edges: use the middle 56% horizontally.
            mp.inputs["Location"].default_value = (0.22, 0.0, 0)
            mp.inputs["Scale"].default_value = (0.56, 1.0, 1)
            L(nt, mp.outputs[0], tex.inputs["Vector"])
            em = nt.nodes.new("ShaderNodeEmission")
            em.inputs["Strength"].default_value = 0.35
            L(nt, tex.outputs["Color"], em.inputs["Color"])
            L(nt, em.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
            nt.nodes.remove(bsdf(nt))
        # The cropped image is ~square (0.56 * 16/9), so a square plane keeps it unstretched; horizon near eye height.
        plane("street_backdrop", 7.5, 7.5, c, m, loc=(W / 2, -4.5, -2.2), rot=(0, 0, math.radians(180)))
    box("pavement", (-2, -4.5, -0.12), (W + 2, -WALL_T, -0.02), c, m_concrete_wet("pavement_wet"), bevel=0)
    box("eave", (-0.5, -0.9, 2.25), (W + 0.5, -WALL_T, 2.32), c, m_simple("eave", (0.05, 0.05, 0.05), 0.6), bevel=0.004)

    # Noren: three panels over the doorway, hanging from a pole, with gentle procedural folds.
    nf = os.path.join(TEX, "noren_0.png")
    if os.path.exists(nf):
        mat = m_image("noren", nf, rough=0.9, translucent=0.4)
        span = DOOR[1] - DOOR[0] + 0.2
        h = 0.78
        panel_w = span / 3 - 0.01
        for i in range(3):
            x0 = DOOR[0] - 0.1 + i * (span / 3)
            me = bpy.data.meshes.new(f"noren_{i}")
            bm = bmesh.new()
            nu, nv = 24, 30
            uvl = bm.loops.layers.uv.new("UVMap")
            vs = [[None] * (nv + 1) for _ in range(nu + 1)]
            for a in range(nu + 1):
                for b in range(nv + 1):
                    u, v = a / nu, b / nv
                    x = x0 + u * panel_w
                    z = 2.12 - (1 - v) * h
                    fold = 0.018 * math.sin(u * math.pi * 5 + i * 1.7) * (1 - v) ** 0.7
                    sway = 0.03 * (1 - v) ** 2
                    vs[a][b] = bm.verts.new((x, -0.2 + fold - sway, z))
            for a in range(nu):
                for b in range(nv):
                    face = bm.faces.new((vs[a][b], vs[a + 1][b], vs[a + 1][b + 1], vs[a][b + 1]))
                    for lp, (ua, vb) in zip(face.loops, [(a, b), (a + 1, b), (a + 1, b + 1), (a, b + 1)]):
                        # Each panel shows its third of the noren image.
                        # Panel i shows third (2 - i): build.py mirrors whole panels, which reverses their order.
                        lp[uvl].uv = ((2 - i + ua / nu * (panel_w / (span / 3))) / 3, vb / nv)
            bm.to_mesh(me)
            bm.free()
            o = bpy.data.objects.new(f"noren_{i}", me)
            c.objects.link(o)
            me.materials.append(mat)
            o.modifiers.new("solid", "SOLIDIFY").thickness = 0.002
            for p in me.polygons:
                p.use_smooth = True
        pole = cylinder("noren_pole", 0.012, span + 0.2, c, m_simple("pole", (0.1, 0.07, 0.04), 0.5), verts=12)
        pole.rotation_euler = (0, math.radians(90), 0)
        pole.location = ((DOOR[0] + DOOR[1]) / 2, -0.2, 2.13)  # cylinder origin is its centre
