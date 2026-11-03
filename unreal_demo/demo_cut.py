""""I solved Blender -> Unreal": the HK dai pai dong, same camera moves in Cycles and in Unreal, with wipes.

    uv run --python 3.13 --with pillow --with numpy python -I unreal_demo/demo_cut.py [--only s1_street_crane,...]

Inputs: the graded Cycles shots (scenes/hk-dai-pai-dong/out/shots/<shot>_graded.mp4) and the Unreal MRQ frames
(unreal_demo/mrq/SEQ_<shot>/####.png, 0-based = Blender frame - 1). Both are 1920x804 at 24 fps and the cameras are
keyed every frame from the same camrig bake, so frame i of one sits on frame i of the other.
Per shot the footage is letterboxed into 1920x1080; a divider at x = p(t) * W shows Unreal left of it and Cycles right
of it (p = 0 all Cycles, 1 all Unreal), eased between keyframes. Labels live in the letterbox bars, never on the image.
Also writes unreal_demo/out/<shot>_ue.mp4 (the Unreal render alone).
Output: breakdown/unreal_demo/unreal_demo.mp4 (house style: assemble.py fonts/colours, xfade, nvenc VBR ~30 Mbps).
"""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("FFMPEG", r"C:\Users\apek-anna\AppData\Local\CapCut\Apps\9.5.0.4050\ffmpeg.exe")
sys.path.insert(0, str(ROOT / "breakdown"))
from assemble import BG, DIM, FF, FPS, H, INK, W, duration, ff, font  # noqa: E402

BRASS = (226, 178, 92)
XF = 0.5
FH = 804
Y0 = (H - FH) // 2  # 138
SEG = ROOT / "breakdown/unreal_demo"
SEG_ENC = ["-an", "-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "15", "-b:v", "0", "-pix_fmt", "yuv420p"]
CYC = ROOT / "scenes/hk-dai-pai-dong/out/shots"
UE = ROOT / "unreal_demo/mrq"

# shot, caption (bottom bar), divider keyframes (t seconds, p)
SHOTS = [
    ("s1_street_crane", "Crane down the street  ·  32 mm  ·  f/4",
     [(0, 0), (1.5, 0), (2.9, 1)]),
    ("h1_walk_in_to_wok", "Handheld walk to the wok  ·  24 mm  ·  one take",
     [(0, 0), (2.4, 0), (3.8, 1), (8.0, 1), (9.2, 0.5), (15.6, 0.5), (16.8, 1)]),
    ("s3_wok_push", "Push in on the wok  ·  35 mm  ·  f/2",
     [(0, 0), (0.7, 0), (2.0, 1)]),
    ("h2_walk_tables_neon", "Walk past the tables to the neon  ·  24 mm  ·  one take",
     [(0, 0), (2.2, 0), (3.6, 1), (7.4, 1), (8.6, 0.5), (13.6, 0.5), (14.8, 1)]),
]


def smooth(a):
    a = min(max(a, 0.0), 1.0)
    return a * a * (3 - 2 * a)


def p_at(keys, t):
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, p0), (t1, p1) in zip(keys, keys[1:]):
        if t <= t1:
            return p0 + (p1 - p0) * smooth((t - t0) / max(t1 - t0, 1e-6))
    return keys[-1][1]


def text_centered(d, y, txt, fnt, fill):
    d.text(((W - d.textlength(txt, font=fnt)) / 2, y), txt, font=fnt, fill=fill)


def still_video(img, secs, out):
    png = out.with_suffix(".png")
    img.save(png)
    ff("-loop", "1", "-t", f"{secs:.3f}", "-i", png, "-vf", f"fps={FPS},format=yuv420p", *SEG_ENC, out)
    return secs


