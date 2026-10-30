"""Assemble a behind-the-scenes video for one scene (see breakdown/SPEC.md).

    uv run --with pillow python -I breakdown/assemble.py repair|ramen [--only seg1,seg2] [--draft]

Segments (1920x1080, 24 fps), each written to breakdown/<scene>/seg/<nn>_<name>.mp4, then joined with short crossfades:
  title, concept, a_layout, assets, b_props, c_materials, d_lighting, post, final, end
The dollhouse clips (a_..d_) come from the scene agents in breakdown/<scene>/clips/; a missing clip becomes a labelled
placeholder so the cut can be reviewed before every clip exists. Captions are drawn here with Pillow, because the
ffmpeg builds without libfreetype have no drawtext.
"""

import json
import os
import random
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FF = os.environ.get("FFMPEG", "ffmpeg")
W, H, FPS = 1920, 1080, 24
XF = 0.5  # crossfade between segments, seconds
FONTS = "C:/Windows/Fonts/"
BG = (14, 13, 12)
INK = (236, 230, 220)
DIM = (178, 170, 158)

# Scene id (the prefix on its asset ids) -> its folder under scenes/ and breakdown/.
FOLDER = {"repair": "tokyo-electronics-repair", "ramen": "tokyo-ramen-shop"}

SCENES = {
    "repair": dict(
        title="Electronics repair, late night",
        kicker="Night Shops · Scene 01",
        concept="refs/tokyo-electronics-repair/concept_wide_sunburst_0.png",
        concept2="refs/tokyo-electronics-repair/concept_detail_sunburst_0.png",
        post_raw="scenes/tokyo-electronics-repair/out/shots/h1_back_to_bench/h1_back_to_bench.mp4",
        post_graded="scenes/tokyo-electronics-repair/out/shots/h1_back_to_bench_graded.mp4",
        finals=["scenes/tokyo-electronics-repair/out/shots/h1_back_to_bench_graded.mp4", "scenes/tokyo-electronics-repair/out/shots/s3_bench_rack_100_graded.mp4"],
        res="1920×804",
        accent=(122, 200, 168),
    ),
    "ramen": dict(
        title="Ramen counter, last orders",
        kicker="Night Shops · Scene 02",
        concept="refs/tokyo-ramen-shop/concept_wide_sunburst_0.png",
        concept2="refs/tokyo-ramen-shop/concept_detail_sunburst_0.png",
        post_raw="scenes/tokyo-ramen-shop/out/shots/h1_door_to_counter/h1_door_to_counter.mp4",
        post_graded="scenes/tokyo-ramen-shop/out/shots/h1_door_to_counter/h1_door_to_counter_graded.mp4",
        finals=["scenes/tokyo-ramen-shop/out/shots/h1_door_to_counter/h1_door_to_counter_graded.mp4"],
        res="1280×536",
        accent=(232, 150, 92),
    ),
}


def ff(*args):
    subprocess.run([FF, "-v", "error", "-y", *map(str, args)], check=True)


def duration(path):
    out = subprocess.run([FF, "-i", str(path)], capture_output=True, text=True).stderr
    h, m, s = out.split("Duration: ")[1].split(",")[0].split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def font(name, size):
    return ImageFont.truetype(FONTS + name, size)


