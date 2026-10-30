"""Compositor (Blender 5.0 node-group compositor): glare + lens distortion with chromatic aberration.
Grade, vignette and grain happen afterwards in scenes/tokyo-ramen-shop/scripts/finish.sh (ffmpeg), so they can be tuned without re-rendering."""
import bpy


def _set(n, name, v):
    s = n.inputs.get(name)
    if s is None:
        raise KeyError(f"{n.bl_idname} has no input {name}: {[i.name for i in n.inputs]}")
    s.default_value = v


def build(glare=0.12, distortion=-0.015, dispersion=0.01):
    sc = bpy.context.scene
    t = bpy.data.node_groups.new("ramen_post", "CompositorNodeTree")
    t.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    N, Lk = t.nodes, t.links.new
    rl = N.new("CompositorNodeRLayers")
    out = N.new("NodeGroupOutput")
    g = N.new("CompositorNodeGlare")
    _set(g, "Type", "Fog Glow")
    _set(g, "Quality", "High")
    _set(g, "Threshold", 1.0)
    _set(g, "Strength", glare)
    Lk(rl.outputs["Image"], g.inputs["Image"])
    ld = N.new("CompositorNodeLensdist")
    _set(ld, "Distortion", distortion)
    _set(ld, "Dispersion", dispersion)
    try:
        _set(ld, "Fit", True)
    except Exception:
        pass
    Lk(g.outputs["Image"], ld.inputs["Image"])
    Lk(ld.outputs["Image"], out.inputs["Image"])
    sc.compositing_node_group = t
    sc.render.use_compositing = True
    return t
