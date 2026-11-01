"""Motion renders of an AnyKit kit for the kit supercut: a lineup dolly and per-item turntables, in the same studio as
kit/tools/present.py (neutral grey ground, soft key/fill/rim, AgX, scale bar, ground labels).

    blender -b --factory-startup --python builder/blender_gpu.py --python breakdown/kit_motion.py -- \
        --pkg <unzipped package>/out --out <dir> [--only dolly|turn] [--secs 9] [--turn-secs 4]
        [--samples 96] [--turn-samples 48] [--frames a,b,c] [--ids a,b]

Reads <pkg>/kit.json and <pkg>/items/<id>/<id>.glb (normalised: metres, bottom-centre origin, facing -Y).
Writes <out>/dolly/####.png (1920x1080) and <out>/turn/<id>/####.png (960x540: the item sits in the central square,
so a tile can crop it narrower). --frames renders only those frame numbers (1-based), to check a look first.
Does not reset factory settings (that would drop the GPU device chosen by blender_gpu.py).
"""

import json
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
opt = lambda k, d: type(d)(argv[argv.index(k) + 1]) if k in argv else d
PKG = os.path.abspath(opt("--pkg", "out"))
OUT = os.path.abspath(opt("--out", "motion"))
ONLY = opt("--only", "")
SECS = opt("--secs", 9.0)
TSECS = opt("--turn-secs", 4.0)
SAMPLES = opt("--samples", 96)
TSAMPLES = opt("--turn-samples", 48)
FRAMES = [int(s) for s in opt("--frames", "").split(",") if s]
IDS = [s for s in opt("--ids", "").split(",") if s]
FPS = 24

kit = json.load(open(os.path.join(PKG, "kit.json"), encoding="utf-8"))
items = [it for it in kit["items"] if not IDS or it["id"] in IDS]


def setup():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "GPU"
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPTIX"
    sc.cycles.use_adaptive_sampling = True
    sc.render.use_persistent_data = True
    sc.render.fps = FPS
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.image_settings.compression = 30
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.36, 0.37, 0.38, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
    bpy.ops.mesh.primitive_plane_add(size=1)
    g = bpy.context.object
    g.name = "ground"
    g.scale = (2000, 2000, 1)  # far enough that its edge never shows
    gm = bpy.data.materials.new("ground")
    gm.use_nodes = True
    p = gm.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (0.42, 0.42, 0.42, 1)
    p.inputs["Roughness"].default_value = 0.85
    g.data.materials.append(gm)
    return sc


def light(name, loc, target, energy, size):
    d = bpy.data.lights.new(name, "AREA")
    d.energy, d.size = energy, size
    o = bpy.data.objects.new(name, d)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


def studio(centre, radius):
    c, s = Vector(centre), max(radius, 0.2)
    light("key", c + Vector((1.6, -2.2, 2.4)) * s, c, 220 * s * s, 1.6 * s)
    light("fill", c + Vector((-2.6, -1.4, 1.2)) * s, c, 60 * s * s, 2.5 * s)
    light("rim", c + Vector((-0.8, 2.6, 2.2)) * s, c, 140 * s * s, 1.4 * s)


def load(item):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(PKG, "items", item["id"], f"{item['id']}.glb"))
    new = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new(item["id"], None)
    bpy.context.scene.collection.objects.link(root)
    for o in new:
        if o.parent is None:
            o.parent = root
    bpy.context.view_layer.update()
    return root, [o for o in new if o.type == "MESH"]


def bounds(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def camera(lens):
    d = bpy.data.cameras.new("cam")
    d.lens = lens
    o = bpy.data.objects.new("cam", d)
    bpy.context.scene.collection.objects.link(o)
    bpy.context.scene.camera = o
    return o


def place(cam, centre, az, el, dist):
    a, e = math.radians(az), math.radians(el)
    cam.location = Vector(centre) + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * dist
    cam.rotation_euler = (Vector(centre) - cam.location).to_track_quat("-Z", "Y").to_euler()


def mat(name, rgb):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*rgb, 1)
    p.inputs["Roughness"].default_value = 0.6
    return m


