"""Rebuild an AnyScene export (export_blend.py -> scene.json + GLBs + baked textures) as an Unreal level.

Headless (no editor window), from a shell:
  UnrealEditor-Cmd.exe <project>.uproject -run=pythonscript -script="<path>/build_level.py" -unattended -nosplash -nop4
Configuration comes from environment variables (the pythonscript commandlet does not pass script args reliably):
  ANYSCENE_EXPORT  export folder holding scene.json            (required)
  ANYSCENE_DEST    content root, default /Game/AnyScene/HK
  ANYSCENE_LEVEL   level name, default L_HK
  ANYSCENE_STAGES  comma list of: textures,meshes,materials,level,spawn,fx,sequences (default: all; "lighttex" is part of
                   textures: gobo images and IES profiles)
  ANYSCENE_ONLY    comma list of asset names to (re)import (testing)
  ANYSCENE_NANITE_TRIS  Nanite on for meshes above this triangle count (default 2000; glass meshes never)
  ANYSCENE_MESH_BATCH   Interchange imports in flight per wait (default 16; lower it when memory is tight)
  ANYSCENE_EXPOSURE_OFFSET  extra EV added to the computed manual exposure (calibration)
  ANYSCENE_COLLIDE_MIN_CM  props smaller than this (largest dimension, cm) get no collision (default 25)
  ANYSCENE_PLAYERSTART  "keep" = the spawn stage leaves an existing PlayerStart alone (collision only)
  ANYSCENE_HERO    PlayerStart camera (alias ANYSCENE_HERO_CAM); default the .blend's active camera, then cam_street
  ANYSCENE_LOOK    JSON {"pp": {...}, "light": {...}} overriding the real-time look settings (LOOK below)
  ANYSCENE_FX_TYPES  Niagara effect types to place (default "steam,fire,rain"; "all" = every classified type, see NIAGARA.md)
  ANYSCENE_FX_OVERRIDES  optional JSON {fx id | "type:<type>": {UserParam: value}} applied on top of scene.json fx params
                   (look-match tuning; TOGGLE.md "overrides.json")
  ANYSCENE_CLIP_FRAMES  length of the MRQ_Clip config and of every camera sequence (default 96 = 4 s at 24 fps)
  ANYSCENE_DOLLY   "camA>camB:frames[:name]" (or "camA>fwd150:frames") ;-separated: extra moving-camera sequences
  ANYSCENE_MRQ_RES WxH for the MRQ configs (default the scene's render resolution)
  ANYSCENE_MRQ_OUT MRQ output folder (default <export>/../compare/mrq)
  ANYSCENE_REPORT  build report path (default <export>/build_report.json)

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
STAGES = os.environ.get("ANYSCENE_STAGES", "textures,meshes,materials,level,spawn,fx,sequences").split(",")
ONLY = set(x for x in os.environ.get("ANYSCENE_ONLY", "").split(",") if x)
NANITE_TRIS = int(os.environ.get("ANYSCENE_NANITE_TRIS", "2000"))
MESH_BATCH = int(os.environ.get("ANYSCENE_MESH_BATCH", "16"))  # Interchange imports in flight per wait (memory)
EXPO_OFF = float(os.environ.get("ANYSCENE_EXPOSURE_OFFSET", "0"))
FX_OVR = json.load(open(os.environ["ANYSCENE_FX_OVERRIDES"])) if os.environ.get("ANYSCENE_FX_OVERRIDES") else {}
CLIP_FRAMES = int(os.environ.get("ANYSCENE_CLIP_FRAMES", "96"))
# Niagara effect types the fx stage places (light flicker is always keyed). Steam, fire (round-2 pack) and rain are
# verified in renders; drips, dust, sparks, smoke and fountain stay opt-in until a scene verifies them ("all" = every
# type). See CHANGELOG.md "Fx: fire and rain on by default".
FX_TYPES = set(x for x in os.environ.get("ANYSCENE_FX_TYPES", "steam,fire,rain").split(",") if x)
# Real-time look settings written into every level (grade post-process volume and lights), so they travel with the
# level into any project. ANYSCENE_LOOK='{"pp": {...}, "light": {...}}' overrides single keys (calibration runs).
LOOK = {
    "pp": {
        # Mirror-quality Lumen reflections on the front glass layer (otherwise only the blurry radiance cache).
        "lumen_front_layer_translucency_reflections": True,
        # Tight interiors: small props (cups, bottles, stools) get Lumen cards and occlude GI; fewer final gather
        # leaks and less noise in corners. Defaults are 1.0.
        "lumen_scene_detail": 2.0,
        "lumen_final_gather_quality": 2.0,
    },
    "light": {},
    # Glass (master_glass / glass_params): share of (IOR - 1) used as screen-space refraction on solid glass, and
    # the translucency pass ("before_dof" | "after_dof").
    "glass": {"refraction_scale": 0.35, "pass": "before_dof"},
}
# Blender AgX looks (datafiles/colormanagement/config.ocio): GradingPrimary, log style, contrast around middle grey
# + saturation. UE's ColorContrast is the same operation (pow(x / 0.18, c) in scene linear, before the tone curve).
# UE's default filmic curve already matches AgX *High Contrast* (fitted on a grey ramp, -5..+2.5 stops: best UE
# contrast 0.99, rms 2/255), so each look maps to contrast c_look / 1.4 (Base 0.71, Medium High 0.86, Very High 1.12;
# every fit within ~2/255). Base Contrast scenes were rendered ~40% too contrasty before.
AGX_LOOKS = {"Very High Contrast": (1.57, 0.9), "High Contrast": (1.4, 0.95), "Medium High Contrast": (1.2, 1.0),
             "Base Contrast": (1.0, 1.0), "None": (1.0, 1.0), "Medium Low Contrast": (0.9, 1.05),
             "Low Contrast": (0.8, 1.1), "Very Low Contrast": (0.7, 1.15)}
UE_FILMIC_AGX_CONTRAST = 1.4
for _k, _v in json.loads(os.environ.get("ANYSCENE_LOOK", "{}")).items():
    LOOK[_k].update(_v)

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
        # 4K bakes: without a GC per chunk the commandlet held every imported texture and ran out of memory
        # (~550 of 796 on a 32 GB box shared with other editors).
        unreal.SystemLibrary.collect_garbage()
        log(f"textures {min(i + 64, len(todo))}/{len(todo)} ({time.time() - t:.0f}s)")
    # A crash inside a chunk leaves imported textures without their settings: re-check the linear channels.
    fixed = 0
    lin = [(ch, tex_path(os.path.splitext(os.path.basename(rel))[0])) for a in ASSETS for ch, rel in a.get("tex", {}).items() if ch in ("orm", "normal")]
    for k, (ch, p) in enumerate(lin):
        d = unreal.EditorAssetLibrary.find_asset_data(p)
        if not d.is_valid():
            continue
        tx = d.get_asset()
        if tx and tx.get_editor_property("srgb"):
            tx.set_editor_property("srgb", False)
            tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS if ch == "orm" else unreal.TextureCompressionSettings.TC_NORMALMAP)
            if ch == "normal":
                tx.set_editor_property("flip_green_channel", True)
            EAL.save_loaded_asset(tx, False)
            fixed += 1
        if k % 64 == 63:
            unreal.SystemLibrary.collect_garbage()
    if fixed:
        log(f"textures: fixed settings on {fixed} linear textures")
    stage_light_textures()
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


def gobo_tex_path(rel):
    return f"{DEST}/Gobo/{os.path.splitext(os.path.basename(rel.replace(chr(92), '/')))[0]}"


def ies_path(rel):
    return f"{DEST}/IES/{os.path.splitext(os.path.basename(rel.replace(chr(92), '/')))[0]}"


def stage_light_textures():
    """Gobo images (linear grayscale, wrapping) and IES profiles (TextureLightProfile) referenced by the lights."""
    gobos, ies = {}, {}
    for L in scene["lights"]:
        for lay in (L.get("gobo_fx") or {}).get("layers", []):
            gobos[gobo_tex_path(lay["image"])] = lay
        if L.get("ies_file"):
            ies[ies_path(L["ies_file"])] = L["ies_file"]
    todo = [os.path.join(EXPORT, lay["image"]) for p, lay in gobos.items() if not EAL.does_asset_exist(p)]
    if todo:
        import_files(todo, f"{DEST}/Gobo")
    for p, lay in gobos.items():
        tx = EAL.load_asset(p)
        if tx is None:
            warn(f"gobo import failed {lay['image']}")
            continue
        lin = lay.get("colorspace", "Non-Color") in ("Non-Color", "Linear Rec.709", "Raw")
        tx.set_editor_property("srgb", not lin)
        tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_GRAYSCALE)
        wrap = unreal.TextureAddress.TA_WRAP if lay.get("extension", "REPEAT") == "REPEAT" else unreal.TextureAddress.TA_CLAMP
        tx.set_editor_property("address_x", wrap)
        tx.set_editor_property("address_y", wrap)
        tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_EFFECTS)
        EAL.save_loaded_asset(tx, False)
    todo = [os.path.join(EXPORT, f) for p, f in ies.items() if not EAL.does_asset_exist(p)]
    if todo:
        import_files(todo, f"{DEST}/IES")
    for p, f in ies.items():
        prof = EAL.load_asset(p) if EAL.does_asset_exist(p) else None
        if prof is None:
            warn(f"IES import failed {f}")
            continue
        EAL.save_loaded_asset(prof, False)  # import tasks run with save=False
    log(f"light textures: {len(gobos)} gobo images, {len(ies)} IES profiles")


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
        if i % MESH_BATCH == MESH_BATCH - 1 or i == len(todo) - 1:
            flush(a)
            unreal.SystemLibrary.collect_garbage()
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

def master_baked(masked=False):
    """M_AnyBaked (opaque) or M_AnyBakedMasked: same graph, opacity mask = ORM.R (baked Principled Alpha)."""
    name = "M_AnyBakedMasked" if masked else "M_AnyBaked"
    path = f"{DEST}/Materials/{name}"
    if EAL.does_asset_exist(path):
        return EAL.load_asset(path)
    m = AT.create_asset(name, f"{DEST}/Materials", unreal.Material, unreal.MaterialFactoryNew())
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
    if masked:
        m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
        # (MaterialExpressionDitherTemporalAA is not exposed to Python in 5.8: plain clip.)
        m.set_editor_property("opacity_mask_clip_value", 0.33)
        MEL.connect_material_property(orm, "R", unreal.MaterialProperty.MP_OPACITY_MASK)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m, False)
    return m


def master_asset(name, version=1):
    """Get or create a master material. Returns (material, build): build is True when the graph must be (re)made.
    A master whose AnySceneVersion tag is older than `version` is rebuilt in place (all expressions deleted), so
    the instances and meshes that reference it keep working; untagged masters count as version 1."""
    path = f"{DEST}/Materials/{name}"
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
        if int(EAL.get_metadata_tag(m, "AnySceneVersion") or 1) >= version:
            return m, False
        MEL.delete_all_material_expressions(m)
        log(f"{name}: rebuilding master in place (v{version})")
    else:
        m = AT.create_asset(name, f"{DEST}/Materials", unreal.Material, unreal.MaterialFactoryNew())
    EAL.set_metadata_tag(m, "AnySceneVersion", str(version))
    return m, True


GLASS_VERSION = 2  # bump when the graph changes: older masters are rebuilt in place


def master_glass():
    """Thin-translucent glass (legacy shading, no Substrate needed): a Fresnel-weighted specular layer (lit, with
    Lumen front-layer reflections) over a coloured transmittance that tints what is behind it, like Cycles'
    transmission. The old diffuse-lit translucent master read as milky plastic: white glass took light like paint.
      Transmittance  colour per pass (Blender glass colour); thicker at grazing angles (1/NoV)
      Specular       F0 / 0.08 from the IOR (0.5 at IOR 1.5)
      Roughness      Blender roughness; Lumen blurs the reflection, the background stays sharp (no transmission blur)
      Opacity        frost layer coverage: 0 for clear glass, up to ~0.35 for rough glass (FrostColor, diffuse-lit)
      Refraction     IOR for solid glass (water glasses, bottles, domes); 1 = none for thin panes and windows"""
    m, build = master_asset("M_AnyGlass", GLASS_VERSION)
    if not build:
        return m
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_THIN_TRANSLUCENT)
    # Thin translucency requires "Surface ForwardShading", which is TLM_SURFACE_PER_PIXEL_LIGHTING in Python
    # (TLM_SURFACE is "Surface TranslucencyVolume": the master then fails to compile and renders as the grey default).
    m.set_editor_property("translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    m.set_editor_property("two_sided", True)
    m.set_editor_property("refraction_method", unreal.RefractionMode.RM_INDEX_OF_REFRACTION)
    # Before DOF (the 5.8 default is after): glass in a defocused plane blurs with what is behind it (macro shots).
    tpass = {"before_dof": unreal.MaterialTranslucencyPass.MTP_BEFORE_DOF, "after_dof": unreal.MaterialTranslucencyPass.MTP_AFTER_DOF}
    for k, v in (("allow_front_layer_translucency", True), ("translucency_pass", tpass[LOOK["glass"]["pass"]])):
        try:
            m.set_editor_property(k, v)
        except Exception as ex:  # noqa: BLE001
            warn(f"M_AnyGlass: {k}: {ex}")

    def p(cls, name, v, y):
        n = MEL.create_material_expression(m, cls, -500, y)
        n.set_editor_property("parameter_name", name)
        n.set_editor_property("default_value", v)
        return n
    tr = p(unreal.MaterialExpressionVectorParameter, "Transmittance", unreal.LinearColor(1, 1, 1, 1), 0)
    fc = p(unreal.MaterialExpressionVectorParameter, "FrostColor", unreal.LinearColor(0.8, 0.8, 0.8, 1), -200)
    r = p(unreal.MaterialExpressionScalarParameter, "Roughness", 0.02, 200)
    sp = p(unreal.MaterialExpressionScalarParameter, "Specular", 0.5, 300)
    o = p(unreal.MaterialExpressionScalarParameter, "Opacity", 0.0, 400)
    rf = p(unreal.MaterialExpressionScalarParameter, "Refraction", 1.0, 500)
    MEL.connect_material_property(fc, "", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(r, "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.connect_material_property(sp, "", unreal.MaterialProperty.MP_SPECULAR)
    MEL.connect_material_property(o, "", unreal.MaterialProperty.MP_OPACITY)
    MEL.connect_material_property(rf, "", unreal.MaterialProperty.MP_REFRACTION)
    out = MEL.create_material_expression(m, unreal.MaterialExpressionThinTranslucentMaterialOutput, -100, 0)
    MEL.connect_material_expressions(tr, "", out, "TransmittanceColor")
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m, False)
    return m


def glass_params(a, g):
    """M_AnyGlass instance values for one Blender glass slot (see master_glass)."""
    b = a.get("check_bounds")
    thin = b is not None and min(abs(b["max"][i] - b["min"][i]) for i in range(3)) < 2.5  # panes, windows, doors
    ior = g.get("ior", 1.5)
    rough = g["roughness"]
    return {"Transmittance": g["color"][:3], "FrostColor": [0.8 * x for x in g["color"][:3]],
            "Roughness": max(rough, 0.02),
            "Specular": min(1.0, ((ior - 1) / (ior + 1)) ** 2 / 0.08),
            "Opacity": min(0.35, max(0.0, 0.7 * (rough - 0.05))),
            # Refraction in IOR mode bends the screen-space background by the surface normal; full strength smears
            # whole cups, a third of (IOR - 1) keeps the edge darkening/bending that makes solid glass read as glass.
            "Refraction": 1.0 if thin else 1.0 + (ior - 1.0) * LOOK["glass"]["refraction_scale"], "thin": thin}


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


GOBO_CH = ("LocX", "LocY", "Rot", "ScaleX", "ScaleY")
GOBO_KEYS = {"LocX": "loc_x", "LocY": "loc_y", "Rot": "rot", "ScaleX": "scale_x", "ScaleY": "scale_y"}


def mpc_time():
    """Material parameter collection holding the gobo clock: GoboUseSeq = 0 -> real time (Time node + per-light
    TimeOffset); 1 -> GoboTime, keyed by the level sequences so MRQ frames land on the exact Blender frame."""
    path = f"{DEST}/Materials/MPC_AnyTime"
    if EAL.does_asset_exist(path):
        return EAL.load_asset(path)
    m = AT.create_asset("MPC_AnyTime", f"{DEST}/Materials", unreal.MaterialParameterCollection, unreal.MaterialParameterCollectionFactoryNew())
    ps = []
    for n in ("GoboTime", "GoboUseSeq"):
        p = unreal.CollectionScalarParameter()
        p.set_editor_property("parameter_name", n)
        p.set_editor_property("default_value", 0.0)
        ps.append(p)
    m.set_editor_property("scalar_parameters", ps)
    EAL.save_loaded_asset(m, False)
    return m


def master_gobo():
    """Light-function master for projected-texture (gobo) spots, matching Blender's TexCoord-Normal x/z, y/z
    projector: two texture layers, each with Mapping location / Z rotation / scale animated as
    c0 + v t + A1 sin(2 pi f1 t + p1) + A2 sin(2 pi f2 t + p2) (per channel: vector params <L>_<Ch> = (c0, v, A1, f1)
    and <L>_<Ch>P = (p1, A2, f2, p2)), combined as Gain * (WA a + WB b + Bias)^Gamma, divided by Peak (light
    functions are clamped to 0..1; the light's intensity carries the peak)."""
    path = f"{DEST}/Materials/M_AnyGobo"
    if EAL.does_asset_exist(path):
        return EAL.load_asset(path)
    m = AT.create_asset("M_AnyGobo", f"{DEST}/Materials", unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("material_domain", unreal.MaterialDomain.MD_LIGHT_FUNCTION)
    mpc = mpc_time()
    gobo_default = next((EAL.load_asset(gobo_tex_path(lay["image"])) for L in scene["lights"]
                         for lay in (L.get("gobo_fx") or {}).get("layers", []) if EAL.does_asset_exist(gobo_tex_path(lay["image"]))), None)
    if gobo_default is None:
        warn("M_AnyGobo: no imported gobo texture to use as the sampler default")

    def scalar(name, v, x, y):
        n = MEL.create_material_expression(m, unreal.MaterialExpressionScalarParameter, x, y)
        n.set_editor_property("parameter_name", name)
        n.set_editor_property("default_value", v)
        return n

    def vec(name, v, x, y):
        n = MEL.create_material_expression(m, unreal.MaterialExpressionVectorParameter, x, y)
        n.set_editor_property("parameter_name", name)
        n.set_editor_property("default_value", unreal.LinearColor(*v))
        return n

    # Clock: lerp(Time + TimeOffset, GoboTime, GoboUseSeq)
    tm = MEL.create_material_expression(m, unreal.MaterialExpressionTime, -2400, -600)
    toff = scalar("TimeOffset", 0.0, -2400, -500)
    add = MEL.create_material_expression(m, unreal.MaterialExpressionAdd, -2200, -560)
    MEL.connect_material_expressions(tm, "", add, "A")
    MEL.connect_material_expressions(toff, "", add, "B")
    cps = []
    for i, n in enumerate(("GoboTime", "GoboUseSeq")):
        c = MEL.create_material_expression(m, unreal.MaterialExpressionCollectionParameter, -2400, -400 + 100 * i)
        c.set_editor_property("collection", mpc)
        c.set_editor_property("parameter_name", n)
        cps.append(c)
    lt = MEL.create_material_expression(m, unreal.MaterialExpressionLinearInterpolate, -2000, -500)
    MEL.connect_material_expressions(add, "", lt, "A")
    MEL.connect_material_expressions(cps[0], "", lt, "B")
    MEL.connect_material_expressions(cps[1], "", lt, "Alpha")
    uv = MEL.create_material_expression(m, unreal.MaterialExpressionTextureCoordinate, -2400, -800)
    tan = scalar("TanOuter", 0.8391, -2400, -700)

    def ch(c):
        return (f"({c}.x + {c}.y*T + {c}.z*sin(6.2831853*{c}.w*T + {c}P.x) + {c}P.y*sin(6.2831853*{c}P.z*T + {c}P.w))")

    code = ("float2 p = (UV * 2.0 - 1.0) * Tan;\n"
            "float2 d = float2(-p.y, -p.x);  // Blender light-local (x/z, y/z)\n"
            f"float lx = {ch('LocX')}; float ly = {ch('LocY')}; float r = {ch('Rot')};\n"
            f"float2 s = d * float2({ch('ScaleX')}, {ch('ScaleY')});\n"
            "float c = cos(r); float sn = sin(r);\n"
            "float2 q = float2(s.x * c - s.y * sn, s.x * sn + s.y * c) + float2(lx, ly);\n"
            "return float2(q.x, -q.y);  // Blender image v runs bottom-up")
    samples = []
    defaults = {"LocX": (0, 0, 0, 0), "LocY": (0, 0, 0, 0), "Rot": (0, 0, 0, 0), "ScaleX": (1, 0, 0, 0), "ScaleY": (1, 0, 0, 0)}
    camv = MEL.create_material_expression(m, unreal.MaterialExpressionCameraVectorWS, -2400, 300)
    lfs = scalar("LFScale", 1024.0, -2400, 400)
    srad = scalar("SourceRadius", 0.0, -2400, 500)
    pbias = scalar("PenumbraBias", -1.0, -2400, 600)
    for li, L in enumerate(("A", "B")):
        y0 = li * 1400
        cu = MEL.create_material_expression(m, unreal.MaterialExpressionCustom, -1500, y0)
        cu.set_editor_property("code", code)
        cu.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT2)
        cu.set_editor_property("description", f"GoboUV_{L}")
        names = ["UV", "Tan", "T"] + [n for c in GOBO_CH for n in (c, c + "P")]
        ins = []
        for n in names:
            ci = unreal.CustomInput()
            ci.set_editor_property("input_name", n)
            ins.append(ci)
        cu.set_editor_property("inputs", ins)
        MEL.connect_material_expressions(uv, "", cu, "UV")
        MEL.connect_material_expressions(tan, "", cu, "Tan")
        MEL.connect_material_expressions(lt, "", cu, "T")
        vecs = {}
        for k, c in enumerate(GOBO_CH):
            a = vec(f"{L}_{c}", defaults[c], -1900, y0 + k * 220)
            b = vec(f"{L}_{c}P", (0, 0, 0, 0), -1900, y0 + k * 220 + 110)
            MEL.connect_material_expressions(a, "RGBA", cu, c)
            MEL.connect_material_expressions(b, "RGBA", cu, c + "P")
            vecs[c] = a
        # Penumbra: Cycles evaluates the gobo from every point of the light's disk, so the pattern blurs by the
        # angle SourceRadius / distance (tan units), times the mapping scale in texture space. Light functions are
        # point-projected; pick the mip whose texel matches that blur. CameraVector in a light function is the
        # light-space vector divided by LightFunctionScale (LightFunctionPixelShader.usf).
        mipc = MEL.create_material_expression(m, unreal.MaterialExpressionCustom, -1500, y0 + 1150)
        # Blur radius R texels = s * r / d * TexSize. A disk of radius R is roughly a Gaussian of sigma R/2, which
        # mip log2(R) - 1 (bilinear) approximates; PenumbraBias (default -1) is the look-match knob.
        mipc.set_editor_property("code", "float d = length(LV) * LFScale; if (d < 1.0) return 0.0;\n"
                                 "float s = max(abs(SX.x), abs(SY.x));\n"
                                 "return clamp(log2(max(s * SourceRadius / d * TexSize, 1.0)) + Bias, 0.0, 8.0);")
        mipc.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT1)
        mipc.set_editor_property("description", f"GoboPenumbraMip_{L}")
        ins = []
        for n in ("LV", "LFScale", "SourceRadius", "TexSize", "SX", "SY", "Bias"):
            ci = unreal.CustomInput()
            ci.set_editor_property("input_name", n)
            ins.append(ci)
        mipc.set_editor_property("inputs", ins)
        MEL.connect_material_expressions(camv, "", mipc, "LV")
        MEL.connect_material_expressions(lfs, "", mipc, "LFScale")
        MEL.connect_material_expressions(srad, "", mipc, "SourceRadius")
        MEL.connect_material_expressions(scalar(f"TexSize{L}", 2048.0, -1900, y0 + 1250), "", mipc, "TexSize")
        MEL.connect_material_expressions(vecs["ScaleX"], "RGBA", mipc, "SX")
        MEL.connect_material_expressions(vecs["ScaleY"], "RGBA", mipc, "SY")
        MEL.connect_material_expressions(pbias, "", mipc, "Bias")
        tx = MEL.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, -1100, y0)
        tx.set_editor_property("parameter_name", f"Tex{L}")
        tx.set_editor_property("mip_value_mode", unreal.TextureMipValueMode.TMVM_MIP_LEVEL)
        if not MEL.connect_material_expressions(mipc, "", tx, "Level"):  # pin is "Level" in TMVM_MIP_LEVEL mode
            warn("M_AnyGobo: could not connect the penumbra mip")
        # The default must match the sampler type (linear grayscale), or the master fails to compile and every
        # light function silently does nothing (same trap as the ORM default in M_AnyBaked).
        tx.set_editor_property("texture", gobo_default)
        tx.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE)
        MEL.connect_material_expressions(cu, "", tx, "UVs")
        w = scalar(f"W{L}", 0.5, -1100, y0 + 250)
        mul = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -800, y0)
        MEL.connect_material_expressions(tx, "R", mul, "A")
        MEL.connect_material_expressions(w, "", mul, "B")
        samples.append(mul)
    cu = MEL.create_material_expression(m, unreal.MaterialExpressionCustom, -500, 0)
    cu.set_editor_property("code", "return saturate(Gain * pow(max(A + B + Bias, 0.0), Gamma) * InvPeak);")
    cu.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    cu.set_editor_property("description", "GoboCombine")
    ins = []
    for n in ("A", "B", "Bias", "Gamma", "Gain", "InvPeak"):
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        ins.append(ci)
    cu.set_editor_property("inputs", ins)
    MEL.connect_material_expressions(samples[0], "", cu, "A")
    MEL.connect_material_expressions(samples[1], "", cu, "B")
    for n, v, yy in (("Bias", 0.0, 300), ("Gamma", 1.0, 400), ("Gain", 1.0, 500), ("InvPeak", 1.0, 600)):
        MEL.connect_material_expressions(scalar(n, v, -800, yy), "", cu, n)
    MEL.connect_material_property(cu, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m, False)
    return m


