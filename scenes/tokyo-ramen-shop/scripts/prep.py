"""Prep the picked generated props into scenes/tokyo-ramen-shop/lib/<id>.blend.

Per prop: import GLB -> join -> turn so its front faces -Y (Tripo fronts face +X) -> scale to the manifest size
-> origin at bottom centre -> decimate to a tri budget -> cap texture size -> material fixes (glass, glow, gloss) -> save.

blender -b --factory-startup --python scenes/tokyo-ramen-shop/scripts/prep.py -- [--only id,id]
"""
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(__file__))
from lib import L, SCENE_DIR, ROOT  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ONLY = argv[argv.index("--only") + 1].split(",") if "--only" in argv else None
MAN = {p["id"]: p for p in json.load(open(os.path.join(SCENE_DIR, "assets.json")))["generate"]}
PICKS = json.load(open(os.path.join(SCENE_DIR, "picks.json")))
LIB = os.path.join(SCENE_DIR, "lib")
os.makedirs(LIB, exist_ok=True)
YAW = {"tripo-h31": -90, "meshy": 0}  # degrees about Z that bring each generator's front to -Y

# Tri budgets: props the hero cameras see up close get more.
HERO = {"ramen_bowl_unfinished", "condiment_caddy", "ramen_water_glass", "ramen_chopstick_cup", "stockpot",
        "ticket_machine", "ramen_stool", "ramen_tare_containers", "ramen_cutting_board", "ramen_noodle_boiler", "lantern"}
TEX_4K = {"ticket_machine", "ramen_drink_fridge", "lantern"}


# ------------------------------------------------------------------ material fixes

def principled(m):
    return next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)


def base_tex(m):
    b = principled(m)
    s = b.inputs["Base Color"]
    return s.links[0].from_node if s.is_linked else None


def fx_coat(o, w=0.5, r=0.06):
    """Glazed ceramic / lacquer: clear coat over the baked albedo."""
    for m in o.data.materials:
        b = principled(m)
        b.inputs["Coat Weight"].default_value = w
        b.inputs["Coat Roughness"].default_value = r


def fx_glassy(o, rough=0.06):
    """Glass bottles with opaque contents baked into the texture: keep the albedo, add a glossy glass-like coat."""
    for m in o.data.materials:
        b = principled(m)
        b.inputs["Coat Weight"].default_value = 1.0
        b.inputs["Coat Roughness"].default_value = 0.02
        b.inputs["Coat IOR"].default_value = 1.5
        b.inputs["Specular IOR Level"].default_value = 0.7
        if not b.inputs["Roughness"].is_linked:
            b.inputs["Roughness"].default_value = rough


def fx_clear_glass(o):
    """Whole object is clear glass (water glass): replace the baked material with real glass + faint tint."""
    m = bpy.data.materials.new("clear_glass")
    m.use_nodes = True
    b = principled(m)
    b.inputs["Base Color"].default_value = (0.92, 0.96, 0.95, 1)
    b.inputs["Roughness"].default_value = 0.015
    b.inputs["Transmission Weight"].default_value = 1.0
    b.inputs["IOR"].default_value = 1.5
    o.data.materials.clear()
    o.data.materials.append(m)


def _front_mask(nt, zmin, zmax, facing=0.5):
    """1 where the surface faces local -Y (the prop's front) and object-space z is within [zmin, zmax]."""
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    vt = nt.nodes.new("ShaderNodeVectorTransform")
    vt.vector_type = "NORMAL"
    vt.convert_from = "WORLD"
    vt.convert_to = "OBJECT"
    L(nt, geo.outputs["Normal"], vt.inputs[0])
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    dot.inputs[1].default_value = (0, -1, 0)
    L(nt, vt.outputs[0], dot.inputs[0])
    gt = nt.nodes.new("ShaderNodeMath")
    gt.operation = "GREATER_THAN"
    gt.inputs[1].default_value = facing
    L(nt, dot.outputs["Value"], gt.inputs[0])
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    L(nt, tc.outputs["Object"], sep.inputs[0])
    lo = nt.nodes.new("ShaderNodeMath")
    lo.operation = "GREATER_THAN"
    lo.inputs[1].default_value = zmin
    L(nt, sep.outputs["Z"], lo.inputs[0])
    hi = nt.nodes.new("ShaderNodeMath")
    hi.operation = "LESS_THAN"
    hi.inputs[1].default_value = zmax
    L(nt, sep.outputs["Z"], hi.inputs[0])
    a = nt.nodes.new("ShaderNodeMath")
    a.operation = "MULTIPLY"
    L(nt, lo.outputs[0], a.inputs[0])
    L(nt, hi.outputs[0], a.inputs[1])
    b = nt.nodes.new("ShaderNodeMath")
    b.operation = "MULTIPLY"
    L(nt, a.outputs[0], b.inputs[0])
    L(nt, gt.outputs[0], b.inputs[1])
    return b.outputs[0]


