"""Bake camrig shots to per-frame camera JSON in Unreal space (for an exact Cycles <-> Unreal camera match).

    blender -b scenes/hk-dai-pai-dong/hk.blend --python unreal_demo/bake_cams.py -- \
        --shots scenes/hk-dai-pai-dong/shots.json --only h1_walk_in_to_wok,s1_street_crane --out unreal_demo/cams

Builds each rig exactly as the finals were rendered (render_finals.sh calls shoot.py with --only <shot>, so every
shot was built with seed 0), evaluates the camera per frame (base path, Track To aim, handheld noise / walk bake, roll,
lens, f-stop, focus empty) and writes <out>/<shot>.json. Frames 0 and N+1 are included so motion-blur subframes in
Unreal have keys on both sides of the shot. Never saves the .blend.

Conventions are export_blend.py's: Blender (x, y, z) m -> Unreal (x, -y, z) * 100; the camera's forward (-Z local)
and up (+Y local) are flipped the same way and turned into a rotator in Unreal with make_rot_from_xz.
Focus distance is the depth of the focus empty along the view axis (what Blender's DOF uses; Unreal's manual focus
distance is also a plane distance).
"""
import argparse
import json
import math
import os
import sys

import bpy
from mathutils import Vector

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "camera"))
import camrig  # noqa: E402

a = argparse.ArgumentParser()
a.add_argument("--shots", required=True)
a.add_argument("--only", required=True)
a.add_argument("--out", required=True)
a.add_argument("--seed", type=int, default=0)
args = a.parse_args(sys.argv[sys.argv.index("--") + 1:])

cfg = json.load(open(args.shots, encoding="utf-8"))
only = [x for x in args.only.split(",") if x]
shots = {s["name"]: camrig.merged(cfg.get("defaults", {}), s) for s in cfg["shots"]}
os.makedirs(args.out, exist_ok=True)
sc = bpy.context.scene


def flip(v):
    return [v[0], -v[1], v[2]]


for name in only:
    s = shots[name]
    cam = camrig.build(s, seed=args.seed)
    w, h = camrig.res_for(s)
    n = int(s.get("frames", 120))
    fps = int(s.get("fps", 24))
    cd = cam.data
    sw = cd.sensor_width
    frames = []
    for f in range(0, n + 2):
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        ce = cam.evaluated_get(dg)
        mw = ce.matrix_world.copy()
        r = mw.to_3x3().normalized()
        fwd = r @ Vector((0, 0, -1))
        up = r @ Vector((0, 1, 0))
        pos = mw.translation
        cde = ce.data
        foc_cm = None
        if cde.dof.use_dof and cde.dof.focus_object:
            fo = cde.dof.focus_object.evaluated_get(dg)
            foc_cm = abs((fo.matrix_world.translation - pos).dot(fwd)) * 100
        frames.append({
            "blender_frame": f,
            "matrix_world": [list(row) for row in mw],
            "loc": [pos.x * 100, -pos.y * 100, pos.z * 100],
            "forward": flip(fwd), "up": flip(up),
            "lens_mm": cde.lens, "fstop": cde.dof.aperture_fstop if cde.dof.use_dof else 22.0,
            "focus_cm": foc_cm,
        })
    out = {"shot": name, "fps": fps, "frames_n": n, "res": [w, h], "sensor_width_mm": sw,
           "sensor_height_mm": sw * h / w, "dof": bool(cd.dof.use_dof), "seed": args.seed,
           "shutter_deg": float(s.get("shutter", 180)), "frames": frames}
    p = os.path.join(args.out, name + ".json")
    json.dump(out, open(p, "w"), indent=0)
    f1 = frames[1]
    print(f"BAKE {name}: {n} f @ {fps} fps, {w}x{h}, sensor {sw:.2f} mm, lens {f1['lens_mm']:.1f}, "
          f"focus {f1['focus_cm']}, f/{f1['fstop']:.1f} -> {p}", flush=True)
print("BAKE done", flush=True)
