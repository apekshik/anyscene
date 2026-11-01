"""Street shell for the dai pai dong (world coordinates, metres, Z up). See brief.md for the layout.

Street along +Y. Stall-side facades at x = FX0 (facing +X), far facades at x = FX1 (facing -X).
Pavement z 0, road z ROAD_Z. Everything architectural is direct-modelled here; props come from dress.py.
"""
import math
import os
import random

import bpy
from mathutils import Matrix, Vector

from lib import (TEX, L, box, bsdf, bump, coll, cylinder, mathn, mesh_obj, mix, new_mat, node, noise, plane, ramp,
                 texcoord, m_simple)

FX0, FX1 = -4.0, 9.6          # facade planes
KERB0, KERB1 = 0.0, 7.4       # kerb lines (road between)
ROAD_Z = -0.15
Y0, Y1 = -22.0, 40.0          # modelled street extent
STALL = dict(x0=-4.0, x1=-1.6, y0=-0.5, y1=6.0)
AWN = dict(x0=-4.0, x1=-0.15, y0=-1.0, y1=7.0, z_wall=3.15, z_edge=2.55)
POLE_X = -0.3
POLES_Y = (-0.85, 3.0, 6.85)
FONT = "C:/Windows/Fonts/msjhbd.ttc"
rng = random.Random(11)


def tex(name):
    p = os.path.join(TEX, name + "_0.png")
    return p if os.path.exists(p) else None


# ---------------------------------------------------------------- materials

def _wet_ground(name, base_path, tile, dark, light, puddle_scale, puddle_cut, rough_dry=0.5, fallback_scale=9.0):
    """Wet ground: image (or noise) albedo, darkened, with low-roughness puddles and fine rain ripples in them."""
    m, nt = new_mat(name)
    if not nt:
        return m
    co = texcoord(nt, "Object")
    b = bsdf(nt)
    if base_path:
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (1 / tile, 1 / tile, 1)
        L(nt, co, mp.inputs["Vector"])
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(base_path, check_existing=True)
        t.projection = "FLAT"
        L(nt, mp.outputs[0], t.inputs["Vector"])
        base = mix(nt, 0.55, t.outputs["Color"], (0.0, 0.0, 0.0, 1), "MULTIPLY")
        hgt = t.outputs["Color"]
    else:
        n = noise(nt, fallback_scale, 10, 0.65, co)
        base = ramp(nt, [(0.3, dark), (0.75, light)], n.outputs["Fac"]).outputs["Color"]
        hgt = n.outputs["Fac"]
    pn = noise(nt, puddle_scale, 4, 0.55, co)
    pud = ramp(nt, [(puddle_cut, (0, 0, 0)), (puddle_cut + 0.05, (1, 1, 1))], pn.outputs["Fac"]).outputs["Color"]
    # Wet everywhere (dark, fairly glossy); puddles are mirror-like and darker still.
    col = mix(nt, 0.35, base, (0.0, 0.0, 0.0, 1), "MULTIPLY")
    col = mix(nt, mathn(nt, "MULTIPLY", pud, 0.75), col, (0.004, 0.004, 0.005, 1))
    L(nt, col, b.inputs["Base Color"])
    rough = mix(nt, pud, (rough_dry, rough_dry, rough_dry, 1), (0.015, 0.015, 0.015, 1))
    L(nt, rough, b.inputs["Roughness"])
    b.inputs["Specular IOR Level"].default_value = 0.6
    # Rain ripples (voronoi rings) in the puddles, texture relief outside them.
    rip = node(nt, "ShaderNodeTexVoronoi", Scale=38.0)
    rip.voronoi_dimensions = "4D"
    rip.inputs["W"].driver_add("default_value").driver.expression = "frame * 0.06"
    L(nt, co, rip.inputs["Vector"])
    ring = ramp(nt, [(0.0, (0, 0, 0)), (0.1, (1, 1, 1)), (0.18, (0, 0, 0))], rip.outputs["Distance"]).outputs["Color"]
    h = mix(nt, pud, hgt, mathn(nt, "MULTIPLY", ring, 0.3))
    bm = node(nt, "ShaderNodeBump", Strength=0.25, Distance=0.002)
    L(nt, h, bm.inputs["Height"])
    L(nt, bm.outputs[0], b.inputs["Normal"])
    return m


def m_pavement():
    return _wet_ground("pavement_wet", tex("hk_tex_pavement"), 1.6, (0.05, 0.045, 0.045), (0.16, 0.13, 0.12), 0.9, 0.5, 0.42)


def m_road():
    return _wet_ground("road_wet", tex("hk_tex_asphalt"), 3.0, (0.02, 0.02, 0.022), (0.07, 0.068, 0.065), 0.45, 0.47, 0.38)


