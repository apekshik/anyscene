"""Steam and vapor (design coordinates; build.py mirrors afterwards, the bake runs on the saved .blend).

Mantaflow gas domains:
  steam_range   over the range + noodle boiler, under the hood (hood is a collision effector, open top)
  steam_bowl    a small one over the unfinished bowl on the counter
Emitters are hidden discs just below each rim; flow density is broken up by an animated clouds texture so the
plumes come out in wisps instead of a solid column. Bake with scenes/tokyo-ramen-shop/scripts/bake_steam.py (CPU, cache in
scenes/tokyo-ramen-shop/cache/). The cache starts at PREROLL so plumes are fully developed at frame 1 (shots render 1..N).

Plus kitchen_vapor: a drifting low-density noise volume in the kitchen that the pendants and hood strip pick up."""
import math
import os

import bpy

import shell as S
from lib import L, SCENE_DIR, mathn, new_mat, noise, texcoord

PREROLL = -70
END = 300  # covers the ~11 s handheld walkthroughs
CACHE = os.path.join(SCENE_DIR, "cache", "r2")  # round 2; round-1 caches stay in cache/


def _box_mesh(name, lo, hi, c):
    bpy.ops.mesh.primitive_cube_add(size=1)
    o = bpy.context.object
    o.name = name
    for uc in list(o.users_collection):
        uc.objects.unlink(o)
    c.objects.link(o)
    o.scale = [hi[i] - lo[i] for i in range(3)]
    o.location = [(hi[i] + lo[i]) / 2 for i in range(3)]
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return o


def steam_material(name="steam_vol", density=8.0):
    m, nt = new_mat(name)
    if nt:
        nt.nodes.remove(nt.nodes["Principled BSDF"])
        v = nt.nodes.new("ShaderNodeVolumePrincipled")
        v.inputs["Color"].default_value = (0.92, 0.92, 0.92, 1)
        v.inputs["Density"].default_value = density
        v.inputs["Density Attribute"].default_value = "density"
        v.inputs["Anisotropy"].default_value = 0.55  # forward scatter: glows when backlit by the hood strip
        L(nt, v.outputs[0], nt.nodes["Material Output"].inputs["Volume"])
    return m


def _domain(name, lo, hi, res, c, noise_scale=2):
    o = _box_mesh(name, lo, hi, c)
    mod = o.modifiers.new("Fluid", "FLUID")
    mod.fluid_type = "DOMAIN"
    ds = mod.domain_settings
    ds.domain_type = "GAS"
    ds.resolution_max = res
    ds.time_scale = 1.0
    ds.use_adaptive_timesteps = True
    ds.cfl_condition = 3.0
    ds.alpha = -0.15          # density sinks a little (steam is moist), heat carries it up
    ds.beta = 1.6
    ds.vorticity = 0.25
    ds.use_dissolve_smoke = True
    ds.dissolve_speed = 60
    ds.use_dissolve_smoke_log = True
    ds.use_collision_border_top = False
    ds.use_noise = True
    ds.noise_scale = noise_scale
    ds.noise_strength = 1.2
    ds.noise_pos_scale = 1.6
    ds.cache_type = "ALL"
    ds.cache_data_format = "OPENVDB"
    ds.cache_directory = os.path.join(CACHE, name)
    ds.cache_frame_start = PREROLL
    ds.cache_frame_end = END
    o.data.materials.append(steam_material())
    o.visible_shadow = False
    o.display_type = "WIRE"
    return o


def _clouds(name, size=0.06):
    t = bpy.data.textures.get(name) or bpy.data.textures.new(name, "CLOUDS")
    t.noise_scale = size
    t.noise_depth = 3
    t.contrast = 1.6
    return t


def _emitter(name, x, y, z, r, c, density=0.55, temp=2.0, tex=None, vel=0.25):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=0.012, vertices=24, location=(x, y, z))
    o = bpy.context.object
    o.name = name
    for uc in list(o.users_collection):
        uc.objects.unlink(o)
    c.objects.link(o)
    mod = o.modifiers.new("Fluid", "FLUID")
    mod.fluid_type = "FLOW"
    fs = mod.flow_settings
    fs.flow_type = "SMOKE"
    fs.flow_behavior = "INFLOW"
    fs.flow_source = "MESH"
    fs.surface_distance = 1.0  # effectively in cells: 0.012 only emitted from discs wide enough to contain cell centres
    fs.density = density
    fs.temperature = temp
    fs.smoke_color = (0.95, 0.95, 0.95)
    fs.subframes = 1
    fs.use_initial_velocity = True
    fs.velocity_normal = vel
    if tex:
        fs.use_texture = True
        fs.noise_texture = tex
        fs.texture_map_type = "AUTO"
        fs.texture_size = 1.0
        # Scroll the texture so the puffs change over time.
        d = fs.driver_add("texture_offset")
        d.driver.expression = "frame * 0.018"
    o.hide_render = True
    o.display_type = "WIRE"
    return o


