"""/build refine stage, Blender side. Works on a scene.blend written by assemble.py.

    blender -b scene.blend --python refine_blender.py -- views  out_dir
        straight-on front render of every prop in the asset library (+ views.json: how each image maps to the mesh),
        for Claude to mark screens, glass and lamps on.
    blender -b scene.blend --python refine_blender.py -- apply  refine.json  out_dir
        applies refine.json: per-prop surfaces (emissive screens with generated content and scanlines, real glass,
        lit lamps with a light per placement, glowing panels) and tileable textures on the scripted pieces; saves.
    blender -b scene.blend --python refine_blender.py -- pano   shots.json out_dir [--samples 64] [--res 2048]
        equirectangular Cycles panoramas from each still's camera position: the exact Blender lighting, for a 360 view.
    blender -b scene.blend --python refine_blender.py -- glb    out_dir [--tris 60000]
        the assembled scene as a decimated glTF with its lights (KHR_lights_punctual), for a real-time 3D view.

A prop's front view looks along +Y at its front face (props are normalised to face -Y with the origin at the bottom
centre), so a box marked on the image maps straight back to X/Z on the mesh and is projected onto it with rays.
"""

import hashlib
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:]
cmd = argv[0]
opt = lambda k, d: type(d)(argv[argv.index(k) + 1]) if k in argv else d


def library():
    c = bpy.data.collections.get("asset_library")
    return list(c.objects) if c else []


def scene_objects():
    c = bpy.data.collections.get("scene")
    return list(c.objects) if c else []


def bounds(ob):
    vs = [v.co for v in ob.data.vertices]
    lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    return lo, hi


