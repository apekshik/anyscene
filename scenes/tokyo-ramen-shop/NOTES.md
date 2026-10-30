# Ramen shop — notes

Pipeline: `assets.json` → `gen.mjs` (GPT Image 2.5 Sunburst refs + Tripo H3.1 and Meshy 7.1 for every prop)
→ `scenes/tokyo-ramen-shop/scripts/compare.py` + `review.sh` (ref | H3.1 | Meshy, front/back/clay) → `picks.json`
→ `scenes/tokyo-ramen-shop/scripts/prep.py` (→ `lib/<id>.blend`) → `scenes/tokyo-ramen-shop/scripts/build.py` (shell, dress + validate, light, post, cameras, mirror)
→ `scenes/tokyo-ramen-shop/scripts/render.py` (stills, clip chunks) → `finish.sh` (ffmpeg grade, vignette, grain, NVENC).

Rebuild and render:
```

bash pipeline/gpu_run.sh "$B" -b --factory-startup --python scenes/tokyo-ramen-shop/scripts/build.py -- --samples 256 --save --final
bash pipeline/gpu_run.sh "$B" -b scenes/tokyo-ramen-shop/ramen.blend --python scenes/tokyo-ramen-shop/scripts/render.py -- stills wide,counter --samples 384
bash scenes/tokyo-ramen-shop/scripts/render_clip.sh
```
Previews: `build.py -- --preview wide,counter,kitchen,door,top [--clay] --samples 32 --tag _x` → `out/prev/`.

