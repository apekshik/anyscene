# Repair shop — notes and gotchas

Pipeline (all scripted, run from the repo root):

1. `scenes/tokyo-electronics-repair/assets.json` — 32 generated props (4 from the head-to-head + 28 new), direct-modelled list.
2. `node scenes/tokyo-electronics-repair/scripts/refs.mjs` — GPT Image 2.5 Sunburst product refs + scene textures (street, tags, labels, poster, calendar, decal).
3. `node scenes/tokyo-electronics-repair/scripts/gen3d.mjs [ids]` — every prop through Tripo H3.1 and Meshy 7.1, 12 at a time; skips existing GLBs.
4. `bash scenes/tokyo-electronics-repair/scripts/compare_ready.sh` + `scenes/tokyo-electronics-repair/scripts/sheet.sh` — same-light renders, review sheets; picks in `picks.json`.
5. `scenes/tokyo-electronics-repair/scripts/prep.py` → `scenes/tokyo-electronics-repair/props/<id>.blend` (front to -Y, real scale, bottom-centre origin, decimate, ≤2K textures).
6. `scenes/tokyo-electronics-repair/scripts/fixes.py` — script repairs: oscilloscope CRT (finds the green screen by ray-casting the front and sampling the
   albedo at the hit UVs, then builds a domed emissive graticule + trace patch), helping-hands lens faces → glass, CRT TV screen → blue glow.
7. `bash scenes/tokyo-electronics-repair/scripts/rebuild.sh 4` — shell → dress (passes 1-4) → validate → lights → cameras → `repair_final.blend`.
8. Renders through `pipeline/gpu_run.sh`: `preview.py` (stills), `render_frames.py` (clip chunks), `grade.sh` (post).

Gotchas:

- glTF imports come in with `rotation_mode = QUATERNION`; setting `rotation_euler` on a copy does nothing until the mode is XYZ.
- A smooth-shaded box without a bevel interpolates normals across its faces; a glass slab built that way refracts like a lens.
- Generated lamp shades are closed meshes: a spot light placed inside the shade is blocked. Put it just under the rim.
- Light panels outside a storefront show up as bright discs through the glass; turn off camera/glossy/transmission visibility.
- Drop rays must start under whatever is above the support (ceiling conduit at 2.65 m, the rack shelf above, the bench drawer
  cabinets); starting on a face lands the prop inside it.
- A float check that starts its ray just below the prop's bottom begins inside a thin bench top and reports the top's thickness.
- The fal queue is shared with the ramen agent; ~10 % of jobs failed with Tripo 504 "downstream service unavailable" or
  ECONNRESET while polling. Re-running gen3d.mjs with the ids recovers them.
- Blender 5.0 compositing is `scene.compositing_node_group` (a CompositorNodeTree with a Group Output); Glare's type is an input socket.
- The CapCut ffmpeg has no glob, drawtext, eq or libx264; it has curves, hue, rgbashift, vignette, noise and h264_nvenc.

## Round 2 (densify, grime, de-brand, cinematic shots)

Build: `bash scenes/tokyo-electronics-repair/scripts/rebuild2.sh C` = shell -> dress.py pass 4 -> validate -> dress2.py A|B|C -> grime.py -> lights.py ->
cameras.py -> `repair_final.blend`. Finals: `bash scenes/tokyo-electronics-repair/scripts/render_round2.sh` (heroes, then every shot in 24-frame chunks
through `scenes/tokyo-electronics-repair/scripts/shoot.sh`, then a graded mp4 per shot). Shots: `scenes/tokyo-electronics-repair/shots.json` (camrig contract).

- fal was locked ("Exhausted balance") for all of round 2. The manifest already holds the 70 round-2 props (pass A/B, `*_nb`
  regenerations, street props, `models` per prop, P2 for tiny ones); `refs.mjs` then `gen3d.mjs` pick them up after a top-up.
  Everything in the round-2 passes is therefore direct-modelled or an instanced/tinted generated prop.
