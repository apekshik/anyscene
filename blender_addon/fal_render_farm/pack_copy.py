"""Run by the add-on in a separate background Blender, on a temporary copy of the user's file (never the file itself):

    blender -b --factory-startup <copy.blend> --python pack_copy.py -- <out.blend>

Makes linked library data local, packs images/fonts/sounds/volumes, and refuses (exit 2) if anything the render
needs still points outside the file, listing each path on a "PACK-PROBLEM:" line.
"""

import os
import sys

import bpy

out = sys.argv[sys.argv.index("--") + 1]

if bpy.data.libraries:
    print("PACK-INFO: making linked data local:", ", ".join(l.filepath for l in bpy.data.libraries))
    try:
        bpy.ops.object.make_local(type="ALL")
    except RuntimeError as e:
        print("PACK-INFO: make_local:", e)

try:
    bpy.ops.file.pack_all()
except RuntimeError as e:  # missing files: reported below as problems
    print("PACK-INFO: pack_all:", str(e).strip())

problems, warnings = [], []
for img in bpy.data.images:
    if img.users and img.source in {"FILE", "SEQUENCE", "TILED", "MOVIE"} and not img.packed_file and img.filepath:
        problems.append(f"image not packed ({img.source.lower()}): {img.name} -> {img.filepath}")
for v in bpy.data.volumes:
    if v.users and not v.packed_file and v.filepath:
        problems.append(f"volume not packed: {v.name} -> {v.filepath}")
for c in bpy.data.cache_files:
    if c.users:
        problems.append(f"cache file (Alembic/USD) can't be packed: {c.name} -> {c.filepath}")
for lib in bpy.data.libraries:
    problems.append(f"library still linked: {lib.filepath}")
for ob in bpy.data.objects:
    for m in ob.modifiers:
        if m.type == "FLUID" and m.fluid_type == "DOMAIN":
            warnings.append(f"fluid domain {ob.name}: its disk cache is not shipped "
                            f"({bpy.path.abspath(m.domain_settings.cache_directory)})")

for w in warnings:
    print("PACK-WARNING:", w)
for p in problems:
    print("PACK-PROBLEM:", p)
if problems:
    sys.exit(2)

bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out), copy=True, compress=True)
print("PACK-OK:", os.path.getsize(out))
