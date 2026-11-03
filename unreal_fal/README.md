# unreal_fal: the Blender -> Unreal export stage on fal Serverless

`app.py` is the fal app **`apek/blend2unreal`** (private). It runs `export_blend.py` headless on RTX 5090 workers. The
slow texture bake is sharded across workers, and finished assets are cached by content hash on `/data`.

```bash
cd unreal_fal
fal deploy app.py::Blend2Unreal --app-name blend2unreal --auth private --reset-scale
python client.py upload hk_scene.zip                 # .blend or .zip (a .blend + grade.sh); pack images/fonts first
python client.py export <scene_url> --options '{"frame": 60, "dof": {"cam_street": [9.5, 2.8]}}' --out result.json
```

## API

`POST /export`
```json
{"scene_url": "https://.../hk_scene.zip",
 "options": {"frame": 60, "density": 1024, "max_res": 4096, "dof": {"cam_street": [9.5, 2.8]},
             "grade_sh": "grade.sh", "blend": null, "device": "gpu", "shards": 0, "procs": 0},
 "use_cache": true, "fresh": false, "inline_scene_json": true}
```
Response:
```json
{"job_id": "x_...", "zip_url": "...zip", "scene_json_url": "...scene.json", "scene_json": {...},
 "report": {"counts": {...}, "cache": {...}, "not_baked": [], "not_converted": [...], "warnings": [...],
            "timings": {...}, "worker_seconds": {...}, "shards": [...]},
 "minutes": 5.4}
```
- `device`, `shards` and `procs` don't change the result, so they are left out of the retry fingerprint.
- The app scales to zero (`min_concurrency = 0`), so a cold `/export` first waits ~1-2 min for a worker to boot. Set it to 1 to keep a warm worker ($2.50/h).
- Repeating an identical request returns the finished result, or attaches to a live attempt (heartbeat), or resumes
  a dead one and re-attaches to its shard requests. `fresh: true` exports again.
- `use_cache: false` re-bakes everything into a job-private cache, deleted afterwards. The shared cache is never
  read or changed.

`POST /shard` is internal: `/export` calls it on other workers. Benches call it with `use_cache: false`.

## Pipeline

1. **Plan** (`--plan-out`, ~25 s for HK): names every unique mesh, hashes it and estimates its bake cost.
   - The hash covers: evaluated mesh, material node trees (recursively, with packed image bytes), world-space
     scale, bake settings, the Blender version and the exporter file itself.
   - Materials that read their object (Object Info, object coordinates, object attributes) also hash that object.
2. **Shards**:
   - Cache misses are dealt longest-first into N shards: ~2 min of estimated work per Blender process, at most 32.
   - Shard 0 runs on the `/export` worker; the others are `/shard` requests, submitted and polled (not
     `subscribe()`).
   - Each worker runs 2 Blender processes x 3 threads with OptiX. Each process is resumed up to 6 times after a
     Blender bake crash.
   - Every finished asset is written to `/data/blend2unreal/cache/<h[:2]>/<h>/` (written to a temp dir, then
     renamed into place).
   - Assets still missing after round 1 are re-dealt in a second round.
3. **Merge** (`--plan --cache --link-cache --no-bake`): pulls every asset from the cache by symlink, then writes
   volumes, lights, cameras, world, grade LUT and `scene.json`.
4. **Package**: copies off `/data` with 16 parallel readers, zips (PNG/EXR stored, the rest deflated) and uploads
   to fal storage.

## Machine notes (measured)

- An RTX 5090 worker is **6 cores / 60 GB** (`os.cpu_count()` says 512: the host's). Probed:
  - L: 4 cores / 15 GB
  - XL: 8 / 30 GB
  - RTX PRO 6000: 6
  - H100: 12 / 112 GB
- Per-asset time is mostly CPU: unwrap, Cycles sync, PNG encode.
- 36-asset HK bench on one worker:

  | Setup | Wall time |
  |---|---|
  | GPU, 2 procs x 3 threads | 122 s |
  | GPU, 1 proc x 6 threads | 196 s |
  | CPU, 2 procs | 785 s (road alone 354 s) |

  **GPU (OptiX) is ~6x faster**: it is the default.
- OptiX compiles its "shader raytrace" kernels (AO and Bevel nodes) on the first such bake: ~230 s per process on a
  fresh worker. The warm-up in `setup()` now bakes an AO+Bevel material, and the kernel cache is shared on `/data`
  with the render farm (`/data/anyscene-farm/optix/<gpu>`).

## Changes to merge back into `unreal/`

`export_blend.py` (copied from `unreal/` at 21:15 on Nov 1, after its last edit at 20:25):
1. New flags: `--plan-out FILE`, `--plan FILE`, `--keys FILE`, `--cache DIR`, `--link-cache` (see the docstring).
   Without them the exporter behaves as before, apart from items 2-4.
2. **Asset names are computed over the whole sorted key list before any filtering by `--keys`.**
   - Without `--only`/`--limit` the names are the same as before.
   - With them, the collision suffix `_NNN` now uses the index in the full list. Before, it was the index in the
     filtered list.
3. `scene.json` assets gain `"hash"` when `--cache` is used. Shard mode writes `out/shard_<keys file>`, not
   `scene.json`.
4. With `--gpu`, the bake scene selects OptiX devices itself (a factory-startup Blender would otherwise bake on the
   CPU). Locally, `gpu_prefs.py` via `EXPORT_PRE` keeps working.

`build_level.py`, `render_shots.py`, `side_by_side.py`, `agx_view.py`, `make_copy.py`: unchanged copies.

New: `app.py`, `client.py`, this README.

## Known limits / follow-ups

- The cache on `/data` has no eviction (HK is ~4.6 GB). Job-private caches are deleted after the job.
- `smart_project` UV layouts of converted text (fascia_text_*, neon_*) differ between Linux and Windows Blender.
  Each export's textures match its own GLB UVs, but the PNGs are not byte-comparable across platforms.
- `scene.json` paths use `/` (relpaths on Linux). The local Windows export used `\`. `build_level.py` joins them
  with `os.path.join`, which works on both.
