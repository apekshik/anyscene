"""Draw a Plan as a top-down floor plan PNG: walls and openings, labelled footprints (invented items dashed), lights,
and the reference camera with its field of view."""

import math

from PIL import Image, ImageDraw, ImageFont

from schema import Plan

BG = (246, 243, 236)
INK = (40, 38, 34)
WALL = (30, 28, 26)
REF = (52, 98, 160)       # objects seen in the reference
INV = (176, 112, 46)      # invented objects
LIGHT = (232, 170, 30)
CAM = (192, 57, 43)
CAT_FILL = {"structure": 0.10, "furniture": 0.22, "fixture": 0.18, "prop": 0.30, "clutter": 0.12,
            "decal": 0.05, "signage": 0.08}


def _font(size):
    for name in ("arial.ttf", "DejaVuSans.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _dashed(d, pts, fill, width=2, dash=7, gap=5):
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        length = math.hypot(x1 - x0, y1 - y0)
        if length < 1e-6:
            continue
        n = max(1, int(length // (dash + gap)))
        for i in range(n):
            a, b = i * (dash + gap) / length, min(1, (i * (dash + gap) + dash) / length)
            d.line([(x0 + (x1 - x0) * a, y0 + (y1 - y0) * a), (x0 + (x1 - x0) * b, y0 + (y1 - y0) * b)],
                   fill=fill, width=width)


def draw(plan: Plan, path: str, px_per_m: int = 110) -> str:
    r = plan.room
    margin = 140
    W, H = int(r.width * px_per_m + 2 * margin), int(r.depth * px_per_m + 2 * margin + 60)
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img, "RGBA")
    # plan space -> image: x right, y up the page (entrance at the bottom)
    P = lambda x, y: (margin + x * px_per_m, H - margin - 30 - y * px_per_m)

    # grid, 1 m
    for gx in range(int(r.width) + 1):
        d.line([P(gx, 0), P(gx, r.depth)], fill=(225, 220, 210), width=1)
    for gy in range(int(r.depth) + 1):
        d.line([P(0, gy), P(r.width, gy)], fill=(225, 220, 210), width=1)

    # walls (outdoor settings get a light outline)
    wall_w = 7 if plan.setting == "interior" else 3
    corners = [P(0, 0), P(r.width, 0), P(r.width, r.depth), P(0, r.depth)]
    d.line(corners + [corners[0]], fill=WALL, width=wall_w)
    for o in plan.openings:  # gap in the wall + a thin line for its extent
        a, b = o.center - o.width / 2, o.center + o.width / 2
        seg = {"front": (P(a, 0), P(b, 0)), "back": (P(a, r.depth), P(b, r.depth)),
               "left": (P(0, a), P(0, b)), "right": (P(r.width, a), P(r.width, b))}[o.wall]
        d.line(seg, fill=BG, width=wall_w + 2)
        d.line(seg, fill=(120, 150, 190) if o.kind in ("window", "shopfront") else (150, 140, 120), width=2)

    small, mid = _font(13), _font(16)
    # footprints, biggest first so small props draw on top
    for ob in sorted((o for o in plan.objects if o.w > 0 and o.d > 0), key=lambda o: -o.w * o.d):
        col = REF if ob.source == "reference" else INV
        c, s = math.cos(math.radians(ob.rot)), math.sin(math.radians(ob.rot))
        pts = [P(ob.x + dx * c - dy * s, ob.y + dx * s + dy * c)
               for dx, dy in ((-ob.w / 2, -ob.d / 2), (ob.w / 2, -ob.d / 2), (ob.w / 2, ob.d / 2), (-ob.w / 2, ob.d / 2))]
        d.polygon(pts, fill=col + (int(255 * CAT_FILL.get(ob.category, 0.2)),))
        if ob.source == "invented":
            _dashed(d, pts, col)
        else:
            d.polygon(pts, outline=col, width=2)
        # front marker
        centre = P(ob.x, ob.y)
        tip = P(ob.x + s * (ob.d / 2), ob.y - c * (ob.d / 2))
        d.line([centre, tip], fill=col, width=1)
        if ob.category != "structure" and (ob.w * ob.d > 0.25 or ob.category == "fixture"):
            tw = d.textlength(ob.id, font=small)
            d.text((centre[0] - tw / 2, centre[1] - 7), ob.id, font=small, fill=INK)

    for li in plan.lights:
        x, y = P(li.x, li.y)
        rad = {"low": 5, "medium": 7, "high": 9}[li.power]
        d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=LIGHT + (230,), outline=(120, 80, 0), width=1)

    cam = plan.reference_camera
    cx, cy = P(cam.position[0], cam.position[1])
    ang = math.atan2(cam.look_at[1] - cam.position[1], cam.look_at[0] - cam.position[0])
    half = math.atan(18 / cam.lens_mm)
    reach = 2.2 * px_per_m
    for a in (ang - half, ang + half):
        d.line([(cx, cy), (cx + reach * math.cos(a), cy - reach * math.sin(a))], fill=CAM, width=2)
    d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=CAM)
    d.text((cx + 9, cy + 4), f"reference camera {cam.lens_mm:.0f} mm", font=small, fill=CAM)

    # title + legend
    d.text((margin, 24), f"{plan.name}  ·  {r.width:.1f} × {r.depth:.1f} m, {r.height:.1f} m high", font=_font(22), fill=INK)
    lx, ly = margin, 58
    for col, text, dashed in ((REF, "seen in reference", False), (INV, "invented", True)):
        box = [lx, ly, lx + 26, ly + 14]
        d.rectangle(box, fill=col + (60,))
        (_dashed(d, [(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])], col) if dashed
         else d.rectangle(box, outline=col, width=2))
        d.text((lx + 34, ly - 2), text, font=mid, fill=INK)
        lx += 210
    d.ellipse([lx, ly + 1, lx + 12, ly + 13], fill=LIGHT)
    d.text((lx + 20, ly - 2), "light", font=mid, fill=INK)
    d.text((margin, H - 40), "entrance / front ↓     grid = 1 m", font=small, fill=(120, 115, 105))
    img.save(path)
    return path
