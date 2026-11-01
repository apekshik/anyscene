"""/build: assemble a scene .blend from a Plan, then swap generated meshes in as they arrive. Deterministic, no agent.

    blender -b --factory-startup --python endpoint/assemble.py -- build plan.json assets.json out_dir
    blender -b out_dir/scene.blend --python endpoint/assemble.py -- swap assets.json out_dir

build:
- shell: floor (and walls + ceiling for interiors) from the plan's room and openings;
- every generated prop whose mesh has arrived: its GLB imported once, joined, turned so its front faces -Y (Tripo's
  front is +X), scaled uniformly to the plan's size (by height for upright things, by footprint for flat ones), origin
  at the bottom centre, then instanced (linked duplicates) at every placement;
- every generated prop still pending: a stand-in box at its planned size, tagged so swap can replace it later;
- everything else (counters, shelves, structure, signage): boxes in the plan's palette;
- lights from the plan, world from time_of_day, then the grounding pass (floaters dropped onto their support);
- writes scene.blend and shots.json (the reference camera plus two auto-framed eye-level stills) for camera/shoot.py.
swap: replaces stand-ins whose asset has arrived since, re-runs grounding, saves. Reports what is still a stand-in.
"""

import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

STANDIN = "anyscene_standin"   # custom property on stand-in boxes: the asset id they stand in for
OBJECT_ID = "anyscene_object"  # custom property on every placed prop: its plan object id


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def material(name, rgb, rough=0.7):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    return m


def collection(name, hidden=False):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
    if hidden:
        bpy.context.view_layer.layer_collection.children[name].exclude = True
    return c


def box(name, center, size, rot=0.0, mat=None, coll=None):
    mesh = bpy.data.meshes.new(name)
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()
    mesh.transform(Matrix.Diagonal((*size, 1)))
    o = bpy.data.objects.new(name, mesh)
    o.location, o.rotation_euler = center, (0, 0, math.radians(rot))
    if mat:
        mesh.materials.append(mat)
    (coll or collection("scene")).objects.link(o)
    return o


def load_asset(a):
    """Import an asset's GLB once and normalise it into a single mesh object in the hidden library."""
    lib = collection("asset_library", hidden=True)
    if a["id"] in lib.objects:
        ob = lib.objects[a["id"]]
        return ob, Vector(ob["dims"])
    model, path = next(iter(a["meshes"].items()))
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    for o in new:
        o.rotation_mode = "XYZ"  # glTF imports come in as quaternions
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.parent = None
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for o in new:
        if o != ob and o.name in bpy.data.objects:
            bpy.data.objects.remove(o)
    if model == "tripo-h31":  # Tripo's front is +X; turn it to face -Y like everything else
        ob.data.transform(Matrix.Rotation(math.radians(-90), 4, "Z"))
    vs = [v.co for v in ob.data.vertices]
    lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    ob.data.transform(Matrix.Translation(-Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))))
    ob.name = ob.data.name = a["id"]
    ob["dims"] = list(hi - lo)
    for c in ob.users_collection:
        c.objects.unlink(ob)
    lib.objects.link(ob)
    return ob, hi - lo


def place_mesh(spec, a):
    """Instance an asset's mesh at a plan object's position, scaled uniformly to its planned size."""
    src, dims = load_asset(a)
    upright = spec["h"] >= 0.25 * max(spec["w"], spec["d"])  # upright: fit height; flat: fit footprint
    s = spec["h"] / max(dims.z, 1e-4) if upright else max(spec["w"], spec["d"]) / max(dims.x, dims.y, 1e-4)
    inst = bpy.data.objects.new(spec["id"], src.data)  # linked duplicate: one mesh, many placements
    collection("scene").objects.link(inst)
    inst.location = (spec["x"], spec["y"], spec["z"])
    inst.rotation_euler = (0, 0, math.radians(spec["rot"]))
    inst.scale = (s, s, s)
    inst[OBJECT_ID] = spec["id"]
    return inst


