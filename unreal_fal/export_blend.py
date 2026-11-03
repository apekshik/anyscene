"""AnyScene -> Unreal export: bake every surface material to PBR textures, export one GLB per unique mesh, and write
scene.json (placements, lights, cameras, world, volumes, grade) in Unreal units and axes.

    blender -b <COPY of scene.blend> --python export_blend.py -- --out <dir> [--frame 60] [--only a,b] [--limit N]
            [--density 1024] [--max-res 4096] [--grade-sh scenes/<id>/scripts/grade.sh] [--ffmpeg path]
            [--dof '{"cam_street": [9.5, 2.8]}'] [--no-bake] [--cpu-threads 0]
            [--plan-out plan.json | --plan plan.json [--keys shard.json]] [--cache DIR [--link-cache]]

Sharded (TOGGLE.md section 5; unreal_fal/app.py runs it on fal):
  1. --plan-out plan.json: classify, name every asset, hash it (evaluated mesh + material node trees + bake settings +
     this file) and estimate its bake cost; no baking, no volumes, no world. Asset names come from the full key list,
     so they are the same in every process.
  2. --plan plan.json --keys shard.json --cache DIR: bake and export only these asset keys (any number of processes,
     on any number of machines) and store each finished asset in DIR/<hash[:2]>/<hash>/. Writes no scene.json.
  3. --plan plan.json --cache DIR --no-bake [--link-cache]: the merge. Every asset comes from the cache (symlinked with
     --link-cache), then scene.json, volumes, lights, cameras, world and grade are written as usual.
  Without --plan, --cache alone also works in one process: finished assets are reused across exports.

Never saves the .blend (it modifies the open file in memory: new UV layers, converted text/curves). Rerunnable:
textures and GLBs that already exist are skipped (delete <out>/tex/<asset>_* or <out>/mesh/<asset>.glb to redo one).

Conventions written to scene.json
  * Space: Unreal (cm, X forward, Y right, Z up, left-handed). Blender (x, y, z) m -> Unreal (x, -y, z) * 100.
    Object transforms are S*M*S with S = diag(1,-1,1), given as location, quaternion (x,y,z,w) and scale.
  * Mesh GLBs are exported in object-local space at identity; the Unreal importer maps glTF to its own axes, so
    build_level.py checks the result against "check_bounds" for the first assets.
  * Photometry: 683 lm/W. Point/spot cd = 683 * P / (4 pi); area cd = 683 * P / pi; sun lux = 683 * S;
    emissive nits = 683 * strength; sky radiance x 683. Exposure: Blender pixel = L_b * 2^exposure, so the Unreal
    manual exposure is EV100 = log2(683 / 1.2) - exposure (written as grade.ev100).
  * Bake: every surface material (procedural or not) is baked per unique mesh into one texture set on a bake UV:
    BaseColor (sRGB png), ORM (R=1, G=roughness, B=metallic, linear png), Normal (tangent, OpenGL +Y, png, only if a
    material perturbs the normal), Emissive (sRGB png + scale, only if emissive). Glass slots (transmission > 0.5)
    are not baked: they keep their own material slot and parameters.
"""
import bmesh  # noqa: F401  (kept for hand edits)
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time

import bpy
import numpy as np
from mathutils import Matrix, Vector

LM_PER_W = 683.0
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


OUT = os.path.abspath(arg("--out", "unreal_export"))
FRAME = int(arg("--frame", "60"))
ONLY = set(x for x in arg("--only", "").split(",") if x)
LIMIT = int(arg("--limit", "0"))
DENSITY = float(arg("--density", "1024"))  # bake px per metre of sqrt(surface area)
MAX_RES = int(arg("--max-res", "4096"))
NO_BAKE = "--no-bake" in argv
DOF = json.loads(arg("--dof", "{}"))
GRADE_SH = arg("--grade-sh")
FFMPEG = arg("--ffmpeg", os.environ.get("FFMPEG", "ffmpeg"))  # pipeline/env.sh exports FFMPEG (ffmpeg is not on PATH here)
THREADS = int(arg("--cpu-threads", "0"))
GPU = "--gpu" in argv          # bake with OptiX (run through pipeline/gpu_run.sh)
REVERSE = "--reverse" in argv  # walk assets from the end: a second process can share the work
PLAN_OUT = arg("--plan-out")   # plan pass: write the asset plan and stop
PLAN = arg("--plan")           # names and hashes from a plan pass (shards and merge)
KEYS = arg("--keys")           # shard: a JSON list of asset keys to bake/export; nothing else is written
CACHE = arg("--cache")         # bake cache dir: <hash[:2]>/<hash>/{mesh.glb, meta.json, base.png, ...}
LINK_CACHE = "--link-cache" in argv  # symlink cached files into --out instead of copying them

SRC = bpy.data.filepath
if not SRC or os.path.basename(SRC) == "hk.blend" and "scenes" in SRC.replace("\\", "/").split("/"):
    print("export_blend: refusing to run on a scene's own .blend; open a copy", flush=True)
    sys.exit(1)

for d in ("mesh", "tex", "world", "grade"):
    os.makedirs(os.path.join(OUT, d), exist_ok=True)

sc = bpy.context.scene
sc.frame_set(FRAME)
S = Matrix.Diagonal((1.0, -1.0, 1.0, 1.0))
LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.append(s)
    print("EXPORT", s, flush=True)


def ue_vec(v, scale=100.0):
    return [v[0] * scale, -v[1] * scale, v[2] * scale]


def ue_xform(mw):
    t = S @ mw @ S
    loc, rot, scl = t.decompose()
    return {"loc": [loc.x * 100, loc.y * 100, loc.z * 100], "quat": [rot.x, rot.y, rot.z, rot.w], "scale": list(scl)}


def ue_axes(mw):
    """Forward (-Z local) and up (+Y local) of a Blender camera/light in Unreal axes."""
    r = mw.to_3x3().normalized()
    f = r @ Vector((0, 0, -1))
    u = r @ Vector((0, 1, 0))
    return [f.x, -f.y, f.z], [u.x, -u.y, u.z]


def safe(name):
    return re.sub(r"[^A-Za-z0-9_]", "_", name)[:60]


# ------------------------------------------------------------------ material inspection

