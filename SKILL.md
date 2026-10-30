---
name: anyscene
description: Build a photoreal, film-style Blender scene from a one-paragraph brief. Generate concept images and every prop with image→3D models on fal, then script the layout, set dressing, grime, lighting, camera moves and grade. Use it when someone asks for a realistic 3D environment, a set or a cinematic shot of a place, whether starting fresh or extending an existing AnyScene scene.
---

# AnyScene

AnyScene turns a brief like "a 1 AM electronics repair shop in Tokyo, rain outside" into a dressed, lit Blender scene with
cinematic shots and a behind-the-scenes video. Agents built the two example scenes (`scenes/tokyo-electronics-repair`, `scenes/tokyo-ramen-shop`) with this process.
Each has 75–90 generated props, 8–9 shots, and about $150 of generation per round.

You are the art department, set dresser, gaffer and DP. Everything is a script you can re-run; the .blend is a build output.
Never hand-edit a .blend you can't regenerate.

## Requirements

| Tool | Notes |
|---|---|
| Blender 5.0+ | `$BLENDER`. Background mode (`-b`) for everything; the GUI is only for a human to look. |
| ffmpeg | `$FFMPEG`. Needs an h264 encoder (`libx264` or `h264_nvenc`), `curves`, `hue`, `vignette`, `noise`, `xfade`. |
| Node 20+ | for `generate/fal.mjs` |
| fal key | `FAL_KEY` env var. Never print or log it. |
| GPU | 12–16 GB is enough for one Cycles render at a time. Two at once runs out of memory: see GPU rules. |

## Layout of a scene

```
scenes/<scene>/
  brief.md            the brief + decisions (mood, time, lens style), kept up to date (new; the reference scenes keep this in NOTES.md)
  assets.json         room dims + every prop: id, prompt, height h, optional dims [x,y,z]
  picks.json          per prop: chosen model + one-line why; retired / debranded flags
  shots.json          camrig shots (see camera/README.md)
  NOTES.md            gotchas you hit, in one line each — read it before touching the scene
  props/<id>.blend    prepped props (output of prep)
  out/                renders, sheets, graded shots
  scripts/            the scene's build scripts: shell, dress, validate, grime, lights, post
refs/<scene>/         concept images, prop references, textures/decals
assets/gen/<model>/<id>/model.glb   raw generator output (never edited)
```

