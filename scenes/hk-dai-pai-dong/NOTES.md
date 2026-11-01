# Dai pai dong — notes

A semi-outdoor scene: a short Hong Kong street (pavement, kerb, road, tenements both sides, harbour card at the end)
with the stall under a corrugated awning. 80 manifest props → 78 placed generated picks (2 retired), 183 placements (v2).

Pipeline (run from the repo root; every Blender call goes through `scripts/blend.sh` or `scripts/shoot.sh`,
both of which use `pipeline/gpu_run.sh` + `gpu_prefs.py`):

1. `uv run --no-project python -I scenes/hk-dai-pai-dong/scripts/manifest.py` → `assets.json` (80 props incl. `_nb`, 14 textures).
2. `node scenes/hk-dai-pai-dong/scripts/gen.mjs --stage refs`, check the sheets, then `--stage 3d` (Tripo H3.1 + Meshy 7.1, pool 12).
3. `bash scenes/hk-dai-pai-dong/scripts/compare.sh` (12 props per GPU-queue call) + `review.sh <tag>` (sheets of unpicked props)
   → `node scenes/hk-dai-pai-dong/scripts/pick.mjs id model "why"` → `picks.json`.
4. `blend.sh` + `prep.py -- --only ...` → `props/<id>.blend`.
5. `bash scenes/hk-dai-pai-dong/scripts/blend.sh build -- --save [--preview street,wok,table,walk,flame,top] [--clay]`:
   shell → dress → resolve + validate (`out/validate.txt`) → grime → lights → fx → post → `hk.blend`.
6. `check_path.py` on shots, `shoot.sh --framing`, then `render_finals.sh` (24-frame chunks, grade, frame-count check),
   `stills.py` for hero stills, `render_bts.sh` for the four dollhouse clips.

## Gotchas
- No system Python on this box: helper scripts run with `uv run --no-project python -I` (Pillow via `--with pillow`).
  Open JSON with `encoding="utf-8"`: picks/assets carry Chinese text and Windows defaults to cp1252.
- `bpy.utils.system_resource("DATAFILES", path="studiolights/world/studio.exr")` returns `""` in 5.0.1, so the shared
  `render_compare.py` fails every render with "Cannot read ''". The local `scripts/compare.py` joins the path by hand.
- `read_factory_settings()` inside a build script resets user prefs too: re-select OptiX after it (build.py does),
  or the gpu_prefs pre-script is undone and Cycles renders on the CPU.
- `against="x-"` takes the wall coordinate, not the prop centre: passing the centre left the cart and range 0.4 m off the shelves.
- Wok wells: a lowest-point height map over the generated range found the front gutter, and a guess from the compare
  renders was 25 cm off. A top-down ortho Workbench render of the placed range (2 mm/px) gave the real wells: 45% of depth,
  25% / 75% of width (`dress.burner_wells`). Seat woks by the mean of their lowest vertices: the long-handled wok's bbox
  centre is ~20 cm off its bowl. Both slips were only visible in a close still, not the 32-spp previews: render a close-up.
- `pipeline/env.sh` sets `FFMPEG=ffmpeg` when unset, so exporting the CapCut path *after* sourcing it does nothing and
  every encode fails with "ffmpeg: command not found". Export it before, and in child scripts check `command -v`.
- Changing set dressing mid-render means wiping the shot's frames: a chunked take mixes old and new positions otherwise.
- Lying-flat props (wok tools, strainer, umbrella) need a max-dimension size (`m`), not `h`: by height the tools were 1.7 m long.
- Stools around tables must drop from below the table top (start_z 0.6), or they land on the table edge.
- Shelf props: pack along the shelf by real footprint *then* drop; dropping first let plates land on the rice cooker next door.
- A placement deleted with `bpy.data.objects.remove` must not be the cached library root: instances are always copies now.
- The stall's own tenement had ground-floor pilasters running through the back shelves: pilasters inside the stall start at 3.2 m.
- Generated street lamp is centred on its bbox, so the pole is not at the origin: find the pole base from the lowest vertices.
- Wok flame = emission-only Principled Volume ring around each well. Too-small ring = hidden under the wok; low-contrast noise
  = orange fog. Vertically stretched 4D noise with a tight ramp reads as tongues.
- Steam is a procedural plume volume, not Mantaflow: the walkthroughs are 408–480-frame uncut takes and a Mantaflow cache
  that long can't be baked inside the 10-minute GPU-queue budget. Volume boxes have object motion blur off anyway.
- Bare bulbs at 1.95 m and the stall sign board (orig. bottom 1.93 m) were inside the walk path's 0.45 m clearance; the board
  now sits on the beam (bottom ~2.1 m).
- fal: Meshy 7.1 ~8–20 min/job vs Tripo ~3.5 min; the fal account is shared with the other scene's session. 158 jobs took ~4 h.
  Meshy failed 3× on `hk_crate_stack` (fal "downstream_service_error" 500) → Tripo-only pick.
- Both generators turned the racing newspaper's printed horses into 3D figurines: retired; a direct-modelled folded slab
  textured with the reference photo replaces it.
- Brand check: only the beer crate ref came back branded ("RIVERTON Brewing Co."): `hk_beer_crate_nb`. Shop/neon names were
  checked against real HK businesses/brands; dropped 榮華, 利群, 華豐, 金鳳, 聯發, 德昌, 永利, 新華, 深夜食堂.
- Final frames: ~14 s each at 1920×804, 48 spp, with haze/steam/flame volumes and drizzle (rest of the shared GPU queue on top).

