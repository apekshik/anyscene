"""Contact sheet of labelled images.

uv run --with pillow python -I scenes/hk-dai-pai-dong/scripts/sheet.py OUT.png COLS CELL img1 [img2 ...]
  an img argument may be "label=path"; a row of several images per prop: "label=a.png|b.png|c.png" (rows mode)
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

out, cols, cell = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
items = []
for a in sys.argv[4:]:
    lab, _, p = a.partition("=") if "=" in a else (os.path.basename(a).rsplit(".", 1)[0], "", a)
    items.append((lab, p.split("|")))
per = max(len(p) for _, p in items)
font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", max(12, cell // 16))
if per > 1:  # rows mode: one prop per row
    W, H = per * cell, len(items) * cell
    rows, cw = len(items), per
else:
    rows = (len(items) + cols - 1) // cols
    W, H, cw = cols * cell, rows * cell, cols
sheet = Image.new("RGB", (W, H), (30, 30, 30))
d = ImageDraw.Draw(sheet)
for i, (lab, paths) in enumerate(items):
    for j, p in enumerate(paths):
        x, y = ((j * cell, i * cell) if per > 1 else ((i % cols) * cell, (i // cols) * cell))
        if os.path.exists(p):
            im = Image.open(p).convert("RGB")
            im.thumbnail((cell, cell))
            sheet.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
        else:
            d.text((x + 10, y + cell // 2), "missing", fill=(200, 60, 60), font=font)
        if j == 0:
            d.rectangle((x, y, x + len(lab) * font.size * 0.6 + 8, y + font.size + 6), fill=(0, 0, 0))
            d.text((x + 4, y + 2), lab, fill=(255, 230, 120), font=font)
sheet.save(out)
print("sheet", out, W, H)
