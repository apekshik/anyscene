# Mission control 1970s — notes

Brief and decisions: `brief.md`. Fictional agency *Aurora Flight Directorate*, mission PERSEUS 7; all screen text and
labels are invented (screens.py, placards in dress.py).

## Pipeline (run from the repo root, every Blender call through `pipeline/gpu_run.sh`)

1. `node scenes/mission-control-1970s/scripts/refs.mjs` — Sunburst refs for `assets.json` (props + textures + detail concept).
   Brand check: `scripts/refsheet.sh`. Rejected refs are kept in `refs/mission-control-1970s/props_rejected/`.
2. `node scenes/mission-control-1970s/scripts/gen3d.mjs [ids]` — Tripo H3.1 + Meshy 7.1 per prop, 12 at a time.
3. `scripts/compare_batch.sh` (same-light renders, 10-prop GPU chunks) + `scripts/sheet.sh` → `picks.json`.
4. `scripts/prep.py` → `props/<id>.blend` (+ `props/<id>.json` sidecar), then `scripts/fixes.py` (CRT face patches).
5. `scripts/screens.py` → `refs/mission-control-1970s/tex/screens/*.png` (CRT pages + wall display, Eevee + numpy bloom).
6. `scripts/build.py` → `mc.blend`: shell → dress (+ validate with spiral resolve) → screens → grime → lights → haze → post.
7. Shots: `shots.json`; `scripts/shoot.sh` (GPU prefs + camrig), `scripts/check_path.py`, `scripts/render_finals.sh`
   (24-frame chunks, grade, frame-count check).
8. Breakdown: `scripts/bts.py` + `scripts/bts_render.sh` → `breakdown/mission-control-1970s/clips/`.

## Gotchas

- `bpy.utils.system_resource("DATAFILES", path="studiolights/world/studio.exr")` returns `""` in 5.0.1; the shared
  `pipeline/render_compare.py` (and the repair copy) fail every render with "Cannot read ''". Join the path yourself.
- `render_compare.py` renders every prop of every scene in `assets/gen` (no id filter) and points the Tripo camera at the
  side (yaw.json lookup). The scene copy `scripts/compare.py` takes ids and fixes Tripo's +X front with yaw 90.
- Prep skip-by-mtime against `picks.json` re-prepped every prop on every pick edit, which silently dropped the CRT
  patches from fixes.py. Now a sidecar `props/<id>.json` records model/yaw/lay; any re-prep must be followed by fixes.py.
- The generated consoles' own writing shelf is ~20 cm deep at 0.57 m; clutter had nowhere to go. A scripted laminate desk
  run (0.46 m) sits in front of each row, ending 6 mm short of the console fronts so the validator stays clean.
- Drop rays must start below the console's upper housing; a ray starting at desk+0.95 m began *inside* the housing and hit
  its inner faces. Props with overhangs (desk lamps, chairs) are dropped by their lowest vertices, not their bbox.
- Validator: furniture collections must exclude placed props (each placed prop otherwise "intersects" itself) and the
  placards (they sit on console tops on purpose). Wall props need ~3.5 cm off the right/back walls (acoustic panels).
- Screen detection (fixes.py): green-or-dark texels facing -Y in the upper 45 % of the front; the b/w ceiling TV needed a
  grey-glass mask instead. Round radar tubes bulge ~2 cm past the bezel plane: a 6 mm dome left a hole in the middle.
- Glass ashtray: both generators bake opaque grey glass. Transmission comes from an HSV mask on the albedo (low saturation,
  light) so the butts stay opaque. Don't use that mask on cream enamel (the water cooler would turn to glass).
- Lamp glow on console buttons is texture emission with `emission_sampling = NONE`; CRT patches keep sampling (192 faces
  each) so they light the desks.
- Blender ray_cast hits volume boxes (haze) and decals: run all drops before haze/grime.
- Eevee framing renders show the windows black; check window views in Cycles.
- camrig handheld walk: keep 0.45 m from every mesh; the window aisle is 1.95 m wide, so the path hugs x ≈ 1.0–1.4.
- Render cost (1920×804, 48 spp, OptiX denoise): a `--still` is ~15 s but frames in final (animation) mode were
  ~24–34 s. Bisected with 4-frame chunks: no haze ~4 s/frame; room haze alone ~7; smoke curls alone ~7; both ~21 —
  the curls sit inside the room volume and overlapping volumes are what cost. Motion blur, lens FX, the frame-driven
  noise drift and heterogeneous vs homogeneous room haze made little difference; persistent data made it *slower*
  (29 vs 24 s). Fix: homogeneous room layers, and every shot except the push-in renders with the curls hidden
  (`NOCURL` → `scripts/nocurl.py` in shoot.sh). Time chunks, not stills, before estimating a render budget.
