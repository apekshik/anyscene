# TOGGLE.md: an `unreal` option on `/ref2scene`, and `/scene2unreal`

Design note. Nothing here is implemented yet. It builds on `unreal/export_blend.py`, `unreal/build_level.py`,
`unreal/render_mrq.ps1`, `unreal/perf.ps1` and `unreal/NIAGARA.md`, and on `builder/app.py`
(`SceneBuilderApp`, `BuildRequest`, `_build_and_shoot`).

## 1. API

### 1a. Toggle on `/ref2scene` (and its `/build` alias)

Add one optional field to `BuildRequest`. Like `shots`, it stays **out of the build fingerprint** (`fp` in `_build`),
so one Blender build serves any number of Unreal conversions.

```python
class UnrealOptions(BaseModel):
    enabled: bool = Field(True, description="Convert the passed build into an Unreal 5.8 level.")
    cameras: list[str] = Field(default_factory=list, description="Cameras to render MRQ stills from (default: every scouting camera in shots.json).")
    fx: bool = Field(True, description="Port effects (flames, steam, rain, ...) per NIAGARA.md. False: static fog only.")
    look_match_rounds: int = Field(2, description="Agent look-match passes against the Cycles frames (0 = deterministic conversion only).")
    package: str = Field("plugin", description="plugin: a UE content plugin zip (drop into any 5.8 project). uproject: a full project zip. both.")
    still_res: list[int] = Field([1920, 1080], description="MRQ still resolution (W, H).")
    clip_frames: int = Field(0, description="Also render N-frame MRQ clips per camera (0 = stills only).")
    perf: bool = Field(True, description="Run the real-time perf capture (CSV profiler, GPU memory) at perf_res.")
    perf_res: list[int] = Field([2560, 1440])
    gpu_budget_ms: float = Field(16.6, description="Real-time frame budget the perf report grades against.")

class BuildRequest(BaseModel):
    ...
    unreal: UnrealOptions | None = Field(None, description="Optional: once the build passes its critic, convert it to Unreal.")
```

Add to `BuildResponse`: `unreal_job: dict | None`, holding status, `request_id` and an error if any, with the same
shape as `shots_job`. Add `unreal: UnrealResult | None` (§3).

### 1b. Standalone `/scene2unreal`

`SceneUnrealRequest = {build_id: str, **UnrealOptions, fresh: bool = False, effort: str = "medium"}`.
- It runs on any finished build in `/data/anyscene/builder/<build_id>`.
- It is retry-safe the same way `_build` is: an index keyed by `sha256(build_id + options)` and an `.alive`
  heartbeat.
- `/ref2scene` with `unreal` set calls it **after** `_build`, exactly like `_anyshot`.
- Run it as a **separate fal app** (`anyscene-unreal`) on a UE container. The builder image stays Blender-only, and
  the UE image (about 40 GB with DDC) only starts when someone asks for Unreal. The builder forwards the order with
  `fal_client` and relays the stage lines, as `call_anyshot` does.

## 2. What runs after the critic passes

The gate is the same as for shots: `res.critiques[-1]["passed"] and res.scene_blend_url`.

