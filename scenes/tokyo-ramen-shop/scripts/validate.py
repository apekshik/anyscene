"""Placement validator: floating props, interpenetration between props, out-of-room, scale sanity.
Runs after every dressing pass (design coordinates, before the mirror) and writes a report."""
import itertools
import json
import os

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import shell as S
from lib import SCENE_DIR

OUTSIDE_OK = {"lantern", "ramen_vending_machine_nb"}


def _bounds(o):
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))


def _bvh(o, dg):
    ev = o.evaluated_get(dg)
    me = ev.to_mesh()
    me.transform(o.matrix_world)
    t = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
    ev.to_mesh_clear()
    return t


def run(placed, report_path):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    man = {p["id"]: p for p in json.load(open(os.path.join(SCENE_DIR, "assets.json")))["generate"]}
    issues = []
    objs = [o for o, _ in placed]
    for o, mode in placed:
        pid = o.name.split(".")[0]
        lo, hi = _bounds(o)
        # Floating: ray down from just above the bottom centre must hit something within 1.5 cm.
        if mode == "rest":
            hide = o.hide_get()
            o.hide_set(True)
            dg.update()
            gaps = []
            # Include near-corner rays so props on legs or feet are not reported as floating.
            for fx, fy in ((0.5, 0.5), (0.3, 0.3), (0.7, 0.7), (0.3, 0.7), (0.7, 0.3), (0.06, 0.06), (0.94, 0.94), (0.06, 0.94), (0.94, 0.06)):
                p = Vector((lo.x + (hi.x - lo.x) * fx, lo.y + (hi.y - lo.y) * fy, lo.z + 0.003))
                ok, loc, *_ = bpy.context.scene.ray_cast(dg, p, Vector((0, 0, -1)))
                gaps.append((p.z - loc.z) if ok else 9.0)
            o.hide_set(hide)
            if min(gaps) > 0.015:
                issues.append(f"FLOATING {o.name}: {min(gaps) * 100:.1f} cm above support")
        # Out of room.
        if pid not in OUTSIDE_OK and (lo.x < -0.02 or hi.x > S.W + 0.02 or lo.y < -0.02 or hi.y > S.D + 0.02 or hi.z > S.H + 0.01):
            issues.append(f"OUT_OF_ROOM {o.name}: x {lo.x:.2f}..{hi.x:.2f} y {lo.y:.2f}..{hi.y:.2f} z top {hi.z:.2f}")
        # Scale sanity against the manifest (instances may be scaled on purpose).
        spec = man.get(pid)
        if spec:
            size = hi - lo
            dims = o.dimensions  # local box x scale, so a rotated prop is not over-measured
            got = dims.z if "h" in spec else max(dims)
            want = (spec.get("h") or spec.get("m")) * o.scale.x
            if abs(got - want) / want > 0.15:
                issues.append(f"SCALE {o.name}: {got:.2f} m vs {want:.2f} m")
    # Interpenetration between props whose boxes overlap.
    trees = {}
    for a, b in itertools.combinations(objs, 2):
        la, ha = _bounds(a)
        lb, hb = _bounds(b)
        if any(ha[i] < lb[i] or hb[i] < la[i] for i in range(3)):
            continue
        ta = trees.get(a.name) or trees.setdefault(a.name, _bvh(a, dg))
        tb = trees.get(b.name) or trees.setdefault(b.name, _bvh(b, dg))
        n = len(ta.overlap(tb))
        if n > 40:
            issues.append(f"INTERSECT {a.name} x {b.name}: {n} face pairs")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        f.write("\n".join(issues) or "OK")
    print(f"VALIDATE {len(issues)} issues -> {report_path}")
    for i in issues:
        print("  ", i)
    return issues
