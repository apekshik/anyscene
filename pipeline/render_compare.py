"""Head-to-head renders of generated props: same studio light and camera fit for every model.

blender -b --factory-startup --python pipeline/render_compare.py -- assets/gen out/compare
For every assets/gen/<model>/<prop>/model.glb writes out/compare/<model>/<prop>_{beauty,clay}.png + stats.json.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

ROOT, OUT = map(os.path.abspath, sys.argv[sys.argv.index("--") + 1:][:2])
# Blender's bundled studio HDRI. bpy.utils.system_resource() returns "" for this in 5.0.1, so build the path from the
# version folder that sits next to the binary (Contents/Resources on macOS).
_VER = "%d.%d" % bpy.app.version[:2]
_BIN = os.path.dirname(bpy.app.binary_path)
HDRI = next((p for p in (os.path.join(_BIN, _VER), os.path.join(_BIN, "..", "Resources", _VER))
             if os.path.isdir(p)), os.path.join(_BIN, _VER))
HDRI = os.path.join(HDRI, "datafiles", "studiolights", "world", "studio.exr")
RES = 900
PROBE = bool(os.environ.get("PROBE"))
# Camera azimuth offset per generator so the "front" view faces the side the reference image shows.
_yaw_path = os.path.join(OUT, "yaw.json")
YAW = json.load(open(_yaw_path)) if os.path.exists(_yaw_path) else {}


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == "OPTIX"
    sc.cycles.device = "GPU"
    sc.cycles.samples = 96
    sc.cycles.use_denoising = True
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    world = bpy.data.worlds.new("w")
    sc.world = world
    world.use_nodes = True
    nt = world.node_tree
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(HDRI)
    bg = nt.nodes["Background"]
    bg.inputs["Strength"].default_value = 0.6
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    return sc


def add_light(name, loc, energy, size, color=(1, 1, 1)):
    d = bpy.data.lights.new(name, "AREA")
    d.energy, d.size, d.color = energy, size, color
    o = bpy.data.objects.new(name, d)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (-Vector(loc)).to_track_quat("-Z", "Y").to_euler()  # area lights shine along -Z


def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    meshes = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    return meshes


def bounds(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def stats(objs, real_size):
    tris = verts = 0
    images = {}
    for o in objs:
        me = o.data
        me.calc_loop_triangles()
        tris += len(me.loop_triangles)
        verts += len(me.vertices)
        for slot in o.material_slots:
            if slot.material and slot.material.use_nodes:
                for n in slot.material.node_tree.nodes:
                    if n.type == "TEX_IMAGE" and n.image:
                        out = [l.to_socket.name for l in n.outputs["Color"].links]
                        images[n.image.name] = {"size": list(n.image.size), "feeds": out}
    return {"tris": tris, "verts": verts, "objects": len(objs), "images": images, "size_m": [round(v, 3) for v in real_size]}


def clay_wire(objs):
    m = bpy.data.materials.new("clay")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.55, 0.55, 0.55, 1)
    bsdf.inputs["Roughness"].default_value = 0.6
    wire = nt.nodes.new("ShaderNodeWireframe")
    wire.use_pixel_size = True
    wire.inputs["Size"].default_value = 0.35
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["A"].default_value = (0.55, 0.55, 0.55, 1)
    mix.inputs["B"].default_value = (0.08, 0.12, 0.2, 1)
    nt.links.new(wire.outputs["Fac"], mix.inputs["Factor"])
    nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    for o in objs:
        o.data.materials.clear()
        o.data.materials.append(m)


def render_one(glb, out_prefix):
    sc = reset()
    objs = import_glb(glb)
    lo, hi = bounds(objs)
    real = hi - lo
    # Normalize: centre on origin, rest on the floor, largest dimension 1 m (framing only; real size goes in stats).
    s = 1.0 / max(real)
    root = bpy.data.objects.new("root", None)
    sc.collection.objects.link(root)
    for o in [o for o in bpy.data.objects if o.parent is None and o is not root]:
        o.parent = root
    c = (lo + hi) / 2
    root.scale = (s, s, s)
    root.location = (-c.x * s, -c.y * s, -lo.z * s)
    bpy.context.view_layer.update()
    lo, hi = bounds(objs)
    centre = (lo + hi) / 2
    radius = (hi - lo).length / 2

    # Shadow catcher-ish floor.
    bpy.ops.mesh.primitive_plane_add(size=20)
    floor = bpy.context.object
    fm = bpy.data.materials.new("floor")
    fm.use_nodes = True
    fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.32, 0.32, 0.33, 1)
    fm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.8
    floor.data.materials.append(fm)

    add_light("key", (2.2, -2.6, 3.0), 260, 1.6)
    add_light("fill", (-3.0, -1.5, 1.6), 70, 2.5, (0.85, 0.9, 1.0))
    add_light("rim", (-1.0, 3.0, 2.5), 160, 1.2)

    cam_d = bpy.data.cameras.new("cam")
    cam_d.lens = 70
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam
    fov = cam_d.angle
    dist = radius / math.sin(fov / 2) * 1.02

    def shoot(az_deg, el_deg, path):
        az, el = math.radians(az_deg), math.radians(el_deg)
        d = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
        cam.location = centre + d * dist
        cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)

    st = stats(objs, real)
    if PROBE:  # four cardinal views to find which way a generator's "front" faces
        sc.render.resolution_x = sc.render.resolution_y = 360
        sc.cycles.samples = 16
        for az in (0, 90, 180, 270):
            shoot(az, 15, f"{out_prefix}_az{az:03d}.png")
        return st
    yaw = YAW.get(os.path.basename(os.path.dirname(out_prefix)), 0)
    shoot(yaw - 30, 18, out_prefix + "_beauty.png")
    shoot(yaw + 150, 22, out_prefix + "_back.png")
    clay_wire(objs)
    shoot(yaw - 30, 18, out_prefix + "_clay.png")
    return st


def main():
    allstats = {}
    for model in sorted(os.listdir(ROOT)):
        for prop in sorted(os.listdir(os.path.join(ROOT, model))):
            glb = os.path.join(ROOT, model, prop, "model.glb")
            if not os.path.exists(glb):
                continue
            od = os.path.join(OUT, model)
            os.makedirs(od, exist_ok=True)
            prefix = os.path.join(od, prop)
            done = prefix + ("_az270.png" if PROBE else "_clay.png")
            if os.path.exists(done) and os.path.getmtime(done) > os.path.getmtime(glb):
                print("skip", model, prop)
                continue
            print("render", model, prop, flush=True)
            try:
                allstats.setdefault(model, {})[prop] = render_one(glb, prefix)
            except Exception as e:  # keep going; a broken GLB is itself a result
                allstats.setdefault(model, {})[prop] = {"error": repr(e)}
                print("FAILED", model, prop, e, flush=True)
    sp = os.path.join(OUT, "stats.json")
    old = json.load(open(sp)) if os.path.exists(sp) else {}
    for m, d in allstats.items():
        old.setdefault(m, {}).update(d)
    json.dump(old, open(sp, "w"), indent=2)


main()
