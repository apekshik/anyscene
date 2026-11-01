"""Placement validator for the dressed mission-control room.

blender -b scenes/mission-control-1970s/mc.blend --python scenes/mission-control-1970s/scripts/validate.py
Also imported by build.py (`validate.check(resolve=True)` after dressing: clashing / floating small props are
spiral-searched to a clear spot on the same support).
Flags: FLOAT (> 1 cm above the support under it; the ray starts above the support's top, with the prop moved away),
GROUND (contact points, i.e. the prop's lowest vertices, > 2 mm above the nearest surface straight below, skipping the
prop itself and volumes; resolve lowers the prop onto it, see settle()), CLIP (two props interpenetrating: BVH triangle
overlap), FURNITURE (a prop's mesh, lifted 3 mm, intersects the shell
or direct-modelled furniture), OUT (outside the room), SCALE (off the manifest size by > 25 %).
Last line: "VALIDATE n issues over m props".
"""
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout as L  # noqa: E402

ROOT = os.environ.get("ANYSCENE_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SCN = os.path.join(ROOT, "scenes", "mission-control-1970s")
FURN_COLLS = ("shell", "furniture", "display")  # placards sit on console tops on purpose
SMALL = 1.1  # props whose largest dimension is under this (desk clutter, chairs) may be moved by resolve


def world_bb(o):
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))


def tree(o, lift=0.0):
    dg = bpy.context.evaluated_depsgraph_get()
    eo = o.evaluated_get(dg)
    me = eo.to_mesh()
    me.transform(Matrix.Translation((0, 0, lift)) @ o.matrix_world)
    t = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
    eo.to_mesh_clear()
    return t


def overlap(a, b):
    return any(a[1][k] < b[0][k] or b[1][k] < a[0][k] for k in range(3)) is False


def float_gap(o):
    sc = bpy.context.scene
    lo, hi = world_bb(o)
    z0 = o.location.z
    o.location.z -= 100
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    best = None
    for fx, fy in ((0.5, 0.5), (0.3, 0.3), (0.7, 0.3), (0.3, 0.7), (0.7, 0.7)):
        p = Vector((lo.x + (hi.x - lo.x) * fx, lo.y + (hi.y - lo.y) * fy, lo.z + 0.02))
        hit, loc, n, i, ob, m = sc.ray_cast(dg, p, Vector((0, 0, -1)))
        if hit:
            g = lo.z - loc.z
            best = g if best is None else min(best, g)
    o.location.z = z0
    bpy.context.view_layer.update()
    return best


GROUND_TOL = 0.002
NOT_SURFACE = ("haze", "smoke_curl", "backdrop")