def gobo_mi(L):
    """Material instance of M_AnyGobo for one light's gobo_fx entry."""
    g = L["gobo_fx"]
    m = mi("MI_Gobo_" + L["name"], master_gobo())
    lays = g["layers"][:2]
    if len(g["layers"]) > 2:
        warn(f"{L['name']}: {len(g['layers'])} gobo layers, master takes 2")
    if g.get("coord") != "normal_projective":
        warn(f"{L['name']}: gobo coordinates '{g.get('coord')}' approximated as the Normal x/z, y/z projector")
    fps = g.get("fps", 24.0)
    MEL.set_material_instance_scalar_parameter_value(m, "TanOuter", math.tan(math.radians(L["outer_cone"])))
    MEL.set_material_instance_scalar_parameter_value(m, "TimeOffset", scene.get("frame", 0) / fps)
    cb = g["combine"]
    w = list(cb["weights"][:2]) + [0.0] * (2 - len(lays))
    for li, Ln in enumerate(("A", "B")):
        lay = lays[min(li, len(lays) - 1)]
        tx = EAL.load_asset(gobo_tex_path(lay["image"]))
        if tx:
            MEL.set_material_instance_texture_parameter_value(m, f"Tex{Ln}", tx)
        MEL.set_material_instance_scalar_parameter_value(m, f"W{Ln}", w[li] if li < len(lays) else 0.0)
        mp = lay.get("mapping") or {}
        for c in GOBO_CH:
            e = mp.get(GOBO_KEYS[c]) or {"c0": 1.0 if c.startswith("Scale") else 0.0, "v": 0.0, "sines": []}
            s = (e.get("sines") or []) + [[0.0, 0.0, 0.0]] * 2
            MEL.set_material_instance_vector_parameter_value(m, f"{Ln}_{c}", unreal.LinearColor(e["c0"], e["v"], s[0][0], s[0][1]))
            MEL.set_material_instance_vector_parameter_value(m, f"{Ln}_{c}P", unreal.LinearColor(s[0][2], s[1][0], s[1][1], s[1][2]))
    MEL.set_material_instance_scalar_parameter_value(m, "Bias", cb["bias"])
    MEL.set_material_instance_scalar_parameter_value(m, "Gamma", cb["gamma"])
    MEL.set_material_instance_scalar_parameter_value(m, "Gain", cb["gain"])
    MEL.set_material_instance_scalar_parameter_value(m, "InvPeak", 1.0 / max(g["peak"], 1e-6))
    MEL.set_material_instance_scalar_parameter_value(m, "SourceRadius", L.get("source_radius", 0.0))
    MEL.set_material_instance_scalar_parameter_value(m, "LFScale", 1024.0)
    for li, Ln in enumerate(("A", "B")):
        lay = lays[min(li, len(lays) - 1)]
        MEL.set_material_instance_scalar_parameter_value(m, f"TexSize{Ln}", float(max(lay.get("size") or [2048])))
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
    masked = master_baked(masked=True) if any(a.get("alpha") for a in ASSETS) else None
    for a in ASSETS:
        sm = find_mesh(a)
        if sm is None:
            continue
        m = mi("MI_" + a["asset"], masked if a.get("alpha") else baked)
        MEL.set_material_instance_parent(m, masked if a.get("alpha") else baked)  # existing MI: reparent
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
            MEL.set_material_instance_parent(gm, glass)
            gp = glass_params(a, g)
            for pn in ("Transmittance", "FrostColor"):
                c = gp[pn]
                MEL.set_material_instance_vector_parameter_value(gm, pn, unreal.LinearColor(c[0], c[1], c[2], 1))
            for pn in ("Roughness", "Specular", "Opacity", "Refraction"):
                MEL.set_material_instance_scalar_parameter_value(gm, pn, gp[pn])
            REPORT.setdefault("glass", {})[f"{a['asset']}_glass{k}"] = {k2: (round(v, 3) if isinstance(v, float) else v)
                                                                       for k2, v in gp.items() if k2 in ("thin", "Opacity", "Refraction", "Roughness")}
            EAL.save_loaded_asset(gm, False)
            mats.append(gm)
        if a.get("sections"):
            # The GLB keeps only the materials its faces use (an all-glass pane has just the glass section).
            mats = [mats[min(s, len(mats) - 1)] for s in a["sections"]]
        elif len(a.get("glass", [])) >= len(a.get("slots", [])) > 0:
            # Exports from before "sections": a glass-only mesh lost its unused BAKED slot 0 in the GLB, so its
            # only sections are glass.
            mats = mats[1:]
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


