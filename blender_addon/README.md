# fal Render Farm (Blender add-on)

Render the open scene on the AnyScene render farm (fal Serverless, RTX PRO 6000 GPUs) instead of your local GPU.
Direct a downloaded scene in your own Blender (cameras, lights, edits), then press **Render animation on fal**. Frames
come back into the scene's own output path with the same names a local render would give them.

```
blender_addon/
  fal_render_farm/            the add-on (an extension folder: blender_manifest.toml + bl_info, works either way)
    __init__.py               panel, operators, preferences, status bar, UI timer
    job.py                    planning (main thread) and the job runner (background thread)
    fal_api.py                fal queue API + fal storage upload over plain urllib
    pack_copy.py              runs in a separate Blender on a temp copy: make local, pack_all, refuse on externals
    farm_gpu.py               shipped in every bundle, run with --python on the farm: OptiX/CUDA + GPU on every scene
  fal_render_farm-1.0.0.zip   installable build
  tests/                      make_test_scene.py, test_farm.py (headless end-to-end test against the real farm)
```

## Install

Blender 4.2 or newer (built and tested on 5.0.1).

1. **Edit > Preferences > Get Extensions**, then the drop-down at the top right > **Install from Disk...**, and pick
   `blender_addon/fal_render_farm-1.0.0.zip`. Dragging the zip onto the Blender window also works.
2. Enable **fal Render Farm** if it isn't enabled already.

For development, symlink or copy `blender_addon/fal_render_farm/` into an extensions repo (or a legacy
`scripts/addons/` folder) instead.

## Set the key

Open the add-on's preferences (Preferences > Add-ons > fal Render Farm):

- **fal key**: the key of the account that owns the farm app (the Serverless key the farm is deployed under,
  `FAL_SERVERLESS_KEY` in this repo, not a generation-only `FAL_KEY`). It's a password field, stored in Blender's user preferences (`userpref.blend`), and the
  add-on never prints or logs it. Press **Check key** to make sure fal accepts it.
- **Farm app**: empty by default; set it to your own deployment of `farm/app.py`, e.g.
  `<your-fal-username>/blender-farm-2` (see "Farm change" below). The add-on refuses to render until it's set. A farm
  deployed from the older build as `blender-farm` returns **PNG frames only**; `blender-farm-2` is the same farm with
  one backward-compatible addition (an `outputs` field), so it also returns EXR, multilayer EXR, JPEG, TIFF and so on.
  The panel warns when the output format isn't PNG and the app is a `.../blender-farm`.
- **Frames per chunk** (24) and **Concurrent chunks** (20): one chunk is one farm request on one GPU.
- **Chunk timeout**, **Encode MP4 when done**, and the **ffmpeg** path (empty means use the one on PATH).

Remember to save preferences (or keep auto-save on).

## Render

**Properties > Render > fal Render Farm**:

- **Render animation on fal** renders the scene's frame range (and frame step).
- **Render this frame on fal** renders the current frame and saves it to the output path as frame N. If an Image
  Editor is open, the frame is shown there when it arrives.
- **Cancel** cancels in-flight chunks on fal. Frames that already arrived stay on disk.
- **Retry failed chunks** re-submits failed chunks against the bundle that's already uploaded.

What happens when you press render:

1. The open file, unsaved edits included, is written to a temp folder with `save_as_mainfile(copy=True)`. Your
   working file isn't modified or re-saved, and it doesn't get marked dirty.
2. A separate background Blender opens that copy, makes linked data local, runs `pack_all` and saves `scene.blend`.
   If something still points outside the file (unpackable images or movies, Alembic/USD caches, libraries), the
   render stops and the panel lists those paths.
3. `scene.blend` and `farm_gpu.py` are zipped, the `bundle_id` is set to the first 16 hex characters of the zip's
   sha256, and the zip is uploaded to fal storage. An unchanged bundle is uploaded only once per session.
