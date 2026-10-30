"""Glowing textures on dense generated meshes (ticket machine, fridge, lantern) turned every triangle into a light:
a 545k-emitter light tree took ~290 s of sync per frame. Their light comes from area/point lights anyway, so
emissive materials on meshes over 2k triangles stop being sampled as lights (they still glow to the camera)."""
import bpy


def _emissive(m):
    if not m or not m.node_tree:
        return False
    for n in m.node_tree.nodes:
        if n.type == "EMISSION":
            return True
        if n.type == "BSDF_PRINCIPLED":
            s = n.inputs["Emission Strength"]
            if s.is_linked or s.default_value > 0:
                c = n.inputs["Emission Color"]
                if c.is_linked or any(v > 0 for v in c.default_value[:3]):
                    return True
    return False


def run(min_tris=2000):
    done = []
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        if sum(len(p.vertices) - 2 for p in o.data.polygons) < min_tris:
            continue
        for m in o.data.materials:
            if _emissive(m) and m.cycles.emission_sampling != "NONE":
                m.cycles.emission_sampling = "NONE"  # lives on m.cycles in 5.0
                done.append(m.name)
    print("emitters: sampling off for", done, flush=True)
    return done


if __name__ == "__main__":
    run()
    bpy.ops.wm.save_mainfile()


def no_volume_blur():
    """Object motion blur on the Mantaflow domains makes Cycles build velocity motion from the noise grids:
    ~290 s of sync per frame. Camera blur stays; the steam itself just isn't motion-blurred."""
    for o in bpy.data.objects:
        if any(m.type == "FLUID" and m.fluid_type == "DOMAIN" for m in o.modifiers):
            o.cycles.use_motion_blur = False
            print("emitters: no motion blur on", o.name, flush=True)