LFV_BASE_CM = 500.0  # ULocalFogVolumeComponent::GetBaseVolumeSize()


def lfv_tiles(b, max_aspect=1.5):
    """Cover a box (center, half-extent cm) with spheres: one sphere of radius max(half-extent) when the box is
    roughly cubic, else a row of spheres of radius = the smaller of the two larger half-extents along the long axis
    (a long flat box must not become one giant ball). Returns [(center, radius_cm)]."""
    e = list(b["extent"])
    c = list(b["center"])
    order = sorted(range(3), key=lambda i: -e[i])
    big, mid = e[order[0]], e[order[1]]
    if big <= max_aspect * mid:
        return [(c, max(e))]
    r = mid
    n = max(1, math.ceil(big / r))
    out = []
    for k in range(n):
        p = list(c)
        p[order[0]] = c[order[0]] - big + r + (2 * big - 2 * r) * (k / max(n - 1, 1))
        out.append((p, r))
    return out


def vignette_intensity(angle, w, h):
    """UE vignette intensity matching ffmpeg's vignette=angle (finish.sh). ffmpeg multiplies the display-encoded
    frame by cos(angle * d / dmax)^4; UE multiplies scene linear by 1 / (1 + I^2 r^2)^2 before the tone curve, where
    a display factor f is about f^1.41 in linear (UE filmic: 1.64x display code per stop around middle grey).
    Least-squares fit over the frame (the old linear guess, 0.45 at PI/4, was about 40% too weak)."""
    a = h / w
    s = math.sqrt(2) / math.sqrt(1 + a * a)
    pts = []
    for j in range(20):
        for i in range(40):
            px, py = (i + 0.5) / 20 - 1, (j + 0.5) / 10 - 1
            dn = math.hypot(px * w / 2, py * h / 2) / math.hypot(w / 2, h / 2)
            pts.append(((px * s) ** 2 + (py * a * s) ** 2, max(math.cos(angle * dn), 0) ** 4))
    pts = [(r2, f ** 1.41) for r2, f in pts]
    return min((sum((1 / (1 + I * I * r2) ** 2 - t) ** 2 for r2, t in pts), I) for I in (k * 0.005 for k in range(300)))[1]


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
        for k, v in LOOK["light"].items():
            c.set_editor_property(k, v)
        if L.get("gobo_fx") and L["type"] == "SPOT":
            # Light functions are clamped to 0..1: the material divides the pattern by its peak, the light carries it.
            g = L["gobo_fx"]
            c.set_editor_property("intensity", L["candela"] * g["peak"])
            c.set_editor_property("light_function_material", gobo_mi(L))
            c.set_editor_property("light_function_scale", unreal.Vector(1024, 1024, 1024))  # uniform: x/z ratio intact
            c.set_editor_property("light_function_fade_distance", 1.0e6)
            ec = g.get("emission_color") or [1, 1, 1]
            if max(ec) > 0 and any(abs(x - 1) > 1e-3 for x in ec):
                col = [a * b for a, b in zip(L["color"], ec)]
                mx = max(col)
                c.set_light_color(unreal.LinearColor(*(x / mx for x in col), 1.0), True)
                c.set_editor_property("intensity", L["candela"] * g["peak"] * mx)
            REPORT.setdefault("gobos", {})[L["name"]] = {"peak": g["peak"], "mean": g.get("mean"), "layers": len(g["layers"])}
        elif L.get("gobo_fx"):
            warn(f"{L['name']}: gobo on a {L['type']} light not converted (spot only)")
        if L.get("ies_file"):
            prof = EAL.load_asset(ies_path(L["ies_file"]))
            if prof:
                c.set_editor_property("ies_texture", prof)
                # Cycles' IES node normalises the profile and the light power carries the brightness: keep candela.
                c.set_editor_property("use_ies_brightness", False)
            else:
                warn(f"{L['name']}: IES profile {L['ies_file']} not imported")
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
        if C.get("exposure"):  # per-camera exposure offset on top of the grade's manual exposure
            pp = cc.get_editor_property("post_process_settings")
            pp.set_editor_property("override_auto_exposure_bias", True)
            pp.set_editor_property("auto_exposure_bias", scene["grade"]["exposure"] + C["exposure"] - math.log2(scene["lm_per_w"]) + EXPO_OFF)
            cc.set_editor_property("post_process_settings", pp)
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
        for k, (ctr, r_cm) in enumerate(lfv_tiles(v["bounds_ue"])):
            lf = eas.spawn_actor_from_class(unreal.LocalFogVolume, V(ctr), unreal.Rotator(0, 0, 0))
            lf.set_actor_label(f"LFV_{name}" + (f"_{k}" if k else ""))
            lf.set_folder_path("Volumes")
            # LocalFogVolume: base radius 500 cm (GetBaseVolumeSize), the proxy turns the scale into a sphere from
            # the max axis (LocalFogVolumeSceneProxy.cpp:34), so scale uniformly to the wanted radius.
            sc_ = r_cm / LFV_BASE_CM
            lf.set_actor_scale3d(unreal.Vector(sc_, sc_, sc_))
            lc = lf.get_component_by_class(unreal.LocalFogVolumeComponent)
            dens = max(v["density"])  # Blender density = extinction per metre
            emit = max(v["emission"])
            path_m = 2.0 * r_cm / 100.0
            # RadialFogExtinction is the optical depth straight through the centre (LocalFogVolumeCommon.ush),
            # independent of size: sigma (1/m) x path length (m).
            tau = max(dens * path_m, 1e-3)  # emissive-only volumes still need a little medium (coverage > 0)
            lc.set_editor_property("radial_fog_extinction", tau)
            lc.set_editor_property("height_fog_extinction", 0.0)
            al = v["albedo"]
            lc.set_editor_property("fog_albedo", unreal.LinearColor(al[0], al[1], al[2], 1))
            lc.set_editor_property("fog_phase_g", min(v["anisotropy"], 0.9))
            if emit > 0 and v.get("emission_color"):
                ec = v["emission_color"]
                # UE adds FogEmissive x coverage (1 - e^-tau) (LocalFogVolumeCommon.ush). Cycles through the centre:
                # 683 x emit x (1 - e^-(sigma p)) / sigma nits (683 x emit x p when sigma -> 0). Match the two.
                lc_nits = 683 * emit * ((1 - math.exp(-dens * path_m)) / dens if dens > 1e-6 else path_m)
                E = lc_nits / (1 - math.exp(-tau))
                lc.set_editor_property("fog_emissive", unreal.LinearColor(ec[0] * E, ec[1] * E, ec[2] * E, 1))
            REPORT.setdefault("local_fog", []).append({"volume": name, "radius_cm": round(r_cm, 1), "scale": round(sc_, 4),
                                                       "radial_fog_extinction": round(dens * path_m, 5)})
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
        ov("vignette_intensity", vignette_intensity(ff["vignette_angle_rad"], *g.get("resolution", [1920, 804])))
    if "chromatic_px" in ff:
        ov("scene_fringe_intensity", 0.6)
    if "grain_strength" in ff:
        ov("film_grain_intensity", ff["grain_strength"] / 100.0)
    lut = EAL.load_asset(tex_path("lut_grade"))
    if lut:
        ov("color_grading_lut", lut)
        ov("color_grading_intensity", 1.0)
    ov("motion_blur_amount", 0.0)
    look = g.get("look") or "None"
    agx = AGX_LOOKS.get(look.split(" - ", 1)[-1]) if g.get("view_transform") == "AgX" else None
    if agx:
        c = agx[0] / UE_FILMIC_AGX_CONTRAST
        ov("color_contrast", unreal.Vector4(c, c, c, 1.0))
        ov("color_saturation", unreal.Vector4(agx[1], agx[1], agx[1], 1.0))
        REPORT["look"] = {"view": f"AgX / {look}", "ue_contrast": round(c, 3), "saturation": agx[1]}
    else:
        warn(f"view transform {g.get('view_transform')!r} / look {look!r}: no tone match (UE filmic as is)")
    for k, v in LOOK["pp"].items():
        if isinstance(v, str) and "." in v:  # enum from JSON, e.g. "LumenRayLightingModeOverride.HIT_LIGHTING"
            en, mem = v.split(".", 1)
            v = getattr(getattr(unreal, en), mem)
        ov(k, v)
    ppv.settings = s
    REPORT["exposure_bias"] = bias
    # Collision and the PlayerStart are the "spawn" stage (it needs the saved level and cooked collision).
    if not les.save_current_level():
        unreal.EditorLoadingAndSavingUtils.save_map(unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world(), lpath)
    REPORT["timings"]["level_s"] = round(time.time() - t)
    REPORT["actors"] = {"meshes": n, "lights": nl, "cameras": len(scene["cameras"])}