- De-branding without regeneration: `views.py` renders bbox-fitted ortho views; `debrand.py` takes rectangles in those views'
  normalised coordinates, ray-casts them onto the mesh, maps hits to texels per material, dilates, and fills each region with the
  label's ground colour (median of its brighter half) plus grain, and flattens the same texels in the normal map (embossed text
  otherwise survives). A UV-space blur fill smeared neighbouring UV islands into the patch: flat ground colour works better.
  Labels that cover a whole product (spray cans, cup noodle, tissue box) were replaced by generic direct-modelled versions.
  Originals are kept in `scenes/tokyo-electronics-repair/props_prebrand/`.
- `box_blur` via cumulative sums leaves round-off non-zeros everywhere: threshold masks at > 0.01, not > 0.
- Joined direct props get a bottom-centre origin; children parented after a join must be offset by the moved origin.
  `put()` settles by the world bbox minimum, so it works for any origin.
- Per-instance variation: the `grime_layer` group multiplies albedo by Object Info > Color, so `ob.color` tints instances that
  share a mesh (yellowed / dark / cool).
- camrig's final mode doesn't enable a GPU compute device: run it with `--python scenes/tokyo-electronics-repair/scripts/gpu_prefs.py` first
  (`shoot.sh` does), otherwise Cycles renders on the CPU at ~4-5 min/frame instead of ~12-15 s.
- Night look is fragile: each new practical needs the exposure re-checked (round 2 ended at exposure 0.45 with the counter lamp,
  ring lamp, one rack tube, TV glow and the vending spill).
- The AO node inside the grime group costs almost nothing here (profiled: 6.1 s with or without).
- Left racks / under-counter were near black in the first round-2 hero. Fix: a clip-lamp practical on the middle rack post
  (`rack_clip_lamp`, own spot + glow), a soft overhead `rack_bounce` area (11 W, glossy off), a low warm `counter_bounce`
  on the shop side of the counter, rack tube 13 W, exposure 0.95 (+0.5 EV), and the grade lifts blacks (curves start at
  ~0.03 instead of ~0.01). A 45 W bounce plus 1.0 exposure looked like the room lights were on: keep bounce low and let the
  practicals make the contrast.
- s3, s4, s5 and s6 were rendered before that exposure lift (one stop of difference is mostly absorbed by the per-shot grade).
- CRT TVs: scanlines + rolling bar + sin*sin vignette on the no-signal glow (grime.py); a product of triangle waves made
  visible diamond banding.
- camrig focus `obj` uses the bbox centre: for a deep object (oscilloscope) the screen face sits ~15 cm in front of it and is
  slightly soft at 135 mm; use a `pos` on the face instead.
- fal unlocked mid-round (new user-env key). 73 round-2 props through both models: 146 jobs, ~31 failed on the first pass
  (Meshy timeouts, a fal-side 422 "AIModel must be one of ..." from meshy/v7.1, ECONNRESET); two retries recovered all but
  three Meshy jobs (cable_crate, parts_bins, receipts -> H3.1 only).
- Generated winners replace direct stand-ins in `dress2.py` (`SWAPS` by object name, `ADDS` for new ones; names are kept so
  lights/shots that reference them keep working). Debranded originals are swapped for their `*_nb` regenerations through
  `scenes/tokyo-electronics-repair/nb_swap.json`, except the oscilloscope, solder station, helping hands and CRT TV, which carry script fixes.
- Generated props are larger than the stand-ins: `resolve_clashes()` (end of dress2) runs the validator's rules and
  spiral-searches each clashing or floating smaller prop to a clear spot (23 moved, 0 removed).
- Validator now has a real mesh check against fixed furniture (`FURNITURE`, BVH overlap with the prop lifted 3 mm). It caught:
  the work lamp through `drawer_cabinet_2` (the user's bug; lamp re-posed from the front edge right of the scope, arm reaching
  back-left over the helping hands, spot re-aimed at them), the vintage radio through the ceiling conduit drop, the desk fan,
  kerosene heater, portable TV and microwave through the rack shelf above them, the speaker pair through a rack shelf, and the
  wall clock into the back wall (v1 scene). rebuild2.sh now validates after dress2 as well.
- The street had no ground beyond the pavement strip, so a dropped generated vending machine fell to z = -48; added a road slab.
