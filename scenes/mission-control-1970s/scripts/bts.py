"""Behind-the-scenes "dollhouse" clips (breakdown/SPEC.md), adapted from the repair scene's bts.py.

  blender -b scenes/mission-control-1970s/mc.blend --python .../bts.py -- setup
      -> breakdown/mission-control-1970s/bts.blend (copy + bts camera); never saves over a scene file
  blender -b breakdown/mission-control-1970s/bts.blend --python .../bts.py -- <a_layout|b_props|c_materials|d_lighting> [first last] [clay]
      -> breakdown/mission-control-1970s/clips/<clip>/####.png (existing frames skipped). Each run goes through gpu_run.sh.

One continuous 120° orbit around the room, A 0-30°, B 30-60°, C 60-90°, D 90-120° (ease in on A, out on D). The
camera stays on the back/left side so the wall display faces it the whole way; ceiling and the walls nearest the
camera are hidden per frame.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

ROOT = os.environ.get("ANYSCENE_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUT = os.path.join(ROOT, "breakdown", "mission-control-1970s")
W, D, H = 11.0, 13.0, 3.6
CENTRE = Vector((5.6, 6.9, 0.6))
AZ0 = -165.0
ELEV, DIST, LENS = 40.0, 19.0, 30.0
CLIPS = {"a_layout": (144, 0, 30, "in"), "b_props": (240, 30, 60, None),
         "c_materials": (144, 60, 90, None), "d_lighting": (240, 90, 120, "out")}
args = sys.argv[sys.argv.index("--") + 1:]
sc = bpy.context.scene

SHELL_COLLS = ("shell", "display", "furniture")
PROP_COLLS = ("consoles", "chairs", "furniture", "wall_items", "desk_props", "placards")
WALLS = {
    (-1, 0): ("wall_left", "sill", "mullion_", "transom", "window_glass", "blind", "poster_"),
    (1, 0): ("wall_right", "acoustic_right", "base_right"),
    (0, -1): ("wall_back", "door_", "exit_", "acoustic_back"),
    (0, 1): ("wall_front", "base_front"),
}


def coll_objs(names):
    out = []
    for n in names:
        c = bpy.data.collections.get(n)
        if c:
            out += list(c.all_objects)
    return out


def azimuth(clip, f):
    n, a0, a1, ease = CLIPS[clip]
    u = (f - 1) / (n - 1)
    if ease == "in":
        u = 2 * u * u - u ** 3
    elif ease == "out":
        u = u + u * u - u ** 3
    return AZ0 + a0 + (a1 - a0) * u


def cam_pose(az):
    a, e = math.radians(az), math.radians(ELEV)
    p = CENTRE + Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e))) * DIST
    return p, (CENTRE - p).to_track_quat("-Z", "Y").to_euler()


if args[0] == "setup":
    cd = bpy.data.cameras.new("bts_cam")
    cd.lens, cd.sensor_width, cd.sensor_fit = LENS, 36.0, "HORIZONTAL"
    cd.shift_y = -0.1  # room sits a little high: the bottom 140 px stay clear for captions
    cd.dof.use_dof = False
    cd.clip_end = 200
    cam = bpy.data.objects.new("bts_cam", cd)
    sc.collection.objects.link(cam)
    os.makedirs(OUT, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "bts.blend"), copy=True)
    print("BTS setup saved")
    sys.exit(0)

clip = args[0]
n = CLIPS[clip][0]
first, last = (int(args[1]), int(args[2])) if len(args) > 2 else (1, n)
CLAY_PLATE = len(args) > 3 and args[3] == "clay"
cam = bpy.data.objects["bts_cam"]
sc.camera = cam
sc.frame_start, sc.frame_end = 1, n
r = sc.render
r.resolution_x, r.resolution_y, r.resolution_percentage = 1920, 1080, 100
r.fps = 24
r.use_motion_blur = False
r.use_compositing = False
r.image_settings.file_format = "PNG"
r.image_settings.color_mode = "RGB"
r.image_settings.color_depth = "8"
r.film_transparent = False
for f in range(1, n + 1):
    p, rot = cam_pose(azimuth(clip, f))
    cam.location, cam.rotation_euler = p, rot
    cam.keyframe_insert("location", frame=f)
    cam.keyframe_insert("rotation_euler", frame=f)

props = {o for o in coll_objs(PROP_COLLS) if o.get("placed") or o.parent is None and o.name.startswith(("placard", "poster", "exit_text"))}
props = {o for o in props if not o.name.startswith(("coffee_table",))}
shell = set(coll_objs(SHELL_COLLS)) - props
ceiling = set(coll_objs(("ceiling_fixtures",))) | {sc.objects["ceiling"]}
outside = set(coll_objs(("outside",)))
haze = [o for o in coll_objs(("haze",))]
lights = [o for o in sc.objects if o.type == "LIGHT"]
decals = set(coll_objs(("decals",)))
for o in sc.objects:
    if o.type in ("MESH", "CURVE", "FONT", "LIGHT"):
        o.hide_render = False
for o in ceiling | outside:
    o.hide_render = True


def wall_objs(normal):
    pre = WALLS[normal]
    objs = [o for o in sc.objects if o.name.startswith(pre)]
    nx, ny = normal
    for o in props:  # wall-hung props go with their wall
        if not o.get("wall"):
            continue
        x, y = o.matrix_world.translation.x, o.matrix_world.translation.y
        if (nx < 0 and x < 0.5) or (nx > 0 and x > W - 0.5) or (ny < 0 and y < 0.5) or (ny > 0 and y > D - 0.5):
            objs.append(o)
    return objs


cut = {k: wall_objs(k) for k in WALLS}
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
    for o in lights:
        o.hide_render = True
    for o in haze:
        o.hide_render = True
    w = sc.world
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.75, 0.77, 0.8, 1)
    bg.inputs["Strength"].default_value = 0.5 if clay else 0.45
    ld = bpy.data.lights.new("bts_sun", "SUN")
    ld.energy, ld.angle = (1.6 if clay else 2.0), math.radians(12)
    s = bpy.data.objects.new("bts_sun", ld)
    sc.collection.objects.link(s)
    s.rotation_euler = (math.radians(38), math.radians(8), math.radians(-30))
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    r.engine = "BLENDER_EEVEE"
    ev = sc.eevee
    ev.taa_render_samples = 32
    ev.use_raytracing = True
    ev.use_shadows = True


def clay_override():
    m = bpy.data.materials.get("bts_clay") or bpy.data.materials.new("bts_clay")
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.62, 0.62, 0.6, 1)
    b.inputs["Roughness"].default_value = 0.7
    sc.view_layers[0].material_override = m


def emission_off_in_studio():
    """Screens and lamp glow would read as lit in the 'flat' materials pass; mute them (keyed multiplier = 0)."""
    for m in bpy.data.materials:
        if not m.node_tree:
            continue
        b = next((nd for nd in m.node_tree.nodes if nd.type == "BSDF_PRINCIPLED"), None)
        if b is None:
            continue
        es = b.inputs["Emission Strength"]
        if es.is_linked:
            nt = m.node_tree
            mul = nt.nodes.new("ShaderNodeMath")
            mul.operation = "MULTIPLY"
            nt.links.new(es.links[0].from_socket, mul.inputs[0])
            mul.inputs[1].default_value = 0.15
            nt.links.new(mul.outputs[0], es)
        else:
            es.default_value *= 0.15


if clip == "a_layout":
    studio(True)
    clay_override()
    for o in props | decals:
        o.hide_render = True
    risers = [o for o in shell if o.parent is None and o.name.startswith(("floor_t1", "floor_t2", "step", "nosing", "display", "coffee_table"))]
    risers.sort(key=lambda o: -o.location.y)
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
    for o in decals:
        o.hide_render = True
    order = sorted(props, key=lambda o: (o.get("order", 10 ** 6) if o.get("placed") else 10 ** 5 + len(o.name)))
    # big furniture first is already the dressing order (consoles, chairs, room furniture, wall items, desks)
    span = 194
    for i, o in enumerate(order):
        f0 = 1 + int(span * (i / max(1, len(order) - 1)) ** 1.25)
        for fr, s in ((f0, 0.0), (f0 + 4, 1.12), (f0 + 6, 0.97), (f0 + 8, 1.0)):
            o.delta_scale = (s, s, s)
            o.keyframe_insert("delta_scale", frame=fr)

elif clip == "c_materials" and CLAY_PLATE:
    studio(True)
    clay_override()
    for o in decals:
        o.hide_render = True

elif clip == "c_materials":
    studio(False)
    emission_off_in_studio()
    for m in bpy.data.materials:
        if not m.node_tree:
            continue
        for nd in m.node_tree.nodes:
            if nd.type == "GROUP" and nd.node_tree and nd.node_tree.name == "grime_layer":
                s = nd.inputs["Factor"]
                v = s.default_value
                s.default_value = 0.0
                s.keyframe_insert("default_value", frame=48)
                s.default_value = v
                s.keyframe_insert("default_value", frame=96)
    for m in bpy.data.materials:
        if m.name.startswith(("decal_",)) and m.node_tree:
            a = m.node_tree.nodes.get("decal_alpha")
            if a:
                v = a.inputs[1].default_value
                a.inputs[1].default_value = 0.0
                a.inputs[1].keyframe_insert("default_value", frame=48)
                a.inputs[1].default_value = v
                a.inputs[1].keyframe_insert("default_value", frame=96)

elif clip == "d_lighting":
    r.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for dv in prefs.devices:
        dv.use = dv.type == "OPTIX"
    c = sc.cycles
    c.device = "GPU"
    c.samples = 16
    c.use_adaptive_sampling = True
    c.adaptive_threshold = 0.05
    c.use_denoising = True
    c.denoiser = "OPTIX"
    c.max_bounces = 4
    c.diffuse_bounces, c.glossy_bounces, c.transmission_bounces = 2, 2, 4
    c.volume_step_rate = 8.0
    r.use_persistent_data = True
    sc.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.3
    RAMP = 10
    # light_order groups (lights.py): 1 lamps, 2 troffers, 3 display spill, 4 pad spill, 5 accents, 6 fills
    START = {1: 10, 2: 88, 3: 66, 4: 112, 5: 100, 6: 140}
    for o in lights:
        g = int(o.get("light_order", 600)) // 100
        f0 = START.get(g, 150) + (int(o.get("light_order", 0)) % 100) % 6 * 3 if g == 1 else START.get(g, 150)
        e = o.data.energy
        o.data.energy = 0.0
        o.data.keyframe_insert("energy", frame=f0)
        o.data.energy = e
        o.data.keyframe_insert("energy", frame=f0 + RAMP)
    # emissive materials: CRTs + console lamps with the screens stage, wall display after, troffer lenses with the
    # tubes, exit + backdrop with accents/outside
    EMIT = (("CRT_SLOT", 44), ("wall_wall", 66), ("troffer_", 88), ("exit_", 100), ("backdrop", 112))
    for m in bpy.data.materials:
        if not m.node_tree:
            continue
        b = next((nd for nd in m.node_tree.nodes if nd.type == "BSDF_PRINCIPLED"), None)
        if b is None:
            continue
        es = b.inputs["Emission Strength"]
        if not es.is_linked and es.default_value <= 0:
            continue
        f0 = next((v for k, v in EMIT if m.name.startswith(k)), 44)
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
    # image-emission materials (backdrop) use an Emission Strength default > 0 handled above
    for o in haze:
        o.hide_render = False
        mt = o.active_material
        k = next((nd for nd in mt.node_tree.nodes if nd.type == "MATH" and nd.outputs[0].links
                  and nd.outputs[0].links[0].to_socket.name == "Density"), None)
        if k:
            d = k.inputs[1].default_value
            k.inputs[1].default_value = 0.0
            k.inputs[1].keyframe_insert("default_value", frame=176)
            k.inputs[1].default_value = d
            k.inputs[1].keyframe_insert("default_value", frame=212)

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
