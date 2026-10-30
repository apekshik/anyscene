# AnyScene

Photoreal Blender scenes from a one-paragraph brief, built by AI agents.

You describe a place. An agent following [`SKILL.md`](SKILL.md) then:
1. generates concept images and a reference image for every prop;
2. turns each prop into 3D with both Tripo H3.1 and Meshy 7.1 on [fal](https://fal.ai), and picks the better one;
3. scripts the room, dresses it from big furniture down to small clutter, and checks every prop for collisions and floating;
4. adds grime, decals, night lighting, haze, steam and rain;
5. shoots cinematic and handheld walk-through shots, renders them in Cycles and grades them;
6. cuts a behind-the-scenes video of how the scene was built.

No prop is modelled by hand. The two example scenes were each made in about a day of agent work, for about $150 of generation.

| Scene | Props | Shots |
|---|---|---|
| [`scenes/tokyo-electronics-repair`](scenes/tokyo-electronics-repair) — a 1 AM electronics repair counter, rain outside | 86 generated | 7 cinematic + 2 handheld |
| [`scenes/tokyo-ramen-shop`](scenes/tokyo-ramen-shop) — a ramen counter at last orders, steam and rain | 74 generated | 6 cinematic + 2 handheld |

This repo holds the process and the code. The finished scenes (.blend files, generated models, renders) are large and are
downloaded separately.

## Layout

```
SKILL.md        the process, step by step, with every gotcha we hit; agents start here
generate/       fal client: reference images and image→3D (Tripo H3.1, Meshy 7.1), with a spend log
pipeline/       env.sh (finds Blender/ffmpeg), GPU queue, comparison renders, gallery page
camera/         camera rig and shot renderer: moves, rack focus, handheld walk, lens FX (see camera/README.md)
breakdown/      the behind-the-scenes video and the promo cut
scenes/<name>/  one folder per scene: assets.json (props), picks.json (model choices), shots.json, NOTES.md, scripts/
```

Each scene keeps its own build scripts in `scripts/`. A scene's room shell and dressing are specific to that place, so a
new scene starts from the closer example and an agent rewrites those parts.

## Requirements

- Blender 5.0+ (`BLENDER`, otherwise found on PATH or in the default install location)
- ffmpeg with `h264_nvenc` (`FFMPEG`, default `ffmpeg`). The example scenes were built on Windows with an NVIDIA GPU;
  on other GPUs, swap `h264_nvenc` for `libx264` in the encode steps.
- Node 20+
- A fal API key in `FAL_KEY`
- `uv` for the breakdown videos (`uv run --with pillow python breakdown/assemble.py <scene>`)

## Start a new scene

Point your agent at `SKILL.md` and give it a brief:

> Use SKILL.md to build a new scene: a Lisbon tram depot at dawn, one tram half-stripped for repair.

Then check its work at each step's gate: concept, prop picks, clay layout, lit stills, shot previews.

## Credits

The process follows the "create high quality blender scene with AI" video workflow: concept image, scripted room shell,
image-to-3D props, scripted repair, dressing, shaders, lighting, handheld camera, grade.

## License

Code: MIT, see [LICENSE](LICENSE). Generated assets are released separately under their own license.
