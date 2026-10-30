"""Behind-the-scenes "dollhouse" clips for the repair shop (breakdown/SPEC.md).

  blender -b scenes/tokyo-electronics-repair/repair_final.blend --python scenes/tokyo-electronics-repair/scripts/bts.py -- setup
      -> breakdown/tokyo-electronics-repair/bts.blend (copy of the final scene + bts camera); never saves over a scene file
  blender -b breakdown/tokyo-electronics-repair/bts.blend --python scenes/tokyo-electronics-repair/scripts/bts.py -- <a_layout|b_props|c_materials|d_lighting> [first last]
      -> breakdown/tokyo-electronics-repair/clips/<clip>/####.png (existing frames are skipped). Run each through pipeline/gpu_run.sh.

One continuous 120° orbit around the room centre, split A 0-30°, B 30-60°, C 60-90°, D 90-120° (ease-in on A,
ease-out on D). Walls nearest the camera and the ceiling are hidden per frame, so the interior reads as a dollhouse.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

ROOT = os.environ.get("ANYSCENE_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUT = os.path.join(ROOT, "breakdown", "tokyo-electronics-repair")
W, D, H = 4.2, 6.5, 2.7
CENTRE = Vector((2.0, 3.35, 0.75))
AZ0 = -150.0          # world azimuth (deg, from +X, CCW) at orbit 0°: front-left; the orbit sweeps across the storefront
ELEV, DIST, LENS = 42.0, 10.2, 30.0  # side to front-right, bench (left) and racks (right) both side-on, counter in the middle
CLIPS = {"a_layout": (144, 0, 30, "in"), "b_props": (240, 30, 60, None),
         "c_materials": (144, 60, 90, None), "d_lighting": (240, 90, 120, "out")}
args = sys.argv[sys.argv.index("--") + 1:]
sc = bpy.context.scene

# ------------------------------------------------------------------ object groups
SHELL_COLLS = ("shell", "storefront", "bench", "drawers", "shelving", "counter", "ceiling", "deco")
PROP_COLLS = ("props", "dress2_A_mid", "dress2_B_clutter", "dress2_C_micro")
EXTERIOR = ("pavement", "road", "street_backdrop")
CEILING_EXTRA = ("fixture_racks", "tube_racks_", "tube_on")
# cutaway walls: outward normal -> objects that go with that wall
WALLS = {
    (-1, 0): ("wall_left", "baseboard_l", "poster_extra_0", "poster_tape_0", "outlet_"),
    (1, 0): ("wall_right", "baseboard_r", "poster_parts", "sticky_7"),
    (0, -1): ("front_", "glass_", "door_leaf", "decal_signage", "flyer_glass", "flyer_tape"),
    (0, 1): ("wall_back", "door_frame", "door_slab", "door_handle", "baseboard_b", "calendar", "backroom_dark", "repair_wall_clock", "poster_extra_1",
             "poster_tape_1"),
}


def coll_objs(names):
    out = []
    for n in names:
        c = bpy.data.collections.get(n)
        if c:
            out += list(c.all_objects)
    return out


def starts(o, prefixes):
    return o.name.startswith(prefixes)


def azimuth(clip, f):
    n, a0, a1, ease = CLIPS[clip]
    u = (f - 1) / (n - 1)
    if ease == "in":
        u = 2 * u * u - u ** 3          # slope 0 -> 1
    elif ease == "out":
        u = u + u * u - u ** 3          # slope 1 -> 0
    return AZ0 + a0 + (a1 - a0) * u


def cam_pose(az):
    a, e = math.radians(az), math.radians(ELEV)
    p = CENTRE + Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e))) * DIST
    return p, (CENTRE - p).to_track_quat("-Z", "Y").to_euler()


# ------------------------------------------------------------------ setup
if args[0] == "setup":
    cd = bpy.data.cameras.new("bts_cam")
    cd.lens, cd.sensor_width, cd.sensor_fit = LENS, 36.0, "HORIZONTAL"
    cd.shift_y = -0.12  # room sits higher in frame: bottom 140 px stay clear for captions
    cd.dof.use_dof = False
    cd.clip_end = 100
    cam = bpy.data.objects.new("bts_cam", cd)
    sc.collection.objects.link(cam)
    clay = bpy.data.materials.new("bts_clay")
    b = clay.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.62, 0.62, 0.6, 1)
    b.inputs["Roughness"].default_value = 0.7
    os.makedirs(OUT, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "bts.blend"), copy=True)
    print("BTS setup saved")
    sys.exit(0)

clip = args[0]
n = CLIPS[clip][0]
first, last = (int(args[1]), int(args[2])) if len(args) > 2 else (1, n)
CLAY_PLATE = len(args) > 3 and args[3] == "clay"  # c_materials clay plate for the clay -> material wipe
cam = bpy.data.objects["bts_cam"]
sc.camera = cam
sc.frame_start, sc.frame_end = 1, n
r = sc.render
r.resolution_x, r.resolution_y, r.resolution_percentage = 1920, 1080, 100
r.fps = 24
r.use_motion_blur = False
r.use_compositing = False  # no lens fx / glare: clean plates, the main session grades
r.image_settings.file_format = "PNG"
r.image_settings.color_mode = "RGB"
r.image_settings.color_depth = "8"
r.film_transparent = False
for o in bpy.data.objects:
    if o.animation_data and o.name.startswith(("CR_", "cam_handheld")):
        o.animation_data_clear()

# camera: one key per frame
for f in range(1, n + 1):
    p, rot = cam_pose(azimuth(clip, f))
    cam.location, cam.rotation_euler = p, rot
    cam.keyframe_insert("location", frame=f)
    cam.keyframe_insert("rotation_euler", frame=f)

# ------------------------------------------------------------------ visibility
everything = [o for o in sc.objects if o.type in ("MESH", "CURVE", "LIGHT", "VOLUME")]
shell = set(coll_objs(SHELL_COLLS))
props = set(coll_objs(PROP_COLLS))
ceiling = set(coll_objs(("ceiling",))) | {o for o in sc.objects if starts(o, CEILING_EXTRA)} | {sc.objects["ceiling"]}
exterior = set(coll_objs(("street",))) | {o for o in sc.objects if starts(o, EXTERIOR)}
exterior |= {o for o in props if starts(o, ("vending_", "vm_bottle", "bike_", "aframe_", "umbrella_puddle"))
             and o.location.y < -0.1}
night = [o for o in coll_objs(("night_rig",))]
haze = sc.objects.get("haze")
lights = [o for o in sc.objects if o.type == "LIGHT"]
for o in everything:
    o.hide_render = False


def wall_objs(normal):
    pre = WALLS[normal]
    return [o for o in sc.objects if starts(o, pre) and o not in props or o.name in pre]


cut = {k: wall_objs(k) for k in WALLS}
for o in ceiling:
    o.hide_render = True
show_exterior = False  # with the storefront cut away the street props sit in the foreground; street light comes from lamps
for o in exterior:
    o.hide_render = not show_exterior
for o in sc.objects:
    if o.name.startswith(("CR_", "focus_", "clay_")):
        o.hide_render = True
# per-frame wall cutaway (constant keys)
for f in range(1, n + 1):
    a = math.radians(azimuth(clip, f))
    d = (math.cos(a), math.sin(a))
    for (nx, ny), objs in cut.items():
        hide = d[0] * nx + d[1] * ny > 0.25
        for o in objs:
            o.hide_render = hide
            o.keyframe_insert("hide_render", frame=f)
for o in {o for objs in cut.values() for o in objs}:
    if o.animation_data and o.animation_data.action:
        act = o.animation_data.action
        for fc in act.layers[0].strips[0].channelbag(act.slots[0]).fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"


def studio(clay):
    """Bright even look: grey world, a soft sun, night lights + haze off, neutral exposure."""
    for o in lights:
        o.hide_render = True
    if haze:
        haze.hide_render = True
    w = sc.world
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.75, 0.77, 0.8, 1)
    bg.inputs["Strength"].default_value = 1.2 if clay else 0.9
    ld = bpy.data.lights.new("bts_sun", "SUN")
    ld.energy, ld.angle = (2.2 if clay else 2.5), math.radians(12)
    s = bpy.data.objects.new("bts_sun", ld)
    sc.collection.objects.link(s)
    s.rotation_euler = (math.radians(38), math.radians(8), math.radians(140))
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    r.engine = "BLENDER_EEVEE"
    ev = sc.eevee
    ev.taa_render_samples = 32
    ev.use_raytracing = True
    ev.use_shadows = True


def clay_override():
    m = bpy.data.materials.get("bts_clay")
    if m is None:  # an unused material is not saved with the copy, so build it here
        m = bpy.data.materials.new("bts_clay")
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (0.62, 0.62, 0.6, 1)
        b.inputs["Roughness"].default_value = 0.7
    sc.view_layers[0].material_override = m


# ------------------------------------------------------------------ clips
if clip == "a_layout":
    studio(True)
    clay_override()
    for o in props:
        o.hide_render = True
    # furniture blocks rise into place over the first 2 s (walls and floor stay)
    risers = [o for o in shell if o.parent is None and not starts(o, ("floor", "wall_", "front_", "glass_", "door", "baseboard",
                                                                     "backroom", "ceiling", "pavement", "road", "street", "decal"))]
    risers.sort(key=lambda o: (o.users_collection[0].name, o.location.y))
    for i, o in enumerate(risers):
        f0 = 1 + int(30 * i / max(1, len(risers) - 1))
        o.delta_location = (0, 0, -3.0)
        o.keyframe_insert("delta_location", index=2, frame=f0)
        o.delta_location = (0, 0, 0.12)
        o.keyframe_insert("delta_location", index=2, frame=f0 + 12)
        o.delta_location = (0, 0, 0)
        o.keyframe_insert("delta_location", index=2, frame=f0 + 18)

elif clip == "b_props":
    studio(True)
    clay_override()
    tops = [o for o in props if o.parent is None and not o.hide_render and o not in exterior]

    def vol(o):
        pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
        s = Vector((max(p.x for p in pts) - min(p.x for p in pts), max(p.y for p in pts) - min(p.y for p in pts),
                    max(p.z for p in pts) - min(p.z for p in pts)))
        return s.x * s.y * max(s.z, 0.01)
    curves = [o for o in tops if o.type == "CURVE"]
    meshes = sorted([o for o in tops if o.type != "CURVE"], key=vol, reverse=True)
    order = meshes + curves  # cables last: they grow along their length
    span = 194
    for i, o in enumerate(order):
        f0 = 1 + int(span * (i / max(1, len(order) - 1)) ** 1.35)  # big things get more room, clutter speeds up
        if o.type == "CURVE":
            o.data.bevel_factor_mapping_end = "SPLINE"
            o.data.bevel_factor_end = 0.0
            o.data.keyframe_insert("bevel_factor_end", frame=f0)
            o.data.bevel_factor_end = 1.0
            o.data.keyframe_insert("bevel_factor_end", frame=f0 + 8)
            continue
        for fr, s in ((f0, 0.0), (f0 + 4, 1.12), (f0 + 6, 0.97), (f0 + 8, 1.0)):
            o.delta_scale = (s, s, s)
            o.keyframe_insert("delta_scale", frame=fr)

elif clip == "c_materials" and CLAY_PLATE:
    studio(True)
    clay_override()

elif clip == "c_materials":
    studio(False)
    # grime + decals fade in over frames 48-96 (the clay->material wipe over 1-48 is done on the frames, see bts_wipe)
    def key_value(sock, v0, v1):
        sock.default_value = v0
        sock.keyframe_insert("default_value", frame=48)
        sock.default_value = v1
        sock.keyframe_insert("default_value", frame=96)
    for m in bpy.data.materials:
        if not m.node_tree:
            continue
        for nd in m.node_tree.nodes:
            if nd.type == "GROUP" and nd.node_tree and nd.node_tree.name == "grime_layer":
                key_value(nd.inputs["Amount"], 0.0, nd.inputs["Amount"].default_value)
    DECALS = ("poster", "calendar", "flyer", "sticky", "price", "repair_tags", "tape_yellowed", "decal_signage", "drawer_labels",
              "puddle")
    for m in bpy.data.materials:
        if not m.node_tree or not any(k in m.name for k in DECALS):
            continue
        nt = m.node_tree
        out = next(nd for nd in nt.nodes if nd.type == "OUTPUT_MATERIAL")
        src = out.inputs["Surface"].links[0].from_socket
        mix = nt.nodes.new("ShaderNodeMixShader")
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        nt.links.new(tr.outputs[0], mix.inputs[1])
        nt.links.new(src, mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
        key_value(mix.inputs[0], 0.0, 1.0)

elif clip == "d_lighting":
    r.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for dv in prefs.devices:
        dv.use = dv.type == "OPTIX"
    c = sc.cycles
    c.device = "GPU"
    c.samples = 12
    c.use_adaptive_sampling = True
    c.adaptive_threshold = 0.05
    c.use_denoising = True
    c.denoiser = "OPTIX"
    c.max_bounces = 4
    c.diffuse_bounces, c.glossy_bounces, c.transmission_bounces = 2, 2, 4
    c.volume_step_rate = 8.0
    c.volume_max_steps = 256
    r.use_persistent_data = True
    sc.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.4  # near black
    # (start frame, names): practicals, signage/neon, window/street, fills + bounce
    STAGES = [
        (10, ("lamp_spot", "lamp_bounce")), (22, ("scope_spill",)), (32, ("counter_lamp_spot", "counter_lamp_fill")),
        (42, ("ring_lamp_light",)), (52, ("rack_clip_spot", "rack_clip_glow")),
        (72, ("neon_magenta",)), (80, ("neon_cyan",)), (88, ("aframe_glow", "vending_spill")),
        (108, ("street_fill",)), (118, ("streetlamp",)),
        (138, ("tube_racks_light",)), (150, ("rack_bounce",)), (160, ("counter_bounce",)),
    ]
    EMIT = {  # emissive materials switch on with their practical
        "scope_crt": 22, "tv_crt": 52, "register_vfd": 32, "ring_led": 42, "clip_bulb": 52, "fluoro_on": 138,
        "street_backdrop": 108, "vending_panel": 88, "aframe_bulb": 88,
    }
    RAMP = 10
    staged = set()
    for f0, names in STAGES:
        for nm in names:
            o = sc.objects.get(nm)
            if not o:
                continue
            e = o.data.energy
            o.data.energy = 0.0
            o.data.keyframe_insert("energy", frame=f0)
            o.data.energy = e
            o.data.keyframe_insert("energy", frame=f0 + RAMP)
            staged.add(o.name)
    for o in lights:  # anything not in the list comes on with the fills
        if o.name not in staged and not o.hide_render:
            e = o.data.energy
            o.data.energy = 0.0
            o.data.keyframe_insert("energy", frame=160)
            o.data.energy = e
            o.data.keyframe_insert("energy", frame=170)
    # emissive materials: a keyed multiplier in front of Emission Strength (default 0 = off until its stage)
    for m in bpy.data.materials:
        if not m.node_tree:
            continue
        b = next((nd for nd in m.node_tree.nodes if nd.type == "BSDF_PRINCIPLED"), None)
        if b is None:
            continue
        es = b.inputs["Emission Strength"]
        if not es.is_linked and es.default_value <= 0:
            continue
        f0 = next((v for k, v in EMIT.items() if k in m.name), 100)
        nt = m.node_tree
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        if es.is_linked:
            nt.links.new(es.links[0].from_socket, mul.inputs[0])
        else:
            mul.inputs[0].default_value = es.default_value
        nt.links.new(mul.outputs[0], es)
        mul.inputs[1].default_value = 0.0
        mul.inputs[1].keyframe_insert("default_value", frame=f0)
        mul.inputs[1].default_value = 1.0
        mul.inputs[1].keyframe_insert("default_value", frame=f0 + RAMP)
    # volumetrics: haze and rain fade in at the end
    if haze:
        haze.hide_render = False
        pv = next(nd for nd in haze.active_material.node_tree.nodes if nd.type == "PRINCIPLED_VOLUME")
        dens = pv.inputs["Density"]
        d = dens.default_value
        dens.default_value = 0.0
        dens.keyframe_insert("default_value", frame=176)
        dens.default_value = d
        dens.keyframe_insert("default_value", frame=212)
    rain = bpy.data.materials.get("rain")
    if rain:
        b = rain.node_tree.nodes["Principled BSDF"]
        a = b.inputs["Alpha"]
        a.default_value = 0.0
        a.keyframe_insert("default_value", frame=176)
        a.default_value = 0.35
        a.keyframe_insert("default_value", frame=212)

out = os.path.join(OUT, "clips", clip + ("_clayplate" if CLAY_PLATE else ""))
os.makedirs(out, exist_ok=True)
for f in range(first, last + 1):
    path = os.path.join(out, f"{f:04d}.png")
    if os.path.exists(path):
        continue
    sc.frame_set(f)
    r.filepath = path
    bpy.ops.render.render(write_still=True)
    print("BTS", clip, f, flush=True)
