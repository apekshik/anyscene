"""Prep picked generated props into a library .blend (the video's "generated + refined" step).

blender -b --factory-startup --python scenes/tokyo-electronics-repair/scripts/prep.py -- [id ...]
Reads scenes/tokyo-electronics-repair/assets.json + picks.json. For each pick: import GLB, join, turn so the front faces -Y,
scale to the manifest size, origin at bottom centre, decimate, downscale textures to <= 2K, save
scenes/tokyo-electronics-repair/props/<id>.blend (one collection named after the id, ready to link/append).
"""
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

ROOT = os.environ.get("ANYSCENE_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SCN = os.path.join(ROOT, "scenes", "tokyo-electronics-repair")
FRONT_YAW = {"tripo-h31": 90, "meshy": 0}  # where the generator's front points (deg from -Y), see out/compare/yaw.json
MAX_TEX = 2048

man = {a["id"]: a for a in json.load(open(os.path.join(SCN, "assets.json")))["generate"]}
picks = json.load(open(os.path.join(SCN, "picks.json")))
only = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def tri_budget(a):
    # heroes on the bench close-up keep more detail; big background props less; tiny props least
    if a.get("hero"):
        return 200_000
    return 120_000 if a["size"] >= 0.3 else 50_000


def prep(pid):
    a, pick = man[pid], picks[pid]
    model = pick["model"]
    glb = os.path.join(ROOT, "assets", "gen", model, pid, "model.glb")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=glb)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    for o in bpy.data.objects:
        o.select_set(o.type == "MESH")
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.parent = None
    ob.matrix_world = ob.matrix_world.copy()
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for o in [o for o in bpy.data.objects if o is not ob]:
        bpy.data.objects.remove(o)
    # turn front to -Y, plus any per-pick extra yaw
    yaw = -math.radians(FRONT_YAW[model] + pick.get("yaw", 0))
    ob.data.transform(Matrix.Rotation(yaw, 4, "Z"))
    # scale + bottom-centre origin
    vs = [v.co for v in ob.data.vertices]
    lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    dims = hi - lo
    s = a["size"] / (dims.z if a["fit"] == "h" else max(dims))
    ob.data.transform(Matrix.Translation(-Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))))
    ob.data.transform(Matrix.Scale(s, 4))
    ob.location = (0, 0, 0)
    # decimate
    tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
    budget = tri_budget(a)
    if tris > budget:
        m = ob.modifiers.new("dec", "DECIMATE")
        m.ratio = budget / tris
        bpy.ops.object.modifier_apply(modifier="dec")
    for p in ob.data.polygons:
        p.use_smooth = True
    # textures <= 2K, saved next to the library file
    texdir = os.path.join(SCN, "props", "tex")
    os.makedirs(texdir, exist_ok=True)
    for i, img in enumerate(bpy.data.images):
        if img.size[0] == 0:
            continue
        if max(img.size) > MAX_TEX:
            f = MAX_TEX / max(img.size)
            img.scale(int(img.size[0] * f), int(img.size[1] * f))
        path = os.path.join(texdir, f"{pid}_{i}_{img.name.split('_')[0][:12]}.png")
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
        img.filepath = path
    ob.name = pid
    mat_names = []
    for i, slot in enumerate(ob.material_slots):
        if slot.material:
            slot.material.name = f"{pid}_mat{i}"
            mat_names.append(slot.material.name)
    coll = bpy.data.collections.new(pid)
    bpy.context.scene.collection.children.link(coll)
    for c in ob.users_collection:
        c.objects.unlink(ob)
    coll.objects.link(ob)
    ob["source_model"] = model
    ob["tris"] = sum(len(p.vertices) - 2 for p in ob.data.polygons)
    out = os.path.join(SCN, "props", f"{pid}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out)
    d = ob.dimensions
    print(f"PREP {pid} {model} tris {tris}->{ob['tris']} dims {d.x:.2f}x{d.y:.2f}x{d.z:.2f}")


for pid in picks:
    if only and pid not in only:
        continue
    try:
        prep(pid)
    except Exception as e:
        print("PREP FAILED", pid, repr(e))
