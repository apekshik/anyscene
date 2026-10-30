"""Round-2 generated assets, applied to the *mirrored* scene (world coordinates), so the same code patches the saved
ramen_r2.blend (keeping its baked steam caches) and runs at the end of build.py.

textures(): brighter street backdrop, image neon signs, alpha-keyed decals (hood drips, backsplash splatter,
counter rings, floor grime, fingerprints), generated flyers / price strips / sticker sheet replacing the
text-object versions, a peeling winter-special poster.
props(): round-2 picks placed with dress.place in MIRROR mode, swapping out the reused round-1 instances."""
import math
import os
import random

import bpy
from mathutils import Matrix, Vector

import clutter
import dress
import shell as S
from lib import L, TEX, bsdf, coll, mathn, new_mat

W = S.W
rng = random.Random(23)


def wx(design_x):
    return W - design_x


# ------------------------------------------------------------------ materials

def _img(name):
    return bpy.data.images.load(os.path.join(TEX, f"{name}_0.png"), check_existing=True)


def m_decal(name, tex, key="white", color_mul=(1, 1, 1), rough=0.6, gain=1.6, gloss_coat=0.0, uv_rect=None):
    """Image decal; alpha keyed from luminance: key='white' (dark marks on white) or 'black' (light marks on black)."""
    m, nt = new_mat(name)
    if not nt:
        return m
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = _img(tex)
    t.extension = "CLIP"
    if uv_rect:
        uv = nt.nodes.new("ShaderNodeTexCoord")
        mp = nt.nodes.new("ShaderNodeMapping")
        (u0, v0), (u1, v1) = uv_rect
        mp.inputs["Location"].default_value = (u0, v0, 0)
        mp.inputs["Scale"].default_value = (u1 - u0, v1 - v0, 1)
        L(nt, uv.outputs["UV"], mp.inputs["Vector"])
        L(nt, mp.outputs[0], t.inputs["Vector"])
    bw = nt.nodes.new("ShaderNodeRGBToBW")
    L(nt, t.outputs["Color"], bw.inputs[0])
    a = bw.outputs[0] if key == "black" else mathn(nt, "SUBTRACT", 1.0, bw.outputs[0])
    a = mathn(nt, "MULTIPLY", mathn(nt, "SUBTRACT", a, 0.06), gain, clamp=True)
    b = bsdf(nt)
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    mul.inputs["B"].default_value = (*color_mul, 1)
    L(nt, t.outputs["Color"], mul.inputs["A"])
    L(nt, mul.outputs["Result"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = rough
    b.inputs["Coat Weight"].default_value = gloss_coat
    L(nt, a, b.inputs["Alpha"])
    return m


def m_print(name, tex, rough=0.8, emission=0.0, uv_rect=None, key=None):
    """Printed paper / backlit sign: plain image material (optional emission, optional white key)."""
    m, nt = new_mat(name)
    if not nt:
        return m
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = _img(tex)
    if uv_rect:
        uv = nt.nodes.new("ShaderNodeTexCoord")
        mp = nt.nodes.new("ShaderNodeMapping")
        (u0, v0), (u1, v1) = uv_rect
        mp.inputs["Location"].default_value = (u0, v0, 0)
        mp.inputs["Scale"].default_value = (u1 - u0, v1 - v0, 1)
        L(nt, uv.outputs["UV"], mp.inputs["Vector"])
        L(nt, mp.outputs[0], t.inputs["Vector"])
    b = bsdf(nt)
    L(nt, t.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = rough
    if emission:
        L(nt, t.outputs["Color"], b.inputs["Emission Color"])
        b.inputs["Emission Strength"].default_value = emission
    if key == "white":
        bw = nt.nodes.new("ShaderNodeRGBToBW")
        L(nt, t.outputs["Color"], bw.inputs[0])
        L(nt, mathn(nt, "MULTIPLY", mathn(nt, "SUBTRACT", 0.97, bw.outputs[0]), 25.0, clamp=True), b.inputs["Alpha"])
    if key == "black":
        bw = nt.nodes.new("ShaderNodeRGBToBW")
        L(nt, t.outputs["Color"], bw.inputs[0])
        L(nt, mathn(nt, "MULTIPLY", bw.outputs[0], 6.0, clamp=True), b.inputs["Alpha"])
    return m


def decal(c, name, mat, w, h, origin, direction, up=(0, 0, 1), spin=0.0, offset=0.0015, res=(2, 2), curl=0.0):
    p = clutter.paper(name, w, h, c, mat, curl=curl, res=res)
    for mod in list(p.modifiers):
        p.modifiers.remove(mod)  # decals are zero-thickness films
    if not clutter.stick(p, origin, direction, up, offset):
        bpy.data.objects.remove(p)
        return None
    if spin:
        p.matrix_world = p.matrix_world @ Matrix.Rotation(math.radians(spin), 4, "Z")
    p.visible_shadow = False
    return p


def _remove_with_children(o):
    for ch in list(o.children_recursive):
        bpy.data.objects.remove(ch)
    bpy.data.objects.remove(o)


# ------------------------------------------------------------------ textures pass

def textures():
    c = coll("r2_textures", bpy.data.collections["ramen"])
    # Brighter, richer street photo behind the door/window.
    bd = bpy.data.objects.get("street_backdrop")
    if bd and os.path.exists(os.path.join(TEX, "street_backdrop2_nb_0.png")):
        for n in bd.data.materials[0].node_tree.nodes:
            if n.type == "TEX_IMAGE":
                n.image = _img("street_backdrop2_nb")
            if n.type == "EMISSION":
                n.inputs["Strength"].default_value = 1.3
    # Neon: image signs (glowing, black keyed out) in place of the text-object neon.
    for old, tex, w, h, em in (("neon_izakaya", "neon_sign_a", 0.62, 0.83, 6.0), ("neon_snack", "neon_sign_b", 0.5, 0.67, 5.0)):
        o = bpy.data.objects.get(old)
        if not o:
            continue
        loc = o.matrix_world.translation.copy()
        box = bpy.data.objects.get(old + "_box")
        bpy.data.objects.remove(o)
        if box:
            bpy.data.objects.remove(box)
        s = clutter.paper(old + "_img", w, h, c, m_print(old + "_img", tex, 0.4, emission=em, key="black"), res=(1, 1))
        for mod in list(s.modifiers):
            s.modifiers.remove(mod)
        # Face +Y (toward the shop), upright.
        # Local +Z (front) -> world +Y, local +Y (up) -> world +Z, local +X -> world -X (viewer's right).
        s.matrix_world = Matrix.Translation(loc) @ Matrix(((-1, 0, 0), (0, 0, 1), (0, 1, 0))).transposed().to_4x4()
    # Grease drips down the hood front (faces the customers: world +X at x = 0.75).
    drips = m_decal("decal_drips", "decal_grease_drips", key="black", color_mul=(0.55, 0.38, 0.18), rough=0.15, gain=2.2, gloss_coat=0.6)
    for y in (3.9, 4.9):
        decal(c, "decal_drips", drips, 1.0, 0.42, (1.3, y, 2.1), (-1, 0, 0))
    # Oil splatter on the backsplash behind the range and boiler.
    spl = m_decal("decal_splatter", "decal_grease_splatter", key="white", color_mul=(0.32, 0.24, 0.17), rough=0.25, gain=0.5, gloss_coat=0.4)  # 1.4 read as orange wallpaper
    for y, z, sp in ((3.75, 1.2, 0), (4.6, 1.3, 90), (5.4, 1.15, 200)):
        decal(c, "decal_splatter", spl, 0.75, 0.75, (0.6, y, z), (-1, 0, 0), spin=sp)
    # Rings from bowls and glasses on the counter between the place settings.
    rings = m_decal("decal_rings", "decal_rings", key="white", color_mul=(0.55, 0.42, 0.3), rough=0.35, gain=0.55)  # subtle
    for y in (2.55, 3.95, 4.8, 5.85):
        decal(c, "decal_rings", rings, 0.28, 0.28, (2.3, y, 1.6), (0, 0, -1), up=(1, 0, 0), spin=rng.uniform(0, 360), offset=0.0008)
    # Footprints and grime on the floor: customer aisle and kitchen aisle.
    grime = m_decal("decal_floor", "decal_floor_grime", key="white", color_mul=(0.5, 0.45, 0.4), rough=0.8, gain=1.1)
    for x, y in ((2.85, 0.9), (2.95, 2.3), (2.8, 3.9), (3.0, 5.3), (0.85, 2.2), (0.85, 4.3), (0.8, 5.9)):
        decal(c, "decal_floor", grime, 0.9, 0.9, (x, y, 0.4), (0, 0, -1), up=(0, 1, 0), spin=rng.uniform(0, 360), offset=0.0008)
    # Fingerprints on the door glass, the window and the drink fridge door.
    fp = m_decal("decal_fingerprints", "decal_fingerprints", key="black", color_mul=(0.9, 0.9, 0.9), rough=0.5, gain=0.8)
    decal(c, "decal_fp", fp, 0.35, 0.35, (2.6, 0.8, 1.15), (0, -1, 0), offset=0.004)
    decal(c, "decal_fp", fp, 0.3, 0.3, (2.15, 0.8, 1.05), (0, -1, 0), offset=0.004)
    fr = bpy.data.objects.get("ramen_drink_fridge")
    if fr:
        ctr = sum((fr.matrix_world @ Vector(cc) for cc in fr.bound_box), Vector()) / 8
        decal(c, "decal_fp", fp, 0.3, 0.3, (ctr.x - 0.8, ctr.y, 1.1), (1, 0, 0), offset=0.012)
    # Generated flyers onto the existing (curled, pinned) flyer sheets.
    for name, tex in (("flyer_parttime", "flyer_parttime"), ("flyer_lostcat", "flyer_lostcat"), ("flyer_festival", "flyer_festival")):
        f = bpy.data.objects.get(name)
        if not f:
            continue
        for ch in list(f.children):
            if ch.type == "FONT" or ch.data.materials and ch.data.materials[0].name.startswith("photo"):
                bpy.data.objects.remove(ch)
        f.data.materials.clear()
        f.data.materials.append(m_print(name + "_img", tex, 0.85))
    # Price strips: one generated strip photo in place of the eight text strips.
    strips = [o for o in bpy.data.objects if o.name.startswith("price_strip")]
    if strips:
        ctr = sum((o.matrix_world.translation for o in strips), Vector()) / len(strips)
        for o in strips:
            _remove_with_children(o)
        decal(c, "price_strips", m_print("price_strips_img", "price_strips", 0.8), 0.72, 0.405, (ctr.x - 0.5, ctr.y, ctr.z), (1, 0, 0), curl=0.01, res=(8, 4))
    # Sticker sheet: each old sticker becomes one cell of the generated sheet (4 x 2 grid), keyed off white.
    old = [o for o in bpy.data.objects if o.name.startswith("sticker")]
    cells = [((i % 4) / 4, 1 - (i // 4 + 1) / 2) for i in range(8)]
    for i, o in enumerate(old):
        mw = o.matrix_world.copy()
        _remove_with_children(o)
        (u0, v0) = cells[i % 8]
        m = m_print(f"sticker_cell{i}", "stickers_sheet_nb", 0.45, uv_rect=((u0, v0), (u0 + 0.25, v0 + 0.5)), key="white")
        s = clutter.paper(f"sticker_img{i}", 0.085, 0.17, c, m, res=(2, 2), curl=0.01 if i == 2 else 0.0)
        for mod in list(s.modifiers):
            s.modifiers.remove(mod)
        s.matrix_world = mw
    # Peeling winter-special poster on the customer wall (world x = W, facing -X).
    decal(c, "poster_special", m_print("poster_special_img", "poster_menu_special", 0.75), 0.36, 0.48, (3.0, 3.75, 1.4), (1, 0, 0), curl=0.05, res=(10, 12))
    print("r2gen: textures applied", flush=True)


# ------------------------------------------------------------------ props pass

# Direct-modelled object name prefix -> the generated prop that replaces it (only removed if that pick exists).
REPLACED = {"tongs": "ramen_tongs", "coin_": "ramen_coins", "tape_roll": "ramen_tape_roll", "power_strip": "ramen_power_strip",
            "cat_placemat": "ramen_cat_dish", "pet_bowl": "ramen_cat_dish", "wall_hook": "ramen_hook_items",
            "key_ring": "ramen_hook_items", "plastic_bag": "ramen_hook_items", "vending_body": "ramen_vending_machine",
            "vending_display": "ramen_vending_machine", "vending_header": "ramen_vending_machine", "vending_slot": "ramen_vending_machine"}


def props():
    import emitters
    import grime
    import validate
    root = bpy.data.collections["ramen"]
    # 1. Drop the round-1 reuse pass (props_a) and the direct-modelled pieces that now have generated versions.
    old_a = bpy.data.collections.get("props_a")
    if old_a:
        for o in list(old_a.all_objects):
            if o.name in bpy.data.objects:
                _remove_with_children(o)
    for o in list(bpy.data.objects):
        if o.name not in bpy.data.objects or o.parent is not None:
            continue
        mats = [m.name for m in o.data.materials if m] if o.type == "MESH" else []
        pid = next((v for k, v in REPLACED.items() if o.name.startswith(k)), None)
        if pid is None and "key_metal" in mats:
            pid = "ramen_hook_items"
        if pid and dress._have(pid):
            _remove_with_children(o)
    # 2. Place the round-2 picks in the mirrored scene.
    dress.MIRROR = True
    dress.PLACED.clear()
    dress.pass_a2(coll("props_a2", root))
    dress.pass_bc_gen(coll("props_bc2", root))
    placed = list(dress.PLACED)
    dress.MIRROR = False
    # 3. Same housekeeping the build does: dense emitters, grime on the new materials, validation.
    emitters.run()
    for o, _ in placed:
        for m in o.data.materials:
            if m and not m.get("grimed") and not any(k in m.name.lower() for k in ("glass", "fridge", "vending")):
                grime.overlay(m, ao=0.6, dust=0.35)
    from lib import SCENE_DIR
    validate.run(placed, os.path.join(SCENE_DIR, "out", "validate_r2gen.txt"))
    print("r2gen: props placed", len(placed), flush=True)
    return placed


def apply():
    textures()
    props()