- Stopping a background task (the harness's TaskStop) killed only the outer shell: `render_finals.sh` and
  `bts_render.sh` kept running, kept queueing chunks, and rendered frames from two different builds. Kill the loop
  scripts by pid (`ps -ef | grep render_finals`), then their waiting `gpu_run.sh` children, before restarting.
- A GUI Blender (not this scene's) was open on the box holding ~2 GB and some GPU time; GPU memory sat at 14.5/16 GB
  during finals. Left alone (not ours).
- Grounding (v2): the validator's bbox FLOAT check (1 cm) missed contact-point gaps. `drop()` takes the *highest* hit
  under a prop's base, so anything whose feet overhang the desk's 2 mm metal edge lip hung ~2.5 mm over the laminate,
  and the CRT terminal, dropped after the hard hat at the same spot, landed on the hat (2 cm up once resolve moved it).
  validate.py now has GROUND (rays from the lowest vertices, as `pipeline/grounding.py`, 2 mm tolerance) and
  `settle()` after resolve; placards settle with their consoles. `pipeline/grounding.py --all` leaves only wall-hung
  and bracket-hung shell parts. Low-angle check stills: `scripts/lowcams.py` → out/sheets/ground_lowangle.png.
- Backdrop through the windows: a 96 m card at 45 m read as a wall-sized photo. 24 m reads as ~3 km away, but its
  edges show; the final card is 72 m with the image mapped to the middle third and EXTEND, so sky and marsh run on.

## Results

- 76 generated props (Tripo 30 / Meshy 46 picks, every pick with a reason in picks.json), 146 placed instances,
  validator 0 issues. fal spend for this scene ≈ $133 (84 images, 76 Tripo, 83 Meshy calls incl. failed retries).
- Shots (1920×804, 48 spp, OptiX denoise, ffmpeg grade): orbital_push 5 s, fd_wide 6 s, display_rack 5 s,
  printer_crane 5 s, walk_windows 20 s, walk_rows 17 s (both handheld walk profile). out/graded/*.mp4, reel
  out/mc_reel.mp4 (58 s), chat copy out/mc_reel_chat.mp4 (25 MB). Hero stills: out/stills/.
- **Farm frames:** 1,212 of the 1,392 final frames (fd_wide 61–144, display_rack, printer_crane, both walks) were
  rendered elsewhere (PNG metadata: /data/anyscene-farm/bundles/d45a7c39d1bb879a/scene.blend, 48 spp, ~3 s/frame)
  and copied into out/shots/*/frames at 16:50–16:53 — not by this session. Audited: complete sequences, the right
  CR_<shot>_cam cameras, 48 spp, no visible seam against the local frames (fd_wide 60→61). Kept as they are.
- v2 (grounded rebuild, mc.blend 22:05): all 1,392 frames re-rendered on the farm (v1 frames deleted in a disk
  clean-up), regraded 22:27; graded mp4s and reel replaced, same durations, reel 1,392 frames.
- Breakdown: breakdown/mission-control-1970s/clips/{a_layout 144, b_props 240, c_materials 144, d_lighting 240}.mp4
  + `*_contact.png`. d_lighting is the slow one (~5–22 min per 40-frame chunk, with another scene sharing the GPU).

## SKILL.md: steps that were wrong, missing or unclear (first real test)

1. **Step 5 / `pipeline/render_compare.py` is broken on Blender 5.0.1** (empty HDRI path, every render fails), has no
   prop-id filter (renders every scene's GLBs), and reads `yaw.json` from the output folder, which nothing writes — so
   Tripo's "front" render shows the prop's side. The skill tells you to use it as-is.
2. **Step 3 size keys are underspecified.** It says `h` + optional `dims`, but flat props (open binders, glasses,
   printouts) need "largest dimension", and the example scenes use `fit`/`size` (repair) or `h`/`dims`/`m` (ramen).
   Pick one schema and document it; this scene uses `h` | `dims` | `max`.
3. **Step 6 doesn't say re-prepping wipes script fixes (step 9).** Prep and the CRT/glass fixes edit the same
   `props/<id>.blend`; any re-prep (pick change) must be followed by the fixes. Order and idempotency need stating.
4. **Steps 8/9 assume generated furniture has usable surfaces.** Generated consoles' desk shelves were ~20 cm deep;
   the fix was a scripted desk. Worth a line: check the support surfaces of generated furniture before planning clutter.
5. **Step 9 "fix glass by script" has no recipe** for glass inside a textured prop (ashtray with butts). An HSV-masked
   transmission on the albedo works; say so.
6. **Step 11 says "Volumetric haze: cheap and worth it."** Not here: overlapping volumes tripled the frame cost.
   Add: one volume, no overlaps; time a 4-frame chunk in final mode, not a `--still`.
7. **Step 12/13 budget numbers** ("4–12 s per frame") came from stills; final-mode frames here were 2× a still.
   The budget step should say to measure with `--frames a-b`.
8. **"Gate: the user agrees on the look"** has no instruction for side sessions where the concept is pre-approved;
   I treated the given concept as the gate.
9. **Runaway background jobs.** "Killing a waiting shell does not kill its child processes" is in the GPU section,
   but the concrete failure (stopping a harness background task leaves the loop running) needs a how-to: kill
   the loop script's pid, then its `gpu_run.sh` children.
10. **Step 2** says to run the detail concept too, but the brief arrived with an approved wide concept; unclear
    whether the detail is still required (I generated one: `refs/mission-control-1970s/concept_detail_0.png`).
11. **No guidance on Meshy failures that repeat.** Three references failed three times with fal 500
    `downstream_service_error`; the skill says "re-run the same ids". Say when to stop and go single-model.
12. **Step 15 + `breakdown/SPEC.md`** say "repair, ramen" only; a third scene has to guess the camera rules apply as-is.
