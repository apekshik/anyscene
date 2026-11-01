"""Render settings and the light compositor (Glare only; the grade is ffmpeg, see grade.sh).
Also turns off light-sampling on emissive dense generated meshes."""
import bpy

import emitters


def build():
    sc = bpy.context.scene
    sc.cycles.samples = 56
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPTIX"
    sc.cycles.volume_step_rate = 4.0      # haze/steam: coarser steps, fine at 48-64 spp with the denoiser
    sc.cycles.volume_preview_step_rate = 4.0
    sc.cycles.volume_max_steps = 256
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = 0.5
    emitters.run()
    emitters.no_volume_blur()
    # Compositor: glare (fog glow) on the bulbs and neon.
    tree = bpy.data.node_groups.new("hk_comp", "CompositorNodeTree")
    sc.compositing_node_group = tree
    rl = tree.nodes.new("CompositorNodeRLayers")
    gl = tree.nodes.new("CompositorNodeGlare")
    try:
        gl.inputs["Type"].default_value = "Fog Glow"
    except Exception:
        gl.glare_type = "FOG_GLOW"
    for k, v in (("Threshold", 1.2), ("Strength", 0.35), ("Size", 0.6)):
        if k in gl.inputs:
            gl.inputs[k].default_value = v
    out = tree.nodes.new("NodeGroupOutput")
    tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    tree.links.new(rl.outputs["Image"], gl.inputs["Image"])
    tree.links.new(gl.outputs["Image"], out.inputs[0])
    print("POST done", flush=True)
