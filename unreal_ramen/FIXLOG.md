# Ramen → Unreal 5.8: fix log

Copies: scripts in `anyscene/unreal_ramen/` (pristine originals as copied at 20:17 in `_orig/`), scene copy
`anyscene-unreal/ramen/ramen_copy.blend`, project `anyscene-unreal/AnySceneRamen/`. Patch of all script changes: `ramen_fixes.patch` (`diff -ru _orig .`, 216 lines).

**G** = generic (mergeable into `anyscene/unreal/`), **R** = ramen-specific (lives in `anyscene-unreal/ramen/work/`).

## Mergeable change list (generic)

| # | File | Change | Why |
|---|------|--------|-----|
| G1 | `export.sh` | Run the `export_blend.py` next to the script, not `$A/unreal/export_blend.py` | Per-scene copies of `unreal/` silently ran the shared exporter (the one other jobs are editing). |
| G2 | `export.sh` | `EXPORT_NOQUEUE=1` skips `pipeline/gpu_run.sh` | CPU bakes don't need the GPU; with an Unreal job holding the queue the export just waited. |
| G3 | `export_blend.py` | Mantaflow domains (FLUID modifier, DOMAIN) go to `fx` (`kind: mantaflow_gas`, cache path, bounds) instead of `sample_volume` | The slice bake can't see the cache grids; it read the steam shader's constant density 8.0 and would build an opaque local-fog box. Steam is a Niagara job (NIAGARA.md). |
| G4 | `build_level.py` | `ANYSCENE_HERO_CAM` picks the PlayerStart camera (was hard-coded `cam_street`, fallback = first camera) | Scenes without `cam_street` got whatever camera came first. |
| G5 | `render_mrq.ps1`, `perf.ps1` | Full `-dpcvars` set (asset/texture/static-mesh async compilation off, Niagara wait-on-activate) | Was `Editor.AsyncAssetCompilation=0` only. |
| G7 | `build_level.py` `stage_materials` | All-glass meshes (no baked slots): assign the glass MIs from section 0 | glTF drops the unused BAKED slot 0, leaving 1 section, which got the untextured baked MI. Windows, door panes, fridge door, water glasses and jars rendered opaque (11 assets here; HK likely has the same). |
| G8 | `export_blend.py` `ensure_bake_uv` | Set `active_render` on the original UV **by name** after `uv_layers.new("bake")` | **Biggest visual bug.** `uv_layers.new()` reallocates the collection; setting `active_render` through the stale reference cleared it on every layer, so image nodes with an implicit UV (and Texture Coordinate → UV) sampled a single texel. Every re-unwrapped poster, calendar, flyer, sticker, menu card, decal, neon sign and the UV-driven tile wall baked to a flat colour (37 of 152 smart_project assets here). Verified in isolation (`work/uvdbg2.py`: after the old code both layers read `active_render=False`). HK/caustic/bakery/MC exports are very likely affected too. Not fixed upstream as of 21:50. |
| G9 | `export_blend.py` (Rewire orm, `cuts_out`, `e["alpha"]`) + `build_level.py` (`master_baked(masked=True)`) | Principled Alpha baked into ORM.R (was a constant 1); assets with a linked/<1 alpha get `M_AnyBakedMasked` (opacity mask = ORM.R, clip 0.33) | Luminance-keyed decals (floor grime, drips, splatter, rings) and stickers rendered as opaque dark/light squares. `MaterialExpressionDitherTemporalAA` is not exposed to Python in 5.8, so it's a plain clip. 30 assets here. Assets that are opaque keep `M_AnyBaked` (R=1, unchanged). |
| G10 | `export_blend.py` `--only` (note, not fixed) | `--only` matches object names, not asset names (assets named from mesh data, e.g. `decal_floor_001` ← object `decal_floor.001`) | Re-exporting by asset name silently skipped 17 of 42. Workaround: map assets → object names via placements. Suggest matching `an` too. |
| G6 | `perf.ps1` | `r.setres <ResX>x<ResY>w` added to `-ExecCmds` | Same fix mission-control landed upstream (their version also adds a comment line); take upstream's. Confirmed needed: the log shows 1066x600 until `r.SetRes = "2560x1440w"` on frame 1, and the CSV metadata then reads 2560x1440. |

## Ramen-specific