def output_node(nt):
    outs = [n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"]
    for n in outs:
        if n.is_active_output:
            return n
    return outs[0] if outs else None


def surface_shader(m):
    if not m or not m.node_tree:
        return None
    o = output_node(m.node_tree)
    if not o or not o.inputs["Surface"].is_linked:
        return None
    return o.inputs["Surface"].links[0].from_node


def is_volume_only(m):
    if not m or not m.node_tree:
        return False
    o = output_node(m.node_tree)
    return bool(o and o.inputs["Volume"].is_linked and not o.inputs["Surface"].is_linked)


def find_principled(m):
    sh = surface_shader(m)
    if sh is None:
        return None
    if sh.type == "BSDF_PRINCIPLED":
        return sh
    # Mix shaders etc.: first principled upstream.
    seen, stack = set(), [sh]
    while stack:
        n = stack.pop()
        if n.name in seen:
            continue
        seen.add(n.name)
        if n.type == "BSDF_PRINCIPLED":
            return n
        for i in n.inputs:
            for l in i.links:
                stack.append(l.from_node)
    return None


def is_glass(m):
    p = find_principled(m)
    if p is not None:
        return (not p.inputs["Transmission Weight"].is_linked) and p.inputs["Transmission Weight"].default_value > 0.5
    sh = surface_shader(m)
    return sh is not None and sh.type in ("BSDF_GLASS", "BSDF_REFRACTION")


def glass_params(m):
    p = find_principled(m)
    if p is None:
        return {"color": [1, 1, 1], "roughness": 0.0, "ior": 1.45}
    c = p.inputs["Base Color"].default_value
    return {"color": [c[0], c[1], c[2]], "roughness": p.inputs["Roughness"].default_value,
            "ior": p.inputs["IOR"].default_value, "alpha": p.inputs["Alpha"].default_value}


def emissive(m):
    sh = surface_shader(m)
    if sh is None:
        return False
    if sh.type == "EMISSION":
        return True
    p = find_principled(m)
    if p is None:
        return False
    s = p.inputs["Emission Strength"]
    c = p.inputs["Emission Color"]
    return (s.is_linked or s.default_value > 0) and (c.is_linked or any(v > 0 for v in c.default_value[:3]))


def perturbs_normal(m):
    p = find_principled(m)
    return bool(p and p.inputs["Normal"].is_linked)


def uses_object_dependence(m):
    """Nodes whose result depends on the object it sits on (bakes per representative instance)."""
    if not m or not m.node_tree:
        return []
    hits = set()
    def walk(nt):
        for n in nt.nodes:
            if n.type in ("OBJECT_INFO", "AMBIENT_OCCLUSION", "NEW_GEOMETRY", "BEVEL"):
                hits.add(n.type)
            if n.type == "TEX_COORD":
                for k in ("Object", "Generated"):
                    if n.outputs[k].is_linked:
                        hits.add("COORD_" + k)
            if n.type == "ATTRIBUTE" and n.attribute_type in ("OBJECT", "INSTANCER"):
                hits.add("ATTR_" + n.attribute_name)
            if n.type == "GROUP" and n.node_tree:
                walk(n.node_tree)
    walk(m.node_tree)
    return sorted(hits)


def animated(m):
    ad = m.node_tree.animation_data if m and m.node_tree else None
    return bool(ad and (ad.drivers or ad.action))


# ------------------------------------------------------------------ scene classification

def particle_instancers():
    srcs, emitters = set(), set()
    for o in sc.objects:
        for md in o.modifiers:
            if md.type == "PARTICLE_SYSTEM":
                st = md.particle_system.settings
                emitters.add(o.name)
                if st.render_type == "OBJECT" and st.instance_object:
                    srcs.add(st.instance_object.name)
                if st.render_type == "COLLECTION" and st.instance_collection:
                    srcs.update(x.name for x in st.instance_collection.all_objects)
    return srcs, emitters


def object_attr_values(o):
    """Values of the object attributes (Attribute node, type Object/Instancer) its materials read, e.g. a per-console
    screen_idx choosing which CRT page shows. Instances that differ in them cannot share one bake."""
    vals = set()
    for s in o.material_slots:
        for h in uses_object_dependence(s.material):
            if h.startswith("ATTR_"):
                vals.add(f"{h[5:]}={o.get(h[5:])}")
    return sorted(vals)


def mesh_key(o):
    if o.type == "MESH" and not any(md.show_render for md in o.modifiers):
        av = object_attr_values(o)
        return "m_" + o.data.name + ("|" + ",".join(av) if av else "")
    return "o_" + o.name


def tri_count(me):
    me.calc_loop_triangles()
    return len(me.loop_triangles)


def render_uv(me):
    return next((l for l in me.uv_layers if l.active_render), None) or me.uv_layers.active


def uv_ok(me):
    """True if the active render UV is a usable non-overlapping atlas inside 0..1 (generated-prop style)."""
    uvl = render_uv(me)
    if uvl is None or len(me.loop_triangles) == 0:
        return False
    n = len(me.loops)
    uv = np.empty(n * 2, np.float32)
    uvl.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    if uv.min() < -0.01 or uv.max() > 1.01:
        return False
    lt = np.empty(len(me.loop_triangles) * 3, np.int32)
    me.loop_triangles.foreach_get("loops", lt)
    t = uv[lt.reshape(-1, 3)]
    a = 0.5 * np.abs((t[:, 1, 0] - t[:, 0, 0]) * (t[:, 2, 1] - t[:, 0, 1]) - (t[:, 2, 0] - t[:, 0, 0]) * (t[:, 1, 1] - t[:, 0, 1]))
    total = float(a.sum())
    if total > 1.02 or total < 0.05:
        return False
    # Coarse overlap check: rasterise triangle centroids+vertices into a 512 grid weighted by area.
    g = 512
    idx = np.clip((t.mean(axis=1) * g).astype(np.int32), 0, g - 1)
    occ = np.zeros((g, g), np.float64)
    np.add.at(occ, (idx[:, 1], idx[:, 0]), a)
    return float(occ.max()) < 4.0 / (g * g) + 1e-4 or total < 0.9


def surface_area(o, me):
    mw = o.matrix_world
    me.calc_loop_triangles()
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    m3 = np.array(mw.to_3x3())
    co = co @ m3.T
    vt = np.empty(len(me.loop_triangles) * 3, np.int32)
    me.loop_triangles.foreach_get("vertices", vt)
    t = co[vt.reshape(-1, 3)]
    return float(0.5 * np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1).sum())


def pow2(x, lo, hi):
    r = lo
    while r < x and r < hi:
        r *= 2
    return min(r, hi)


# ------------------------------------------------------------------ baking

BAKE_SCENE = None


def bake_scene():
    global BAKE_SCENE
    if BAKE_SCENE is None:
        bs = bpy.data.scenes.new("__bake")
        bs.render.engine = "CYCLES"
        bs.cycles.device = "GPU" if GPU else "CPU"
        if GPU:  # device prefs live in user preferences, not the .blend: a factory Blender would bake on the CPU
            prefs = bpy.context.preferences.addons["cycles"].preferences
            if prefs.compute_device_type == "NONE" or not any(d.use and d.type != "CPU" for d in prefs.devices):
                prefs.compute_device_type = "OPTIX"
                prefs.get_devices()
                for d in prefs.devices:
                    d.use = d.type == "OPTIX"
            log("bake device:", prefs.compute_device_type, [d.name for d in prefs.devices if d.use])
        bs.cycles.samples = 4
        bs.cycles.use_denoising = False
        bs.render.bake.margin = 8
        bs.render.bake.use_clear = True
        bs.render.bake.target = "IMAGE_TEXTURES"
        if THREADS:
            bs.render.threads_mode = "FIXED"
            bs.render.threads = THREADS
        bs.world = sc.world
        bs.frame_current = FRAME
        BAKE_SCENE = bs
    return BAKE_SCENE


def run_bake(o, kind):
    bs = bake_scene()
    vl = bs.view_layers[0]
    with bpy.context.temp_override(scene=bs, view_layer=vl, object=o, active_object=o,
                                   selected_objects=[o], selected_editable_objects=[o]):
        if kind == "NORMAL":
            bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT", margin=8, use_clear=True)
        else:
            bpy.ops.object.bake(type="EMIT", margin=8, use_clear=True)


def _src(sock):
    return sock.links[0].from_socket if sock.is_linked else None


