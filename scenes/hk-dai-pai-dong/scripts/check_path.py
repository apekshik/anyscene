"""Camera-path clearance check for camrig shots: every frame's camera position vs every render-visible mesh (BVH nearest).
blender -b scenes/hk-dai-pai-dong/hk.blend --python scenes/hk-dai-pai-dong/scripts/check_path.py -- <shots.json> <name,name> [min=0.25]"""
import json, os, sys
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "camera"))
import camrig  # noqa: E402
a = sys.argv[sys.argv.index("--") + 1:]
cfg = json.load(open(a[0]))
names = a[1].split(",")
lim = float(a[2]) if len(a) > 2 else 0.25
sc = bpy.context.scene
dg = bpy.context.evaluated_depsgraph_get()
skip = ("drizzle", "drip", "awning_drips", "haze", "steam_", "wok_flame", "skyline", "CR_", "clay", "harbour")
trees = []
for o in sc.objects:
    if o.type not in ("MESH", "CURVE") or not o.visible_get() or o.hide_render or o.name.startswith(skip):
        continue
    eo = o.evaluated_get(dg)
    me = eo.to_mesh()
    if me is None or not len(me.polygons):
        continue
    me.transform(o.matrix_world)
    trees.append((o.name, BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(p.vertices) for p in me.polygons])))
    eo.to_mesh_clear()
shots = [camrig.merged(cfg.get("defaults", {}), s) for s in cfg["shots"]]
for i, s in enumerate(shots):
    if s["name"] not in names:
        continue
    cam = camrig.build(s, seed=i * 7)
    worst = (9, None, 0)
    bad = 0
    for f in range(1, int(s["frames"]) + 1):
        sc.frame_set(f)
        p = cam.matrix_world.translation.copy()
        for n, t in trees:
            loc, nrm, idx, d = t.find_nearest(p, lim * 2)
            if loc is not None and d < worst[0]:
                worst = (d, n, f)
            if loc is not None and d < lim:
                bad += 1
    print(f"PATH {s['name']}: min clearance {worst[0]:.2f} m to {worst[1]} at frame {worst[2]}; {bad} frame-object hits under {lim} m")