| # | Where | Change | Why |
|---|-------|--------|-----|
| R1 | `work/prep_copy.py` | 5 decal/poster images with `//..\..\refs\ramen\tex` paths re-pointed (absolute) at `blender-scene/refs/ramen/tex`; steam cache dirs re-pointed at the original `scenes/ramen/cache/r2` (read only) | Plain file copy breaks relative paths (make_copy.py would have had to open the original, which is open in the user's GUI Blender). |
| R2 | `work/prep_copy.py` | Added `cam_bowl` (shots.json `bowl_insert` key: pos (3.2, 2.3, 1.42), aim bowl + 7 cm, 100 mm f/2, focus 1.52 m) | The blend has no close-up camera; shot cameras are created by the camrig at render time. |
| R3 | export args | `--frame 1` (heroes and render.py stills use frame 1), `--grade-sh scenes/ramen/finish.sh`, CapCut ffmpeg | Scene's grade lives in finish.sh. |

## Overlap with upstream (`anyscene/unreal/`, mission-control's fixes landed after my copy)

- **G7 ≈ upstream "sections-based material mapping for all-glass meshes"**. Upstream's is better (exporter writes the real
  `sections` list); merge upstream's and drop G7.
- **G6 = upstream `perf.ps1` r.setres**. Take upstream's.
- Upstream's export.sh crash-resume, GLB-exists done test and the ffmpeg-from-env change were already in my copy.
- **Not upstream yet, merge these:** G1, G2, G3, G4, G5, **G8 (flat posters/decals)**, **G9 (alpha cutouts)**, G10 (note).
  G8 hunk applies on top of upstream as-is: upstream line ~544 still sets `ar.active_render = True` on the stale reference.

## Results

Level `/Game/AnyScene/Ramen/L_Ramen`: 296 mesh actors (274 unique meshes), 23 lights (8 spot, 8 rect, 7 point),
7 cine cameras, height fog (haze_volume) + 1 local fog volume (kitchen_vapor), grade PPV with finish.sh LUT.
PlayerStart = cam_wide. Steam (2 Mantaflow domains) and rain (35k particles) are in `scene.json` fx, not built.

**Perf** (standalone `-game`, offscreen, 2560x1440, Lumen HWRT + VSM + Nanite + volumetric fog, 841 frames from
cam_wide, GPU otherwise idle at the time: 1.4 GB used before the run):
85.6 fps mean · frame 11.7 ms (p95 12.7) · GPU 11.2 ms (p95 11.8) · game 1.2 ms · peak GPU memory +3.9 GB.
Top GPU passes: Lights 6.1 ms (23 movable shadowed lights; half the frame), TSR 0.9, shadow depths 0.7,
Lumen reflections 0.6, Nanite vis 0.3, volumetric fog 0.3.

**Stage timings** (machine shared with ~5 other Blender/Unreal jobs, CPU at 100%, RAM ~0 free during export):
| stage | time |
|---|---|
| scene copy (1.27 GB blend + 1.2 GB lib) + path prep | ~1 min |
| export (CPU bake, 274 assets, one Blender OIIO crash + resume) | 41 min wall (2164 s second run) |
| UE build, full (textures 60 s, meshes 801 s, materials 216 s, level 4 s, sequences 10 s) | 18 min |
| fix pass: re-export 42 assets (2 runs) | 1.5 min |
| fix pass: reimport + materials/level/sequences | ~1.5 min |
| MRQ stills, warm DDC (wide / counter / bowl) | 39 / 20 / 20 s (cold first pass: 246 / 108 / 56 s) |
| Cycles reference, cam_bowl, 256 spp OptiX | 65 s render, 69 s wall |
| perf run (900 frames) | 37 s |

## Honest read of the match

- **Layout, props, lighting placement, framing: near-identical** in all three views. Every prop, lamp, sign, stool,
  poster and decal is where Cycles has it; shadows from the pendants and the counter spots fall the same way.
- **Biggest miss: steam.** Cycles' counter and wide shots are dominated by a bright steam wall over the stove; UE has
  none (Niagara gap, NIAGARA.md). It also changes the mood: Cycles' kitchen glows, UE's kitchen is clear and harder.
- **Tone:** UE is flatter and slightly brighter in the shadows, less of Cycles' warm crush (AgX vs UE filmic + LUT;
  the open AgX tone-match item).
- **Backsplash:** stainless at roughness 0.19 / metallic 1 reads as crinkled mirror foil under Lumen vs grey grime in
  Cycles. The bake is correct; the procedural grime (AO + noise) gets lost at 1024x4096 and Lumen reflects the lamps
  harder. Would want a roughness floor or AO-in-roughness tweak (not done).
- **Glass:** water glasses read milky/plastic (translucent master, no refraction, white tint); Cycles' are dark and
  refractive. Window/door glass is fine (rain-on-glass texture lost).
- **Close-up:** a stray white sliver on the counter left of the bowl in UE (not in Cycles); likely one of the
  masked decals/Planes clipping differently. Not investigated.
- Faint counter ring stains (decal_rings) are mostly clipped away by the 0.33 mask.