Reusable pieces (don't fork them per scene unless you need to change them):
- `generate/fal.mjs`: image and 3D generation, with an append-only spend log.
- `pipeline/gpu_run.sh`: a FIFO GPU queue.
- `pipeline/render_compare.py`: same-light comparison renders.
- `camera/`: camera rig and shot renderer.
- `breakdown/assemble.py`: the behind-the-scenes video.
- `pipeline/build_scenes_page.mjs`: the gallery page.

## The pipeline

Work in this order. Each step ends with a **gate**: a contact sheet or check you look at before moving on. Look at the
images yourself. A script that ran without errors proves nothing about how the scene looks.

### 1. Brief → scene spec

Write `brief.md`:
- the place, the time of day and the weather;
- 3–5 mood words;
- the room size in metres;
- where the street/door is (put it at y=0 and make the room deep along +Y);
- zones (counter, bench, kitchen, racks);
- 2–3 hero spots the camera will live on;
- the light sources that would really exist there (practicals).

Real places are small: the repair shop is about 3.5 × 6 m. Keep it tight. Density sells realism more than size does.

### 2. Concept images

Run `node generate/fal.mjs image --variant sunburst --out refs/<scene>/concept_wide --prompt "..."`, and again for a
detail shot. GPT Image 2.5 Sunburst beat Flare on legible signage text and natural grade. These set palette, clutter level
and the prop list; you don't match them shot for shot.

**Gate:** the user (or you, if running solo) agrees on the look.

### 3. Prop manifest

List every object in `assets.json`. Sort them into four tiers:
- **furniture** (scripted);
- **hero props** (generated);
- **mid props** (generated);
- **clutter and decals** (generated or direct-modelled).

Decide per object whether to generate it or direct-model it:
- **Direct-model** anything architectural or simple-and-exact: walls, counters, shelving, boxes, cables, paper, glass panes, signage text (real font text objects).
- **Generate** anything with character: appliances, tools, electronics, crockery, food, bins.

Give every generated prop:
- `h`: its real height in metres;
- `dims`: for boxy things, because generators invent depth (fridges, ticket machines, ranges);
- a prompt describing one object, its condition and its materials. **No brand names.**

### 4. References → 3D, both models

For each prop:
1. Generate a reference with the scan template appended. This is the exact text the reference scenes used:
   > No real-world brand names or logos. Product reference photograph for 3D scanning. The entire object fully visible and centered, three-quarter front view from slightly above, plain seamless light-grey background, soft even diffuse studio lighting, no harsh shadows, no other objects, no hands, realistic used and worn condition, sharp focus, true-to-life materials.
2. Send the same reference to **both** Tripo H3.1 (`--model tripo-h31`) and Meshy 7.1 (`--model meshy`).

Notes:
- Run about 12 jobs concurrently. About 10–20% fail transiently (504, ECONNRESET, Meshy timeouts after about 10 min); re-run the same ids. The script skips GLBs that already exist.
- **Never run two generation passes at once.** Existence is checked at start, so in-flight jobs get double-submitted.
- References often come back with real brands even when told not to. Check every reference and regenerate those that carry one as `<id>_nb`, with a fictional brand.

**Gate:** a reference sheet with no real brands.

### 5. Compare and pick

Render reference | Tripo | Meshy, front, back and clay, under the same light (`render_compare.py`), then sheet them. Pick per prop and
record the choice and a one-line why in `picks.json`.

What the reference scenes found across ~150 props:
- **Meshy 7.1** wins about 70% of the time: small consumer items, sharper printed labels.
- **Tripo H3.1** wins big hard-surface heroes, where real geometry matters (knobs, bezels, dents). It's about 2M tris, so it needs decimating.
- **Both** produce opaque glass, so fix glass by script.
- Meshy speckles flat panels. Look at the clay render, not just the beauty render: it shows which details are real geometry.

**Gate:** the picks sheet. Every prop has a winner or is retired.

### 6. Prep

Turn every pick into `props/<id>.blend`:
- **Front faces −Y.** Tripo's front faces +X, so rotate it −90°; Meshy's already faces −Y. Rotate the mesh data, not the object.
- **Real scale** from `h`/`dims`.
- **Bottom-centre origin.**
- **Decimate** heroes to about 150k tris.
- **Textures** at 2K or less.

Gotchas:
- glTF imports use QUATERNION rotation mode, so `rotation_euler` is silently ignored. Set `rotation_mode = "XYZ"` first.
- glTF images arrive packed. Calling `pack()` again on an unmodified image drops its data and the prop renders magenta. Repack only the images you resized.
- Pass absolute paths to Blender, or relative paths resolve against the wrong directory.

### 7. Shell and layout

Script the room: floor, walls, ceiling, storefront and glass, counters, shelving and fixed furniture. Name objects clearly; shots and
lights reference them by name. Gotchas:
- A smooth-shaded box without a bevel acts as a lens when it's glass.
- `matrix_world` on objects created in the same script is stale until `view_layer.update()`.

**Gate:** a clay sheet from the hero camera positions.

### 8. Dressing, big → small

Place furniture props, then heroes, then mid props, then clutter. Each pass drops props onto surfaces with raycasts.

- **Start drop rays below anything overhead** (shelf above, hood, conduit), or the prop lands on top of it.
- **Vary instances** with `ob.color` multiplied into albedo (Object Info › Color), so repeated meshes don't read as copies.
- **Run the validator after every pass.** Check each prop for:
  - a BVH mesh overlap against fixed furniture (lift the prop 3 mm before testing);
  - prop–prop clashes;
  - floating more than 1 cm. Start the float ray *above* the support's top face, or a thin bench top reports its own thickness.

  Clashing small props get spiral-searched to a clear spot. Validator reports are noisy, so read them: a plinth or pots on a burner can be legitimate.

**Gate:** the validator shows 0 unexplained issues, plus a dressed clay sheet and a textured flat-lit sheet.

### 9. Script fixes, grime and de-branding

- **Screens:** CRT screens become emissive with a scanline glow, and scopes get a graticule and trace. Fix lamp lenses, display glass and bottles to real glass.
- **Grime:** a shared node group with AO-driven dirt, edge wear and per-instance tint. Add decals (stains, flyers, stickers) generated on flat backgrounds, alpha-keyed and stuck on with raycasts.
- **De-branding without regenerating:** render ortho views and mark the brand rectangles. Raycast the rectangles to texels, fill each with the label's ground colour plus grain, and flatten the same texels in the normal map, or embossed text survives.

### 10. Lighting (night)

1. Start with practicals: the light fixtures a real place would have (lamps, pendants, tubes, signage, screens, the fridge, the street spill).
2. Add fills last and keep them weak. A 45 W bounce at exposure 1.0 made the room look like the overhead lights were on. Let the practicals make the contrast.

Gotchas:
- **Lamp shades:** generated shades are closed meshes, so put spots just under the rim, not inside.
- **Light direction:** area lights shine along local −Z.
- **Glass:** hide fills from camera, glossy *and* transmission rays, or they show through glass as bright discs.
- **Emissive meshes:** on dense generated meshes, texture-driven emission turns every triangle into a light. Set `material.cycles.emission_sampling = "NONE"` on those.
- **Exposure:** re-check it after every new practical.

**Gate:** Cycles stills of each hero spot at 32–64 spp.

### 11. Atmosphere and FX

- **Volumetric haze:** cheap and worth it.
- **Steam (Mantaflow):** set `surface_distance` around 1.0 (it is measured in cells), and keep emitters well inside the domain.
- **Bake cache:** use negative cache frames so plumes are developed at frame 1. Clear the cache folder with `rmtree`: `fluid.free_all()` is async in background mode and deletes the new bake.
- **Motion blur:** turn object motion blur **off** on volume domains, or each frame costs about 290 s.
- **Rain:** particles with `rotation_mode = "VEL"` and drop geometry along +X.

### 12. Shots

Write `shots.json` for `camera/shoot.py`. Its README is the contract: moves, rack focus, lens FX and the handheld profiles.

1. **Block:** start with `--framing` (3 stamped stills per shot), then `--preview` (Eevee, stamped).
2. **Design:** mix 2–3 cinematic moves (push-ins, a dolly zoom, a 100–135 mm rack) with 1–2 long **handheld walkthroughs**: `"handheld": {"profile": "walk"}`, a 4–6 key `path` at walking pace. People respond most to the walkthroughs. Keep them as long, uncut takes.
3. **Path check:** check the camera against the scene before rendering, keeping more than 0.45 m from every mesh on every frame.
4. **Focus:**
   - A focus target must never be one the camera passes through, or the distance collapses to 0 and the frame goes soft. Rack to something past it first.
   - Focus `obj` uses the bounding-box centre. For deep objects, put a `pos` on the face you want sharp.

**Gate:** previews reviewed. Each shot's framing, move and focus are approved before any final render.

### 13. Final renders

- **GPU prefs:** `blender -b file.blend` renders Cycles on the **CPU** unless a pre-script sets the GPU compute device (`--python scenes/<scene>/scripts/gpu_prefs.py`, before any other `--python`). Device prefs are user prefs and aren't saved in the .blend. This cost the reference scenes hours.
- **Chunks:** render in 24-frame chunks through `pipeline/gpu_run.sh`. Existing frames are skipped, so runs resume.
- **Settings:** 2.39:1 at 1280–1920 px wide, 48–64 spp with the denoiser. That runs about 4–12 s per frame on a 5070 Ti.
- **Encode:** with NVENC. Check every graded output's duration and frame count. A grade run over a frame folder with a gap silently produces a short clip.

### 14. Post

Grade in ffmpeg, not the Blender compositor. The 5.0 colour-balance and mask nodes misbehave. Keep only Glare and Lens
Distortion in Blender. Grade with `curves` (lift blacks to about 0.03, teal shadows, warm highlights), `hue=s=0.88`, a slight
`rgbashift`, `vignette` and temporal `noise`.

Deliver:
- graded shots;
- a reel (concat with stream copy);
- a compressed copy under 30 MB for chat.

### 15. Behind the scenes (optional)

`breakdown/SPEC.md` + `breakdown/assemble.py` make a one-minute video: concept, layout, props, dressing, materials, lighting, post and final shot.
The scene supplies four "dollhouse" clips, one 120° orbit with the ceiling and near walls hidden:
- clay layout;
- props popping in;
- clay to textures to grime;
- lights coming on in order.

## Running several scenes or agents at once

- **Ownership:** each agent owns its scene's folders and asset ids. Shared tools are read-only; copy one into your scene to change it.
- **One Blender on the GPU at a time:** previews included, everything through `pipeline/gpu_run.sh`. Keep each locked call under about 10 minutes.
- **Waiting on a condition:** wait on the actual condition, not a guess. A "GPU busy" check must not match its own command line, and killing a waiting shell does not kill its child processes. Both of these caused duplicate renders that overwrote finished work. After a pause or crash, list every `blender` process before starting anything.
- **Cross-scene ordering:** marker files only, e.g. `.gpu.<scene>_done`, and create one only when the work is actually done.
- **Other GPU apps:** another GPU-heavy app (Houdini, Unreal) running alongside can slow Cycles 8×. Tell the user rather than closing their apps.

## Budget and time (fal, Oct 2026)

| Item | Cost |
|---|---|
| Reference image | ~$0.25 |
| Tripo H3.1 | ~$0.60 |
| Meshy 7.1 | ~$0.80 |
| Per prop, both models | **~$1.65** |
| ~90-prop scene | ~$150 |

Every call is logged to `generate/spend.jsonl`; `node generate/fal.mjs spend` totals it.

Time on one 16 GB GPU: a scene is roughly a day of agent work, and the final shots are about 1–2 GPU-hours.

## Generalising to a new scene

1. Start from the closer example scene: copy its `assets.json`, `shots.json` and `scripts/` into `scenes/<your-scene>/`
   (name the folder after the place, e.g. `lisbon-tram-depot`), then rewrite `brief.md` and `assets.json` for it.
2. Reuse the shared tools as they are. Reuse an example scene's `scripts/` as a starting point, but the
   shell and the dressing passes are always scene-specific. That's where your judgement goes.
3. Keep `NOTES.md` as you go. Anything that cost you more than 10 minutes gets one line. The next agent reads it first.

## Definition of done

- [ ] Every placed prop is in `picks.json` with a reason, and no real brands are visible in any shot.
- [ ] The validator is clean, or every remaining report is explained.
- [ ] Each hero spot has a final still, and every shot is rendered, graded and has the right duration.
- [ ] There's a reel and a compressed copy; an optional BTS video.
- [ ] `NOTES.md` is updated, and the spend is totalled.