def key_gobo_time(seq, n_frames, frame0=None):
    """Drive MPC_AnyTime from the sequence: GoboUseSeq = 1 and GoboTime = (Blender frame0 + f) / fps keyed on every
    frame, so MRQ frame f shows the gobo state of Blender frame frame0 + f (temporal sub-samples interpolate)."""
    if not any(L.get("gobo_fx") for L in scene["lights"]):
        return
    mpc = mpc_time()
    fps = scene["grade"].get("fps", 24)
    frame0 = scene.get("frame", 0) if frame0 is None else frame0
    try:
        tr = seq.add_track(unreal.MovieSceneMaterialParameterCollectionTrack)
    except Exception:
        tr = seq.add_master_track(unreal.MovieSceneMaterialParameterCollectionTrack)
    tr.set_editor_property("mpc", mpc)
    sec = tr.add_section()
    sec.set_range(0, n_frames)
    tick = seq.get_tick_resolution()
    tpf = tick.numerator / tick.denominator / fps
    lin = unreal.MovieSceneKeyInterpolation.LINEAR
    sec.add_scalar_parameter_key("GoboUseSeq", unreal.FrameNumber(0), 1.0, lin)
    for f in range(n_frames + 1):
        sec.add_scalar_parameter_key("GoboTime", unreal.FrameNumber(round(f * tpf)), (frame0 + f) / fps, lin)


