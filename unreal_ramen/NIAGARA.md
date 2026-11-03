# NIAGARA.md: porting AnyScene (Blender/Cycles) effects to Unreal 5.8

This is the converter agent's guide to effects: flames, steam, smoke, haze plumes, rain or drizzle, drips and splashes,
sparks and embers, dust motes, fountain jets, and screen or light flicker. Geometry, materials, lights, cameras and fog
already convert (`export_blend.py` writes `scene.json`, then `build_level.py` builds the level). This file covers
what comes next: classify each Blender effect, pick a technique, place it, render it through MRQ and compare it
with Cycles.

Everything marked *[engine]* was confirmed in the installed UE 5.8 files under `C:\Program Files\Epic Games\UE_5.8`.
Items marked *[docs]* come from dev.epicgames.com. Items marked *[untested]* are design guidance: verify them on the
first scene and update this file.

---

## 0. Read this first: findings that change the plan

1. **No built-in fire, steam, smoke or rain system ships with 5.8.** The Niagara plugin includes only generic emitter
   templates (Fountain, HangingParticulates, RecycleParticlesInView, BlowingParticles, DirectionalBurst, ...). There is
   no StarterContent `P_Fire` / `P_Steam` on this install. Real fire and smoke exist only as **NiagaraFluids** grid sims,
   which are Beta and expensive. Plan on an **AnySceneFX content plugin**: about ten master systems authored once, so
   the converter only places them and sets their parameters. Never author Niagara graphs at build time.
2. **Local fog volumes in `build_level.py` are the wrong size.** `ULocalFogVolumeComponent::GetBaseVolumeSize()`
   returns **500 cm**, and the proxy collapses the scale to a uniform sphere using the **max axis**
   (`LocalFogVolumeSceneProxy.cpp:34`) *[engine]*. `build_level.py` assumes a 100 cm unit and non-uniform scale, so
   every LFV comes out about 5x too large and spherical. That is why the wok "flame" became a large static emissive
   glow. `RadialFogExtinction` is also integrated in unit-sphere space: the optical depth straight through the centre
   is exactly `RadialFogExtinction`, independent of size (`LocalFogVolumeCommon.ush:178-203`). The correct mapping is
   **extinction = Blender density (1/m) x path length (m)**, not the raw density.
3. **Particles never reach the level.** The exporter only logs particle emitters into `fx` (no transform, no bounds,
   no velocity), and `build_level.py` ignores `fx`. That is why the HK drizzle and drips are missing. Steam is
   procedural 4D-noise volume shaders, which the exporter samples at one frame into a static LFV. Animated steam
   cannot survive that path.
4. **MRQ needs `render_warm_up_frames = True` for GPU particles.** The flag's own tooltip says GPU particles need the
   warm-up frames to be rendered *[engine: MoviePipelineAntiAliasingSetting.h]*. `build_level.py` already sets it
   (64 engine warm-up frames). Keep it, and keep `use_camera_cut_for_warm_up = False`, or `engine_warm_up_count` is
   ignored.
5. **Pass `fx.Niagara.ForceWaitForCompilationOnActivate=1` in `-dpcvars` for every headless render.** Otherwise a
   component activates while its scripts or GPU shaders are still compiling, and the first frames render without the
   effect. This is the Niagara equivalent of the `Editor.AsyncAssetCompilation=0` gotcha already in
   `render_shots.py`. The per-component property `bWaitForCompilationOnActivate` is editor-only data
   (`NiagaraComponent.cpp:1358`) *[engine]*.
6. **User parameters set from Python in the editor are saved with the level.** In editor builds, `SetVariableFloat`
   and the other setters also call `SetParameterOverride`, which writes `InstanceParameterOverrides`
   (`NiagaraComponent.cpp:2875, 4376`) *[engine]*. So build, set, `save_current_level()` works headlessly. The
   parameter must exist on the asset and the type must match exactly. A wrong name or wrong type is a **silent no-op**.
7. **Epic ships an AI toolset for Niagara authoring:** `Engine/Plugins/Experimental/Toolsets/NiagaraToolsets` (plus
   `ToolsetRegistry`, both disabled by default). Its tools create systems, add emitters, modules, renderers and user
   variables, set stack inputs, and read compile errors and stack issues. You can call them from Python through
   `unreal.ToolsetRegistry.execute_tool(toolset, tool, json)`. Use this for the **one-time** authoring of the AnySceneFX
   templates, in a full editor session with an RHI. Do not use it in the per-scene build. It is Experimental. Its
   bundled skills (`Content/Python/skills/*.py`) are worth reading. They are summarised in §1 where relevant.
8. **Animated SVTs import headlessly from VDB.** `USparseVolumeTextureFactory` skips its dialog when the import is
   automated or running in a commandlet, auto-detects numbered `.vdb` sequences, and maps the `density` grid to
   attributes A.R (unorm8), with up to 4 other grids in B (fp16) (`SparseVolumeTextureFactory.cpp:40-108, 436`)
   *[engine]*. Blender 5.0 bundles the `openvdb` Python module (`5.0/python/lib/site-packages/openvdb.cp311-*.pyd`), so
   the exporter can write VDBs from procedural volumes itself.

---

## 1. Niagara essentials (only what the converter needs)

- **System > emitters > modules.** A *system* (`UNiagaraSystem`, the asset you place) contains *emitters*. Each
  emitter runs four script stacks in a fixed order: System Spawn/Update, then Emitter Spawn/Update, then Particle
  Spawn/Update. Spawn runs once at creation and Update runs every tick. Within Particle Update the order is forces,
  then collision, then exactly one velocity solve. *Renderers* (sprite, mesh, ribbon, light, ...) draw an emitter's
  particles.
- **Namespaces.** `User.*` is the external interface: set per component, read anywhere. `Engine.*` is read-only (delta
  time, owner transform). `System.*`, `Emitter.*` and `Particles.*` are written by their own scope.
  **Expose everything the converter sets as a `User.` parameter.** From Python, pass the bare name (`SpawnRate`). The
  `User.` prefix also resolves (`RedirectUserVariable`). There is no enum setter: set the int.
- **Types matter.** World-space anchors are `Position` (LWC-aware): use `set_variable_position`. Directions,
  velocities, wind and box extents are `Vector3`: use `set_variable_vec3`. Colours are `LinearColor`.
- **CPU vs GPU.** System and emitter scripts always run on the CPU VM. Only particle scripts move to the GPU.
  - Use **GPU** for anything sustained in the hundreds or more (rain, dust, steam puffs, sparks).
  - Use **CPU** for small counts and for any emitter with a **Light renderer**: light, decal and component renderers
    force the emitter to CPU.
  - A system can mix both.
- **Fixed bounds.** Use fixed bounds for every converter-placed effect. They are cheapest, work on CPU and GPU, and
  stop the culling surprises. Dynamic bounds are CPU-only. GPU emitters without fixed or programmable bounds cull
  wrongly. Set them per instance with `set_system_fixed_bounds(Box)` in **local space**: use the Blender domain or
  emitter box plus travel distance (velocity x lifetime).
