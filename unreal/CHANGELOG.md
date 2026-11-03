# unreal/ converter changelog

## 2026-11-02: one converter (all threads merged) + real-time look pass

Every per-scene thread worked on a copy of `unreal/` taken at 20:17 on 2026-11-01 (`unreal_bakery/_orig` and
`unreal_ramen/_orig` are that snapshot; `unreal_fx/ORIG.md5` and the caustic copy match it). They were merged as
three-way merges against that base, so mission control's 8 fixes, which were already in `unreal/`, stay as they were.
The thread folders are untouched and are now superseded by this one.

### Merged from the threads

| From | What | Where |
|---|---|---|
| caustic (`unreal_caustic/MERGE_BACK.patch`) | Gobo light functions (`M_AnyGobo` + `MPC_AnyTime`, animated mapping fitted to drift+sines, strength chain reduced), IES profiles, a constant emission strength scaling candela | export_blend.py, build_level.py (`stage_light_textures`, `master_gobo`, `gobo_mi`, `key_gobo_time`) |
| caustic | Local-fog fix: tiled LFVs (`lfv_tiles`), uniform scale from the 500 cm base sphere, `radial_fog_extinction` = σ·path, emissive matched to Cycles through the coverage term | build_level.py `stage_level` |
| caustic | Memory: `collect_garbage()` per texture/mesh chunk, `ANYSCENE_MESH_BATCH` | build_level.py |
| caustic | `ANYSCENE_DOLLY` moving-camera sequences, `MRQ_Clip` (whole playback range), `ANYSCENE_MRQ_RES`, `ANYSCENE_MRQ_OUT` | build_level.py |
| caustic | render_mrq.ps1 parameters (`-Project/-Dest/-Level/-ResX/-ResY`) and the full `-dpcvars` set incl. `r.TextureStreaming=0`; export.sh runs the exporter next to itself; side_by_side.py name patterns | render_mrq.ps1, export.sh, side_by_side.py |
| bakery (`anyscene-unreal/bakery/FIXLOG.md`) | #1/#2 hero camera: `ANYSCENE_HERO` → scene.json `active_camera` → `cam_street` → first camera | build_level.py, export_blend.py |
| bakery | #3 full `-dpcvars` in perf.ps1 | perf.ps1 |
| bakery | #5 per-camera `exposure` custom property → CineCamera post-process exposure bias | export_blend.py, build_level.py |
| bakery | #4 side_by_side.py `SBS_CYC` / `SBS_UE` / `SBS_CYC_LABEL` (both `{cam}` and the bakery's `{c}` work) | side_by_side.py |
| bakery | #7/#8 glass look: superseded by the new glass master below (same diagnosis: diffuse-lit white glass = milky veil) | build_level.py |
| ramen (`unreal_ramen/FIXLOG.md`) | **G8** `ensure_bake_uv`: set `active_render` by name after `uv_layers.new()` (posters, signs, decals, menus baked to a flat colour) | export_blend.py |
| ramen | **G9** Principled Alpha baked into ORM.R; cut-out assets get `M_AnyBakedMasked` (clip 0.33); existing MIs are reparented | export_blend.py, build_level.py |
| ramen | G3 Mantaflow domains become `fx` notes instead of opaque fog boxes; G4 `ANYSCENE_HERO_CAM` kept as an alias of `ANYSCENE_HERO` | export_blend.py, build_level.py |
| effects (`unreal_fx/CHANGES.md`) | `fx_pack.py`, `fxlib.py`, `fx_recipes/`, `fx_export.py`, `templates.json`, `FX_AGENT.md` copied in. The exporter calls `fx_export.classify` (`--no-fx` skips it; a failure only logs). `stage_fx`, `place_fx`, `key_flicker`, the fx warm-up in MRQ configs, `ANYSCENE_FX_OVERRIDES`, `ANYSCENE_CLIP_FRAMES` | export_blend.py, build_level.py |
| effects (round 2, synced 2026-11-02 after the merge) | `fx_pack.py`, `fx_export.py`, `fx_recipes/`, `templates*.json`, `FX_AGENT.md` replaced with unreal_fx's round-2 versions: the set_params garbage literal that blacked out every emissive sprite (the reason fire was invisible), in-place pack rebuilds (no `__build` leftovers), pixel coverage, fire pivot, camera-visible fire measurement, physical rain intensity. `classify()` signature unchanged; build_level.py needed nothing. Rebuild `/Game/AnySceneFX` with fx_pack.py in any project that has the old pack | fx_* |
| effects | **Behind a flag:** `ANYSCENE_FX_TYPES`. At merge time the default was `steam`, because fire did not render and rain was too faint. Since round 2 it is `steam,fire,rain` (see "Fx: fire and rain on by default"); other types still need `all` or their name. Flicker tracks are always keyed. The stage skips cleanly when `/Game/AnySceneFX` isn't in the project | build_level.py |
| fal (`unreal_fal/`) | Sharded/cached export: `--plan-out`, `--plan`, `--keys`, `--cache`, `--link-cache`, content hashes; asset names are computed over the full key list, so they are the same in every shard and for `--only` re-exports (before, an `--only` run could name a colliding asset differently); `--gpu` forces OptiX when a factory Blender would bake on the CPU | export_blend.py |