def make_dolly(spec, eas, fps):
    """ANYSCENE_DOLLY="camA>camB:frames[:name]": a CineCamera moving linearly from camera A's transform to camera
    B's (lens from A) over N frames, as SEQ_<name> for an MRQ clip."""
    a, rest = spec.split(">", 1)
    parts = rest.split(":")
    b, n = parts[0], int(parts[1]) if len(parts) > 1 else 96
    name = parts[2] if len(parts) > 2 else f"dolly_{a}"
    ca = next((C for C in scene["cameras"] if C["name"] == a), None)
    if b.startswith("fwd") and ca is not None:  # "camA>fwd150": push in 150 cm along camera A's view axis
        d = float(b[3:])
        cb = dict(ca, loc=[ca["loc"][i] + ca["forward"][i] * d for i in range(3)])
    else:
        cb = next((C for C in scene["cameras"] if C["name"] == b), None)
    if ca is None or cb is None:
        warn(f"dolly {spec}: camera missing")
        return
    old = next((x for x in eas.get_all_level_actors() if x.get_actor_label() == name), None)
    if old:
        eas.destroy_actor(old)
    ra, rb = rot_fu(ca["forward"], ca["up"]), rot_fu(cb["forward"], cb["up"])
    act = eas.spawn_actor_from_class(unreal.CineCameraActor, V(ca["loc"]), ra)
    act.set_actor_label(name)
    act.set_folder_path("Cameras")
    cc = act.get_cine_camera_component()
    fb = cc.get_editor_property("filmback")
    fb.set_editor_property("sensor_width", ca["sensor_width_mm"])
    fb.set_editor_property("sensor_height", ca["sensor_height_mm"])
    cc.set_editor_property("filmback", fb)
    cc.set_editor_property("current_focal_length", ca["lens_mm"])
    cc.set_editor_property("current_aperture", 22.0)
    fs = cc.get_editor_property("focus_settings")
    fs.set_editor_property("focus_method", unreal.CameraFocusMethod.DISABLE)
    cc.set_editor_property("focus_settings", fs)
    sp = f"{DEST}/Sequences/SEQ_{name}"
    if EAL.does_asset_exist(sp):
        EAL.delete_asset(sp)
    seq = AT.create_asset(f"SEQ_{name}", f"{DEST}/Sequences", unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
    seq.set_display_rate(unreal.FrameRate(fps, 1))
    seq.set_playback_start(0)
    seq.set_playback_end(n)
    bnd = seq.add_possessable(act)
    tt = bnd.add_track(unreal.MovieScene3DTransformTrack)
    ts = tt.add_section()
    ts.set_range(0, n)
    chs = ts.get_all_channels()
    lin = unreal.MovieSceneKeyInterpolation.LINEAR

    def unwrap(x, y):
        while y - x > 180:
            y -= 360
        while y - x < -180:
            y += 360
        return y
    va = [ca["loc"][0], ca["loc"][1], ca["loc"][2], ra.roll, ra.pitch, ra.yaw]
    vb = [cb["loc"][0], cb["loc"][1], cb["loc"][2], unwrap(ra.roll, rb.roll), unwrap(ra.pitch, rb.pitch), unwrap(ra.yaw, rb.yaw)]
    for i in range(6):
        chs[i].add_key(unreal.FrameNumber(0), va[i], interpolation=lin)
        chs[i].add_key(unreal.FrameNumber(n), vb[i], interpolation=lin)
    for i in range(6, 9):
        chs[i].add_key(unreal.FrameNumber(0), 1.0)
    try:
        ct = seq.add_track(unreal.MovieSceneCameraCutTrack)
    except Exception:
        ct = seq.add_master_track(unreal.MovieSceneCameraCutTrack)
    cs = ct.add_section()
    cs.set_range(0, n)
    cs.set_camera_binding_id(seq.get_binding_id(bnd) if hasattr(seq, "get_binding_id") else unreal.MovieSceneSequenceExtensions.get_binding_id(seq, bnd))
    key_gobo_time(seq, n)
    EAL.save_loaded_asset(seq, False)
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    log(f"dolly {name}: {a} -> {b}, {n} frames")


# ------------------------------------------------------------------ effects (NIAGARA.md §2)

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
    fxs = [f for f in scene.get("fx", []) if f.get("technique") in ("niagara", "niagara_flipbook") and f.get("template")
           and ("all" in FX_TYPES or f["type"] in FX_TYPES)]
    if not fxs:
        log("fx: nothing to place (ANYSCENE_FX_TYPES=" + ",".join(sorted(FX_TYPES)) + ")")
        return
    if not EAL.does_directory_exist("/Game/AnySceneFX"):
        warn("fx: /Game/AnySceneFX is not in this project (build it with fx_pack.py or copy it in); no effects placed")
        return
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les.load_level(f"{DEST}/{LEVEL}")
    for a in eas.get_all_level_actors():   # rerunnable on its own: drop the previous pass's effects
        if a.get_actor_label().startswith("FX_"):
            eas.destroy_actor(a)
    systems = {}
    n = sum(1 for fx in fxs if place_fx(eas, fx, systems))
    skipped = [f.get("id", f.get("name")) for f in scene.get("fx", []) if f not in fxs]
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


# ------------------------------------------------------------------ spawn (collision + PlayerStart)

COLLIDE_MIN_CM = float(os.environ.get("ANYSCENE_COLLIDE_MIN_CM", "25"))  # smaller props get no collision


def hero_camera():
    """ANYSCENE_HERO (or ANYSCENE_HERO_CAM), else the .blend's active camera (scene.json "active_camera"), else
    cam_street, else the first camera."""
    want = [os.environ.get("ANYSCENE_HERO") or os.environ.get("ANYSCENE_HERO_CAM"), scene.get("active_camera"), "cam_street"]
    return next((c for w in want if w for c in scene["cameras"] if c["name"] == w), scene["cameras"][0] if scene["cameras"] else None)


def stage_spawn():
    """Make a built level walkable in PIE / -game. Rerunnable on its own (ANYSCENE_STAGES=spawn) on any level built
    from this export, e.g. after the level was copied into another project.
      Collision: meshes are imported without collision primitives, so the pawn fell through every floor. Set
      geometry gets complex-as-simple collision (exact, nothing to generate); props smaller than
      ANYSCENE_COLLIDE_MIN_CM, glass-only meshes, alpha-cut decals and the sky dome get NoCollision.
      PlayerStart: exactly one per level, on the floor under the hero camera (line trace) + 92 cm, with the camera's
      yaw, nudged up to 6 m sideways (staying at floor level) until the default pawn (35 cm sphere) overlaps nothing. (It used to sit at the camera's
      height, in the air or inside a prop, and some levels had none, so the pawn spawned at the origin.)"""
    t = time.time()
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    lpath = f"{DEST}/{LEVEL}"
    les.load_level(lpath)
    by = {a["asset"]: a for a in scene["assets"]}
    by_label = {p["name"]: p["asset"] for p in scene["placements"]}
    done, on, off = set(), 0, 0
    for act in eas.get_all_level_actors():
        if not isinstance(act, unreal.StaticMeshActor):
            continue
        c = act.static_mesh_component
        sm = c.static_mesh
        if sm is None:
            continue
        a = by.get(by_label.get(act.get_actor_label(), "")) or by.get(sm.get_name())
        _, ext = act.get_actor_bounds(False)
        size = 2 * max(ext.x, ext.y, ext.z)
        if (a is None or size < COLLIDE_MIN_CM or (a.get("glass") and not a.get("tex")) or a.get("alpha")):
            c.set_collision_profile_name("NoCollision")
            off += 1
            continue
        if sm.get_path_name() not in done:
            done.add(sm.get_path_name())
            bs = sm.get_editor_property("body_setup")
            if bs is None:
                warn(f"{sm.get_name()}: no body setup, no collision")
            else:
                bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
                EAL.save_loaded_asset(sm, False)
        c.set_collision_profile_name("BlockAll")
        on += 1
    log(f"spawn: collision on {on} actors ({len(done)} meshes), none on {off}")
    rec = {"collision_actors": on, "collision_meshes": len(done), "no_collision_actors": off}
    starts = [a for a in eas.get_all_level_actors() if isinstance(a, unreal.PlayerStart)]
    hero = hero_camera()
    if starts and os.environ.get("ANYSCENE_PLAYERSTART") == "keep":  # a hand-placed start stays
        hero = None
        rec["player_start_kept"] = [a.get_actor_label() for a in starts]
    else:
        for a in starts:
            eas.destroy_actor(a)
    if hero:
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        yaw = rot_fu(hero["forward"], [0, 0, 1]).yaw
        cam = V(hero["loc"])
        vis = unreal.TraceTypeQuery.TRACE_TYPE_QUERY1  # Visibility

        def floor_at(x, y):
            hit = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(x, y, cam.z), unreal.Vector(x, y, cam.z - 3000),
                                                          vis, True, [], unreal.DrawDebugTrace.NONE, True)
            h = hit.to_tuple() if hit is not None else None
            return h[4].z if h and h[0] else None  # (blocking_hit, initial_overlap, time, distance, location, ...)

        def free(p):
            # The pawn GameModeBase spawns (DefaultPawn) is a 35 cm sphere; a full 88 cm character capsule fails in
            # tight sets like the ramen aisle (hanging lamps, wall shelves at head height).
            hit = unreal.SystemLibrary.sphere_trace_single(world, p, p + unreal.Vector(0, 0, 1), 36.0, vis, True, [],
                                                           unreal.DrawDebugTrace.NONE, True)
            h = hit.to_tuple() if hit is not None else None
            if h and h[0] and len(rec.setdefault("blocked_by", [])) < 3:
                rec["blocked_by"].append([h[9].get_actor_label() if h[9] else None, round(h[4].z), bool(h[1])])
            return not (h and h[0])
        # Rings around the camera; the floor is the lowest surface found within 6 m (a trace from eye height can
        # land on a stool or a counter), and only spots at floor level count.
        cands = []
        for r in range(0, 630, 30):
            for k in range(1 if r == 0 else 24):
                ang = 2 * math.pi * k / 24
                x, y = cam.x + r * math.cos(ang), cam.y + r * math.sin(ang)
                z = floor_at(x, y)
                if z is not None:
                    cands.append((r, x, y, z))
        best = None
        if cands:
            z0 = min(c[3] for c in cands)
            low = [c for c in cands if c[3] <= z0 + 20]
            rec["floor"] = {"z": round(z0, 1), "samples": len(cands), "at_floor": len(low),
                            "heights": sorted({round(c[3]) for c in cands})[:12]}
            for r, x, y, z in low:
                if free(unreal.Vector(x, y, z + 92.0)):
                    best = (unreal.Vector(x, y, z + 92.0), r)
                    break
        if best is None:
            z = floor_at(cam.x, cam.y)
            best = (unreal.Vector(cam.x, cam.y, z + 92.0 if z is not None else cam.z), None)
            warn(f"spawn: no free spot within 6 m of {hero['name']}" + ("" if z is not None else ", and no floor under it"))
        ps = eas.spawn_actor_from_class(unreal.PlayerStart, best[0], unreal.Rotator(0, 0, yaw))
        ps.set_actor_label("PlayerStart_" + hero["name"])
        rec.update({"player_start": [round(best[0].x, 1), round(best[0].y, 1), round(best[0].z, 1)], "yaw": round(yaw, 1),
                    "camera": hero["name"], "camera_z": round(cam.z, 1), "nudge_cm": best[1]})
    log("spawn:", json.dumps(rec))
    REPORT["spawn"] = rec
    if not les.save_current_level():
        unreal.EditorLoadingAndSavingUtils.save_map(unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world(), lpath)
    REPORT["timings"]["spawn_s"] = round(time.time() - t)


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
        key_gobo_time(seq, 48)
        key_flicker(seq, eas, fps)
        EAL.save_loaded_asset(seq, False)
    for spec in [s for s in os.environ.get("ANYSCENE_DOLLY", "").split(";") if s]:
        make_dolly(spec, eas, fps)
    # MRQ configs: MRQ_Still = deferred + PNG (UE tone curve + grade LUT); MRQ_Linear = EXR with the tone curve off
    # (scene-linear, already exposed) so Blender's AgX view transform can be applied to the Unreal lighting.
    res = [int(x) for x in os.environ["ANYSCENE_MRQ_RES"].split("x")] if os.environ.get("ANYSCENE_MRQ_RES") else scene["grade"].get("resolution", [1920, 804])
    # MRQ_Clip = MRQ_Still over the sequence's whole playback range (dolly clips).
    # Engine warm-up must also cover the longest effect pre-roll (NIAGARA.md section 2.4), on top of the component warm-up.
    warm = max([64] + [int(math.ceil(f["time"]["preroll_s"] * fps * 1.5)) for f in scene.get("fx", [])
                       if "time" in f and ("all" in FX_TYPES or f.get("type") in FX_TYPES)])
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
        out.use_custom_playback_range = name != "MRQ_Clip"
        out.custom_start_frame, out.custom_end_frame = 0, 1
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
     "fx": stage_fx, "spawn": stage_spawn, "sequences": stage_sequences}[st]()
REPORT["total_s"] = round(time.time() - T0)
json.dump(REPORT, open(os.environ.get("ANYSCENE_REPORT") or os.path.join(EXPORT, "build_report.json"), "w"), indent=1)
log("done", json.dumps(REPORT)[:2000])
