# Behind-the-scenes videos — shared spec

One BTS video per scene (repair, ramen), about 60–75 s, showing how the scene was built:
layout → generated props → placing them → materials and grime → lighting → post → final shot.
The two videos must look like a pair, so both scenes follow this spec exactly.

## Who makes what

- **Scene agents (repair, ramen)** render the four "dollhouse" clips below from their own scene files,
  into `breakdown/<scene>/clips/`. Nobody else knows your stage files and object collections.
- **Main session** makes the concept, asset-generation, post-wipe and final-shot segments,
  the captions, and assembles the video (`breakdown/assemble.py`). Don't make captions or titles.

## Output format for the dollhouse clips

- 1920×1080, 24 fps, PNG frames in `breakdown/<scene>/clips/<clip>/####.png` plus an mp4 of the same
  (h264_nvenc, any decent bitrate) at `breakdown/<scene>/clips/<clip>.mp4`. No text, no grade, no letterbox.
- Leave the bottom 140 px free of anything important (captions go there).

## The dollhouse camera (same for all four clips)

One continuous orbit split into four clips, so they cut together as one move:

- A cutaway view of the whole interior from a high three-quarter angle (about 35–45° down), looking at the
  middle of the room. Hide the ceiling and the one or two walls nearest the camera at every angle, so the
  interior reads like a dollhouse. Hide anything that blocks the view for the whole orbit (exterior shell,
  awning, street) unless it is part of what that clip shows.
- Lens about 28–35 mm, f/8 or no DOF. Fit the whole interior with a little margin.
- Total orbit: 120° around the room's vertical axis, at constant angular speed, ease in on clip A only and
  ease out on clip D only. Clip A covers 0–30°, B 30–60°, C 60–90°, D 90–120°.
- Put the start angle where the room reads best (counter/bench in view all the way).

## The four clips

| Clip | Frames | What it shows |
|---|---|---|
| `a_layout` | 144 (6 s) | The empty shell as the layout: walls, floor, counter/bench blocks, shelves. Clay look: one flat light-grey material on everything (Workbench or Eevee with a soft studio light and AO). Optionally the shell pieces rise into place in the first 2 s. |
| `b_props` | 240 (10 s) | Same clay look. The generated props appear one at a time in a sensible order (big furniture and shelves first, then big props, then small clutter), each scaling up from 0 with a small overshoot over ~6 frames. All props in place by frame ~200; hold after that. |
| `c_materials` | 144 (6 s) | Switch from clay to the real textured materials with neutral flat lighting (bright, even, no night mood): a wipe or dissolve over the first ~2 s. Then fade in the grime and decals (stains, wear, posters, signage) over the next ~2 s. |
| `d_lighting` | 240 (10 s) | Start from the textured scene in darkness (world near black, every light off). Turn the lights on one after another over ~7 s, with a short ramp each: key practicals first (lamp/pendants), then signage/neon, window/street, fills and bounce last. Then the volumetrics (steam, haze, rain) fade in. End on the full night look. |

Render engines: A–C in Eevee (fast). D in Cycles with low samples and the denoiser; it is the money shot,
so keep it clean, but under ~10 GPU-minutes.

## GPU rules (one 16 GB card shared by both scenes)

- Every Blender run, previews included, goes through `pipeline/gpu_run.sh`. Never two Blenders on the GPU.
- Don't hold the GPU between clips; release it so the other scene can interleave.
- Don't save over any existing .blend; build the BTS setup in a script on a copy (`breakdown/<scene>/bts.blend`).

## When done

Check a contact sheet of each clip yourself, then report: clip paths, frame counts, GPU minutes, and anything
that looks off. Don't commit or publish.