def label_layer(txt, colour, size=30, right=False):
    """RGBA strip (W x Y0) for the top bar with the label left- or right-aligned, a small accent tick before it."""
    im = Image.new("RGBA", (W, Y0), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = font("bahnschrift.ttf", size)
    tw = d.textlength(txt, font=f)
    x = W - 56 - tw if right else 56 + 18
    y = Y0 - 30 - size
    d.rectangle((x - 18, y + 6, x - 12, y + size + 2), fill=colour + (255,))
    d.text((x, y), txt, font=f, fill=colour + (255,))
    return np.asarray(im, np.float32) / 255.0


def bottom_layer(left, right):
    im = Image.new("RGBA", (W, H - Y0 - FH), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = font("segoeuisl.ttf", 26)
    d.text((56, 26), left, font=f, fill=DIM + (255,))
    tw = d.textlength(right, font=f)
    d.text((W - 56 - tw, 26), right, font=f, fill=DIM + (255,))
    return np.asarray(im, np.float32) / 255.0


def comp(dst, layer, alpha):
    if alpha <= 0:
        return
    a = layer[..., 3:4] * alpha
    dst[:] = dst * (1 - a) + layer[..., :3] * 255 * a


def cycles_frames(shot):
    src = CYC / f"{shot}_graded.mp4"
    p = subprocess.Popen([FF, "-v", "error", "-i", str(src), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         stdout=subprocess.PIPE)
    while True:
        b = p.stdout.read(W * FH * 3)
        if len(b) < W * FH * 3:
            break
        yield np.frombuffer(b, np.uint8).reshape(FH, W, 3)
    p.wait()


def ue_only_mp4(shot):
    out = ROOT / f"unreal_demo/out/{shot}_ue.mp4"
    out.parent.mkdir(exist_ok=True)
    ff("-framerate", FPS, "-start_number", 0, "-i", UE / f"SEQ_{shot}/%04d.png", "-vf", "format=yuv420p",
       "-c:v", "h264_nvenc", "-preset", "p7", "-rc", "vbr", "-cq", "16", "-b:v", "0", "-movflags", "+faststart", out)
    return out


def shot_segment(shot, caption, keys, out):
    ue_files = sorted((UE / f"SEQ_{shot}").glob("*.png"))
    lab_ue = label_layer("UNREAL ENGINE 5.8  ·  REAL TIME", BRASS)
    lab_cy = label_layer("BLENDER  ·  CYCLES", INK, right=True)
    bot = bottom_layer(caption, "same camera, keyed every frame  ·  frame-synced")
    enc = subprocess.Popen([FF, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", *SEG_ENC, str(out)], stdin=subprocess.PIPE)
    n = 0
    for i, cy in enumerate(cycles_frames(shot)):
        if i >= len(ue_files):
            raise SystemExit(f"{shot}: Cycles has more frames than Unreal ({len(ue_files)})")
        ue = np.asarray(Image.open(ue_files[i]).convert("RGB"))
        t = i / FPS
        p = p_at(keys, t)
        x = int(round(p * W))
        fr = np.zeros((H, W, 3), np.float32)
        img = cy.astype(np.float32).copy()
        if x > 0:
            img[:, :x] = ue[:, :x]
        if 0 < x < W:
            img[:, max(0, x - 1): x + 2] = BRASS
        fr[Y0: Y0 + FH] = img
        top = fr[:Y0]
        comp(top, lab_ue, smooth(p / 0.3) if p < 1 else 1.0)
        comp(top, lab_cy, smooth((1 - p) / 0.3) if p > 0 else 1.0)
        fade_b = smooth((t - 0.3) / 0.6)
        comp(fr[Y0 + FH:], bot, fade_b)
        enc.stdin.write(fr.clip(0, 255).astype(np.uint8).tobytes())
        n += 1
    enc.stdin.close()
    enc.wait()
    if n != len(ue_files):
        print(f"WARNING {shot}: Cycles {n} frames, Unreal {len(ue_files)}")
    return n / FPS


def blurred(shot, at, dim=0.36):
    png = SEG / f"_bg_{shot}.png"
    ff("-ss", f"{at:.2f}", "-i", CYC / f"{shot}_graded.mp4", "-frames:v", "1", png)
    fr = Image.open(png).convert("RGB")
    c = Image.new("RGB", (W, H), BG)
    c.paste(fr.filter(ImageFilter.GaussianBlur(18)).point(lambda v: int(v * dim)), (0, Y0))
    return c


def title_card(out, secs=3.2):
    c = blurred("s1_street_crane", 2.5)
    d = ImageDraw.Draw(c)
    y = (H - 36 - 30 - 100 - 30 - 34) // 2
    text_centered(d, y, "ANYSCENE", font("bahnschrift.ttf", 34), BRASS)
    text_centered(d, y + 66, "I solved Blender → Unreal", font("segoeuib.ttf", 100), INK)
    text_centered(d, y + 66 + 140, "Any Blender scene, converted automatically. Real time.", font("segoeuisl.ttf", 36), DIM)
    return still_video(c, secs, out)


def stats_card(out, secs=5.0):
    c = blurred("h2_walk_tables_neon", 12.0, 0.30)
    d = ImageDraw.Draw(c)
    rows = [
        ("732 objects  ·  42 lights", "every material, camera and light converted"),
        ("56 fps at 1440p", "RTX 5070 Ti  ·  17.9 ms frame time  ·  Lumen + Nanite, project defaults"),
        ("Built headless. One command.", "Blender scene in, Unreal level out."),
    ]
    big, small = font("segoeuib.ttf", 64), font("segoeuisl.ttf", 32)
    block = 64 + 32 + 32
    gap = 70
    y = (H - (3 * block + 2 * gap)) // 2
    for head, sub in rows:
        text_centered(d, y, head, big, INK)
        text_centered(d, y + 64 + 32, sub, small, DIM)
        y += block + gap
    return still_video(c, secs, out)


def end_card(out, secs=3.8):
    c = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(c)
    y = (H - 100 - 40 - 36) // 2
    text_centered(d, y, "AnyScene → Unreal", font("segoeuib.ttf", 100), INK)
    text_centered(d, y + 140, "Blender in. Real-time level out. Same shot, both engines.", font("bahnschrift.ttf", 36), BRASS)
    return still_video(c, secs, out)


def xfade_join(parts, final):
    inputs, chain = [], []
    for p, _ in parts:
        inputs += ["-i", p]
    prev, offset = "[0:v]", parts[0][1]
    for i in range(1, len(parts)):
        lbl = f"[x{i}]"
        chain.append(f"{prev}[{i}:v]xfade=transition=fade:duration={XF}:offset={offset - XF:.3f}{lbl}")
        offset += parts[i][1] - XF
        prev = lbl
    chain.append(f"{prev}fade=t=in:st=0:d=0.4,fade=t=out:st={offset - 0.8:.3f}:d=0.8[vout]")
    ff(*inputs, "-filter_complex", ";".join(chain), "-map", "[vout]", "-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq",
       "-multipass", "fullres", "-rc", "vbr", "-b:v", "30M", "-maxrate", "36M", "-bufsize", "48M", "-pix_fmt", "yuv420p",
       "-r", str(FPS), "-movflags", "+faststart", final)
    return offset


def main():
    SEG.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else None
    parts = [(SEG / "_title.mp4", title_card(SEG / "_title.mp4"))]
    for shot, cap, keys in SHOTS:
        out = SEG / f"_shot_{shot}.mp4"
        if only is None or shot in only or not out.exists():
            ue_only_mp4(shot)
            d = shot_segment(shot, cap, keys, out)
            print(f"segment {shot} {d:.2f} s", flush=True)
        parts.append((out, duration(out)))
    parts.append((SEG / "_stats.mp4", stats_card(SEG / "_stats.mp4")))
    parts.append((SEG / "_end.mp4", end_card(SEG / "_end.mp4")))
    final = SEG / "unreal_demo.mp4"
    total = xfade_join(parts, final)
    print(f"{final}  {total:.1f} s, {len(parts)} parts")


if __name__ == "__main__":
    main()