def contact_gaps(props):
    """Same measure as pipeline/grounding.py: rays straight down from each prop's lowest vertices (bottom 1.5 cm or 3 %
    of its height), against every other visible mesh. Returns {name: (gap, support name)}, gap None = nothing below."""
    dg = bpy.context.evaluated_depsgraph_get()
    surf = {}
    verts = {}
    names = {o.name for o in props}
    for o in bpy.context.scene.objects:
        if o.type != "MESH" or not o.visible_get() or o.hide_render or o.name.startswith(NOT_SURFACE):
            continue
        eo = o.evaluated_get(dg)
        me = eo.to_mesh()
        vs = [o.matrix_world @ v.co for v in me.vertices]
        if len(me.polygons):
            surf[o.name] = BVHTree.FromPolygons(vs, [p.vertices[:] for p in me.polygons])
        if o.name in names:
            verts[o.name] = vs
        eo.to_mesh_clear()
    out = {}
    for name, vs in verts.items():
        if len(vs) < 4:
            continue
        zmin = min(v.z for v in vs)
        band = max(0.015, 0.03 * (max(v.z for v in vs) - zmin))
        feet = [v for v in vs if v.z <= zmin + band]
        best = None
        for f in feet[:: max(1, len(feet) // 40)]:
            p = f + Vector((0, 0, 0.002))
            for sname, t in surf.items():
                if sname == name:
                    continue
                hit = t.ray_cast(p, Vector((0, 0, -1)), 50.0)
                if hit[0] is not None and (best is None or hit[3] - 0.002 < best[0]):
                    best = (hit[3] - 0.002, sname)
        out[name] = best or (None, None)
    return out


def settle(props, verbose=True):
    """Lower every floor/desk prop whose nearest contact point is 2 mm - 5 cm above a surface so that point touches.
    (Drops take the *highest* hit under the base, so a prop whose feet overhang the desk's 2 mm edge lip hangs ~2.5 mm
    over the laminate.) Wall-hung props are skipped. Repeated so stacks settle after what they sit on. Direct-modelled
    pieces tagged "settle" (placards) go too, and anything tagged "follows" moves with the object it names."""
    sc = bpy.context.scene
    props = props + [o for o in sc.objects if o.get("settle")]
    for _ in range(3):
        moved = 0
        for name, (g, under) in contact_gaps(props).items():
            o = bpy.context.scene.objects[name]
            if o.get("wall") or g is None or not (GROUND_TOL < g <= 0.05):
                continue
            o.location.z -= g
            for f in sc.objects:
                if f.get("follows") == name:
                    f.location.z -= g
            moved += 1
            if verbose:
                print(f"SETTLED {name} -{g * 100:.1f} cm onto {under}")
        bpy.context.view_layer.update()
        if not moved:
            break


def check(resolve=False, verbose=True):
    sc = bpy.context.scene
    man = {a["id"]: a for a in json.load(open(os.path.join(SCN, "assets.json")))["generate"]}
    props = [o for o in sc.objects if o.get("placed") and o.visible_get() and o.type == "MESH"]
    furn = [o for o in sc.objects if o.type == "MESH" and o.visible_get() and not o.get("placed") and any(c.name in FURN_COLLS for c in o.users_collection)
            and not o.name.startswith(("window_glass", "door_window", "disp_", "floor_t0"))]
    issues = []
    moved = []
    ftrees = {f.name: (tree(f), world_bb(f)) for f in furn}
    for _round in range(2 if resolve else 1):
        issues.clear()
        bpy.context.view_layer.update()
        boxes = {o.name: world_bb(o) for o in props}
        trees = {o.name: tree(o) for o in props}
        bad = set()
        for o in props:
            lo, hi = boxes[o.name]
            if lo.x < -0.02 or lo.y < -0.02 or hi.x > L.W + 0.02 or hi.y > L.D + 0.02 or hi.z > L.H + 0.01:
                issues.append(f"OUT {o.name}")
            if not o.get("wall"):
                g = float_gap(o)
                if g is None or g > 0.01:
                    issues.append(f"FLOAT {o.name} {('%.1f cm' % (g * 100)) if g is not None else 'no support'}")
                    bad.add(o.name)
            a = man.get(o.get("prop_id"))
            if a:
                d = o.dimensions
                if "dims" in a:
                    got, want = d.z, a["dims"][2]
                elif "h" in a:
                    got, want = d.z, a["h"]
                else:
                    got, want = max(d), a["max"]
                if abs(got / want - 1) > 0.25:
                    issues.append(f"SCALE {o.name} {got:.2f} vs {want}")
        names = [o.name for o in props]
        for i, a_ in enumerate(names):
            for b_ in names[i + 1:]:
                if not overlap(boxes[a_], boxes[b_]):
                    continue
                n = len(trees[a_].overlap(trees[b_]))
                if n > 30:
                    issues.append(f"CLIP {a_} x {b_} ({n} tri pairs)")
                    sa, sb = max(sc.objects[a_].dimensions), max(sc.objects[b_].dimensions)
                    bad.add(a_ if sa < sb else b_)
        for o in props:
            t = tree(o, 0.003)
            for fname, (ft, fb) in ftrees.items():
                if not overlap(boxes[o.name], fb):
                    continue
                n = len(t.overlap(ft))
                if n > 20:
                    issues.append(f"FURNITURE {o.name} x {fname} ({n} tri pairs)")
                    bad.add(o.name)
        if resolve and _round == 1:
            settle(props, verbose)
        if not resolve or _round == 1:
            break
        for name in sorted(bad):
            o = sc.objects[name]
            if max(o.dimensions) < SMALL and not o.get("wall"):
                if spiral(o, props, trees):
                    moved.append(name)
                    trees[name] = tree(o)
    for name, (g, under) in contact_gaps([o for o in props if not o.get("wall")] + [o for o in sc.objects if o.get("settle")]).items():
        if g is None:
            issues.append(f"GROUND {name} nothing below")
        elif g > GROUND_TOL:
            issues.append(f"GROUND {name} {g * 100:.1f} cm above {under}")
    if verbose:
        for s in issues:
            print(s)
        if moved:
            print("RESOLVED (moved)", ", ".join(moved))
        print(f"VALIDATE {len(issues)} issues over {len(props)} props", flush=True)
    return issues


def spiral(o, props, trees, rmax=0.5):
    """Move o around its spot in a growing spiral, dropping it at each candidate until it sits flat (< 1 cm float)
    and clashes with nothing. Returns True when it found a spot."""
    import dress  # noqa: E402  (drop helper)
    x0, y0, z0 = o.location
    lo, hi = world_bb(o)
    start = lo.z + 0.25
    for k in range(1, 60):
        r = rmax * k / 60
        a = k * 2.4
        o.location = (x0 + r * math.cos(a), y0 + r * math.sin(a), z0)
        dress.drop(o, start)
        bpy.context.view_layer.update()
        g = float_gap(o)
        if g is None or g > 0.01:
            continue
        t = tree(o)
        ob = world_bb(o)
        if any(p is not o and overlap(ob, world_bb(p)) and len(t.overlap(trees[p.name])) > 30 for p in props):
            continue
        return True
    o.location = (x0, y0, z0)
    return False


if __name__ == "__main__":
    check()