def fx_front_glow(o, strength, zmin, zmax, gamma=2.2):
    """Backlit panel (ticket buttons, fridge interior): emit the albedo, brightest where the texture is light."""
    for m in o.data.materials:
        nt = m.node_tree
        tex = base_tex(m)
        b = principled(m)
        if tex is None:
            continue
        pw = nt.nodes.new("ShaderNodeMath")
        pw.operation = "POWER"
        bw = nt.nodes.new("ShaderNodeRGBToBW")
        L(nt, tex.outputs["Color"], bw.inputs[0])
        L(nt, bw.outputs[0], pw.inputs[0])
        pw.inputs[1].default_value = gamma
        mask = _front_mask(nt, zmin, zmax)
        k = nt.nodes.new("ShaderNodeMath")
        k.operation = "MULTIPLY"
        L(nt, pw.outputs[0], k.inputs[0])
        L(nt, mask, k.inputs[1])
        s = nt.nodes.new("ShaderNodeMath")
        s.operation = "MULTIPLY"
        s.inputs[1].default_value = strength
        L(nt, k.outputs[0], s.inputs[0])
        L(nt, tex.outputs["Color"], b.inputs["Emission Color"])
        L(nt, s.outputs[0], b.inputs["Emission Strength"])


def fx_lantern(o, strength=2.2):
    """Paper lantern lit from inside: translucent paper + emission of the albedo (dark kanji stay dark)."""
    for m in o.data.materials:
        nt = m.node_tree
        tex = base_tex(m)
        b = principled(m)
        if tex is None:
            continue
        L(nt, tex.outputs["Color"], b.inputs["Emission Color"])
        b.inputs["Emission Strength"].default_value = strength
        b.inputs["Subsurface Weight"].default_value = 0.3


def fx_glass_front(o, zmin, zmax):
    """Glass-front fridge: add a real glass pane in front of the door so it gets reflections and depth."""
    lo, hi = bounds([o])
    w = (hi.x - lo.x) * 0.82
    me = bpy.data.meshes.new("door_glass")
    y = lo.y - 0.004
    me.from_pydata([(-w / 2, y, zmin), (w / 2, y, zmin), (w / 2, y, zmax), (-w / 2, y, zmax)], [], [(0, 1, 2, 3)])
    g = bpy.data.objects.new(o.name + "_glass", me)
    bpy.context.scene.collection.objects.link(g)
    m = bpy.data.materials.new("fridge_glass")
    m.use_nodes = True
    b = principled(m)
    b.inputs["Roughness"].default_value = 0.03
    b.inputs["Transmission Weight"].default_value = 1.0
    b.inputs["Base Color"].default_value = (0.95, 0.97, 0.97, 1)
    me.materials.append(m)
    g.parent = o