class Rewire:
    """Temporarily route one Principled channel into an Emission shader on the material output."""

    def __init__(self, m, channel, img):
        self.m, self.nt = m, m.node_tree
        self.added, self.saved = [], None
        nt = self.nt
        out = output_node(nt)
        p = find_principled(m)
        sh = surface_shader(m)
        em = nt.nodes.new("ShaderNodeEmission")
        self.added.append(em)
        em.inputs["Strength"].default_value = 1.0
        col = em.inputs["Color"]
        if channel == "base":
            if p is not None:
                s = p.inputs["Base Color"]
                if s.is_linked:
                    nt.links.new(_src(s), col)
                else:
                    col.default_value = s.default_value
            elif sh is not None and sh.type == "EMISSION":
                col.default_value = (0, 0, 0, 1)
            elif sh is not None and "Color" in sh.inputs:
                s = sh.inputs["Color"]
                if s.is_linked:
                    nt.links.new(_src(s), col)
                else:
                    col.default_value = s.default_value
            else:
                col.default_value = (0.5, 0.5, 0.5, 1)
        elif channel == "orm":
            # R=1 (no separate AO), G=roughness, B=metallic
            cmb = nt.nodes.new("ShaderNodeCombineColor")
            self.added.append(cmb)
            cmb.inputs[0].default_value = 1.0
            for i, k, dv in ((1, "Roughness", 0.5), (2, "Metallic", 0.0)):
                if p is not None and p.inputs[k].is_linked:
                    nt.links.new(_src(p.inputs[k]), cmb.inputs[i])
                else:
                    cmb.inputs[i].default_value = p.inputs[k].default_value if p is not None else dv
            nt.links.new(cmb.outputs[0], col)
        elif channel == "emit":
            if sh is not None and sh.type == "EMISSION":
                for k in ("Color", "Strength"):
                    s = sh.inputs[k]
                    if s.is_linked:
                        nt.links.new(_src(s), em.inputs[k])
                    else:
                        em.inputs[k].default_value = s.default_value
            elif p is not None:
                for k, ek in (("Emission Color", "Color"), ("Emission Strength", "Strength")):
                    s = p.inputs[k]
                    if s.is_linked:
                        nt.links.new(_src(s), em.inputs[ek])
                    else:
                        em.inputs[ek].default_value = s.default_value
            else:
                col.default_value = (0, 0, 0, 1)
        if out is not None:
            self.saved = _src(out.inputs["Surface"])
            nt.links.new(em.outputs[0], out.inputs["Surface"])
        self.out = out
        self.tex = nt.nodes.new("ShaderNodeTexImage")
        self.tex.image = img
        self.added.append(self.tex)
        nt.nodes.active = self.tex

    def restore(self):
        nt = self.nt
        if self.out is not None:
            for l in list(self.out.inputs["Surface"].links):
                nt.links.remove(l)
            if self.saved is not None:
                nt.links.new(self.saved, self.out.inputs["Surface"])
        for n in self.added:
            nt.nodes.remove(n)


class TargetOnly:
    """For the normal bake: keep the material, just add the active target image node."""

    def __init__(self, m, img):
        self.nt = m.node_tree
        self.tex = self.nt.nodes.new("ShaderNodeTexImage")
        self.tex.image = img
        self.nt.nodes.active = self.tex

    def restore(self):
        self.nt.nodes.remove(self.tex)


def new_img(name, res, colorspace, is_float=False):
    old = bpy.data.images.get(name)
    if old:
        bpy.data.images.remove(old)
    w, h = (res, res) if isinstance(res, int) else res
    img = bpy.data.images.new(name, w, h, alpha=False, float_buffer=is_float)
    img.colorspace_settings.name = colorspace
    return img


def save_png(img, path):
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()


def bake_channel(o, mats, channel, res, path):
    cs = {"base": "sRGB", "orm": "Non-Color", "emit": "Linear Rec.709", "normal": "Non-Color"}[channel]
    img = new_img("__bake_" + channel, res, cs, is_float=(channel == "emit"))
    rw = []
    try:
        seen = set()
        for m in mats:
            if m is None or m.name in seen or m.node_tree is None:
                continue
            seen.add(m.name)
            rw.append(TargetOnly(m, img) if channel == "normal" else Rewire(m, channel, img))
        run_bake(o, "NORMAL" if channel == "normal" else "EMIT")
    finally:
        for r in rw:
            r.restore()
    scale = 1.0
    if channel == "emit":
        w, h = (res, res) if isinstance(res, int) else res
        px = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(-1, 4)[:, :3]
        mx = float(np.percentile(px.max(axis=1), 99.95)) if px.size else 0.0
        scale = max(mx, 1e-6)
        out = bpy.data.images.new("__emit_png", w, h, alpha=False)
        out.colorspace_settings.name = "sRGB"
        q = np.ones((w * h, 4), np.float32)
        q[:, :3] = np.clip(px / scale, 0, 1)
        out.pixels.foreach_set(q.ravel())
        save_png(out, path)
        bpy.data.images.remove(out)
    else:
        save_png(img, path)
    bpy.data.images.remove(img)
    return scale


def uv_stats(me, name):
    """UV coords of a layer and the fraction of the 0..1 square its triangles cover."""
    uvl = me.uv_layers[name]
    uv = np.empty(len(me.loops) * 2, np.float32)
    uvl.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    me.calc_loop_triangles()
    lt = np.empty(len(me.loop_triangles) * 3, np.int32)
    me.loop_triangles.foreach_get("loops", lt)
    t = uv[lt.reshape(-1, 3)]
    a = 0.5 * np.abs((t[:, 1, 0] - t[:, 0, 0]) * (t[:, 2, 1] - t[:, 0, 1]) - (t[:, 2, 0] - t[:, 0, 0]) * (t[:, 1, 1] - t[:, 0, 1]))
    return uv, float(a.sum())


def uv_world_scale(o, me, uv):
    """Area-weighted mean world length (m) of one UV unit along u and along v (per-loop uv array, n x 2)."""
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3) @ np.array(o.matrix_world.to_3x3()).T
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    if nt == 0:
        return 0.0, 0.0
    vt = np.empty(nt * 3, np.int32)
    lt = np.empty(nt * 3, np.int32)
    me.loop_triangles.foreach_get("vertices", vt)
    me.loop_triangles.foreach_get("loops", lt)
    P = co[vt.reshape(-1, 3)].astype(np.float64)
    T = uv[lt.reshape(-1, 3)].astype(np.float64)
    e1, e2 = P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]
    d1, d2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    ok = np.abs(det) > 1e-12
    if not ok.any():
        return 0.0, 0.0
    e1, e2, d1, d2, det = e1[ok], e2[ok], d1[ok], d2[ok], det[ok][:, None]
    dpdu = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) / det
    dpdv = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) / det
    w = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
    if w.sum() <= 0:
        return 0.0, 0.0
    return float((np.linalg.norm(dpdu, axis=1) * w).sum() / w.sum()), float((np.linalg.norm(dpdv, axis=1) * w).sum() / w.sum())


def ensure_bake_uv(o, me_owner):
    """Pick the UV to bake into: a good existing atlas (square texture), or a fresh smart-projected 'bake' layer
    whose islands are stretched to fill 0..1 so long thin parts get a non-square texture instead of a mostly
    empty square one. Returns (uv name, kept, aspect w/h, uv coverage)."""
    me = me_owner.data
    if "bake" in me.uv_layers:
        me.uv_layers.active = me.uv_layers["bake"]
        return "bake", False, me_owner.get("_bake_aspect", 1.0), me_owner.get("_bake_cov", 0.5)
    me.calc_loop_triangles()
    if uv_ok(me):
        ar = render_uv(me)
        me.uv_layers.active = ar
        return ar.name, True, 1.0, max(uv_stats(me, ar.name)[1], 0.05)
    ar = render_uv(me)
    uvl = me.uv_layers.new(name="bake")
    if ar is not None:
        ar.active_render = True  # keep materials reading their original UVs
    me.uv_layers.active = uvl
    vl = bpy.context.view_layer
    for x in vl.objects:
        if x.select_get():
            x.select_set(False)
    vl.objects.active = me_owner
    me_owner.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.003, scale_to_bounds=False)
    try:
        bpy.ops.uv.select_all(action="SELECT")
        bpy.ops.uv.pack_islands(rotate=True, margin=0.003, shape_method="AABB", scale=True)
    except Exception as ex:  # noqa: BLE001
        log("pack_islands failed", me_owner.name, ex)
    bpy.ops.object.mode_set(mode="OBJECT")
    me_owner.select_set(False)
    uv, _ = uv_stats(me, "bake")
    lo, hi = uv.min(axis=0), uv.max(axis=0)
    span = np.maximum(hi - lo, 1e-6)
    aspect = float(span[0] / span[1])
    uv = (uv - lo) / span * 0.99 + 0.005
    me.uv_layers["bake"].data.foreach_set("uv", uv.astype(np.float32).ravel())  # re-fetch: edit-mode toggles free the old layer pointer
    # smart_project unwraps in object-local space, so a non-uniformly scaled object (a unit plane scaled to a 4.2 x 2.1 m
    # display) gets islands whose UV proportions are not its world proportions, and the span ratio above was 1:16 for a
    # 2:1 quad (512 x 4096 texture: 1/4 the texels across the short side). Pick W:H from the world-space length of one
    # UV unit along u and v instead, so texels come out square on the real surface.
    su, sv = uv_world_scale(me_owner, me, uv)
    if su > 0 and sv > 0:
        aspect = su / sv
    _, cov = uv_stats(me, "bake")
    me_owner["_bake_aspect"], me_owner["_bake_cov"] = aspect, cov
    return "bake", False, aspect, max(cov, 0.05)