| # | Stage | Where | Deterministic? |
|---|---|---|---|
| 1 | **Export**: `blender -b <copy> --python export_blend.py -- --out exp/ --gpu --grade-sh ... --frame <hero frame>`, sharded (§5), then a merge pass writes `scene.json` incl. `fx` (NIAGARA.md §4) and the flipbook / VDB bakes the FX plan asks for | builder GPU worker (has Blender + OptiX cache) or the UE worker if Blender is installed there | yes |
| 2 | **FX plan**: `fx_plan.py` fills `technique / template / params` per `fx` entry from the NIAGARA.md decision table | either | yes (rules); entries with `confidence < 0.6` are queued for the agent |
| 3 | **UE build**: `UnrealEditor-Cmd AnySceneUE.uproject -run=pythonscript -script=build_level.py` (stages textures, meshes, materials, level, fx, sequences) on a **Linux GPU container** with the AnySceneFX plugin preinstalled and a persistent DDC on `/data` | UE worker | yes |
| 4 | **Shader warm**: one `-game -RenderOffscreen` run of the level with `fx.Niagara.ForceWaitForCompilationOnActivate=1` and `Editor.AsyncAssetCompilation=0` to fill the DDC (skipped when DDC is warm) | UE worker | yes |
| 5 | **MRQ stills** per camera (`MRQ_Still` + `MRQ_Linear`), plus clips if requested | UE worker | yes, given a fixed seed and warm-up |
| 6 | **Look-match pass** (agent): compare against the Cycles stills (`side_by_side.py`, crops per `fx` bounds, exposure, fog), adjust **parameters only** (exposure offset, fog density, FX user params, light scale) with the NIAGARA.md §6 rules, rebuild only the `level`/`fx` stages, re-render; `look_match_rounds` times | UE worker + Claude | agent-judged, logged as a param diff |
| 7 | **Perf**: `perf.ps1`-equivalent `-game -RenderOffscreen` with `csvprofile`, `nvidia-smi` sampling | UE worker | measured |
| 8 | **Package**: `Plugins/AnyScene_<build>/Content/...` (+ `.uplugin`) zip; optionally the whole `.uproject` minus `Intermediate/`, `Saved/`, `DerivedDataCache/` | UE worker | yes |

**Linux notes.**
- The Linux editor renders through Vulkan (SM6). `-RenderOffscreen` works without a display. Install the Vulkan ICD
  from the NVIDIA container toolkit (`NVIDIA_DRIVER_CAPABILITIES=all`, as the builder Dockerfile already sets).
- Lumen with hardware ray tracing on Vulkan needs a recent driver. Fall back to `r.Lumen.HardwareRayTracing 0` and
  record which mode the render used.
- Swap the Windows `.ps1` wrappers for Python `subprocess` callers. `render_mrq.ps1` and `perf.ps1` are thin.
- Validate on Linux once against the Windows reference box before trusting look-match numbers. Vulkan vs D3D12
  shading differences are small but non-zero. *[untested]*

## 3. Outputs (`UnrealResult`)

```json
{
  "package_url": "...AnyScene_b_xxxx_plugin.zip",
  "uproject_url": "... (optional)",
  "stills": [{"camera": "cam_street", "ue": "...png", "ue_linear": "...exr", "cycles": "...png", "side_by_side": "...png"}],
  "clips": [],
  "look_match": {"rounds": 2, "changes": [{"round": 1, "target": "fx:steam_wok_0", "param": "Opacity", "from": 0.12, "to": 0.18, "why": "transmission 0.71 vs 0.58"}]},
  "fx": [{"id": "steam_wok_0", "type": "steam", "technique": "niagara", "template": "/AnySceneFX/Systems/NS_Steam", "status": "ok"}],
  "perf": {"res": [2560, 1440], "gpu_ms_p50": 0, "gpu_ms_p95": 0, "frame_ms_p95": 0, "gpu_mem_delta_mb": 0, "draw_calls": 0, "verdict": "within budget|over budget"},
  "build_report": "...build_report.json",
  "warnings": [],
  "minutes": {"export": 0, "ue_build": 0, "mrq": 0, "look_match": 0, "total": 0}
}
```

## 4. Time and cost (from the HK run: 627 meshes)

| Stage | HK today (serial) | With §5 sharding | Notes |
|---|---|---|---|
| Blender export (bake + GLB) | ~35 min | ~6-9 min | about 3.3 s per unique mesh; scales with unique meshes, not instances |
| FX bakes (flipbooks / VDB) | n/a | +2-6 min | only for `niagara_flipbook` / `svt` entries; runs in parallel with the mesh shards |
| UE build (import + level) | ~15 min | ~10-15 min | import-bound; Interchange is already batched by 16; FX stage adds < 1 min |
| Shader warm (cold DDC) | ~3-5 min | 0-5 min | ~0 once `/data` DDC is warm for the templates and master materials |
| MRQ stills | ~1 min/still | ~1 min/still | 3 cameras x (1 + rounds) with rounds = 2 → 9 stills ≈ 9 min (or ~45 s each when batched in one process instead of one per camera) |
| Look-match agent | n/a | ~3-5 min/round of thinking + rebuild (`level,fx` stages ≈ 1-2 min) | |
| Perf capture | n/a | ~2 min | 900 frames + startup |
| **Total** | **~55 min + stills** | **~30-40 min** | |