def text(body, loc, size, m):
    c = bpy.data.curves.new("t", "FONT")
    c.body, c.size, c.align_x = body, size, "CENTER"
    o = bpy.data.objects.new("label_" + body[:20], c)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (math.pi / 2, 0, 0)
    o.data.materials.append(m)
    return o


def render_frames(sc, folder, n, per_frame):
    """Render frames 1..n (or just FRAMES) into folder/####.png, calling per_frame(t in 0..1) first."""
    os.makedirs(folder, exist_ok=True)
    for f in FRAMES or range(1, n + 1):
        if f > n:
            continue
        path = os.path.join(folder, f"{f:04d}.png")
        if os.path.exists(path) and not FRAMES:
            continue  # resumable
        per_frame((f - 1) / max(n - 1, 1))
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)


def smoothstep(a):
    a = min(max(a, 0.0), 1.0)
    return a * a * (3 - 2 * a)


def dolly():
    """The lineup laid out exactly like present.py, then a slow lateral move along it. The framed width follows the
    tallest item near the camera (smoothed), so a 13 cm sign is not lost next to a 1.4 m peel."""
    sc = setup()
    sc.cycles.samples = SAMPLES
    loaded = [(it, *load(it)) for it in items]
    heights = [bounds(m)[1].z for _, _, m in loaded]
    gap = max(0.06, 0.12 * max(heights))
    x, depth = 0.0, 0.0
    for it, root, meshes in loaded:
        lo, hi = bounds(meshes)
        root.location.x = x + (hi.x - lo.x) / 2 - (lo.x + hi.x) / 2
        x += hi.x - lo.x + gap
        depth = max(depth, hi.y - lo.y)
    bpy.context.view_layer.update()
    allm = [o for _, _, m in loaded for o in m]
    lo, hi = bounds(allm)
    total = hi.x - lo.x
    nice = min((0.05, 0.1, 0.2, 0.25, 0.5, 1.0, 2.0, 5.0), key=lambda v: abs(v - total / 5))
    step = nice / 10 if nice <= 0.25 else 0.1
    dark, light_m, ink = mat("bar_dark", (0.03, 0.03, 0.03)), mat("bar_light", (0.85, 0.85, 0.85)), mat("ink", (0.04, 0.04, 0.04))
    by = lo.y - max(0.06, depth * 0.35)
    th = max(0.004, nice / 40)
    for i in range(round(nice / step)):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(lo.x + step * (i + 0.5), by, 0.001))
        b = bpy.context.object
        b.scale = (step, th * 2, 0.002)
        b.data.materials.append(dark if i % 2 == 0 else light_m)
    text(f"{nice * 100:.0f} cm" if nice < 1 else f"{nice:g} m", (lo.x + nice / 2, by - th, th * 1.5), th * 4, ink)
    lsize = max(0.01, min(0.04, gap * 0.22))
    spans = []
    for it, root, meshes in loaded:
        l2, h2 = bounds(meshes)
        text(it.get("label", it["id"])[:28], ((l2.x + h2.x) / 2, l2.y - lsize * 1.5, 0.003), lsize, ink)
        spans.append((l2.x, h2.x, h2.z))
    bpy.context.view_layer.update()
    studio(Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, hi.z * 0.42)), max(total, hi.z) * 0.6)

    sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
    cam = camera(50)
    fov = cam.data.angle  # horizontal for a landscape frame
    aspect = 16 / 9
    base = max(total / 4.5, 0.45)  # narrowest framed width: about a fifth of the row
    n = int(round(SECS * FPS))
    def need(cx):
        """Framed width at cx: wide enough that every item in the central 90% of that same frame fits in height
        (a fixed point: widening can bring a taller item into view, so iterate; it only grows)."""
        w = base
        for _ in range(20):
            hmax = max([z for a, b, z in spans if b > cx - 0.45 * w and a < cx + 0.45 * w] or [0.05])
            w2 = max(base, hmax * 1.6 * aspect)
            if w2 <= w + 1e-6:
                break
            w = w2
        return w

    # ends: first item's left edge / last item's right edge about 9% in from the frame edge (fixed points again)
    xa, xb = lo.x + 0.41 * base, hi.x - 0.41 * base
    for _ in range(20):
        xa, xb = lo.x + 0.41 * need(xa), hi.x - 0.41 * need(xb)
    if xb < xa:
        xa = xb = (lo.x + hi.x) / 2
    xs, raw = [], []
    for i in range(n):
        u = i / max(n - 1, 1)
        cx = xa + (xb - xa) * (0.5 * u + 0.5 * smoothstep(u))  # near-constant speed, soft start and stop
        xs.append(cx)
        raw.append(need(cx))
    # dilate (never frame tighter than an item needs) then a wide gaussian, so the zoom is a gentle push/pull
    rad = int(FPS * 0.8)
    dil = [max(raw[max(0, i - rad):i + rad + 1]) for i in range(n)]
    sig = FPS * 1.0
    ws = []
    for i in range(n):
        acc = wsum = 0.0
        for j in range(n):
            k = math.exp(-((i - j) / sig) ** 2 / 2)
            acc += dil[j] * k
            wsum += k
        ws.append(max(acc / wsum, raw[i]))

    def pose(t):
        i = min(int(round(t * (n - 1))), n - 1)
        w = ws[i]
        vh = w / aspect
        dist = (w / 2) / math.tan(fov / 2)  # w is the width seen at the row, so ws and the path ends agree
        centre = Vector((xs[i], (lo.y + hi.y) / 2 - 0.1 * depth, vh * 0.26))
        place(cam, centre, 0, 13, dist)

    render_frames(sc, os.path.join(OUT, "dolly"), n, pose)