## Gotchas
- **matrix_world is stale** on objects created in the same script until `view_layer.update()`; the mirror pass read identity matrices and threw the whole room away.
- **Mirror without mirroring text**: layout is authored counter-on-left, then every top-level transform is conjugated `M @ mw @ F` (x-flip) so positions reflect but objects stay proper rotations; printed labels still read. Camera animation is created *after* the mirror (keyframes aren't conjugated).
- **glTF import uses quaternion rotation mode**: `rotation_euler` is silently ignored, both in prep (rotate mesh data instead) and when dressing (set `rotation_mode = "XYZ"`).
- **glTF images arrive already packed**; calling `img.pack()` again on an unmodified one (empty filepath) silently drops its data → magenta props. Only repack images you resized.
- Tripo H3.1 fronts face +X, Meshy -Y; prep turns Tripo by -90° so every prop's front is -Y.
- Generators invent depth: boxy appliances (ticket machine, fridge, boiler, gas range) get per-axis `dims` in the manifest.
- Drop-to-surface rays must start *below* the hood/shelves (default 1.3 m), or kitchen props land on top of the hood.
- Area lights shine along local -Z: `rot x +90` → +Y, `rot y -90` → +X. Two fills were pointing out of the shop.
- Hidden fill lights still show **through rough glass** unless `visible_transmission = False` too (door panes went white).
- Brick texture is 2D (ignores object Z) → use UVs on walls facing X.
- Compositor (5.0 node group): only glare + lens distortion/CA kept in Blender; an ellipse-mask vignette and colour balance produced a quarter-frame / blue-tint domain bug, so grade/vignette/grain live in `finish.sh`.
- CapCut's ffmpeg has no `eq`, `drawtext`, glob input or libx264 → `curves`/`hue` and `h264_nvenc`.
- `render.resolution_percentage` must be set to 100 explicitly (factory-empty scenes default lower).
- Validator: "floating ticket_machine 12 cm" is its raised plinth; "gas_range x stockpot" is pots seated on the burner grates (decimated meshes interpenetrate a few mm). Both accepted.
- fal: two Tripo jobs failed transiently in a 12-wide pool; a plain retry worked.

## Round 2 (densify, grime, steam, exterior, camrig shots)
Build is now `build.py` stages `shell,dress,passA,passB,passC,grime,steam,light,post`, saved to `ramen_r2.blend`;
`scenes/tokyo-ramen-shop/scripts/rebuild.sh` = build (CPU) → `bake_steam.py` (CPU, cache in `cache/r2/`) → optional GPU preview.
Process sheets per pass: `scenes/tokyo-ramen-shop/scripts/process_r2.sh` → `out/process/r2_<pass>.png` (wide + counter, lit / clay).
Shots: `shots.json` (world = post-mirror coordinates) rendered with `camera/shoot.py` → `out/shots/<shot>/`.

- **fal balance ran out** at the start of round 2 (403 "User is locked … Exhausted balance"). `round2.json` holds the
  47 Pass A/B/C prop prompts + 16 decal/flyer/neon textures, merged into `assets.json`; `gen_retry.sh` retries every 10 min.
  Meanwhile pass A reuses/varies the round-1 picks and passes B/C are direct-modelled (paper + real Yu Gothic text objects).
- **Mirror conjugation moves origins, not vertices.** Anything built with world-space vertices and origin at 0 (noren
  panels, curves for conduit/cables/noodles) was shifted +W instead of mirrored. `mirror_x` now recentres such origins first.
- **Mantaflow `surface_distance` is effectively in cells**: 0.012 emitted only from discs wide enough to contain cell
  centres (pots yes, the bowl never). Use ~1.0. Also keep emitters well inside the domain (border cells are walls).
- `bpy.ops.fluid.free_all()` is an async job in background mode: called before `bake_all()` it ran *after* the bake and
  deleted the new cache. Clear the cache folder with `shutil.rmtree` instead.
- Negative cache frames work (`cache_frame_start = -70`): shots render frames 1..N with fully developed plumes.
- Cache paths are saved relative (`//cache/...`): copying a .blend elsewhere points it at a different cache.
- Particle `rotation_mode = "VEL"` aligns the instance's +X with velocity: lay rain-drop geometry along X.
- A SimpleDeform-bent towel exploded into a floating sheet; replaced with the hand-towel prop on the pass.
- Killing a stray background Blender was refused by the sandbox classifier; work around by writing to a new .blend
  name and cache folder rather than racing the orphan.
- **`blender -b file.blend` renders on the CPU**: Cycles device prefs are user preferences, not saved in the .blend.
  Every render from a saved file now runs `--python scenes/tokyo-ramen-shop/scripts/gpu_prefs.py` first (OptiX). Round 1's final stills and
  clip were CPU renders (that is why they took ~9 min / ~37 s per frame); round 2's first shot chunk ran at ~8 min/frame
  for the same reason before this was caught.
- **Object motion blur on Mantaflow domains = ~290 s of Cycles sync per frame** (velocity motion built from the noise
  grids); render itself was 7 s. `emitters.no_volume_blur()` turns object blur off on the domains only (camera blur stays).
  Found by bisecting with tiny CPU renders (sync is CPU-side, so no GPU lock needed).
- Texture-driven emission on dense generated meshes made every triangle a light (545k-emitter light tree);
  `emitters.run()` sets `material.cycles.emission_sampling = "NONE"` (5.0 moved it under `.cycles`) on heavy meshes.

## Round 2b: generated props swapped in (after the fal key was replaced)
- `r2gen.py` runs post-mirror in world coordinates, so the same code patches the steam-baked `ramen_r2.blend`
  (caches untouched; backup `ramen_r2_pre_gen.blend`) and runs at the end of `build.py` (stage `r2gen`).
  `dress.place(..., MIRROR=True)` converts design coordinates (x→W−x, facing→−facing, x± walls swapped).
- `dress.pass_a2` replaces the 34 reused round-1 instances with round-2 picks (`pick(id, fallback)`); `pass_bc_gen`
  swaps generated tongs/coins/tape/power strip/cat dish/hook items/vending machine for the direct-modelled ones.
- **Brands:** several references came back with real brands (Kirkland, McCormick, Ajinomoto, Nissin, Asahi, Marlboro,
  Kirin, Sharpie, 7-Eleven, Rinnai, CHNT, FamilyMart, PayPay, Hanshin, a known anime character). Those got `_nb`
  regenerations with fictional Japanese brands (`add_nb.mjs`); `dress.BRANDED` makes the branded originals unplaceable.
  Gyoza griddle (Rinnai) and junction box (CHNT) were left out instead. Round-1 assets still carry brands
  (Kirin crate/fridge, Sapporo poster, Kikkoman/mirin bottles, rice-cooker/register logos) — not yet de-branded.
- Meshy 7.1 took ~10 min per job; 15 jobs timed out in fal.mjs. Five placed props are Tripo-only for that reason.
- Running two gen.mjs passes at once double-submits in-flight jobs (existence is checked at start): avoid.
- Decals: generated on flat black/white backgrounds, alpha keyed from luminance (`m_decal`), stuck with raycasts.
