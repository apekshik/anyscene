"""Build the AnySceneFX template pack (/Game/AnySceneFX) from scratch: sprite materials + NS_Fire, NS_Steam, NS_Rain,
NS_Drips, NS_DustMotes, every one exposing the shared User parameters from NIAGARA.md §3, and write templates.json
(the param_types contract build_level.py reads).

Headless, rerunnable (deletes and rebuilds the pack); needs the NiagaraToolsets + ToolsetRegistry plugins enabled:
  UnrealEditor-Cmd <project>.uproject -run=pythonscript -script="<path>/fx_pack.py" -unattended -nosplash -nop4
Env: ANYSCENEFX_ROOT (default /Game/AnySceneFX), ANYSCENEFX_JSON (where templates.json goes, default next to this file),
     ANYSCENEFX_RECIPES (extra recipe folders), ANYSCENEFX_ONLY (comma list of NS_ names to rebuild; others untouched).

Authoring goes through Epic's experimental NiagaraToolsets (unreal.ToolsetRegistry.execute_tool), wrapped in fxlib.py.
Every template starts from the stateful Fountain emitter (SpawnRate, InitializeParticle, ShapeLocation, AddVelocity,
GravityForce, Drag, ScaleColor, Solve) and rewires its inputs to User parameters with links or one-line HLSL.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unreal  # noqa: E402

import fxlib as F  # noqa: E402

ROOT = os.environ.get("ANYSCENEFX_ROOT", "/Game/AnySceneFX")
OUT_JSON = os.environ.get("ANYSCENEFX_JSON", os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates.json"))
EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
REPORT = {"systems": {}, "materials": [], "errors": []}


def log(*a):
    unreal.log_warning("FXPACK " + " ".join(str(x) for x in a))


# ------------------------------------------------------------------ materials

# Shared HLSL helpers for the Custom nodes: value noise + fbm, and a blackbody approximation (Kelvin -> linear RGB).
HELPERS = """struct AFX {
 float h(float2 p) { return frac(sin(dot(p, float2(127.1, 311.7))) * 43758.5453); }
 float n(float2 p) { float2 i = floor(p); float2 f = frac(p); f = f * f * (3.0 - 2.0 * f);
   return lerp(lerp(h(i), h(i + float2(1, 0)), f.x), lerp(h(i + float2(0, 1)), h(i + float2(1, 1)), f.x), f.y); }
 float fbm(float2 p) { return 0.5 * n(p) + 0.25 * n(p * 2.03 + 1.7) + 0.125 * n(p * 4.01 + 3.1); }
 float3 bb(float k) { float t = clamp(k, 1000.0, 12000.0) / 100.0;
   float r = t <= 66.0 ? 1.0 : saturate(1.292936 * pow(t - 60.0, -0.1332047));
   float g = t <= 66.0 ? saturate(0.3900816 * log(t) - 0.6318414) : saturate(1.129891 * pow(t - 60.0, -0.0755148));
   float b = t >= 66.0 ? 1.0 : (t <= 19.0 ? 0.0 : saturate(0.5432068 * log(t - 10.0) - 1.1962541));
   float3 c = float3(r, g, b); return c * c; }
};
AFX X;
"""

# Per material: custom HLSL for (rgb, opacity). Inputs: UV, PC (particle colour rgb), PA (particle alpha), R (particle
# random), T (time), DP (dynamic parameter: x = Intensity, y = Temperature K).
MATS = {
    # Additive flame tongue on a tall sprite (UV.y 0 = top). Colour hotter at the base; Temperature > 0 swaps in blackbody.
    "M_AFX_Flame": dict(blend="ADDITIVE", lit=False, rgb="""
float y = 1.0 - UV.y;
float t = T * 1.6 + R * 17.0;
float d = X.fbm(float2(UV.x * 3.0 + R * 5.0, y * 2.0 - t * 2.2)) - 0.5;
float x = (UV.x - 0.5 + d * 0.25 * y) * 2.0;
float w = lerp(0.85, 0.3, saturate(y));
float across = exp(-3.0 * (x / w) * (x / w));
float along = smoothstep(0.0, 0.15, y) * smoothstep(1.0, 0.45 + d * 0.4, y);
float body = across * along;
float3 col = DP.y > 0 ? X.bb(DP.y * lerp(1.15, 0.8, y)) : PC * lerp(float3(1.25, 1.15, 0.95), float3(0.95, 0.75, 0.65), y);
return col * body * PA * DP.x;""", op="return 1;"),
    # Soft, noisy steam puff. Lit translucent (volumetric non-directional), before DOF, depth-faded.
    "M_AFX_Steam": dict(blend="TRANSLUCENT", lit=True, depth_fade=12.0, rgb="return PC * DP.x;", base="return PC;", op="""
