"""Cycles-vs-Unreal comparison sheets: Cycles graded on the left, Unreal on the right, labelled, same height.
    uv run --no-project --with pillow python -I side_by_side.py <cycles_dir> <ue_dir> <out_dir> [street,table,wok]
Reads <cycles_dir>/<cam>_graded.png and <ue_dir>/cam_<cam>.png; writes <out_dir>/<cam>.png and <out_dir>/all.png.
File names are patterns: SBS_CYC="{cam}_graded.png", SBS_UE="cam_{cam}.png" (e.g. SBS_UE="SEQ_{cam}.0000.png" for MRQ).
SBS_CYC_LABEL sets the left label (default "Cycles graded").
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

cyc, ue, out = sys.argv[1:4]
cams = (sys.argv[4] if len(sys.argv) > 4 else "street,table,wok").split(",")
os.makedirs(out, exist_ok=True)
H = 804
LABEL = os.environ.get("SBS_LABEL", "Unreal 5.8 (Lumen)")
CYC_LABEL = os.environ.get("SBS_CYC_LABEL", "Cycles graded")
CYC_FMT = os.environ.get("SBS_CYC", "{cam}_graded.png")
UE_FMT = os.environ.get("SBS_UE", "cam_{cam}.png")
try:
    font = ImageFont.truetype("arial.ttf", 28)
except OSError:
    font = ImageFont.load_default()


def fit(p):
    im = Image.open(p).convert("RGB")
    return im.resize((round(im.width * H / im.height), H), Image.LANCZOS)


rows = []
for c in cams:
    a = fit(os.path.join(cyc, CYC_FMT.format(cam=c)))
    up = os.path.join(ue, UE_FMT.format(cam=c))
    b = fit(up) if os.path.exists(up) else Image.new("RGB", a.size, (60, 0, 0))
    sheet = Image.new("RGB", (a.width + b.width + 8, H), (255, 255, 255))
    sheet.paste(a, (0, 0))
    sheet.paste(b, (a.width + 8, 0))
    d = ImageDraw.Draw(sheet)
    for x, t in ((12, f"{CYC_LABEL}  {c}"), (a.width + 20, f"{LABEL}  {c}")):
        d.rectangle([x - 6, 8, x + 12 + int(d.textlength(t, font=font)), 46], fill=(0, 0, 0))
        d.text((x, 12), t, fill=(255, 255, 255), font=font)
    sheet.save(os.path.join(out, f"{c}.png"))
    rows.append(sheet)
    print("wrote", os.path.join(out, f"{c}.png"))
w = max(r.width for r in rows)
allim = Image.new("RGB", (w, sum(r.height for r in rows) + 8 * (len(rows) - 1)), (255, 255, 255))
y = 0
for r in rows:
    allim.paste(r, (0, y))
    y += r.height + 8
allim.resize((allim.width // 2, allim.height // 2), Image.LANCZOS).save(os.path.join(out, "all.png"))
