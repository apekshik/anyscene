"""Ramen scene helpers: geometry primitives and procedural materials (Blender 5.0, Cycles)."""
import math
import os

import bpy
from mathutils import Vector

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SCENE_DIR = os.path.join(ROOT, "scenes", "hk-dai-pai-dong")
TEX = os.path.join(ROOT, "refs", "hk-dai-pai-dong", "tex")


# ---------------------------------------------------------------- collections / objects

def coll(name, parent=None):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    p = parent or bpy.context.scene.collection
    if c.name not in [x.name for x in p.children]:
        p.children.link(c)
    return c


def link(obj, c):
    for uc in list(obj.users_collection):
        uc.objects.unlink(obj)
    c.objects.link(obj)
    return obj


def mesh_obj(name, verts, faces, c, mat=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    o = bpy.data.objects.new(name, me)
    c.objects.link(o)
    if mat:
        me.materials.append(mat)
    return o


def box(name, lo, hi, c, mat=None, bevel=0.004, rot_z=0.0):
    """Axis-aligned box from corner lo to corner hi (world metres), origin at its bottom centre."""
    lo, hi = Vector(lo), Vector(hi)
    s = hi - lo
    hx, hy = s.x / 2, s.y / 2
    v = [(-hx, -hy, 0), (hx, -hy, 0), (hx, hy, 0), (-hx, hy, 0), (-hx, -hy, s.z), (hx, -hy, s.z), (hx, hy, s.z), (-hx, hy, s.z)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    o = mesh_obj(name, v, f, c, mat)
    o.location = ((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z)
    o.rotation_euler.z = rot_z
    uv_cube(o)
    if bevel:
        m = o.modifiers.new("bevel", "BEVEL")
        m.width = bevel
        m.segments = 2
        m.limit_method = "ANGLE"
        m.harden_normals = False
    for p in o.data.polygons:
        p.use_smooth = False
    return o


def plane(name, w, h, c, mat=None, loc=(0, 0, 0), rot=(0, 0, 0)):
    """Vertical plane w x h facing -Y in local space (so rot z=0 faces the street side), UV 0-1."""
    v = [(-w / 2, 0, 0), (w / 2, 0, 0), (w / 2, 0, h), (-w / 2, 0, h)]
    o = mesh_obj(name, v, [(0, 1, 2, 3)], c, mat)
    uv = o.data.uv_layers.new(name="UVMap")
    for i, co in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
        uv.data[i].uv = co
    o.location = loc
    o.rotation_euler = rot
    return o


def cylinder(name, r, h, c, mat=None, loc=(0, 0, 0), verts=32):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, vertices=verts, location=(loc[0], loc[1], loc[2] + h / 2))
    o = bpy.context.object
    o.name = name
    link(o, c)
    if mat:
        o.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return o


def uv_cube(o, scale=1.0):
    """World-size box UVs (1 UV unit = 1 m) so image textures keep real scale."""
    me = o.data
    uv = me.uv_layers.get("UVMap") or me.uv_layers.new(name="UVMap")
    for p in me.polygons:
        n = p.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for li in p.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            a, b = [(1, 2), (0, 2), (0, 1)][ax]
            uv.data[li].uv = (co[a] * scale, co[b] * scale)


# ---------------------------------------------------------------- material helpers

def new_mat(name):
    m = bpy.data.materials.get(name)
    if m:
        return m, None
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    return m, m.node_tree


def bsdf(nt):
    return nt.nodes["Principled BSDF"]


def node(nt, kind, **inputs):
    n = nt.nodes.new(kind)
    for k, v in inputs.items():
        if k in n.inputs:
            n.inputs[k].default_value = v
        else:
            setattr(n, k, v)
    return n


def L(nt, a, b):
    nt.links.new(a, b)


def ramp(nt, stops, src=None):
    r = nt.nodes.new("ShaderNodeValToRGB")
    els = r.color_ramp.elements
    while len(els) > 2:
        els.remove(els[-1])
    for i, (pos, col) in enumerate(stops):
        e = els[i] if i < 2 else els.new(pos)
        e.position = pos
        e.color = col if len(col) == 4 else (*col, 1)
    if src is not None:
        L(nt, src, r.inputs["Fac"])
    return r


def texcoord(nt, kind="Object"):
    return nt.nodes.new("ShaderNodeTexCoord").outputs[kind]


def noise(nt, scale, detail=6, rough=0.55, coord=None, dim="3D"):
    n = node(nt, "ShaderNodeTexNoise", Scale=scale, Detail=detail, Roughness=rough)
    n.noise_dimensions = dim
    if coord is not None:
        L(nt, coord, n.inputs["Vector"])
    return n


def bump(nt, height, strength=0.2, distance=0.01, normal=None):
    b = node(nt, "ShaderNodeBump", Strength=strength, Distance=distance)
    L(nt, height, b.inputs["Height"])
    if normal is not None:
        L(nt, normal, b.inputs["Normal"])
    return b


def mix(nt, fac, a, b, blend="MIX"):
    m = nt.nodes.new("ShaderNodeMix")
    m.data_type = "RGBA"
    m.blend_type = blend
    for sock, val in (("Factor", fac), ("A", a), ("B", b)):
        if isinstance(val, bpy.types.NodeSocket):
            L(nt, val, m.inputs[sock])
        else:
            m.inputs[sock].default_value = val
    return m.outputs["Result"]


def mathn(nt, op, a, b=0.0, clamp=False):
    m = nt.nodes.new("ShaderNodeMath")
    m.operation = op
    m.use_clamp = clamp
    for i, val in enumerate((a, b)):
        if isinstance(val, bpy.types.NodeSocket):
            L(nt, val, m.inputs[i])
        else:
            m.inputs[i].default_value = val
    return m.outputs[0]


# ---------------------------------------------------------------- materials

def m_plaster(name="plaster", base=(0.62, 0.57, 0.48)):
    m, nt = new_mat(name)
    if not nt:
        return m
    co = texcoord(nt)
    n1 = noise(nt, 3.0, 8, 0.6, co)
    grime = noise(nt, 0.8, 4, 0.5, co)
    col = ramp(nt, [(0.35, (base[0] * 0.72, base[1] * 0.68, base[2] * 0.6)), (0.65, base)], n1.outputs["Fac"])
    # Smoky grime toward the ceiling (object z) mixed with low-frequency blotches.
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    L(nt, texcoord(nt, "Generated"), sep.inputs[0])
    hgt = mathn(nt, "POWER", sep.outputs["Z"], 3.0)
    gfac = mathn(nt, "MULTIPLY", mathn(nt, "ADD", hgt, mathn(nt, "MULTIPLY", grime.outputs["Fac"], 0.35)), 0.55, clamp=True)
    c2 = mix(nt, gfac, col.outputs["Color"], (0.25, 0.2, 0.14, 1), "MULTIPLY")
    b = bsdf(nt)
    L(nt, c2, b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.92
    L(nt, bump(nt, noise(nt, 40, 6, 0.6, co).outputs["Fac"], 0.12, 0.004).outputs[0], b.inputs["Normal"])
    return m


def m_wood(name, dark=(0.06, 0.03, 0.015), light=(0.2, 0.1, 0.045), along="X", scale=1.0, gloss=0.35, wear=True, fine_mix=0.35, bump_k=0.18):
    """Oiled worn wood: wave-texture grain along an axis, glossy wiped patches, cup rings (voronoi) on top."""
    m, nt = new_mat(name)
    if not nt:
        return m
    co = texcoord(nt)
    mp = nt.nodes.new("ShaderNodeMapping")
    L(nt, co, mp.inputs["Vector"])
    # Stretch the noise along the grain axis.
    s = {"X": (0.12, 3.0, 3.0), "Y": (3.0, 0.12, 3.0), "Z": (3.0, 3.0, 0.12)}[along]
    mp.inputs["Scale"].default_value = [v * scale for v in s]
    wave = node(nt, "ShaderNodeTexWave", Scale=1.6, Distortion=9.0, Detail=6.0)
    wave.wave_type = "BANDS"
    wave.bands_direction = {"X": "Y", "Y": "X", "Z": "X"}[along]
    L(nt, mp.outputs[0], wave.inputs["Vector"])
    fine = noise(nt, 30, 10, 0.7, mp.outputs[0])
    g = mix(nt, fine_mix, wave.outputs["Fac"], fine.outputs["Fac"])
    col = ramp(nt, [(0.2, dark), (0.85, light)], g)
    b = bsdf(nt)
    blot = noise(nt, 1.3, 3, 0.5, co)
    rough = ramp(nt, [(0.35, (gloss * 0.45,) * 3), (0.7, (gloss * 1.9,) * 3)], blot.outputs["Fac"]).outputs["Color"]
    base = col.outputs["Color"]
    if wear:
        # Cup rings: thin bands of voronoi distance, a few per metre.
        # Two sets: glass rings (~3.5 cm radius) and bowl rings (~6 cm), each on about half the cells.
        for sc_, band, sel in ((3.0, 0.105, 0.5), (1.7, 0.1, 0.62)):
            vor = node(nt, "ShaderNodeTexVoronoi", Scale=sc_, Randomness=1.0)
            L(nt, co, vor.inputs["Vector"])
            ring = ramp(nt, [(0.0, (0, 0, 0)), (band - 0.008, (0, 0, 0)), (band, (1, 1, 1)), (band + 0.012, (0, 0, 0))], vor.outputs["Distance"])
            rsel = ramp(nt, [(0.0, (0, 0, 0)), (sel, (0, 0, 0)), (sel + 0.02, (1, 1, 1))], vor.outputs["Color"])
            rings = mathn(nt, "MULTIPLY", ring.outputs["Color"], rsel.outputs["Color"])
            base = mix(nt, mathn(nt, "MULTIPLY", rings, 0.7), base, (0.02, 0.01, 0.005, 1))
        # Worn edges: where the bevelled normal departs from the true normal, the finish is rubbed through.
        bv = nt.nodes.new("ShaderNodeBevel")
        bv.inputs["Radius"].default_value = 0.006
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        dot = nt.nodes.new("ShaderNodeVectorMath")
        dot.operation = "DOT_PRODUCT"
        L(nt, bv.outputs[0], dot.inputs[0])
        L(nt, geo.outputs["Normal"], dot.inputs[1])
        edge = ramp(nt, [(0.9, (1, 1, 1)), (0.985, (0, 0, 0))], dot.outputs["Value"])
        base = mix(nt, mathn(nt, "MULTIPLY", edge.outputs["Color"], 0.8), base, (0.36, 0.22, 0.12, 1))
        rough = mix(nt, edge.outputs["Color"], rough, (0.75, 0.75, 0.75, 1))
        # Edge wear lightens high-traffic zones (low-frequency noise).
        base = mix(nt, mathn(nt, "MULTIPLY", ramp(nt, [(0.55, (0, 0, 0)), (0.8, (1, 1, 1))], noise(nt, 2.0, 4, 0.5, co).outputs["Fac"]).outputs["Color"], 0.35), base, (0.32, 0.2, 0.11, 1))
    L(nt, base, b.inputs["Base Color"])
    L(nt, rough, b.inputs["Roughness"])
    b.inputs["Coat Weight"].default_value = 0.15
    b.inputs["Coat Roughness"].default_value = 0.25
    L(nt, bump(nt, g, bump_k, 0.002).outputs[0], b.inputs["Normal"])
    return m


def m_concrete_wet(name="concrete_wet"):
    m, nt = new_mat(name)
    if not nt:
        return m
    co = texcoord(nt)
    n1 = noise(nt, 6, 10, 0.65, co)
    col = ramp(nt, [(0.3, (0.035, 0.034, 0.032)), (0.7, (0.11, 0.105, 0.095))], n1.outputs["Fac"])
    puddle = ramp(nt, [(0.48, (0.0,) * 3), (0.56, (1.0,) * 3)], noise(nt, 0.9, 3, 0.5, co).outputs["Fac"])
    b = bsdf(nt)
    L(nt, mix(nt, mathn(nt, "MULTIPLY", puddle.outputs["Color"], 0.5), col.outputs["Color"], (0.015, 0.015, 0.014, 1)), b.inputs["Base Color"])
    rough = mix(nt, puddle.outputs["Color"], (0.7, 0.7, 0.7, 1), (0.08, 0.08, 0.08, 1))
    L(nt, rough, b.inputs["Roughness"])
    L(nt, bump(nt, noise(nt, 60, 8, 0.7, co).outputs["Fac"], 0.25, 0.003).outputs[0], b.inputs["Normal"])
    return m


def m_stainless(name="stainless", brushed_axis="X", smudge=0.6, dark=False):
    m, nt = new_mat(name)
    if not nt:
        return m
    co = texcoord(nt)
    mp = nt.nodes.new("ShaderNodeMapping")
    L(nt, co, mp.inputs["Vector"])
    mp.inputs["Scale"].default_value = {"X": (1, 400, 400), "Y": (400, 1, 400), "Z": (400, 400, 1)}[brushed_axis]
    brush = noise(nt, 1.0, 4, 0.5, mp.outputs[0])
    smear = noise(nt, 2.5, 6, 0.6, co)
    b = bsdf(nt)
    b.inputs["Metallic"].default_value = 1.0
    c = (0.42, 0.42, 0.43, 1) if dark else (0.62, 0.62, 0.63, 1)
    grease = ramp(nt, [(0.45, (0, 0, 0)), (0.75, (1, 1, 1))], smear.outputs["Fac"])
    L(nt, mix(nt, mathn(nt, "MULTIPLY", grease.outputs["Color"], 0.5 * smudge), c, (0.25, 0.22, 0.17, 1)), b.inputs["Base Color"])
    r = ramp(nt, [(0.0, (0.18,) * 3), (1.0, (0.42,) * 3)], mix(nt, 0.5, brush.outputs["Fac"], grease.outputs["Color"]))
    L(nt, r.outputs["Color"], b.inputs["Roughness"])
    b.inputs["Anisotropic"].default_value = 0.5
    return m


def m_glass_rain(name="glass_rain", tint=(0.9, 0.95, 0.95)):
    """Door/window glass with raindrops (voronoi bumps) and a streaky dirty film."""
    m, nt = new_mat(name)
    if not nt:
        return m
    co = texcoord(nt)
    vor = node(nt, "ShaderNodeTexVoronoi", Scale=45.0, Randomness=1.0)
    vor.feature = "SMOOTH_F1" if hasattr(vor, "feature") else vor.feature
    L(nt, co, vor.inputs["Vector"])
    drop = ramp(nt, [(0.0, (1, 1, 1)), (0.3, (0, 0, 0))], vor.outputs["Distance"])
    mask = ramp(nt, [(0.55, (0, 0, 0)), (0.6, (1, 1, 1))], vor.outputs["Color"])
    h = mathn(nt, "MULTIPLY", drop.outputs["Color"], mask.outputs["Color"])
    b = bsdf(nt)
    b.inputs["Base Color"].default_value = (*tint, 1)
    b.inputs["Transmission Weight"].default_value = 1.0
    b.inputs["IOR"].default_value = 1.45
    film = noise(nt, 3, 6, 0.6, co)
    L(nt, ramp(nt, [(0.3, (0.02,) * 3), (0.8, (0.12,) * 3)], film.outputs["Fac"]).outputs["Color"], b.inputs["Roughness"])
    L(nt, bump(nt, h, 0.6, 0.002).outputs[0], b.inputs["Normal"])
    return m


def m_simple(name, color, rough=0.5, metal=0.0, coat=0.0, trans=0.0, ior=1.45, emission=None, estr=0.0, alpha=1.0):
    m, nt = new_mat(name)
    if not nt:
        return m
    b = bsdf(nt)
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Transmission Weight"].default_value = trans
    b.inputs["IOR"].default_value = ior
    b.inputs["Alpha"].default_value = alpha
    if emission:
        b.inputs["Emission Color"].default_value = (*emission, 1)
        b.inputs["Emission Strength"].default_value = estr
    return m


def m_image(name, path, rough=0.7, emission=0.0, translucent=0.0, alpha_from_image=False, bump_strength=0.0):
    m, nt = new_mat(name)
    if not nt:
        return m
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(path, check_existing=True)
    b = bsdf(nt)
    L(nt, tex.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = rough
    if emission:
        L(nt, tex.outputs["Color"], b.inputs["Emission Color"])
        b.inputs["Emission Strength"].default_value = emission
    if translucent:
        b.inputs["Subsurface Weight"].default_value = 0.0
        tr = nt.nodes.new("ShaderNodeBsdfTranslucent")
        L(nt, tex.outputs["Color"], tr.inputs["Color"])
        mx = nt.nodes.new("ShaderNodeMixShader")
        mx.inputs[0].default_value = translucent
        out = nt.nodes["Material Output"]
        L(nt, b.outputs[0], mx.inputs[1])
        L(nt, tr.outputs[0], mx.inputs[2])
        L(nt, mx.outputs[0], out.inputs["Surface"])
    if bump_strength:
        bw = nt.nodes.new("ShaderNodeRGBToBW")
        L(nt, tex.outputs["Color"], bw.inputs[0])
        L(nt, bump(nt, bw.outputs[0], bump_strength, 0.002).outputs[0], b.inputs["Normal"])
    return m


def m_tile(name="tile_white"):
    m, nt = new_mat(name)
    if not nt:
        return m
    co = texcoord(nt, "UV")  # brick is 2D (ignores Z of object coords), so use the world-scale box UVs
    br = node(nt, "ShaderNodeTexBrick", Scale=1.0, **{"Mortar Size": 0.012, "Brick Width": 0.1, "Row Height": 0.1})
    br.offset = 0.0
    L(nt, co, br.inputs["Vector"])
    br.inputs["Color1"].default_value = (0.78, 0.77, 0.72, 1)
    br.inputs["Color2"].default_value = (0.72, 0.71, 0.66, 1)
    br.inputs["Mortar"].default_value = (0.13, 0.1, 0.06, 1)  # stained grout
    grime = noise(nt, 1.5, 5, 0.55, co)
    b = bsdf(nt)
    L(nt, mix(nt, mathn(nt, "MULTIPLY", grime.outputs["Fac"], 0.45), br.outputs["Color"], (0.35, 0.28, 0.17, 1), "MULTIPLY"), b.inputs["Base Color"])
    L(nt, ramp(nt, [(0.0, (0.08,) * 3), (1.0, (0.6,) * 3)], br.outputs["Fac"]).outputs["Color"], b.inputs["Roughness"])
    L(nt, bump(nt, mathn(nt, "SUBTRACT", 1.0, br.outputs["Fac"]), 0.4, 0.003).outputs[0], b.inputs["Normal"])
    return m


# ---------------------------------------------------------------- lights

def area(name, c, loc, rot, size, energy, color=(1, 1, 1), shape="RECTANGLE", size_y=None, spread=180):
    d = bpy.data.lights.new(name, "AREA")
    d.shape = shape
    d.size = size
    if size_y:
        d.size_y = size_y
    d.energy = energy
    d.color = color
    d.spread = math.radians(spread)
    o = bpy.data.objects.new(name, d)
    c.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    # Fill/glow cards must not show up as white rectangles, directly or refracted through the rough door glass.
    o.visible_camera = False
    o.visible_transmission = False
    return o


def point(name, c, loc, energy, color=(1, 0.75, 0.45), radius=0.03):
    d = bpy.data.lights.new(name, "POINT")
    d.energy = energy
    d.color = color
    d.shadow_soft_size = radius
    o = bpy.data.objects.new(name, d)
    c.objects.link(o)
    o.location = loc
    return o


def spot(name, c, loc, rot, energy, color=(1, 0.75, 0.45), angle=110, blend=0.6, radius=0.02):
    d = bpy.data.lights.new(name, "SPOT")
    d.energy = energy
    d.color = color
    d.spot_size = math.radians(angle)
    d.spot_blend = blend
    d.shadow_soft_size = radius
    o = bpy.data.objects.new(name, d)
    c.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    return o


def blackbody(k):
    """Approximate RGB for a colour temperature (for light colours without nodes)."""
    t = k / 100.0
    r = 255 if t <= 66 else 329.7 * (t - 60) ** -0.1332
    g = 99.47 * math.log(t) - 161.12 if t <= 66 else 288.1 * (t - 60) ** -0.0755
    b = 255 if t >= 66 else (0 if t <= 19 else 138.5 * math.log(t - 10) - 305.04)
    return tuple(max(0, min(255, x)) / 255 for x in (r, g, b))