float2 c = UV - 0.5;
float r = length(c) * 2.0;
float a = saturate(1.0 - r); a = a * a * (3.0 - 2.0 * a);
float n = X.fbm(UV * 2.6 + float2(R * 7.1, R * 3.3 + T * 0.12));
return PA * a * saturate(n * 1.8 - 0.3);"""),
    # Velocity-aligned streak (UV.x across, UV.y along), lit with a little emissive so it reads against the dark.
    "M_AFX_Streak": dict(blend="TRANSLUCENT", lit=True, rgb="""
float x = abs(UV.x - 0.5) * 2.0;
float a = saturate(1.0 - x);
return PC * DP.x * a * a;""", base="return PC;", op="""
float x = abs(UV.x - 0.5) * 2.0;
float a = saturate(1.0 - x); a *= a;
return PA * a * saturate(UV.y * 5.0) * saturate((1.0 - UV.y) * 5.0);"""),
    # Round mote.
    "M_AFX_Mote": dict(blend="TRANSLUCENT", lit=True, rgb="return PC * DP.x;", base="return PC;", op="""
float r = length(UV - 0.5) * 2.0;
float a = saturate(1.0 - r);
return PA * a * a;"""),
}


def make_material(name, spec):
    folder = f"{ROOT}/Materials"
    path = f"{folder}/{name}"
    if EAL.does_asset_exist(path):
        # The templates reference their materials and deleting a referenced asset can crash the editor: rebuild the
        # graph in place.
        m = EAL.load_asset(path)
        MEL.delete_all_material_expressions(m)
    else:
        m = AT.create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("blend_mode", getattr(unreal.BlendMode, "BLEND_" + spec["blend"]))
    m.set_editor_property("two_sided", True)
    if spec["lit"]:
        m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
        m.set_editor_property("translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_VOLUMETRIC_NON_DIRECTIONAL)
    else:
        m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    # Foreground plumes in defocused areas (cam_wok) must blur with DOF.
    m.set_editor_property("translucency_pass", unreal.MaterialTranslucencyPass.MTP_BEFORE_DOF)
    MEL.set_material_usage(m, unreal.MaterialUsage.MATUSAGE_NIAGARA_SPRITES)
    y = 0
    def node(cls, x=-900):
        nonlocal y
        y += 160
        return MEL.create_material_expression(m, cls, x, y)
    uv = node(unreal.MaterialExpressionTextureCoordinate)
    pc = node(unreal.MaterialExpressionParticleColor)
    pr = node(unreal.MaterialExpressionParticleRandom)
    tm = node(unreal.MaterialExpressionTime)
    dp = node(unreal.MaterialExpressionDynamicParameter)
    # DynamicParameter defaults (used if the emitter does not write Particles.DynamicMaterialParameter): 1 nit, no blackbody.
    dp.set_editor_property("default_value", unreal.LinearColor(1.0, 0.0, 0.0, 0.0))
    dpm = node(unreal.MaterialExpressionComponentMask)
    dpm.set_editor_property("r", True)
    dpm.set_editor_property("g", True)
    MEL.connect_material_expressions(dp, "RGBA", dpm, "")

    def custom(code, out_type):
        c = node(unreal.MaterialExpressionCustom, -400)
        c.set_editor_property("code", HELPERS + code.strip())
        c.set_editor_property("output_type", out_type)
        ins = []
        for nm in ("UV", "PC", "PA", "R", "T", "DP"):
            ci = unreal.CustomInput()
            ci.set_editor_property("input_name", nm)
            ins.append(ci)
        c.set_editor_property("inputs", ins)
        MEL.connect_material_expressions(uv, "", c, "UV")
        MEL.connect_material_expressions(pc, "", c, "PC")
        MEL.connect_material_expressions(pc, "A", c, "PA")
        MEL.connect_material_expressions(pr, "", c, "R")
        MEL.connect_material_expressions(tm, "", c, "T")
        MEL.connect_material_expressions(dpm, "", c, "DP")
        return c

    MEL.connect_material_property(custom(spec["rgb"], unreal.CustomMaterialOutputType.CMOT_FLOAT3), "",
                                  unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    if spec.get("base"):
        MEL.connect_material_property(custom(spec["base"], unreal.CustomMaterialOutputType.CMOT_FLOAT3), "",
                                      unreal.MaterialProperty.MP_BASE_COLOR)
    if spec["blend"] != "ADDITIVE":
        op = custom(spec["op"], unreal.CustomMaterialOutputType.CMOT_FLOAT1)
        if spec.get("depth_fade"):
            df = node(unreal.MaterialExpressionDepthFade, -150)
            df.set_editor_property("fade_distance_default", spec["depth_fade"])
            MEL.connect_material_expressions(op, "", df, "Opacity")
            op = df
        MEL.connect_material_property(op, "", unreal.MaterialProperty.MP_OPACITY)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m, False)
    REPORT["materials"].append(path)
    return f"{path}.{name}"


# ------------------------------------------------------------------ niagara helpers

NT = {  # Niagara type structs for user variables / linked inputs
    "float": "/Script/Niagara.NiagaraFloat", "int": "/Script/Niagara.NiagaraInt32", "bool": "/Script/Niagara.NiagaraBool",
    "vec3": "/Script/CoreUObject.Vector3f", "vec2": "/Script/CoreUObject.Vector2f", "color": "/Script/CoreUObject.LinearColor",
    "pos": "/Script/Niagara.NiagaraPosition", "vec4": "/Script/CoreUObject.Vector4f",
}
ENUMS = {}


def enum_value(enum_path, want):
    """Enum inputs come back as NewEnumeratorN: resolve a display name (case-insensitive substring) to its entry."""
    if enum_path not in ENUMS:
        info = F.call("UEnum_Info", {"enum": F.ref(enum_path)}, toolset="NiagaraToolsets.NiagaraToolset_Info")
        ENUMS[enum_path] = info
    info = ENUMS[enum_path]
    s = info if isinstance(info, str) else json.dumps(info)
    try:
        d = json.loads(s)
        while isinstance(d, str):
            d = json.loads(d)
    except Exception:
        d = None
    pairs = []
    if isinstance(d, dict):
        vals = d.get("returnValue", d)
        if isinstance(vals, str):
            try:
                vals = json.loads(vals)
            except Exception:
                pass
        if isinstance(vals, dict):
            vals = vals.get("Values", vals.get("values", []))
        for v in vals if isinstance(vals, list) else []:
            if isinstance(v, dict):
                pairs.append((v.get("Name") or v.get("name"), v.get("DisplayName") or v.get("displayName") or ""))
    if not pairs:
        pairs = re.findall(r'"(?:name|enumName)"\s*:\s*"([^"]+)"[^}]*?"display(?:Name)?"\s*:\s*"([^"]*)"', s)
    for nm, disp in pairs:
        if want.lower() == (disp or "").lower():
            return nm, disp
    for nm, disp in pairs:
        if want.lower() in (disp or "").lower() or want.lower() in nm.lower():
            return nm, disp
    raise RuntimeError(f"enum {enum_path}: no value like {want!r} in {pairs} raw={s[:1500]}")


def v_float(x):
    return {"struct": F.ref("/Script/Niagara.NiagaraFloat"), "value": {"value": float(x)}}


def v_bool(b):
    return {"struct": F.ref("/Script/Niagara.NiagaraBool"), "value": {"value": -1 if b else 0}}


def v_int(i):
    return {"struct": F.ref("/Script/Niagara.NiagaraInt32"), "value": {"value": int(i)}}


def v_link(name, typ):
    return {"struct": F.ref("/Script/NiagaraEditor.NiagaraExt_StackInputData_Linked"),
            "value": {"linkedVariable": {"name": name, "type": {"classStructOrEnum": F.ref(NT[typ])}}}}


def v_hlsl(expr):
    return {"struct": F.ref("/Script/NiagaraEditor.NiagaraExt_StackInputData_HlslExpression"), "value": {"hlslExpression": expr}}


class Sys:
    def __init__(self, name, params):
        self.name = name
        self.final = f"{ROOT}/Systems/{name}"
        self.path = f"{self.final}.{name}"
        self.params = params
        self.topo = {}
        self.issues = []
        if EAL.does_asset_exist(self.final):
            # Placed levels reference the templates and deleting (or consolidating) a referenced system crashes the
            # editor or leaves redirectors: rebuild in place instead. Strip every emitter and user variable, keep the asset.
            summ = F.call("GetSystemSummary", {"system": F.ref(self.path)})
            summ = summ.get("returnValue", summ)
            for e in summ.get("emitters", []):
                F.call("RemoveEmitter", {"emitterToRemove": F.item(self.path, e["emitterName"])}, check=False)
            old_uv = [{"name": u["name"], "type": u["type"]} for u in summ.get("userVariables", [])]
            if old_uv:
                F.call("RemoveUserVariables", {"system": F.ref(self.path), "variablesToRemove": old_uv}, check=False)
            log("system", name, "rebuilt in place: removed", len(summ.get("emitters", [])), "emitters,", len(old_uv), "user vars")
        else:
            F.call("CreateNiagaraSystem", {"assetName": name, "assetPath": f"{ROOT}/Systems",
                                           "templateSystem": F.ref("/Niagara/DefaultAssets/DefaultSystem.DefaultSystem")})
            # DefaultSystem ships with a stock "Fountain" emitter: drop it, templates add their own named emitters.
            F.call("RemoveEmitter", {"emitterToRemove": F.item(self.path, "Fountain")}, check=False)
        uv = []
        for k, (t, dv, desc) in params.items():
            if t == "float":
                val = v_float(dv)
            elif t == "int":
                val = v_int(dv)
            elif t == "bool":
                val = v_bool(dv)
            elif t == "color":
                val = {"struct": F.ref("/Script/CoreUObject.LinearColor"), "value": dict(zip("rgba", list(dv) + [1.0] * (4 - len(dv))))}
            else:  # vec3 / pos
                val = {"struct": F.ref(NT[t] if t == "pos" else "/Script/CoreUObject.Vector3f"), "value": dict(zip("xyz", dv))}
            uv.append({"name": k, "type": {"classStructOrEnum": F.ref(NT[t])}, "defaultValue": val, "description": desc})
        try:
            F.call("AddUserVariables", {"system": F.ref(self.path), "variablesToAdd": uv})
        except RuntimeError:
            # Some builds only accept the double-precision Vector struct as a default value: retry vec3 defaults that way.
            for u in uv:
                if u["defaultValue"]["struct"]["refPath"] == "/Script/CoreUObject.Vector3f":
                    u["defaultValue"]["struct"] = F.ref("/Script/CoreUObject.Vector")
            F.call("AddUserVariables", {"system": F.ref(self.path), "variablesToAdd": uv})

    def system_data(self, **kw):
        F.call("SetSystemData", {"system": F.ref(self.path), "systemData": {"propertyValues": json.dumps(kw)}})

    def emitter(self, template, want):
        t = F.call("AddEmitter", {"system": F.ref(self.path), "emitterName": want,
                                  "templateEmitter": F.ref(f"/Niagara/DefaultAssets/Templates/Emitters/{template}.{template}")})
        t = t.get("returnValue", t) if isinstance(t, dict) else t
        name = t["emitterName"] if isinstance(t, dict) and "emitterName" in t else want
        self.topo[name] = t
        return name

    def emitter_data(self, em, **kw):
        F.call("SetEmitterData", {"emitter": F.item(self.path, em), "emitterData": {"propertyValues": json.dumps(kw)}})

    def inputs_of(self, em, script, module):
        t = F.call("GetModuleTopology", {"moduleRef": F.item(self.path, em, script, module)})
        t = t.get("returnValue", t)
        return {i["name"]: i for i in t.get("inputs", [])}

    def set(self, em, script, module, inp, val):
        """val: number | bool | ('link', 'User.X', type) | ('hlsl', expr) | ('enum', display) | raw instanced dict."""
        if isinstance(val, tuple) and val[0] == "enum":
            ins = self.inputs_of(em, script, module)
            if inp not in ins:
                raise RuntimeError(f"{self.name}/{em}/{module}: no input {inp!r}; have {sorted(ins)}")
            ep = ins[inp]["type"]["classStructOrEnum"]["refPath"]
            nm, disp = enum_value(ep, val[1])
            val = {"struct": F.ref("/Script/NiagaraEditor.NiagaraExt_StackInputData_Enum"),
                   "value": {"enum": F.ref(ep), "enumName": nm, "displayName": disp}}
        elif isinstance(val, tuple) and val[0] == "link":
            val = v_link(val[1], val[2])
        elif isinstance(val, tuple) and val[0] == "hlsl":
            val = v_hlsl(val[1])
        elif isinstance(val, bool):
            val = v_bool(val)
        elif isinstance(val, (int, float)):
            val = v_float(val)
        try:
            F.call("SetStackInputData", {"stackInputRef": F.item(self.path, em, script, module, inputs=[inp]), "inputData": val})
        except RuntimeError as e:
            self.issues.append(f"set {em}/{module}/{inp}: {str(e)[:400]}")
            log("ERR", self.name, em, module, inp, str(e)[:400])

    def add_module(self, em, script, asset, before=""):
        t = F.call("AddModule", {"moduleLocationRef": F.item(self.path, em, script, before), "moduleAsset": F.ref(asset)})
        t = t.get("returnValue", t)
        return t["moduleName"], {i["name"]: i for i in t.get("inputs", [])}

    def set_params(self, em, script, entries, before=""):
        """entries: [(Particles.Name, type, hlsl)] -> one SetParameters module.
        AddSetParametersModule accepts an HLSL default without error but stores a garbage literal (seen: a Vector4f
        x = -4.2e36, which blacked out every emissive sprite). So always add with a typed placeholder, rewire each
        entry to its HLSL with SetStackInputData, and read the values back."""
        typed = {"float": v_float(0.0), "int": v_int(0), "bool": v_bool(False),
                 "vec3": {"struct": F.ref("/Script/CoreUObject.Vector3f"), "value": {"x": 0, "y": 0, "z": 0}},
                 "vec4": {"struct": F.ref("/Script/CoreUObject.Vector4f"), "value": {"x": 0, "y": 0, "z": 0, "w": 0}},
                 "color": {"struct": F.ref("/Script/CoreUObject.LinearColor"), "value": {"r": 1, "g": 1, "b": 1, "a": 1}}}
        ps = [{"variable": {"name": n, "type": {"classStructOrEnum": F.ref(NT[t])}}, "defaultValue": typed[t]} for n, t, e in entries]
        try:
            t = F.call("AddSetParametersModule", {"moduleLocationRef": F.item(self.path, em, script, before), "parameters": ps})
            t = t.get("returnValue", t)
            mn = t["moduleName"]
            names = [i["name"] for i in t.get("inputs", [])]
            for n, ty, e in entries:
                k = next((x for x in names if x == n or x.endswith(n.split(".")[-1])), n)
                self.set(em, script, mn, k, ("hlsl", e))
            got = F.call("GetModuleInputValues", {"moduleRef": F.item(self.path, em, script, mn)}, check=False)
            got = got.get("returnValue", got) if isinstance(got, dict) else {}
            vals = {i["name"]: i.get("value", {}) for i in (got.get("inputs", []) if isinstance(got, dict) else [])}
            for n, ty, e in entries:
                v = next((v for k, v in vals.items() if k == n or k.endswith(n.split(".")[-1])), None)
                if v is None or "Hlsl" not in json.dumps(v.get("struct", {})):
                    self.issues.append(f"setparams {em}/{n}: HLSL did not stick, read back {json.dumps(v)[:200]}")
                    log("ERR", self.name, em, "setparams readback", n, json.dumps(v)[:200])
        except RuntimeError as e:
            self.issues.append(f"setparams {em}: {str(e)[:400]}")
            log("ERR", self.name, em, "setparams", str(e)[:400])

    def renderer(self, em, idx, **kw):
        try:
            F.call("SetRendererData", {"renderer": F.item(self.path, em, renderer=idx), "rendererData": {"propertyValues": json.dumps(kw)}})
        except RuntimeError as e:
            self.issues.append(f"renderer {em}/{idx}: {str(e)[:400]}")
            log("ERR", self.name, em, "renderer", str(e)[:400])

    def finish(self):
        sysobj = unreal.load_asset(self.path)
        if sysobj is not None:
            # Force a synchronous compile so the saved asset carries compiled scripts (render runs only load it).
            try:
                sysobj.request_compile(True)
            except Exception:
                pass
            try:
                unreal.NiagaraEditorFunctionLibrary  # noqa: B018
            except Exception:
                pass
            EAL.save_loaded_asset(sysobj, False)
        st = F.call("GetSystemCompileState", {"system": F.ref(self.path)}, check=False)
        # GetStackIssues builds Slate curve widgets and asserts without a Slate app: only in a full editor session.
        si = F.call("GetStackIssues", {"system": F.ref(self.path)}, check=False) if os.environ.get("ANYSCENEFX_STACK_ISSUES") else None
        REPORT["systems"][self.name] = {"path": self.path, "issues": self.issues, "compile": st, "stack_issues": si,
                                        "params": {k: v[0] for k, v in self.params.items()}}
        log("system", self.name, "issues", len(self.issues))


# ------------------------------------------------------------------ the shared parameter contract

def common(spawn, life, size, vel, color, intensity, opacity, box, wind=(0, 0, 0), gravity=0.0, drag=0.0, jitter=0.1,
           noise=0.0, noise_freq=0.01, grow=0.0, aspect=1.0, temperature=0.0):
    return {
        "SpawnRate": ("float", spawn, "particles per second"),
        "LifetimeMin": ("float", life[0], "s"), "LifetimeMax": ("float", life[1], "s"),
        "SizeMin": ("float", size[0], "sprite width, cm"), "SizeMax": ("float", size[1], "sprite width, cm"),
        "Aspect": ("float", aspect, "sprite length / width (streaks, flame tongues)"),
        "Velocity": ("vec3", vel, "initial (and terminal, with Drag) velocity, cm/s, world"),
        "VelocityJitter": ("float", jitter, "0..1 cone spread (Blender factor_random)"),
        "Wind": ("vec3", wind, "constant drift, cm/s"),
        "Gravity": ("float", gravity, "0..1 x 980 cm/s2"),
        "Drag": ("float", drag, "linear drag 1/s; with drag the particle settles at Velocity + Wind"),
        "BoxExtent": ("vec3", box, "spawn box half extent, cm, local"),
        "Color": ("color", color, "albedo (lit) or emissive tint (unlit)"),
        "Intensity": ("float", intensity, "emissive luminance multiplier, nits"),
        "Opacity": ("float", opacity, "per-sprite peak alpha"),
        "Temperature": ("float", temperature, "K; > 0 replaces Color with blackbody (fire)"),
        "NoiseStrength": ("float", noise, "curl-noise force, cm/s2"),
        "NoiseFreq": ("float", noise_freq, "curl-noise frequency, 1/cm"),
        "Grow": ("float", grow, "sprite size growth over life (size x (1 + Grow x age))"),
    }


FADE = "saturate(Particles.NormalizedAge * {a}) * saturate((1.0 - Particles.NormalizedAge) * {b})"


def fountain_core(s, em, *, gpu, material, fade=(6.0, 2.5), aligned=False, sort=False, curl=True, grow=True, nonuniform=False,
                  pivot=(0.5, 0.5)):
    """Rewire a Fountain emitter to the shared User parameters."""
    s.emitter_data(em, SimTarget="GPUComputeSim" if gpu else "CPUSim", bDeterminism=True, RandomSeed=abs(hash(s.name + em)) % 100000,
                   CalculateBoundsMode="Fixed", FixedBounds={"min": {"x": -500, "y": -500, "z": -500}, "max": {"x": 500, "y": 500, "z": 500}, "isValid": True},
                   bLocalSpace=False)
    EU, PS, PU = "EmitterUpdateScript", "ParticleSpawnScript", "ParticleUpdateScript"
    s.set(em, EU, "SpawnRate", "SpawnRate", ("link", "User.SpawnRate", "float"))
    s.set(em, PS, "InitializeParticle", "Lifetime Min", ("link", "User.LifetimeMin", "float"))
    s.set(em, PS, "InitializeParticle", "Lifetime Max", ("link", "User.LifetimeMax", "float"))
    s.set(em, PS, "InitializeParticle", "Color", ("hlsl", "float4(User.Color.r, User.Color.g, User.Color.b, User.Opacity)"))
    if nonuniform:
        s.set(em, PS, "InitializeParticle", "Sprite Size Mode", ("enum", "Random Non-Uniform"))
        s.set(em, PS, "InitializeParticle", "Sprite Size Min", ("hlsl", "float2(User.SizeMin, User.SizeMin * User.Aspect)"))
        s.set(em, PS, "InitializeParticle", "Sprite Size Max", ("hlsl", "float2(User.SizeMax, User.SizeMax * User.Aspect)"))
        if not aligned:
            # Elongated sprites (tongues, streaks) have an up: the Fountain's random sprite rotation would point them anywhere.
            s.set(em, PS, "InitializeParticle", "Sprite Rotation Mode", ("enum", "Unset"))
    else:
        s.set(em, PS, "InitializeParticle", "Uniform Sprite Size Min", ("link", "User.SizeMin", "float"))
        s.set(em, PS, "InitializeParticle", "Uniform Sprite Size Max", ("link", "User.SizeMax", "float"))
    if aligned:
        s.set(em, PS, "InitializeParticle", "Sprite Rotation Mode", ("enum", "Unset"))
    s.set(em, PS, "ShapeLocation", "Shape Primitive", ("enum", "Box"))
    s.set(em, PS, "ShapeLocation", "Box Size", ("hlsl", "User.BoxExtent * 2.0"))
    s.set(em, PS, "AddVelocity", "Velocity Speed", ("hlsl", "length(User.Velocity)"))
    s.set(em, PS, "AddVelocity", "Cone Axis", ("hlsl", "normalize(User.Velocity + float3(0.0, 0.0, 0.0001))"))
    s.set(em, PS, "AddVelocity", "Cone Angle", ("hlsl", "User.VelocityJitter * 90.0"))
    s.set(em, PS, "AddVelocity", "Rotation Coordinate Space", ("enum", "World"))
    # Intensity + temperature reach the material through the dynamic parameter.
    s.set_params(em, PS, [("Particles.DynamicMaterialParameter", "vec4", "float4(User.Intensity, User.Temperature, 0.0, 0.0)")])
    # Forces: with linear drag k, the force (V + W) k - g makes the particle settle at Velocity + Wind.
    s.set(em, PU, "GravityForce", "Gravity", ("hlsl", "(User.Velocity + User.Wind) * User.Drag + float3(0.0, 0.0, -980.0 * User.Gravity)"))
    s.set(em, PU, "Drag", "Drag", ("link", "User.Drag", "float"))
    s.set(em, PU, "ScaleColor", "Scale Alpha", ("hlsl", FADE.format(a=fade[0], b=fade[1])))
    if curl:
        mn, ins = s.add_module(em, PU, "/Niagara/Modules/Update/Forces/V2/CurlNoiseForce.CurlNoiseForce", before="SolveForcesAndVelocity")
        for k in ins:
            kl = k.lower()
            if "strength" in kl:
                s.set(em, PU, mn, k, ("link", "User.NoiseStrength", "float"))
            elif "frequency" in kl:
                s.set(em, PU, mn, k, ("link", "User.NoiseFreq", "float"))
        REPORT.setdefault("curl_inputs", sorted(ins))
    if grow:
        mn, ins = s.add_module(em, PU, "/Niagara/Modules/Update/Size/ScaleSpriteSize.ScaleSpriteSize")
        s.set(em, PU, mn, "Scale Sprite Size Mode", ("enum", "Non-Uniform"))
        ins = s.inputs_of(em, PU, mn)
        k = next((k for k, i in ins.items() if "Vector2f" in i["type"]["classStructOrEnum"]["refPath"] and i.get("bIsVisible")), None)
        REPORT.setdefault("scalesize_inputs", {k: [i["type"]["classStructOrEnum"]["refPath"].split(".")[-1], i.get("bIsVisible")] for k, i in ins.items()})
        if k:
            s.set(em, PU, mn, k, ("hlsl", "float2(1.0, 1.0) * (1.0 + User.Grow * Particles.NormalizedAge)"))
        else:
            s.issues.append(f"ScaleSpriteSize: no Vector2f scale input in {sorted(ins)}")
    s.renderer(em, 0, Material=F.ref(material), Alignment="VelocityAligned" if aligned else "Unaligned",
               FacingMode="FaceCameraPosition" if aligned else "FaceCamera", SortMode="ViewDepth" if sort else "None",
               PixelCoverageMode="Enabled", bCastShadows=False, MotionVectorSetting="Disable" if not aligned else "AutoDetect",
               PivotInUVSpace={"x": pivot[0], "y": pivot[1]})


def to_val(v):
    """Recipe JSON value -> Sys.set value: number | bool | {"link","type"} | {"hlsl"} | {"enum"}."""
    if isinstance(v, dict):
        if "link" in v:
            return ("link", v["link"], v.get("type", "float"))
        if "hlsl" in v:
            return ("hlsl", v["hlsl"])
        if "enum" in v:
            return ("enum", v["enum"])
    return v


def load_recipes():
    """Built-in recipes (fx_recipes/*.json next to this file) + any in ANYSCENEFX_RECIPES (a folder, os.pathsep-separated).
    A later recipe with the same name replaces an earlier one, so an agent can override a built-in."""
    dirs = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "fx_recipes")]
    dirs += [d for d in os.environ.get("ANYSCENEFX_RECIPES", "").split(os.pathsep) if d]
    out = {}
    for d in dirs:
        for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if f.endswith(".json"):
                r = json.load(open(os.path.join(d, f)))
                out[r["name"]] = r
    return out


def build_recipe(r, mats):
    PU = "ParticleUpdateScript"
    c = r.get("common", {})
    params = common(spawn=c.get("spawn", 50), life=c.get("life", (1, 2)), size=c.get("size", (5, 10)), vel=c.get("vel", (0, 0, 0)),
                    color=c.get("color", (1, 1, 1)), intensity=c.get("intensity", 0.0), opacity=c.get("opacity", 1.0),
                    box=c.get("box", (10, 10, 10)), wind=c.get("wind", (0, 0, 0)), gravity=c.get("gravity", 0.0), drag=c.get("drag", 0.0),
                    jitter=c.get("jitter", 0.1), noise=c.get("noise", 0.0), noise_freq=c.get("noise_freq", 0.01), grow=c.get("grow", 0.0),
                    aspect=c.get("aspect", 1.0), temperature=c.get("temperature", 0.0))
    for k, (t, dv, desc) in r.get("extra", {}).items():
        params[k] = (t, tuple(dv) if isinstance(dv, list) else dv, desc)
    s = Sys(r["name"], params)
    sy = r.get("system", {})
    lo, hi = sy.get("bounds", [[-200, -200, -200], [200, 200, 200]])
    s.system_data(bDeterminism=True, RandomSeed=int(sy.get("seed", 1)), bFixedBounds=True,
                  FixedBounds={"min": dict(zip("xyz", lo)), "max": dict(zip("xyz", hi)), "isValid": True})
    for e in r["emitters"]:
        em = s.emitter(e.get("template", "Fountain"), e["name"])
        if e.get("core") is not None:
            k = dict(e["core"])
            k["material"] = mats[k["material"]]
            k["fade"] = tuple(k.get("fade", (6.0, 2.5)))
            fountain_core(s, em, **k)
        if e.get("emitter_data"):
            s.emitter_data(em, **e["emitter_data"])
        for script, module, inp, val in e.get("inputs", []):
            s.set(em, script, module, inp, to_val(val))
        for m in e.get("add_modules", []):
            mn, ins = s.add_module(em, m.get("script", PU), m["asset"], before=m.get("before", ""))
            for inp, val in m.get("inputs", {}).items():
                s.set(em, m.get("script", PU), mn, inp, to_val(val))
        # One SetParameters module per (script, position): several modules in a row crashed the toolset headless.
        groups = {}
        for sp in e.get("set_params", []):
            groups.setdefault((sp[0], sp[4] if len(sp) > 4 else ""), []).append(tuple(sp[1:4]))
        for (script, before), entries in groups.items():
            s.set_params(em, script, entries, before=before)
        for idx in sorted(e.get("remove_renderers", []), reverse=True):
            try:
                F.call("RemoveRenderer", {"rendererToRemove": F.item(s.path, em, renderer=idx)})
            except RuntimeError as x:
                s.issues.append(f"remove renderer {em}/{idx}: {x}")
        for rd in e.get("add_renderers", []):
            res = F.call("AddRenderer", {"newRendererLocation": F.item(s.path, em), "rendererClass": F.ref("/Script/Niagara." + rd["class"])})
            res = res.get("returnValue", res) if isinstance(res, dict) else res
            s.renderer(em, int(res.get("index", 0)) if isinstance(res, dict) else 0, **rd.get("data", {}))
        for idx, data in e.get("renderer_data", {}).items():
            if "Material" in data and data["Material"] in mats:
                data = dict(data, Material=F.ref(mats[data["Material"]]))
            s.renderer(em, int(idx), **data)
    s.finish()
    REPORT["systems"][r["name"]].update({"fx_types": r.get("fx_types", []), "description": r.get("description", "")})


def build():
    for p in (f"{ROOT}/Systems", f"{ROOT}/Materials"):
        if not EAL.does_directory_exist(p):
            EAL.make_directory(p)
    recipes = load_recipes()
    only = set(x for x in os.environ.get("ANYSCENEFX_ONLY", "").split(",") if x)
    allm = dict(MATS)
    for r in recipes.values():
        allm.update(r.get("materials", {}))
    # Materials: all of them on a full build; on an ANYSCENEFX_ONLY build just the ones those recipes ship.
    want_m = set(allm) if not only else {m for n in only for m in recipes[n].get("materials", {})}
    mats = {k: f"{ROOT}/Materials/{k}.{k}" for k in allm}
    for k in sorted(want_m):
        mats[k] = make_material(k, allm[k])
    log("materials", sorted(want_m))
    for name, r in recipes.items():
        if only and name not in only:
            continue
        build_recipe(r, mats)
    # templates.json is the converter's contract: merge, so a partial (ANYSCENEFX_ONLY) build keeps the others.
    out = json.load(open(OUT_JSON)) if os.path.exists(OUT_JSON) and only else {}
    for k, v in REPORT["systems"].items():
        out[k] = {"path": v["path"], "params": v["params"], "fx_types": v.get("fx_types", []), "description": v.get("description", "")}
    json.dump(out, open(OUT_JSON, "w"), indent=1)
    REPORT["toolset_log"] = F.LOG
    json.dump(REPORT, open(OUT_JSON.replace(".json", "_report.json"), "w"), indent=1, default=str)
    log("done", OUT_JSON, sum(len(v["issues"]) for v in REPORT["systems"].values()), "issues")


try:
    build()
except Exception as e:  # keep the partial report
    import traceback
    REPORT["errors"].append(traceback.format_exc())
    REPORT["toolset_log"] = F.LOG
    json.dump(REPORT, open(OUT_JSON.replace(".json", "_report.json"), "w"), indent=1, default=str)
    log("FAILED", e)