def bake_size(area, cov, aspect, kept):
    """Texture W,H so texel density is ~DENSITY px/m over the real surface; power of two, clamped."""
    d = DENSITY if area < 2 else DENSITY / 2 if area < 50 else DENSITY / 4  # big architecture: coarser texels
    px = d * d * area / cov
    lo = 1024 if kept else 32
    w = pow2(math.sqrt(px * aspect), lo, MAX_RES)
    h = pow2(math.sqrt(px / aspect), lo, MAX_RES)
    if kept:
        w = h = min(max(w, h), 2048)  # generated props: their own atlas, 1-2K
    return w, h


# ------------------------------------------------------------------ bake cache (content hashes)

# Any edit to this file changes every hash: a cached bake is only reused by the exact code that made it.
CODE_SIG = hashlib.sha256(open(__file__, "rb").read()).hexdigest()[:16] if "__file__" in globals() else "nofile"
_UI_PROPS = {"rna_type", "name", "label", "location", "location_absolute", "width", "width_hidden", "height",
             "dimensions", "select", "show_options", "show_preview", "show_texture", "hide", "use_custom_color",
             "color", "parent", "inputs", "outputs", "internal_links", "warning_propagation", "color_tag"}
_SIGS = {}


def _val(v, depth=0):
    """A deterministic, address-free description of an RNA value (node property or socket default)."""
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, bpy.types.Image):
        return ("image", image_sig(v))
    if isinstance(v, bpy.types.NodeTree):
        return ("tree", tree_sig(v))
    if isinstance(v, bpy.types.ColorRamp):
        return ("ramp", v.color_mode, v.interpolation, v.hue_interpolation,
                [(round(e.position, 6), _val(tuple(e.color))) for e in v.elements])
    if isinstance(v, bpy.types.CurveMapping):
        return ("curves", _val(tuple(v.black_level)), _val(tuple(v.white_level)), v.extend,
                [[(_val(tuple(p.location)), p.handle_type) for p in c.points] for c in v.curves])
    if isinstance(v, bpy.types.ID):
        return ("id", type(v).__name__, v.name)
    if isinstance(v, bpy.types.bpy_struct):
        return ("struct", struct_sig(v, depth + 1)) if depth < 3 else ("struct", type(v).__name__)
    try:
        return tuple(_val(x, depth) for x in v)
    except TypeError:
        return type(v).__name__


def struct_sig(st, depth=0):
    out = []
    for p in st.bl_rna.properties:
        k = p.identifier
        if k in _UI_PROPS or k.startswith("bl_") or p.type == "COLLECTION":
            continue
        try:
            out.append((k, _val(getattr(st, k), depth)))
        except Exception:  # noqa: BLE001  (write-only / context-dependent properties)
            pass
    return out


def image_sig(img):
    key = ("img", img.as_pointer())
    if key not in _SIGS:
        h = hashlib.sha256(repr((img.source, tuple(img.size), img.colorspace_settings.name, img.alpha_mode)).encode())
        if img.packed_file:
            h.update(img.packed_file.data)
        elif img.source == "FILE" and os.path.exists(bpy.path.abspath(img.filepath)):
            with open(bpy.path.abspath(img.filepath), "rb") as f:
                h.update(f.read())
        elif img.source == "GENERATED":
            h.update(repr((img.generated_type, img.generated_width, img.generated_height,
                           _val(tuple(img.generated_color)))).encode())
        else:
            h.update(img.filepath.encode())
        _SIGS[key] = h.hexdigest()[:24]
    return _SIGS[key]


def tree_sig(nt):
    key = ("tree", nt.as_pointer())  # embedded material trees all share one name
    if key not in _SIGS:
        _SIGS[key] = "cycle"  # a group that (somehow) contains itself
        nodes = []
        for n in sorted(nt.nodes, key=lambda n: n.name):
            ins = [(i.identifier, i.is_linked, None if i.is_linked or not hasattr(i, "default_value") else _val(i.default_value))
                   for i in n.inputs]
            nodes.append((n.bl_idname, n.name, struct_sig(n), ins))
        links = sorted((l.from_node.name, l.from_socket.identifier, l.to_node.name, l.to_socket.identifier, l.is_muted)
                       for l in nt.links)
        _SIGS[key] = hashlib.sha256(repr((nodes, links)).encode()).hexdigest()[:24]
    return _SIGS[key]


def material_sig(m):
    if m is None:
        return None
    if m.node_tree is None:
        return ("plain", _val(tuple(m.diffuse_color)), round(m.roughness, 6), round(m.metallic, 6))
    return tree_sig(m.node_tree)


_ATTR = {"FLOAT": (1, np.float32, "value"), "INT": (1, np.int32, "value"), "FLOAT_VECTOR": (3, np.float32, "vector"),
         "FLOAT_COLOR": (4, np.float32, "color"), "BYTE_COLOR": (4, np.float32, "color"), "BOOLEAN": (1, bool, "value"),
         "FLOAT2": (2, np.float32, "vector"), "INT8": (1, np.int32, "value"), "INT32_2D": (2, np.int32, "value"),
         "QUATERNION": (4, np.float32, "value")}


def mesh_sig(me):
    """Hash of the (evaluated) mesh: topology, every attribute (positions, UVs, colours, materials, sharpness) and the
    corner normals the tangent-space normal bake and the GLB normals come from."""
    h = hashlib.sha256()
    a = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get("loop_start", a)
    h.update(a.tobytes())
    for at in sorted(me.attributes, key=lambda x: x.name):
        h.update(repr((at.name, at.domain, at.data_type, len(at.data))).encode())
        spec = _ATTR.get(at.data_type)
        if spec is None:
            continue
        k, dt, prop = spec
        buf = np.empty(len(at.data) * k, dt)
        try:
            at.data.foreach_get(prop, buf)
        except Exception:  # noqa: BLE001
            buf = np.array([getattr(d, prop) for d in at.data], dtype=dt)
        h.update(buf.tobytes())
    for l in me.uv_layers:
        h.update(repr((l.name, l.active, l.active_render)).encode())
    try:
        cn = np.empty(len(me.loops) * 3, np.float32)
        me.corner_normals.foreach_get("vector", cn)
        h.update(np.round(cn, 5).tobytes())
    except Exception:  # noqa: BLE001
        pass
    return h.hexdigest()


def asset_hash(rep, ev, mats):
    """Content key of one exported asset (GLB + texture set + meta): evaluated mesh, materials, world-space scale
    (texel density), bake settings, Blender version and this exporter. Materials that read the object they sit on
    (Object Info, object coordinates, object attributes, ...) also key on that representative object."""
    h = hashlib.sha256(repr((CODE_SIG, bpy.app.version_string, DENSITY, MAX_RES, FRAME)).encode())
    h.update(mesh_sig(ev).encode())
    h.update(repr([material_sig(m) for m in mats]).encode())
    h.update(repr([round(x, 5) for r in rep.matrix_world.to_3x3() for x in r]).encode())
    if any(uses_object_dependence(m) for m in mats if m):
        h.update(repr((rep.name, [round(x, 5) for r in rep.matrix_world for x in r], object_attr_values(rep),
                       _val(tuple(rep.color)), rep.pass_index)).encode())
    return h.hexdigest()[:32]