def ground(objects):
    """Drop each object onto whatever is under its lowest points (same method as pipeline/grounding.py)."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    trees = {}
    for o in collection("scene").objects:
        if o.type == "MESH":
            me = o.evaluated_get(dg).to_mesh()
            if me.polygons:
                mw = o.matrix_world
                trees[o.name] = BVHTree.FromPolygons([mw @ v.co for v in me.vertices], [p.vertices[:] for p in me.polygons])
            o.evaluated_get(dg).to_mesh_clear()
    dropped = 0
    for inst in objects:
        me = inst.evaluated_get(dg).to_mesh()
        vs = [inst.matrix_world @ v.co for v in me.vertices]
        inst.evaluated_get(dg).to_mesh_clear()
        if not vs:
            continue
        zmin = min(v.z for v in vs)
        feet = [v for v in vs if v.z <= zmin + 0.015][::max(1, len(vs) // 400)]
        gaps = [t.ray_cast(f + Vector((0, 0, 0.002)), Vector((0, 0, -1)), 5.0)[3]
                for f in feet for name, t in trees.items() if name != inst.name]
        gaps = [g - 0.002 for g in gaps if g is not None]
        if gaps and 0.01 < min(gaps) < 3.0:
            inst.location.z -= min(gaps)
            dropped += 1
    return dropped


def build(plan, assets, out):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples, sc.cycles.use_denoising = 64, True
    sc.view_settings.view_transform = "AgX"
    sc["anyscene_plan"] = json.dumps(plan)

    pal = [hex_rgb(c) for c in plan.get("palette") or ["#8a8478"]]
    m_floor = material("floor", tuple(c * 0.6 for c in pal[0]), 0.6)
    m_wall = material("wall", tuple(0.35 + 0.4 * c for c in pal[min(1, len(pal) - 1)]), 0.85)
    m_box = [material(f"box_{i}", tuple(0.25 + 0.6 * c for c in p), 0.6) for i, p in enumerate(pal)]
    m_standin = material("standin", (0.55, 0.55, 0.58), 0.9)

    R = plan["room"]
    W, D, H = R["width"], R["depth"], R["height"]
    box("floor", (W / 2, D / 2, -0.05), (W + 6, D + 6, 0.1), mat=m_floor)
    if plan["setting"] == "interior":
        T = 0.12
        walls = {"front": ((0, 0), (1, 0), W), "back": ((0, D), (1, 0), W), "left": ((0, 0), (0, 1), D), "right": ((W, 0), (0, 1), D)}
        for wall, (origin, axis, length) in walls.items():
            ops = sorted((o for o in plan["openings"] if o["wall"] == wall), key=lambda o: o["center"])
            pieces, a = [], 0.0
            for o in ops:
                s, e = o["center"] - o["width"] / 2, o["center"] + o["width"] / 2
                pieces.append((a, s, 0, H))
                if o["sill"] > 0:
                    pieces.append((s, e, 0, o["sill"]))
                if o["sill"] + o["height"] < H:
                    pieces.append((s, e, o["sill"] + o["height"], H))
                a = e
            pieces.append((a, length, 0, H))
            for i, (s, e, z0, z1) in enumerate(pieces):
                if e - s > 0.01 and z1 - z0 > 0.01:
                    mid = (s + e) / 2
                    size = (e - s, T, z1 - z0) if axis[0] else (T, e - s, z1 - z0)
                    box(f"wall_{wall}_{i}", (origin[0] + axis[0] * mid, origin[1] + axis[1] * mid, (z0 + z1) / 2), size, mat=m_wall)
        box("ceiling", (W / 2, D / 2, H + 0.05), (W, D, 0.1), mat=m_wall)

    by_object = {oid: a for a in assets.values() for oid in a["objects"]}
    placed, standins = [], 0
    for spec in plan["objects"]:
        if spec["w"] <= 0 or spec["d"] <= 0 or spec["h"] <= 0 or spec["category"] == "decal":
            continue
        a = by_object.get(spec["id"])
        if a and a.get("meshes") and not a.get("failed"):
            try:
                placed.append(place_mesh(spec, a))
                continue
            except RuntimeError as e:  # a broken or truncated GLB: stand in for it instead of failing the build
                print(f"assemble: {a['id']} mesh failed to import ({str(e)[:80]}), using a stand-in")
                a["meshes"] = {}
        if a:  # generated prop not here yet (or broken): a stand-in box at its planned size, swapped in later
            o = box(spec["id"], (spec["x"], spec["y"], spec["z"] + spec["h"] / 2), (spec["w"], spec["d"], spec["h"]),
                    spec["rot"], m_standin)
            o[STANDIN], o[OBJECT_ID] = a["id"], spec["id"]
            standins += 1
        else:
            box(spec["id"], (spec["x"], spec["y"], spec["z"] + spec["h"] / 2), (spec["w"], spec["d"], spec["h"]),
                spec["rot"], m_box[hash(spec["category"]) % len(m_box)])

    for li in plan["lights"]:
        data = bpy.data.lights.new(li["id"], "POINT")
        data.energy = {"low": 25, "medium": 80, "high": 220}[li["power"]] * (2.5 if li["kind"] in ("street", "window") else 1)
        data.color, data.shadow_soft_size = hex_rgb(li["color"]), 0.12
        lo = bpy.data.objects.new(li["id"], data)
        lo.location = (li["x"], li["y"], li["z"])
        collection("lights").objects.link(lo)

    world = bpy.data.worlds.new("world")
    world.use_nodes = True
    tod = plan.get("time_of_day", "night").lower()
    sky = {"dawn": ((0.55, 0.45, 0.42), 0.6), "day": ((0.6, 0.72, 0.9), 1.6), "dusk": ((0.45, 0.32, 0.38), 0.5)}
    rgb, strength = next((v for k, v in sky.items() if k in tod), ((0.03, 0.04, 0.07), 0.25))
    world.node_tree.nodes["Background"].inputs[0].default_value = (*rgb, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = strength
    sc.world = world

    dropped = ground(placed)
    print(f"assemble: {len(placed)} props placed, {standins} stand-ins pending, {dropped} dropped onto their support")

    rc = plan["reference_camera"]
    still = lambda name, pos, aim, lens: {"name": name, "move": "static", "frames": 1, "focus": {"mode": "none"},
                                          "keys": [{"t": 0, "pos": pos, "aim": aim, "lens": lens}]}
    views = auto_views(W, D, rc["position"])
    shots = {"defaults": {"fps": 24, "res": [1920, 804], "aspect": "2.39", "samples": 128, "shutter": 0, "fstop": 4.0},
             "shots": [still("ref_view", rc["position"], rc["look_at"], rc["lens_mm"])]
                      + [still(f"view_{i + 1}", pos, aim, 24) for i, (pos, aim) in enumerate(views)]}
    json.dump(shots, open(os.path.join(out, "shots.json"), "w"), indent=1)
    save(out)


def auto_views(W, D, ref_pos, n=2):
    """Pick n eye-level camera spots in open space (at least 0.6 m from any surface) with a clear line of sight to the
    middle of the space, as far from the reference camera and each other as possible, so the stills show other angles."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    verts, polys = [], []
    for o in collection("scene").objects:
        if o.type != "MESH" or o.name in ("floor", "ceiling"):
            continue
        me = o.evaluated_get(dg).to_mesh()
        base, mw = len(verts), o.matrix_world
        verts += [mw @ v.co for v in me.vertices]
        polys += [[base + i for i in p.vertices] for p in me.polygons]
        o.evaluated_get(dg).to_mesh_clear()
    bvh = BVHTree.FromPolygons(verts, polys) if polys else None
    target = Vector((W / 2, D / 2, 1.0))
    cands = []
    for i in range(1, 12):
        for j in range(1, 12):
            p = Vector((W * i / 12, D * j / 12, 1.6))
            if bvh:
                near = bvh.find_nearest(p)
                if near[0] is not None and near[3] < 0.6:
                    continue
                to = target - p
                hit = bvh.ray_cast(p, to.normalized(), to.length)
                if hit[0] is not None:
                    continue
            cands.append(p)
    picked = [Vector(ref_pos)]
    out = []
    for _ in range(n):
        if not cands:
            break
        best = max(cands, key=lambda c: min((c - q).length for q in picked))
        picked.append(best)
        out.append(([round(best.x, 3), round(best.y, 3), round(best.z, 3)], [target.x, target.y, target.z]))
    return out


