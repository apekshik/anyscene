"""Make a scene .blend self-contained for the render farm (run inside Blender, never on the working file in place).

    blender -b scene.blend --python farm/pack.py -- <out.blend>

Packs images, fonts, sounds and volumes into the file, makes linked library data local, and refuses to write the
bundle if anything still points outside it (fluid/particle caches have to be shipped next to the .blend instead; the
script prints them). The input file is never saved.
"""

import os
import sys

import bpy

out = sys.argv[sys.argv.index("--") + 1]

if bpy.data.libraries:
    print("pack: making linked data local from", [l.filepath for l in bpy.data.libraries])
    bpy.ops.object.make_local(type="ALL")

bpy.ops.file.pack_all()

problems = []
for mod_owner in bpy.data.objects:
    for m in mod_owner.modifiers:
        if m.type == "FLUID" and m.fluid_type == "DOMAIN":
            problems.append(f"fluid cache {mod_owner.name}: {bpy.path.abspath(m.domain_settings.cache_directory)}")
for img in bpy.data.images:
    if img.source in {"FILE", "SEQUENCE", "TILED"} and not img.packed_file and img.filepath and img.users:
        problems.append(f"image not packed: {img.name} -> {img.filepath}")
for v in bpy.data.volumes:
    if not v.packed_file and v.filepath:
        problems.append(f"volume not packed: {v.name} -> {v.filepath}")
for lib in bpy.data.libraries:
    problems.append(f"library still linked: {lib.filepath}")

print("pack: external paths left:", len(problems))
for p in problems:
    print("pack:   ", p)
if any(not p.startswith("fluid cache") for p in problems):
    sys.exit(1)

os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out), copy=True, compress=True)
print("pack: wrote", out, f"{os.path.getsize(out) / 1e6:.0f} MB")
