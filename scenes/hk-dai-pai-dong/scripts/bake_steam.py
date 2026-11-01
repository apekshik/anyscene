"""Bake the Mantaflow steam domains of scenes/tokyo-ramen-shop/ramen.blend (CPU) and save the .blend.

blender -b scenes/tokyo-ramen-shop/ramen.blend --python scenes/tokyo-ramen-shop/scripts/bake_steam.py -- [--res-scale 1.0] [--end 150] [--only steam_bowl]
"""
import os
import shutil
import sys
import time

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
scale = float(argv[argv.index("--res-scale") + 1]) if "--res-scale" in argv else 1.0
end = int(argv[argv.index("--end") + 1]) if "--end" in argv else None
only = argv[argv.index("--only") + 1].split(",") if "--only" in argv else None

for o in bpy.data.objects:
    mod = next((m for m in o.modifiers if m.type == "FLUID" and m.fluid_type == "DOMAIN"), None)
    if not mod or (only and o.name not in only):
        continue
    ds = mod.domain_settings
    if scale != 1.0:
        ds.resolution_max = max(24, int(ds.resolution_max * scale))
    if end is not None:
        ds.cache_frame_end = end
    # free_all runs as an async job that would delete the new cache after the bake, so clear the folder directly.
    shutil.rmtree(bpy.path.abspath(ds.cache_directory), ignore_errors=True)
    t0 = time.time()
    with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o]):
        r = bpy.ops.fluid.bake_all()
    print(f"BAKE {o.name} res {ds.resolution_max} frames {ds.cache_frame_start}..{ds.cache_frame_end} {r} in {time.time() - t0:.0f}s", flush=True)
bpy.ops.wm.save_mainfile()
print("SAVED", bpy.data.filepath)