- Grounding (v2, after Apek spotted floating chairs): `_drop` rested the *bbox* on the highest hit under the footprint, so
  a stool whose box clipped a table edge sat 74 cm up with its feet over the road, and the road tables (base 15 cm lower)
  were taller than the stools' fixed 0.6 m drop start, so 11 stools stood *on* the t3–t5 table tops (grounded, so no
  float check caught it). Now: drop by footprint, then `settle()` down by the smallest clearance of the feet and a spread
  of all vertices (feet alone sank plates into table rims); stools drop from table base + 0.5 m; hanging props are
  `no_support`; the validator's FLOAT uses contact points (as `pipeline/grounding.py`) and a GROUND rule says stools/tables
  must stand on pavement/road. A pass-through ray stepping 1 mm past the prop's own surface skipped supports closer than
  that and mis-measured every gap: step 10 µm. The 54 cm fried-rice platter had no room on t1 (it sat on the cups): dropped.
- Bulb glass emission 60 → 18 (burnt out to a white disc). Wok flames: tongues hug the bowl, full strength under the wok,
  gone ~5 cm above the well rim, finer vertically stretched noise, blue jets broken by noise; the old wide ring stood off
  the bowl as an orange curtain. `scripts/flame_try.py` swaps the flame/bulb materials into a build for quick look-dev.

## Results (2026-10-30)
- Picks: 69 Meshy 7.1, 9 Tripo H3.1, 2 retired (newspaper → direct-modelled; beer crate → `_nb`). Validator: 0 open, 3 accepted.
- fal spend for this scene: 261 calls, ~$140 est (97 GPT Image 2.5 refs/textures, 85 Meshy, 79 Tripo).
- Shots (`out/shots/<shot>_graded.mp4`, 1920×804, 48 spp, ffmpeg grade): s1_street_crane 5 s, h1_walk_in_to_wok 20 s,
  s2_teapot_wok_rack 6 s, s3_wok_push 4 s, h2_walk_tables_neon 17 s, s4_neon_tilt 5 s; reel `out/shots/hk_dai_pai_dong_reel.mp4`
  (57 s) and `hk_dai_pai_dong_reel_small.mp4` (<30 MB). Hero stills `out/stills/*_graded.png` (64 spp).
- Breakdown: `breakdown/hk-dai-pai-dong/clips/{a_layout,b_props,c_materials,d_lighting}` (144/240/144/240 frames + mp4).
- Part of h2 and all of s1–s4 were found already rendered when `render_finals.sh` reached them (frames at ~1.5 s/frame
  wall time, not by this session's driver). They match the current hk.blend and shots.json (checked by eye), so they were kept.
- Clay passes inherit the night exposure (+0.4 EV) and wash out: bts.py sets −0.7 EV for clay.

## SKILL.md: what was wrong, missing or unclear for a semi-outdoor scene
1. **Step 1 assumes a room** ("room size", "door at y=0, deep along +Y", ceiling). A street needs: street axis, facade
   planes on both sides, kerb/road heights, how far the modelled street runs before a backdrop card, and what is overhead
   (awning) instead of a ceiling. I documented the conventions in `brief.md`; SKILL.md should say what to write for open sites.
2. **Step 7 "Shell and layout" has no guidance for facades.** At street scale, buildings are 16–27 m tall and mostly seen
   at grazing angles: generated orthographic facade photos on planes + 3D ledges/pilasters/AC units/signs worked; say so.
   Also: ground-floor architecture (pilasters, fascias) collides with set dressing that backs onto it.
3. **Step 8 drop rays: "start below anything overhead"** needs a per-prop drop height, not one per scene. Outdoors there are
   several overhead layers (awning, sign boards, hanging bulbs, shelves, table tops for stools).
4. **Step 11 says Mantaflow steam**, but the same SKILL asks for long uncut walkthroughs. Those two conflict with the
   10-minute GPU-queue rule (a 500-frame cache won't bake in one call). Say when a procedural volume is the better choice.
5. **Step 11 has no fire.** Wok flames / gas jets / candles need guidance (emission volume vs mesh, light flicker drivers).
6. **Rain vs drizzle and wet ground** are one line in the SKILL; wet pavement (puddle mask, roughness, ripples) is the
   most important material outdoors and deserves a step.
7. **Step 5 compare**: the shared `render_compare.py` is broken on 5.0.1 (HDRI path, above), and its Tripo "front" view is a
   side view unless `yaw.json` is filled in — say so, or fix the shared script.
8. **Step 12 path check**: the 0.45 m clearance rule fights bulbs on cords and sign boards at head height on a street stall.
   Worth saying "raise set pieces to clear the walk, or route around".
9. **Step 15 dollhouse for open sites**: "hide the ceiling and near walls" doesn't apply. What worked: orbit on the open
   (street) side only, hide the awning tarp and rafters, hide everything on the far pavement/far buildings for the whole orbit,
   hide cross-street cables. The SPEC's 120° orbit around a "room's vertical axis" should allow a partial orbit for open sites.
10. **Budget/time table**: fal Meshy throughput collapses when two sessions share one account; plan ~4 h for 158 jobs, and
    start the scene shell while generation runs (the order in the SKILL suggests waiting).
11. **No step mentions sky/backdrop.** Outdoors at night the sky and the far end of the street are in most frames.
12. **Gate wording "agree on the look"** at step 2 is fine, but for an approved concept with a real landmark in it (here the
    harbour tower), the SKILL should say to keep landmarks soft/unrecognisable or regenerate the backdrop without them.
13. **Step 8 has no contact check.** A footprint/bbox raycast drop puts props on whatever is highest under the box, not
    under the feet; say to settle by the lowest vertices and run `pipeline/grounding.py` after every dressing pass, with
    a rule that furniture stands on the ground. Low-angle stills (knee height) are the visual check.
