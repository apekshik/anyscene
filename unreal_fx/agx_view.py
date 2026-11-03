"""Apply a Blender view transform (default AgX + the scene's look) to Unreal scene-linear EXRs (MRQ_Linear output),
so UE and Cycles frames can be compared through the same tone mapper.
    blender -b --factory-startup --python agx_view.py -- <in.exr> <out.png> [look] [exposure]
"""
import sys
import bpy

a = sys.argv[sys.argv.index("--") + 1:]
src, dst = a[0], a[1]
look = a[2] if len(a) > 2 else "AgX - Medium High Contrast"
expo = float(a[3]) if len(a) > 3 else 0.0
sc = bpy.context.scene
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = look
sc.view_settings.exposure = expo
sc.render.image_settings.file_format = "PNG"
img = bpy.data.images.load(src)
img.save_render(dst, scene=sc)
print("AGX", src, "->", dst, flush=True)
