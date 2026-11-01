"""Build the dai pai dong scene from scratch and save hk.blend (the .blend is a build output).

blender -b --factory-startup --python scenes/hk-dai-pai-dong/scripts/build.py -- [--stages shell,dress,validate,light,fx,post]
        [--save] [--out hk.blend] [--preview street,wok,table,top] [--clay] [--samples 32] [--engine cycles|eevee] [--tag _x]
Previews go to scenes/hk-dai-pai-dong/out/prev/<cam><tag>.png. Run through pipeline/gpu_run.sh, after gpu_prefs.py.
"""
import math
import os
import sys
import time

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shell  # noqa: E402
from lib import SCENE_DIR, coll  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


STAGES = arg("--stages", "shell,dress,validate,grime,light,fx,post").split(",")
PREVIEW = [p for p in arg("--preview", "").split(",") if p]
TAG = arg("--tag", "")

# Hero cameras: name -> (pos, aim, lens)
CAMS = {
    "street": ((4.6, -9.0, 1.6), (-2.2, 3.0, 1.9), 28),
    "wok": ((-1.55, 3.7, 1.3), (-2.8, 2.95, 0.68), 28),
    "table": ((0.45, -1.1, 1.1), (-2.4, 2.4, 0.9), 32),
    "walk": ((3.2, -5.5, 1.62), (-2.4, 2.6, 1.3), 24),
    "top": ((9.5, -9.0, 13.0), (-1.5, 2.8, 0.5), 24),
    "flame": ((-2.05, 2.15, 0.95), (-2.92, 2.55, 0.62), 35),
    "up": ((2.0, -4.0, 1.4), (-1.5, 6.0, 9.0), 20),
}


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    # read_factory_settings also resets user prefs, so select the OptiX device again (else Cycles renders on the CPU).
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == "OPTIX"
    sc.cycles.device = "GPU"
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 8
    sc.cycles.glossy_bounces = 4
    sc.cycles.transmission_bounces = 6
    sc.cycles.volume_bounces = 1
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.cycles.blur_glossy = 1.0
    sc.render.resolution_x, sc.render.resolution_y = 1920, 804
    sc.render.resolution_percentage = 100
    sc.render.fps = 24
    sc.frame_start, sc.frame_end = 1, 240
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = 0.0
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = 0.5
    sc.unit_settings.system = "METRIC"
    return sc


def add_camera(name, pos, aim, lens, c):
    d = bpy.data.cameras.new(name)
    d.lens = lens
    d.sensor_width = 24.89
    d.clip_start = 0.05
    d.clip_end = 600
    o = bpy.data.objects.new(name, d)
    c.objects.link(o)
    o.location = pos
    o.rotation_euler = (Vector(aim) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
    return o


def clay_override():
    m = bpy.data.materials.new("clay")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.6, 0.6, 0.6, 1)
    b.inputs["Roughness"].default_value = 0.7
    bpy.context.view_layer.material_override = m


def preview(names, clay, samples, engine):
    sc = bpy.context.scene
    od = os.path.join(SCENE_DIR, "out", "prev")
    os.makedirs(od, exist_ok=True)
    if clay:
        clay_override()
        # Clay under a soft sky so the layout reads (night lighting hides it).
        w = sc.world.node_tree.nodes["Background"]
        for l in list(w.inputs["Color"].links):
            sc.world.node_tree.links.remove(l)
        w.inputs["Color"].default_value = (0.55, 0.6, 0.7, 1)
        w.inputs["Strength"].default_value = 0.6
        sun = bpy.data.lights.new("clay_sun", "SUN")
        sun.energy = 2.5
        so = bpy.data.objects.new("clay_sun", sun)
        sc.collection.objects.link(so)
        so.rotation_euler = (math.radians(40), math.radians(15), math.radians(-35))
        for o in sc.objects:  # volumes and rain read as fog in clay
            if o.name.startswith(("steam", "haze", "rain", "drizzle")):
                o.hide_render = True
    sc.cycles.samples = samples
    sc.render.resolution_percentage = 50
    sc.render.use_motion_blur = False
    if engine == "eevee":
        sc.render.engine = "BLENDER_EEVEE"
    for n in names:
        sc.camera = bpy.data.objects["cam_" + n]
        sc.render.filepath = os.path.join(od, f"{n}{'_clay' if clay else ''}{TAG}.png")
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        print(f"PREVIEW {n} {time.time() - t0:.1f}s -> {sc.render.filepath}", flush=True)


def main():
    t0 = time.time()
    sc = reset()
    shell.build()
    cams = coll("cameras")
    for n, (p, a, l) in CAMS.items():
        add_camera("cam_" + n, p, a, l, cams)
    sc.camera = bpy.data.objects["cam_street"]
    if "dress" in STAGES:
        import dress
        dress.run()
        if "validate" in STAGES:
            import validate
            validate.resolve(dress.PLACED)
            validate.run(dress.PLACED, os.path.join(SCENE_DIR, "out", "validate.txt"))
    if "grime" in STAGES:
        import grime
        grime.build()
    if "light" in STAGES:
        import lights
        lights.build()
    if "fx" in STAGES:
        import fx
        fx.build()
    if "post" in STAGES:
        import post
        post.build()
    print(f"BUILD done in {time.time() - t0:.0f}s", flush=True)
    if "--save" in argv:
        out = os.path.join(SCENE_DIR, arg("--out", "hk.blend"))
        bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
        print("SAVED", out, flush=True)
    if PREVIEW:
        preview(PREVIEW, "--clay" in argv, int(arg("--samples", 32)), arg("--engine", "cycles"))


main()
