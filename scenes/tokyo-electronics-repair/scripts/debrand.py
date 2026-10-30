"""De-brand prepped props by painting over brand marks in their albedo textures (scripted texture paint).

blender -b --factory-startup --python scenes/tokyo-electronics-repair/scripts/debrand.py -- [id ...]
Regions are rectangles in the normalised coordinates of views.py's ortho images (u right, v down, 0..1).
For each region: cast rays from that view across the rectangle, collect the texels the hits land on, dilate that mask
in UV space, and fill it with a normalised-convolution blur of the surrounding unmasked texels plus a little grain, so
the patch takes the colour of the plastic/paint around it. The edited texture is saved next to the original as *_nb.png.
"""
import os
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(__file__))
from views import VIEWS, frame  # noqa: E402

ROOT = os.environ.get("ANYSCENE_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PROPS = os.path.join(ROOT, "scenes", "tokyo-electronics-repair", "props")
only = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

WRAP = [("front", 0.0, 0.22, 1.0, 1.0), ("back", 0.0, 0.22, 1.0, 1.0), ("left", 0.0, 0.22, 1.0, 1.0), ("right", 0.0, 0.22, 1.0, 1.0)]
REGIONS = {
    "oscilloscope": [("front", 0.46, 0.2, 0.62, 0.255)],
    "solder_station": [("front", 0.02, 0.42, 0.39, 0.55), ("front", 0.73, 0.2, 0.9, 0.42)],
    "repair_multimeter_yellow": [("top", 0.13, 0.09, 0.36, 0.19)],
    "repair_multimeter_red": [("front", 0.13, 0.04, 0.27, 0.13), ("front", 0.5, 0.03, 0.72, 0.14), ("top", 0.16, 0.22, 0.7, 0.32)],
    "repair_bench_psu": [("front", 0.02, 0.11, 0.98, 0.2)],
    "repair_tool_chest": [("front", 0.2, 0.02, 0.58, 0.18), ("front", 0.56, 0.15, 0.7, 0.23), ("front", 0.64, 0.24, 0.8, 0.31),
                          ("front", 0.66, 0.51, 0.82, 0.59), ("front", 0.15, 0.25, 0.3, 0.4), ("front", 0.22, 0.73, 0.48, 0.85),
                          ("right", 0.45, 0.25, 0.7, 0.42), ("right", 0.5, 0.55, 0.72, 0.7), ("left", 0.28, 0.25, 0.6, 0.42),
                          ("left", 0.25, 0.55, 0.5, 0.7), ("back", 0.62, 0.02, 0.82, 0.13), ("top", 0.1, 0.1, 0.9, 0.9)],
    # spray cans, cup noodle and tissue box are replaced by direct-modelled generic versions (props_direct.py)
    "repair_boxes_b": [("front", 0.28, 0.64, 0.62, 0.82), ("back", 0.28, 0.64, 0.62, 0.82)],
    "repair_vcr_open": [("front", 0.02, 0.43, 0.13, 0.54)],
    "repair_rice_cooker": [("front", 0.38, 0.46, 0.54, 0.56)],
    "repair_vintage_radio": [("front", 0.1, 0.58, 0.35, 0.69)],
    "repair_receiver": [("front", 0.02, 0.3, 0.27, 0.38)],
    "repair_solder_junk": [("top", 0.08, 0.26, 0.34, 0.38), ("top", 0.68, 0.38, 0.94, 0.49),
                           ("front", 0.43, 0.34, 0.69, 0.48), ("back", 0.3, 0.34, 0.57, 0.48),
                           ("left", 0.0, 0.3, 1.0, 0.6), ("right", 0.0, 0.3, 1.0, 0.6)],
    "repair_laptop_broken": [("top", 0.26, 0.3, 0.38, 0.38), ("top", 0.48, 0.72, 0.58, 0.8)],
    "repair_crt_stack": [("front", 0.46, 0.22, 0.58, 0.31)],
    "repair_turntable": [("front", 0.43, 0.18, 0.57, 0.37), ("top", 0.44, 0.27, 0.58, 0.36), ("top", 0.06, 0.71, 0.24, 0.81)],
    "repair_desk_fan": [("front", 0.36, 0.86, 0.57, 0.96), ("front", 0.4, 0.28, 0.6, 0.4)],
    "repair_kerosene_heater": [("front", 0.4, 0.46, 0.6, 0.56)],
}


def albedo_nodes(ob):
    """Material index -> the image node feeding Base Color (generated props can carry several materials)."""
    out = {}
    for i, slot in enumerate(ob.material_slots):
        if not slot.material or not slot.material.node_tree:
            continue
        for n in slot.material.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image and any(l.to_socket.name == "Base Color" for l in n.outputs["Color"].links):
                out[i] = n
                break
    return out


def box_blur(a, r):
    """Separable box blur (r px) over axes 0 and 1, edge-clamped, via cumulative sums."""
    for ax in (0, 1):
        pad = [(0, 0)] * a.ndim
        pad[ax] = (r + 1, r)
        p = np.pad(a, pad, mode="edge")
        c = np.cumsum(p, axis=ax)
        hi = np.take(c, range(2 * r + 1, c.shape[ax]), axis=ax)
        lo = np.take(c, range(0, c.shape[ax] - 2 * r - 1), axis=ax)
        a = (hi - lo) / (2 * r + 1)
    return a


class Tex:
    def __init__(self, node):
        self.node, self.img = node, node.image
        self.w, self.h = self.img.size
        px = np.empty(self.w * self.h * 4, dtype=np.float32)
        self.img.pixels.foreach_get(px)
        self.px = px.reshape(self.h, self.w, 4)
        self.rgb = self.px[..., :3].copy()
        self.total = np.zeros((self.h, self.w), dtype=bool)


def debrand(pid):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(PROPS, f"{pid}.blend"))
    ob = bpy.data.objects[pid]
    if ob.get("debranded"):
        print("already", pid)
        return
    nodes = albedo_nodes(ob)
    texs = {}  # image name -> Tex (materials may share an image)
    mat_tex = {}
    for mi, n in nodes.items():
        texs.setdefault(n.image.name, Tex(n))
        mat_tex[mi] = texs[n.image.name]
    me = ob.data
    me.calc_loop_triangles()
    verts = [v.co.copy() for v in me.vertices]
    tris = me.loop_triangles
    bvh = BVHTree.FromPolygons(verts, [tuple(t.vertices) for t in tris])
    uvl = me.uv_layers.active.data
    hits = 0
    rng = np.random.default_rng(1)
    for view, u0, v0, u1, v1 in REGIONS[pid]:
        masks = {k: np.zeros((t.h, t.w), dtype=bool) for k, t in texs.items()}
        c, span, d, hx, vx = frame(ob, view)
        area = (u1 - u0) * (v1 - v0)
        step = 1 / 512 if area > 0.05 else 0.5 / 512
        for u in np.arange(u0, u1, step):
            for v in np.arange(v0, v1, step):
                p = c + hx * ((u - 0.5) * span) + vx * ((0.5 - v) * span) - d * 3
                loc, nrm, idx, dist = bvh.ray_cast(p, d)
                if loc is None:
                    continue
                t = tris[idx]
                tx = mat_tex.get(t.material_index)
                if tx is None:
                    continue
                a, b, cc = (verts[i] for i in t.vertices)
                e0, e1, e2 = b - a, cc - a, loc - a
                d00, d01, d11, d20, d21 = e0.dot(e0), e0.dot(e1), e1.dot(e1), e2.dot(e0), e2.dot(e1)
                den = d00 * d11 - d01 * d01 or 1e-12
                bv = (d11 * d20 - d01 * d21) / den
                bw = (d00 * d21 - d01 * d20) / den
                uv = uvl[t.loops[0]].uv * (1 - bv - bw) + uvl[t.loops[1]].uv * bv + uvl[t.loops[2]].uv * bw
                masks[tx.img.name][int((uv.y % 1) * (tx.h - 1)), int((uv.x % 1) * (tx.w - 1))] = True
                hits += 1
        for k, mask in masks.items():
            tx = texs[k]
            # dilate a few texels so glyph edges are covered too (threshold: cumsum round-off leaves tiny non-zeros)
            m = box_blur(mask.astype(np.float64), 3) > 0.01
            if not m.any():
                continue
            # paint colour: the label background, i.e. the median of the brighter half of the texels under the region
            # (printing is mostly dark marks on a lighter ground); dark grounds use the darker half instead
            cols = tx.px[..., :3][m]
            lum = cols @ np.array([0.2126, 0.7152, 0.0722])
            side = lum >= np.median(lum) if np.median(lum) > 0.25 else lum <= np.median(lum)
            base_col = np.median(cols[side], axis=0)
            grain = 1 + rng.normal(0, 0.02, (tx.h, tx.w))[..., None] + box_blur(rng.normal(0, 1, (tx.h, tx.w)), 6)[..., None] * 0.15
            soft = np.clip(box_blur(m.astype(np.float64), 2) * 1.5, 0, 1)[..., None]
            tx.rgb = tx.rgb * (1 - soft) + (base_col * grain) * soft
            tx.total |= m
    painted = 0
    for k, tx in texs.items():
        if not tx.total.any():
            continue
        tx.px[..., :3] = tx.rgb
        base, ext = os.path.splitext(bpy.path.abspath(tx.img.filepath_raw or tx.img.filepath))
        if not os.path.basename(base):
            base = os.path.join(PROPS, "tex", f"{pid}_{k}")
        out = f"{base}_nb.png"
        nb = bpy.data.images.new(f"{k}_nb", tx.w, tx.h, alpha=True)
        nb.pixels.foreach_set(tx.px.ravel())
        nb.filepath_raw = out
        nb.file_format = "PNG"
        nb.save()
        nb.filepath = out
        for n in nodes.values():
            if n.image == tx.img:
                n.image = nb
        painted += int(tx.total.sum())
        # embossed print survives in the normal map: flatten the same texels there
        mat = next(sl.material for sl in ob.material_slots if sl.material and tx.node.name in sl.material.node_tree.nodes
                   and sl.material.node_tree.nodes[tx.node.name] == tx.node)
        for n in mat.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image and any(l.to_node.type == "NORMAL_MAP" for l in n.outputs["Color"].links):
                nw, nh = n.image.size
                npx = np.empty(nw * nh * 4, dtype=np.float32)
                n.image.pixels.foreach_get(npx)
                npx = npx.reshape(nh, nw, 4)
                ys = (np.arange(nh) * tx.h // nh)[:, None]
                xs = (np.arange(nw) * tx.w // nw)[None, :]
                mm = tx.total[ys, xs]
                npx[mm, 0:3] = (0.5, 0.5, 1.0)
                nimg = bpy.data.images.new(n.image.name + "_nb", nw, nh, alpha=True)
                nimg.colorspace_settings.name = "Non-Color"
                nimg.pixels.foreach_set(npx.ravel())
                nb_out = os.path.splitext(bpy.path.abspath(n.image.filepath_raw or n.image.filepath))[0] + "_nb.png"
                nimg.filepath_raw = nb_out
                nimg.file_format = "PNG"
                nimg.save()
                nimg.filepath = nb_out
                n.image = nimg
    ob["debranded"] = True
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(PROPS, f"{pid}.blend"))
    print(f"DEBRAND {pid}: {hits} hits, {painted} texels repainted over {len(texs)} textures")


for pid in REGIONS:
    if only and pid not in only:
        continue
    try:
        debrand(pid)
    except Exception as e:
        print("DEBRAND FAILED", pid, repr(e))