def gpu():
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            if any(d.type == kind for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type == kind
                bpy.context.scene.cycles.device = "GPU"
                return
        except TypeError:
            continue


# ---------------------------------------------------------------- views
def views(out):
    os.makedirs(out, exist_ok=True)
    sc = bpy.data.scenes.new("refine_views")
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "FLAT"
    sc.display.shading.color_type = "TEXTURE"
    sc.render.film_transparent = False
    sc.world = bpy.data.worlds.new("v")
    cam_data = bpy.data.cameras.new("vcam")
    cam_data.type = "ORTHO"
    cam = bpy.data.objects.new("vcam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    meta = {}
    for ob in library():
        for o in list(sc.collection.objects):
            if o != cam:
                sc.collection.objects.unlink(o)
        sc.collection.objects.link(ob)
        lo, hi = bounds(ob)
        w, h = (hi.x - lo.x) * 1.08, (hi.z - lo.z) * 1.08
        cx, cz = (lo.x + hi.x) / 2, (lo.z + hi.z) / 2
        aspect = max(0.25, min(4.0, w / max(h, 1e-4)))
        sc.render.resolution_x, sc.render.resolution_y = (768, max(64, int(768 / aspect))) if aspect >= 1 else (max(64, int(768 * aspect)), 768)
        cam_data.ortho_scale = max(w, h)
        cam.location = (cx, lo.y - 5.0, cz)
        cam.rotation_euler = (math.radians(90), 0, 0)  # looks along +Y, at the front face
        sc.render.filepath = os.path.join(out, f"{ob.name}.png")
        bpy.ops.render.render(write_still=True, scene=sc.name)
        fw, fh = (cam_data.ortho_scale, cam_data.ortho_scale / aspect) if aspect >= 1 else (cam_data.ortho_scale * aspect, cam_data.ortho_scale)
        meta[ob.name] = {"x0": cx - fw / 2, "x1": cx + fw / 2, "z0": cz - fh / 2, "z1": cz + fh / 2, "y0": lo.y - 1.0}
        sc.collection.objects.unlink(ob)
    json.dump(meta, open(os.path.join(out, "views.json"), "w"), indent=1)
    print(f"refine: {len(meta)} front views")


# ---------------------------------------------------------------- materials
def node_mat(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    return m, m.node_tree.nodes, m.node_tree.links


def screen_material(name, image_path):
    m, n, l = node_mat(name)
    b = n["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.01, 0.012, 0.01, 1)
    b.inputs["Roughness"].default_value = 0.12  # glassy tube face
    uv = n.new("ShaderNodeUVMap")
    uv.uv_map = "screen_uv"
    tex = n.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(image_path, check_existing=True)
    l.new(uv.outputs["UV"], tex.inputs["Vector"])
    wave = n.new("ShaderNodeTexWave")  # scanlines across the screen
    wave.bands_direction = "Y"
    wave.inputs["Scale"].default_value = 220
    l.new(uv.outputs["UV"], wave.inputs["Vector"])
    ramp = n.new("ShaderNodeMapRange")
    ramp.inputs["To Min"].default_value, ramp.inputs["To Max"].default_value = 0.72, 1.0
    l.new(wave.outputs["Fac"], ramp.inputs["Value"])
    mul = n.new("ShaderNodeMix")
    mul.data_type, mul.blend_type = "RGBA", "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    l.new(tex.outputs["Color"], mul.inputs[6])
    l.new(ramp.outputs["Result"], mul.inputs[7])
    l.new(mul.outputs[2], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = 3.5
    return m


def glass_material():
    m, n, _ = node_mat("refine_glass")
    b = n["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.9, 0.95, 0.95, 1)
    b.inputs["Transmission Weight"].default_value = 1.0
    b.inputs["Roughness"].default_value = 0.04
    b.inputs["IOR"].default_value = 1.45
    return m


def lamp_material(color):
    m, n, _ = node_mat("refine_lamp_" + color.lstrip("#"))
    b = n["Principled BSDF"]
    rgb = tuple(int(color.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Emission Color"].default_value = (*rgb, 1)
    b.inputs["Emission Strength"].default_value = 12.0
    return m


def glow_material(ob):
    """Glowing panel (backlit sign, indicator bank): its own albedo becomes emission."""
    src = ob.data.materials[0] if ob.data.materials else None
    m = src.copy() if src else bpy.data.materials.new("refine_glow")
    m.name = f"refine_glow_{ob.name}"
    m.use_nodes = True
    n, l = m.node_tree.nodes, m.node_tree.links
    b = next((x for x in n if x.type == "BSDF_PRINCIPLED"), None)
    if b:
        col = b.inputs["Base Color"]
        if col.is_linked:
            l.new(col.links[0].from_socket, b.inputs["Emission Color"])
        else:
            b.inputs["Emission Color"].default_value = col.default_value
        b.inputs["Emission Strength"].default_value = 2.0
    return m


def tile_material(name, image_path, tile_m):
    m, n, l = node_mat(name)
    b = n["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.65
    coord = n.new("ShaderNodeTexCoord")
    mapping = n.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1 / tile_m, 1 / tile_m, 1 / tile_m)
    tex = n.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(image_path, check_existing=True)
    tex.projection, tex.projection_blend = "BOX", 0.25
    l.new(coord.outputs["Object"], mapping.inputs["Vector"])
    l.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    l.new(tex.outputs["Color"], b.inputs["Base Color"])
    return m


# ---------------------------------------------------------------- apply
def faces_in_box(ob, meta, box):
    """Polygons of `ob` hit by rays shot along +Y through the box (normalised image coords, y down)."""
    tree = BVHTree.FromObject(ob, bpy.context.evaluated_depsgraph_get(), deform=False)
    x0 = meta["x0"] + box[0] * (meta["x1"] - meta["x0"])
    x1 = meta["x0"] + box[2] * (meta["x1"] - meta["x0"])
    z1 = meta["z1"] - box[1] * (meta["z1"] - meta["z0"])
    z0 = meta["z1"] - box[3] * (meta["z1"] - meta["z0"])
    hits, n = set(), 24
    for i in range(n + 1):
        for j in range(n + 1):
            x, z = x0 + (x1 - x0) * i / n, z0 + (z1 - z0) * j / n
            loc, nor, idx, _ = tree.ray_cast(Vector((x, meta["y0"], z)), Vector((0, 1, 0)), 50)
            if idx is not None and nor.y < 0.2:  # front-facing faces only
                hits.add(idx)
    return hits, (x0, x1, z0, z1)


def assign(ob, faces, mat, uv_rect=None):
    me = ob.data
    if mat.name not in [m.name for m in me.materials if m]:
        me.materials.append(mat)
    slot = [m.name if m else "" for m in me.materials].index(mat.name)
    if uv_rect:
        uvl = me.uv_layers.get("screen_uv") or me.uv_layers.new(name="screen_uv")
        x0, x1, z0, z1 = uv_rect
    for p in me.polygons:
        if p.index in faces:
            p.material_index = slot
            if uv_rect:
                for li in p.loop_indices:
                    co = me.vertices[me.loops[li].vertex_index].co
                    uvl.data[li].uv = ((co.x - x0) / max(x1 - x0, 1e-4), (co.z - z0) / max(z1 - z0, 1e-4))


def apply(spec, out):
    os.makedirs(out, exist_ok=True)
    meta = spec["views"]
    lib = {o.name: o for o in library()}
    placements = {}
    for o in scene_objects():
        if o.type == "MESH" and o.data.name in lib:
            placements.setdefault(o.data.name, []).append(o)
    counts = {"screen": 0, "glass": 0, "lamp": 0, "glow": 0, "lights": 0, "textured": 0}
    for aid, surfaces in spec["surfaces"].items():
        ob = lib.get(aid)
        if ob is None or aid not in meta:
            continue
        for k, s in enumerate(surfaces):
            faces, rect = faces_in_box(ob, meta[aid], s["box"])
            if not faces:
                continue
            kind = s["kind"]
            if kind == "screen" and s.get("image"):
                assign(ob, faces, screen_material(f"refine_screen_{aid}_{k}", s["image"]), rect)
            elif kind == "glass":
                assign(ob, faces, glass_material())
            elif kind == "lamp":
                color = s.get("color", "#ffc98a")
                assign(ob, faces, lamp_material(color))
                c = sum((ob.data.polygons[i].center for i in faces), Vector()) / len(faces)
                for inst in placements.get(aid, []):  # one real light per placement, just in front of the bulb
                    data = bpy.data.lights.new(f"refine_light_{inst.name}_{k}", "POINT")
                    data.energy, data.shadow_soft_size = 35.0, 0.05
                    data.color = tuple(int(color.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
                    lo = bpy.data.objects.new(data.name, data)
                    lo.location = inst.matrix_world @ (c + Vector((0, -0.04, -0.02)))
                    bpy.data.collections["scene"].objects.link(lo)
                    counts["lights"] += 1
            elif kind == "glow":
                assign(ob, faces, glow_material(ob))
            counts[kind] = counts.get(kind, 0) + 1
    for oid, tex in spec.get("textures", {}).items():
        o = bpy.data.objects.get(oid)
        if o and o.type == "MESH" and tex.get("image"):
            name = "refine_tile_" + hashlib.md5(tex["image"].encode()).hexdigest()[:8]
            m = bpy.data.materials.get(name) or tile_material(name, tex["image"], tex.get("tile_m", 0.8))
            o.data.materials.clear()
            o.data.materials.append(m)
            counts["textured"] += 1
    print("refine: applied " + ", ".join(f"{v} {k}" for k, v in counts.items()))
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "scene.blend"), compress=True)


# ---------------------------------------------------------------- panoramas
def pano(shots_path, out):
    gpu()
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = opt("--samples", 64)
    sc.cycles.use_denoising = True
    res = opt("--res", 2048)
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = res, res // 2, 100
    cam_data = bpy.data.cameras.new("pano")
    cam_data.type = "PANO"
    cam_data.panorama_type = "EQUIRECTANGULAR"
    cam = bpy.data.objects.new("pano", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    os.makedirs(out, exist_ok=True)
    for shot in json.load(open(shots_path))["shots"]:
        k = shot["keys"][0]
        pos, aim = Vector(k["pos"]), Vector(k["aim"])
        yaw = math.atan2(aim.y - pos.y, aim.x - pos.x) - math.pi / 2
        cam.location = pos
        cam.rotation_euler = (math.radians(90), 0, yaw)  # level, facing the shot's aim, so the seam sits behind
        sc.render.filepath = os.path.join(out, f"pano_{shot['name']}.png")
        bpy.ops.render.render(write_still=True)
        print("refine: panorama", shot["name"])


# ---------------------------------------------------------------- glb
def glb(out, tris_cap):
    os.makedirs(out, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    done = set()
    for o in scene_objects():
        if o.type == "MESH" and o.data.name not in done:
            n = sum(len(p.vertices) - 2 for p in o.data.polygons)
            if n > tris_cap:
                dec = o.modifiers.new("refine_decimate", "DECIMATE")
                dec.ratio = tris_cap / n
            done.add(o.data.name)
        o.select_set(o.type in ("MESH", "LIGHT"))
    tex = opt("--tex", 1024)  # generated meshes carry 4K sets; a browser viewer needs far less
    for im in bpy.data.images:
        if max(im.size) > tex:
            s = tex / max(im.size)
            im.scale(max(1, int(im.size[0] * s)), max(1, int(im.size[1] * s)))
    path = os.path.join(out, "scene.glb")
    bpy.ops.export_scene.gltf(filepath=path, use_selection=True, export_apply=True, export_lights=True,
                              export_draco_mesh_compression_enable=True, export_image_format="JPEG", export_cameras=False)
    print("refine: wrote", path, f"{os.path.getsize(path) / 1e6:.0f} MB")


if __name__ == "__main__":
    if cmd == "views":
        views(argv[1])
    elif cmd == "apply":
        apply(json.load(open(argv[1], encoding="utf-8")), argv[2])
    elif cmd == "pano":
        pano(argv[1], argv[2])
    elif cmd == "glb":
        glb(argv[1], opt("--tris", 60000))
