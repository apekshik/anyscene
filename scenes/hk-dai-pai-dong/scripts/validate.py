"""Placement validator: FLOAT (contact-point gap, as pipeline/grounding.py), CLIP (prop x prop), FURNITURE (prop x fixed structure), SCALE, OUT.

Run after every dressing pass (build.py does). resolve() spiral-searches small clashing/floating props to a clear spot.
Some reports are legitimate and listed in ACCEPT with the reason (woks sit in the burner wells, etc.).
"""
import itertools
import json
import math
import os
import re

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

import shell as S
from lib import SCENE_DIR

FIXED_COLLS = ("stall", "shell", "street", "signs")
SKIP_FIXED = ("pavement", "road", "line_", "drain_", "harbour", "kerb", "far_", "skyline")  # ground is the support
GROUND_ONLY = ("hk_stool", "hk_table")  # furniture that must stand on the pavement/road, never on another prop
GROUND = ("pavement", "road", "kerb")
# (regex on "a x b" or the prop name, reason): reviewed and accepted reports.
ACCEPT = [
    (r"wok_(rice|back).* x wok_range", "woks sit down in the burner wells"),
    (r"wok_range x wok_(rice|back)", "woks sit down in the burner wells"),
    (r"FLOAT .*hk_umbrella", "leans on the awning pole"),
    (r"SCALE hk_newspaper", "direct-modelled folded paper (8 mm), manifest h was for the generated one"),
]


def _bb(o):
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    for ch in o.children:
        pts += [ch.matrix_world @ Vector(c) for c in ch.bound_box]
    return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))


def _tree(o, dg, lift=0.0):
    ev = o.evaluated_get(dg)
    me = ev.to_mesh()
    me.transform(Matrix.Translation((0, 0, lift)) @ o.matrix_world)
    t = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
    ev.to_mesh_clear()
    return t


def _overlap(a, b):
    (la, ha), (lb, hb) = a, b
    return not any(ha[i] < lb[i] or hb[i] < la[i] for i in range(3))


def check(placed):
    import dress
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    man = {p["id"]: p for p in json.load(open(os.path.join(SCENE_DIR, "assets.json"), encoding="utf-8"))["generate"]}
    issues = []  # (kind, obj, text)
    objs = [o for o, _ in placed if o.name in bpy.data.objects]
    boxes = {o.name: _bb(o) for o in objs}
    for o, mode in placed:
        if o.name not in bpy.data.objects:
            continue
        lo, hi = boxes[o.name]
        if mode == "rest":
            # contact points (lowest vertices), not the bbox: a stool whose box clipped a table top sat 74 cm up
            g, on = dress.contact_gap(o)
            if g is None or g > 0.01:
                gap = "nothing below" if g is None else f"{g * 100:.1f} cm above {on}"
                issues.append(("FLOAT", o, f"FLOAT {o.name} ({o['prop_id']}): {gap}"))
            elif o["prop_id"].startswith(GROUND_ONLY) and not on.startswith(GROUND):
                issues.append(("FLOAT", o, f"GROUND {o.name} ({o['prop_id']}): stands on {on}, not the ground"))
        if lo.x < S.FX0 - 0.6 or hi.x > S.FX1 + 0.6 or lo.z < S.ROAD_Z - 0.03:
            issues.append(("OUT", o, f"OUT {o.name}: x {lo.x:.2f}..{hi.x:.2f} z {lo.z:.2f}"))
        spec = man.get(o.get("prop_id"))
        if spec:
            d = o.dimensions
            target = spec.get("h") or spec["m"]
            got = d.z if "h" in spec else max(d)
            want = target * o.scale.z
            if abs(got / o.scale.z - target) / target > 0.15:
                issues.append(("SCALE", o, f"SCALE {o.name}: {got:.2f} m vs {want:.2f} m"))
    trees = {}
    for a, b in itertools.combinations(objs, 2):
        if not _overlap(boxes[a.name], boxes[b.name]):
            continue
        ta = trees.get(a.name) or trees.setdefault(a.name, _tree(a, dg))
        tb = trees.get(b.name) or trees.setdefault(b.name, _tree(b, dg))
        n = len(ta.overlap(tb))
        if n > 30:
            small = a if (boxes[a.name][1] - boxes[a.name][0]).length < (boxes[b.name][1] - boxes[b.name][0]).length else b
            issues.append(("CLIP", small, f"CLIP {a.name} x {b.name}: {n} tri pairs"))
    fixed = [o for o in bpy.context.scene.objects if o.type in ("MESH", "FONT") and o.visible_get()
             and any(c.name in FIXED_COLLS for c in o.users_collection) and not o.name.startswith(SKIP_FIXED)]
    fb = {f.name: _bb(f) for f in fixed}
    ft = {}
    for o in objs:
        t = None
        for f in fixed:
            if not _overlap(boxes[o.name], fb[f.name]):
                continue
            t = t or _tree(o, dg, lift=0.003)
            tf = ft.get(f.name) or ft.setdefault(f.name, _tree(f, dg))
            n = len(t.overlap(tf))
            if n > 15:
                issues.append(("FURNITURE", o, f"FURNITURE {o.name} x {f.name}: {n} tri pairs"))
    return issues


def accepted(text):
    for pat, why in ACCEPT:
        if re.search(pat, text):
            return why
    return None


def resolve(placed, rounds=2):
    """Spiral-search small props (< 0.6 m) that clash or float to the nearest clear spot on the same support."""
    import dress
    moved = 0
    for _ in range(rounds):
        bad = {o.name: o for kind, o, t in check(placed) if kind in ("CLIP", "FURNITURE", "FLOAT") and not accepted(t)
               and o.get("mode") == "rest" and max(o.dimensions) < 0.6}
        if not bad:
            break
        for o in bad.values():
            x0, y0 = o.location.x, o.location.y
            best = None
            for k in range(1, 40):
                ang = k * 2.4
                r = 0.03 * math.sqrt(k) * 1.6
                o.location.x, o.location.y = x0 + r * math.cos(ang), y0 + r * math.sin(ang)
                dress._drop(o, o.get("start_z", 1.5))
                bpy.context.view_layer.update()
                if not [t for kind, oo, t in check([(o, "rest")] + [(p, m) for p, m in placed if p is not o and _overlap(_bb(p), _bb(o))])
                        if oo is o or o.name in t]:
                    best = (o.location.x, o.location.y, o.location.z)
                    break
            if best:
                moved += 1
            else:
                o.location.x, o.location.y = x0, y0
                dress._drop(o, o.get("start_z", 1.5))
    print("RESOLVE moved", moved, flush=True)
    return moved


def run(placed, report_path):
    issues = check(placed)
    lines = []
    for kind, o, t in issues:
        why = accepted(t)
        lines.append(f"{t}   [accepted: {why}]" if why else t)
    open_ = [l for l in lines if "[accepted" not in l]
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) or "OK")
        f.write(f"\n\nVALIDATE {len(open_)} open, {len(lines) - len(open_)} accepted, {len(placed)} props\n")
    print(f"VALIDATE {len(open_)} open, {len(lines) - len(open_)} accepted over {len(placed)} props -> {report_path}", flush=True)
    for l in open_:
        print("  ", l)
    return open_
