"""Script repairs on prepped props (the video's "AI-assisted model repair" + "PBR refinement").

blender -b --factory-startup --python scenes/tokyo-electronics-repair/scripts/fixes.py -- [id ...]
Edits scenes/tokyo-electronics-repair/props/<id>.blend in place; run after prep.py. Fixes are keyed by prop id.
"""
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = os.environ.get("ANYSCENE_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PROPS = os.path.join(ROOT, "scenes", "tokyo-electronics-repair", "props")
only = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def albedo_image(ob):
    for slot in ob.material_slots:
        for n in slot.material.node_tree.nodes:
            if n.type == "TEX_IMAGE" and any(l.to_socket.name == "Base Color" for l in n.outputs["Color"].links):
                return n.image
    return None


def front_colour_grid(ob, step=0.004):
    """Ray-cast a grid at the prop from -Y; return (x, z, hit_y, rgb) for every hit, colour read from the albedo map."""
    me = ob.data
    me.calc_loop_triangles()
    verts = [v.co.copy() for v in me.vertices]
    tris = [tuple(t.vertices) for t in me.loop_triangles]
    bvh = BVHTree.FromPolygons(verts, tris)
    uvl = me.uv_layers.active.data
    tri_uv = [[uvl[l].uv.copy() for l in t.loops] for t in me.loop_triangles]
    img = albedo_image(ob)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    d = ob.dimensions
    out = []
    for x in np.arange(-d.x / 2, d.x / 2, step):
        for z in np.arange(0.002, d.z, step):
            loc, nrm, idx, dist = bvh.ray_cast(Vector((x, -1.0, z)), Vector((0, 1, 0)))
            if loc is None:
                continue
            t = me.loop_triangles[idx]
            a, b, c = (verts[i] for i in t.vertices)
            # barycentric weights for UV interpolation
            v0, v1, v2 = b - a, c - a, loc - a
            d00, d01, d11, d20, d21 = v0.dot(v0), v0.dot(v1), v1.dot(v1), v2.dot(v0), v2.dot(v1)
            den = d00 * d11 - d01 * d01 or 1e-12
            bv = (d11 * d20 - d01 * d21) / den
            bw = (d00 * d21 - d01 * d20) / den
            bu = 1 - bv - bw
            uv = tri_uv[idx][0] * bu + tri_uv[idx][1] * bv + tri_uv[idx][2] * bw
            col = px[int((uv.y % 1) * (h - 1)), int((uv.x % 1) * (w - 1)), :3]
            out.append((x, z, loc.y, col))
    return out


def crt_material(name, tint, trace=True, strength=6.0):
    """CRT face: dark tinted glass with a phosphor graticule and a sine trace (oscilloscope), or a flat glow (TV)."""
    m = bpy.data.materials.new(name)
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.01, 0.015, 0.012, 1)
    b.inputs["Roughness"].default_value = 0.08
    b.inputs["Coat Weight"].default_value = 1.0
    b.inputs["Coat Roughness"].default_value = 0.03
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs["Vector"])
    glow = nt.nodes.new("ShaderNodeMath")
    if trace:
        # graticule: thin lines every 1/10 in x and 1/8 in y
        def lines(axis, n):
            mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = n
            nt.links.new(sep.outputs[axis], mul.inputs[0])
            fr = nt.nodes.new("ShaderNodeMath"); fr.operation = "PINGPONG"; fr.inputs[1].default_value = 0.5
            nt.links.new(mul.outputs[0], fr.inputs[0])
            lt = nt.nodes.new("ShaderNodeMath"); lt.operation = "LESS_THAN"; lt.inputs[1].default_value = 0.03
            nt.links.new(fr.outputs[0], lt.inputs[0])
            return lt.outputs[0]
        grid = nt.nodes.new("ShaderNodeMath"); grid.operation = "MAXIMUM"
        nt.links.new(lines("X", 10), grid.inputs[0]); nt.links.new(lines("Y", 8), grid.inputs[1])
        # trace: |y - (0.5 + 0.28 sin(2pi*2.5x))| < 0.012
        sx = nt.nodes.new("ShaderNodeMath"); sx.operation = "MULTIPLY"; sx.inputs[1].default_value = 2 * math.pi * 2.5
        nt.links.new(sep.outputs["X"], sx.inputs[0])
        sn = nt.nodes.new("ShaderNodeMath"); sn.operation = "SINE"; nt.links.new(sx.outputs[0], sn.inputs[0])
        sa = nt.nodes.new("ShaderNodeMath"); sa.operation = "MULTIPLY_ADD"; sa.inputs[1].default_value = 0.28; sa.inputs[2].default_value = 0.5
        nt.links.new(sn.outputs[0], sa.inputs[0])
        df = nt.nodes.new("ShaderNodeMath"); df.operation = "SUBTRACT"; nt.links.new(sep.outputs["Y"], df.inputs[0]); nt.links.new(sa.outputs[0], df.inputs[1])
        ab = nt.nodes.new("ShaderNodeMath"); ab.operation = "ABSOLUTE"; nt.links.new(df.outputs[0], ab.inputs[0])
        tr = nt.nodes.new("ShaderNodeMath"); tr.operation = "SMOOTH_MIN"  # soft falloff for phosphor bloom
        tr2 = nt.nodes.new("ShaderNodeMapRange"); tr2.inputs["From Min"].default_value = 0.02; tr2.inputs["From Max"].default_value = 0.0
        nt.links.new(ab.outputs[0], tr2.inputs["Value"])
        glow.operation = "MULTIPLY_ADD"
        nt.links.new(grid.outputs[0], glow.inputs[0]); glow.inputs[1].default_value = 0.12
        nt.links.new(tr2.outputs["Result"], glow.inputs[2])
        base = nt.nodes.new("ShaderNodeMath"); base.operation = "ADD"; base.inputs[1].default_value = 0.025
        nt.links.new(glow.outputs[0], base.inputs[0])
        g_out = base.outputs[0]
    else:
        nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 400
        nt.links.new(tc.outputs["UV"], nz.inputs["Vector"])
        glow.operation = "MULTIPLY_ADD"; glow.inputs[1].default_value = 0.25; glow.inputs[2].default_value = 0.6
        nt.links.new(nz.outputs["Fac"], glow.inputs[0])
        g_out = glow.outputs[0]
    em = nt.nodes.new("ShaderNodeMath"); em.operation = "MULTIPLY"; em.inputs[1].default_value = strength
    nt.links.new(g_out, em.inputs[0])
    if not trace:  # TVs: instances share this material, so the glow is switched per object by the "tv_on" property
        at = nt.nodes.new("ShaderNodeAttribute"); at.attribute_type = "OBJECT"; at.attribute_name = "tv_on"
        em2 = nt.nodes.new("ShaderNodeMath"); em2.operation = "MULTIPLY"
        nt.links.new(em.outputs[0], em2.inputs[0]); nt.links.new(at.outputs["Fac"], em2.inputs[1])
        em = em2
    b.inputs["Emission Color"].default_value = (*tint, 1)
    nt.links.new(em.outputs[0], b.inputs["Emission Strength"])
    return m


