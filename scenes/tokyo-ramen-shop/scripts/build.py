"""Build the ramen shop .blend from scratch, optionally render previews.

blender -b --factory-startup --python scenes/tokyo-ramen-shop/scripts/build.py -- [--stages shell,dress,light,post] [--preview cam1,cam2]
        [--clay] [--samples 32] [--res 960] [--save] [--out scenes/tokyo-ramen-shop/out/prev]
"""
import argparse
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(__file__))
import lib  # noqa: E402
import shell  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--stages", default="shell,dress,passA,passB,passC,grime,r2gen,steam,light,post")
ap.add_argument("--preview", default="")
ap.add_argument("--clay", action="store_true")
ap.add_argument("--samples", type=int, default=32)
ap.add_argument("--res", type=int, default=960)
ap.add_argument("--save", action="store_true")
ap.add_argument("--out", default=os.path.join(lib.SCENE_DIR, "out", "prev"))
ap.add_argument("--tag", default="")
ap.add_argument("--blend", default="ramen_r2.blend", help="file name under scenes/tokyo-ramen-shop for --save")
ap.add_argument("--final", action="store_true", help="1920x1080, --samples, 16-bit PNG (for the saved .blend / stills)")
A = ap.parse_args(argv)
# Handheld clip: a slow step forward down the aisle toward the door, drifting toward the counter.
CLIP = dict(start=(0.8, 6.15, 1.52), end=(0.76, 5.35, 1.47), target=(1.5, 1.2, 1.02), lens=22, frames=120)
STAGES = A.stages.split(",")

CAMS = {
    # Wide hero from the back of the aisle toward the door, counter on the right (matches concept_wide).
    "wide": dict(loc=(0.78, 6.2, 1.5), target=(1.45, 0.6, 1.0), lens=20),
    # Seated at the counter, looking across the bowl into the kitchen pass (matches concept_detail).
    "counter": dict(loc=(0.82, 3.0, 1.36), target=(3.1, 4.6, 0.72), lens=24, focus=(1.45, 3.35, 0.95), fstop=4.0),
    # Overview for checking layout.
    "top": dict(loc=(1.8, 3.5, 9.0), target=(1.8, 3.5, 0), lens=18),
    "kitchen": dict(loc=(2.6, 0.8, 1.6), target=(3.0, 4.5, 0.9), lens=20),
    "door": dict(loc=(1.1, 2.4, 1.45), target=(1.4, -3.0, 1.3), lens=24),
}


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == "OPTIX"
    sc.cycles.device = "GPU"
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPTIX"
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = -0.12
    sc.render.fps = 24
    world = bpy.data.worlds.new("world")
    sc.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.004, 0.005, 0.007, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
    return sc


def add_camera(name, loc, target, lens, c):
    d = bpy.data.cameras.new(name)
    d.lens = lens
    d.sensor_width = 36
    d.clip_start = 0.02
    o = bpy.data.objects.new(name, d)
    c.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    o["target"] = target
    return o


def mirror_x(root):
    """Layout is authored with the counter on the camera's left; the concept has it on the right.
    Conjugate every top-level transform by an x-flip about the room centre: positions reflect, but each
    object stays a proper (non-mirrored) rotation, so printed text on props and planes still reads correctly."""
    M = Matrix.Translation((shell.W, 0, 0)) @ Matrix.Scale(-1, 4, (1, 0, 0))
    F = Matrix.Scale(-1, 4, (1, 0, 0))
    bpy.context.view_layer.update()  # matrix_world is stale on new objects until the depsgraph updates
    objs = [o for o in bpy.data.objects if o.parent is None]
    # Geometry authored in world space (origin at 0: noren panels, conduit, cables, noodles) would only be shifted,
    # because the conjugation mirrors origins, not vertices. Move those origins to their bounds centre first.
    for o in objs:
        if o.type in ("MESH", "CURVE") and o.location.length < 1e-6 and o.data and o.data.users == 1:
            bb = [Vector(c) for c in o.bound_box]
            ctr = sum(bb, Vector()) / 8
            if ctr.length > 1e-4:
                o.data.transform(Matrix.Translation(-ctr))
                o.location = ctr
    bpy.context.view_layer.update()
    for o in objs:
        o.matrix_world = M @ o.matrix_world @ F


