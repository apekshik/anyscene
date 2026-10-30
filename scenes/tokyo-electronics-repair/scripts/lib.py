"""Small direct-modelling + material library for the repair shop scene (Blender 5.0)."""
import math
import os
import random

import bpy
import bmesh
from mathutils import Vector

ROOT = os.environ.get("ANYSCENE_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def sock(node, name, kind=None):
    """Enabled input socket by name (Mix nodes have several sockets per name)."""
    for s in node.inputs:
        if s.name == name and s.enabled and (kind is None or s.type == kind):
            return s
    raise KeyError(name)


def collection(name, parent=None):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    p = parent or bpy.context.scene.collection
    if c.name not in [x.name for x in p.children]:
        p.children.link(c)
    return c


def link(obj, coll):
    for c in obj.users_collection:
        c.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def box(name, lo, hi, mat=None, coll=None, bevel=0.002, uv_scale=1.0):
    """Axis-aligned box from world-space corners, real geometry (no object scale), box-projected UVs in metres."""
    lo, hi = Vector(lo), Vector(hi)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    size = hi - lo
    for v in bm.verts:
        v.co = Vector((v.co.x * size.x, v.co.y * size.y, v.co.z * size.z))
    uv = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        n = f.normal
        for l in f.loops:
            co = l.vert.co + (lo + hi) / 2
            if abs(n.z) > 0.5:
                l[uv].uv = (co.x * uv_scale, co.y * uv_scale)
            elif abs(n.x) > 0.5:
                l[uv].uv = (co.y * uv_scale, co.z * uv_scale)
            else:
                l[uv].uv = (co.x * uv_scale, co.z * uv_scale)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = (lo + hi) / 2
    (coll or bpy.context.scene.collection).objects.link(ob)
    if mat:
        me.materials.append(mat)
    if bevel > 0 and min(size) > bevel * 3:
        m = ob.modifiers.new("bevel", "BEVEL")
        m.width = bevel
        m.segments = 2
        m.limit_method = "ANGLE"
        m.harden_normals = True
        for p in me.polygons:  # smooth only with a bevel + hardened normals; a smooth unbevelled slab refracts like a lens
            p.use_smooth = True
    return ob


def cylinder(name, centre, r, h, mat=None, coll=None, axis="Z", verts=24):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=centre)
    ob = bpy.context.object
    ob.name = name
    if axis == "X":
        ob.rotation_euler = (0, math.pi / 2, 0)
    elif axis == "Y":
        ob.rotation_euler = (math.pi / 2, 0, 0)
    if mat:
        ob.data.materials.append(mat)
    if coll:
        link(ob, coll)
    return ob


def plane(name, centre, w, h, normal="-Y", mat=None, coll=None):
    """Upright (or flat with normal Z) textured plane, UV 0..1."""
    me = bpy.data.meshes.new(name)
    hw, hh = w / 2, h / 2
    if normal in ("-Y", "Y"):
        vs = [(-hw, 0, -hh), (hw, 0, -hh), (hw, 0, hh), (-hw, 0, hh)]
    elif normal in ("-X", "X"):
        vs = [(0, hw, -hh), (0, -hw, -hh), (0, -hw, hh), (0, hw, hh)]
    else:
        vs = [(-hw, -hh, 0), (hw, -hh, 0), (hw, hh, 0), (-hw, hh, 0)]
    if normal in ("Y", "X"):
        vs = [vs[1], vs[0], vs[3], vs[2]]
    me.from_pydata(vs, [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for i, l in enumerate(me.loops):
        uv.data[i].uv = [(0, 0), (1, 0), (1, 1), (0, 1)][l.vertex_index]
    ob = bpy.data.objects.new(name, me)
    ob.location = centre
    (coll or bpy.context.scene.collection).objects.link(ob)
    if mat:
        me.materials.append(mat)
    return ob


def set_uv_rect(ob, u0, v0, u1, v1):
    uv = ob.data.uv_layers[0]
    for i, l in enumerate(ob.data.loops):
        c = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)][l.vertex_index]
        uv.data[i].uv = c


# ---------------------------------------------------------------- materials

def _new(name):
    m = bpy.data.materials.get(name)
    if m:
        return m, None
    m = bpy.data.materials.new(name)
    nt = m.node_tree
    return m, nt


def principled(name, color, rough=0.5, metal=0.0, **kw):
    m, nt = _new(name)
    if nt is None:
        return m
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    for k, v in kw.items():
        b.inputs[k].default_value = v
    return m


def _noise(nt, scale, detail=6, coord=None):
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    if coord is not None:
        nt.links.new(coord, n.inputs["Vector"])
    return n


def _ramp(nt, src, stops):
    r = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(src, r.inputs["Fac"])
    els = r.color_ramp.elements
    for i, (pos, col) in enumerate(stops):
        e = els[i] if i < len(els) else els.new(pos)
        e.position = pos
        e.color = (*col, 1) if len(col) == 3 else col
    return r