def cache_dir(h):
    return os.path.join(CACHE, h[:2], h)


def _cache_files(an):
    """Cache file name -> path in --out for asset `an`."""
    files = {"mesh.glb": os.path.join(OUT, "mesh", an + ".glb"), "meta.json": os.path.join(OUT, "mesh", an + ".json"),
             "emit.png.json": os.path.join(OUT, "tex", f"{an}_emit.png.json")}
    for c in ("base", "orm", "normal", "emit"):
        files[c + ".png"] = os.path.join(OUT, "tex", f"{an}_{c}.png")
    return files


def cache_fetch(h, an):
    d = cache_dir(h)
    if not os.path.exists(os.path.join(d, "ready")):
        return False
    for name, dst in _cache_files(an).items():
        src = os.path.join(d, name)
        if not os.path.exists(src):
            continue
        if os.path.lexists(dst):
            os.remove(dst)
        if LINK_CACHE:
            os.symlink(src, dst)
        else:
            shutil.copyfile(src, dst)
    return True


def cache_store(h, an):
    """Copy a finished asset into the cache: written to a temp dir, then renamed into place (concurrent writers race
    harmlessly; the first rename wins)."""
    d = cache_dir(h)
    if os.path.exists(os.path.join(d, "ready")):
        return
    tmp = f"{d}.tmp{os.getpid()}"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    for name, src in _cache_files(an).items():
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(tmp, name))
    open(os.path.join(tmp, "ready"), "w").write(an)
    try:
        os.rename(tmp, d)
    except OSError:
        shutil.rmtree(tmp, ignore_errors=True)
        if not os.path.exists(os.path.join(d, "ready")):
            raise


# ------------------------------------------------------------------ export

def to_mesh_object(o):
    """Text/curve objects -> real mesh objects (evaluated) in a scratch collection; originals hidden."""
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    n = bpy.data.objects.new(o.name + "__mesh", me)
    c = bpy.data.collections.get("__converted") or bpy.data.collections.new("__converted")
    if c.name not in sc.collection.children:
        sc.collection.children.link(c)
    c.objects.link(n)
    n.matrix_world = o.matrix_world.copy()
    for k in ("visible_shadow", "visible_camera", "visible_glossy", "visible_diffuse"):
        setattr(n, k, getattr(o, k))
    o.hide_render = True
    return n


def export_glb(o, uv_name, glass_slots, path):
    """Evaluated mesh at identity with only the bake UV; slots: 0 = baked, 1+ = each glass material."""
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    for l in [l for l in me.uv_layers if l.name != uv_name]:
        me.uv_layers.remove(l)
    if len(me.uv_layers):
        me.uv_layers[0].name = "UVMap"
    gl = list(glass_slots)
    mi = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get("material_index", mi)
    remap = np.zeros(max(len(o.material_slots), 1), np.int32)
    for i in range(len(o.material_slots)):
        remap[i] = gl.index(i) + 1 if i in gl else 0
    mi = remap[np.clip(mi, 0, len(remap) - 1)]
    me.polygons.foreach_set("material_index", mi)
    me.materials.clear()
    base = bpy.data.materials.get("BAKED") or bpy.data.materials.new("BAKED")
    me.materials.append(base)
    for k, gi in enumerate(gl):
        gm = bpy.data.materials.get(f"GLASS_{k}") or bpy.data.materials.new(f"GLASS_{k}")
        me.materials.append(gm)
    tmp = bpy.data.objects.new("__export", me)
    sc.collection.objects.link(tmp)
    vl = bpy.context.view_layer
    for x in vl.objects:
        if x.select_get():
            x.select_set(False)
    tmp.select_set(True)
    vl.objects.active = tmp
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True,
                              export_materials="PLACEHOLDER", export_texcoords=True, export_normals=True,
                              export_tangents=True, export_yup=True, export_animations=False,
                              export_cameras=False, export_lights=False, export_extras=False)
    bpy.data.objects.remove(tmp)
    bpy.data.meshes.remove(me)


# ------------------------------------------------------------------ volumes