def screen_patch(ob, rect, y, mat, name, bulge=0.004):
    """Slightly domed patch over rect=(x0, z0, x1, z1) at depth y (just in front of the hit surface), UV 0..1."""
    x0, z0, x1, z1 = rect
    me = bpy.data.meshes.new(name)
    nx, nz = 12, 10
    vs, fs, uvs = [], [], []
    for j in range(nz + 1):
        for i in range(nx + 1):
            u, v = i / nx, j / nz
            dome = bulge * (1 - (2 * u - 1) ** 2) * (1 - (2 * v - 1) ** 2)
            vs.append((x0 + (x1 - x0) * u, y - 0.0015 - dome, z0 + (z1 - z0) * v))
    for j in range(nz):
        for i in range(nx):
            a = j * (nx + 1) + i
            fs.append((a, a + 1, a + nx + 2, a + nx + 1))
    me.from_pydata(vs, [], fs)
    uv = me.uv_layers.new(name="UVMap")
    for li, l in enumerate(me.loops):
        k = l.vertex_index
        uv.data[li].uv = ((k % (nx + 1)) / nx, (k // (nx + 1)) / nz)
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    p = bpy.data.objects.new(name, me)
    ob.users_collection[0].objects.link(p)
    return p


def join_into(ob, part):
    bpy.ops.object.select_all(action="DESELECT")
    part.select_set(True)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.join()


def fix_oscilloscope(ob):
    hits = front_colour_grid(ob)
    green = [(x, z, y) for x, z, y, c in hits if c[1] > c[0] + 0.06 and c[1] > c[2] + 0.02 and c[1] > 0.12]
    xs, zs, ys = zip(*green)
    # trim outliers (labels with green ink) to the dense core
    x0, x1 = np.percentile(xs, 3), np.percentile(xs, 97)
    z0, z1 = np.percentile(zs, 3), np.percentile(zs, 97)
    y = float(np.percentile(ys, 10))
    print(f"oscilloscope screen rect x {x0:.3f}..{x1:.3f} z {z0:.3f}..{z1:.3f} y {y:.3f} from {len(green)} green hits")
    join_into(ob, screen_patch(ob, (x0, z0, x1, z1), y, crt_material("scope_crt", (0.25, 1.0, 0.45)), "screen"))


def fix_lens(ob):
    """Helping hands: the generator returned the magnifier as a solid disc; turn its inner faces into glass."""
    vs = [v.co for v in ob.data.vertices]
    top = max(v.z for v in vs)
    up = [v for v in vs if v.z > top - 0.08]
    c = Vector((sum(v.x for v in up) / len(up), sum(v.y for v in up) / len(up), sum(v.z for v in up) / len(up)))
    r = (max(v.x for v in up) - min(v.x for v in up)) / 2
    glass = bpy.data.materials.new("lens_glass")
    g = glass.node_tree.nodes["Principled BSDF"]
    g.inputs["Base Color"].default_value = (0.95, 0.97, 0.96, 1)
    g.inputs["Roughness"].default_value = 0.02
    g.inputs["Transmission Weight"].default_value = 1.0
    g.inputs["IOR"].default_value = 1.52
    ob.data.materials.append(glass)
    gi = len(ob.data.materials) - 1
    n = 0
    for p in ob.data.polygons:
        pc = p.center
        if (Vector((pc.x, 0, pc.z)) - Vector((c.x, 0, c.z))).length < r * 0.8 and abs(pc.y - c.y) < r * 0.5:
            p.material_index = gi
            n += 1
    print(f"helping_hands lens: {n} faces -> glass (centre {tuple(round(v, 3) for v in c)}, r {r:.3f})")


def fix_crt_tv(ob):
    """Shelf CRT left on a dark blue 'no signal' screen: find the dark screen on the front, put a glowing patch on it."""
    hits = front_colour_grid(ob)
    d = ob.dimensions
    dark = [(x, z, y) for x, z, y, c in hits if sum(c) / 3 < 0.09 and abs(x) < d.x * 0.45 and z > d.z * 0.2]
    xs, zs, ys = zip(*dark)
    x0, x1 = np.percentile(xs, 10), np.percentile(xs, 90)
    z0, z1 = np.percentile(zs, 10), np.percentile(zs, 90)
    y = float(min(ys)) - 0.002  # (front is -Y) just in front of the tube's most forward point (the patch adds its own dome)
    print(f"crt screen rect x {x0:.3f}..{x1:.3f} z {z0:.3f}..{z1:.3f}")
    join_into(ob, screen_patch(ob, (x0, z0, x1, z1), y, crt_material("tv_crt", (0.12, 0.25, 1.0), trace=False, strength=0.4), "screen", 0.008))


FIXES = {"oscilloscope": fix_oscilloscope, "helping_hands": fix_lens, "repair_crt_tv": fix_crt_tv}

for pid, fn in FIXES.items():
    if only and pid not in only:
        continue
    path = os.path.join(PROPS, f"{pid}.blend")
    if not os.path.exists(path):
        print("skip (not prepped)", pid)
        continue
    bpy.ops.wm.open_mainfile(filepath=path)
    ob = bpy.data.objects[pid]
    if ob.get("fixed"):
        print("already fixed", pid)
        continue
    fn(ob)
    ob = bpy.data.objects[pid]
    ob["fixed"] = True
    bpy.ops.wm.save_as_mainfile(filepath=path)
    print("FIXED", pid)
