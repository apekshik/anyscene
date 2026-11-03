"""Camera-match check: overlay Unreal MRQ frames on the Cycles frames of the same shot.

    uv run --python 3.13 --with pillow --with numpy python -I unreal_demo/check_match.py <shot> [blender_frame ...]

Default frames: 1 and the middle frame. Writes unreal_demo/check/<shot>_f####.png, a 2x2 sheet:
  Cycles | Unreal
  50/50 blend | edges (Cycles red, Unreal cyan; white where they coincide)
and prints an edge-alignment score per frame: the best integer shift (px) between the two edge maps within +-12 px
(0,0 = aligned) and the edge correlation at zero shift vs at the best shift.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
shot = sys.argv[1]
cam = json.load(open(ROOT / f"unreal_demo/cams/{shot}.json"))
n = cam["frames_n"]
frames = [int(x) for x in sys.argv[2:]] or [1, (n + 1) // 2]
OUT = ROOT / "unreal_demo/check"
OUT.mkdir(exist_ok=True)
fnt = ImageFont.truetype("C:/Windows/Fonts/bahnschrift.ttf", 26)


def edges(im):
    g = im.convert("L").filter(ImageFilter.GaussianBlur(1.2)).filter(ImageFilter.FIND_EDGES)
    a = np.asarray(g, np.float32)
    return a / (a.max() + 1e-6)


def corr(a, b):
    a = a - a.mean()
    b = b - b.mean()
    return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9))


for f in frames:
    cy = Image.open(ROOT / f"scenes/hk-dai-pai-dong/out/shots/{shot}/frames/{f:04d}.png").convert("RGB")
    ue = Image.open(ROOT / f"unreal_demo/mrq/SEQ_{shot}/{f - 1:04d}.png").convert("RGB").resize(cy.size)
    ec, eu = edges(cy), edges(ue)
    # Search shifts on a 1/2-res copy, centre region (avoid lens-distorted borders).
    h, w = ec.shape
    c0, c1 = ec[h // 6: -h // 6, w // 6: -w // 6], eu
    best = (-1, 0, 0)
    for dy in range(-12, 13, 2):
        for dx in range(-12, 13, 2):
            s = corr(c0, c1[h // 6 + dy: h - h // 6 + dy, w // 6 + dx: w - w // 6 + dx])
            if s > best[0]:
                best = (s, dx, dy)
    zero = corr(c0, c1[h // 6: h - h // 6, w // 6: w - w // 6])
    print(f"CHECK {shot} f{f}: edge corr at 0 shift {zero:.3f}, best {best[0]:.3f} at dx={best[1]} dy={best[2]} px")
    ov = np.zeros((h, w, 3), np.float32)
    k = 3.0
    ov[..., 0] = np.clip(ec * k, 0, 1)
    ov[..., 1] = np.clip(eu * k, 0, 1)
    ov[..., 2] = np.clip(eu * k, 0, 1)
    ov = np.maximum(ov, np.clip(np.minimum(ec, eu) * k, 0, 1)[..., None])
    tiles = [(cy, "Cycles"), (ue, "Unreal (MRQ)"), (Image.blend(cy, ue, 0.5), "50/50 blend"),
             (Image.fromarray((ov * 255).astype(np.uint8)), f"edges: Cycles red / Unreal cyan  best shift {best[1]},{best[2]} px")]
    tw, th = w // 2, h // 2
    sheet = Image.new("RGB", (tw * 2, th * 2))
    for i, (im, lab) in enumerate(tiles):
        t = im.resize((tw, th), Image.LANCZOS)
        d = ImageDraw.Draw(t)
        d.rectangle((0, 0, d.textlength(lab, font=fnt) + 20, 36), fill=(0, 0, 0))
        d.text((10, 4), lab, font=fnt, fill=(255, 255, 255))
        sheet.paste(t, ((i % 2) * tw, (i // 2) * th))
    p = OUT / f"{shot}_f{f:04d}.png"
    sheet.save(p)
    # Full-res crop of the blend for a close look.
    Image.blend(cy, ue, 0.5).crop((w // 2 - 480, h // 2 - 200, w // 2 + 480, h // 2 + 200)).save(OUT / f"{shot}_f{f:04d}_blendcrop.png")
    print("wrote", p)
