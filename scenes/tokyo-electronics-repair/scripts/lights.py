"""Night lighting, haze, render settings and compositor for the repair shop (the video's lighting + atmosphere steps).

blender -b <in.blend> --python scenes/tokyo-electronics-repair/scripts/lights.py -- <out.blend>
Idempotent: removes its own objects (collection "night_rig") before rebuilding.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

out = os.path.abspath(sys.argv[sys.argv.index("--") + 1])
sc = bpy.context.scene
W, D, H = 4.2, 6.5, 2.7

old = bpy.data.collections.get("night_rig")
if old:
    for o in list(old.objects):
        bpy.data.objects.remove(o)
    bpy.data.collections.remove(old)
rig = bpy.data.collections.new("night_rig")
sc.collection.children.link(rig)


def light(name, kind, loc, energy, color, target=None, **kw):
    d = bpy.data.lights.new(name, kind)
    d.energy = energy
    d.color = color
    for k, v in kw.items():
        setattr(d, k, v)
    o = bpy.data.objects.new(name, d)
    rig.objects.link(o)
    o.location = loc
    o.visible_camera = o.visible_glossy = o.visible_transmission = False  # light, not a visible panel in the glass
    if target is not None:
        o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


# --- world: almost black, a hint of blue so shadows are not dead
w = sc.world or bpy.data.worlds.new("night")
sc.world = w
bg = w.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.004, 0.006, 0.012, 1)
bg.inputs["Strength"].default_value = 1.0

# --- outside: cool street spill through the storefront + two neon accents (the backdrop plane also emits)
light("street_fill", "AREA", (W / 2, -1.6, 2.4), 70, (0.55, 0.68, 1.0), (W / 2, 3.0, 0.3), shape="RECTANGLE", size=4.5, size_y=1.6)
light("neon_magenta", "AREA", (3.4, -2.4, 2.8), 55, (1.0, 0.18, 0.5), (2.6, 2.5, 0.5), size=0.8)
light("neon_cyan", "AREA", (0.7, -2.8, 2.2), 40, (0.2, 0.85, 1.0), (1.2, 3.0, 0.8), size=0.6)
light("streetlamp", "SPOT", (1.0, -3.0, 4.2), 220, (0.75, 0.82, 1.0), (1.4, 2.0, 0.0), spot_size=math.radians(55), spot_blend=0.6, shadow_soft_size=0.15)

# the street backdrop stays visible through the glass and in reflections, but must not flood the room with diffuse light
bd = sc.objects.get("street_backdrop")
if bd:
    bd.visible_diffuse = False
    bd.visible_volume_scatter = False

# --- work lamp: warm spot from the shade, plus a tiny bulb glow. Follows the dressed lamp if present.
lamp = sc.objects.get("repair_work_lamp")
shade = Vector((0.42, 2.62, 1.38))
if lamp:
    # the generated shade is a closed mesh: put the spot just under its rim, found from the vertices at the arm end
    # which end is the shade: the x-extreme farthest from the clamp (the lowest vertices)
    vs = [lamp.matrix_world @ v.co for v in lamp.data.vertices]
    zmin = min(v.z for v in vs)
    clamp_x = sum(v.x for v in vs if v.z < zmin + 0.05) / max(1, sum(1 for v in vs if v.z < zmin + 0.05))
    lo_x, hi_x = min(v.x for v in vs), max(v.x for v in vs)
    end = lo_x if abs(lo_x - clamp_x) > abs(hi_x - clamp_x) else hi_x
    sh = [v for v in vs if abs(v.x - end) < 0.17 and v.z > zmin + 0.2]
    rim = min(v.z for v in sh)
    shade = Vector((sum(v.x for v in sh) / len(sh), sum(v.y for v in sh) / len(sh), rim - 0.012))
hh = sc.objects.get("helping_hands")  # keep the pool on the helping hands and the board in its clips
target = (hh.matrix_world.translation + Vector((0.0, 0.0, 0.0))) if hh else Vector((shade.x - 0.08, shade.y - 0.1, 0.88))
target = Vector((target.x - 0.04, target.y - 0.06, 0.88))
light("lamp_spot", "SPOT", shade, 40, (1.0, 0.72, 0.45), target, spot_size=math.radians(75), spot_blend=0.55, shadow_soft_size=0.025)
light("lamp_bounce", "POINT", shade + Vector((0, 0, 0.04)), 1.5, (1.0, 0.7, 0.45), shadow_soft_size=0.03)

# --- warm under-shelf strip over the back of the bench (left on, low)
# (an under-shelf strip was tried here; it only made the pegboard a hot panel)

# --- oscilloscope glow (screen emission comes from the prop fix; this adds spill on the bench)
osc = sc.objects.get("oscilloscope")
if osc:
    fwd = osc.matrix_world.to_3x3() @ Vector((0, -1, 0))
    p = osc.matrix_world @ Vector((-0.06, -0.3, 0.11))
    sp = light("scope_spill", "AREA", p, 0.6, (0.35, 1.0, 0.55), p + fwd, size=0.12)
    sp.visible_volume_scatter = False

# --- round 2 practicals: they lift the racks and counter out of black with motivated light
def bbox(name):
    o = sc.objects.get(name)
    if not o:
        return None
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi, (lo + hi) / 2


b = bbox("counter_lamp")
if b:  # green banker lamp: warm pool on the counter + a faint glow on the shade
    lo, hi, ce = b
    p = Vector((ce.x, ce.y, hi.z - 0.05))
    light("counter_lamp_spot", "SPOT", p, 9, (1.0, 0.75, 0.45), (ce.x - 0.25, ce.y - 0.2, 0.95), spot_size=math.radians(110), spot_blend=0.8, shadow_soft_size=0.03)
    light("counter_lamp_fill", "POINT", p + Vector((0, 0, 0.03)), 1.2, (0.5, 1.0, 0.6), shadow_soft_size=0.05)
b = bbox("ring_lamp_led")
if b:  # ring magnifier lamp at the second station: cool LED disc
    lo, hi, ce = b
    light("ring_lamp_light", "SPOT", ce - Vector((0, 0, 0.01)), 9, (0.85, 0.92, 1.0), (ce.x + 0.05, ce.y, 0.88), spot_size=math.radians(100), spot_blend=0.9, shadow_soft_size=0.06)
b = bbox("tube_on")
if b:  # one fluorescent tube left on over the racks
    lo, hi, ce = b
    t = light("tube_racks_light", "AREA", ce - Vector((0, 0, 0.03)), 13, (0.8, 0.9, 1.0), (ce.x, ce.y, 0.0), shape="RECTANGLE", size=0.06, size_y=1.2)
b = bbox("rack_clip_bulb")
if b:  # clip lamp on the racks: warm cone down the rack fronts and into the aisle
    lo, hi, ce = b
    light("rack_clip_spot", "SPOT", ce, 30, (1.0, 0.8, 0.55), (3.35, 3.3, 0.55), spot_size=math.radians(105), spot_blend=0.7, shadow_soft_size=0.03)
    light("rack_clip_glow", "POINT", ce + Vector((0.03, 0, 0.03)), 0.8, (1.0, 0.8, 0.55), shadow_soft_size=0.02)
# soft bounce: what the clip lamp and tube throw back off the floor and ceiling over the rack side of the room
bo = light("rack_bounce", "AREA", (3.2, 3.2, 2.55), 11, (0.95, 0.88, 0.8), (3.2, 3.2, 0.0), shape="RECTANGLE", size=1.6, size_y=3.8)
bo.visible_glossy = False
bo.data.use_shadow = True
# the counter lamp pool bounced off the floor onto the shop side of the counter
light("counter_bounce", "AREA", (2.7, 2.75, 0.35), 4, (1.0, 0.82, 0.62), (2.7, 1.9, 0.45), shape="RECTANGLE", size=1.4, size_y=0.4)
b = bbox("vending_panel") or bbox("vending_machine")
if b:
    lo, hi, ce = b
    if not sc.objects.get("vending_panel"):  # generated machine: spill from its lit front (faces +Y)
        ce = Vector((ce.x, hi.y, ce.z + 0.2))
    light("vending_spill", "AREA", ce + Vector((0, 0.15, 0)), 20, (0.85, 0.92, 1.0), (ce.x + 0.5, 3.0, 0.5), size=0.9)
b = bbox("aframe_lamp") or bbox("aframe_1")
if b:
    light("aframe_glow", "POINT", b[2] + Vector((0, 0.1, 0)), 8, (1.0, 0.7, 0.4), shadow_soft_size=0.05)
for o in sc.objects:
    if o.name.startswith("rain_"):
        o.visible_volume_scatter = False

# --- haze: one volume box over the interior
fog = bpy.data.meshes.new("haze")
import bmesh  # noqa: E402

bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1)
bm.to_mesh(fog)
bm.free()
fo = bpy.data.objects.new("haze", fog)
rig.objects.link(fo)
fo.location = (W / 2, D / 2 + 0.02, H / 2)
fo.scale = (W - 0.02, D - 0.06, H - 0.02)
fm = bpy.data.materials.get("haze_vol") or bpy.data.materials.new("haze_vol")
nt = fm.node_tree
for n in list(nt.nodes):
    if n.type != "OUTPUT_MATERIAL":
        nt.nodes.remove(n)
pv = nt.nodes.new("ShaderNodeVolumePrincipled")
pv.inputs["Density"].default_value = 0.018
pv.inputs["Anisotropy"].default_value = 0.35
pv.inputs["Color"].default_value = (0.85, 0.88, 0.9, 1)
nt.links.new(pv.outputs["Volume"], nt.nodes["Material Output"].inputs["Volume"])
fo.data.materials.append(fm)
fo.visible_shadow = True

# --- render settings
sc.render.engine = "CYCLES"
c = sc.cycles
c.samples = 256
c.device = "GPU"
c.use_denoising = True
c.denoiser = "OPTIX"
c.volume_step_rate = 4.0
c.max_bounces = 8
c.caustics_reflective = False
c.caustics_refractive = False
c.blur_glossy = 1.0
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
sc.view_settings.exposure = 0.95  # +0.5 EV over the first round-2 pass: racks and floor must read
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
sc.render.use_motion_blur = True
sc.render.motion_blur_shutter = 0.5
sc.render.fps = 24

# --- compositor: bloom on practicals + lens distortion with a little dispersion (grade/vignette/grain in ffmpeg)
ng = bpy.data.node_groups.get("repair_comp") or bpy.data.node_groups.new("repair_comp", "CompositorNodeTree")
for n in list(ng.nodes):
    ng.nodes.remove(n)
if not ng.interface.items_tree:
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
rl = ng.nodes.new("CompositorNodeRLayers")
gl = ng.nodes.new("CompositorNodeGlare")
gl.inputs["Type"].default_value = "Bloom"
gl.inputs["Threshold"].default_value = 0.9
gl.inputs["Strength"].default_value = 0.35
gl.inputs["Size"].default_value = 0.6
ld = ng.nodes.new("CompositorNodeLensdist")
ld.inputs["Distortion"].default_value = -0.012
ld.inputs["Dispersion"].default_value = 0.008
go = ng.nodes.new("NodeGroupOutput")
ng.links.new(rl.outputs["Image"], gl.inputs["Image"])
ng.links.new(gl.outputs["Image"], ld.inputs["Image"])
ng.links.new(ld.outputs["Image"], go.inputs[0])
sc.compositing_node_group = ng
sc.render.use_compositing = True

bpy.ops.wm.save_as_mainfile(filepath=out)
print("lit ->", out)
