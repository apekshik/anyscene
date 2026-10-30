"""One combined video for posting: both scenes' hero shots with each scene's breakdown cut in between.

    uv run --with pillow python -I breakdown/promo.py

Order: repair h1 (with a name tag) → repair breakdown → repair h2 → s3 bokeh close-up →
       ramen h1 (name tag) → ramen breakdown → ramen h2 → end card.
The breakdown reuses the captioned BTS segments from breakdown/<scene>/seg/ (run assemble.py first), sped up or trimmed so
each scene's breakdown runs about 20 s. Writes breakdown/night_shops_promo.mp4 (posting quality) and a _small copy (< 30 MB).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assemble import BG, DIM, FOLDER, FPS, H, INK, LETTERBOX, ROOT, SCENES, W, XF, duration, ff, font  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

OUT = ROOT / "breakdown/promo"
ENC = ["-c:v", "h264_nvenc", "-preset", "p6", "-cq", "18", "-pix_fmt", "yuv420p", "-an"]

# (segment, mode, target seconds): "speed" plays the whole segment faster, "trim" keeps its start.
BREAKDOWN = [
    ("01_concept", "trim", 2.6),
    ("02_a_layout", "speed", 2.6),
    ("03_assets", "speed", 3.6),
    ("04_b_props", "speed", 3.6),
    ("05_c_materials", "speed", 3.0),
    ("06_d_lighting", "speed", 4.4),
    ("07_post", "trim", 3.2),
]

HEROES = {
    "repair": {
        "open": "scenes/tokyo-electronics-repair/out/shots/h1_back_to_bench_graded.mp4",
        "close": ["scenes/tokyo-electronics-repair/out/shots/h2_shop_walkaround_graded.mp4", "scenes/tokyo-electronics-repair/out/shots/s3_bench_rack_100_graded.mp4"],
    },
    "ramen": {
        "open": "scenes/tokyo-ramen-shop/out/shots/h1_door_to_counter/h1_door_to_counter_graded.mp4",
        "close": ["scenes/tokyo-ramen-shop/out/shots/h2_counter_walkaround/h2_counter_walkaround_graded.mp4"],
    },
}


def tag_png(path, kicker, title, accent):
    """Lower-left name tag in the bottom letterbox bar."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((96, H - 118), kicker.upper(), font=font("bahnschrift.ttf", 24), fill=accent + (255,))
    d.text((96, H - 88), title, font=font("segoeuib.ttf", 40), fill=INK + (255,))
    img.save(path)


def hero(src, out, tag=None):
    if tag:
        fade = "fade=t=in:st=0.6:d=0.6:alpha=1,fade=t=out:st=4.2:d=0.6:alpha=1"
        ff("-i", ROOT / src, "-loop", "1", "-i", tag, "-filter_complex",
           f"[0:v]{LETTERBOX},fps={FPS},setsar=1,format=yuv420p[v];[1:v]format=rgba,{fade}[c];[v][c]overlay=0:0:shortest=1,format=yuv420p",
           *ENC, out)
    else:
        ff("-i", ROOT / src, "-vf", f"{LETTERBOX},fps={FPS},setsar=1,format=yuv420p", *ENC, out)
    return duration(out)


def piece(seg, mode, target, out):
    src_dur = duration(seg)
    if mode == "speed":
        vf = f"setpts=PTS*{target / src_dur:.5f},fps={FPS}"
        ff("-i", seg, "-vf", f"{vf},format=yuv420p", "-t", f"{target:.3f}", *ENC, out)
    else:
        ff("-ss", "0.2", "-t", f"{target:.3f}", "-i", seg, "-vf", f"fps={FPS},format=yuv420p", *ENC, out)
    return duration(out)


def end_card(out):
    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)
    lines = [("segoeuib.ttf", 72, INK, "Night Shops"),
             ("segoeuisl.ttf", 34, DIM, "Two scenes · 160 generated props · no hand modelling"),
             ("segoeuisl.ttf", 30, DIM, "GPT Image 2.5 → Tripo H3.1 / Meshy 7.1 on fal → Blender, scripted by AI agents")]
    y = (H - sum(s + 30 for _, s, _, _ in lines)) // 2
    for f, s, c, t in lines:
        fnt = font(f, s)
        d.text(((W - d.textlength(t, font=fnt)) / 2, y), t, font=fnt, fill=c)
        y += s + 30
    png = out.with_suffix(".png")
    canvas.save(png)
    ff("-loop", "1", "-t", "3.5", "-i", png, "-vf", f"fps={FPS},format=yuv420p", *ENC, out)
    return 3.5


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    parts = []  # (path, seconds, crossfade into this part?)
    for scene in ("repair", "ramen"):
        cfg, h = SCENES[scene], HEROES[scene]
        tag = OUT / f"{scene}_tag.png"
        tag_png(tag, cfg["kicker"], cfg["title"], cfg["accent"])
        p = OUT / f"{scene}_0_open.mp4"
        parts.append((p, hero(h["open"], p, tag), True))
        for seg, mode, target in BREAKDOWN:
            p = OUT / f"{scene}_1_{seg}.mp4"
            parts.append((p, piece(ROOT / f"breakdown/{FOLDER[scene]}/seg/{seg}.mp4", mode, target, p), True))
        # Back-to-back closing heroes hard-cut (like the handheld reel): join them first with a stream copy,
        # since xfade won't chain after a filter concat.
        closes = []
        for i, src in enumerate(h["close"]):
            p = OUT / f"{scene}_2_close{i}.mp4"
            hero(src, p)
            closes.append(p)
        p = OUT / f"{scene}_2_close.mp4"
        lst = OUT / f"{scene}_close.txt"
        lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in closes))
        ff("-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", p)
        parts.append((p, duration(p), True))
    p = OUT / "end.mp4"
    parts.append((p, end_card(p), True))

    inputs, chain = [], []
    for p, _, _ in parts:
        inputs += ["-i", p]
    prev, offset = "[0:v]", parts[0][1]
    for i in range(1, len(parts)):
        lbl = f"[x{i}]"
        chain.append(f"{prev}[{i}:v]xfade=transition=fade:duration={XF}:offset={offset - XF:.3f}{lbl}")
        offset += parts[i][1] - XF
        prev = lbl
    final = ROOT / "breakdown/night_shops_promo.mp4"
    ff(*inputs, "-filter_complex", ";".join(chain), "-map", prev, "-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq",
       "-rc", "vbr", "-b:v", "14M", "-maxrate", "20M", "-bufsize", "28M", "-pix_fmt", "yuv420p", "-movflags", "+faststart", final)
    dur = duration(final)
    small = final.with_name("night_shops_promo_small.mp4")
    kbps = int(28 * 8 * 1000 / dur)  # ~28 MB
    ff("-i", final, "-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq", "-multipass", "fullres", "-rc", "vbr",
       "-b:v", f"{kbps}k", "-maxrate", f"{int(kbps * 1.4)}k", "-bufsize", f"{kbps * 2}k", "-pix_fmt", "yuv420p", "-movflags", "+faststart", small)
    (OUT / "parts.json").write_text(json.dumps([[str(p.name), round(s, 2)] for p, s, _ in parts], indent=1))
    print(f"wrote {final} ({dur:.1f} s) and {small.name}")


if __name__ == "__main__":
    main()