- **Warm-up and pre-roll.** `UNiagaraSystem.WarmupTime / WarmupTickCount / WarmupTickDelta` simulate N ticks on
  activation in one frame. Per instance, set `override_warmup_settings = True`, `warmup_tick_count` and
  `warmup_tick_delta`. The component passes these to the instance at activation (`NiagaraComponent.cpp:1219`)
  *[engine]*. Rule: **warm-up time ≥ the longest particle lifetime x 1.5**, so the effect is in steady state on
  frame 1. Mirror Blender's negative `frame_start` (HK drizzle starts at -80) or the Mantaflow `PREROLL`.
- **Determinism and seeds.**
  - The system flag `bDeterminism` + `RandomSeed` makes the instance seed equal the system seed plus the component's
    `RandomSeedOffset`. Without it, every reset gets a random seed.
  - Emitters carry their own `bDeterminism` / `RandomSeed` too.
  - Turn both on in every AnySceneFX template. Set `set_random_seed_offset(hash(fx_id) & 0x7fffffff)` per instance so
    copies differ but runs repeat. The offset is applied on activation or reset, so set it before saving.
  - CPU emitters with determinism repeat exactly under MRQ's fixed timestep. Treat GPU emitters as "very close" *[untested]*.
    For bit-exact repeats, use a sim cache (§2.6).
- **Lit vs unlit sprites.**
  - Fire, embers, sparks, CRT glow: **unlit**, additive or translucent, emissive only.
  - Steam, smoke, haze, dust, rain: **lit translucent**. Use *Translucency Lighting Mode = Volumetric NonDirectional*
    (cheapest, soft) or *Volumetric PerVertex NonDirectional*. The directional modes only matter for normal-mapped
    smoke.
  - Prefer Masked over Translucent where blending allows (drops, chunky debris).
  - Translucent materials need **Two Sided** when seen from both sides.
  - Each material needs the usage flag for its renderer: `MaterialEditingLibrary.set_material_usage(mat,
    unreal.MaterialUsage.MATUSAGE_NIAGARA_SPRITES)`. In 5.8 the `bUsedWith*` flags are deprecated in favour of the
    usage accessor *[engine: Material.h:749]*.
- **Lumen.**
  - Particles do not contribute to Lumen GI or reflections as emitters: a fire sprite lights nothing. Light comes from
    a real light (§3, Lighting).
  - Lit translucent particles receive Lumen GI through the low-resolution translucency lighting volume, so expect
    soft, slightly flat shading.
  - Emissive particles are not in the Lumen scene: they will not show in reflections the way Cycles shows them.
- **Volumetric fog.**
  - A sprite with a **Volume-domain material** injects albedo, emissive and extinction into the volumetric-fog froxel
    grid. This gives real 3D density with no billboard edges *[docs: Volumetric Fog]*. Mesh renderers reject the Volume
    domain *[engine: NiagaraMeshRendererProperties.cpp:1380]*.
  - It needs an Exponential Height Fog with *Volumetric Fog* on, which the converter already spawns.
  - The grid is coarse and camera-aligned, so use it for haze plumes and soft steam bodies, not crisp wisps.
- **Translucency sorting.**
  - Within an emitter: `SortMode = ViewDepth` on the sprite renderer. Leave it at `None` for additive fire and sparks;
    sorting costs GPU time.
  - Between components, sorting is by bounds centre. Fix wrong-order overlaps with the primitive property
    `translucency_sort_priority`, or by splitting the bounds.
- **Depth of field.** Translucent materials default to `TranslucencyPass = MTP_AfterDOF` *[engine: Material.cpp:1183]*,
  so out-of-focus steam stays sharp. For effects in defocused regions (foreground steam in `cam_wok`), set
  `TranslucencyPass = MTP_BeforeDOF` in the template material, or in a second material variant.

---

## 2. Placing and driving Niagara from Python, headless

### 2.1 Confirmed API (UE 5.8, from `NiagaraComponent.h`, `NiagaraActor.h`, `NiagaraFunctionLibrary.h`)

| Need | Call |
|---|---|
| Place | `eas.spawn_actor_from_class(unreal.NiagaraActor, loc, rot)`. Same reason as `spawn_mesh()` in `build_level.py`: spawn by class in the commandlet |
| Component | `act.get_editor_property("niagara_component")` (UPROPERTY `NiagaraComponent`) |
| Set asset | `nc.set_asset(system, True)`. The second arg resets existing overrides: set the asset **first**, then the parameters |
| Float, int, bool | `nc.set_variable_float(name, v)`, `set_variable_int`, `set_variable_bool` |
| Vector, colour | `set_variable_vec3(name, unreal.Vector)`, `set_variable_vec2`, `set_variable_vec4`, `set_variable_linear_color(name, unreal.LinearColor)`, `set_variable_quat` |
| Position (LWC) | `set_variable_position(name, unreal.Vector)` |
| Objects | `set_variable_texture`, `set_variable_material`, `set_variable_static_mesh`, `set_variable_object`, `set_variable_actor` |
| Read back (verify) | `get_variable_float(name)` and the like. In Python these return `(value, is_valid)`; assert `is_valid` |
| Seed | `nc.set_random_seed_offset(int)` |
| Bounds | `nc.set_system_fixed_bounds(unreal.Box)`, `set_emitter_fixed_bounds(emitter_name, box)`; read back with `get_system_fixed_bounds()` |
| Warm-up | `nc.set_editor_property("override_warmup_settings", True)`, `("warmup_tick_count", n)`, `("warmup_tick_delta", dt)` |
| Scalability | `nc.set_allow_scalability(False)`. Cinematic renders must not be distance-culled by an Effect Type |
| Sequencer age | `set_age_update_mode(unreal.NiagaraAgeUpdateMode.DESIRED_AGE_NO_SEEK)`, `set_desired_age(t)`, `seek_to_desired_age(t)` |
| Manual sim | `advance_simulation(ticks, dt)`, `advance_simulation_by_time(seconds, dt)`, `reset_system()`, `reinitialize_system()` |
| Sim cache | `set_sim_cache(cache, reset)`. Capture with `NiagaraSimCacheFunctionLibrary.capture_niagara_sim_cache_immediate(...)` |
| Runtime spawn | `unreal.NiagaraFunctionLibrary.spawn_system_at_location(world, system, loc, rot, scale, auto_destroy, auto_activate, pool, precull)`. Do not use it for level building: it is a transient runtime spawn |

Python names are the snake_case form of the C++ names, with a property's `b` prefix dropped. No stub exists yet
(`Intermediate/PythonStub/unreal.py` is generated only with Developer Mode on). On first use, run
`dir(unreal.NiagaraComponent)` in the build log and fix any name that differs.

### 2.2 Placement snippet (goes into a `stage_fx()` in `build_level.py`)

