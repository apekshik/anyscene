"""Rebuild an AnyScene export (export_blend.py -> scene.json + GLBs + baked textures) as an Unreal level.

Headless (no editor window), from a shell:
  UnrealEditor-Cmd.exe <project>.uproject -run=pythonscript -script="<path>/build_level.py" -unattended -nosplash -nop4
Configuration comes from environment variables (the pythonscript commandlet does not pass script args reliably):
  ANYSCENE_EXPORT  export folder holding scene.json            (required)
  ANYSCENE_DEST    content root, default /Game/AnyScene/HK
  ANYSCENE_LEVEL   level name, default L_HK
  ANYSCENE_STAGES  comma list of: textures,meshes,materials,level,fx,sequences (default: all)
  ANYSCENE_FX_OVERRIDES  optional JSON {fx id | "type:<type>": {UserParam: value}} applied on top of scene.json fx params
                   (look-match tuning; TOGGLE.md "overrides.json")
  ANYSCENE_CLIP_FRAMES  length of the MRQ_Clip config and of every camera sequence (default 96 = 4 s at 24 fps)
  ANYSCENE_ONLY    comma list of asset names to (re)import (testing)
  ANYSCENE_NANITE_TRIS  Nanite on for meshes above this triangle count (default 2000; glass meshes never)
  ANYSCENE_EXPOSURE_OFFSET  extra EV added to the computed manual exposure (calibration)

Assets that already exist are reused (delete the folder to force a reimport). The level is rebuilt from scratch.
"""
import json
import math
import os
import time

import unreal
import warnings

warnings.simplefilter("ignore", DeprecationWarning)  # UE turns deprecated-property warnings into exceptions

EXPORT = os.environ.get("ANYSCENE_EXPORT", "")
DEST = os.environ.get("ANYSCENE_DEST", "/Game/AnyScene/HK")
LEVEL = os.environ.get("ANYSCENE_LEVEL", "L_HK")
STAGES = os.environ.get("ANYSCENE_STAGES", "textures,meshes,materials,level,fx,sequences").split(",")
ONLY = set(x for x in os.environ.get("ANYSCENE_ONLY", "").split(",") if x)
NANITE_TRIS = int(os.environ.get("ANYSCENE_NANITE_TRIS", "2000"))
EXPO_OFF = float(os.environ.get("ANYSCENE_EXPOSURE_OFFSET", "0"))
FX_OVR = json.load(open(os.environ["ANYSCENE_FX_OVERRIDES"])) if os.environ.get("ANYSCENE_FX_OVERRIDES") else {}
CLIP_FRAMES = int(os.environ.get("ANYSCENE_CLIP_FRAMES", "96"))

EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
T0 = time.time()
REPORT = {"warnings": [], "timings": {}}
KEEP = []


def log(*a):
    unreal.log_warning("ANYSCENE " + " ".join(str(x) for x in a))


def warn(msg):
    REPORT["warnings"].append(msg)
    log("WARN", msg)


scene = json.load(open(os.path.join(EXPORT, "scene.json"), encoding="utf-8"))
ASSETS = [a for a in scene["assets"] if not ONLY or a["asset"] in ONLY]


# ------------------------------------------------------------------ textures

def tex_path(name):
    return f"{DEST}/Tex/{name}"


def import_files(files, dest):
    tasks = []
    for f in files:
        t = unreal.AssetImportTask()
        t.filename = f
        t.destination_path = dest
        t.automated = True
        t.save = False
        t.replace_existing = True
        tasks.append(t)
    if tasks:
        AT.import_asset_tasks(tasks)
    return tasks


def stage_textures():
    t = time.time()
    todo = []
    for a in ASSETS:
        for ch, rel in a.get("tex", {}).items():
            n = os.path.splitext(os.path.basename(rel))[0]
            if not EAL.does_asset_exist(tex_path(n)):
                todo.append((os.path.join(EXPORT, rel), ch, n))
    lut = scene["grade"].get("ffmpeg", {}).get("lut")
    extra = []
    if lut and not EAL.does_asset_exist(tex_path("lut_grade")):
        extra.append(os.path.join(EXPORT, lut))
    sky = (scene.get("world") or {}).get("equirect_exr")
    if sky and not EAL.does_asset_exist(tex_path("sky")):
        extra.append(os.path.join(EXPORT, sky))
    log(f"textures: importing {len(todo)} (+{len(extra)} extra)")
    for i in range(0, len(todo), 64):
        chunk = todo[i:i + 64]
        import_files([f for f, _, _ in chunk], f"{DEST}/Tex")
        for f, ch, n in chunk:
            tx = EAL.load_asset(tex_path(n))
            if tx is None:
                warn(f"texture import failed {f}")
                continue
            if ch == "orm":
                tx.set_editor_property("srgb", False)
                tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
            elif ch == "normal":
                tx.set_editor_property("srgb", False)
                tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
                tx.set_editor_property("flip_green_channel", True)  # Blender bakes OpenGL (+Y) normals
            else:
                tx.set_editor_property("srgb", True)
            EAL.save_loaded_asset(tx, False)
        log(f"textures {min(i + 64, len(todo))}/{len(todo)} ({time.time() - t:.0f}s)")
    if extra:
        import_files(extra, f"{DEST}/Tex")
        l = EAL.load_asset(tex_path("lut_grade"))
        if l:
            l.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_COLOR_LOOKUP_TABLE)
            l.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
            l.set_editor_property("srgb", False)
            l.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
            EAL.save_loaded_asset(l, False)
        s = EAL.load_asset(tex_path("sky"))
        if s:
            EAL.save_loaded_asset(s, False)
    REPORT["timings"]["textures_s"] = round(time.time() - t)