**Cost** = GPU-minutes x the fal machine rate, plus agent tokens.
- GPU time is about 35 GPU-minutes on the parallel path.
- The export shards are CPU-heavy. Bakes can use `--gpu` (OptiX) on the builder's own GPU. Run the export on the
  builder worker that already holds the scene, and hand only `exp/` (GLBs + PNGs, roughly 1-3 GB for HK) to the UE
  app through `/data`.
- Agent tokens apply only to look-match rounds and to low-confidence FX entries: roughly one Claude session of about
  15-30 tool calls per round.
- With `look_match_rounds = 0` the job is purely deterministic and costs only GPU time.

## 5. Parallelizing the slow export

The export is embarrassingly parallel per unique mesh. Bakes are independent, and existing outputs are skipped
(rerunnable).

1. **Plan pass.** One quick Blender process classifies the objects and writes `export_plan.json`: the list of asset
   keys with estimated bake pixels (area x density). It does no baking.
2. **Shards.** Run *N* Blender processes on copies of the `.blend`, each started with `--shard i/N`. This is a new
   flag: keep `keys[k]` where `k % N == i`, after sorting by estimated cost and dealing round-robin, so shards
   balance. Each shard bakes into the shared `tex/` and `mesh/` directories.
   - Today's `--reverse` and `--only` already show that two processes can share the folder safely.
   - Pick *N* = min(CPU cores ÷ 4, 8) for CPU bakes. With `--gpu`, run 2-3 processes per GPU, since OptiX bakes are
     short and the time goes into Blender overhead.
3. **Merge pass.** One process with `--no-bake`. Every texture and GLB already exists, so it only writes
   `scene.json`, lights, cameras, world, grade and `fx`. This also removes the partial-`scene.json` merge
   (`ONLY`/`LIMIT` branch) from the hot path.
4. **Cache across builds.** Key `tex/` and `mesh/` by a hash of (evaluated mesh data + material node trees + bake
   settings). The same prop library recurs across scenes, and a retry of `/scene2unreal` re-bakes nothing.
5. **FX bakes** (flipbook renders, VDB sampling) are extra shards, scheduled first because they are the longest
   single jobs.

The UE side can overlap with the export. Start texture import of finished shards while the others are still baking:
the `textures` stage is rerunnable and skips assets that exist. Mesh import order does not matter.

## 6. Deterministic vs agent-judged

**Deterministic.** Same input gives the same output, so these steps are cacheable and testable.
- Everything in `export_blend.py`, and the fx classification scores.
- `fx_plan.py` technique and parameter mapping (NIAGARA.md §3-5).
- `build_level.py`.
- Seeds: `RandomSeedOffset = crc32(fx id)`.
- Warm-up counts.
- MRQ settings.
- Packaging.
- Perf numbers (measured, so noisy within ±5%).

**Agent-judged.** Logged as explicit parameter diffs, bounded by `look_match_rounds`.
- Low-confidence fx classification (< 0.6), including `unknown` entries.
- Switching technique when a parameter-only match fails after three rounds (NIAGARA.md §6.5).
- Exposure and fog calibration offsets.
- FX user-parameter tuning.
- Light scale tweaks.
- The final "does it read like the Cycles frame" verdict, which goes into the response next to the side-by-sides.

**Rule.** The agent never edits `build_level.py`, `export_blend.py` or templates during a job. It writes overrides to
`exp/overrides.json`, which `build_level.py` applies on top of `scene.json`. A rerun with the same overrides
reproduces the agent's result exactly.