def _mix(nt, fac, a, b, blend="MIX"):
    m = nt.nodes.new("ShaderNodeMix")
    m.data_type = "RGBA"
    m.blend_type = blend
    if isinstance(fac, float):
        sock(m, "Factor", "VALUE").default_value = fac
    else:
        nt.links.new(fac, sock(m, "Factor", "VALUE"))
    for s, v in (("A", a), ("B", b)):
        if isinstance(v, tuple):
            sock(m, s, "RGBA").default_value = (*v, 1) if len(v) == 3 else v
        else:
            nt.links.new(v, sock(m, s, "RGBA"))
    return m.outputs["Result"]


def _bump(nt, height, strength, dist=0.002):
    b = nt.nodes.new("ShaderNodeBump")
    b.inputs["Strength"].default_value = strength
    b.inputs["Distance"].default_value = dist
    nt.links.new(height, b.inputs["Height"])
    return b.outputs["Normal"]


def grimy(name, base, grime=(0.18, 0.16, 0.13), rough=(0.45, 0.75), metal=0.0, scale=3.0, amount=0.35, bump=0.15):
    """Generic worn surface: base colour broken up by large-scale grime and fine speckle, roughness follows grime."""
    m, nt = _new(name)
    if nt is None:
        return m
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    n1 = _noise(nt, scale, 8, tc.outputs["Object"])
    n2 = _noise(nt, scale * 40, 4, tc.outputs["Object"])
    r1 = _ramp(nt, n1.outputs["Fac"], [(0.45, (0, 0, 0)), (0.75, (1, 1, 1))])
    fac = _mix(nt, 0.5, r1.outputs["Color"], n2.outputs["Color"], "MULTIPLY")
    f2 = nt.nodes.new("ShaderNodeMath")
    f2.operation = "MULTIPLY"
    f2.inputs[1].default_value = amount * 2
    nt.links.new(fac, f2.inputs[0])
    col = _mix(nt, f2.outputs[0], base, grime)
    nt.links.new(col, b.inputs["Base Color"])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value = rough[0]
    mr.inputs["To Max"].default_value = rough[1]
    nt.links.new(f2.outputs[0], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], b.inputs["Roughness"])
    b.inputs["Metallic"].default_value = metal
    nt.links.new(_bump(nt, n2.outputs["Fac"], bump), b.inputs["Normal"])
    return m


def wood(name, light=(0.42, 0.27, 0.15), dark=(0.2, 0.11, 0.05), scale=2.0, worn=0.3):
    m, nt = _new(name)
    if nt is None:
        return m
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (scale * 6, scale * 0.15, scale * 6)  # long streaks along Y (bench/shelf length)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nz = _noise(nt, 4.0, 8, mp.outputs["Vector"])
    w = nt.nodes.new("ShaderNodeTexWave")  # kept for the bump only
    w.wave_type = "BANDS"
    w.bands_direction = "X"
    w.inputs["Scale"].default_value = 40.0
    w.inputs["Distortion"].default_value = 1.5
    nt.links.new(mp.outputs["Vector"], w.inputs["Vector"])
    r = _ramp(nt, nz.outputs["Fac"], [(0.3, dark), (0.7, light)])
    grime = _noise(nt, 1.5, 6, tc.outputs["Object"])
    gr = _ramp(nt, grime.outputs["Fac"], [(0.5, (0, 0, 0)), (0.8, (1, 1, 1))])
    f = nt.nodes.new("ShaderNodeMath")
    f.operation = "MULTIPLY"
    f.inputs[1].default_value = worn
    nt.links.new(gr.outputs["Color"], f.inputs[0])
    col = _mix(nt, f.outputs[0], r.outputs["Color"], (0.06, 0.04, 0.025))
    nt.links.new(col, b.inputs["Base Color"])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value = 0.35
    mr.inputs["To Max"].default_value = 0.7
    nt.links.new(nz.outputs["Fac"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], b.inputs["Roughness"])
    nt.links.new(_bump(nt, w.outputs["Fac"], 0.08), b.inputs["Normal"])
    return m


