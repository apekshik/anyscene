"""Stills from the hero cameras of a built .blend (run with gpu_prefs.py first for Cycles).

blender -b mc.blend --python gpu_prefs.py --python preview.py -- --cams cam_a,cam_b [--engine cycles|eevee|workbench]
    [--samples 32] [--pct 50] [--tag x] [--exposure 0]
-> scenes/mission-control-1970s/out/prev/<tag>_<cam>.png
"""
import argparse
import os
import sys

import bpy

ROOT = os.environ.get("ANYSCENE_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUT = os.path.join(ROOT, "scenes", "mission-control-1970s", "out", "prev")
ap = argparse.ArgumentParser()
ap.add_argument("--cams", default="cam_back_wide,cam_row_a,cam_windows,cam_printer,cam_display")
ap.add_argument("--engine", default="cycles")
ap.add_argument("--samples", type=int, default=32)
ap.add_argument("--pct", type=int, default=50)
ap.add_argument("--tag", default="p")
ap.add_argument("--exposure", type=float, default=None)
a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
sc = bpy.context.scene
sc.render.resolution_percentage = a.pct
if a.exposure is not None:
    sc.view_settings.exposure = a.exposure
if a.engine == "eevee":
    sc.render.engine = "BLENDER_EEVEE"
    sc.eevee.taa_render_samples = a.samples
elif a.engine == "workbench":
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "MATERIAL"
    sc.display.shading.show_cavity = True
    sc.display.shading.show_shadows = True
    sc.view_settings.view_transform = "Standard"
else:
    sc.cycles.samples = a.samples
os.makedirs(OUT, exist_ok=True)
for c in a.cams.split(","):
    sc.camera = bpy.data.objects[c]
    sc.render.filepath = os.path.join(OUT, f"{a.tag}_{c}.png")
    bpy.ops.render.render(write_still=True)
    print("PREVIEW", sc.render.filepath, flush=True)