def caption_png(path, step, head, sub, accent):
    """Bottom-band caption: step number, heading, one line of detail, over a soft dark gradient."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    grad = Image.new("L", (1, 260))
    for y in range(260):
        grad.putpixel((0, y), int(200 * (y / 259) ** 1.6))
    img.paste(Image.new("RGBA", (W, 260), (8, 8, 8, 255)), (0, H - 260), grad.resize((W, 260)))
    d = ImageDraw.Draw(img)
    x, y = 96, H - 128
    d.text((x, y), step, font=font("bahnschrift.ttf", 30), fill=accent + (255,))
    sx = x + d.textlength(step, font=font("bahnschrift.ttf", 30)) + 22
    d.text((sx, y - 6), head, font=font("segoeuib.ttf", 36), fill=INK + (255,))
    d.text((sx, y + 44), sub, font=font("segoeui.ttf", 27), fill=DIM + (255,))
    img.save(path)


def with_caption(src_args, vf, dur, cap, out):
    """Encode one segment: src (any ffmpeg input args) through vf to 1920x1080, caption fading in and out."""
    fade = f"fade=t=in:st=0.35:d=0.5:alpha=1,fade=t=out:st={max(dur - 0.9, 0.5):.2f}:d=0.5:alpha=1"
    ff(*src_args, "-loop", "1", "-t", f"{dur:.3f}", "-i", cap,
       "-filter_complex", f"[0:v]{vf},fps={FPS},setsar=1,format=yuv420p,trim=duration={dur:.3f}[v];[1:v]format=rgba,{fade}[c];[v][c]overlay=0:0:format=auto,format=yuv420p",
       "-an", "-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "19", "-b:v", "0", out)


LETTERBOX = f"scale={W}:-2:flags=lanczos,pad={W}:{H}:0:(oh-ih)/2:color=black"


def title_card(cfg, out, end=False):
    still = ROOT / cfg["finals"][0]
    frame = out.with_suffix(".bg.png")
    ff("-ss", "6" if not end else "3", "-i", still, "-frames:v", "1", "-vf", f"scale={W}:-2", frame)
    bg = Image.open(frame).convert("RGB")
    bg = bg.resize((W, int(bg.height * W / bg.width)))
    canvas = Image.new("RGB", (W, H), BG)
    canvas.paste(bg.filter(ImageFilter.GaussianBlur(14)).point(lambda v: int(v * 0.42)), (0, (H - bg.height) // 2))
    d = ImageDraw.Draw(canvas)
    if end:
        lines = [("segoeuisl.ttf", 30, DIM, "Layout, props, lighting and post all scripted in Blender 5.0"),
                 ("segoeuisl.ttf", 30, DIM, "Props: GPT Image 2.5 references → Tripo H3.1 / Meshy 7.1 on fal"),
                 ("segoeuib.ttf", 44, INK, cfg["title"])]
    else:
        lines = [("bahnschrift.ttf", 30, cfg["accent"], cfg["kicker"].upper()),
                 ("segoeuib.ttf", 76, INK, cfg["title"]),
                 ("segoeuisl.ttf", 34, DIM, "How the scene was built")]
    total = sum(s + 26 for _, s, _, _ in lines)
    y = (H - total) // 2
    for f, s, c, t in lines:
        fnt = font(f, s)
        d.text(((W - d.textlength(t, font=fnt)) / 2, y), t, font=fnt, fill=c)
        y += s + 26
    canvas.save(frame)
    dur = 3.0
    ff("-loop", "1", "-t", dur, "-i", frame, "-vf", f"fps={FPS},format=yuv420p", "-c:v", "h264_nvenc", "-preset", "p6", "-cq", "18", out)
    return dur


def concept(cfg, out, cap):
    """Two reference images with a slow push each (zoompan), the starting point for the scene."""
    parts = []
    for i, key in enumerate(["concept", "concept2"]):
        p = out.with_name(f"{out.stem}_{i}.mp4")
        frames = 72
        ff("-loop", "1", "-i", ROOT / cfg[key], "-vf",
           f"scale=3840:-2,zoompan=z='1.0+0.06*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},format=yuv420p",
           "-frames:v", frames, "-c:v", "h264_nvenc", "-preset", "p6", "-cq", "18", p)
        parts.append(p)
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts))
    joined = out.with_name(out.stem + "_j.mp4")
    ff("-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined)
    dur = duration(joined)
    with_caption(["-i", joined], "null", dur, cap, out)
    return dur


def prop_list(scene):
    picks = json.loads((ROOT / f"scenes/{FOLDER[scene]}/picks.json").read_text(encoding="utf-8"))
    refs = [p for p in (ROOT / "refs").rglob("*_0.png")]
    keys = [k for k in picks if not k.startswith("_")]
    rows = []
    for k in keys:
        v = picks[k]
        if not isinstance(v, dict) or v.get("model") in (None, "none") or v.get("retired") or f"{k}_nb" in keys:
            continue
        ids = [k, f"{scene}_{k}"]
        ref = next((r for r in refs if any(r.name == f"{i}_0.png" for i in ids)), None)
        model = v["model"]
        rend = {}
        for view in ("clay", "beauty"):
            for d in (f"scenes/{FOLDER[scene]}/compare/{model}", f"out/compare/{model}"):
                f = next((ROOT / d / f"{i}_{view}.png" for i in ids if (ROOT / d / f"{i}_{view}.png").exists()), None)
                if f:
                    rend[view] = f
                    break
        if ref and len(rend) == 2:
            rows.append(dict(key=k, model=model, ref=ref, **rend))
    counts = {}
    for k in keys:
        v = picks[k]
        if isinstance(v, dict) and v.get("model") not in (None, "none") and not v.get("retired") and f"{k}_nb" not in keys:
            counts[v["model"]] = counts.get(v["model"], 0) + 1
    return rows, counts


def assets(cfg, scene, out, cap):
    """A wall of props: each tile goes image reference → untextured mesh → textured mesh, staggered in a wave."""
    rows, counts = prop_list(scene)
    random.seed(7)
    cols, nrows = 8, 4
    pick = rows[: cols * nrows]
    tile = 184
    gap = 10
    gx = (W - cols * tile - (cols - 1) * gap) // 2
    gy = 140
    cache = {}

    def load(p):
        if p not in cache:
            im = Image.open(p).convert("RGB")
            im.thumbnail((tile, tile))
            t = Image.new("RGB", (tile, tile), (29, 27, 25))
            t.paste(im, ((tile - im.width) // 2, (tile - im.height) // 2))
            cache[p] = t
        return cache[p]

    frames_dir = out.with_suffix("")
    frames_dir.mkdir(parents=True, exist_ok=True)
    n = int(8.5 * FPS)
    hdr = font("segoeuisl.ttf", 30)
    tag = font("bahnschrift.ttf", 20)
    total = sum(counts.values())
    header = f"{total} props generated  ·  " + "  ·  ".join(f"{'Meshy 7.1' if m == 'meshy' else 'Tripo H3.1'}: {c}" for m, c in sorted(counts.items()))
    for f in range(n):
        canvas = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(canvas)
        d.text(((W - d.textlength(header, font=hdr)) / 2, 76), header, font=hdr, fill=DIM)
        for i, r in enumerate(pick):
            cx, cy = i % cols, i // cols
            delay = (cx + cy) * 5  # diagonal wave, frames
            t = f - delay
            # 0..48 reference, 48..60 → clay, 60..96 clay, 96..108 → textured, then textured
            stages = [(0, load(r["ref"])), (60, load(r["clay"])), (108, load(r["beauty"]))]
            im = stages[0][1]
            for start, s_im in stages[1:]:
                a = min(max((t - (start - 12)) / 12, 0), 1)
                if a > 0:
                    im = Image.blend(im, s_im, a)
            x, y = gx + cx * (tile + gap), gy + cy * (tile + gap)
            canvas.paste(im, (x, y))
            label = "REF" if t < 54 else ("MESH" if t < 102 else ("TRIPO" if r["model"] != "meshy" else "MESHY"))
            d.text((x + 8, y + tile - 24), label, font=tag, fill=cfg["accent"] if label in ("TRIPO", "MESHY") else DIM)
        canvas.save(frames_dir / f"{f:04d}.png")
    raw = out.with_name(out.stem + "_raw.mp4")
    ff("-framerate", FPS, "-i", frames_dir / "%04d.png", "-c:v", "h264_nvenc", "-preset", "p6", "-cq", "18", "-pix_fmt", "yuv420p", raw)
    dur = n / FPS
    with_caption(["-i", raw], "null", dur, cap, out)
    return dur


def clip(scene, name, out, cap, fallback_s):
    src = ROOT / f"breakdown/{FOLDER[scene]}/clips/{name}.mp4"
    if src.exists():
        dur = duration(src)
        with_caption(["-i", src], f"scale={W}:{H}", dur, cap, out)
    else:
        dur = fallback_s
        with_caption(["-f", "lavfi", "-i", f"color=c=0x222018:s={W}x{H}:d={dur}"], "null", dur, cap, out)
    return dur


def post(cfg, out, cap):
    """Raw render vs graded: a divider sweeps across, raw on the left of it, final on the right."""
    raw, graded = ROOT / cfg["post_raw"], ROOT / cfg["post_graded"]
    dur = 6.0
    ss = 4.0
    sweep = f"(0.85-0.7*(t/{dur}))"  # divider moves from 85% to 15% of the width
    tmp = out.with_name(out.stem + "_raw.mp4")
    ff("-ss", ss, "-t", dur, "-i", raw, "-ss", ss, "-t", dur, "-i", graded, "-filter_complex",
       f"[0:v]{LETTERBOX},setsar=1,format=yuv444p[a];[1:v]{LETTERBOX},setsar=1,format=yuv444p[b];"
       f"[a][b]blend=all_expr='if(lt(X,W*{sweep.replace('t/', 'T/')}),A,B)'[o];"
       f"color=c=white:s=3x804:d={dur}[ln];[o][ln]overlay=x='W*{sweep}-1':y=138:eval=frame,format=yuv420p",
       "-c:v", "h264_nvenc", "-preset", "p6", "-cq", "18", tmp)
    with_caption(["-i", tmp], "null", dur, cap, out)
    return dur


def final(cfg, out, cap):
    parts = [ROOT / p for p in cfg["finals"]]
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts))
    joined = out.with_name(out.stem + "_j.mp4")
    ff("-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined)
    dur = duration(joined)
    with_caption(["-i", joined], LETTERBOX, dur, cap, out)
    return dur


def main():
    scene = sys.argv[1]
    only = None
    if "--only" in sys.argv:
        only = set(sys.argv[sys.argv.index("--only") + 1].split(","))
    cfg = SCENES[scene]
    seg = ROOT / f"breakdown/{FOLDER[scene]}/seg"
    seg.mkdir(parents=True, exist_ok=True)
    rows, counts = prop_list(scene)
    total = sum(counts.values())
    ac = cfg["accent"]
    plan = [
        ("title", lambda o, c: title_card(cfg, o), None),
        ("concept", lambda o, c: concept(cfg, o, c), ("01", "Concept", "GPT Image 2.5 night references set the mood, palette and the props to make")),
        ("a_layout", lambda o, c: clip(scene, "a_layout", o, c, 6), ("02", "Layout", "The room is blocked out in Blender from a Python script: walls, counter, shelving, window")),
        ("assets", lambda o, c: assets(cfg, scene, o, c), ("03", "Props", f"Each prop: an image reference, then a 3D mesh from Tripo H3.1 or Meshy 7.1, the better one picked by eye")),
        ("b_props", lambda o, c: clip(scene, "b_props", o, c, 10), ("04", "Set dressing", f"{total} generated props placed by script, then checked for collisions and floating")),
        ("c_materials", lambda o, c: clip(scene, "c_materials", o, c, 6), ("05", "Materials and grime", "The generated textures, then wear, stains, decals and signage layered on top")),
        ("d_lighting", lambda o, c: clip(scene, "d_lighting", o, c, 10), ("06", "Lighting", "Practical lamps first, then signage and the street, fills last, then haze and steam")),
        ("post", lambda o, c: post(cfg, o, c), ("07", "Post", "Left: the raw Cycles render. Right: lens distortion, dispersion, glare, grade and grain")),
        ("final", lambda o, c: final(cfg, o, c), ("08", "Final", f"Handheld walk camera, Cycles at {cfg['res']}")),
        ("end", lambda o, c: title_card(cfg, o, end=True), None),
    ]
    durs = {}
    dur_file = seg / "durations.json"
    if dur_file.exists():
        durs = json.loads(dur_file.read_text())
    for i, (name, fn, capt) in enumerate(plan):
        out = seg / f"{i:02d}_{name}.mp4"
        if only and name not in only and out.exists():
            durs.setdefault(name, duration(out))
            continue
        cap = seg / f"{i:02d}_{name}_cap.png"
        if capt:
            caption_png(cap, *capt, ac)
        print(f"segment {name}", flush=True)
        durs[name] = fn(out, cap)
    dur_file.write_text(json.dumps(durs, indent=1))

    # Join with crossfades.
    names = [n for n, _, _ in plan]
    inputs, chain, offset = [], [], 0.0
    for i, n in enumerate(names):
        inputs += ["-i", seg / f"{i:02d}_{n}.mp4"]
    prev = "[0:v]"
    offset = durs[names[0]] - XF
    for i in range(1, len(names)):
        lbl = f"[x{i}]"
        chain.append(f"{prev}[{i}:v]xfade=transition=fade:duration={XF}:offset={offset:.3f}{lbl}")
        prev = lbl
        offset += durs[names[i]] - XF
    out = ROOT / f"breakdown/{FOLDER[scene]}/{scene}_bts.mp4"
    ff(*inputs, "-filter_complex", ";".join(chain), "-map", prev, "-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq",
       "-rc", "vbr", "-b:v", "12M", "-maxrate", "18M", "-bufsize", "24M", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out)
    print(f"wrote {out} ({duration(out):.1f} s)")


if __name__ == "__main__":
    main()