```python
NS = {}
def fx_system(path):
    if path not in NS:
        NS[path] = unreal.load_asset(path)
        if NS[path] is None:
            warn(f"fx template missing: {path}")
    return NS[path]

def place_fx(eas, fx):
    sysasset = fx_system(fx["template"])
    if sysasset is None:
        return None
    q = fx["transform"]["quat"]
    act = eas.spawn_actor_from_class(unreal.NiagaraActor, V(fx["transform"]["loc"]),
                                     unreal.Quat(*q).rotator())
    act.set_actor_label("FX_" + fx["id"]); act.set_folder_path("FX")
    nc = act.get_editor_property("niagara_component")
    nc.set_asset(sysasset, True)                       # 1. asset first (resets overrides)
    for k, v in fx["params"].items():                  # 2. typed user params
        t = fx["param_types"][k]
        if t == "float":   nc.set_variable_float(k, float(v))
        elif t == "int":   nc.set_variable_int(k, int(v))
        elif t == "bool":  nc.set_variable_bool(k, bool(v))
        elif t == "vec3":  nc.set_variable_vec3(k, V(v))
        elif t == "pos":   nc.set_variable_position(k, V(v))
        elif t == "color": nc.set_variable_linear_color(k, unreal.LinearColor(*v[:3], v[3] if len(v) > 3 else 1))
    nc.set_random_seed_offset(fx["seed"])              # 3. determinism
    b = unreal.Box(); b.min = V(fx["bounds_local"]["min"]); b.max = V(fx["bounds_local"]["max"]); b.is_valid = True
    nc.set_system_fixed_bounds(b)                      # 4. bounds (local)
    nc.set_editor_property("override_warmup_settings", True)   # 5. pre-roll
    nc.set_editor_property("warmup_tick_delta", 1.0 / 30.0)
    nc.set_editor_property("warmup_tick_count", int(math.ceil(fx["time"]["preroll_s"] * 30)))
    nc.set_allow_scalability(False)
    for k, t in fx["param_types"].items():             # 6. verify: silent no-ops are the main failure
        if t == "float":
            val, ok = nc.get_variable_float(k)
            if not ok: warn(f"{fx['id']}: user param {k} not on {fx['template']}")
    return act
```
Then call `les.save_current_level()`, as `stage_level` already does. Construct `unreal.Box` the way above, or with
keyword args. Check the result with `get_system_fixed_bounds()`.

### 2.3 Commandlet (`-run=pythonscript`) limits

- **Commandlets render nothing.** A commandlet uses the null RHI unless it is started with `-AllowCommandletRendering`
  (`LaunchEngineLoop.cpp:2246`) *[engine]*.
  - These need no RHI and work in the commandlet: placing actors, setting user parameters, fixed bounds, warm-up
    fields, seeds, and saving.
  - GPU emitters do not simulate there, and their compute shaders are not exercised.
  - Niagara VM script compilation is a DDC/ShaderCompileWorker job. It works from a commandlet, as cooking proves.
    Ship the templates **pre-compiled and saved** in the AnySceneFX plugin, so a fresh build only loads them.
- **The first render compiles shaders.** GPU sim shaders and particle material shaders compile on the first
  `-game -RenderOffscreen` run.
  - Pass `-dpcvars=Editor.AsyncAssetCompilation=0,fx.Niagara.ForceWaitForCompilationOnActivate=1`.
  - Budget a one-off cold-DDC compile of about 2-5 minutes per new template set. Keep the DDC on persistent storage
    (`/data`) in the container.
- **Don't author Niagara graphs in the commandlet.** `UNiagaraSystemFactoryNew` exposes no Python properties.
  `EditorAssetLibrary.duplicate_asset()` works for "copy a template and tweak it", but tweaking stack inputs needs
  the NiagaraToolsets editor functions, which expect a full editor. Per-scene variation goes through user parameters,
  not new assets.
- **Plugins.** Niagara is on by default. If you use NiagaraFluids (Beta), NiagaraSimCaching or NiagaraMRQ, enable them
  in `AnySceneUE.uproject` (`"Plugins"`) **before** the build. Enabling a plugin mid-session needs a restart.

### 2.4 MRQ settings for particles (the `MRQ_Still` / `MRQ_Linear` configs in `stage_sequences`)

- `MoviePipelineAntiAliasingSetting`:
  - `engine_warm_up_count = 64`: game-thread ticks with no render; the cheap warm-up.
  - `render_warm_up_frames = True`: required for GPU particles, depth-buffer collision and GPU warm-up.
  - `use_camera_cut_for_warm_up = False`.
  - `temporal_sample_count = 8`: Niagara ticks once per temporal sub-sample, so the accumulation itself gives sprite
    motion blur.
  - Raise `engine_warm_up_count` to `ceil(max_lifetime_s x fps x 1.5)` when the scene's longest lifetime exceeds
    64/24 s, for example slow steam with 6 s lifetimes.
- **Fixed timestep.** MRQ always steps the world at the sequence rate. Particle state is a pure function of frames
  since activation plus the seed, so the warm-up count must be identical between runs.
- **Pre-roll belongs in the asset or component.** Component warm-up (§2.2) runs on activation, before any MRQ frame.
  Use both component warm-up and MRQ engine warm-up: the first covers steady state, the second covers shader compile
  and streaming.
- `MoviePipelineGameOverrideSetting` (already added) forces cinematic scalability. Also call `set_allow_scalability(False)`
  on every component so Effect Type culling can't drop an effect.
- **Sequencer track (optional, for exact scrubbing).** Add a Niagara System track to the camera's level sequence,
  with a spawn section set to `SectionEvaluateBehavior = ActivateIfInactive` and
  `AgeUpdateMode = DesiredAgeNoSeek`. Age then follows sequence time instead of wall-clock ticks
  (`MovieSceneNiagaraSystemSpawnSection.h`) *[engine]*. Only do this if stills differ between runs.
- **NiagaraMRQ plugin.** It adds a data interface that tells a system whether MRQ is running, plus the temporal sample
  index and count. Use it only if a template must branch for offline quality, for example more particles under MRQ.

### 2.5 Light and screen flicker (not Niagara)

- **Flickering lights.** HK `wok_fire_*` uses a Python driver on `energy`.
  - Do not parse driver expressions. **Sample** the evaluated value per frame in the exporter: `frame_set(f)`, read
    `L.energy` for frames `[start, start+N)`.
  - Write `flicker.values` and key a Sequencer float track on the light's `intensity`, in the camera sequence.
  - Rendered through MRQ, this is deterministic and frame-exact.
- **CRT, screen and sign flicker.** Use a material, not Niagara.
  - Add `FlickerAmp`, `FlickerHz` and `ScanlineDensity` scalar parameters to `M_AnyBaked`'s emissive path, or to a
    dedicated `M_AnyScreen` master: emissive x (1 + amp x noise(time x Hz)), plus a rolling bar.
  - The source is `animated_materials` in the asset entry. Sample the emission strength curve the same way as lights.

### 2.6 When exact repeatability matters: sim caches

Capture the steady-state window once and assign it with `set_sim_cache`. Playback is then identical every run. Use
`capture_niagara_sim_cache_immediate` / `..._multi_frame` from `NiagaraSimCacheFunctionLibrary` in an editor session
with an RHI, or record with a Niagara Cache track in Sequencer (plugin `NiagaraSimCaching`). Only needed for hero
shots and A/B parameter tuning, where seed noise would hide a parameter change.

---

## 3. The template library (`/AnySceneFX/`)

Build these as a content plugin, `Plugins/AnySceneFX/Content/Systems/NS_*.uasset`, authored once and committed.

**Shared rules for every template.**
- `bDeterminism` on, at system and emitter level.
- Fixed bounds mode.
- World space, not local.
- Warm-up 0 in the asset. The converter sets it per instance.
- Every tunable is a `User.` parameter with a real-world default (cm, cm/s, s, nits, K).

**Common user parameters**, the same names in every system so the placement code stays generic:

| Name | Type | Meaning |
|---|---|---|
| `SpawnRate` | float | particles per second (or `Count` for bursts) |
| `LifetimeMin`, `LifetimeMax` | float | seconds |
| `SizeMin`, `SizeMax` | float | sprite size, cm |
| `Velocity` | vec3 | initial velocity, cm/s, world |
| `VelocityJitter` | float | 0..1 fraction (Blender `factor_random`) |
| `Wind` | vec3 | constant drift, cm/s |
| `Gravity` | float | 0..1 x 980 cm/s² |
| `BoxExtent` | vec3 | spawn box half-extent, cm (spawn shape = local box) |
| `Color` | color | albedo (lit) or emissive tint (unlit) |
| `Intensity` | float | emissive luminance multiplier, nits |
| `Opacity` | float | per-sprite peak alpha |
| `Temperature` | float | K, feeds a material `BlackBody` node (fire, embers) |
| `NoiseStrength`, `NoiseFreq` | float | curl-noise force amplitude and frequency |

The seed is not a parameter: it is the component's `RandomSeedOffset`.

**Starting assets that ship with 5.8.** These are mount paths. The engine plugin `/Niagara/` lives at
`Engine/Plugins/FX/Niagara/Content/`, and `/NiagaraFluids/` at `Engine/Plugins/FX/NiagaraFluids/Content/`.

- Emitters: `/Niagara/DefaultAssets/Templates/Emitters/{Fountain, HangingParticulates, RecycleParticlesInView,
  BlowingParticles, DirectionalBurst, OmnidirectionalBurst, SimpleSpriteBurst, SingleLoopingParticle, Minimal,
  UpwardMeshBurst, LocationBasedRibbon, StaticBeam, DynamicBeam, ConfettiBurst}`
- Systems: `/Niagara/DefaultAssets/Templates/Systems/{FountainLightweight, DirectionalBurst, RadialBurst,
  SimpleExplosion, MinimalLightweight, ...}`. The `*Lightweight` systems use stateless emitters, which the Niagara
  toolset cannot edit. Copy the stateful emitters instead.
- Behaviour examples (reference wiring): `/Niagara/DefaultAssets/Templates/BehaviorExamples/{SubUVAnimation,
  SpriteFacingAndAlignment, KillParticles, ...}`
- Fluids (Beta): `/NiagaraFluids/Templates/Gas/3D/Systems/{Grid3D_Gas_Fire, Grid3D_Gas_Smoke, Grid3D_Gas_ColoredFire,
  Grid3D_Gas_ColoredSmoke, Grid3D_MovingGridFire, Grid3D_Gas_Explosion}`, `.../Gas/2D/Systems/{Grid2D_Gas_SmokeFire,
  Grid2D_Gas_Smoke, Grid2D_Gas_MovingFire}`, `/NiagaraFluids/Templates/Liquid/3D/Systems/{Grid3D_Flip_Hose,
  Grid3D_Flip_Splash, Grid3D_Flip_Pool}`; materials `/NiagaraFluids/Materials/Grid3D/M_RayMarch_Fire*`,
  `MI_HeterogeneousVolumes_*`.
- Default sprite materials: `/Niagara/DefaultAssets/DefaultSpriteMaterial`, `M_DepthFade_SpriteSimple`.

**Units used in the mappings below.**
- Blender is metres, the exporter writes centimetres, and Blender axes map to Unreal as (x, -y, z).
- Volume density σ is extinction per metre. Volume emission strength *E* adds radiance per metre, so a slab of
  thickness *t* m that is optically thin glows at about *E·t* (Blender radiance units) = **683·E·t nits**. This is the
  same 683 lm/W the exporter uses for surfaces.
- **Sprite opacity from density.** For a plume of depth *L* (m) seen through *n* overlapping sprites, the target
  optical depth is τ = σ·L. Per-sprite α = 1 − exp(−τ/n). Estimate *n* ≈ SpawnRate × Lifetime × (sprite area ÷
  plume cross-section area).

### 3.1 Per-effect table