# ------------------------------------------------------------------ meshes

def mesh_folder(a):
    return f"{DEST}/Meshes/{a['asset']}"


def find_mesh(a):
    for p in EAL.list_assets(mesh_folder(a), recursive=True, include_folder=False):
        d = unreal.EditorAssetLibrary.find_asset_data(p)
        if d.asset_class_path.asset_name == "StaticMesh":
            return EAL.load_asset(p)
    return None


def pipeline_for(a):
    p = unreal.InterchangeGenericAssetsPipeline()
    mp = p.get_editor_property("mesh_pipeline")
    mp.set_editor_property("import_static_meshes", True)
    mp.set_editor_property("import_skeletal_meshes", False)
    mp.set_editor_property("build_nanite", a["tris"] > NANITE_TRIS and not a.get("glass"))
    mp.set_editor_property("generate_lightmap_u_vs", False)
    try:
        mp.set_editor_property("collision", False)
    except Exception:
        pass
    mat = p.get_editor_property("material_pipeline")
    mat.set_editor_property("import_materials", False)
    try:
        tp = mat.get_editor_property("texture_pipeline")
        tp.set_editor_property("import_textures", False)
    except Exception as ex:  # noqa: BLE001
        log("texture pipeline", ex)
    cm = p.get_editor_property("common_meshes_properties")
    cm.set_editor_property("recompute_normals", False)
    cm.set_editor_property("recompute_tangents", False)
    cm.set_editor_property("use_mikk_t_space", True)
    cm.set_editor_property("remove_degenerates", False)
    return p


def stage_meshes():
    t = time.time()
    im = unreal.InterchangeManager.get_interchange_manager_scripted()
    todo = [a for a in ASSETS if find_mesh(a) is None]
    log(f"meshes: importing {len(todo)} of {len(ASSETS)}")

    def queue(a):
        src = im.create_source_data(os.path.join(EXPORT, a["glb"]))
        prm = unreal.ImportAssetParameters()
        prm.is_automated = True
        prm.replace_existing = True
        pipe = pipeline_for(a)
        KEEP.append(pipe)  # soft path to a transient pipeline: keep it alive until the import is done
        prm.override_pipelines = [unreal.SoftObjectPath(pipe.get_path_name())]
        im.import_asset(mesh_folder(a), src, prm)

    def flush(last):
        # UE 5.8 commandlet: the import queued last before wait_until_all_tasks_done() logs "start importing" and
        # never completes (1 in 16 meshes went missing). Queue the last asset a second time as a sacrificial
        # sentinel so the real import of it completes.
        queue(last)
        im.wait_until_all_tasks_done(True)

    for i, a in enumerate(todo):
        queue(a)
        if i % 16 == 15 or i == len(todo) - 1:
            flush(a)
            log(f"meshes {i + 1}/{len(todo)} ({time.time() - t:.0f}s)")
    for attempt in range(2):
        miss = [a for a in ASSETS if find_mesh(a) is None]
        if not miss:
            break
        log(f"meshes: retry {len(miss)} missing (pass {attempt + 1})")
        for a in miss:
            queue(a)
        flush(miss[-1])
    # Orientation check against the exporter's expected local bounds.
    checks = []
    for a in ASSETS[:40]:
        sm = find_mesh(a)
        if sm is None:
            warn(f"mesh missing after import: {a['asset']}")
            continue
        bb = sm.get_bounding_box()
        got = [bb.min.x, bb.min.y, bb.min.z, bb.max.x, bb.max.y, bb.max.z]
        exp = a["check_bounds"]["min"] + a["check_bounds"]["max"]
        exp = [min(exp[0], exp[3]), min(exp[1], exp[4]), min(exp[2], exp[5]), max(exp[0], exp[3]), max(exp[1], exp[4]), max(exp[2], exp[5])]
        err = max(abs(g - e) for g, e in zip(got, exp))
        checks.append(err)
        if err > 2.0:
            warn(f"bounds mismatch {a['asset']}: got {[round(x, 1) for x in got]} expected {[round(x, 1) for x in exp]}")
    REPORT["orientation_max_err_cm"] = max(checks) if checks else None
    for a in ASSETS:
        sm = find_mesh(a)
        if sm:
            EAL.save_loaded_asset(sm, False)
    REPORT["timings"]["meshes_s"] = round(time.time() - t)


# ------------------------------------------------------------------ materials