FIX = {
    "ramen_water_glass": [(fx_clear_glass, {})],
    "condiment_caddy": [(fx_glassy, {})],
    "ramen_soy_bottles": [(fx_coat, {"w": 0.6, "r": 0.1})],
    "ramen_bowl_stack": [(fx_coat, {})],
    "ramen_bowl_unfinished": [(fx_coat, {"w": 0.6, "r": 0.04})],
    "ramen_maneki_neko": [(fx_coat, {"w": 0.7, "r": 0.05})],
    "ramen_dish_rack": [(fx_coat, {"w": 0.4, "r": 0.08})],
    "ramen_chopstick_cup": [(fx_coat, {"w": 0.35, "r": 0.15})],
    "ticket_machine": [(fx_front_glow, {"strength": 3.0, "zmin": 0.62, "zmax": 1.5})],
    "ramen_drink_fridge": [(fx_front_glow, {"strength": 2.5, "zmin": 0.25, "zmax": 1.55}), (fx_glass_front, {"zmin": 0.25, "zmax": 1.5})],
    "lantern": [(fx_lantern, {})],
    "ramen_vending_machine": [(fx_front_glow, {"strength": 3.0, "zmin": 0.35, "zmax": 1.75})],
    "ramen_beer_bottle_glass": [(fx_glassy, {})],
    "ramen_ashtray": [(fx_glassy, {"rough": 0.03})],
    "ramen_shelf_jars": [(fx_glassy, {})],
    "ramen_condiment_tray2": [(fx_glassy, {})],
    "ramen_tea_cup": [(fx_coat, {"w": 0.6, "r": 0.08})],
    "ramen_beni_shoga_pot": [(fx_coat, {})],
    "ramen_plate_stack": [(fx_coat, {})],
    "ramen_daruma": [(fx_coat, {"w": 0.4, "r": 0.2})],
    "ramen_smartphone": [(fx_coat, {"w": 1.0, "r": 0.03})],
    "ramen_egg_container": [(fx_coat, {"w": 0.8, "r": 0.05})],
    "ramen_chashu_tray": [(fx_coat, {"w": 0.5, "r": 0.1})],
}


# ------------------------------------------------------------------ geometry

def bounds(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def prep(pid, model):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    glb = os.path.join(ROOT, "assets", "gen", model, pid, "model.glb")
    bpy.ops.import_scene.gltf(filepath=glb)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    for o in bpy.data.objects:
        o.select_set(o in meshes)
    bpy.context.view_layer.objects.active = meshes[0]
    # Bake parent transforms into the meshes, drop empties, join.
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    for o in [o for o in bpy.data.objects if o.type != "MESH"]:
        bpy.data.objects.remove(o)
    if len(meshes) > 1:
        bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    o.name = pid
    o.data.name = pid
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    # glTF imports use quaternion rotation mode, so turn the mesh data itself rather than rotation_euler.
    o.data.transform(Matrix.Rotation(math.radians(YAW[model]), 4, "Z"))
    o.data.update()
    bpy.context.view_layer.update()

    lo, hi = bounds([o])
    size = hi - lo
    spec = MAN[pid]
    s = spec["h"] / size.z if "h" in spec else spec["m"] / max(size)
    me = o.data
    centre = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    if "dims" in spec:
        # Boxy appliances: generators invent the depth, so fit width/depth/height separately.
        w, d, h = spec["dims"]
        S = Matrix.Diagonal((w / size.x, d / size.y, h / size.z, 1))
        s = h / size.z
    else:
        S = Matrix.Scale(s, 4)
    me.transform(S @ Matrix.Translation(-centre))
    me.update()
    o.location = (0, 0, 0)

    me.calc_loop_triangles()
    tris = len(me.loop_triangles)
    budget = 220_000 if pid in HERO else (40_000 if max(size) * s < 0.3 else 90_000)
    if tris > budget * 1.1:
        d = o.modifiers.new("dec", "DECIMATE")
        d.ratio = budget / tris
        d.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier="dec")
    for p in me.polygons:
        p.use_smooth = True

    cap = 4096 if pid in TEX_4K else 2048
    for img in bpy.data.images:
        # glTF images arrive already packed. Re-packing an unmodified one (empty filepath) silently drops
        # its data, so only resized images get packed again (from their new pixel buffer).
        if img.source == "FILE" and img.size[0] > cap:
            img.scale(cap, cap)
            img.pack()

    for fn, kw in FIX.get(pid, FIX.get(spec.get("replaces", ""), [])):  # _nb variants share the original's fixes
        fn(o, **kw)
    o["source_model"] = model
    o["target"] = spec.get("h", spec.get("m"))
    me.calc_loop_triangles()
    out = os.path.join(LIB, pid + ".blend")
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    lo, hi = bounds([o])
    print(f"PREP {pid} {model} tris {tris}->{len(me.loop_triangles)} size {tuple(round(v, 3) for v in (hi - lo))}", flush=True)


for pid, pick in PICKS.items():
    if ONLY and pid not in ONLY:
        continue
    try:
        prep(pid, pick["model"])
    except Exception as e:
        print("PREP FAILED", pid, repr(e), flush=True)