| Effect | AnySceneFX system, and how to start it | Key parameter mapping from Blender | Lighting | Real-time budget |
|---|---|---|---|---|
| **Fire / flames** (gas jets, wok, candles, braziers) | `NS_Fire`. Start from `SingleLoopingParticle` + `Fountain` (stateful copies). Two emitters: (a) a **SubUV flame** emitter with a flipbook **baked from the Blender flame volume** (§5.1), unlit additive, random start frame, `bSubImageBlend`; (b) a small blue-core emitter. Hero close-ups: `Grid3D_Gas_Fire` or an SVT (§5) | Domain box → `BoxExtent` and the emitter ring radius. Principled Volume `Emission Strength` x density-ramp peak x thickness → `Intensity` (683·E·t nits). `Emission Color` ramp at 0.6 → `Color`, or `Blackbody Intensity`/`Temperature` → `Temperature`. Flame height (density falloff z) → `Velocity.z` x Lifetime. Noise scroll rate (driver `frame*k`) → flipbook fps | Fire itself lights nothing. **Reuse the Blender practical lights** (`wok_fire_*`, `wok_blue_*` convert already) with the sampled flicker track (§2.5). If the scene has no light, add one CPU emitter with a Light renderer: one particle, `RadiusScale` ≈ flame height x 4, `bAffectsTranslucency` on. Cap: ≤ 4 Niagara lights per scene, ≤ 1 per fire | ≤ 40 sprites per flame, about 0.1 ms. Fluids fire: 1-3 ms at 64³; cinematic only |
| **Steam** (woks, pots, kettles, vents) | `NS_Steam`. Start from `Fountain`. GPU sprites, lit translucent (Volumetric NonDirectional), soft puff texture or a baked steam flipbook, curl noise, size grows x3-5 over life, alpha fades in and out. Add a second **Volume-domain sprite** emitter (§1) for the dense core when volumetric fog is on | Plume box (HK `steam_wok_i`: bottom z = wok rim, top = awning): base disc radius = 0.08 x box width → `BoxExtent`; `rise` (driver `-frame*rise`, m/frame) x fps x 100 → `Velocity.z`; `lean` → `Wind`. Lifetime = box height ÷ rise speed. Density `strength` x 9 (shader constant) = σ peak → `Opacity` by the formula above. `Color` 0.9 grey, anisotropy 0.5 → material phase (backlit glow: enable forward scatter in the material, or rely on volumetric fog) | Lit by scene lights. Needs the practical light behind it to read (HK hood strip, bulbs). `TranslucencyPass = BeforeDOF` for foreground plumes | 200-600 sprites per plume, 0.2-0.5 ms (overdraw-bound) |
| **Smoke** (cigarette curls, exhaust, chimneys) | `NS_Smoke` = `NS_Steam` with a darker albedo, slower rise and a longer life. Thin curls: a **ribbon** emitter (`LocationBasedRibbon`) with curl noise reads better than sprites | MC `smoke_curl_*`: box 0.18 x 0.18 x 0.75 m, noise scroll `-frame*0.012` → `Velocity.z` = 0.012 x fps x 100 cm/s; density 6 → ribbon width 0.5-1 cm, `Opacity` 0.3. Albedo (0.82, 0.8, 0.76) → `Color` | Lit translucent | ribbons: ≤ 3 per curl, negligible |
| **Haze plume / room haze** | Usually **not Niagara**. Homogeneous layers → Exponential Height Fog + Local Fog Volumes (§5.3). Moving plumes (street haze drifting under a light) → `NS_HazePlume`: a few big Volume-domain sprites (2-6 m) | Haze box σ → height fog density (existing code). Local plume: `RadialFogExtinction` = σ x diameter (m) (§0.2). Albedo, anisotropy → `fog_albedo`, `fog_phase_g`. Noise drift → `Wind` | Volumetric fog lighting only. Lights need `volumetric_scattering_intensity` > 0 (already mapped from Blender `visible_volume_scatter`) | LFV about 0.05 ms each; volume sprites 0.3 ms |
| **Rain / drizzle** | `NS_Rain`. Start from `RecycleParticlesInView` (keeps the rain around the camera) or a plain box-spawn GPU emitter. Velocity-aligned sprites (`Alignment = VelocityAligned`), streak length = speed x shutter, masked or translucent, `PixelCoverageMode` Automatic (sub-pixel streaks flicker under TSR otherwise) | Particle settings: `count`, `lifetime`, `frame_start/end` → `SpawnRate = count / (frame_end − frame_start) x fps`; `object_align_factor` (m/s) x 100 → `Velocity` (Blender (x,y,z) → (x,−y,z)); `factor_random` → `VelocityJitter`; emitter object box → `BoxExtent` + transform; instance-object radius x 2 → sprite width (≥ 0.15 cm, or it vanishes), length → streak length; drop material emission 0.5 / alpha 0.35 → `Intensity`, `Opacity` | Lit translucent or unlit with a faint emissive. Rain reads by **backlight**: check it against the street lights in the Cycles frames | GPU, 10k-40k alive, 0.3-0.8 ms |
| **Drips / splashes** | `NS_Drips`: GPU sprites spawned on a line (awning edge) under gravity, killed at the ground plane, plus an **event-free** splash: a second emitter spawned at the computed impact height with `DirectionalBurst`-style spray, or a splash flipbook. Ground ripples: decal flipbook or a puddle material, not particles | `awning_drips`: emitter box (thin strip) → spawn line; `count/span` → `SpawnRate`; `gravity` 1 → `Gravity` = 1; drop size → sprite size; ground z → `KillHeight` (extra user param) | Lit translucent drops; splash unlit-ish | ≤ 200 drops, ≤ 1k spray, about 0.1 ms |
| **Sparks / embers** | `NS_Sparks`: `Fountain` + velocity-aligned additive sprites, gravity, drag, short life. `NS_Embers`: slow buoyant glowing points with curl noise, long life | Particle `velocity`/`normal_factor` → `Velocity`; lifetime → Lifetime; emission colour or temperature → `Temperature` (material BlackBody) and `Intensity` = 683 x strength | Unlit additive; never a light per spark. One Light-renderer particle for a whole shower at most | ≤ 2k, 0.1-0.2 ms |
| **Dust motes** | `NS_DustMotes`: start from `HangingParticulates`. Tiny lit sprites, near-zero velocity, curl-noise drift; only visible inside light shafts, so lit translucent with a strong forward-scatter look | Blender dust particles: count over box volume → density per m³; `SpawnRate` keeps the alive count = count; size 0.05-0.2 cm; box → `BoxExtent` | Lit; needs a shaft light (spot or sun) in the frame | ≤ 3k, 0.1 ms |
| **Fountain water jets** | `NS_FountainJet`: start from `Fountain`, GPU, velocity-aligned stretched sprites + a mist emitter; for hero pools use `Grid3D_Flip_Hose` (Beta, expensive) | Nozzle object → position + direction; jet apex height *h* → `Velocity` = sqrt(2·980·h) cm/s along the nozzle; flow rate → `SpawnRate`; spread → `VelocityJitter` | Lit translucent with high specular-looking emissive edge; check against Cycles highlights | 5k-20k, 0.5 ms; FLIP 3-8 ms |
| **Screen / CRT / light flicker** | Material parameters + Sequencer tracks (§2.5). No Niagara | Sampled emission or energy curves | n/a | ~0 |

Fire, steam and smoke can borrow the **flipbook-from-Blender** path (§5.1). The look then comes from the exact Cycles
shader, and Niagara only supplies motion, variety and parallax.

### 3.2 Authoring the templates once

1. Use a full editor on a GPU box, with `NiagaraToolsets` + `ToolsetRegistry` enabled (Experimental).
2. Discover tool names with `unreal.ToolsetRegistry.get_all_toolset_json_schemas()`.
3. Per template:
   - `CreateNiagaraSystem` from an empty or minimal system;
   - `AddEmitter(<emitter template above>)`;
   - `AddUserVariables(...)`, using the shared parameter names;
   - `SetStackInputData` to link module inputs to the `User.` parameters;
   - `SetRendererData` for alignment, SubUV and sort settings;
   - `SetSystemData` for determinism and fixed bounds.
4. Then call `GetSystemCompileState` and `GetStackIssues`, and fix every error. Epic's own skill text says errors only
   surface once the system has compiled in the editor.
5. A human pass in the Niagara editor is fine as well. The contract is only the user-parameter list above.
6. Save, commit the plugin, and record each system's parameter list in `Plugins/AnySceneFX/templates.json`
   (`{"NS_Steam": {"SpawnRate": "float", ...}}`). The converter reads `param_types` from that file.

---

## 4. Detection rules and the `scene.json` `fx` schema

### 4.1 Classifying Blender effects (exporter side)

Walk every renderable object. A hit gets an `fx` entry and is **not** also exported as a mesh or an LFV, unless
§5 picks the LFV technique. Score each candidate type with the evidence below, take the highest score, and set
`confidence` = top score ÷ (top + runner-up).

| Evidence | Where | Points toward |
|---|---|---|
| Material is volume-only (`is_volume_only`) with `PRINCIPLED_VOLUME` | material | a volume type (steam / smoke / haze / fire) |
| Principled Volume `Emission Strength` > 0, or linked, or `Blackbody Intensity` > 0, or a `BLACKBODY` node, or a `VALTORGB` ramp into Emission Color with orange-to-blue stops | node tree | **fire** |
| Volume with emission 0, albedo > 0.85 grey, density driven by noise + a mapping driver on Z (`-frame*k`) | node tree + drivers | **steam** (k fast, under a hot object) or **smoke** (albedo < 0.85, or name) |
| Volume with no `TEX_NOISE` or a constant density, box > 3 m on its long axis | node tree + size | **haze** (→ fog, §5.3) |
| Volume with noise but drift ≤ 0.002 m/frame and large box | node tree | **haze plume** |
| `FLUID` modifier `DOMAIN`, `domain_type GAS`, cache in OPENVDB | modifier | steam / smoke / fire by `flow_type` of the FLOW objects (`SMOKE`, `FIRE`, `BOTH`) → prefer **SVT** (§5.2) |
| `FLUID` DOMAIN `LIQUID` | modifier | fountain or splash (mesh cache → Alembic or FLIP; flag it for agent review) |
| `VOLUME` object (VDB file) | object type | SVT direct import |
| `PARTICLE_SYSTEM` with `physics_type NEWTON`, `rotation_mode VEL`, velocity mostly −Z ≥ 3 m/s, small elongated instance | particle settings | **rain** |
| … same, slow (< 1 m/s) along −Z, `effector_weights.gravity` ≈ 1, emitter is a thin strip | particle settings | **drips** |
| particles with gravity, short life (< 1.5 s), emissive instance material | settings + material | **sparks** |
| particles with emissive instance, upward velocity, long life | | **embers** |
| particles with ~0 velocity, gravity 0, tiny instance, box emitter | | **dust motes** |
| particles from a small emitter with upward velocity cone, gravity 1, water-like instance (transmission or low roughness) | | **fountain** |
| `NODES` modifier whose tree contains `DISTRIBUTE_POINTS_IN_VOLUME`/`ON_FACES` + `INSTANCE_ON_POINTS` and a `SCENE_TIME` input driving `SET_POSITION` | geometry nodes | rain, dust or drips by the same velocity rules. Sample point positions at two frames to get the velocity |
| Material with drivers/keys on Emission Strength or Color, on a mesh that is a screen (prop name `screen`, `crt`, `monitor`, `tv`, `display`, `sign`) | `animated_materials` | **screen flicker** |
| Light with driver/action on `energy`/`color` | `light_entry.animated` | **light flicker** (sample the curve) |
| Object or material **name** contains a type word (`steam`, `vapor`, `smoke`, `curl`, `haze`, `fog`, `mist`, `flame`, `fire`, `ember`, `spark`, `rain`, `drizzle`, `drip`, `splash`, `dust`, `mote`, `fountain`, `jet`, `flicker`) | names | +2 to that type (tie-breaker, never sufficient alone) |

