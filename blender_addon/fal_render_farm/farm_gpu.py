"""Shipped in every bundle and run with --python before the render: headless Blender on the farm would otherwise
render Cycles on the CPU. Picks OptiX (else CUDA), enables only those devices, and puts every scene on the GPU now,
on file load and at render start. Nothing else about the scene is touched. (Same idea as builder/blender_gpu.py.)"""

import bpy
from bpy.app.handlers import persistent


def _devices():
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
    except (KeyError, AttributeError):
        return "no cycles"
    for kind in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
        except TypeError:
            continue
        if any(d.type == kind for d in prefs.devices):
            for d in prefs.devices:
                d.use = d.type == kind
            return kind
    return "none"


@persistent
def _gpu_scenes(*_):
    for sc in bpy.data.scenes:
        sc.cycles.device = "GPU"


print("fal-farm: compute device", _devices())
_gpu_scenes()
bpy.app.handlers.load_post.append(_gpu_scenes)
bpy.app.handlers.render_init.append(_gpu_scenes)
