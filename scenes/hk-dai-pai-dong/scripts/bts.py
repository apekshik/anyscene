"""Behind-the-scenes dollhouse clips (breakdown/SPEC.md) for an open street stall, from a copy of hk.blend (never saved).

blender -b scenes/hk-dai-pai-dong/hk.blend --python .../gpu_prefs.py --python .../bts.py -- <clip> [--pass clay|plain|full]
        [--frames a-b] [--samples n] [--out dir] [--still f]
clip: a_layout | b_props | c_materials | d_lighting

"Dollhouse" for an open stall: a high 120-degree orbit around the stall and the street with the awning tarp hidden,
on the street side of the stall (the tenement wall behind the kitchen is the backdrop). The far-side buildings and
everything over the far pavement would sit between the camera and the stall, so they are hidden for the whole orbit.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
CLIP = argv[0]


def opt(k, d=None):
    return argv[argv.index(k) + 1] if k in argv else d


PASS = opt("--pass", {"a_layout": "clay", "b_props": "clay", "c_materials": "full", "d_lighting": "night"}[CLIP])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUT = os.path.abspath(opt("--out", os.path.join(ROOT, "breakdown", "hk-dai-pai-dong", "clips", CLIP)))
CENTER = Vector((-0.4, 2.6, 0.6))
FRAMES = {"a_layout": 144, "b_props": 240, "c_materials": 144, "d_lighting": 240}
N = FRAMES[CLIP]
SPAN = {"a_layout": (-62, -32), "b_props": (-32, -2), "c_materials": (-2, 28), "d_lighting": (28, 58)}[CLIP]
DIST, ELEV, LENS = 15.5, math.radians(38), 30

sc = bpy.context.scene
sc.animation_data_clear()
sc.view_settings.exposure = 0.0
sc.frame_start, sc.frame_end = 1, N
sc.render.fps = 24
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1920, 1080, 100
sc.render.use_compositing = False     # no grade, no lens fx (spec)
sc.render.use_motion_blur = False
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_depth = "8"
sc.render.film_transparent = False

objs = list(bpy.data.objects)


def coll_objs(*names):
    out = set()
    for n in names:
        c = bpy.data.collections.get(n)
        if c:
            out |= set(c.all_objects)
    return out


def bbox(o):
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return (Vector([min(p[i] for p in pts) for i in range(3)]), Vector([max(p[i] for p in pts) for i in range(3)]))


def hide(os_):
    for o in os_:
        o.hide_render = True
        o.hide_viewport = True


LIGHTS = {o for o in objs if o.type == "LIGHT"}
CAMS = {o for o in objs if o.type == "CAMERA"}
VOLUMES = {o for o in objs if o.name.startswith(("haze", "steam_", "drizzle", "awning_drips", "wok_flame"))}
SHELL = coll_objs("shell", "street", "stall") - VOLUMES
SIGNS = coll_objs("signs")
DETAIL = coll_objs("street_detail")
DECALS = {o for o in objs if o.get("decal") or o.name.startswith(("menu_strips", "stall_sign", "fascia_text"))}
AWNING = {o for o in objs if o.name.startswith(("awning_tarp", "awn_rafter"))}
FAR = {o for o in objs if o.type in ("MESH", "CURVE", "FONT") and o.parent is None and bbox(o)[0].x > 6.9}
CABLES = {o for o in objs if o.name.startswith("cable_x")}
SKY = {o for o in objs if o.name.startswith(("skyline_card", "harbour_water"))}
hide(AWNING | FAR | CABLES)
lamp = bpy.data.objects.get("street_lamp")
if lamp:
    hide([lamp])


def angle_at(f):
    t = (f - 1) / (N - 1)
    a0, a1 = SPAN
    v = 1 / 0.875
    if CLIP == "a_layout":       # ease in only
        u = v * t * t / 0.5 if t < 0.25 else v * (0.125 + (t - 0.25))
    elif CLIP == "d_lighting":   # ease out only
        s = 1 - t
        u = 1 - (v * s * s / 0.5 if s < 0.25 else v * (0.125 + (s - 0.25)))
    else:
        u = t
    return math.radians(a0 + (a1 - a0) * u)


cd = bpy.data.cameras.new("bts_cam")
cd.lens = LENS
cd.sensor_width = 36
cd.clip_start = 0.1
cd.clip_end = 400
cd.dof.use_dof = False
cd.shift_y = -0.06             # bottom 140 px stays clear for captions
cam = bpy.data.objects.new("bts_cam", cd)
sc.collection.objects.link(cam)
sc.camera = cam
for f in range(1, N + 1):
    a = angle_at(f)
    pos = CENTER + Vector((math.cos(a) * math.cos(ELEV), math.sin(a) * math.cos(ELEV), math.sin(ELEV))) * DIST
    cam.location = pos
    cam.rotation_euler = (CENTER - pos).to_track_quat("-Z", "Y").to_euler()
    cam.keyframe_insert("location", frame=f)
    cam.keyframe_insert("rotation_euler", frame=f)


def eevee():
    sc.render.engine = "BLENDER_EEVEE"
    ee = sc.eevee
    for attr, v in (("taa_render_samples", 32), ("use_shadows", True), ("use_raytracing", True), ("use_fast_gi", True)):
        if hasattr(ee, attr):
            setattr(ee, attr, v)


def studio_world(color, strength):
    nt = sc.world.node_tree
    bg = nt.nodes["Background"]
    for l in list(bg.inputs["Color"].links):
        nt.links.remove(l)
    bg.inputs["Color"].default_value = (*color, 1)
    bg.inputs["Strength"].default_value = strength


def add_sun(energy, rot=(50, 0, 30), size=8):
    ld = bpy.data.lights.new("bts_sun", "SUN")
    ld.energy = energy
    ld.angle = math.radians(size)
    so = bpy.data.objects.new("bts_sun", ld)
    sc.collection.objects.link(so)
    so.rotation_euler = [math.radians(v) for v in rot]
    return so


def clay():
    m = bpy.data.materials.new("BTS_CLAY")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.62, 0.62, 0.6, 1)
    b.inputs["Roughness"].default_value = 0.65
    bpy.context.view_layer.material_override = m
    hide(LIGHTS | VOLUMES | DECALS | SKY)
    studio_world((0.7, 0.72, 0.76), 0.45)
    add_sun(4.5, rot=(48, 0, 120))
    sc.view_settings.exposure = -0.7   # the scene carries +0.4 EV for the night look: clay washed out without this
    eevee()


def neutral():
    hide(LIGHTS | VOLUMES | SKY)
    studio_world((0.8, 0.8, 0.8), 1.1)
    add_sun(2.5, rot=(50, 0, 140))
    eevee()
    # Emissive signage would blow out under flat light: keep only its albedo.
    for m in bpy.data.materials:
        if m.node_tree:
            for n in m.node_tree.nodes:
                if n.type == "BSDF_PRINCIPLED" and not n.inputs["Emission Strength"].is_linked:
                    n.inputs["Emission Strength"].default_value = min(n.inputs["Emission Strength"].default_value, 0.6)
    if PASS == "plain":
        hide(DECALS | {o for o in objs if o.name.startswith(("poster_", "menu_strips"))})
        for o in objs:
            o.color = (1, 1, 1, 1)   # per-instance grime tint off


def clip_a():
    """The layout: ground, facades, stall frame and shelves; pieces rise into place over the first 2 s."""
    keep = (SHELL | CAMS) - AWNING - FAR
    hide([o for o in objs if o not in keep])
    pieces = [o for o in keep if o.parent is None and o.type in ("MESH", "CURVE", "FONT")
              and not o.name.startswith(("pavement", "road", "kerb", "harbour", "skyline", "line_", "drain_"))]
    pieces.sort(key=lambda o: (bbox(o)[0].z, -bbox(o)[0].x))
    for i, o in enumerate(pieces):
        s = 4 + int(36 * i / max(1, len(pieces) - 1))
        z = o.location.z
        o.location.z = z - 3.5
        o.keyframe_insert("location", index=2, frame=1)
        o.keyframe_insert("location", index=2, frame=s)
        o.location.z = z
        o.keyframe_insert("location", index=2, frame=s + 10)


def clip_b():
    """Props pop in: furniture, then big props, then clutter (each scales up with a small overshoot)."""
    hide(SIGNS | DETAIL)
    props = [o for o in objs if o.parent is None and o.get("placed") and not o.hide_render]
    def vol(o):
        lo, hi = bbox(o)
        return (hi - lo).x * (hi - lo).y * (hi - lo).z
    props.sort(key=lambda o: (0 if "furniture" in o.users_collection[0].name else 1, -vol(o)))
    n = len(props)
    for i, o in enumerate(props):
        f = 8 + int(188 * (i / max(1, n - 1)) ** 1.4)
        s = o.scale.copy()
        o.scale = (0, 0, 0)
        o.keyframe_insert("scale", frame=1)
        o.keyframe_insert("scale", frame=f)
        o.scale = s * 1.12
        o.keyframe_insert("scale", frame=f + 4)
        o.scale = s
        o.keyframe_insert("scale", frame=f + 6)
    print("BTS props animated", n, flush=True)


def _mul_node(nt, sock, key_frames):
    src = sock.links[0].from_socket if sock.is_linked else None
    m = nt.nodes.new("ShaderNodeMath")
    m.operation = "MULTIPLY"
    if src is not None:
        nt.links.new(src, m.inputs[0])
    else:
        m.inputs[0].default_value = sock.default_value if not hasattr(sock.default_value, "__len__") else 1.0
    nt.links.new(m.outputs[0], sock)
    for f, v in key_frames:
        m.inputs[1].default_value = v
        m.inputs[1].keyframe_insert("default_value", frame=f)
    return m


def ramp(f0, length=8):
    return [(1, 0.0), (f0, 0.0), (f0 + length, 1.0)]


def clip_d():
    """Textured scene in the dark: bulbs, wok fire, shade, fluorescent; then neon/lightboxes; street; fills;
    then steam, haze and drizzle fade in. Lights carry ["order"]/["cat"] from lights.py."""
    sc.render.engine = "CYCLES"
    sc.cycles.samples = int(opt("--samples", 16))
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPTIX"
    sc.cycles.use_adaptive_sampling = True
    sc.render.use_persistent_data = True
    sc.view_settings.exposure = 0.6   # dollhouse distance: lift the night look a little
    sc.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.15
    cat_t = {"practical": (10, 100), "signage": (104, 138), "street": (140, 150), "fill": (154, 160)}
    by_cat = {}
    for o in sorted(LIGHTS, key=lambda o: o.get("order", 999)):
        if o.name.startswith("bts_"):
            continue
        by_cat.setdefault(o.get("cat", "fill"), []).append(o)
    when = {}
    for cat, lst in by_cat.items():
        a, b = cat_t.get(cat, (156, 160))
        for i, o in enumerate(lst):
            when[o.name] = a + int((b - a) * i / max(1, len(lst) - 1))
    for o in LIGHTS:
        if o.name.startswith("bts_"):
            continue
        f0 = when.get(o.name, 158)
        if o.data.animation_data:  # flicker drivers would override the keys
            o.data.animation_data_clear()
        e = o.data.energy
        for f, v in ramp(f0, 10):
            o.data.energy = e * v
            o.data.keyframe_insert("energy", frame=f)
    # Emissive materials come on with their category: bulbs/flames with the practicals, neon with the signage.
    def mat_time(name):
        if name.startswith(("bulb_glow", "fluoro_glow")):
            return 14
        if name.startswith(("neon_", "lightbox_")):
            return 108
        if name.startswith(("bldg_", "facemat")) or "facemat" in name:
            return 146
        if name == "skyline":
            return 150
        return 120
    done = set()
    for m in bpy.data.materials:
        if not m.node_tree or m.name in done:
            continue
        for n in m.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                s = n.inputs["Emission Strength"]
                if s.is_linked or s.default_value > 0:
                    _mul_node(m.node_tree, s, ramp(mat_time(m.name), 10))
                    done.add(m.name)
            elif n.type == "EMISSION":
                _mul_node(m.node_tree, n.inputs["Strength"], ramp(mat_time(m.name), 10))
                done.add(m.name)
    # Flame volumes come on with the first practicals; steam, haze and drizzle last.
    vol_time = {"flame_vol": (30, "Emission Strength", 8), "steam_wok": (166, "Density", 24), "steam_pot": (172, "Density", 24),
                "street_haze": (178, "Density", 26)}
    for m in bpy.data.materials:
        if m.name in vol_time and m.node_tree:
            f0, sock, ln = vol_time[m.name]
            for n in m.node_tree.nodes:
                if n.type == "PRINCIPLED_VOLUME":
                    _mul_node(m.node_tree, n.inputs[sock], ramp(f0, ln))
    rain = bpy.data.materials.get("drizzle")
    if rain:
        b = next(n for n in rain.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        _mul_node(rain.node_tree, b.inputs["Alpha"], ramp(190, 24))
        _mul_node(rain.node_tree, b.inputs["Emission Strength"], ramp(190, 24))
    print("BTS lights", len(LIGHTS), "emissive mats", len(done), flush=True)


if CLIP == "a_layout":
    clay()
    clip_a()
elif CLIP == "b_props":
    clay()
    clip_b()
elif CLIP == "c_materials":
    if PASS == "clay":
        clay()
        hide(SIGNS | DETAIL)
    else:
        neutral()
elif CLIP == "d_lighting":
    clip_d()

a, b = (int(x) for x in opt("--frames", f"1-{N}").split("-"))
sc.frame_start, sc.frame_end = a, b
os.makedirs(OUT, exist_ok=True)
sc.render.filepath = os.path.join(OUT, "")
if "--still" in argv:
    f = int(opt("--still"))
    sc.frame_set(f)
    sc.render.filepath = os.path.join(OUT, f"still_{f:04d}.png")
    bpy.ops.render.render(write_still=True)
else:
    bpy.ops.render.render(animation=True)
print("BTS rendered", CLIP, PASS, a, b, flush=True)
