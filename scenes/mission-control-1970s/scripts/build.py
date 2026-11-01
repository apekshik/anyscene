"""Mission control 1970s: the whole scene build, in stages.

blender -b --factory-startup --python scenes/mission-control-1970s/scripts/build.py -- \
    [--stages shell,dress,screens,lights,haze,post] [--save scenes/mission-control-1970s/mc.blend] [--clay]
Coordinates: x across (0 = window wall), y from the back door (0) to the wall display (13), z up. Metres.
Every stage is a function in a module next to this file; the .blend is a build output, never hand-edited.
"""
import argparse
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--stages", default="shell,dress,screens,grime,lights,haze,post")
ap.add_argument("--save", default=os.path.join(lib.ROOT, "scenes", "mission-control-1970s", "mc.blend"))
ap.add_argument("--clay", action="store_true")
ap.add_argument("--dress-passes", default="furniture,heroes,mid,clutter")
args = ap.parse_args(argv)
stages = args.stages.split(",")

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.unit_settings.system = "METRIC"

import shell  # noqa: E402

shell.build()
if "dress" in stages:
    import dress  # noqa: E402
    dress.build(args.dress_passes.split(","))
    import validate  # noqa: E402
    validate.check(resolve=True)
if "screens" in stages:
    import fixscreens  # noqa: E402
    fixscreens.build()
if "grime" in stages:
    import grime  # noqa: E402
    grime.build()
if "lights" in stages:
    import lights  # noqa: E402
    lights.build()
if "haze" in stages:
    import haze  # noqa: E402
    haze.build()
import post  # noqa: E402
post.build(clay=args.clay)
bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.save))
print("SAVED", args.save, flush=True)
