"""Install the built extension zip the way a user would, into a throwaway user profile, and check it registers.

    BLENDER_USER_RESOURCES=<empty temp dir> blender -b --factory-startup --python-exit-code 1 \
        --python test_zip_install.py -- blender_addon/fal_render_farm-1.0.0.zip
"""

import os
import sys

import bpy

zip_path = os.path.abspath(sys.argv[sys.argv.index("--") + 1])
ext_dir = bpy.utils.user_resource("EXTENSIONS")
assert os.environ.get("BLENDER_USER_RESOURCES") and os.path.normcase(os.path.abspath(ext_dir)).startswith(os.path.normcase(os.path.abspath(os.environ["BLENDER_USER_RESOURCES"]))), \
    f"refusing to install into the real profile ({ext_dir})"
print("ZIP-TEST extensions dir:", ext_dir)

res = bpy.ops.extensions.package_install_files(repo="user_default", filepath=zip_path, enable_on_install=True)
print("ZIP-TEST install:", res)
name = "bl_ext.user_default.fal_render_farm"
assert name in bpy.context.preferences.addons, list(bpy.context.preferences.addons.keys())
prefs = bpy.context.preferences.addons[name].preferences
assert prefs.app_id == "" and prefs.chunk_size == 24 and prefs.concurrency == 100, "defaults"
assert hasattr(bpy.types, "FALRF_PT_panel"), "panel not registered"
assert bpy.ops.fal_render_farm.render.poll(), "render op poll"
assert not bpy.ops.fal_render_farm.cancel.poll(), "cancel op poll"
print("ZIP-TEST OK: installed and enabled as", name, "with defaults", prefs.app_id, prefs.chunk_size, prefs.concurrency)