4. Frames that already exist at their output path are **skipped** (that's how resume works). The remaining frames
   are cut into chunks. Each chunk goes to the queue API as
   `{bundle}/scene.blend -S <scene> --python {bundle}/farm_gpu.py -o {out}/frames/<filename pattern> -s A -e B -j STEP -a`,
   and at most *Concurrent chunks* are in flight at once.
5. Each finished chunk's zip is downloaded and its files are written to the paths that `scene.render.frame_path()`
   gives locally. That covers `#` padding, relative `//` paths and the file extension setting.

The scene renders with its own settings: engine, samples, resolution and percentage, file format and colour depth,
view layers, compositor, color management and camera. The only thing the farm changes is the device: `farm_gpu.py`
selects OptiX (or CUDA) and sets `cycles.device = 'GPU'`, the same way `builder/blender_gpu.py` does for the builder.

Progress appears in the panel (phase, chunks queued/rendering/done/failed, frames, elapsed time, GPU-seconds and their
cost) and in the status bar. Everything runs on a background thread, and a timer redraws the UI every 0.5 s, so
Blender stays responsive. Each failed chunk shows its error. A chunk is retried once automatically before it's marked
failed.

When an animation finishes with PNG/JPEG/TIFF/... frames and ffmpeg is available, the add-on writes an H.264 MP4
(`<name>_<first>-<last>.mp4`, CRF 16) next to the frames. EXR frames are skipped, because they're linear and belong
in your grade.

## What the estimate means

The estimate scales a measured reference to your scene. Mission control rendered at **5 to 7 s per frame at
1920x804 and 48 spp** on an RTX PRO 6000. That figure is multiplied by `(your pixels / 1920x804) x (your samples / 48)`,
using Cycles samples or EEVEE render samples. Each chunk also adds about 20 s of overhead (Blender start, scene load,
returning the frames). GPU time is priced at **$4.00 per GPU-hour**. Wall time assumes chunks run *Concurrent chunks*
at a time, plus about 90 s of cold start if the app has scaled to zero.

Treat the estimate as an order-of-magnitude figure, not a quote. Scene complexity, volumes, adaptive sampling,
denoising, light paths and EEVEE versus Cycles can each move the real number by 2x or more. Once a job is running,
the panel shows the real GPU-seconds the farm reports (render time plus bundle fetch per chunk). That figure leaves
out cold starts and idle keep-alive, which fal also bills.

## Troubleshooting

- **"Set your fal key"** or **HTTP 401/403**: the key is missing, or it belongs to an account that can't see the farm
  app. Use the farm owner's Serverless key and press **Check key**.
- **"the file references data that can't be packed"**: these are the listed images/movies/caches. Fix their paths or
  make them local. Fluid and other disk simulation caches aren't shipped (you get a warning, not an error), so bake
  them into the mesh or render those shots locally.
- **"output path is relative (//) but this file has never been saved"**: save the file once, or set an absolute
  output path.
- **"Output is a video format"**: the farm renders frame sequences in chunks. Pick PNG/EXR/... and turn on *Encode
  MP4*.
- **A chunk fails with "the farm returned no OPEN_EXR files"**: you're on a `blender-farm` deployment, which only returns
  PNG. Deploy and switch to `<your-fal-username>/blender-farm-2`.
- **Chunks sit in "queued"**: the farm is busy or scaling up (it allows at most 20 workers, shared with other jobs on
  the same app). They start once workers free up.
- **A chunk timed out**: lower *Frames per chunk*, or raise *Chunk timeout* (the farm's hard cap is 3600 s per request).
- **Frames look different from a local render**: the farm runs Blender **5.0.1** on Linux. Scenes that depend on
  add-ons (custom nodes, drivers that call add-on Python, Python-scripted drivers in general) only render correctly if
  the farm has them, and it has no add-ons. Disk caches and file-output nodes with absolute paths aren't shipped
  either.
- **Nothing comes back for a stereo/multiview scene**: per-view files (`_L`/`_R`) are written next to the frames,
  but resume doesn't know about them yet.
- The **System Console** (Window > Toggle System Console) shows one `fal render farm:` line per step and per chunk.

## Tests

```
"C:/Program Files/Blender Foundation/Blender 5.0/blender.exe" -b --factory-startup --python-exit-code 1 \
    --python blender_addon/tests/test_farm.py -- <workdir> --app <your-fal-username>/blender-farm-2 [--chunk 12] [--ffmpeg <path>]

BLENDER_USER_RESOURCES=<empty temp dir> "C:/Program Files/Blender Foundation/Blender 5.0/blender.exe" -b \
    --factory-startup --python-exit-code 1 --python blender_addon/tests/test_zip_install.py -- blender_addon/fal_render_farm-1.0.0.zip
```

Rebuild the zip with `blender --factory-startup --command extension build --source-dir blender_addon/fal_render_farm --output-dir blender_addon`.

The test builds a 48-frame 640x360 Cycles scene with an external texture and enables the add-on from its folder. It
reads `FAL_SERVERLESS_KEY` from the Windows user environment, for that process only, then draws the panel and polls
the operators. It renders the animation through the operator and checks every frame name. It also confirms the
working .blend is untouched, tests resume (it deletes 2 frames and re-renders), compares frame 1 against a local GPU
render (PSNR), and renders one EXR frame. It ends with a `TEST-SUMMARY` JSON line.

## Farm change (blender-farm-2)

`farm/app.py` gained one optional request field, `outputs` (glob patterns relative to `{out}`). It defaults to
`["**/*.png"]`, which is exactly the old behaviour, so existing clients (`farm/farm.py`, AnyShot's `farm_render`) are
unaffected. The add-on always sends `["frames/**/*"]`, and an older `blender-farm` deployment ignores the unknown field.
The changed app is deployed as `blender-farm-2` on your own account:

```
fal deploy farm/app.py::BlenderFarm --app-name blender-farm-2 --auth private
```

An existing `blender-farm` deployment doesn't need to be redeployed.