def master_baked():
    path = f"{DEST}/Materials/M_AnyBaked"
    if EAL.does_asset_exist(path):
        return EAL.load_asset(path)
    m = AT.create_asset("M_AnyBaked", f"{DEST}/Materials", unreal.Material, unreal.MaterialFactoryNew())
    def tex(name, x, y, default, stype):
        n = MEL.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, x, y)
        n.set_editor_property("parameter_name", name)
        n.set_editor_property("texture", unreal.load_asset(default))
        n.set_editor_property("sampler_type", stype)
        return n
    m.set_editor_property("used_with_nanite", True)
    bc = tex("BaseColor", -600, -200, "/Engine/EngineResources/WhiteSquareTexture", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    # The ORM default must itself be a linear TC_MASKS texture: an sRGB default (WhiteSquareTexture) fails the
    # master's compile ("Sampler type is Masks, should be Color") and every instance silently falls back to the
    # default grid material, while Nanite meshes using it vanish.
    orm_default = next((tex_path(os.path.splitext(os.path.basename(a["tex"]["orm"]))[0]) for a in scene["assets"]
                        if a.get("tex", {}).get("orm") and EAL.does_asset_exist(tex_path(os.path.splitext(os.path.basename(a["tex"]["orm"]))[0]))), None)
    orm = tex("ORM", -600, 50, orm_default or "/Engine/EngineResources/WhiteSquareTexture", unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    nrm = tex("Normal", -600, 300, "/Engine/EngineMaterials/DefaultNormal", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    em = tex("Emissive", -600, 550, "/Engine/EngineResources/Black", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    es = MEL.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -600, 800)
    es.set_editor_property("parameter_name", "EmissiveScale")
    es.set_editor_property("default_value", 0.0)
    mul = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -250, 600)
    MEL.connect_material_expressions(em, "RGB", mul, "A")
    MEL.connect_material_expressions(es, "", mul, "B")
    MEL.connect_material_property(bc, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(orm, "G", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.connect_material_property(orm, "B", unreal.MaterialProperty.MP_METALLIC)
    MEL.connect_material_property(nrm, "RGB", unreal.MaterialProperty.MP_NORMAL)
    MEL.connect_material_property(mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    m.set_editor_property("two_sided", True)  # generated props and single planes (signs, facades) are often open
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m, False)
    return m


def master_glass():
    path = f"{DEST}/Materials/M_AnyGlass"
    if EAL.does_asset_exist(path):
        return EAL.load_asset(path)
    m = AT.create_asset("M_AnyGlass", f"{DEST}/Materials", unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    m.set_editor_property("translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    m.set_editor_property("two_sided", True)
    c = MEL.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -500, 0)
    c.set_editor_property("parameter_name", "Color")
    c.set_editor_property("default_value", unreal.LinearColor(1, 1, 1, 1))
    r = MEL.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -500, 200)
    r.set_editor_property("parameter_name", "Roughness")
    r.set_editor_property("default_value", 0.05)
    o = MEL.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -500, 350)
    o.set_editor_property("parameter_name", "Opacity")
    o.set_editor_property("default_value", 0.25)
    MEL.connect_material_property(c, "", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(r, "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.connect_material_property(o, "", unreal.MaterialProperty.MP_OPACITY)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m, False)
    return m


def master_sky():
    """Unlit sky dome: equirect texture looked up by view direction (Blender world, +Y at the image centre)."""
    path = f"{DEST}/Materials/M_AnySky"
    if EAL.does_asset_exist(path):
        return EAL.load_asset(path)
    m = AT.create_asset("M_AnySky", f"{DEST}/Materials", unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    # IsSky: the real-time sky light capture only sees sky-flagged materials, and without it the editor/-game
    # build stamps "YOUR SCENE CONTAINS A SKYDOME MESH WITH A SKY MATERIAL..." over every uncovered pixel.
    m.set_editor_property("is_sky", True)
    m.set_editor_property("two_sided", True)
    cv = MEL.create_material_expression(m, unreal.MaterialExpressionCameraVectorWS, -900, 0)
    cu = MEL.create_material_expression(m, unreal.MaterialExpressionCustom, -650, 0)
    cu.set_editor_property("code", "float3 d = -normalize(V); float3 b = float3(d.x, -d.y, d.z);\n"
                           "float u = atan2(b.y, -b.x) / (2*3.14159265) + 0.5; float v = acos(clamp(b.z,-1,1)) / 3.14159265;\n"
                           "return float2(frac(u + 0.25), v);")
    cu.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT2)
    ci = unreal.CustomInput()
    ci.set_editor_property("input_name", "V")
    cu.set_editor_property("inputs", [ci])
    MEL.connect_material_expressions(cv, "", cu, "V")
    tx = MEL.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, -350, 0)
    tx.set_editor_property("parameter_name", "Sky")
    sky = EAL.load_asset(tex_path("sky"))
    if sky:
        tx.set_editor_property("texture", sky)
        tx.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    MEL.connect_material_expressions(cu, "", tx, "UVs")
    sc = MEL.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -350, 250)
    sc.set_editor_property("parameter_name", "Scale")
    sc.set_editor_property("default_value", 683.0)
    mul = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -100, 50)
    MEL.connect_material_expressions(tx, "RGB", mul, "A")
    MEL.connect_material_expressions(sc, "", mul, "B")
    MEL.connect_material_property(mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m, False)
    return m


def mi(name, parent):
    path = f"{DEST}/Materials/MI/{name}"
    if EAL.does_asset_exist(path):
        return EAL.load_asset(path)
    f = unreal.MaterialInstanceConstantFactoryNew()
    m = AT.create_asset(name, f"{DEST}/Materials/MI", unreal.MaterialInstanceConstant, f)
    MEL.set_material_instance_parent(m, parent)
    return m


def stage_materials():
    t = time.time()
    baked, glass = master_baked(), master_glass()
    for a in ASSETS:
        sm = find_mesh(a)
        if sm is None:
            continue
        m = mi("MI_" + a["asset"], baked)
        for ch, pname in (("base", "BaseColor"), ("orm", "ORM"), ("normal", "Normal"), ("emit", "Emissive")):
            rel = a.get("tex", {}).get(ch)
            if rel:
                tx = EAL.load_asset(tex_path(os.path.splitext(os.path.basename(rel))[0]))
                if tx:
                    MEL.set_material_instance_texture_parameter_value(m, pname, tx)
        if a.get("emissive"):
            MEL.set_material_instance_scalar_parameter_value(m, "EmissiveScale", a["emissive_scale"] * scene["lm_per_w"])
        EAL.save_loaded_asset(m, False)
        mats = [m]
        for k, g in enumerate(a.get("glass", [])):
            gm = mi(f"MI_{a['asset']}_glass{k}", glass)
            c = g["color"]
            MEL.set_material_instance_vector_parameter_value(gm, "Color", unreal.LinearColor(c[0], c[1], c[2], 1))
            MEL.set_material_instance_scalar_parameter_value(gm, "Roughness", g["roughness"])
            EAL.save_loaded_asset(gm, False)
            mats.append(gm)
        n = sm.get_num_sections(0)
        for i in range(n):
            sm.set_material(i, mats[min(i, len(mats) - 1)])
        if n != len(mats):
            warn(f"{a['asset']}: {n} sections vs {len(mats)} materials")
        EAL.save_loaded_asset(sm, False)
    REPORT["timings"]["materials_s"] = round(time.time() - t)


# ------------------------------------------------------------------ level

def V(v):
    return unreal.Vector(v[0], v[1], v[2])


def rot_fu(f, u):
    return unreal.MathLibrary.make_rot_from_xz(V(f), V(u))


def spawn_mesh(eas, sm, loc, rot):
    """spawn_actor_from_object returns None in the pythonscript commandlet (no actor factory); spawn by class."""
    act = eas.spawn_actor_from_class(unreal.StaticMeshActor, loc, rot)
    act.static_mesh_component.set_static_mesh(sm)
    return act


def stage_level():
    t = time.time()
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    lpath = f"{DEST}/{LEVEL}"
    # delete_asset on a map silently fails in the commandlet: remove the .umap file itself (nothing has loaded it yet).
    umap = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir()),
                        lpath[len("/Game/"):] + ".umap")
    if os.path.exists(umap):
        os.remove(umap)
        unreal.AssetRegistryHelpers.get_asset_registry().scan_files_synchronous([umap], True)
    if not les.new_level(lpath):
        raise RuntimeError(f"new_level failed for {lpath}")
    by = {a["asset"]: a for a in scene["assets"]}
    meshes = {}
    n = 0
    for p in scene["placements"]:
        a = by.get(p["asset"])
        if a is None:
            continue
        if p["asset"] not in meshes:
            meshes[p["asset"]] = find_mesh(a)
        sm = meshes[p["asset"]]
        if sm is None:
            continue
        q = p["quat"]
        rot = unreal.Quat(q[0], q[1], q[2], q[3]).rotator()
        act = spawn_mesh(eas, sm, V(p["loc"]), rot)
        act.set_actor_scale3d(V(p["scale"]))
        act.set_actor_label(p["name"])
        act.set_folder_path("Meshes")
        c = act.static_mesh_component
        c.set_editor_property("cast_shadow", p.get("shadow", True))
        if not p.get("camera_visible", True):
            c.set_editor_property("visible_in_ray_tracing", True)
            c.set_editor_property("hidden_in_game", True)
        n += 1
    log(f"level: {n} mesh actors")
    # Lights.
    nl = 0
    for L in scene["lights"]:
        loc = V(L["loc"])
        rot = rot_fu(L["forward"], L["up"])
        if L["type"] == "POINT":
            act = eas.spawn_actor_from_class(unreal.PointLight, loc, rot)
        elif L["type"] == "SPOT":
            act = eas.spawn_actor_from_class(unreal.SpotLight, loc, rot)
        elif L["type"] == "AREA":
            act = eas.spawn_actor_from_class(unreal.RectLight, loc, rot)
        elif L["type"] == "SUN":
            act = eas.spawn_actor_from_class(unreal.DirectionalLight, loc, rot)
        else:
            warn(f"light type {L['type']} skipped ({L['name']})")
            continue
        act.set_actor_label(L["name"])
        act.set_folder_path("Lights")
        c = act.light_component
        c.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        c.set_light_color(unreal.LinearColor(*L["color"], 1.0), True)
        if L["type"] == "SUN":
            c.set_editor_property("intensity", L["lux"])
            c.set_editor_property("light_source_angle", L.get("angle_deg", 0.5))
        else:
            c.set_editor_property("intensity_units", unreal.LightUnits.CANDELAS)
            c.set_editor_property("intensity", L["candela"])
            c.set_editor_property("attenuation_radius", L["attenuation_radius"])
        if L["type"] in ("POINT", "SPOT"):
            c.set_editor_property("source_radius", L["source_radius"])
            c.set_editor_property("soft_source_radius", 0.0)
        if L["type"] == "SPOT":
            c.set_editor_property("outer_cone_angle", L["outer_cone"])
            c.set_editor_property("inner_cone_angle", L["inner_cone"])
        if L["type"] == "AREA":
            c.set_editor_property("source_width", max(L["width"], 1.0))
            c.set_editor_property("source_height", max(L["height"], 1.0))
            spread = L.get("spread_deg", 180)
            c.set_editor_property("barn_door_angle", min(spread / 2, 88.0))
            c.set_editor_property("barn_door_length", 0.0 if spread >= 179 else 20.0)
        c.set_editor_property("cast_shadows", L["cast_shadows"])
        c.set_editor_property("specular_scale", L["specular"])
        c.set_editor_property("diffuse_scale", L["diffuse"])
        c.set_editor_property("volumetric_scattering_intensity", L["volume"])
        nl += 1
    log(f"level: {nl} lights")
    # Cameras.
    for C in scene["cameras"]:
        act = eas.spawn_actor_from_class(unreal.CineCameraActor, V(C["loc"]), rot_fu(C["forward"], C["up"]))
        act.set_actor_label(C["name"])
        act.set_folder_path("Cameras")
        cc = act.get_cine_camera_component()
        fb = cc.get_editor_property("filmback")
        fb.set_editor_property("sensor_width", C["sensor_width_mm"])
        fb.set_editor_property("sensor_height", C["sensor_height_mm"])
        cc.set_editor_property("filmback", fb)
        cc.set_editor_property("current_focal_length", C["lens_mm"])
        cc.set_editor_property("current_aperture", C["dof"]["fstop"] if C["dof"]["enabled"] else 22.0)
        fs = cc.get_editor_property("focus_settings")
        fs.set_editor_property("focus_method", unreal.CameraFocusMethod.MANUAL if C["dof"]["enabled"] else unreal.CameraFocusMethod.DISABLE)
        fs.set_editor_property("manual_focus_distance", C["dof"]["focus_cm"])
        cc.set_editor_property("focus_settings", fs)
        if any(abs(s) > 1e-4 for s in C["shift"]):
            warn(f"{C['name']}: lens shift {C['shift']} has no CineCamera equivalent")
    # Sky dome + sky light.
    w = scene.get("world") or {}
    sky_mat = master_sky() if EAL.does_asset_exist(tex_path("sky")) else None
    if sky_mat:
        dome = spawn_mesh(eas, unreal.load_asset("/Engine/EngineMeshes/Sphere"), unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
        dome.set_actor_scale3d(unreal.Vector(4000, 4000, 4000))
        dome.set_actor_label("SkyDome")
        dome.static_mesh_component.set_material(0, sky_mat)
        dome.static_mesh_component.set_editor_property("cast_shadow", False)
    sl = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 500), unreal.Rotator(0, 0, 0))
    sl.set_actor_label("SkyLight")
    slc = sl.get_component_by_class(unreal.SkyLightComponent)
    slc.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
    slc.set_editor_property("real_time_capture", True)
    slc.set_editor_property("source_type", unreal.SkyLightSourceType.SLS_CAPTURED_SCENE)
    slc.set_editor_property("intensity", 1.0)
    # Fog: the largest low-density volume becomes the height fog; the rest become local fog volumes.
    vols = scene.get("volumes", {})
    haze = max(vols.items(), key=lambda kv: kv[1]["bounds_ue"]["extent"][0] * kv[1]["bounds_ue"]["extent"][1], default=(None, None))
    fog = eas.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    fog.set_actor_label("HeightFog")
    fc = fog.component
    if haze[1]:
        h = haze[1]
        d = [max(x, 1e-6) for x in h["density"]]
        z0 = h["bounds_m"]["lo"][2]
        z1 = h["bounds_m"]["hi"][2]
        zs = [z0 + f * (z1 - z0) for f in h["levels"]]
        k = math.log(d[0] / d[-1]) / max(zs[-1] - zs[0], 0.1)  # per metre
        fog.set_actor_location(unreal.Vector(0, 0, zs[0] * 100), False, False)
        # UE height fog: extinction per cm = FogDensity / 1000 -> per metre FogDensity / 10; falloff per cm = F / 1000.
        fc.set_editor_property("fog_density", d[0] * 10.0)
        fc.set_editor_property("fog_height_falloff", k * 10.0)
        fc.set_editor_property("enable_volumetric_fog", True)
        fc.set_editor_property("volumetric_fog_scattering_distribution", min(h["anisotropy"], 0.9))
        al = h["albedo"]
        fc.set_editor_property("volumetric_fog_albedo", unreal.Color(r=int(al[0] * 255), g=int(al[1] * 255), b=int(al[2] * 255), a=255))
        mr = w.get("mean_radiance", [0.02, 0.02, 0.03])
        fc.set_editor_property("fog_inscattering_luminance", unreal.LinearColor(mr[0] * 683, mr[1] * 683, mr[2] * 683, 1))
        REPORT["haze"] = {"source": haze[0], "fog_density": d[0] * 10, "falloff": k * 10}
    for name, v in vols.items():
        if name == haze[0] or v.get("claimed_by_fx"):
            continue  # effects (flames, plumes) are Niagara now: an LFV can neither move nor take their shape
        b = v["bounds_ue"]
        lf = eas.spawn_actor_from_class(unreal.LocalFogVolume, V(b["center"]), unreal.Rotator(0, 0, 0))
        lf.set_actor_label("LFV_" + name)
        lf.set_folder_path("Volumes")
        # A local fog volume is a sphere of radius GetBaseVolumeSize() = 500 cm at scale 1, and the proxy collapses the
        # scale to the max axis (LocalFogVolumeSceneProxy.cpp): scale uniformly to the box's largest half-extent.
        r_cm = max(b["extent"])
        lf.set_actor_scale3d(unreal.Vector(1, 1, 1) * (r_cm / 500.0))
        lc = lf.get_component_by_class(unreal.LocalFogVolumeComponent)
        dens = max(v["density"])
        emit = max(v["emission"])
        # RadialFogExtinction is the optical depth straight through the centre (unit-sphere integral): sigma x 2r.
        lc.set_editor_property("radial_fog_extinction", dens * 2 * r_cm / 100.0)
        lc.set_editor_property("height_fog_extinction", 0.0)
        al = v["albedo"]
        lc.set_editor_property("fog_albedo", unreal.LinearColor(al[0], al[1], al[2], 1))
        lc.set_editor_property("fog_phase_g", min(v["anisotropy"], 0.9))
        if emit > 0 and v.get("emission_color"):
            ec = v["emission_color"]
            lc.set_editor_property("radial_fog_extinction", max(dens, 0.01) * 2 * r_cm / 100.0)
            # fog_emissive is luminance: emission per metre x 683 (lm/W, as for every other emitter).
            lc.set_editor_property("fog_emissive", unreal.LinearColor(ec[0] * emit * 683, ec[1] * emit * 683, ec[2] * emit * 683, 1))
        if v.get("animated"):
            warn(f"volume {name}: animated procedural density baked to a static local fog volume")
    # Post-process (grade).
    g = scene["grade"]
    ppv = eas.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    ppv.set_actor_label("Grade")
    ppv.set_editor_property("unbound", True)
    s = ppv.settings
    def ov(k, v):
        s.set_editor_property("override_" + k, True)
        s.set_editor_property(k, v)
    ov("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL)
    ov("auto_exposure_apply_physical_camera_exposure", False)
    bias = g["exposure"] - math.log2(scene["lm_per_w"]) + EXPO_OFF
    ov("auto_exposure_bias", bias)
    glare = next((n for n in g.get("compositor", []) if "Glare" in n["type"]), None)
    if glare:
        ov("bloom_intensity", float(glare["inputs"].get("Strength", 0.35)))
        ov("bloom_threshold", -1.0)
    ff = g.get("ffmpeg") or {}
    if "vignette_angle_rad" in ff:
        ov("vignette_intensity", min(1.0, ff["vignette_angle_rad"] / (math.pi / 4) * 0.45))
    if "chromatic_px" in ff:
        ov("scene_fringe_intensity", 0.6)
    if "grain_strength" in ff:
        ov("film_grain_intensity", ff["grain_strength"] / 100.0)
    lut = EAL.load_asset(tex_path("lut_grade"))
    if lut:
        ov("color_grading_lut", lut)
        ov("color_grading_intensity", 1.0)
    ov("motion_blur_amount", 0.0)
    ppv.settings = s
    REPORT["exposure_bias"] = bias
    # Player start at the first hero camera for standalone perf runs.
    hero = next((c for c in scene["cameras"] if c["name"] == "cam_street"), scene["cameras"][0] if scene["cameras"] else None)
    if hero:
        ps = eas.spawn_actor_from_class(unreal.PlayerStart, V(hero["loc"]), rot_fu(hero["forward"], [0, 0, 1]))
        ps.set_actor_label("PlayerStart_" + hero["name"])
    if not les.save_current_level():
        unreal.EditorLoadingAndSavingUtils.save_map(unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world(), lpath)
    REPORT["timings"]["level_s"] = round(time.time() - t)
    REPORT["actors"] = {"meshes": n, "lights": nl, "cameras": len(scene["cameras"])}


# ------------------------------------------------------------------ effects (NIAGARA.md ยง2)

def fx_params(fx):
    p = dict(fx.get("params", {}))
    for key in ("type:" + fx["type"], fx["id"]):
        p.update(FX_OVR.get(key, {}))
    return p


def place_fx(eas, fx, systems):
    path = fx["template"]
    if path not in systems:
        systems[path] = unreal.load_asset(path)
        if systems[path] is None:
            warn(f"fx template missing: {path}")
    sysasset = systems[path]
    if sysasset is None:
        return None
    t = fx["transform"]
    act = eas.spawn_actor_from_class(unreal.NiagaraActor, V(t["loc"]), unreal.Quat(*t["quat"]).rotator())
    act.set_actor_label("FX_" + fx["id"])
    act.set_folder_path("FX")
    nc = act.get_editor_property("niagara_component")
    nc.set_asset(sysasset, True)                                  # 1. asset first: set_asset resets overrides
    params, types = fx_params(fx), fx.get("param_types", {})
    for k, v in params.items():                                   # 2. typed user parameters
        ty = types.get(k, "float")
        if ty == "float":
            nc.set_variable_float(k, float(v))
        elif ty == "int":
            nc.set_variable_int(k, int(v))
        elif ty == "bool":
            nc.set_variable_bool(k, bool(v))
        elif ty == "vec3":
            nc.set_variable_vec3(k, V(v))
        elif ty == "pos":
            nc.set_variable_position(k, V(v))
        elif ty == "color":
            nc.set_variable_linear_color(k, unreal.LinearColor(v[0], v[1], v[2], v[3] if len(v) > 3 else 1.0))
    nc.set_random_seed_offset(int(fx["seed"]) & 0x7FFFFFFF)       # 3. determinism
    bl = fx.get("bounds_local") or {"min": [-e for e in fx["bounds_ue"]["extent"]], "max": fx["bounds_ue"]["extent"]}
    nc.set_system_fixed_bounds(unreal.Box(V(bl["min"]), V(bl["max"])))   # 4. fixed bounds, local space
    fps = fx["time"].get("fps", 24)
    ticks = int(math.ceil(fx["time"]["preroll_s"] * fps))
    nc.set_editor_property("override_warmup_settings", True)      # 5. pre-roll to steady state on activation
    nc.set_editor_property("warmup_tick_delta", 1.0 / fps)
    nc.set_editor_property("warmup_tick_count", ticks)
    try:
        nc.set_editor_property("allow_scalability", False)        # cinematic: never culled by an effect type
    except Exception:
        pass
    # 6. verify: a wrong name or type is a silent no-op, so read every parameter back.
    getters = {"float": nc.get_variable_float, "int": nc.get_variable_int, "bool": nc.get_variable_bool,
               "vec3": nc.get_variable_vec3, "pos": nc.get_variable_position, "color": nc.get_variable_color}
    bad = []
    for k in params:
        try:
            r = getters[types.get(k, "float")](k)
            ok = r[1] if isinstance(r, tuple) else r is not None
        except Exception:
            ok = False
        if not ok:
            bad.append(k)
    rec = {"id": fx["id"], "type": fx["type"], "template": path, "params_set": len(params), "params_invalid": bad,
           "bounds": [list(bl["min"]), list(bl["max"])], "bounds_readback": str(nc.get_system_fixed_bounds())[:200],
           "warmup_ticks": ticks, "seed": int(fx["seed"]) & 0x7FFFFFFF,
           "overrides": {k: v for k, v in params.items() if fx.get("params", {}).get(k) != v}}
    if bad:
        REPORT.setdefault("errors", []).append(f"{fx['id']}: user params not on {path}: {bad}")
        log("ERROR", fx["id"], "invalid params", bad)
    REPORT.setdefault("fx", []).append(rec)
    return act


def stage_fx():
    t = time.time()
    fxs = [f for f in scene.get("fx", []) if f.get("technique") in ("niagara", "niagara_flipbook") and f.get("template")]
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les.load_level(f"{DEST}/{LEVEL}")
    for a in eas.get_all_level_actors():   # rerunnable on its own: drop the previous pass's effects
        if a.get_actor_label().startswith("FX_"):
            eas.destroy_actor(a)
    systems = {}
    n = sum(1 for fx in fxs if place_fx(eas, fx, systems))
    skipped = [f["id"] for f in scene.get("fx", []) if f not in fxs]
    if skipped:
        warn(f"fx not placed (technique not handled here): {skipped}")
    if not les.save_current_level():
        unreal.EditorLoadingAndSavingUtils.save_map(unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world(), f"{DEST}/{LEVEL}")
    log(f"fx: {n} niagara actors")
    REPORT["timings"]["fx_s"] = round(time.time() - t)


def key_flicker(seq, eas, fps):
    """Light flicker sampled by the exporter (fx[].flicker): a float track on the light component's intensity."""
    lights = {a.get_actor_label(): a for a in eas.get_all_level_actors() if isinstance(a, unreal.Light)}
    for fx in scene.get("fx", []):
        fl = fx.get("flicker")
        if not fl or fl["target"] not in lights:
            continue
        lc = lights[fl["target"]].light_component
        base = lc.get_editor_property("intensity")
        try:
            b = seq.add_possessable(lc)
            tr = b.add_track(unreal.MovieSceneFloatTrack)
            tr.set_property_name_and_path("Intensity", "Intensity")
            sec = tr.add_section()
            sec.set_range(0, len(fl["values"]))
            ch = sec.get_all_channels()[0]
            for i, v in enumerate(fl["values"]):
                ch.add_key(unreal.FrameNumber(i), base * v)
            REPORT.setdefault("flicker", []).append({"light": fl["target"], "keys": len(fl["values"])})
        except Exception as e:
            warn(f"flicker track on {fl['target']} failed: {e}")


def stage_sequences():
    """One single-shot LevelSequence per scene camera (camera cut bound to the CineCameraActor) plus a saved MRQ
    primary config, so a still or clip renders headless with:
      UnrealEditor-Cmd <uproject> <map> -game -LevelSequence=<SEQ> -MoviePipelineConfig=<CFG> -RenderOffscreen ..."""
    t = time.time()
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    lpath = f"{DEST}/{LEVEL}"
    les.load_level(lpath)
    fps = scene["grade"].get("fps", 24)
    for C in scene["cameras"]:
        cam = next((a for a in eas.get_all_level_actors() if a.get_actor_label() == C["name"]), None)
        if cam is None:
            continue
        sp = f"{DEST}/Sequences/SEQ_{C['name']}"
        if EAL.does_asset_exist(sp):
            EAL.delete_asset(sp)
        seq = AT.create_asset(f"SEQ_{C['name']}", f"{DEST}/Sequences", unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
        seq.set_display_rate(unreal.FrameRate(fps, 1))
        seq.set_playback_start(0)
        seq.set_playback_end(max(48, CLIP_FRAMES))
        b = seq.add_possessable(cam)
        try:
            track = seq.add_track(unreal.MovieSceneCameraCutTrack)
        except Exception:
            track = seq.add_master_track(unreal.MovieSceneCameraCutTrack)
        sec = track.add_section()
        sec.set_range(0, max(48, CLIP_FRAMES))
        bid = unreal.MovieSceneObjectBindingID()
        bid = seq.get_binding_id(b) if hasattr(seq, "get_binding_id") else unreal.MovieSceneSequenceExtensions.get_binding_id(seq, b)
        sec.set_camera_binding_id(bid)
        key_flicker(seq, eas, fps)
        EAL.save_loaded_asset(seq, False)
    # MRQ configs: MRQ_Still = deferred + PNG (UE tone curve + grade LUT); MRQ_Linear = EXR with the tone curve off
    # (scene-linear, already exposed) so Blender's AgX view transform can be applied to the Unreal lighting.
    res = scene["grade"].get("resolution", [1920, 804])
    # Engine warm-up must also cover the longest effect pre-roll (NIAGARA.md ง2.4), on top of the component warm-up.
    warm = max([64] + [int(math.ceil(f["time"]["preroll_s"] * fps * 1.5)) for f in scene.get("fx", [])])
    for name, linear in (("MRQ_Still", False), ("MRQ_Linear", True), ("MRQ_Clip", False)):
        cp = f"{DEST}/MRQ/{name}"
        if EAL.does_asset_exist(cp):
            EAL.delete_asset(cp)
        cfg = AT.create_asset(name, f"{DEST}/MRQ", unreal.MoviePipelinePrimaryConfig, None)
        if cfg is None:
            warn("could not create MoviePipelinePrimaryConfig asset")
            continue
        cfg.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPassBase)
        if linear:
            cfg.find_or_add_setting_by_class(unreal.MoviePipelineImageSequenceOutput_EXR)
            col = cfg.find_or_add_setting_by_class(unreal.MoviePipelineColorSetting)
            col.set_editor_property("disable_tone_curve", True)
        else:
            cfg.find_or_add_setting_by_class(unreal.MoviePipelineImageSequenceOutput_PNG)
        cfg.find_or_add_setting_by_class(unreal.MoviePipelineGameOverrideSetting)
        out = cfg.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
        out.output_directory = unreal.DirectoryPath(os.environ.get("ANYSCENE_MRQ_OUT", os.path.join(EXPORT, "..", "compare", "mrq")).replace("\\", "/"))
        out.file_name_format = "{sequence_name}" + ("_linear" if linear else "") + ".{frame_number}"
        out.output_resolution = unreal.IntPoint(res[0], res[1])
        out.use_custom_playback_range = True
        out.custom_start_frame, out.custom_end_frame = 0, (CLIP_FRAMES if name == "MRQ_Clip" else 1)
        aa = cfg.find_or_add_setting_by_class(unreal.MoviePipelineAntiAliasingSetting)
        aa.override_anti_aliasing = True
        aa.anti_aliasing_method = unreal.AntiAliasingMethod.AAM_TSR
        aa.temporal_sample_count = 8
        aa.engine_warm_up_count = warm
        aa.use_camera_cut_for_warm_up = False
        aa.render_warm_up_frames = True
        EAL.save_loaded_asset(cfg, False)
    REPORT["timings"]["sequences_s"] = round(time.time() - t)


for st in STAGES:
    log("stage", st)
    {"textures": stage_textures, "meshes": stage_meshes, "materials": stage_materials, "level": stage_level,
     "fx": stage_fx, "sequences": stage_sequences}[st]()
REPORT["total_s"] = round(time.time() - T0)
json.dump(REPORT, open(os.path.join(EXPORT, "build_report.json"), "w"), indent=1)
log("done", json.dumps(REPORT)[:2000])
