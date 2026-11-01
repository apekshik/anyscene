"""Find props that float above (or sink into) whatever they should rest on, measured at their actual contact points.

    blender -b scene.blend --python pipeline/grounding.py -- [--report out.json] [--fix] [--tol 0.01] [--save out.blend]

For each mesh object (or GLB import root with mesh children) it takes the lowest vertices in world space - chair feet,
stool legs, a pot's base ring - and casts a ray straight down from just above each, ignoring the object itself.
  gap  = distance from those contact points to the nearest surface below (positive = floating)
A bounding-box check misses floaters whenever the box bottom isn't where the object touches down (splayed legs,
decimated feet, an origin offset), which is how chairs end up hovering.

--fix moves each floating object down by its smallest contact gap (so at least one foot touches) and prints what moved.
It never moves an object up and skips anything parented to another object (it moves with its parent).
"""

import json
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
opt = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
TOL = float(opt("--tol", 0.01))
FIX = "--fix" in argv
SKIP_PREFIX = ("CR_", "camrig", "wall", "floor", "ceiling", "street", "road", "pavement", "ground", "rain", "steam",
               "haze", "smoke", "decal", "flame", "glow", "light", "neon", "sign")

# Things that legitimately hang: checked only if --all is passed.
HANGING = ("aircon", "clock", "speaker_wall", "tv_ceiling", "extinguisher", "poster", "sign", "lamp_pendant", "pendant",
           "bulb", "lantern", "noren", "awning", "fan_wall", "shelf_wall", "hook", "calendar", "menu", "blind", "curtain",
           "cable", "wire", "pipe", "ledge", "bracket", "frame", "transom", "bezel", "door", "window", "mount")
# Volumes and particles are not surfaces: never count them as something to rest on.
NOT_SURFACE = ("haze", "drizzle", "rain", "steam", "smoke", "fog", "mist", "vapor", "vapour", "plume", "volume", "flame")
PREFIX = opt("--prefix")  # e.g. "hk_": only check this scene's generated props


def wanted(o):
    n = o.name.lower()
    if o.parent is not None or not o.visible_get() or o.hide_render or n.startswith(SKIP_PREFIX):
        return False
    if not (o.type == "MESH" or any(c.type == "MESH" for c in o.children_recursive)):
        return False
    if PREFIX and not n.startswith(PREFIX):
        return False
    return "--all" in argv or not any(k in n for k in HANGING)


dg = bpy.context.evaluated_depsgraph_get()
roots = [o for o in bpy.context.scene.objects if wanted(o)]
MAX_GAP = float(opt("--max-gap", 0.6))  # bigger gaps are almost always deliberate (wall-hung); report separately


def world_verts(root):
    vs = []
    for o in [root, *root.children_recursive]:
        if o.type != "MESH":
            continue
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        mw = o.matrix_world
        vs += [mw @ v.co for v in me.vertices]
        ev.to_mesh_clear()
    return vs


# One BVH per object so a ray can skip the object it starts from.
trees = {}
for o in bpy.context.scene.objects:
    if o.type == "MESH" and o.visible_get() and not o.hide_render and not any(k in o.name.lower() for k in NOT_SURFACE):
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        if len(me.polygons):
            mw = o.matrix_world
            trees[o.name] = BVHTree.FromPolygons([mw @ v.co for v in me.vertices], [p.vertices[:] for p in me.polygons])
        ev.to_mesh_clear()


def nearest_below(p, own):
    best = None
    for name, t in trees.items():
        if name in own:
            continue
        hit = t.ray_cast(p, Vector((0, 0, -1)), 50.0)
        if hit[0] is not None and (best is None or hit[3] < best[0]):
            best = (hit[3], name)
    return best


report = []
for root in roots:
    vs = world_verts(root)
    if len(vs) < 4:
        continue
    zmin = min(v.z for v in vs)
    height = max(v.z for v in vs) - zmin
    if height < 0.02:
        continue
    # contact candidates: lowest 1.5 cm (or 3 % of the height), thinned to at most 40 points
    band = max(0.015, 0.03 * height)
    feet = [v for v in vs if v.z <= zmin + band]
    feet = feet[:: max(1, len(feet) // 40)]
    own = {o.name for o in [root, *root.children_recursive]}
    gaps = []
    for f in feet:
        hit = nearest_below(f + Vector((0, 0, 0.002)), own)
        if hit:
            gaps.append((hit[0] - 0.002, hit[1]))
    if not gaps:
        report.append({"object": root.name, "issue": "nothing below", "z": round(zmin, 3)})
        continue
    g, under = min(gaps)
    if TOL < g <= MAX_GAP:
        report.append({"object": root.name, "issue": "floating", "gap_cm": round(g * 100, 1), "on": under})
        if FIX and root.parent is None:
            root.location.z -= g
            report[-1]["fixed"] = True
    elif g < -0.03:
        report.append({"object": root.name, "issue": "sunk", "depth_cm": round(-g * 100, 1), "on": under})

floating = [r for r in report if r["issue"] == "floating"]
print(f"grounding: {len(roots)} objects checked, {len(floating)} floating > {TOL * 100:.0f} cm, "
      f"{sum(r['issue'] == 'sunk' for r in report)} sunk > 3 cm, {sum(r['issue'] == 'nothing below' for r in report)} with nothing below")
for r in sorted(floating, key=lambda r: -r["gap_cm"]):
    print(f"grounding:   FLOAT {r['object']:<40} {r['gap_cm']:>6.1f} cm above {r['on']}" + ("  -> fixed" if r.get("fixed") else ""))
if opt("--report"):
    json.dump(report, open(opt("--report"), "w"), indent=1)
if FIX and opt("--save"):
    bpy.ops.wm.save_as_mainfile(filepath=opt("--save"), copy=True)
    print("grounding: saved", opt("--save"))
