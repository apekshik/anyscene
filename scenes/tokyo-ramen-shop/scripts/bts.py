"""Behind-the-scenes dollhouse clips (breakdown/SPEC.md) from breakdown/tokyo-ramen-shop/bts.blend (never saved).

blender -b breakdown/tokyo-ramen-shop/bts.blend --python scenes/tokyo-ramen-shop/scripts/gpu_prefs.py --python scenes/tokyo-ramen-shop/scripts/bts.py -- <clip> [--pass clay|plain|full] [--frames a-b] [--samples n] [--out dir]
clip: a_layout | b_props | c_materials | d_lighting
c_materials renders three passes (clay 1-48, plain 1-96, full 49-144) that bts_ramen.sh composites with ffmpeg.
World coordinates are post-mirror: kitchen wall at x=0, customer wall at x=W, street at y<0.
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
OUT = os.path.abspath(opt("--out", os.path.join(ROOT, "breakdown", "tokyo-ramen-shop", "clips", CLIP)))
W, D, H = 3.6, 7.0, 2.6
CENTER = Vector((W / 2, D / 2, 0.55))
FRAMES = {"a_layout": 144, "b_props": 240, "c_materials": 144, "d_lighting": 240}
N = FRAMES[CLIP]
SPAN = {"a_layout": (-60, -30), "b_props": (-30, 0), "c_materials": (0, 30), "d_lighting": (30, 60)}[CLIP]
DIST, ELEV, LENS = 11.8, math.radians(40), 30

sc = bpy.context.scene
sc.animation_data_clear()            # drops the handheld clip's exposure keys
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

# Round-1 bug in the saved scenes: the counter foot rail was placed by its end but its origin is its centre, so it
# poked ~0.7 m out through the front wall. Fixed in shell.py; patched here so the clips match the corrected build.
_rail = bpy.data.objects.get("foot_rail")
if _rail:
    bpy.context.view_layer.update()
    _lo = min((_rail.matrix_world @ Vector(c)).y for c in _rail.bound_box)
    _rail.location.y += 1.6 - _lo


def coll_objs(name):
    c = bpy.data.collections.get(name)
    return set(c.all_objects) if c else set()


SHELL = coll_objs("shell")
LIGHTS = {o for o in objs if o.type == "LIGHT"}
EXTERIOR = coll_objs("exterior") | {o for o in objs if o.name.startswith(("street_backdrop", "pavement", "eave", "noren", "lantern", "ramen_vending_machine", "neon_"))}
VOLUMES = {o for o in objs if o.name.startswith(("haze_volume", "kitchen_vapor", "steam_", "rain_"))}
DECALS = {o for o in objs if o.name.startswith(("decal_", "sticker_img", "price_strips", "poster_special"))}
POSTERS = {o for o in objs if o.name.split(".")[0] in ("poster_beer", "calendar", "handwritten_notice") or o.name.startswith("flyer_")}
CAMS = {o for o in objs if o.type == "CAMERA"}


def bbox(o):
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return (Vector([min(p[i] for p in pts) for i in range(3)]), Vector([max(p[i] for p in pts) for i in range(3)]))


def key_hide(o, frame, hidden):
    o.hide_render = hidden
    o.hide_viewport = hidden
    o.keyframe_insert("hide_render", frame=frame)
    o.keyframe_insert("hide_viewport", frame=frame)


def hide(os_):
    for o in os_:
        o.hide_render = True
        o.hide_viewport = True


# ------------------------------------------------------------------ camera: one 120° orbit split into four clips

def angle_at(f):
    t = (f - 1) / (N - 1)
    a0, a1 = SPAN
    if CLIP == "a_layout":       # ease in only
        v = 1 / 0.875
        u = v * t * t / 0.5 if t < 0.25 else v * (0.125 + (t - 0.25))
    elif CLIP == "d_lighting":   # ease out only
        s = 1 - t
        v = 1 / 0.875
        u = 1 - (v * s * s / 0.5 if s < 0.25 else v * (0.125 + (s - 0.25)))
    else:
        u = t
    return math.radians(a0 + (a1 - a0) * u)


cd = bpy.data.cameras.new("bts_cam")
cd.lens = LENS
cd.sensor_width = 36
cd.clip_start = 0.1
cd.dof.use_dof = False
cd.shift_y = -0.05             # room sits a little high in frame: bottom 140 px stays clear for captions
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

# ------------------------------------------------------------------ dollhouse cutaway: ceiling always, near walls per frame

# ------------------------------------------------------------------ looks


def eevee():
    sc.render.engine = "BLENDER_EEVEE"
    ee = sc.eevee
    for attr, v in (("taa_render_samples", 32), ("use_shadows", True), ("use_raytracing", True), ("use_fast_gi", True)):
        if hasattr(ee, attr):
            setattr(ee, attr, v)


def studio_world(color, strength):
    w = sc.world
    bg = w.node_tree.nodes["Background"]
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
    hide(LIGHTS | VOLUMES | DECALS | EXTERIOR)
    studio_world((0.7, 0.72, 0.76), 0.45)   # dim fill + strong key: the clay needs form shading
    add_sun(4.5, rot=(48, 0, 120))
    eevee()


def neutral():
    hide(LIGHTS | VOLUMES | EXTERIOR)
    studio_world((0.8, 0.8, 0.8), 1.1)
    add_sun(2.5)
    eevee()
    if PASS == "plain":
        hide(DECALS | POSTERS)


def cutaway():
    """Ceiling always off; walls (and wall-mounted things) on the camera side keyed off per frame. Runs after the look,
    so anything a look already hid (exterior, volumes) stays hidden."""
    hide([o for o in objs if o.name.startswith("ceiling")])
    WALLS = {  # outward normal -> shell/wall-ish objects on that side
        (1, 0): lambda lo, hi: lo.x > W - 0.25,
        (0, -1): lambda lo, hi: hi.y < 0.25,
        (0, 1): lambda lo, hi: lo.y > D - 0.25,
    }
    WALLISH = ("wall_", "front_", "wainscot", "skirting", "door", "win_", "ceiling", "eave", "noren")
    side_objs = {k: [] for k in WALLS}
    corner_objs = []
    for o in objs:
        if o.parent is not None or o.type not in ("MESH", "CURVE", "FONT") or o in VOLUMES or o.hide_render:
            continue
        lo, hi = bbox(o)
        near = [k for k, test in WALLS.items() if test(lo - Vector((0.45, 0.45, 0)), hi + Vector((0.45, 0.45, 0)))]
        if hi.z > 1.2 and len(near) == 2 and not o.name.startswith(WALLISH):
            corner_objs.append((o, near))   # tall thing in a corner (drink fridge): off once both its walls are off
        for k, test in WALLS.items():
            if not test(lo, hi):
                continue
            thin = (hi.x - lo.x if k[0] else hi.y - lo.y) < 0.3
            wall_mounted = lo.z > 0.45 and thin
            if o.name.startswith(WALLISH) or wall_mounted:
                side_objs[k].append(o)
    for k, lst in side_objs.items():
        prev = None
        for f in range(1, N + 1):
            a = angle_at(f)
            hidden = k[0] * math.cos(a) + k[1] * math.sin(a) > 0.3
            if hidden != prev:
                for o in lst:
                    key_hide(o, f, hidden)
                prev = hidden
        for o in lst:
            if o.animation_data and o.animation_data.action:
                act = o.animation_data.action
                fcs = act.fcurves if hasattr(act, "fcurves") else act.layers[0].strips[0].channelbag(act.slots[0]).fcurves
                for fc in fcs:
                    for kp in fc.keyframe_points:
                        kp.interpolation = "CONSTANT"

    for o, ks in corner_objs:
        prev = None
        for f in range(1, N + 1):
            a = angle_at(f)
            hidden = all(k[0] * math.cos(a) + k[1] * math.sin(a) > 0.3 for k in ks)
            if hidden != prev:
                key_hide(o, f, hidden)
                prev = hidden


# ------------------------------------------------------------------ clips


def clip_a():
    """Shell only, pieces rising into place over the first 2 s (floor first, then by height)."""
    hide([o for o in objs if o not in SHELL and o not in CAMS] + [o for o in SHELL if o.name.startswith(("menu_plaques", "poster", "calendar", "handwritten"))])
    pieces = [o for o in SHELL if o.parent is None and not o.name.startswith(("floor", "ceiling"))]
    pieces.sort(key=lambda o: (bbox(o)[0].z, bbox(o)[0].y))
    for i, o in enumerate(pieces):
        s = 4 + int(36 * i / max(1, len(pieces) - 1))
        z = o.location.z
        o.location.z = z - 2.8
        o.keyframe_insert("location", index=2, frame=1)
        o.keyframe_insert("location", index=2, frame=s)
        o.location.z = z
        o.keyframe_insert("location", index=2, frame=s + 10)


def clip_b():
    props = [o for o in objs if o.parent is None and o not in SHELL and o not in LIGHTS | VOLUMES | DECALS | EXTERIOR | CAMS
             and o.type in ("MESH", "CURVE", "FONT", "EMPTY") and not o.hide_render]
    props.sort(key=lambda o: -max(1e-6, (lambda lo, hi: (hi - lo).x * (hi - lo).y * (hi - lo).z)(*bbox(o))))
    n = len(props)
    for i, o in enumerate(props):
        f = 8 + int(188 * (i / max(1, n - 1)) ** 1.5)   # big things spaced out first, clutter rains in at the end
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
    """Insert value*k into a socket (linked or default) and key k over key_frames [(frame, value), ...]."""
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
    """Textured scene in darkness; practicals, signage, street, then fills; volumetrics last."""
    sc.render.engine = "CYCLES"
    sc.cycles.samples = int(opt("--samples", 16))
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPTIX"
    sc.cycles.use_adaptive_sampling = True
    sc.render.use_persistent_data = True
    sc.view_settings.exposure = 0.35   # dollhouse distance: lift the night look a little
    hide([o for o in objs if o.name.startswith(("street_backdrop", "road"))])
    order = [("pendant_spot_0", 12), ("pendant_glow_0", 12), ("pendant_spot_1", 20), ("pendant_glow_1", 20),
             ("pendant_spot_2", 28), ("pendant_glow_2", 28), ("pendant_spot_3", 36), ("pendant_glow_3", 36),
             ("hood_strip", 50), ("kitchen_tube", 58), ("kitchen_tube_front", 64), ("ticket_glow", 76), ("fridge_glow", 84),
             ("lantern_light", 100), ("neon_izakaya_spill", 108), ("neon_snack_spill", 114), ("vending_glow", 120),
             ("street_lamp", 132), ("street_fill", 140), ("door_spill", 146), ("window_spill", 150), ("street_bounce", 156)]
    when = dict(order)
    for o in LIGHTS:
        if o.name.startswith("bts_"):
            continue
        f0 = when.get(o.name, 160)
        e = o.data.energy
        for f, v in ramp(f0, 10):
            o.data.energy = e * v
            o.data.keyframe_insert("energy", frame=f)
    # Emissive materials follow the light they belong to.
    owner_time = [("pendant_bulb", 12), ("ticket_machine", 76), ("ramen_drink_fridge", 84), ("lantern", 100), ("neon_izakaya", 108),
                  ("neon_snack", 114), ("ramen_vending_machine", 120), ("lamp_lens", 132)]
    done = set()
    for o in objs:
        if o.type != "MESH":
            continue
        f0 = next((t for p, t in owner_time if o.name.startswith(p)), None)
        for m in o.data.materials:
            if not m or not m.node_tree or m.name in done:
                continue
            for n in m.node_tree.nodes:
                if n.type == "BSDF_PRINCIPLED":
                    s = n.inputs["Emission Strength"]
                    if s.is_linked or s.default_value > 0:
                        _mul_node(m.node_tree, s, ramp(f0 or 60, 10))
                        done.add(m.name)
                elif n.type == "EMISSION":
                    _mul_node(m.node_tree, n.inputs["Strength"], ramp(f0 or 60, 10))
                    done.add(m.name)
    # Volumetrics and rain last.
    vol_time = {"haze": 166, "kitchen_vapor": 174, "steam_vol": 182}
    for m in bpy.data.materials:
        if not m.node_tree:
            continue
        for n in m.node_tree.nodes:
            if n.type == "PRINCIPLED_VOLUME" and m.name in vol_time:
                _mul_node(m.node_tree, n.inputs["Density"], ramp(vol_time[m.name], 26))
    rain = bpy.data.materials.get("rain")
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
    else:
        neutral()
elif CLIP == "d_lighting":
    clip_d()

cutaway()

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
