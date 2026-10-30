"""Run as the first --python: Cycles device prefs live in user preferences, not the .blend, so a plain
`blender -b scene.blend` renders on the CPU. Select OptiX GPUs and set the scene to GPU."""
import bpy

prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "OPTIX"
prefs.get_devices()
for d in prefs.devices:
    d.use = d.type == "OPTIX"
for sc in bpy.data.scenes:
    sc.cycles.device = "GPU"
print("gpu_prefs:", [d.name for d in prefs.devices if d.use], flush=True)