def build(c, pots, boiler, bowl):
    """pots: [(x, y, rim_z, r)], boiler: (x, y, top_z, w, d) or None, bowl: (x, y, rim_z, r) or None."""
    tex = _clouds("steam_puffs")
    # Floor well below the pot rims (pots sit in the burner grates, rims ~0.76-0.9 m): emitters must not touch the border cells.
    dom = _domain("steam_range", (S.W - 0.85, 3.3, 0.6), (S.W - 0.015, 6.15, 2.25), 200, c)
    # Only pots on the range / back counter inside the domain steam (shelf and floor pots are cold).
    pots = [p for p in pots if S.W - 0.85 < p[0] and 3.3 < p[1] < 6.15 and p[2] < 1.6]
    for i, (x, y, z, r) in enumerate(pots):
        _emitter(f"steam_src_pot{i}", x, y, z - 0.03, r * 0.85, c, density=1.0 - 0.15 * i, temp=2.2, tex=tex)
    if boiler:
        x, y, z, w, d = boiler
        for j, dy in enumerate((-0.12, 0.12)):
            _emitter(f"steam_src_boiler{j}", x - 0.04, y + dy, z - 0.02, 0.11, c, density=0.8, temp=2.6, tex=tex, vel=0.4)
    # The hood is a collision object for the range domain (steam pools under it and rolls out the front).
    hood = bpy.data.objects.get("hood")
    if hood:
        m = hood.modifiers.new("Fluid", "FLUID")
        m.fluid_type = "EFFECTOR"
        m.effector_settings.effector_type = "COLLISION"
    if bowl:
        x, y, z, r = bowl
        _domain("steam_bowl", (x - 0.24, y - 0.24, z - 0.12), (x + 0.24, y + 0.24, z + 0.6), 110, c)
        _emitter("steam_src_bowl", x, y, z - 0.035, r * 0.7, c, density=0.6, temp=1.6, tex=_clouds("steam_puffs_bowl", 0.03), vel=0.08)
    kitchen_vapor(c)
    return dom


def kitchen_vapor(c, density=0.035):
    """Drifting vapor layer in the kitchen, thicker toward the hood and the ceiling."""
    m, nt = new_mat("kitchen_vapor")
    if nt:
        nt.nodes.remove(nt.nodes["Principled BSDF"])
        co = texcoord(nt, "Object")
        mp = nt.nodes.new("ShaderNodeMapping")
        L(nt, co, mp.inputs["Vector"])
        mp.inputs["Scale"].default_value = (1.0, 1.0, 1.6)
        n = noise(nt, 1.8, 4, 0.55, mp.outputs[0], dim="4D")
        n.inputs["W"].driver_add("default_value").driver.expression = "frame * 0.006"
        # Slow upward drift of the pattern.
        mp.inputs["Location"].driver_add("default_value", 2).driver.expression = "-frame * 0.002"
        wisps = mathn(nt, "MAXIMUM", mathn(nt, "SUBTRACT", n.outputs["Fac"], 0.42), 0.0)
        gen = nt.nodes.new("ShaderNodeSeparateXYZ")
        L(nt, texcoord(nt, "Generated"), gen.inputs[0])
        up = mathn(nt, "POWER", gen.outputs["Z"], 1.5)
        # Toward the hood wall: +X in design space, but the mirror only moves objects, so it ends up at generated X=0.
        side = mathn(nt, "POWER", mathn(nt, "SUBTRACT", 1.0, gen.outputs["X"]), 2.0)
        k = mathn(nt, "MULTIPLY", mathn(nt, "MULTIPLY", wisps, mathn(nt, "ADD", up, side)), density * 14)
        v = nt.nodes.new("ShaderNodeVolumePrincipled")
        v.inputs["Color"].default_value = (0.9, 0.9, 0.9, 1)
        v.inputs["Anisotropy"].default_value = 0.5
        L(nt, mathn(nt, "ADD", k, density * 0.25), v.inputs["Density"])
        L(nt, v.outputs[0], nt.nodes["Material Output"].inputs["Volume"])
    o = _box_mesh("kitchen_vapor", (S.PASS_X + 0.25, 0.9, 1.0), (S.W - 0.02, S.D - 0.05, S.H - 0.02), c)
    o.data.materials.append(m)
    o.visible_shadow = False
    return o
