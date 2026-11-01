"""Script repairs on prepped props: CRT faces. Generators bake screens into opaque albedo; this finds each screen on the
front of the prop and lays a thin domed patch over it carrying a placeholder material CRT_SLOT_<k> that the scene's
fixscreens.py swaps for the emissive phosphor shader (so every console instance can show a different page).

blender -b --factory-startup --python scenes/mission-control-1970s/scripts/fixes.py -- [id ...]
Edits props/<id>.blend in place (after prep.py; skipped when already fixed unless FORCE=1).
Detection (after the repair scene's oscilloscope fix): ray-cast a grid at the prop from -Y, read the albedo at each hit's UV,
mark screen-like texels (dark glass or phosphor green), take the largest connected regions in the upper part of the
front, fit a plane through their hits and build the patch on that plane. `screens_override.json` can pin a rect by hand.
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = os.environ.get("ANYSCENE_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SCN = os.path.join(ROOT, "scenes", "mission-control-1970s")
PROPS = os.path.join(SCN, "props")
OVR = os.path.join(SCN, "screens_override.json")
only = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

# id -> number of screens, shape, lowest z (fraction of height) a screen can start at, min area (m^2)
CFG = {
    "mc_console_crt": dict(n=1, zmin=0.55),
    "mc_console_twin": dict(n=2, zmin=0.55),
    "mc_console_scope": dict(n=1, zmin=0.55, round=True),
    "mc_console_comms": dict(n=1, zmin=0.55),
    "mc_crt_terminal": dict(n=1, zmin=0.3, amin=0.01),
    "mc_tv_ceiling": dict(n=1, zmin=0.0, amin=0.01, grey=True),  # b/w set: light grey glass
}


def albedo_image(ob):
    for slot in ob.material_slots:
        if not slot.material:
            continue
        for n in slot.material.node_tree.nodes:
            if n.type == "TEX_IMAGE" and any(l.to_socket.name == "Base Color" for l in n.outputs["Color"].links):
                return n.image
    for slot in ob.material_slots:  # fall back to any image
        for n in slot.material.node_tree.nodes if slot.material else []:
            if n.type == "TEX_IMAGE" and n.image:
                return n.image
    return None


def front_grid(ob, step):
    me = ob.data
    me.calc_loop_triangles()
    verts = [v.co.copy() for v in me.vertices]
    bvh = BVHTree.FromPolygons(verts, [tuple(t.vertices) for t in me.loop_triangles])
    uvl = me.uv_layers.active.data
    img = albedo_image(ob)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    d = ob.dimensions
    xs = np.arange(-d.x / 2, d.x / 2, step)
    zs = np.arange(0.002, d.z, step)
    col = np.zeros((len(zs), len(xs), 3), np.float32)
    hy = np.full((len(zs), len(xs)), np.nan, np.float32)
    ny = np.zeros((len(zs), len(xs)), np.float32)
    for j, z in enumerate(zs):
        for i, x in enumerate(xs):
            loc, nrm, idx, dist = bvh.ray_cast(Vector((x, -5.0, z)), Vector((0, 1, 0)))
            if loc is None:
                continue
            t = me.loop_triangles[idx]
            a, b, c = (verts[k] for k in t.vertices)
            v0, v1, v2 = b - a, c - a, loc - a
            d00, d01, d11, d20, d21 = v0.dot(v0), v0.dot(v1), v1.dot(v1), v2.dot(v0), v2.dot(v1)
            den = d00 * d11 - d01 * d01 or 1e-12
            bv = (d11 * d20 - d01 * d21) / den
            bw = (d00 * d21 - d01 * d20) / den
            uv = uvl[t.loops[0]].uv * (1 - bv - bw) + uvl[t.loops[1]].uv * bv + uvl[t.loops[2]].uv * bw
            col[j, i] = px[int((uv.y % 1) * (h - 1)), int((uv.x % 1) * (w - 1)), :3]
            hy[j, i] = loc.y
            ny[j, i] = nrm.y
    return xs, zs, col, hy, ny


def components(mask):
    lab = np.zeros(mask.shape, np.int32)
    n = 0
    for j0, i0 in zip(*np.nonzero(mask)):
        if lab[j0, i0]:
            continue
        n += 1
        st = [(j0, i0)]
        lab[j0, i0] = n
        while st:
            j, i = st.pop()
            for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                a, b = j + dj, i + di
                if 0 <= a < mask.shape[0] and 0 <= b < mask.shape[1] and mask[a, b] and not lab[a, b]:
                    lab[a, b] = n
                    st.append((a, b))
    return lab, n


def find_screens(ob, cfg):
    step = 0.006 if ob.dimensions.x > 0.6 else 0.003
    xs, zs, col, hy, ny = front_grid(ob, step)
    r, g, b = col[..., 0], col[..., 1], col[..., 2]
    v = col.max(axis=2)
    greenish = (g > r * 1.08) & (g >= b * 0.95)
    screenish = (greenish & (v < 0.75)) | ((v < 0.12) & (g >= r * 0.9))
    if cfg.get("grey"):
        screenish = (col.max(axis=2) - col.min(axis=2) < 0.08) & (v > 0.3)
    screenish &= ~np.isnan(hy) & (ny < -0.3)  # facing the operator
    zz = np.broadcast_to(zs[:, None], hy.shape)
    screenish &= zz > cfg["zmin"] * ob.dimensions.z
    # close small holes (text on the screen) with a 3x3 majority pass
    m = screenish.astype(np.float32)
    k = np.pad(m, 1)
    s = sum(k[1 + dj:1 + dj + m.shape[0], 1 + di:1 + di + m.shape[1]] for dj in (-1, 0, 1) for di in (-1, 0, 1))
    screenish = (s >= 5)
    lab, n = components(screenish)
    amin = cfg.get("amin", 0.03)
    regs = []
    for k in range(1, n + 1):
        sel = lab == k
        area = sel.sum() * step * step
        if area < amin:
            continue
        jj, ii = np.nonzero(sel)
        x0, x1 = np.percentile(xs[ii], 4), np.percentile(xs[ii], 96)
        z0, z1 = np.percentile(zs[jj], 4), np.percentile(zs[jj], 96)
        fill = area / max((x1 - x0) * (z1 - z0), 1e-6)
        if (x1 - x0) / max(z1 - z0, 1e-6) > 3 or (z1 - z0) / max(x1 - x0, 1e-6) > 3:
            continue  # strips (lamp rows, trim) are not screens
        # plane through the hits: y = a x + b z + c
        A = np.c_[xs[ii], zs[jj], np.ones(len(ii))]
        coef, *_ = np.linalg.lstsq(A, hy[jj, ii], rcond=None)
        regs.append(dict(area=area, rect=(float(x0), float(z0), float(x1), float(z1)), plane=[float(c) for c in coef], fill=float(fill)))
    regs.sort(key=lambda r: -r["area"])
    return sorted(regs[:cfg["n"]], key=lambda r: r["rect"][0])


def patch(ob, reg, k, round_=False, bulge=0.006):
    x0, z0, x1, z1 = reg["rect"]
    a, b, c = reg["plane"]
    # most-forward point of the screen face on this plane, so the patch sits proud of the bezel glass
    me = bpy.data.meshes.new(f"screen_{k}")
    nx, nz = 16, 12
    vs, fs = [], []
    for j in range(nz + 1):
        for i in range(nx + 1):
            u, v = i / nx, j / nz
            if round_:  # disc: squash the square grid into a circle
                cu, cv = 2 * u - 1, 2 * v - 1
                cu, cv = cu * math.sqrt(1 - cv * cv / 2), cv * math.sqrt(1 - cu * cu / 2)
                u, v = (cu + 1) / 2, (cv + 1) / 2
            x, z = x0 + (x1 - x0) * u, z0 + (z1 - z0) * v
            dome = bulge * max(0.0, 1 - (2 * u - 1) ** 2) * max(0.0, 1 - (2 * v - 1) ** 2)
            vs.append((x, a * x + b * z + c - 0.003 - dome, z))
    for j in range(nz):
        for i in range(nx):
            q = j * (nx + 1) + i
            fs.append((q, q + 1, q + nx + 2, q + nx + 1))
    me.from_pydata(vs, [], fs)
    uv = me.uv_layers.new(name=ob.data.uv_layers.active.name)
    for li, l in enumerate(me.loops):
        vi = l.vertex_index
        uv.data[li].uv = ((vi % (nx + 1)) / nx, (vi // (nx + 1)) / nz)
    for p in me.polygons:
        p.use_smooth = True
    mat = bpy.data.materials.get(f"CRT_SLOT_{k}") or bpy.data.materials.new(f"CRT_SLOT_{k}")
    mat.diffuse_color = (0.2, 1, 0.4, 1)
    me.materials.append(mat)
    p = bpy.data.objects.new(f"screen_{k}", me)
    ob.users_collection[0].objects.link(p)
    bpy.ops.object.select_all(action="DESELECT")
    p.select_set(True)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.join()


ovr = json.load(open(OVR)) if os.path.exists(OVR) else {}
report = {}
for pid, cfg in CFG.items():
    if only and pid not in only:
        continue
    path = os.path.join(PROPS, f"{pid}.blend")
    if not os.path.exists(path):
        print("FIX skip (not prepped)", pid)
        continue
    bpy.ops.wm.open_mainfile(filepath=path)
    ob = bpy.data.objects[pid]
    if ob.get("fixed") and not os.environ.get("FORCE"):
        print("FIX already", pid)
        continue
    regs = ovr.get(pid) or find_screens(ob, cfg)
    for k, reg in enumerate(regs):
        rnd = cfg.get("round", False) or reg.get("round", False)
        patch(ob, reg, k, rnd, bulge=0.022 if rnd else 0.006)  # radar tubes bulge well past the bezel plane
    ob = bpy.data.objects[pid]
    ob["fixed"] = True
    ob["screens"] = len(regs)
    report[pid] = regs
    bpy.ops.wm.save_as_mainfile(filepath=path)
    print(f"FIXED {pid}: {len(regs)} screens " + "; ".join(f"x {r['rect'][0]:.3f}..{r['rect'][2]:.3f} z {r['rect'][1]:.3f}..{r['rect'][3]:.3f} fill {r.get('fill', 1):.2f}" for r in regs), flush=True)
rp = os.path.join(SCN, "out", "screens_found.json")
old = json.load(open(rp)) if os.path.exists(rp) else {}
old.update(report)
os.makedirs(os.path.dirname(rp), exist_ok=True)
json.dump(old, open(rp, "w"), indent=1)
