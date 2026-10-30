"""Camera-path clearance check: minimum distance from each shot's camera path to render-visible mesh geometry.

blender -b scenes/tokyo-ramen-shop/ramen_r2.blend --python scenes/tokyo-ramen-shop/scripts/camcheck.py -- scenes/tokyo-ramen-shop/shots.json h1_door_to_counter,h2_counter_walkaround [--min 0.25]
Samples the keyed positions (Catmull-Rom for move "path", piecewise linear otherwise); handheld shake is a few mm, ignored."""
import json
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:]
shots = {s["name"]: s for s in json.load(open(argv[0]))["shots"]}
names = argv[1].split(",")
MIN = float(argv[argv.index("--min") + 1]) if "--min" in argv else 0.25
SKIP = ("haze_volume", "kitchen_vapor", "steam_", "rain_", "street_backdrop", "road", "CR_")

dg = bpy.context.evaluated_depsgraph_get()
verts, polys = [], []
for o in bpy.data.objects:
    if o.type != "MESH" or o.hide_render or o.name.startswith(SKIP):
        continue
    if any(m.type == "FLUID" for m in o.modifiers):
        continue
    ev = o.evaluated_get(dg)
    me = ev.to_mesh()
    base = len(verts)
    verts += [o.matrix_world @ v.co for v in me.vertices]
    polys += [tuple(base + i for i in p.vertices) for p in me.polygons]
    ev.to_mesh_clear()
tree = BVHTree.FromPolygons(verts, polys)


def catmull(p0, p1, p2, p3, t):
    return 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)


def sample(s, n=400):
    keys = sorted(s["keys"], key=lambda k: k["t"])
    P = [Vector(k["pos"]) for k in keys]
    T = [k["t"] for k in keys]
    out = []
    for i in range(n + 1):
        t = i / n
        j = max(0, min(len(T) - 2, next((k for k in range(len(T) - 1) if T[k] <= t <= T[k + 1]), len(T) - 2)))
        u = (t - T[j]) / max(1e-6, T[j + 1] - T[j])
        if s.get("move") == "path":
            p0, p3 = P[max(0, j - 1)], P[min(len(P) - 1, j + 2)]
            out.append((t, catmull(p0, P[j], P[j + 1], p3, u)))
        else:
            out.append((t, P[j].lerp(P[j + 1], u)))
    return out


for name in names:
    s = shots[name]
    worst = (9, None, None)
    for t, p in sample(s):
        loc, nrm, idx, d = tree.find_nearest(p)
        if d is not None and d < worst[0]:
            worst = (d, t, p)
    flag = "OK" if worst[0] >= MIN else "TOO CLOSE"
    print(f"CAMCHECK {name}: min {worst[0]:.3f} m at t={worst[1]:.3f} pos {tuple(round(v, 2) for v in worst[2])} -> {flag}", flush=True)