def turntables():
    sc = setup()
    sc.cycles.samples = TSAMPLES
    sc.render.resolution_x, sc.render.resolution_y = 960, 540
    cam = camera(60)
    n = int(round(TSECS * FPS))
    loaded = [(it, *load(it)) for it in items]
    for it, root, meshes in loaded:
        root.hide_render = True
        for o in meshes:
            o.hide_render = True
    for it, root, meshes in loaded:
        for o in meshes:
            o.hide_render = False
        root.rotation_euler = (0, 0, 0)
        bpy.context.view_layer.update()
        lo, hi = bounds(meshes)
        rxy = max(math.hypot(p.x - root.location.x, p.y - root.location.y)
                  for o in meshes for p in (o.matrix_world @ Vector(c) for c in o.bound_box))
        h = hi.z - lo.z
        centre = Vector((root.location.x, root.location.y, lo.z + h / 2))
        radius = math.hypot(rxy, h / 2)
        for o in [o for o in bpy.data.objects if o.type == "LIGHT"]:
            bpy.data.objects.remove(o, do_unlink=True)
        studio(centre, radius * 1.4)
        vfov = 2 * math.atan(math.tan(cam.data.angle / 2) * 9 / 16)
        # fit the spin's bounding cylinder in the frame height: half height + the depth swing seen from 18 degrees
        e = math.radians(20)
        half = (h / 2) * math.cos(e) + rxy * math.sin(e)
        fit_r = max(half, rxy)  # rxy: keep the width inside the central 540x540 square too
        dist = fit_r / math.tan(vfov / 2) * 1.05 + rxy * 0.3
        place(cam, centre, -30, 20, dist)

        def spin(t, root=root):
            root.rotation_euler = (0, 0, math.radians(360 * t * (n - 1) / n))

        render_frames(sc, os.path.join(OUT, "turn", it["id"]), n, spin)
        for o in meshes:
            o.hide_render = True
        root.rotation_euler = (0, 0, 0)


if ONLY in ("", "dolly"):
    dolly()
if ONLY in ("", "turn"):
    turntables()
