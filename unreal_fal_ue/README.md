# unreal_fal_ue: UE 5.8 headless on fal Serverless (`apek/unreal-build`)

Status (2026-11-02): **working end to end.** HK builds on fal and renders with MRQ. Against the local Windows MRQ
frames the result is near-identical: PSNR 47–50 dB and a mean difference of 0.25–0.36 out of 255.

## Endpoints (private app `apek/unreal-build`, GPU-RTX5090)
| route | in | out |
|---|---|---|
| `/smoke` | `{"render": true}` | engine version, GPU, Vulkan, and a lit-cube PNG rendered offscreen |
| `/build` | `{"export_url", "scene": "HK", "level", "stages", "nanite_tris", "exposure_offset"}` | `content_url` (zip of `Content/AnyScene/<scene>`, Config, uproject), `log_url`, `report` |
| `/render` | `{"content_url", "scene", "cameras": [...], "config": "MRQ_Still", "resolution": [1920,804], "frames": 1, "temporal_samples": 8, "warmup_frames": 64}` | per camera: PNG/EXR URLs, an MP4 when frames > 1, logs |

```
# PowerShell 5.1 strips quotes from arguments, so pass the args as @file.json. FAL_KEY comes from FAL_SERVERLESS_KEY.
python -I tools/call.py apek/unreal-build build  @build_args.json  build.json
python -I tools/call.py apek/unreal-build render @render_args.json render.json
python -I tools/fetch.py apek/unreal-build <request_id> out.json --wait   # re-attach to a request after a local crash
```

## Measured on HK (2026-11-02)
- `/build`: 1514 s end to end, broken down as:
  - fetch and unzip of the 4.7 GB export: 163 s
  - UE commandlet: 1054 s (textures 263 s, meshes 629 s, materials 135 s)
  - zip: 230 s
  - upload: 47 s

  The content zip is 4.15 GB.
- `/render`, three cameras at 1920x804, 8 temporal samples and 64 warm-up frames: 1352 s, broken down as:
  - content fetch: 96 s
  - MRQ config: 17 s
  - `cam_street`: 1103 s, the first render, which compiles shaders into a cold DDC
  - `cam_table`: 64 s
  - `cam_wok`: 61 s
- Cold start, measured from zero runners to a new runner answering `/smoke {"render": false}`: 10.8 s. That node
  already had the image cached. A pull onto a node without the image couldn't be forced, so it is not measured;
  expect minutes for 24 GB.
- The shared DDC on `/data` persists across runners, so later renders on any runner skip most shader compiles.
- Cost: an RTX 5090 is $0.000694/s, about $2.50/h. A warm runner (`min_concurrency=1`) costs about $60 a day.
  The app is now scaled to `min_concurrency=0` and `keep_alive=300`. To warm it again:
  `fal apps scale unreal-build --min-concurrency 1 --keep-alive 3600`.

## Container
- The base image is `ghcr.io/epicgames/unreal-engine:dev-slim-5.8.4`: 24 GB compressed, with the engine at
  `/home/ue4/UnrealEngine` and user `ue4`.
  - Pulling it needs a GitHub account linked to Epic and in the EpicGames org, plus a classic PAT with `read:packages`.
    The PAT goes in the user env vars `GHCR_USER`/`GHCR_TOKEN` and is passed as `ContainerImage(registries=...)`;
    the Depot builder is the only thing that uses it.
- On top of the base image:
  - Python 3.13 via uv (it must match the deploying Python);
  - ffmpeg, the Vulkan loader and tools, and the NVIDIA ICD JSON;
  - `NVIDIA_DRIVER_CAPABILITIES=all`.
- The first image build took 644 s. Redeploys with an unchanged image take about 20 s.

```
$env:UE_SOURCE = "ghcr:dev-slim-5.8.4"; $env:GHCR_USER = "apekshik"   # GHCR_TOKEN from the user env var
uv run --python 3.13 --with fal==1.84.0 --with pydantic --with fal-client fal deploy app.py::UnrealBuild --app-name unreal-build --auth private --reset-scale
```
`UE_SOURCE=url:<linux engine zip>` builds from an Epic Linux binary zip instead. `none` builds a probe image with no engine.

## Linux specifics, now verified
- UnrealEditor refuses to run as root, so every engine process runs as `ue4` via `setpriv`.
- Rendering uses `-vulkan -RenderOffscreen` with `SDL_VIDEODRIVER=offscreen`; MRQ runs in `-game` mode with `-LevelSequence`.
- Engine processes run in their own process group:
  - Shutdown is detected from log markers, and the group is killed EXIT_GRACE seconds later; `pkill -u ue4` follows.
    ShaderCompileWorker children otherwise keep stdout open after the engine has exited.
  - Commandlets never log `LogExit`: their last line is `Execution of commandlet took`.
- `skip_retry_conditions=["timeout"]`. Without it, fal re-ran a timed-out build on a new runner every 2 h for 14 h.
- Exports written on Windows hold backslash paths in scene.json. `build_level.py` converts them on Linux; see `_posix_paths`.

## Files (all new; nothing in `unreal/` changed)
- `app.py`: the fal app.
- `mrq_config.py`: makes a per-request MRQ config. It sets the output dir, resolution, frame range, samples and
  warm-up, and `use_camera_cut_for_warm_up=False`.
- `smoke_shot.py`: an offscreen SceneCapture render of a lit cube.
- `template/`: `AnySceneUE.uproject` and Config. `make_project()` swaps the startup map and adds Linux `SF_VULKAN_SM6`.
- `tools/upload_export.py`, `tools/call.py`, `tools/fetch.py`: upload, submit-and-poll, and re-attach.
- `build_level.py`: `unreal/build_level.py` as of 2026-11-01 20:25, plus `_posix_paths` (merge that upstream).
  `app.py` ships whichever `build_level.py` is in this folder.
- `render_mrq.ps1`, `render_shots.py`, `TOGGLE.md`: unchanged copies.

## fal facts learned
- `keep_alive` is capped at 3600 s without a support request.
- Scaling settings persist across deploys; pass `--reset-scale` to apply the values in code.
- A timeout makes the queue retry on a fresh runner unless `skip_retry_conditions` includes `"timeout"`.
- `fal runners list --state terminated --since 6h` and `fal runners logs <id>` recover a dead runner's full log.