def sample_volume(o, n=24, levels=(0.08, 0.3, 0.55, 0.8)):
    """Bake density / emission of a procedural volume on horizontal slices that share the box's object space and
    texture space (so Generated/Object coordinates match). Returns per-level mean density and emission."""
    m = next((m for m in o.data.materials if m and is_volume_only(m)), None)
    if m is None:
        return None
    pv = next((nd for nd in m.node_tree.nodes if nd.type == "PRINCIPLED_VOLUME"), None)
    if pv is None:
        return None
    me0 = o.data
    xs = [v.co.x for v in me0.vertices]
    ys = [v.co.y for v in me0.vertices]
    zs = [v.co.z for v in me0.vertices]
    lo, hi = Vector((min(xs), min(ys), min(zs))), Vector((max(xs), max(ys), max(zs)))
    res = {"levels": [], "density": [], "emission": [], "emission_color": None}
    for f in levels:
        z = lo.z + f * (hi.z - lo.z)
        me = bpy.data.meshes.new("__slice")
        me.from_pydata([(lo.x, lo.y, z), (hi.x, lo.y, z), (hi.x, hi.y, z), (lo.x, hi.y, z)], [], [(0, 1, 2, 3)])
        uv = me.uv_layers.new(name="UVMap")
        for i, c in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
            uv.data[i].uv = c
        me.use_auto_texspace = False
        me.texspace_location = me0.texspace_location
        me.texspace_size = me0.texspace_size
        sl = bpy.data.objects.new("__slice", me)
        sc.collection.objects.link(sl)
        sl.matrix_world = o.matrix_world.copy()
        mc = m.copy()
        me.materials.append(mc)
        nt = mc.node_tree
        pvc = next(nd for nd in nt.nodes if nd.type == "PRINCIPLED_VOLUME")
        out = output_node(nt)
        for l in list(out.inputs["Volume"].links):
            nt.links.remove(l)
        vals = {}
        for key, sock in (("density", "Density"), ("emission", "Emission Strength")):
            em = nt.nodes.new("ShaderNodeEmission")
            s = pvc.inputs[sock]
            if s.is_linked:
                nt.links.new(_src(s), em.inputs["Color"])
            else:
                em.inputs["Color"].default_value = (s.default_value,) * 3 + (1,)
            nt.links.new(em.outputs[0], out.inputs["Surface"])
            img = new_img("__vol", n, "Non-Color", is_float=True)
            tx = nt.nodes.new("ShaderNodeTexImage")
            tx.image = img
            nt.nodes.active = tx
            bs = bake_scene()
            bs.collection.objects.link(sl)
            try:
                run_bake(sl, "EMIT")
            finally:
                bs.collection.objects.unlink(sl)
            px = np.empty(n * n * 4, np.float32)
            img.pixels.foreach_get(px)
            vals[key] = float(px.reshape(-1, 4)[:, 0].mean())
            nt.nodes.remove(tx)
            nt.nodes.remove(em)
            bpy.data.images.remove(img)
        res["levels"].append(f)
        res["density"].append(vals["density"])
        res["emission"].append(vals["emission"])
        bpy.data.objects.remove(sl)
        bpy.data.meshes.remove(me)
        bpy.data.materials.remove(mc)
    c = pv.inputs["Color"].default_value
    res["albedo"] = [c[0], c[1], c[2]]
    res["anisotropy"] = pv.inputs["Anisotropy"].default_value
    ec = pv.inputs["Emission Color"]
    if ec.is_linked:
        # Sample the colour ramp if it is one (flame): mid-height colour as a representative.
        n0 = ec.links[0].from_node
        if n0.type == "VALTORGB":
            res["emission_color"] = list(n0.color_ramp.evaluate(0.6))[:3]
    else:
        res["emission_color"] = list(ec.default_value)[:3]
    mw = o.matrix_world
    corners = [mw @ Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    wlo = Vector([min(c[i] for c in corners) for i in range(3)])
    whi = Vector([max(c[i] for c in corners) for i in range(3)])
    res["bounds_ue"] = {"center": ue_vec((wlo + whi) / 2), "extent": [(whi.x - wlo.x) * 50, (whi.y - wlo.y) * 50, (whi.z - wlo.z) * 50]}
    res["bounds_m"] = {"lo": list(wlo), "hi": list(whi)}
    res["material"] = m.name
    res["animated"] = animated(m)
    return res


# ------------------------------------------------------------------ lights / cameras / world / grade

def light_entry(o):
    L = o.data
    col = Vector(L.color[:3])
    mx = max(col) or 1.0
    P = L.energy
    e = {"name": o.name, "type": L.type, "color": [c / mx for c in col], "energy_w": P,
         "cast_shadows": bool(getattr(L, "use_shadow", True)),
         "specular": 1.0 if getattr(o, "visible_glossy", True) else 0.0,
         "diffuse": 1.0 if getattr(o, "visible_diffuse", True) else 0.0,
         "volume": 1.0 if getattr(o, "visible_volume_scatter", True) else 0.0,
         "loc": ue_vec(o.matrix_world.translation), "animated": bool(L.animation_data and (L.animation_data.drivers or L.animation_data.action))}
    f, u = ue_axes(o.matrix_world)
    e["forward"], e["up"] = f, u
    k = mx  # colour normalisation folds into intensity
    if L.type in ("POINT", "SPOT"):
        e["candela"] = LM_PER_W * P * k / (4 * math.pi)
        e["source_radius"] = L.shadow_soft_size * 100
        e["soft_falloff"] = bool(getattr(L, "use_soft_falloff", True))
        if L.type == "SPOT":
            outer = math.degrees(L.spot_size) / 2
            e["outer_cone"] = min(outer, 80.0)
            e["inner_cone"] = outer * (1 - L.spot_blend)
            if outer > 80:
                e["note"] = f"spot cone {outer * 2:.0f} deg > Unreal max 160: clamped"
    elif L.type == "AREA":
        e["candela"] = LM_PER_W * P * k / math.pi
        e["shape"] = L.shape
        sx = L.size
        sy = L.size_y if L.shape in ("RECTANGLE", "ELLIPSE") else L.size
        sxx, syy, _ = o.matrix_world.to_scale()
        e["width"], e["height"] = sx * sxx * 100, sy * syy * 100
        e["spread_deg"] = math.degrees(getattr(L, "spread", math.pi))
    elif L.type == "SUN":
        e["lux"] = LM_PER_W * P * k
        e["angle_deg"] = math.degrees(L.angle)
    # IES / gobo: node-based light textures.
    if L.use_nodes and L.node_tree:
        for nd in L.node_tree.nodes:
            if nd.type == "TEX_IES":
                e["ies"] = bpy.path.abspath(nd.filepath) if nd.mode == "EXTERNAL" else "internal:" + (nd.ies.name if nd.ies else "")
            if nd.type == "TEX_IMAGE" and nd.image:
                e["gobo"] = bpy.path.abspath(nd.image.filepath)
    att = math.sqrt(max(e.get("candela", 0), 1) / 3.0) * 100
    e["attenuation_radius"] = max(300.0, min(att, 8000.0))
    return e


def camera_entry(o):
    c = o.data
    f, u = ue_axes(o.matrix_world)
    rx, ry = sc.render.resolution_x, sc.render.resolution_y
    sw = c.sensor_width if c.sensor_fit in ("AUTO", "HORIZONTAL") else c.sensor_height * rx / ry
    d = {"name": o.name, "type": c.type, "lens_mm": c.lens, "sensor_width_mm": sw, "sensor_height_mm": sw * ry / rx,
         "sensor_fit": c.sensor_fit, "shift": [c.shift_x, c.shift_y], "clip": [c.clip_start * 100, c.clip_end * 100],
         "loc": ue_vec(o.matrix_world.translation), "forward": f, "up": u,
         "dof": {"enabled": c.dof.use_dof, "focus_cm": c.dof.focus_distance * 100, "fstop": c.dof.aperture_fstop,
                 "blades": c.dof.aperture_blades, "focus_object": c.dof.focus_object.name if c.dof.focus_object else None}}
    if o.name in DOF:
        fd, fs = DOF[o.name]
        d["dof"].update(enabled=True, focus_cm=fd * 100, fstop=fs, source="--dof override (stills script)")
    return d


def world_bake(path, w=2048, h=1024, spp=32):
    ws = bpy.data.scenes.new("__world")
    ws.world = sc.world
    ws.render.engine = "CYCLES"
    ws.cycles.device = "CPU"
    ws.cycles.samples = spp
    ws.render.resolution_x, ws.render.resolution_y, ws.render.resolution_percentage = w, h, 100
    ws.view_settings.view_transform = "Standard"
    ws.render.image_settings.file_format = "OPEN_EXR"
    ws.render.image_settings.color_depth = "16"
    cd = bpy.data.cameras.new("__pano")
    cd.type = "PANO"
    try:
        cd.panorama_type = "EQUIRECTANGULAR"
    except Exception:
        cd.cycles.panorama_type = "EQUIRECTANGULAR"
    co = bpy.data.objects.new("__pano", cd)
    ws.collection.objects.link(co)
    co.rotation_euler = (math.radians(90), 0, math.radians(-90))  # looking +X? (equirect centre = -Y in Blender -> fixed below)
    co.rotation_euler = (math.radians(90), 0, 0)
    ws.camera = co
    ws.render.filepath = path
    with bpy.context.temp_override(scene=ws):
        bpy.ops.render.render(write_still=True, scene=ws.name)
    # mean radiance for the sky light estimate
    img = bpy.data.images.load(path)
    px = np.empty(img.size[0] * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(-1, 4)[:, :3]
    mean = px.mean(axis=0).tolist()
    bpy.data.images.remove(img)
    return {"equirect_exr": path, "mean_radiance": mean, "camera_note": "equirect centre looks along Blender +Y"}


def compositor_nodes():
    # 5.0: compositing_node_group; Scene.node_tree is gone (use_nodes can still read True with no tree).
    tree = getattr(sc, "compositing_node_group", None) or getattr(sc, "node_tree", None)
    if tree is None:
        return []
    out = []
    for n in tree.nodes:
        d = {"type": n.bl_idname, "name": n.name, "inputs": {}}
        for i in n.inputs:
            if i.is_linked or not hasattr(i, "default_value"):
                continue
            v = i.default_value
            try:
                v = v if isinstance(v, str) else list(v)
            except TypeError:
                pass
            if isinstance(v, (int, float, str, list, bool)):
                d["inputs"][i.name] = v
        for k in ("glare_type", "quality", "blend_type"):
            if hasattr(n, k):
                d[k] = getattr(n, k)
        out.append(d)
    return out


def ffmpeg_grade(grade_sh):
    """Pull GRADE="..." out of a scene's grade.sh; split into colour (LUT-able) and spatial filters."""
    txt = open(grade_sh, encoding="utf-8").read()
    m = re.search(r'GRADE="([^"]+)"', txt)
    if not m:
        return None
    filters = [f for f in m.group(1).split(",") if f]
    colour = [f for f in filters if f.split("=")[0] in ("curves", "hue", "eq", "colorbalance", "colorchannelmixer", "lutrgb", "colortemperature")]
    spatial = [f for f in filters if f not in colour]
    g = {"source": grade_sh, "filter": m.group(1), "colour": colour, "spatial": spatial}
    for f in spatial:
        if f.startswith("vignette"):
            a = re.search(r"angle=PI/([\d.]+)", f)
            g["vignette_angle_rad"] = math.pi / float(a.group(1)) if a else math.pi / 5
        if f.startswith("rgbashift"):
            g["chromatic_px"] = 1
    noise = re.search(r"noise=alls=(\d+)", txt)
    if noise:
        g["grain_strength"] = int(noise.group(1))
    return g


def make_lut(colour_filters, path):
    """UE colour grading LUT (256x16, 16 slices of 16x16; R across a slice, G down, B by slice), with the ffmpeg
    colour filters applied. Unreal applies it after the tone curve, i.e. in display space, like ffmpeg on the PNG."""
    n = 16
    ident = os.path.join(os.path.dirname(path), "lut_identity.png")
    img = bpy.data.images.new("__lut", n * n, n, alpha=False)
    img.colorspace_settings.name = "Non-Color"
    px = np.zeros((n, n * n, 4), np.float32)
    for b in range(n):
        for g in range(n):
            for r in range(n):
                px[g, b * n + r] = (r / (n - 1), g / (n - 1), b / (n - 1), 1)
    # Blender rows go bottom-up; UE LUT row 0 (top) is G=0.
    img.pixels.foreach_set(px[::-1].ravel())
    save_png(img, ident)
    bpy.data.images.remove(img)
    if not colour_filters:
        return ident
    cmd = [FFMPEG, "-v", "error", "-y", "-i", ident, "-vf", ",".join(colour_filters), "-frames:v", "1", path]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as ex:
        log("LUT ffmpeg not runnable (pass --ffmpeg or set FFMPEG):", FFMPEG, ex)
        return ident
    if r.returncode != 0:
        log("LUT ffmpeg failed:", r.stderr[:300])
        return ident
    return path


# ------------------------------------------------------------------ main

def write_plan(keys, assets, names, report, n_objs, t0):
    """Plan pass: every asset's name, content hash and estimated bake cost (pixels x channels), for sharding."""
    dg = bpy.context.evaluated_depsgraph_get()
    rows = []
    for k in keys:
        rep = assets[k][0]
        mats = [s.material for s in rep.material_slots]
        bake_mats = [m for m in mats if m and not is_glass(m)]
        ev = rep.evaluated_get(dg).data
        area = surface_area(rep, ev)
        d = DENSITY if area < 2 else DENSITY / 2 if area < 50 else DENSITY / 4
        px = min(d * d * area / 0.6, MAX_RES * MAX_RES) if bake_mats else 0
        nch = (2 + any(perturbs_normal(m) for m in bake_mats) + any(emissive(m) for m in bake_mats)) if bake_mats else 0
        rows.append({"key": k, "asset": names[k], "hash": asset_hash(rep, ev, mats), "tris": tri_count(ev),
                     "area_m2": round(area, 3), "est_px": int(px * nch), "channels": nch, "instances": len(assets[k]),
                     "object_dependent": sorted({x for m in bake_mats for x in uses_object_dependence(m)})})
    plan = {"source": SRC, "frame": FRAME, "density": DENSITY, "max_res": MAX_RES, "code": CODE_SIG,
            "blender": bpy.app.version_string, "objects": n_objs, "assets": rows,
            "placements": sum(r["instances"] for r in rows), "volumes": sorted(report["volumes"]),
            "skipped": report["skipped"], "converted": report["converted"], "plan_s": round(time.time() - t0, 1)}
    json.dump(plan, open(PLAN_OUT, "w", encoding="utf-8"), indent=1)
    log(f"plan written {PLAN_OUT}: {len(rows)} assets, {plan['placements']} placements, "
        f"{sum(r['est_px'] for r in rows) / 1e6:.0f} Mpx to bake, in {plan['plan_s']}s")


def main():
    t0 = time.time()
    srcs, emitters = particle_instancers()
    report = {"skipped": [], "converted": [], "volumes": {}, "fx": [], "warnings": []}
    objs = []
    for o in list(sc.objects):
        if o.hide_render or not o.visible_get():
            if o.type in ("MESH", "FONT", "CURVE") and not o.hide_render:
                pass
            if o.hide_render:
                continue
        if o.name in srcs:
            report["skipped"].append([o.name, "particle instance source (exported as fx note)"])
            continue
        if o.name in emitters:
            st = [md.particle_system.settings for md in o.modifiers if md.type == "PARTICLE_SYSTEM"]
            report["fx"].append({"name": o.name, "kind": "particles", "count": sum(s.count for s in st),
                                 "instance": [s.instance_object.name if s.instance_object else None for s in st],
                                 "lifetime": [s.lifetime for s in st], "velocity": [list(s.object_align_factor) for s in st]})
            if not o.show_instancer_for_render:
                continue
        if o.type in ("FONT", "CURVE", "SURFACE", "META"):
            if o.type == "CURVE" and o.data.bevel_depth == 0 and not o.data.bevel_object and o.data.extrude == 0:
                report["skipped"].append([o.name, "curve without geometry"])
                continue
            n = to_mesh_object(o)
            report["converted"].append([o.name, o.type])
            objs.append(n)
        elif o.type == "MESH":
            mats = [s.material for s in o.material_slots]
            if mats and all(is_volume_only(m) for m in mats if m):
                if PLAN_OUT or KEYS:  # sampled by the merge pass only
                    report["volumes"][o.name] = None
                    continue
                v = sample_volume(o)
                if v:
                    report["volumes"][o.name] = v
                    log("volume", o.name, [round(x, 4) for x in v["density"]], [round(x, 2) for x in v["emission"]])
                continue
            objs.append(o)
    # Group by unique mesh.
    assets = {}
    for o in objs:
        k = mesh_key(o)
        assets.setdefault(k, []).append(o)
    keys = sorted(assets, key=lambda k: assets[k][0].name, reverse=REVERSE)
    if ONLY:
        keys = [k for k in keys if any(o.name in ONLY or o.name.split("__")[0] in ONLY for o in assets[k])]
    if LIMIT:
        keys = keys[:LIMIT]
    # Asset names over the whole key list (the same in every shard), or the plan's.
    names, used = {}, set()
    for ai, k in enumerate(keys):
        rep = assets[k][0]
        an = safe(rep.data.name if k.startswith("m_") else rep.name)
        an = f"{an}_{ai:03d}" if an in used else an
        used.add(an)
        names[k] = an
    if KEYS:
        want = set(json.load(open(KEYS, encoding="utf-8")))
        keys = [k for k in keys if k in want]
    hashes = {}
    if PLAN:
        plan = json.load(open(PLAN, encoding="utf-8"))
        for row in plan["assets"]:
            if row["key"] in names:
                names[row["key"]], hashes[row["key"]] = row["asset"], row["hash"]
        missing = [k for k in keys if k not in hashes]
        if missing:
            log(f"WARNING {len(missing)} asset keys are not in the plan (hashed here): {missing[:5]}")
    if PLAN_OUT:
        write_plan(keys, assets, names, report, len(objs), t0)
        return
    log(f"{len(objs)} mesh objects -> {len(assets)} unique meshes; exporting {len(keys)}")
    entries, placements, shard = [], [], []
    for ai, k in enumerate(keys):
        group = assets[k]
        rep = group[0]
        an = names[k]
        mats = [s.material for s in rep.material_slots]
        glass = [i for i, m in enumerate(mats) if m and is_glass(m)]
        bake_mats = [m for i, m in enumerate(mats) if i not in glass]
        dg = bpy.context.evaluated_depsgraph_get()
        ev = rep.evaluated_get(dg).data
        tris = tri_count(ev)
        area = surface_area(rep, ev)
        # Material sections the GLB really has, in order (0 = baked, k+1 = glass k). glTF drops unused materials, so an
        # all-glass pane has one section, the glass one; build_level used to give it the baked (opaque) material.
        mi_ = np.empty(len(ev.polygons), np.int32)
        ev.polygons.foreach_get("material_index", mi_)
        sect = sorted({(glass.index(int(i)) + 1) if int(i) in glass else 0 for i in np.unique(mi_)}) if len(mi_) else [0]
        texd = os.path.join(OUT, "tex")
        p = {c: os.path.join(texd, f"{an}_{c}.png") for c in ("base", "orm", "normal", "emit")}
        glb = os.path.join(OUT, "mesh", an + ".glb")
        meta = glb[:-4] + ".json"
        done = os.path.exists(glb)  # written after every bake of the asset succeeded
        h = (hashes.get(k) or asset_hash(rep, ev, mats)) if CACHE else None
        cached = bool(h) and not done and cache_fetch(h, an)
        done = done or cached
        if done:
            # Resume: skip the UV unwrap (an edit-mode smart_project per asset). Blender 5.0.1's bake crashes
            # (OpenImageIO ustring::operator= in ccl::create_mesh) after a few hundred unwrap+bake cycles in one
            # process; re-unwrapping every finished asset on resume made it crash at the same asset every time.
            m0 = json.load(open(meta)) if os.path.exists(meta) else {}
            uv_name, kept, cov, res = None, m0.get("uv") == "kept", m0.get("uv_coverage", 0.0), m0.get("res", [0, 0])
        else:
            uv_name, kept, aspect, cov = ensure_bake_uv(rep, rep)
            res = bake_size(area, cov, aspect, kept)
        e = {"asset": an, "key": k, "tris": tris, "area_m2": round(area, 3), "uv": "kept" if kept else "smart_project",
             "res": list(res), "uv_coverage": round(cov, 3), "slots": [m.name if m else None for m in mats], "glass": [glass_params(mats[i]) for i in glass],
             "emissive": False, "normal": False, "emissive_scale": 0.0, "object_dependent": sorted({h for m in bake_mats if m for h in uses_object_dependence(m)}),
             "animated_materials": [m.name for m in bake_mats if m and animated(m)], "instances": len(group),
             "shadow": bool(rep.visible_shadow), "camera_visible": bool(rep.visible_camera), "sections": sect}
        t1 = time.time()
        if bake_mats and not NO_BAKE:
            if not done:  # a crash between channels leaves base without orm: redo the whole set
                bake_scene().collection.objects.link(rep)
                try:
                    bake_channel(rep, bake_mats, "base", res, p["base"])
                    bake_channel(rep, bake_mats, "orm", res, p["orm"])
                    if any(m and perturbs_normal(m) for m in bake_mats):
                        bake_channel(rep, bake_mats, "normal", res, p["normal"])
                    if any(m and emissive(m) for m in bake_mats):
                        s = bake_channel(rep, bake_mats, "emit", res, p["emit"])
                        json.dump({"scale": s}, open(p["emit"] + ".json", "w"))
                finally:
                    bake_scene().collection.objects.unlink(rep)
        e["normal"] = os.path.exists(p["normal"])
        e["emissive"] = os.path.exists(p["emit"])
        if e["emissive"]:
            e["emissive_scale"] = json.load(open(p["emit"] + ".json"))["scale"]
        e["tex"] = {c: os.path.relpath(v, OUT) for c, v in p.items() if os.path.exists(v)}
        if not os.path.exists(glb):
            export_glb(rep, uv_name, glass, glb)
        if not done:
            json.dump({"res": list(res), "uv": e["uv"], "uv_coverage": e["uv_coverage"]}, open(meta, "w"))
        e["glb"] = os.path.relpath(glb, OUT)
        # Local bounds in Unreal axes for the importer orientation check.
        bb = [Vector(c) for c in rep.bound_box]
        e["check_bounds"] = {"min": ue_vec(Vector([min(c[i] for c in bb) for i in range(3)])),
                             "max": ue_vec(Vector([max(c[i] for c in bb) for i in range(3)]))}
        e["bake_s"] = round(time.time() - t1, 1)
        if h:
            e["hash"] = h
            if not cached and not (NO_BAKE and bake_mats):  # never cache an unbaked (texture-less) asset
                cache_store(h, an)
        shard.append({"key": k, "asset": an, "hash": h, "cached": cached, "bake_s": e["bake_s"]})
        entries.append(e)
        for o in group:
            placements.append({"name": o.name, "asset": an, **ue_xform(o.matrix_world),
                               "shadow": bool(o.visible_shadow), "camera_visible": bool(o.visible_camera)})
        log(f"[{ai + 1}/{len(keys)}] {an} tris={tris} res={res} uv={e['uv']} inst={len(group)} {e['bake_s']}s"
            + (" (cache)" if cached else ""))
    if KEYS:
        json.dump(shard, open(os.path.join(OUT, f"shard_{os.path.basename(KEYS)}"), "w"), indent=1)
        log(f"shard done: {len(shard)} assets ({sum(r['cached'] for r in shard)} from cache) in {time.time() - t0:.0f}s")
        return
    # Lights, cameras, world, grade.
    lights = [light_entry(o) for o in sc.objects if o.type == "LIGHT" and not o.hide_render]
    cams = [camera_entry(o) for o in sc.objects if o.type == "CAMERA"]
    world = None
    wpath = os.path.join(OUT, "world", "sky.exr")
    if sc.world:
        world = world_bake(wpath) if not os.path.exists(wpath) or "--rebake-world" in argv else {"equirect_exr": wpath}
        if "mean_radiance" not in world:
            img = bpy.data.images.load(wpath)
            px = np.empty(img.size[0] * img.size[1] * 4, np.float32)
            img.pixels.foreach_get(px)
            world["mean_radiance"] = px.reshape(-1, 4)[:, :3].mean(axis=0).tolist()
            bpy.data.images.remove(img)
        world["equirect_exr"] = os.path.relpath(wpath, OUT)
        world["nits_scale"] = LM_PER_W
    vs = sc.view_settings
    grade = {"view_transform": vs.view_transform, "look": vs.look, "exposure": vs.exposure, "gamma": vs.gamma,
             "use_curve_mapping": vs.use_curve_mapping,
             "ev100": math.log2(LM_PER_W / 1.2) - vs.exposure,
             "compositor": compositor_nodes(),
             "motion_blur": {"on": sc.render.use_motion_blur, "shutter": sc.render.motion_blur_shutter},
             "resolution": [sc.render.resolution_x, sc.render.resolution_y], "fps": sc.render.fps}
    if vs.use_curve_mapping:
        grade["curves"] = [[(p.location[0], p.location[1]) for p in c.points] for c in vs.curve_mapping.curves]
    if GRADE_SH and os.path.exists(GRADE_SH):
        g = ffmpeg_grade(GRADE_SH)
        if g:
            g["lut"] = os.path.relpath(make_lut(g["colour"], os.path.join(OUT, "grade", "lut_grade.png")), OUT)
            grade["ffmpeg"] = g
    scene = {"source": SRC, "frame": FRAME, "units": "unreal cm, X fwd, Y right, Z up", "lm_per_w": LM_PER_W,
             "assets": entries, "placements": placements, "lights": lights, "cameras": cams, "world": world,
             "volumes": report["volumes"], "fx": report["fx"], "grade": grade,
             "skipped": report["skipped"], "converted": report["converted"], "export_s": round(time.time() - t0)}
    jp = os.path.join(OUT, "scene.json")
    if os.path.exists(jp) and (ONLY or LIMIT):
        old = json.load(open(jp, encoding="utf-8"))
        have = {e["asset"] for e in entries}
        scene["assets"] = [e for e in old.get("assets", []) if e["asset"] not in have] + entries
        scene["placements"] = [p for p in old.get("placements", []) if p["asset"] not in have] + placements
    json.dump(scene, open(jp, "w", encoding="utf-8"), indent=1)
    log(f"wrote {jp}: {len(scene['assets'])} assets, {len(scene['placements'])} placements, {len(lights)} lights, "
        f"{len(cams)} cameras, {len(report['volumes'])} volumes in {time.time() - t0:.0f}s")


main()