def floor_tiles(name, tile=0.3, a=(0.55, 0.53, 0.47), b2=(0.33, 0.33, 0.31)):
    """Old checker vinyl floor tiles with grout, scuffs and traffic grime."""
    m, nt = _new(name)
    if nt is None:
        return m
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.offset = 0.0
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Brick Width"].default_value = tile
    br.inputs["Row Height"].default_value = tile
    br.inputs["Mortar Size"].default_value = 0.002
    br.inputs["Color1"].default_value = (*a, 1)
    br.inputs["Color2"].default_value = (*b2, 1)
    br.inputs["Mortar"].default_value = (0.08, 0.075, 0.07, 1)
    nt.links.new(tc.outputs["Object"], br.inputs["Vector"])
    ch = nt.nodes.new("ShaderNodeTexChecker")
    ch.inputs["Scale"].default_value = 1 / tile / 2 * 2
    ch.inputs["Color1"].default_value = (*a, 1)
    ch.inputs["Color2"].default_value = (*b2, 1)
    nt.links.new(tc.outputs["Object"], ch.inputs["Vector"])
    base = _mix(nt, br.outputs["Fac"], ch.outputs["Color"], (0.08, 0.075, 0.07))
    n1 = _noise(nt, 0.8, 8, tc.outputs["Object"])
    g = _ramp(nt, n1.outputs["Fac"], [(0.4, (0, 0, 0)), (0.75, (1, 1, 1))])
    n2 = _noise(nt, 60, 3, tc.outputs["Object"])
    col = _mix(nt, g.outputs["Color"], base, (0.12, 0.1, 0.08), "MULTIPLY")
    col = _mix(nt, 0.15, col, n2.outputs["Color"], "OVERLAY")
    nt.links.new(col, b.inputs["Base Color"])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value = 0.25
    mr.inputs["To Max"].default_value = 0.65
    nt.links.new(n1.outputs["Fac"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], b.inputs["Roughness"])
    nt.links.new(_bump(nt, br.outputs["Fac"], 0.3), b.inputs["Normal"])
    return m


def wall_paint(name, base=(0.62, 0.6, 0.55)):
    """Painted plaster: low-frequency blotches, darker grime band towards the floor."""
    m, nt = _new(name)
    if nt is None:
        return m
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    n1 = _noise(nt, 1.2, 8, tc.outputs["Object"])
    n2 = _noise(nt, 25, 6, tc.outputs["Object"])
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])
    band = _ramp(nt, sep.outputs["Z"], [(0.0, (1, 1, 1)), (0.25, (0, 0, 0))])
    blot = _ramp(nt, n1.outputs["Fac"], [(0.45, (0, 0, 0)), (0.8, (0.6, 0.6, 0.6))])
    fac = _mix(nt, 1.0, band.outputs["Color"], blot.outputs["Color"], "LIGHTEN")
    col = _mix(nt, fac, base, (0.3, 0.27, 0.22))
    col = _mix(nt, 0.08, col, n2.outputs["Color"], "OVERLAY")
    nt.links.new(col, b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.85
    nt.links.new(_bump(nt, n2.outputs["Fac"], 0.05), b.inputs["Normal"])
    return m


def rain_glass(name):
    """Storefront glass with beaded drops and vertical run streaks (normal-only, transmission glass)."""
    m, nt = _new(name)
    if nt is None:
        return m
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.9, 0.95, 0.95, 1)
    b.inputs["Roughness"].default_value = 0.03
    b.inputs["Transmission Weight"].default_value = 1.0
    b.inputs["IOR"].default_value = 1.5
    tc = nt.nodes.new("ShaderNodeTexCoord")
    vo = nt.nodes.new("ShaderNodeTexVoronoi")
    vo.feature = "SMOOTH_F1"
    vo.inputs["Scale"].default_value = 55
    vo.inputs["Randomness"].default_value = 1.0
    nt.links.new(tc.outputs["Object"], vo.inputs["Vector"])
    drops = _ramp(nt, vo.outputs["Distance"], [(0.0, (1, 1, 1)), (0.18, (0, 0, 0))])
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (60, 60, 1.2)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    st = _noise(nt, 1.0, 2, mp.outputs["Vector"])
    streak = _ramp(nt, st.outputs["Fac"], [(0.66, (0, 0, 0)), (0.7, (0.4, 0.4, 0.4))])
    mask = _noise(nt, 3, 2, tc.outputs["Object"])
    mk = _ramp(nt, mask.outputs["Fac"], [(0.4, (0, 0, 0)), (0.6, (1, 1, 1))])
    h = _mix(nt, 1.0, drops.outputs["Color"], streak.outputs["Color"], "LIGHTEN")
    h = _mix(nt, mk.outputs["Color"], (0.0, 0.0, 0.0), h)
    nt.links.new(_bump(nt, h, 0.5, 0.002), b.inputs["Normal"])
    return m


def image_mat(name, path, rough=0.7, emission=0.0, alpha=False, extend="REPEAT"):
    m, nt = _new(name)
    if nt is None:
        return m
    b = nt.nodes["Principled BSDF"]
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(path, check_existing=True)
    t.extension = extend
    nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = rough
    if emission:
        nt.links.new(t.outputs["Color"], b.inputs["Emission Color"])
        b.inputs["Emission Strength"].default_value = emission
    if alpha:
        nt.links.new(t.outputs["Color"], b.inputs["Alpha"])  # white-on-black decals: luminance as alpha
    return m


def emissive(name, color, strength):
    m, nt = _new(name)
    if nt is None:
        return m
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Emission Color"].default_value = (*color, 1)
    b.inputs["Emission Strength"].default_value = strength
    return m