def swap(assets, out):
    """Replace stand-ins whose asset has arrived, then re-ground what changed."""
    swapped, still = [], 0
    plan = json.loads(bpy.context.scene["anyscene_plan"])
    specs = {o["id"]: o for o in plan["objects"]}
    for o in list(collection("scene").objects):
        aid = o.get(STANDIN)
        if not aid:
            continue
        a = assets.get(aid)
        if a and a.get("meshes") and not a.get("failed"):
            spec = specs[o[OBJECT_ID]]
            bpy.data.objects.remove(o)
            swapped.append(place_mesh(spec, a))
        else:
            still += 1
    dropped = ground(swapped)
    print(f"assemble: swapped in {len(swapped)} meshes, {still} stand-ins left, {dropped} dropped onto their support")
    save(out)


def save(out):
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "scene.blend"), compress=True)
    print("assemble: wrote", os.path.join(out, "scene.blend"))


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:]
    cmd = argv[0]
    if cmd == "build":
        plan, assets, out = json.load(open(argv[1], encoding="utf-8")), json.load(open(argv[2], encoding="utf-8"))["assets"], os.path.abspath(argv[3])
        os.makedirs(out, exist_ok=True)
        build(plan, assets, out)
    elif cmd == "swap":
        swap(json.load(open(argv[1], encoding="utf-8"))["assets"], os.path.abspath(argv[2]))