def clay_override():
    m = lib.m_simple("CLAY", (0.5, 0.5, 0.5), 0.6)
    bpy.context.view_layer.material_override = m
    # Keep emitters and glass readable in clay: nothing else needed for a layout check.


def main():
    sc = reset()
    root = lib.coll("ramen")
    cshell = lib.coll("shell", root)
    if "shell" in STAGES:
        shell.build(cshell)
    spots = ()
    if "dress" in STAGES:
        import dress
        import validate
        dress.build(lib.coll("props", root))
        if "passA" in STAGES:
            dress.pass_a(lib.coll("props_a", root))
        validate.run(dress.PLACED, os.path.join(lib.SCENE_DIR, "out", "validate.txt"))
        if "passB" in STAGES or "passC" in STAGES:
            import clutter
            if "passB" in STAGES:
                clutter.pass_b(lib.coll("clutter_b", root))
            if "passC" in STAGES:
                clutter.pass_c(lib.coll("clutter_c", root))
        if "steam" in STAGES:
            import steam
            steam.build(lib.coll("fx", root), *dress.steam_sources())
    if "light" in STAGES:
        import lighting
        lighting.build(lib.coll("lights", root))
        import exterior
        exterior.build(lib.coll("exterior", root))
    ccam = lib.coll("cameras", root)
    for k, v in CAMS.items():
        add_camera("cam_" + k, v["loc"], v["target"], v["lens"], ccam)
    if "post" in STAGES:
        import post
        post.build()
    if "light" not in STAGES:
        # Neutral preview light so shell/dress passes are readable.
        lib.area("prev_key", lib.coll("lights", root), (1.8, 3.5, 2.5), (0, 0, 0), 3.0, 600, size_y=6)
        sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.05, 0.055, 1)
    mirror_x(root)
    import emitters
    emitters.run()
    emitters.no_volume_blur()
    if "grime" in STAGES:
        import grime
        grime.build()
    if "r2gen" in STAGES and "light" in STAGES:
        import r2gen
        r2gen.apply()  # round-2 generated props, decals and prints (post-mirror, world coordinates)
    # Cameras that need world-space targets are set up after the mirror (keyframes are not mirrored).
    import camera
    mx = lambda p: (shell.W - p[0], p[1], p[2])  # noqa: E731
    for k in ("wide", "counter"):
        focus = CAMS[k].get("focus", CAMS[k]["target"])
        camera.still_dof(bpy.data.objects["cam_" + k], mx(focus), fstop=CAMS[k].get("fstop", 2.8))
    clip = add_camera("cam_clip", mx(CLIP["start"]), mx(CLIP["target"]), CLIP["lens"], ccam)
    camera.handheld(clip, mx(CLIP["start"]), mx(CLIP["end"]), mx(CLIP["target"]), frames=CLIP["frames"], fstop=2.4)
    if A.clay:
        clay_override()
    if A.final:
        sc.cycles.samples = A.samples
        sc.cycles.adaptive_threshold = 0.02
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1920, 1080, 100
        sc.render.image_settings.file_format = "PNG"
        sc.render.image_settings.color_depth = "16"
    if A.save:
        path = os.path.join(lib.SCENE_DIR, A.blend)
        bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
        print("saved", path)
    if A.preview:
        os.makedirs(A.out, exist_ok=True)
        sc.cycles.samples = A.samples
        sc.render.resolution_x = A.res
        sc.render.resolution_y = int(A.res * 9 / 16)
        sc.render.resolution_percentage = 100
        for k in A.preview.split(","):
            sc.camera = bpy.data.objects["cam_" + k]
            if "ceiling" in bpy.data.objects:
                bpy.data.objects["ceiling"].hide_render = k == "top"
            sc.render.filepath = os.path.join(A.out, f"{k}{A.tag}.png")
            bpy.ops.render.render(write_still=True)
            print("rendered", sc.render.filepath)


main()
