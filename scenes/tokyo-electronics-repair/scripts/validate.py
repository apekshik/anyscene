"""Placement validator for the dressed repair shop (the video's self-correcting check).

blender -b scenes/tokyo-electronics-repair/repair_dressed.blend --python scenes/tokyo-electronics-repair/scripts/validate.py
Flags: FLOAT (bottom > 1 cm above the support under it), CLIP (two props interpenetrating by more than a sliver),
OUT (outside the room box), SCALE (dimensions off the manifest by > 25 %). Exit summary line: "VALIDATE n issues".
"""
import json
import os

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = os.environ.get("ANYSCENE_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SCN = os.path.join(ROOT, "scenes", "tokyo-electronics-repair")
W, D, H = 4.2, 6.5, 2.7
man = {a["id"]: a for a in json.load(open(os.path.join(SCN, "assets.json")))["generate"]}
sc = bpy.context.scene
dg = bpy.context.evaluated_depsgraph_get()
props = [o for o in sc.objects if o.get("placed") and o.visible_get()]
issues = []


def world_bb(o):
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))), Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))


for o in props:
    lo, hi = world_bb(o)
    # OUT
    if lo.x < -0.02 or lo.y < -0.02 or hi.x > W + 0.02 or hi.y > D + 0.02 or hi.z > H + 0.01:
        issues.append(f"OUT {o.name} bb {tuple(round(v, 2) for v in lo)}..{tuple(round(v, 2) for v in hi)}")
    # FLOAT: cast down from just below the prop's lowest point
    if not o.get("wall"):
        # cast from just above the prop bottom with the prop moved out of the way (a thin top would be entered from below)
        z0 = o.location.z
        o.location.z = -100
        bpy.context.view_layer.update()
        dg2 = bpy.context.evaluated_depsgraph_get()
        hit, loc, n, i, ob, m = sc.ray_cast(dg2, Vector((o.location.x, o.location.y, lo.z + 0.02)), Vector((0, 0, -1)))
        o.location.z = z0
        bpy.context.view_layer.update()
        gap = (lo.z - loc.z) if hit else lo.z
        if gap > 0.01:
            issues.append(f"FLOAT {o.name} {gap * 100:.1f} cm above {ob.name if hit else 'nothing'}")
    # SCALE
    a = man.get(o.get("prop_id"))
    if a and not o.get("scaled"):
        d = o.dimensions
        got = d.z if a["fit"] == "h" else max(d)
        if abs(got / a["size"] - 1) > 0.25:
            issues.append(f"SCALE {o.name} {got:.2f} m vs {a['size']} m")

# CLIP: BVH overlap between props whose boxes intersect
trees = {}
for o in props:
    eo = o.evaluated_get(dg)
    me = eo.to_mesh()
    me.transform(o.matrix_world)
    trees[o.name] = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
    eo.to_mesh_clear()
names = list(trees)
boxes = {o.name: world_bb(o) for o in props}
for i, a_ in enumerate(names):
    for b_ in names[i + 1:]:
        (alo, ahi), (blo, bhi) = boxes[a_], boxes[b_]
        if any(ahi[k] < blo[k] or bhi[k] < alo[k] for k in range(3)):
            continue
        pairs = trees[a_].overlap(trees[b_])
        if len(pairs) > 40:
            issues.append(f"CLIP {a_} x {b_} ({len(pairs)} tri pairs)")

# FURNITURE: real mesh intersection (BVH overlap of evaluated triangles) between every placed prop and the fixed
# furniture/shell. The prop mesh is lifted 3 mm so resting flush on its support is not a hit; anything poking into a
# shelf, cabinet, bench, rack or wall by more than that is.
FURN_COLLS = ("shell", "bench", "drawers", "shelving", "storefront", "counter", "ceiling")
furn = [o for o in sc.objects if o.type == "MESH" and o.visible_get() and any(c.name in FURN_COLLS for c in o.users_collection)
        and not o.name.startswith(("floor", "backroom", "pavement", "street", "glass", "door_leaf", "decal"))]
ftrees = {}
for f in furn:
    ef = f.evaluated_get(dg)
    me = ef.to_mesh()
    me.transform(f.matrix_world)
    ftrees[f.name] = (BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(p.vertices) for p in me.polygons]), world_bb(f))
    ef.to_mesh_clear()
from mathutils import Matrix  # noqa: E402
for o in props:
    eo = o.evaluated_get(dg)
    me = eo.to_mesh()
    me.transform(Matrix.Translation((0, 0, 0.003)) @ o.matrix_world)
    t = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
    eo.to_mesh_clear()
    alo, ahi = boxes[o.name]
    for fname, (ft, (blo, bhi)) in ftrees.items():
        if any(ahi[k] < blo[k] or bhi[k] < alo[k] for k in range(3)):
            continue
        pairs = t.overlap(ft)
        if len(pairs) > 20:
            issues.append(f"FURNITURE {o.name} x {fname} ({len(pairs)} tri pairs)")

for s in issues:
    print(s)
print(f"VALIDATE {len(issues)} issues over {len(props)} props")
