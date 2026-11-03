"""Make a working copy of a scene .blend with all external paths absolute (a plain file copy breaks the scene's
//../../refs/... texture paths as soon as it lives in another folder). The source file is only read.
    blender -b scenes/<id>/<scene>.blend --python unreal/make_copy.py -- <out.blend>
"""
import sys
import bpy

out = sys.argv[sys.argv.index("--") + 1]
assert bpy.path.abspath(out) != bpy.data.filepath, "refusing to overwrite the source .blend"
bpy.ops.file.make_paths_absolute()
bpy.ops.wm.save_as_mainfile(filepath=out, copy=True, relative_remap=False, compress=False)
print("COPY", bpy.data.filepath, "->", out, flush=True)
