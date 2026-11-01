"""Hide the ashtray smoke curls (run before camera/shoot.py). The curls sit inside the room haze; overlapping volumes
cost ~21 s/frame against ~7 s with either alone, and only the push-in onto the hero ashtray needs them."""
import bpy

for o in bpy.data.objects:
    if o.name.startswith("smoke_curl"):
        o.hide_render = True
