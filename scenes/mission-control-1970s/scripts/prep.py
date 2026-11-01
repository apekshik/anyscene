"""Prep picked generated props into per-prop library .blend files.

blender -b --factory-startup --python scenes/mission-control-1970s/scripts/prep.py -- [id ...]
Reads assets.json + picks.json. For each pick: import the GLB, join, turn so the front faces -Y (rotating mesh data),
scale to the manifest size (h = height, dims = per-axis [x, y, z], max = largest dimension), bottom-centre origin,
decimate to the tier budget, textures <= 2K, save props/<id>.blend (one collection named after the id).
Already-prepped props are skipped unless the pick changed model/yaw or the GLB is newer (or FORCE=1); a re-prep
drops fixes.py patches, so run fixes.py after every prep.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

ROOT = os.environ.get("ANYSCENE_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SCN = os.path.join(ROOT, "scenes", "mission-control-1970s")
FRONT_YAW = {"tripo-h31": 90, "meshy": 0}  # where each generator's front points, degrees from -Y (counter-clockwise)
MAX_TEX = 2048
BUDGET = {"hero": 150_000, "mid": 80_000, "clutter": 40_000}

man = {a["id"]: a for a in json.load(open(os.path.join(SCN, "assets.json")))["generate"]}
picks_path = os.path.join(SCN, "picks.json")
picks = {k: v for k, v in json.load(open(picks_path)).items() if not k.startswith("_")}
only = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def prep(pid):
    a, pick = man[pid], picks[pid]
    model = pick["model"]
    glb = os.path.join(ROOT, "assets", "gen", model, pid, "model.glb")
    out = os.path.join(SCN, "props", f"{pid}.blend")
    side = os.path.join(SCN, "props", f"{pid}.json")  # sidecar: which model the .blend was prepped from
    if not os.environ.get("FORCE") and os.path.exists(out) and os.path.exists(side) and os.path.getmtime(out) > os.path.getmtime(glb)             and json.load(open(side)).get("model") == model and json.load(open(side)).get("yaw", 0) == pick.get("yaw", 0) and json.load(open(side)).get("lay", False) == pick.get("lay", False):
        print("PREP skip", pid)
        return
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=glb)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    for o in bpy.data.objects:
        o.select_set(o.type == "MESH")
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    mw = ob.matrix_world.copy()
    ob.parent = None
    ob.rotation_mode = "XYZ"  # glTF imports are QUATERNION; rotation_euler is ignored otherwise
    ob.matrix_world = mw
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for o in [o for o in bpy.data.objects if o is not ob]:
        bpy.data.objects.remove(o)
    yaw = -math.radians(FRONT_YAW[model] + pick.get("yaw", 0))
    ob.data.transform(Matrix.Rotation(yaw, 4, "Z"))
    if pick.get("lay"):  # generator stood a flat object on its edge: lay it front face up
        ob.data.transform(Matrix.Rotation(math.radians(-90), 4, "X"))
    vs = [v.co for v in ob.data.vertices]
    lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    dims = hi - lo
    ob.data.transform(Matrix.Translation(-Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))))
    if "dims" in a:
        sx, sy, sz = (t / max(d, 1e-6) for t, d in zip(a["dims"], dims))
        ob.data.transform(Matrix.Diagonal((sx, sy, sz, 1)))
    else:
        s = a["h"] / dims.z if "h" in a else a["max"] / max(dims)
        ob.data.transform(Matrix.Scale(s, 4))
    ob.location = (0, 0, 0)
    tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
    budget = BUDGET[a.get("tier", "mid")]
    if tris > budget:
        m = ob.modifiers.new("dec", "DECIMATE")
        m.ratio = budget / tris
        bpy.ops.object.modifier_apply(modifier="dec")
    for p in ob.data.polygons:
        p.use_smooth = True
    texdir = os.path.join(SCN, "props", "tex")
    os.makedirs(texdir, exist_ok=True)
    for i, img in enumerate(bpy.data.images):
        if img.size[0] == 0:
            continue
        if max(img.size) > MAX_TEX:
            f = MAX_TEX / max(img.size)
            img.scale(int(img.size[0] * f), int(img.size[1] * f))
        path = os.path.join(texdir, f"{pid}_{i}.png")
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
        img.filepath = path
    ob.name = pid
    ob.data.name = pid
    for i, slot in enumerate(ob.material_slots):
        if slot.material:
            slot.material.name = f"{pid}_mat{i}"
    coll = bpy.data.collections.new(pid)
    bpy.context.scene.collection.children.link(coll)
    for c in ob.users_collection:
        c.objects.unlink(ob)
    coll.objects.link(ob)
    ob["source_model"] = model
    ob["prop_id"] = pid
    ob["tris"] = sum(len(p.vertices) - 2 for p in ob.data.polygons)
    bpy.ops.wm.save_as_mainfile(filepath=out)
    json.dump({"model": model, "yaw": pick.get("yaw", 0), "lay": pick.get("lay", False)}, open(side, "w"))
    d = ob.dimensions
    print(f"PREP {pid} {model} tris {tris}->{ob['tris']} dims {d.x:.2f}x{d.y:.2f}x{d.z:.2f}", flush=True)


for pid in picks:
    if only and pid not in only:
        continue
    if picks[pid].get("retired"):
        continue
    try:
        prep(pid)
    except Exception as e:
        print("PREP FAILED", pid, repr(e), flush=True)