def m_paint(name, color):
    m, nt = new_mat(name)
    if nt:
        b = bsdf(nt)
        co = texcoord(nt)
        worn = ramp(nt, [(0.35, (0, 0, 0)), (0.6, (1, 1, 1))], noise(nt, 6, 6, 0.6, co).outputs["Fac"]).outputs["Color"]
        L(nt, mix(nt, worn, (0.03, 0.03, 0.03, 1), (*color, 1)), b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = 0.2
    return m


def m_grimy(name, color, rough=0.75, metal=0.0, streak=0.6):
    """Painted concrete / metal with vertical rain streaks and low grime (generated z from object bounds)."""
    m, nt = new_mat(name)
    if not nt:
        return m
    co = texcoord(nt)
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (6, 6, 0.25)
    L(nt, co, mp.inputs["Vector"])
    st = noise(nt, 3.0, 6, 0.6, mp.outputs[0])
    blot = noise(nt, 1.2, 5, 0.55, co)
    c = ramp(nt, [(0.3, tuple(v * 0.55 for v in color)), (0.7, color)], blot.outputs["Fac"]).outputs["Color"]
    sk = ramp(nt, [(0.5, (0, 0, 0)), (0.75, (1, 1, 1))], st.outputs["Fac"]).outputs["Color"]
    c = mix(nt, mathn(nt, "MULTIPLY", sk, streak), c, (0.03, 0.03, 0.025, 1), "MULTIPLY")
    b = bsdf(nt)
    L(nt, c, b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    L(nt, bump(nt, noise(nt, 30, 6, 0.6, co).outputs["Fac"], 0.15, 0.004).outputs[0], b.inputs["Normal"])
    return m


def m_facade_img(name, path, lit=4.0, tile_v=1.0):
    """Facade photo on a front plane: diffuse albedo + emission only where the photo is bright (lit windows)."""
    m, nt = new_mat(name)
    if not nt:
        return m
    uv = texcoord(nt, "UV")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1, tile_v, 1)
    L(nt, uv, mp.inputs["Vector"])
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(path, check_existing=True)
    L(nt, mp.outputs[0], t.inputs["Vector"])
    b = bsdf(nt)
    L(nt, t.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.6
    bw = nt.nodes.new("ShaderNodeRGBToBW")
    L(nt, t.outputs["Color"], bw.inputs[0])
    glow = ramp(nt, [(0.42, (0, 0, 0)), (0.75, (1, 1, 1))], bw.outputs[0]).outputs["Color"]
    L(nt, t.outputs["Color"], b.inputs["Emission Color"])
    L(nt, mathn(nt, "MULTIPLY", mathn(nt, "MAXIMUM", glow, 0.0), lit), b.inputs["Emission Strength"])
    L(nt, bump(nt, bw.outputs[0], 0.3, 0.01).outputs[0], b.inputs["Normal"])
    m.cycles.emission_sampling = "NONE"  # glows to camera; real light comes from lamps
    return m


def m_emit(name, color, strength):
    m, nt = new_mat(name)
    if nt:
        b = bsdf(nt)
        b.inputs["Base Color"].default_value = (*color, 1)
        b.inputs["Emission Color"].default_value = (*color, 1)
        b.inputs["Emission Strength"].default_value = strength
    return m


def m_lightbox(name, path, strength=3.0):
    m, nt = new_mat(name)
    if not nt:
        return m
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(path, check_existing=True)
    b = bsdf(nt)
    L(nt, t.outputs["Color"], b.inputs["Base Color"])
    L(nt, t.outputs["Color"], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = strength
    b.inputs["Roughness"].default_value = 0.25
    b.inputs["Coat Weight"].default_value = 0.5
    return m


def m_tarp():
    """Green corrugated plastic awning: translucent-ish, dirty, with algae streaks and drips."""
    m, nt = new_mat("tarp_green")
    if not nt:
        return m
    co = texcoord(nt)
    dirt = noise(nt, 2.0, 6, 0.6, co)
    c = ramp(nt, [(0.25, (0.04, 0.09, 0.05)), (0.7, (0.12, 0.24, 0.13))], dirt.outputs["Fac"]).outputs["Color"]
    b = bsdf(nt)
    L(nt, c, b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.35
    b.inputs["Coat Weight"].default_value = 0.6  # wet
    b.inputs["Coat Roughness"].default_value = 0.08
    b.inputs["Subsurface Weight"].default_value = 0.0
    b.inputs["Transmission Weight"].default_value = 0.0
    return m


# ---------------------------------------------------------------- pieces

def rod(name, p0, p1, r, c, mat, verts=10):
    """Cylinder from p0 to p1 (pipes, rafters, cords)."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=d.length, vertices=verts, location=(p0 + p1) / 2)
    o = bpy.context.object
    o.name = name
    for uc in list(o.users_collection):
        uc.objects.unlink(o)
    c.objects.link(o)
    o.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    if mat:
        o.data.materials.append(mat)
    return o


def text_obj(name, s, c, loc, rot, size, mat, vertical=True, extrude=0.008, bevel=0.003, font=FONT):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = "\n".join(s) if vertical else s
    cu.font = bpy.data.fonts.load(font, check_existing=True)
    cu.size = size
    cu.space_line = 0.9
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.extrude = extrude
    cu.bevel_depth = bevel
    o = bpy.data.objects.new(name, cu)
    c.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    cu.materials.append(mat)
    return o


def ground(c):
    pav = box("pavement", (FX0 - 0.1, Y0, -0.4), (KERB0 - 0.18, Y1, 0.0), c, m_pavement(), 0)
    pav2 = box("pavement_far", (KERB1 + 0.18, Y0, -0.4), (FX1 + 0.1, Y1, 0.0), c, m_pavement(), 0)
    kerb_m = m_grimy("kerb_granite", (0.2, 0.19, 0.18), 0.45, streak=0.2)
    box("kerb", (KERB0 - 0.18, Y0, -0.4), (KERB0, Y1, 0.0), c, kerb_m, 0.012)
    box("kerb_far", (KERB1, Y0, -0.4), (KERB1 + 0.18, Y1, 0.0), c, kerb_m, 0.012)
    road = box("road", (KERB0, Y0, -0.5), (KERB1, Y1 + 60, ROAD_Z), c, m_road(), 0)
    # Double yellow no-stopping lines along both kerbs, broken white centre line.
    yel = m_paint("paint_yellow", (0.75, 0.52, 0.06))
    wht = m_paint("paint_white", (0.7, 0.7, 0.66))
    for x in (0.28, 0.42, KERB1 - 0.42, KERB1 - 0.28):
        box(f"line_y_{x:.2f}", (x - 0.05, Y0, ROAD_Z), (x + 0.05, Y1, ROAD_Z + 0.002), c, yel, 0)
    y = Y0
    while y < Y1:
        box(f"line_c_{y:.0f}", (KERB1 / 2 - 0.06, y, ROAD_Z), (KERB1 / 2 + 0.06, y + 2.5, ROAD_Z + 0.002), c, wht, 0)
        y += 6.0
    # Gutter drain grates.
    grate = m_simple("drain_iron", (0.03, 0.03, 0.03), 0.35, 0.8)
    for gy in (-9.5, -1.8, 9.0, 17.5):
        for gx in (0.05, KERB1 - 0.45):
            box(f"drain_{gx:.1f}_{gy:.0f}", (gx, gy, ROAD_Z - 0.005), (gx + 0.4, gy + 0.9, ROAD_Z + 0.004), c, grate, 0.003)
    # Distant continuation: water and a far harbour-front wall at the end of the street.
    box("harbour_water", (-80, Y1 + 60, -1.6), (90, Y1 + 400, -1.5), c, m_simple("water", (0.005, 0.006, 0.008), 0.03), 0)
    return pav, road


def _floor_ledges(name, c, xf, sgn, y0, y1, z0, z1, m):
    z = z0
    i = 0
    while z < z1 - 0.5:
        a, b_ = sorted((xf, xf + sgn * 0.16))
        box(f"{name}_ledge{i}", (a, y0 + 0.05, z), (b_, y1 - 0.05, z + 0.14), c, m, 0.01)
        z += 2.9
        i += 1


def tenement(c, name, side, y0, y1, height, tex_id, shutter_id, paint, seed=0):
    """One building: textured upper facade plane, 3D floor ledges and pilasters, a ground-floor shopfront
    (two pilasters, a fascia band, a shutter), and a deep mass behind so gaps never show sky."""
    r = random.Random(seed)
    xf = FX0 if side < 0 else FX1
    sgn = 1 if side < 0 else -1          # direction the facade faces (+X for the stall side)
    back = xf - sgn * 8.0
    a, b_ = sorted((back, xf))
    mass = box(f"{name}_mass", (a, y0, 0), (b_, y1, height), c, m_grimy(f"{name}_concrete", paint, 0.85), 0)
    w = y1 - y0
    up_z = 3.7
    # Upper facade photo, tiled so the window size stays roughly real (one tile ~ 9 m tall).
    path = tex(tex_id)
    rot_z = math.radians(90 if sgn > 0 else -90)   # plane faces -Y locally; turn it to face the street
    if path:
        tiles = max(1, round((height - up_z) / 9.5))
        fp = plane(f"{name}_face", w, height - up_z, c, m_facade_img(f"{name}_facemat", path, tile_v=tiles),
                   loc=(xf + sgn * 0.02, (y0 + y1) / 2, up_z), rot=(0, 0, rot_z))
        fp["facade"] = True
    pil = m_grimy(f"{name}_pilaster", tuple(v * 0.85 for v in paint), 0.8)
    _floor_ledges(name, c, xf, sgn, y0, y1, up_z + 2.75, height, pil)
    for yy in (y0, y1 - 0.4):
        a, b_ = sorted((xf, xf + sgn * 0.22))
        # Inside the stall the ground-floor pilasters would cut through the shelves: start them above the awning.
        z0 = 3.2 if side < 0 and yy < AWN["y1"] + 0.5 and yy + 0.4 > AWN["y0"] - 0.5 else 0
        box(f"{name}_pil_{yy:.1f}", (a, yy, z0), (b_, yy + 0.4, height), c, pil, 0.01)
    # Fascia band for the shop sign and the shutter recess.
    a, b_ = sorted((xf, xf + sgn * 0.3))
    box(f"{name}_fascia", (a, y0 + 0.4, 3.05), (b_, y1 - 0.4, 3.7), c, pil, 0.01)
    sp = tex(shutter_id)
    if sp:
        sm, nt = new_mat(f"{name}_shutter")
        if nt:
            t = nt.nodes.new("ShaderNodeTexImage")
            t.image = bpy.data.images.load(sp, check_existing=True)
            L(nt, t.outputs["Color"], bsdf(nt).inputs["Base Color"])
            bsdf(nt).inputs["Roughness"].default_value = 0.45
            bsdf(nt).inputs["Metallic"].default_value = 0.5
            bw = nt.nodes.new("ShaderNodeRGBToBW")
            L(nt, t.outputs["Color"], bw.inputs[0])
            L(nt, bump(nt, bw.outputs[0], 0.5, 0.01).outputs[0], bsdf(nt).inputs["Normal"])
        sh = plane(f"{name}_shutter", w - 0.8, 3.05, c, sm, loc=(xf - sgn * 0.05, (y0 + y1) / 2, 0), rot=(0, 0, rot_z))
        sh["shutter"] = True
    return mass


def facades(c):
    """Stall side and far side, ~5-7 m wide buildings, 16-26 m tall."""
    texs = ["hk_tex_facade_a", "hk_tex_facade_b", "hk_tex_facade_c"]
    shut = ["hk_tex_shutter_a", "hk_tex_shutter_b"]
    paints = [(0.36, 0.38, 0.33), (0.45, 0.42, 0.36), (0.42, 0.33, 0.33), (0.33, 0.36, 0.38), (0.4, 0.4, 0.37)]
    out = []
    for side in (-1, 1):
        y = Y0
        i = 0
        while y < Y1:
            w = rng.uniform(4.8, 7.2)
            h = rng.uniform(16, 27)
            name = f"bldg_{'L' if side < 0 else 'R'}{i}"
            out.append(tenement(c, name, side, y, min(y + w, Y1), h, texs[(i + (side > 0)) % 3], shut[i % 2],
                                paints[(i * 2 + (side > 0)) % len(paints)], seed=i * 7 + (side > 0)))
            y += w
            i += 1
    # Distant blocks beyond the modelled street (silhouettes with a few lit windows), fading into haze.
    far = m_grimy("far_block", (0.12, 0.12, 0.13), 0.9, streak=0.2)
    for k in range(10):
        yy = Y1 + 4 + k * 5.5
        for side in (-1, 1):
            xf = FX0 if side < 0 else FX1
            a, b_ = sorted((xf, xf - (1 if side < 0 else -1) * 8))
            box(f"far_{side}_{k}", (a, yy, 0), (b_, yy + 5, rng.uniform(14, 30)), c, far, 0)
    return out


def sky_card(c):
    """Soft harbour skyline: an emissive photo card far down the street, sized to fill the gap between facades."""
    p = tex("hk_tex_skyline")
    if not p:
        return None
    m, nt = new_mat("skyline")
    if nt:
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(p, check_existing=True)
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Strength"].default_value = 0.9
        L(nt, t.outputs["Color"], em.inputs["Color"])
        nt.nodes.remove(bsdf(nt))
        L(nt, em.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    o = plane("skyline_card", 190, 107, c, m, loc=(3.0, 210, -14), rot=(0, 0, math.radians(180)))
    o.visible_shadow = False
    return o


def world():
    w = bpy.data.worlds.new("night_sky")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    # Low cloud lit orange-magenta from below; darker straight up.
    geo = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    L(nt, geo.outputs["Generated"], sep.inputs[0])
    r = ramp(nt, [(0.0, (0.05, 0.03, 0.04)), (0.25, (0.03, 0.022, 0.035)), (0.7, (0.008, 0.008, 0.014))], sep.outputs["Z"])
    L(nt, r.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    return w


# ---------------------------------------------------------------- stall structure

def corrugated(name, c, x0, x1, y0, y1, z0, z1, pitch=0.076, amp=0.009, mat=None, sag=0.05):
    """Corrugated sheet sloping from (x0, z0) to (x1, z1), ribs running along X (down the slope), slight sag."""
    nx, ny = 24, int((y1 - y0) / (pitch / 4))
    verts, faces = [], []
    for j in range(ny + 1):
        y = y0 + (y1 - y0) * j / ny
        wave = amp * math.sin(2 * math.pi * (y - y0) / pitch)
        for i in range(nx + 1):
            u = i / nx
            x = x0 + (x1 - x0) * u
            z = z0 + (z1 - z0) * u + wave - sag * math.sin(math.pi * u) * (0.6 + 0.4 * math.sin(y * 0.7))
            verts.append((x, y, z))
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            faces.append((a, a + 1, a + nx + 2, a + nx + 1))
    o = mesh_obj(name, verts, faces, c, mat)
    sol = o.modifiers.new("thick", "SOLIDIFY")
    sol.thickness = 0.003
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def stall_frame(c):
    steel = m_grimy("stall_steel", (0.08, 0.1, 0.09), 0.5, 0.7, streak=0.3)
    green = m_grimy("stall_green", (0.07, 0.17, 0.11), 0.55, 0.2, streak=0.5)
    a = AWN
    # Poles at the street edge, a beam along the top, rafters back to the wall bracket.
    for y in POLES_Y:
        cylinder(f"awn_pole_{y:.1f}", 0.025, a["z_edge"] + 0.05, c, steel, loc=(POLE_X, y, 0.0), verts=12)
    beam = box("awn_beam", (POLE_X - 0.025, a["y0"], a["z_edge"]), (POLE_X + 0.025, a["y1"], a["z_edge"] + 0.05), c, steel, 0.004)
    box("awn_wall_rail", (a["x0"], a["y0"], a["z_wall"] - 0.05), (a["x0"] + 0.06, a["y1"], a["z_wall"] + 0.02), c, steel, 0.004)
    for k, y in enumerate([a["y0"] + 0.1 + i * (a["y1"] - a["y0"] - 0.2) / 6 for i in range(7)]):
        rod(f"awn_rafter_{k}", (a["x0"] + 0.06, y, a["z_wall"] - 0.03), (POLE_X, y, a["z_edge"] + 0.04), 0.013, c, steel)
    tarp = corrugated("awning_tarp", c, a["x0"], a["x1"], a["y0"], a["y1"], a["z_wall"] + 0.03, a["z_edge"] + 0.07, mat=m_tarp())
    tarp["awning"] = True
    # Front valance board carrying the stall sign, facing the street (+X).
    p = tex("hk_tex_stall_sign")
    sign_m = m_image_sign("stall_sign", p) if p else green
    # The board sits on the beam, mostly above the awning edge (bottom at ~2.1 m so people walk under it).
    box("stall_sign_board", (POLE_X - 0.02, 0.2, a["z_edge"] - 0.45), (POLE_X + 0.03, 5.4, a["z_edge"] + 0.19), c, green, 0.006)
    if p:
        plane("stall_sign", 5.1, 0.6, c, sign_m, loc=(POLE_X + 0.035, 2.8, a["z_edge"] - 0.43), rot=(0, 0, math.radians(90)))
    # A second sign on the walk-in end, facing the oncoming walker (-Y).
    box("stall_sign_end", (-3.9, a["y0"] - 0.05, 2.0), (-1.7, a["y0"], 2.62), c, green, 0.006)
    if p:
        plane("stall_sign_end_face", 2.15, 0.58, c, sign_m, loc=(-2.8, a["y0"] - 0.055, 2.02), rot=(0, 0, 0))
    return tarp


def m_image_sign(name, path):
    m, nt = new_mat(name)
    if not nt:
        return m
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(path, check_existing=True)
    b = bsdf(nt)
    L(nt, t.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.4
    b.inputs["Coat Weight"].default_value = 0.4
    bw = nt.nodes.new("ShaderNodeRGBToBW")
    L(nt, t.outputs["Color"], bw.inputs[0])
    L(nt, bump(nt, bw.outputs[0], 0.2, 0.004).outputs[0], b.inputs["Normal"])
    return m


def back_shelves(c):
    """Steel wire shelving along the facade behind the cart: three tiers, x -4..-3.6."""
    steel = m_grimy("shelf_steel", (0.35, 0.35, 0.34), 0.35, 0.9, streak=0.4)
    x0, x1 = FX0 + 0.02, FX0 + 0.42
    out = []
    for (y0, y1) in ((-0.3, 1.6), (1.7, 3.6), (3.7, 5.8)):
        for yy in (y0, y1 - 0.03):
            for xx in (x0, x1 - 0.03):
                box(f"shelf_post_{yy:.1f}_{xx:.1f}", (xx, yy, 0), (xx + 0.03, yy + 0.03, 2.3), c, steel, 0.003)
        for z in (1.25, 1.7, 2.15):
            s = box(f"shelf_{y0:.1f}_{z:.2f}", (x0, y0, z), (x1, y1, z + 0.025), c, steel, 0.003)
            s["support"] = True
            out.append(s)
    # Steel prep table at the far end of the stall (beyond the wok range).
    t = box("prep_table", (-3.55, 4.1, 0.86), (-2.7, 5.75, 0.9), c, m_grimy("prep_top", (0.5, 0.5, 0.5), 0.3, 1.0, 0.5), 0.004)
    t["support"] = True
    sh = box("prep_table_shelf", (-3.5, 4.15, 0.18), (-2.75, 5.7, 0.2), c, steel, 0.003)
    sh["support"] = True
    for yy in (4.12, 5.7):
        for xx in (-3.53, -2.75):
            box(f"prep_leg_{yy:.1f}_{xx:.1f}", (xx, yy, 0), (xx + 0.03, yy + 0.03, 0.86), c, steel, 0.003)
    # Behind the kitchen: old white tiles to 1.5 m, greasy green-painted sheet metal above, menu strips on top.
    box("kitchen_tiles", (FX0 - 0.01, -0.5, 0.0), (FX0 + 0.015, 6.0, 1.5), c, m_kitchen_tile(), 0)
    box("kitchen_sheet", (FX0 - 0.01, -0.5, 1.5), (FX0 + 0.012, 6.0, 3.15), c,
        m_grimy("kitchen_sheet_green", (0.12, 0.2, 0.15), 0.4, 0.3, streak=0.9), 0)
    p = tex("hk_tex_menu_strips")
    if p:
        plane("menu_strips", 2.2, 0.62, c, m_image_sign("menu_strips_mat", p), loc=(FX0 + 0.02, 4.75, 2.42),
              rot=(0, 0, math.radians(90)))
    return out


def m_kitchen_tile():
    m, nt = new_mat("tile_kitchen")
    if not nt:
        return m
    co = texcoord(nt, "UV")
    br = node(nt, "ShaderNodeTexBrick", Scale=1.0, **{"Mortar Size": 0.004, "Brick Width": 0.15, "Row Height": 0.15})
    br.offset = 0.0
    L(nt, co, br.inputs["Vector"])
    br.inputs["Color1"].default_value = (0.62, 0.62, 0.57, 1)
    br.inputs["Color2"].default_value = (0.58, 0.58, 0.53, 1)
    br.inputs["Mortar"].default_value = (0.2, 0.18, 0.14, 1)
    grease = ramp(nt, [(0.3, (1, 1, 1)), (0.75, (0.35, 0.26, 0.14))], noise(nt, 2.0, 6, 0.6, texcoord(nt, "Object")).outputs["Fac"])
    b = bsdf(nt)
    L(nt, mix(nt, 1.0, br.outputs["Color"], grease.outputs["Color"], "MULTIPLY"), b.inputs["Base Color"])
    L(nt, ramp(nt, [(0.0, (0.5,) * 3), (1.0, (0.12,) * 3)], br.outputs["Fac"]).outputs["Color"], b.inputs["Roughness"])
    L(nt, bump(nt, mathn(nt, "SUBTRACT", 1.0, br.outputs["Fac"]), 0.3, 0.002).outputs[0], b.inputs["Normal"])
    return m


def decal(name, w, h, c, mat, loc, rot, uv=(0, 0, 1, 1)):
    """Plane facing -Y locally with a UV sub-rectangle (u0, v0, u1, v1) of its image."""
    o = plane(name, w, h, c, mat, loc=loc, rot=rot)
    u0, v0, u1, v1 = uv
    lay = o.data.uv_layers[0]
    for i, co in enumerate([(u0, v0), (u1, v0), (u1, v1), (u0, v1)]):
        lay.data[i].uv = co
    o["decal"] = True
    return o


POSTER_UV = [(0.0, 0.53, 0.33, 0.99), (0.35, 0.56, 0.66, 0.99), (0.68, 0.63, 0.99, 0.97),
             (0.0, 0.03, 0.33, 0.48), (0.35, 0.05, 0.66, 0.48), (0.69, 0.06, 0.99, 0.45)]


def street_detail(c):
    """Fascia shop boards, posters on pilasters, cables strung across the street."""
    # Fascia boards (shops closed: unlit, the street light picks them up). All names fictional.
    names = ["陳記五金", "榮記理髮", "祥興茶行", "德利電器", "金源海味", "聯昌士多", "利源印務", "寶安藥房", "振興車房", "華昌米行",
             "三和雜貨", "福來茶樓", "東成鐘錶", "新記燒臘"]
    cols = [(0.55, 0.06, 0.05), (0.05, 0.16, 0.35), (0.65, 0.5, 0.08), (0.08, 0.3, 0.14), (0.75, 0.72, 0.65)]
    ink = {0: (0.85, 0.75, 0.3), 1: (0.9, 0.9, 0.85), 2: (0.1, 0.05, 0.03), 3: (0.9, 0.85, 0.6), 4: (0.6, 0.05, 0.04)}
    k = 0
    for o in [o for o in bpy.data.objects if o.name.endswith("_fascia")]:
        lo = Vector([min((o.matrix_world @ Vector(v))[i] for v in o.bound_box) for i in range(3)])
        hi = Vector([max((o.matrix_world @ Vector(v))[i] for v in o.bound_box) for i in range(3)])
        if lo.y < STALL["y1"] + 1 and hi.y > STALL["y0"] - 1 and lo.x < 0:
            continue  # the stall's own wall has the awning
        side = -1 if lo.x < 0 else 1
        xf = hi.x if side < 0 else lo.x
        w = min(hi.y - lo.y - 0.6, 4.5)
        yc = (lo.y + hi.y) / 2
        ci = k % len(cols)
        bm = m_grimy(f"fascia_board_{ci}", cols[ci], 0.45, streak=0.5)
        a, b_ = sorted((xf, xf - side * 0.06))
        box(f"fascia_board_{k}", (a, yc - w / 2, 3.12), (b_, yc + w / 2, 3.64), c, bm, 0.006)
        rz = math.radians(90 if side < 0 else -90)
        text_obj(f"fascia_text_{k}", names[k % len(names)], c, (xf - side * 0.065, yc, 3.38), (math.radians(90), 0, rz), 0.36,
                 S_text_mat(ink[ci]), vertical=False, extrude=0.004, bevel=0.001)
        k += 1
    # Posters on the ground-floor pilasters (the pilaster faces the street).
    p = tex("hk_tex_posters")
    if p:
        pm = m_image_sign("posters_mat", p)
        j = 0
        for o in [o for o in bpy.data.objects if "_pil_" in o.name]:
            if rng.random() < 0.55:
                continue
            lo = Vector([min((o.matrix_world @ Vector(v))[i] for v in o.bound_box) for i in range(3)])
            hi = Vector([max((o.matrix_world @ Vector(v))[i] for v in o.bound_box) for i in range(3)])
            side = -1 if lo.x < 0 else 1
            xf = (hi.x + 0.003) if side < 0 else (lo.x - 0.003)
            uv = POSTER_UV[j % 6]
            asp = (uv[3] - uv[1]) / (uv[2] - uv[0])
            w = 0.34
            decal(f"poster_{j}", w, w * asp, c, pm, (xf, (lo.y + hi.y) / 2 + rng.uniform(-0.02, 0.02), rng.uniform(1.0, 1.6)),
                  (0, 0, math.radians(90 if side < 0 else -90) + rng.uniform(-0.04, 0.04)), uv)
            j += 1
    # Cables across the street (sagging catenaries) and along the facades.
    cm = m_simple("cable_black", (0.01, 0.01, 0.01), 0.35)
    for i, (y, z, dy, sag) in enumerate([(-6.5, 7.2, 1.0, 0.7), (2.5, 9.0, -0.6, 0.9), (8.5, 6.4, 0.5, 0.5),
                                          (15.0, 8.2, 1.2, 0.8), (22.0, 10.5, -0.8, 1.0), (-11.0, 9.6, 0.4, 0.8)]):
        cable(f"cable_x{i}", (FX0 + 0.1, y, z), (FX1 - 0.1, y + dy, z + rng.uniform(-0.6, 0.6)), sag, c, cm)
    for i, (x, y0, y1, z) in enumerate([(FX0 + 0.12, -12, 2, 4.0), (FX0 + 0.12, 7, 20, 4.2), (FX1 - 0.12, -10, 18, 4.1)]):
        cable(f"cable_f{i}", (x, y0, z), (x, y1, z + 0.2), 0.35, c, cm, r=0.012)


def S_text_mat(col):
    m, nt = new_mat(f"sign_ink_{col[0]:.2f}_{col[1]:.2f}")
    if nt:
        b = bsdf(nt)
        b.inputs["Base Color"].default_value = (*col, 1)
        b.inputs["Roughness"].default_value = 0.35
    return m


def cable(name, p0, p1, sag, c, mat, r=0.007, n=24):
    p0, p1 = Vector(p0), Vector(p1)
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = r
    cu.bevel_resolution = 2
    sp = cu.splines.new("POLY")
    sp.points.add(n)
    for i in range(n + 1):
        t = i / n
        q = p0.lerp(p1, t)
        q.z -= sag * 4 * t * (1 - t)
        sp.points[i].co = (q.x, q.y, q.z, 1)
    o = bpy.data.objects.new(name, cu)
    c.objects.link(o)
    cu.materials.append(mat)
    return o


def neon_signs(c):
    """Projecting signs on the facades above the street: neon text (tubes = emissive extruded text on a dark box)
    and backlit lightboxes from the generated textures. Every name is fictional."""
    frame = m_simple("sign_frame", (0.02, 0.02, 0.022), 0.45, 0.6)
    signs = []
    N = [  # text, side, y, z, glyph size, colour, strength
        ("夜來香", -1, 1.2, 5.6, 0.62, (1.0, 0.08, 0.12), 22),
        ("金滿樓", -1, 8.6, 6.4, 0.7, (1.0, 0.55, 0.12), 18),
        ("好運麻雀", -1, 14.8, 5.2, 0.55, (0.15, 0.9, 1.0), 20),
        ("大德藥行", 1, 4.5, 6.2, 0.6, (0.2, 1.0, 0.45), 16),
        ("新興旅館", 1, 11.5, 7.6, 0.66, (1.0, 0.25, 0.65), 20),
        ("福興茶餐廳", 1, 19.0, 5.8, 0.52, (1.0, 0.85, 0.3), 14),
        ("永昌押", -1, 22.5, 7.0, 0.72, (1.0, 0.12, 0.1), 18),
        ("美髮", 1, -3.0, 5.0, 0.5, (0.7, 0.3, 1.0), 16),
    ]
    for k, (txt, side, y, z, s, col, st) in enumerate(N):
        xf = FX0 if side < 0 else FX1
        sgn = 1 if side < 0 else -1
        w, h = s * 1.45, len(txt) * s * 0.92 + s * 0.4
        xc = xf + sgn * (0.35 + w / 2)
        bx = box(f"neon_box_{k}", (xc - w / 2, y - 0.09, z - h / 2), (xc + w / 2, y + 0.09, z + h / 2), c, frame, 0.01)
        mat = m_emit(f"neon_{k}", col, st)
        for face, ry in ((-1, 0), (1, 180)):
            t = text_obj(f"neon_{k}_{'f' if face < 0 else 'b'}", txt, c, (xc, y + face * 0.095, z), (math.radians(90), 0, math.radians(ry)), s, mat)
            signs.append(t)
        # Outline tube around the box face.
        for face in (-1, 1):
            yy = y + face * 0.1
            for (p0, p1) in (((xc - w / 2 + 0.04, z - h / 2 + 0.04), (xc + w / 2 - 0.04, z - h / 2 + 0.06)),
                             ((xc - w / 2 + 0.04, z + h / 2 - 0.06), (xc + w / 2 - 0.04, z + h / 2 - 0.04)),
                             ((xc - w / 2 + 0.04, z - h / 2 + 0.04), (xc - w / 2 + 0.06, z + h / 2 - 0.04)),
                             ((xc + w / 2 - 0.06, z - h / 2 + 0.04), (xc + w / 2 - 0.04, z + h / 2 - 0.04))):
                box(f"neon_{k}_edge", (p0[0], yy - 0.006, p0[1]), (p1[0], yy + 0.006, p1[1]), c, mat, 0)
        # Bracket to the wall.
        a, b_ = sorted((xf, xc - sgn * w / 2))
        box(f"neon_bracket_{k}", (a, y - 0.03, z + h / 2 - 0.1), (b_, y + 0.03, z + h / 2 - 0.04), c, frame, 0.004)
        bx["sign"] = txt
    # Lightboxes (generated art) closer to street level.
    LB = [("hk_tex_lightbox_a", 1, 1.8, 4.3), ("hk_tex_lightbox_b", -1, 11.2, 4.4), ("hk_tex_lightbox_c", 1, 15.8, 4.6)]
    for k, (tid, side, y, z) in enumerate(LB):
        p = tex(tid)
        if not p:
            continue
        xf = FX0 if side < 0 else FX1
        sgn = 1 if side < 0 else -1
        w, h = 0.95, 1.3
        xc = xf + sgn * (0.3 + w / 2)
        box(f"lightbox_{k}", (xc - w / 2, y - 0.12, z - h / 2), (xc + w / 2, y + 0.12, z + h / 2), c, frame, 0.01)
        m = m_lightbox(f"lightbox_{k}_mat", p)
        for face, ry in ((-1, 0), (1, 180)):
            plane(f"lightbox_{k}_{'f' if face < 0 else 'b'}", w - 0.06, h - 0.06, c, m,
                  loc=(xc, y + face * 0.125, z - h / 2 + 0.03), rot=(0, 0, math.radians(ry)))
    return signs


def build():
    c = coll("shell")
    st = coll("street")
    stc = coll("stall")
    sg = coll("signs")
    world()
    ground(st)
    facades(c)
    sky_card(c)
    stall_frame(stc)
    back_shelves(stc)
    neon_signs(sg)
    bpy.context.view_layer.update()
    street_detail(coll("street_detail"))
    bpy.context.view_layer.update()
