# unreal_fx → unreal: changes to merge

These files were developed in isolation from `anyscene/unreal/`. The baselines were copied at the start; their
checksums are in `ORIG.md5`. Merge them by copying the new files and applying the hunks below to the two changed
scripts.

## New files (copy as-is into `anyscene/unreal/`)

| File | Purpose |
|---|---|
| `fx_pack.py` | Builds `/Game/AnySceneFX` (materials and Niagara systems) headlessly from `fx_recipes/*.json` via NiagaraToolsets, then writes `templates.json` and `templates_report.json`. Env: `ANYSCENEFX_ONLY`, `ANYSCENEFX_RECIPES`, `ANYSCENEFX_ROOT`, `ANYSCENEFX_JSON` |
| `fxlib.py` | Synchronous wrapper over `unreal.ToolsetRegistry.execute_tool` (it decodes the double-encoded JSON results) |
| `fx_recipes/NS_{Fire,Steam,Smoke,Rain,Drips,DustMotes,Sparks,FountainJet}.json` | Declarative templates. A new effect type is a new recipe, with no code change |
| `fx_export.py` | Blender-side classifier and measurement. Writes `fx` entries per NIAGARA.md §4.2 (incl. `flicker`, `light_link`, `physical`, `bounds_local`, `seed`). It runs standalone too, patching an existing export without re-baking meshes |
| `templates.json` | The generated contract (param types + `fx_types`). Regenerate it with `fx_pack.py` |
| `FX_AGENT.md` | The agent loop for new scenes and new effect types |

## Round 2 fixes (fire + rain)

- `fx_pack.py`:
  - **`set_params` root cause.** `AddSetParametersModule` with an HLSL default silently stored a garbage literal
    (`Particles.DynamicMaterialParameter` x = -4.2e36), which blacked out every emissive sprite. That's why the fire was
    invisible and the rain emissive was 0. It now always adds a typed placeholder, rewires each entry to HLSL, and reads
    the values back. A dropped expression becomes a build issue.
  - **In-place rebuild.** Existing systems are stripped (emitters + user vars) and rebuilt. Existing materials get
    their graph cleared and rebuilt. No delete, consolidate or rename, so placed levels keep working and no `__build`
    assets are left behind.
  - **Sprite renderers.**
    - `PixelCoverageMode=Enabled`, so sub-pixel streaks keep their energy.
    - Non-uniform (elongated) sprites get no random rotation.
    - New `pivot` core option. NS_Fire uses `[0.5, 0.85]`, so tongues grow up from the spawn point.
  - **M_AFX_Flame** is now a soft gaussian tongue (it used to be a hard triangle).
  - NS_Fire's Flames and Core emitters run on GPU sim.
- `fx_export.py`:
  - **Fire is measured from what a camera can see.** `visible_field` ray-casts every emitting sample to every scene
    camera (volume-only objects count as see-through). Ring, band and spawn height come from the visible part.
    `physical.visibility` and `visible_rz` record it.
  - **Fire brightness = view-ray line integral** through the sampled emission (`view_radiance`), not local emission x
    ring spread. HK burners now read 3.2k and 3.7k nits (they used to read 9.7k, and later 1.2k vs 4.8k).
  - **Fire colour comes from the whole flame.** A guard falls back if the colour comes out black.
  - **Rain/drips Intensity** = 683 x drop emission x drop length / streak length (it used to be a 0.1 guess).
- `work/`: `fxstage.sh` (stages fx,sequences), `mrq.sh`, `clean_fire.py` (one-off cleanup of the old leftover), and
  probes (`probe_rend.py`, `probe_dp.py`, `proj_vis.py`).

## `export_blend.py` (one hunk, not yet applied in this copy, to keep the main exporter untouched while others run it)

In `main()`, after the object walk and before `scene = {...}`:
```python
    import fx_export  # unreal/fx_export.py
    report["fx"] = fx_export.classify(sc, FRAME, sorted(emitters), sorted(report["volumes"]),
                                      os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates.json"))
    for e in report["fx"]:
        for o in e["source"]["objects"]:
            if o in report["volumes"]:
                report["volumes"][o]["claimed_by_fx"] = True
```
(`sys.path` already contains the script's folder when Blender runs it with `--python`. If it doesn't, add
`sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))`.) The old `report["fx"]` note entries are replaced.
On HK, the standalone equivalent is:
`blender -b work/hk_copy.blend --python unreal/fx_export.py -- --scene export/scene.json --out <dir>/scene.json --frame 60` (45 s).

## `build_level.py` (applied in `unreal_fx/build_level.py`; diff it against `unreal/build_level.py`)

1. Docstring and env:
   - `ANYSCENE_STAGES` gains `fx`. The default is now `textures,meshes,materials,level,fx,sequences`.
   - New `ANYSCENE_FX_OVERRIDES` (look-match overrides JSON), `ANYSCENE_CLIP_FRAMES` (default 96) and
     `ANYSCENE_MRQ_OUT` (MRQ output folder; the default stays `<export>/../compare/mrq`).
2. **Local fog volume fix** in `stage_level`:
   - Volumes with `claimed_by_fx` are skipped (flames and plumes are Niagara now).
   - Scale is uniform: `max(extent) / 500` (base radius 500 cm, max-axis sphere).
   - `radial_fog_extinction = sigma × 2r` (optical depth through the centre).
   - `fog_emissive` is multiplied by 683.
3. New `fx_params`, `place_fx`, `stage_fx`:
   - The asset is set first, then the typed user params (+ overrides), then every param is read back; invalid
     params go to `REPORT["errors"]`.
   - Seed offset = `crc32(id)`.
   - Fixed local bounds, warm-up ticks = `preroll_s × fps`, `allow_scalability` off.
   - The stage is rerunnable on its own: it deletes `FX_*` actors first.
4. New `key_flicker`: per camera sequence, a float track on the linked practical light's intensity, built from the
   exporter's sampled `flicker.values`.
5. `stage_sequences`:
   - Playback and camera-cut range are `max(48, CLIP_FRAMES)`.
   - New `MRQ_Clip` config (frames `0..CLIP_FRAMES`).
   - `engine_warm_up_count = max(64, ceil(1.5 × longest preroll × fps))`.
   - `use_camera_cut_for_warm_up = False` is now set explicitly.

## Project requirements (`AnySceneUE.uproject` / playground)

- Enable the `Niagara`, `ToolsetRegistry` and `NiagaraToolsets` plugins. The toolsets are only needed where
  `fx_pack.py` runs; rendering only needs Niagara plus the `/Game/AnySceneFX` content.
- MRQ renders: add `fx.Niagara.ForceWaitForCompilationOnActivate=1` to `-dpcvars` in `render_mrq.ps1` and `perf.ps1`.
- The copy project sets `bRemoteExecution=False`, so headless instances don't answer the user's `ue.py` bridge.