Also export, per entry:
- `bounds_ue`;
- the emitter shape (box, disc or line from the object's evaluated mesh bounds);
- `preroll_s` from `frame_start < 0` or the fluid `cache_frame_start`;
- the cameras whose frustum contains the bounds;
- the nearest light within 1 m (`light_link`), so fire never double-lights.

For procedural volumes, keep `sample_volume()` but take **8-16 slices**, not 4. Also measure the drift speed by
diffing the mapping-node location driver between two frames, and write the `params` directly.

### 4.2 Schema (JSON Schema 2020-12) for `scene.json → "fx"`

```json
{
  "$id": "anyscene/fx.schema.json",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["id", "type", "confidence", "source", "transform", "bounds_ue", "technique", "params", "time", "seed"],
    "properties": {
      "id":         {"type": "string", "pattern": "^[A-Za-z0-9_]+$"},
      "type":       {"enum": ["fire", "steam", "smoke", "haze", "haze_plume", "rain", "drips", "splash", "sparks",
                              "embers", "dust", "fountain", "screen_flicker", "light_flicker", "unknown"]},
      "confidence": {"type": "number", "minimum": 0, "maximum": 1},
      "source": {"type": "object", "required": ["kind", "objects"], "properties": {
          "kind":     {"enum": ["volume_shader", "fluid_domain", "vdb", "particles", "geonodes",
                                "animated_emission", "animated_light"]},
          "objects":  {"type": "array", "items": {"type": "string"}},
          "material": {"type": ["string", "null"]},
          "evidence": {"type": "array", "items": {"type": "string"}}}},
      "transform": {"type": "object", "required": ["loc", "quat"], "properties": {
          "loc":   {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
          "quat":  {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4},
          "scale": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}}},
      "bounds_ue":    {"type": "object", "required": ["center", "extent"], "properties": {
          "center": {"type": "array", "items": {"type": "number"}}, "extent": {"type": "array", "items": {"type": "number"}}}},
      "bounds_local": {"type": "object", "properties": {"min": {"type": "array"}, "max": {"type": "array"}}},
      "emitter_shape": {"type": "object", "properties": {
          "kind": {"enum": ["box", "disc", "ring", "line", "plane", "point", "mesh"]},
          "extent_cm": {"type": "array", "items": {"type": "number"}},
          "normal": {"type": "array", "items": {"type": "number"}}}},
      "technique": {"enum": ["niagara", "niagara_flipbook", "niagara_volume_sprite", "svt", "local_fog",
                             "height_fog", "material", "sequencer_curve", "skip"]},
      "template":  {"type": ["string", "null"], "description": "UE object path, e.g. /AnySceneFX/Systems/NS_Steam.NS_Steam"},
      "params":      {"type": "object", "additionalProperties": {"type": ["number", "boolean", "array"]}},
      "param_types": {"type": "object", "additionalProperties": {"enum": ["float", "int", "bool", "vec3", "pos", "color"]}},
      "physical": {"type": "object", "description": "raw Blender-side measurements kept for the look-match pass",
        "properties": {
          "density_per_m": {"type": "number"}, "optical_depth": {"type": "number"},
          "albedo": {"type": "array"}, "anisotropy": {"type": "number"},
          "emission_nits": {"type": "number"}, "emission_color": {"type": "array"}, "temperature_k": {"type": "number"},
          "count": {"type": "integer"}, "lifetime_s": {"type": "array"}, "velocity_cm_s": {"type": "array"},
          "velocity_jitter": {"type": "number"}, "gravity": {"type": "number"}, "size_cm": {"type": "array"},
          "drift_cm_s": {"type": "array"}, "noise_scale_cm": {"type": "number"}}},
      "time": {"type": "object", "required": ["preroll_s", "fps"], "properties": {
          "preroll_s": {"type": "number", "minimum": 0}, "fps": {"type": "number"},
          "start_frame": {"type": "integer"}, "end_frame": {"type": "integer"}, "animated": {"type": "boolean"}}},
      "seed":       {"type": "integer", "minimum": 0},
      "flicker":    {"type": "object", "properties": {
          "target": {"type": "string"}, "property": {"enum": ["intensity", "emissive_scale", "color"]},
          "fps": {"type": "number"}, "values": {"type": "array", "items": {"type": "number"}}}},
      "flipbook":   {"type": "object", "properties": {
          "texture": {"type": "string"}, "grid": {"type": "array"}, "fps": {"type": "number"}, "emissive": {"type": "boolean"}}},
      "vdb":        {"type": "object", "properties": {"files": {"type": "string"}, "grids": {"type": "array"}}},
      "cameras":    {"type": "array", "items": {"type": "string"}},
      "light_link": {"type": ["string", "null"]},
      "notes":      {"type": "array", "items": {"type": "string"}}
    }
  }
}
```
- Units: positions are UE centimetres; velocities are cm/s in UE axes; `extent` is a half-extent in cm; `seed` =
  `crc32(id)`.
- **Ownership.** The exporter fills everything except `technique`, `template` and `params`. A deterministic step
  (`fx_plan.py`, using the decision table in §5.4) fills those three, and the agent may override them.
- `build_level.py` gets a `stage_fx` that dispatches on `technique`. Keep the old `volumes` map for backward
  compatibility, but skip any volume an `fx` entry claims.

---

## 5. Alternatives when Niagara is not the right tool

### 5.1 Flipbooks (SubUV) rendered from the Blender volume

**Best for:** fire, steam puffs and smoke at mid-distance. The look *is* the Cycles shader, with zero tuning of
Niagara colour or density.

How to bake, in a Blender job on the scene copy:
1. Isolate the volume object. Use a transparent film (`film_transparent`) and an orthographic camera fitted to the
   bounds, facing the hero camera's azimuth.
2. Use a black world, plus a neutral key light if the effect is lit (steam). Emissive flames need no light.
3. Render *N* = 64 frames at the scene fps from a steady-state frame. Crossfade the last 16 into the first 16 for a
   loop.
4. Tile 8x8 at 256-512 px per cell. Write RGBA as EXR, or PNG with premultiplied alpha.
5. Export twice for lit effects: an emissive-only pass, and an albedo/alpha pass.
6. Unreal side: `SubImageSize` (8,8) on the sprite renderer, plus a SubUV Animation module whose renderer input
   points at that renderer. Get all three of these right: the grid, the module, and the renderer binding. Any one
   wrong fails **silently**.

Use a flipbook when the camera stays within about 30° of the bake view. Beyond that, sprites rotate visibly; use two
or three bakes at different azimuths, or SVT.

### 5.2 Heterogeneous volumes from VDB (SVT)

**Best for:** hero steam, smoke or fire seen up close or from moving cameras. This is the real 3D density and is the
closest match to Cycles.

**Mantaflow domains.** `cache_data_format = OPENVDB` already writes `cache/data/fluid_data_####.vdb`. Re-save only
the `density`, `flame` and `temperature` grids, or the default mapping packs velocity components into attributes B.

**Procedural shader volumes** (HK steam, MC curls):
1. Sample the material on a 3D grid. Extend `sample_volume` to bake Z slices at 64-128 slices.
2. For animation, repeat per frame for 48-96 frames.
3. Write `.vdb` with Blender's bundled `openvdb` module: `openvdb.FloatGrid`, `copyFromArray`,
   `openvdb.write(path, grids)`.
4. Name the grids `density`, plus `emission` or `temperature`.

**Import into Unreal.**
- Use an `AssetImportTask` on the first file of the numbered sequence. In a commandlet the factory takes the
  unattended path and imports the sequence as an **animated SVT**.
- Optionally pass a `UOpenVDBImportOptionsObject` as `task.options` to control the grid mapping.
- The `InterchangeOpenVDB` plugin is disabled by default. The legacy SVT factory does not need it.

**Render.**
- Spawn `unreal.HeterogeneousVolume`. Its `heterogeneous_volume_component` takes a Volume-domain material that samples
  the SVT (start from `/NiagaraFluids/Materials/Grid3D/Instances/MI_HeterogeneousVolumes_Basic`).
- Animation fields on the component: `frame`, `frame_rate`, `start_frame`, `end_frame`, playing and looping.
- Lighting fields: `step_factor`, `shadow_step_factor`, `lighting_downsample_factor`.
- Map Blender density σ (1/m) to material extinction: σ ÷ 100 per cm, if the material works in world units. Calibrate
  once against a Cycles render of a test cube.

**Cvars.**
- `r.HeterogeneousVolumes 1` (default on).
- `r.HeterogeneousVolumes.Shadows 0` by default: turn it on for self-shadowing steam.
- `r.HeterogeneousVolumes.IndirectLighting 0` by default.
- `r.HeterogeneousVolumes.MaxStepCount 512`.
- `r.HeterogeneousVolumes.Composition 0`: draws before translucency. All *[engine: HeterogeneousVolumes.cpp]*.

**Cost.** Several ms per volume at 1440p. Fine for MRQ, too heavy for a real-time budget unless
`DownsampleFactor` = 2.

### 5.3 Fog for haze

- **Room or street haze** (homogeneous layers, or a large box with gentle noise): Exponential Height Fog plus
  volumetric fog, as `build_level.py` already does.
- **Local layers** (MC ceiling layer, under-awning haze): Local Fog Volumes. Fix §0.2 as follows.
  - Scale = (max box half-extent in cm) ÷ 500.
  - It is a sphere: a long flat box needs several LFVs tiled along its long axis, or height-fog mode
    (`height_fog_extinction`, `height_fog_falloff`, `height_fog_offset`).
  - `radial_fog_extinction` = σ x 2r (m), the optical depth through the centre.
  - `fog_emissive` is luminance: σ_e x 683 nits.
- **Never use an LFV for a flame or a plume.** It cannot move, and its shape is a sphere.

### 5.4 Decision table (per effect)

| Type | Default technique | Use instead when |
|---|---|---|
| fire | `niagara_flipbook` (NS_Fire, flame baked from Blender) | close-up hero, camera moves around it, long shot → `svt` (bake VDB 64 frames) or `Grid3D_Gas_Fire`; tiny candle → unlit sprite, no flipbook |
| steam | `niagara` (NS_Steam lit sprites) + volume-sprite core if volumetric fog is on | Mantaflow cache present, or a hero close-up → `svt`; distant/static → `niagara_flipbook` |
| smoke | curls → `niagara` ribbons; plumes → as steam | — |
| haze | `height_fog` / `local_fog` | visible moving wisps in a light beam → `niagara_volume_sprite` |
| haze_plume | `niagara_volume_sprite` | static in all shots → `local_fog` (fixed size rule) |
| rain | `niagara` (NS_Rain) | only seen through glass far away → material streaks on a card |
| drips / splash | `niagara` (NS_Drips) | ground ripples → animated decal / puddle material |
| sparks / embers | `niagara` | — |
| dust | `niagara` (NS_DustMotes) | — |
| fountain | `niagara` (NS_FountainJet) | Mantaflow liquid cache → Alembic mesh sequence (outside this doc; flag it) |
| screen_flicker / light_flicker | `material` / `sequencer_curve` | — |

---

## 6. Verification loop: did the effect land?

1. **Build.** Run `stage_fx` and save. The build report records, per effect: id, technique, template, user params
   read back (`get_variable_*` valid flags), and fixed bounds read back. Any invalid param is an error, not a warning.
2. **Render.**
   - Render MRQ stills from **every camera in the effect's `cameras`**:
     `render_mrq.ps1 -Cams ...`, with `-dpcvars=Editor.AsyncAssetCompilation=0,fx.Niagara.ForceWaitForCompilationOnActivate=1`.
   - Use the **same frame number** as the Cycles still: the exporter's `--frame`, minus the sequence start.
   - For motion, render 24-frame clips of the effect cameras (`custom_end_frame = 24`).
   - Render twice with identical settings to check determinism: the two images' absolute difference should be ~0
     outside the TSR noise floor.
3. **Compare against Cycles.**
   - Use `side_by_side.py`. Compare in the same view transform: use `MRQ_Linear` EXR + Blender AgX, as the pipeline
     already does.
   - For each effect, crop its projected `bounds_ue` box in both images, then compare:
     - **coverage**: the fraction of crop pixels changed vs a render with the effect hidden; render one "FX off"
       still per camera;
     - **mean luminance** and the **99th-percentile luminance** inside the crop, for emissive effects;
     - **contrast and transmission**: background visibility through steam or haze;
     - hue of emissive effects;
     - for rain, streak count, length and angle.
4. **What to look for.**
   - The effect missing entirely: compile, bounds culling, wrong asset, or warm-up.
   - Popping-in in clips: warm-up too short.
   - A box-shaped cut-off: fixed bounds too small.
   - Sharp steam in a blurred foreground: the TranslucencyPass.
   - Black or flat steam: unlit, or no light behind it.
   - Fire that lights nothing, or double lighting: `light_link`.
   - Rain invisible: sprite under a pixel, so check the `PixelCoverageMode` and the width floor.
   - Stepping between frames: the age mode.
   - A sphere-shaped haze blob: the LFV rule.
5. **Adjustment rules.** Change one parameter per round, at most three rounds per effect, and log each round in the
   build report.
   - Coverage too low → raise `SizeMax` first (x1.3), then `SpawnRate` (x1.5). Too high → the reverse order.
   - Too opaque or too faint at matched coverage → scale `Opacity` by `ln(1−T_cycles)/ln(1−T_ue)` (T =
     transmission).
   - Emissive brightness → scale `Intensity` by `L99_cycles / L99_ue`, clamped to x[0.25, 4] per round.
   - Wrong height or reach → `LifetimeMax` (plumes) or `Velocity.z`; keep `Velocity x Lifetime` = the measured Cycles
     reach.
   - Wrong lean → `Wind`.
   - Rain too dense or sparse → `SpawnRate` by the streak-count ratio; streaks too short → the stretch factor
     (speed x shutter), not velocity.
   - After three rounds without converging, switch technique (§5.4 "use instead") and note why in `notes`.

---

## 7. Known gotchas (with sources)

| Gotcha | Fix | Source |
|---|---|---|
| GPU particles absent or frozen in MRQ warm-up | `render_warm_up_frames = True`; engine warm-up alone doesn't run GPU sims | `MoviePipelineAntiAliasingSetting.h` tooltip *[engine]*; Epic MRQ docs |
| `engine_warm_up_count` ignored | `use_camera_cut_for_warm_up = False` (it's EditCondition-gated) | same header |
| Effect missing on the first frames of an offscreen run | `fx.Niagara.ForceWaitForCompilationOnActivate=1` + `Editor.AsyncAssetCompilation=0` | `NiagaraComponent.cpp:112, 1358` *[engine]*; `render_shots.py` notes |
| Nothing renders or compiles in `-run=pythonscript` | expected: null RHI unless `-AllowCommandletRendering`; render in the `-game` pass | `LaunchEngineLoop.cpp:2246` *[engine]* |
| User param silently ignored | exact name + exact type; read back with `get_variable_*` and check the valid flag; set the asset before params (`set_asset` resets overrides) | `NiagaraComponent.cpp:4376, 4620` *[engine]*; NiagaraToolsets `blueprint_interop` skill |
| Effect culled when its origin leaves the view | fixed bounds covering the whole travel; GPU emitters can't use dynamic bounds | `NiagaraSystem.h:1052`; NiagaraToolsets `optimization` skill |
| Effect dropped at distance or by budget | `set_allow_scalability(False)`; `MoviePipelineGameOverrideSetting` | `NiagaraComponent.h` *[engine]* |
| Different particles every run | system + emitter `bDeterminism`, a fixed `RandomSeedOffset`, fixed MRQ warm-up; sim cache for bit-exact results | `NiagaraSystem.h:1073-1085` *[engine]* |
| Translucent FX sharp in defocused areas | material `TranslucencyPass = MTP_BeforeDOF` (default is AfterDOF) | `Material.h:142`, `Material.cpp:1183` *[engine]* |
| Sprite motion blur smears or vanishes | rely on MRQ temporal samples (8); renderer `MotionVectorSetting` Precise for fast sparks, Disable for steam; post-process motion blur is off in the converter (`motion_blur_amount 0`) | `NiagaraRendererProperties.h:480` *[engine]* |
| Thin rain or sparks flicker or disappear under TSR | `PixelCoverageMode` Automatic (project setting enabled) and a width floor; velocity-aligned streaks | `NiagaraSpriteRendererProperties.h` *[engine]* |
| Fire doesn't light the set; Lumen ignores emissive sprites | real lights (Blender practicals or one Light-renderer particle); Niagara lights are CPU-only and shadowless unless MegaLights (`bAllowMegaLights`, `bMegaLightsCastShadows`) | `NiagaraLightRendererProperties.h:62-110` *[engine]*; NiagaraToolsets `renderers` skill |
| Particle lights invisible in fog | light needs volumetric scattering intensity > 0 | *[docs: Volumetric Fog]* |
| Lit translucency looks flat or blotchy | it's the translucency lighting volume; use Volumetric NonDirectional, keep sprites large and soft | Lumen translucency behaviour *[docs]* |
| SubUV shows the whole atlas | renderer `SubImageSize` + a SubUV module + its renderer binding | NiagaraToolsets `renderers` skill |
| Local fog volume 5x too big / spherical | base radius 500 cm; uniform max-axis scale; extinction = optical depth through the centre | `LocalFogVolumeComponent.h:74`, `LocalFogVolumeCommon.ush:178-203` *[engine]* |
| VDB import pops a dialog | not in a commandlet or with automated tasks; numbered files become an animated SVT | `SparseVolumeTextureFactory.cpp:436` *[engine]* |
| Blender motion blur on volumes | irrelevant in UE, but the Cycles reference frames have no volume blur (object blur off on volume boxes); don't add any in UE either | HK `fx.py`, `SKILL.md` §11 |

**Sources.**
- Installed engine files:
  - `Engine/Plugins/FX/Niagara/Source/Niagara/{Public/NiagaraComponent.h, Public/NiagaraActor.h,
    Public/NiagaraFunctionLibrary.h, Classes/NiagaraSystem.h, Classes/NiagaraEmitter.h,
    Public/NiagaraLightRendererProperties.h, Public/NiagaraSpriteRendererProperties.h, Public/NiagaraCommon.h,
    Public/MovieScene/MovieSceneNiagaraSystemSpawnSection.h, Classes/NiagaraSimCacheFunctionLibrary.h,
    Private/NiagaraComponent.cpp, Private/NiagaraSystemInstance.cpp}`
  - `Engine/Plugins/FX/{NiagaraFluids, NiagaraMRQ, NiagaraSimCaching}`
  - `Engine/Plugins/Experimental/Toolsets/NiagaraToolsets` (tools + `Content/Python/skills`)
  - `Engine/Plugins/Experimental/ToolsetRegistry`
  - `Engine/Plugins/MovieScene/MovieRenderPipeline/.../MoviePipelineAntiAliasingSetting.h`
  - `Engine/Source/Runtime/Engine/Classes/Components/{HeterogeneousVolumeComponent.h, LocalFogVolumeComponent.h}`
  - `Engine/Source/Runtime/Renderer/Private/HeterogeneousVolumes/HeterogeneousVolumes.cpp`
  - `Engine/Shaders/Private/LocalFogVolumes/LocalFogVolumeCommon.ush`
  - `Engine/Source/Editor/SparseVolumeTexture/Private/SparseVolumeTextureFactory.cpp`
  - `Engine/Source/Runtime/Engine/Public/Materials/Material.h`
  - `Engine/Source/Runtime/Launch/Private/LaunchEngineLoop.cpp`
- Epic docs:
  - [Volumetric Fog](https://dev.epicgames.com/documentation/en-us/unreal-engine/volumetric-fog-in-unreal-engine)
  - [Rendering your Niagara systems (MRQ)](https://dev.epicgames.com/documentation/unreal-engine/rendering-your-niagara-systems)
  - [NiagaraMRQ API](https://dev.epicgames.com/documentation/unreal-engine/API/PluginIndex/NiagaraMRQ)
  - [MoviePipelineAntiAliasingSetting (Python API)](https://api.unrealengine.com/INT/PythonAPI/class/MoviePipelineAntiAliasingSetting.html)
- AnyScene:
  - `scenes/hk-dai-pai-dong/scripts/{fx.py, lights.py, steam.py}`, `NOTES.md`
  - `scenes/mission-control-1970s/scripts/haze.py`
  - `SKILL.md` §11, `builder/CRAFT.md`
