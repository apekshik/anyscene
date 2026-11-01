"""Enable OptiX for this Blender session; chain before another script: --python gpu_prefs.py --python shoot.py -- ..."""
import bpy
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "OPTIX"
prefs.get_devices()
for d in prefs.devices:
    d.use = d.type == "OPTIX"
for sc in bpy.data.scenes:
    sc.cycles.device = "GPU"
print("gpu_prefs: OPTIX on", [d.name for d in prefs.devices if d.use])
