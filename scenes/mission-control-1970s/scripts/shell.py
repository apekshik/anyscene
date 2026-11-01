"""Room shell: tiered floor, walls with the window band, back door, ceiling grid with troffers, wall-display frame,
outside launch-pad backdrop. Object names here are referenced by lights, shots and the validator."""
import math
import os

import bpy

import layout as L
import lib
from lib import box, collection, plane

TEX = os.path.join(lib.ROOT, "refs", "mission-control-1970s", "tex")
M = {}


def carpet(name, base=(0.075, 0.085, 0.1), tile=0.6):
    """Low-pile carpet tiles: fibre noise, slight per-tile tone shift, traffic wear in the lanes."""
    m, nt = lib._new(name)
    if nt is None:
        return m
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    fib = lib._noise(nt, 900, 2, tc.outputs["Object"])
    ch = nt.nodes.new("ShaderNodeTexChecker")
    ch.inputs["Scale"].default_value = 1 / tile
    ch.inputs["Color1"].default_value = (1, 1, 1, 1)
    ch.inputs["Color2"].default_value = (0.86, 0.86, 0.86, 1)
    nt.links.new(tc.outputs["Object"], ch.inputs["Vector"])
    wear = lib._noise(nt, 0.7, 6, tc.outputs["Object"])
    wr = lib._ramp(nt, wear.outputs["Fac"], [(0.35, (0.75, 0.75, 0.75)), (0.7, (1.15, 1.12, 1.08))])
    col = lib._mix(nt, 1.0, base, ch.outputs["Color"], "MULTIPLY")
    col = lib._mix(nt, 1.0, col, wr.outputs["Color"], "MULTIPLY")
    col = lib._mix(nt, 0.25, col, fib.outputs["Color"], "OVERLAY")
    nt.links.new(col, b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.95
    b.inputs["Sheen Weight"].default_value = 0.4
    nt.links.new(lib._bump(nt, fib.outputs["Fac"], 0.35, 0.001), b.inputs["Normal"])
    return m


def ceiling_tiles(name):
    """Acoustic 2x4 ft lay-in tiles in a white T-bar grid, pinhole fissure speckle, nicotine yellowing."""
    m, nt = lib._new(name)
    if nt is None:
        return m
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.offset = 0.0
    br.squash = 1.0
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Brick Width"].default_value = 1.2
    br.inputs["Row Height"].default_value = 0.6
    br.inputs["Mortar Size"].default_value = 0.012
    br.inputs["Color1"].default_value = (0.62, 0.6, 0.53, 1)
    br.inputs["Color2"].default_value = (0.58, 0.56, 0.49, 1)
    br.inputs["Mortar"].default_value = (0.7, 0.7, 0.68, 1)
    nt.links.new(tc.outputs["Object"], br.inputs["Vector"])
    pin = lib._noise(nt, 300, 2, tc.outputs["Object"])
    pr = lib._ramp(nt, pin.outputs["Fac"], [(0.62, (1, 1, 1)), (0.7, (0.55, 0.55, 0.55))])
    stain = lib._noise(nt, 0.6, 6, tc.outputs["Object"])
    sr = lib._ramp(nt, stain.outputs["Fac"], [(0.5, (1, 1, 1)), (0.75, (0.72, 0.62, 0.42))])
    col = lib._mix(nt, 1.0, br.outputs["Color"], pr.outputs["Color"], "MULTIPLY")
    col = lib._mix(nt, 1.0, col, sr.outputs["Color"], "MULTIPLY")
    nt.links.new(col, b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.92
    nt.links.new(lib._bump(nt, br.outputs["Fac"], 0.4, 0.004), b.inputs["Normal"])
    return m


def troffer_lens(name, on):
    """Prismatic acrylic diffuser: a fine square-pyramid bump; emissive when on (strength set by lights.py)."""
    m, nt = lib._new(name)
    if nt is None:
        return m
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.78, 0.8, 0.78, 1)
    b.inputs["Roughness"].default_value = 0.35
    b.inputs["Transmission Weight"].default_value = 0.0
    tc = nt.nodes.new("ShaderNodeTexCoord")
    ch = nt.nodes.new("ShaderNodeTexWave")
    ch.inputs["Scale"].default_value = 120
    nt.links.new(tc.outputs["Object"], ch.inputs["Vector"])
    nt.links.new(lib._bump(nt, ch.outputs["Fac"], 0.2, 0.001), b.inputs["Normal"])
    if on:
        b.inputs["Emission Color"].default_value = (0.92, 0.97, 1.0, 1)
        b.inputs["Emission Strength"].default_value = 6.0
    return m


def materials():
    M["carpet"] = carpet("carpet_tiles")
    M["vinyl"] = lib.floor_tiles("vinyl_tiles", tile=0.3, a=(0.42, 0.41, 0.37), b2=(0.36, 0.35, 0.32))
    M["wall"] = lib.wall_paint("wall_paint", base=(0.5, 0.49, 0.44))
    M["wall_dark"] = lib.grimy("display_wall", (0.035, 0.038, 0.04), (0.02, 0.02, 0.02), rough=(0.5, 0.8), amount=0.2)
    M["acoustic"] = lib.grimy("acoustic_panel", (0.23, 0.2, 0.17), (0.12, 0.1, 0.08), rough=(0.85, 0.95), amount=0.25, scale=6, bump=0.3)
    M["ceiling"] = ceiling_tiles("ceiling_tiles")
    M["alu"] = lib.grimy("aluminium", (0.55, 0.56, 0.57), (0.22, 0.21, 0.19), rough=(0.3, 0.5), metal=1.0, amount=0.2, bump=0.05)
    M["tbar"] = lib.principled("tbar_white", (0.72, 0.72, 0.7), 0.4)
    M["glass"] = lib.principled("window_glass", (0.92, 0.95, 0.95), 0.015, **{"Transmission Weight": 1.0, "IOR": 1.5})
    M["door"] = lib.grimy("door_paint", (0.3, 0.32, 0.3), (0.12, 0.11, 0.1), rough=(0.4, 0.7), amount=0.3)
    M["base"] = lib.principled("baseboard", (0.04, 0.04, 0.04), 0.6)
    M["nosing"] = lib.grimy("stair_nosing", (0.45, 0.45, 0.43), (0.12, 0.11, 0.1), rough=(0.35, 0.6), metal=1.0, amount=0.35)
    M["bezel"] = lib.principled("display_bezel", (0.025, 0.025, 0.027), 0.45)
    M["blind"] = lib.grimy("blind_slats", (0.6, 0.58, 0.52), (0.3, 0.27, 0.2), rough=(0.4, 0.6), metal=0.2, amount=0.25)
    M["tr_off"] = troffer_lens("troffer_off", False)
    M["tr_on"] = troffer_lens("troffer_on", True)
    M["tr_dim"] = troffer_lens("troffer_dim", True)
    M["tr_dim"].node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 1.5
    M["tr_frame"] = lib.principled("troffer_frame", (0.7, 0.7, 0.68), 0.35, Metallic=0.3)
    M["black"] = lib.principled("sign_black", (0.015, 0.015, 0.015), 0.4)
    M["sign_text"] = lib.principled("sign_text", (0.85, 0.85, 0.8), 0.5)


TROFFERS_ON = {(1, 2): "tr_on", (2, 4): "tr_on", (3, 0): "tr_on", (3, 2): "tr_dim", (0, 3): "tr_on"}  # (col, row) -> state


def build():
    materials()
    C = collection("shell")
    W, D, H, T = L.W, L.D, L.H, L.T
    # floor tiers (tier slabs are separate objects so the validator / drops see the right top)
    box("floor_t0", (-T, -T, -0.1), (W + T, D + T, 0.0), M["carpet"], C, bevel=0)
    box("floor_t1", (0, 4.5, 0.0), (W, 7.5, 0.35), M["carpet"], C, bevel=0)
    box("floor_t2", (0, 0.0, 0.0), (W, 4.5, 0.7), M["carpet"], C, bevel=0)
    box("nosing_t1", (0, 7.47, 0.33), (W, 7.52, 0.352), M["nosing"], C, bevel=0.003)
    box("nosing_t2", (0, 4.47, 0.68), (W, 4.52, 0.702), M["nosing"], C, bevel=0.003)
    for side, (x0, x1) in (("l", L.AISLE_L), ("r", L.AISLE_R)):  # two 175 mm steps at each riser in each aisle
        box(f"step_t1_{side}", (x0, 7.5, 0.0), (x1, 7.8, 0.175), M["carpet"], C, bevel=0.004)
        box(f"step_t2_{side}", (x0, 4.5, 0.35), (x1, 4.8, 0.525), M["carpet"], C, bevel=0.004)
        box(f"stepnose_t1_{side}", (x0, 7.77, 0.16), (x1, 7.81, 0.177), M["nosing"], C, bevel=0.002)
        box(f"stepnose_t2_{side}", (x0, 4.77, 0.51), (x1, 4.81, 0.527), M["nosing"], C, bevel=0.002)
    box("ceiling", (-T, -T, H), (W + T, D + T, H + 0.05), M["ceiling"], C, bevel=0)

    # left wall with the window band
    box("wall_left_low", (-T, 0, -0.1), (0, D, L.WIN_Z0), M["wall"], C, bevel=0)
    box("wall_left_high", (-T, 0, L.WIN_Z1), (0, D, H), M["wall"], C, bevel=0)
    box("wall_left_a", (-T, 0, L.WIN_Z0), (0, L.WIN_Y0, L.WIN_Z1), M["wall"], C, bevel=0)
    box("wall_left_b", (-T, L.WIN_Y1, L.WIN_Z0), (0, D, L.WIN_Z1), M["wall"], C, bevel=0)
    box("sill", (-T, L.WIN_Y0, L.WIN_Z0 - 0.03), (0.08, L.WIN_Y1, L.WIN_Z0), M["alu"], C, bevel=0.004)
    n = 5
    step = (L.WIN_Y1 - L.WIN_Y0) / n
    for i in range(n + 1):
        y = L.WIN_Y0 + i * step
        box(f"mullion_{i}", (-0.12, y - 0.04, L.WIN_Z0), (-0.04, y + 0.04, L.WIN_Z1), M["alu"], C, bevel=0.004)
    box("transom", (-0.12, L.WIN_Y0, L.WIN_Z1 - 0.06), (-0.04, L.WIN_Y1, L.WIN_Z1), M["alu"], C, bevel=0.004)
    box("window_glass", (-0.085, L.WIN_Y0, L.WIN_Z0), (-0.075, L.WIN_Y1, L.WIN_Z1), M["glass"], C, bevel=0.002)
    # venetian blinds: half the panes have blinds partly down (slats tilted), the rest raised in a stack
    for i in range(n):
        y0, y1 = L.WIN_Y0 + i * step + 0.06, L.WIN_Y0 + (i + 1) * step - 0.06
        drop = [0.55, 0.0, 1.0, 0.0, 0.35][i]
        box(f"blind_head_{i}", (0.0, y0, L.WIN_Z1 - 0.1), (0.05, y1, L.WIN_Z1 - 0.04), M["blind"], C, bevel=0.003)
        nsl = int(drop / 0.045)
        for k in range(nsl):
            z = L.WIN_Z1 - 0.12 - k * 0.045
            s = box(f"blind_{i}_{k}", (-0.012, y0, z - 0.0005), (0.012, y1, z + 0.0005), M["blind"], C, bevel=0)
            s.rotation_euler = (0, math.radians(55), 0)
        stack = 0.08 if nsl else 0.14
        box(f"blind_stack_{i}", (-0.01, y0, L.WIN_Z1 - 0.1 - stack - nsl * 0.045), (0.03, y1, L.WIN_Z1 - 0.1 - nsl * 0.045), M["blind"], C, bevel=0.002)

    # right and back walls; front wall is the dark display wall
    box("wall_right", (W, 0, -0.1), (W + T, D, H), M["wall"], C, bevel=0)
    box("wall_back_a", (-T, -T, -0.1), (L.DOOR_X0, 0, H), M["wall"], C, bevel=0)
    box("wall_back_b", (L.DOOR_X1, -T, -0.1), (W + T, 0, H), M["wall"], C, bevel=0)
    box("wall_back_c", (L.DOOR_X0, -T, L.DOOR_Z1), (L.DOOR_X1, 0, H), M["wall"], C, bevel=0)
    box("wall_front", (-T, D, -0.1), (W + T, D + T, H), M["wall_dark"], C, bevel=0)
    # acoustic panel band on the right wall and the back wall (period fabric panels)
    box("acoustic_right", (W - 0.03, 0.4, 1.0), (W, D - 0.4, 2.9), M["acoustic"], C, bevel=0.005)
    box("acoustic_back_a", (0.3, 0, 1.4), (L.DOOR_X0 - 0.4, 0.03, 2.9), M["acoustic"], C, bevel=0.005)
    box("acoustic_back_b", (L.DOOR_X1 + 0.4, 0, 1.4), (W - 0.3, 0.03, 2.9), M["acoustic"], C, bevel=0.005)
    for nm, lo, hi in (("base_right", (W - 0.012, 0, 0), (W, D, 0.1)), ("base_front", (0, D - 0.012, 0), (W, D, 0.1))):
        box(nm, lo, hi, M["base"], C, bevel=0)
    # back door: two leaves with small wired-glass windows, push bars, exit sign above
    zf = L.TIERS[2][0]
    for i, (x0, x1) in enumerate(((L.DOOR_X0, 5.5), (5.5, L.DOOR_X1))):
        box(f"door_leaf_{i}", (x0 + 0.005, -0.06, zf), (x1 - 0.005, -0.015, L.DOOR_Z1 - 0.01), M["door"], C, bevel=0.004)
        box(f"door_bar_{i}", (x0 + 0.08, -0.012, zf + 1.0), (x1 - 0.08, 0.02, zf + 1.04), M["alu"], C, bevel=0.003)
        box(f"door_window_{i}", (x0 + 0.17, -0.015, zf + 1.35), (x1 - 0.17, -0.01, zf + 1.85), M["glass"], C, bevel=0.002)
    box("door_frame_top", (L.DOOR_X0 - 0.05, -0.02, L.DOOR_Z1 - 0.01), (L.DOOR_X1 + 0.05, 0.02, L.DOOR_Z1 + 0.05), M["alu"], C, bevel=0.003)
    box("exit_sign_box", (5.3, 0.0, L.DOOR_Z1 + 0.12), (5.7, 0.09, L.DOOR_Z1 + 0.32), M["black"], C, bevel=0.004)

    # ceiling grid troffers: 4 columns x 5 rows, a few on
    CT = collection("ceiling_fixtures")
    for ci, x in enumerate((1.8, 4.2, 6.6, 9.0)):
        for ri, y in enumerate((1.6, 4.1, 6.6, 9.1, 11.6)):
            st = TROFFERS_ON.get((ci, ri), "tr_off")
            box(f"troffer_{ci}_{ri}", (x - 0.31, y - 0.61, H - 0.035), (x + 0.31, y + 0.61, H), M["tr_frame"], CT, bevel=0.003)
            lens = box(f"troffer_lens_{ci}_{ri}", (x - 0.28, y - 0.58, H - 0.04), (x + 0.28, y + 0.58, H - 0.034), M[st], CT, bevel=0)
            lens["state"] = st
    # air diffusers (square) between the troffers
    for x, y in ((3.0, 2.85), (7.8, 2.85), (3.0, 7.85), (7.8, 7.85), (5.4, 10.4)):
        box(f"diffuser_{x}_{y}", (x - 0.3, y - 0.3, H - 0.02), (x + 0.3, y + 0.3, H), M["tbar"], CT, bevel=0.004)

    # wall display: bezel box + three screens (materials replaced by fixscreens.py; emissive)
    CD = collection("display")
    box("display_bezel", (1.15, D - 0.16, L.DISP_Z0 - 0.15), (10.35, D, L.DISP_Z1 + 0.12), M["bezel"], CD, bevel=0.01)
    for name, x0, x1 in L.DISP_PANELS:
        p = plane(f"disp_{name}", ((x0 + x1) / 2, D - 0.165, (L.DISP_Z0 + L.DISP_Z1) / 2), x1 - x0, L.DISP_Z1 - L.DISP_Z0, "-Y", M["black"], CD)
        p["screen"] = name
    box("display_ledge", (1.1, D - 0.5, 0.0), (10.4, D - 0.16, 0.85), M["bezel"], CD, bevel=0.01)

    # outside: night launch-pad backdrop far beyond the windows, a dark ground plane below the sill line
    CX = collection("outside")
    lp = os.path.join(TEX, "launch_pad_0.png")
    if os.path.exists(lp):
        mat = lib.image_mat("backdrop_launchpad", lp, rough=1.0, emission=2.2, extend="EXTEND")
        # horizon (52 % up the image) near eye height, the rocket (68 % across) out past the middle windows
        b = plane("backdrop", (-45, -3.4, 1.63), 72, 40.5, "X", mat, CX)
        lib.set_uv_rect(b, -1, -1, 2, 2)  # image in the middle third; EXTEND runs sky and marsh out past the window edges
        b.visible_shadow = False
    g = box("outside_ground", (-80, -40, -6.0), (-0.25, 50, -5.9), lib.principled("ground_dark", (0.01, 0.012, 0.012), 0.9), CX, bevel=0)
    g.visible_shadow = False