Not merged: `unreal_caustic/scene_defaults.patch` (as instructed); the fal app itself (`unreal_fal/app.py`,
`client.py`), which deploys separately but can now run this exporter unchanged.

### Overlaps resolved once

- **Glass-only meshes (bakery #6, ramen G7, upstream `sections`):** upstream's exporter-side `sections` mapping is kept.
  Exports without `sections` (all current bakery/ramen exports) fall back to the bakery rule (every slot is glass →
  drop the unused baked slot). Ramen's third variant (`n < len(mats)`) was dropped.
- **Glass look (bakery #7/#8 vs the new master):** replaced by the thin-translucent master below.
- **Local fog (caustic vs effects):** caustic's tiled, coverage-matched LFVs, plus the effects rule that volumes
  claimed by an fx entry get no LFV.
- **Hero camera (bakery vs ramen):** one lookup, both env names.
- **MRQ_Clip (caustic vs effects):** renders the sequence's whole playback range; camera sequences are
  `max(48, ANYSCENE_CLIP_FRAMES)` long, and dollies use their own length.
- **export.sh queueing (ramen `EXPORT_NOQUEUE` vs upstream `--gpu`):** upstream's (only `--gpu` bakes queue).
- **perf.ps1 `r.setres`:** upstream's (bakery #9 / ramen G6 are the same fix).

### Real-time look (glass, shadows, AO, tone)

**Glass: new `M_AnyGlass` (v2), thin translucency, no Substrate.** Substrate is off in these projects (`r.Substrate 0`),
and turning it on would recompile and change every scene, so the master uses the legacy Thin Translucent shading
model: Surface ForwardShading, a Fresnel-weighted specular layer with Lumen front-layer reflections, and a coloured
transmittance that tints what's behind it with 1/NoV path length. Per slot (`glass_params`): Transmittance = Blender
colour, Specular from the IOR, Roughness, a frost layer for rough glass (opacity 0 → 0.35), and screen-space IOR
refraction for solid glass (35 % of IOR−1); panes thinner than 2.5 cm get none. Glass renders before DOF, so it
defocuses with the scene. Older masters are rebuilt in place (`master_asset` + `AnySceneVersion` tag), so existing
projects pick it up on a `materials` rerun.
- Gotcha: in 5.8 Python, "Surface ForwardShading" is `TLM_SURFACE_PER_PIXEL_LIGHTING`. `TLM_SURFACE` fails to
  compile ("ThinTranslucent materials must use Surface ForwardShading") and the glass silently renders as the grey
  default material.

**Tone: AgX looks.** The builder ignored `grade.look`. A grey-ramp fit of UE's filmic curve (TonemapCommon.ush) against
Blender's AgX looks (config.ocio) shows the default UE curve *is* AgX High Contrast (best `color_contrast` 0.99,
rms 2/255). Each look therefore maps to `color_contrast = c_look / 1.4` plus the look's saturation, fitted within
~2/255 for every look: Base 0.71, Medium High 0.86, High 1.0, Very High 1.12. Base-contrast scenes were about 40 %
too contrasty before, and High Contrast scenes (bakery) were already right.

**Vignette.** The finish.sh `vignette=angle` → UE `vignette_intensity` mapping was a linear guess that came out about
40 % too weak (ramen: 0.39 vs the fitted 0.635), so frame edges were 1.5–2.5× brighter than Cycles. `vignette_intensity()`
now least-squares-fits UE's cos⁴ falloff (in scene linear, before the tone curve) to ffmpeg's display-space falloff
for the frame's aspect ratio.

**Lumen (grade post-process volume, so it travels with the level):** `lumen_front_layer_translucency_reflections`
on (mirror reflections on glass; Epic scalability leaves it off), `lumen_scene_detail` 2 (small props get cards),
`lumen_final_gather_quality` 2 (less noise and leaking in tight interiors). Overridable per key via `ANYSCENE_LOOK`.

**Shadows/AO: what was measured and not changed** (ramen, MRQ A/B, same frame):
- `r.Lumen.ScreenProbeGather.ShortRangeAO.HardwareRayTracing=1`: mean diff 0.4/255. Short-range AO is already on
  (screen space) at Epic/Cine.
- VSM penumbra `r.Shadow.Virtual.SMRT.MaxRayAngleFromLight` 0.03 → 0.15: 1.0/255.
- Hit lighting, skylight off, bloom off, film grain off: no measurable change. Height fog off: −1 to −4 in the shadows.
- Lumen diffuse GI off: the walls drop to almost Cycles' level. The "flat / no AO" read in ramen is mostly
  tone (look + vignette, fixed above) plus Lumen indirect light about 0.5 EV stronger than Cycles' in that narrow room.
  The bounce excess is not fixed: it isn't a surface-cache leak (hit lighting changes nothing) or a sky leak, and it
  needs a per-light-group investigation.

`ANYSCENE_LOOK` also takes `"light": {...}` (light component properties) and `"glass": {"refraction_scale", "pass"}`.

### Walkable levels: collision + PlayerStart (new `spawn` stage)

PIE / `-game` in the playground spawned the pawn at the world origin (`FindPlayerStart: ... NO PLAYERSTART`), or
somewhere it fell or glitched through floors: meshes are imported with `collision` off, and the PlayerStart sat at the
hero camera's height or was missing. The new `spawn` stage runs by default after `level`, and runs on its own with
`ANYSCENE_STAGES=spawn` on any level built from an export, including one already copied into another project:
- **Collision:** set meshes get complex-as-simple collision (exact, nothing generated, no reimport). Props smaller than
  `ANYSCENE_COLLIDE_MIN_CM` (default 25 cm), glass-only meshes, alpha-cut decals and the sky dome get NoCollision.
- **PlayerStart:** exactly one, placed on the floor under the hero camera + 92 cm with the camera's yaw. The search
  works in rings out to 6 m and only accepts floor-level spots: the floor is the lowest surface found, because a
  trace from eye height lands on stools and counters. Each spot must leave a 36 cm sphere (GameModeBase's
  DefaultPawn) overlapping nothing. A full 88 cm character capsule fit nowhere in the ramen aisle. Use
  `ANYSCENE_PLAYERSTART=keep` to leave a hand-placed start alone.
- The report gets a `spawn` record (start, yaw, floor samples, the first blockers). `ANYSCENE_REPORT` redirects
  the report.

### Fx: fire and rain on by default (round-2 fx files synced from unreal_fx/)
- `ANYSCENE_FX_TYPES` now defaults to `steam,fire,rain`. Drips, dust, sparks, smoke and fountain stay opt-in until a
  scene verifies them (or use `all`).
- Fire verified in AnySceneFX (HK cam_wok, MRQ). Tongues render in the gap between pan and collar, where Cycles shows
  them, at about 3.2k/3.7k nits. Rain renders as a faint streak veil that is still softer than Cycles' sparse bright
  drops; tune it through `ANYSCENE_FX_OVERRIDES` (`Opacity`, `SizeMin`).
- A project that places fx needs `/Game/AnySceneFX`. Build it with `fx_pack.py` (it rebuilds in place, so it is
  safe with placed levels). Today the pack only exists in `anyscene-unreal/AnySceneFX`.

### Other
- render_mrq.ps1 `-Cvars` for A/B renders without a rebuild.
- `skipped` fx ids no longer KeyError on note entries (Mantaflow) that have no `id`.
- Builder docstring lists every environment variable.
