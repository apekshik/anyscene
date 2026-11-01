"""AnyKit supercut: five AI-built prop kits in one ~110 s cut, crossfaded, 1920x1080 @ 24 fps.

    uv run --python 3.13 --with pillow python -I breakdown/kit_supercut.py [--check]

Order: open (the five style references -> each wipes to its kit's lineup dolly) -> for each kit a name card, its lineup
dolly, then a grid of six of its turntables (KITS[...]["grid"]) -> end card.

Footage is rendered by breakdown/kit_motion.py into ANYSCENE_RUNS/anykit/motion/run<n>/ (dolly/####.png and
turn/<id>/####.png); item order comes from the kit's kit.json next to it (motion/pkg<n>/out/kit.json).
  ANYSCENE_RUNS    folder holding the endpoint runs            (default ../anyscene-runs)
  FFMPEG           an ffmpeg with h264_nvenc                   (default: CapCut's bundled ffmpeg if found, else ffmpeg)
Cards and captions are drawn with Pillow because that ffmpeg has no drawtext.

Writes breakdown/kit_supercut/anykit_supercut.mp4 (full quality), plus parts.json and, with --check, a contact sheet
and a black/frozen-frame report.
"""

import glob
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if "FFMPEG" not in os.environ:
    capcut = sorted(glob.glob(os.path.expandvars(r"%LOCALAPPDATA%/CapCut/Apps/*/ffmpeg.exe")))
    os.environ["FFMPEG"] = capcut[-1] if capcut else "ffmpeg"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assemble import BG, DIM, FF, FPS, H, INK, W, duration, ff, font  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

RUNS = Path(os.environ.get("ANYSCENE_RUNS", ROOT.parent / "anyscene-runs"))
MOTION = RUNS / "anykit/motion"
OUT = ROOT / "breakdown/kit_supercut"
XF = 0.6  # crossfade, seconds
CARD = 2.6  # name card length, including both crossfades
GRID = 8.0  # the turntable grid: two full 360s of every item in it (the 4 s turntables loop seamlessly)
SEG_ENC = ["-an", "-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "14", "-b:v", "0", "-pix_fmt", "yuv420p"]
BRASS = (226, 178, 92)

KITS = [  # grid: the six items in the kit's turntable grid, in tile order
    dict(n=1, key="orbital", title="Orbital Analysis Desk", place="1970s mission control", accent=(132, 212, 150),
         ref=ROOT / "refs/mission-control-1970s/concept_wide_0.png",
         grid=["line_printer", "crt_monitor", "desk_lamp", "desk_phone", "cigarette_pack", "ashtray"]),
    dict(n=2, key="roussel", title="Maison Roussel Counter", place="Paris bakery", accent=BRASS,
         ref=RUNS / "refs/bakery_0.png",
         grid=["cash_register", "baguette_basket", "brass_scale", "flour_sack", "croissant_tray", "fruit_tart"]),
    dict(n=3, key="ramen", title="Hoshimaru Ramen-ya", place="Tokyo ramen counter", accent=(232, 150, 92),
         ref=ROOT.parent / "blender-scene/refs/ramen/concept_wide_sunburst_0.png",
         grid=["bar_stool", "red_lantern", "stock_pot", "gas_burner", "condiment_caddy", "ramen_bowl"]),
    dict(n=4, key="daipaidong", title="Dai Pai Dong Street Kitchen", place="Hong Kong", accent=(228, 98, 86),
         ref=ROOT / "refs/hk-dai-pai-dong/concept_wide_0.png",
         grid=["gas_cylinder", "plastic_stool", "plastic_crate", "enamel_teapot", "wok", "soy_bottle"]),
    dict(n=5, key="repair", title="Sorano Night Repair Bench", place="Tokyo", accent=(122, 200, 168),
         ref=ROOT.parent / "blender-scene/refs/repair/concept_wide_sunburst_0.png",
         grid=["oscilloscope", "radio_cassette", "vcr_open", "soldering_station", "tool_cup", "solder_spool"]),
]
for k in KITS:  # a kit may name itself: anykit/motion/run<n>/title.txt overrides the default title
    t = MOTION / f"run{k['n']}/title.txt"
    if t.exists():
        k["title"] = t.read_text(encoding="utf-8").strip()


def dolly_files(k):
    return sorted((MOTION / f"run{k['n']}/dolly").glob("*.png"))


def item_ids(k):
    kit = json.loads((MOTION / f"pkg{k['n']}/out/kit.json").read_text(encoding="utf-8"))
    return [it["id"] for it in kit["items"] if (MOTION / f"run{k['n']}/turn/{it['id']}").exists()]


def text_centered(d, y, txt, fnt, fill):
    d.text(((W - d.textlength(txt, font=fnt)) / 2, y), txt, font=fnt, fill=fill)


def still_video(img, secs, out):
    png = out.with_suffix(".png")
    img.save(png)
    ff("-loop", "1", "-t", f"{secs:.3f}", "-i", png, "-vf", f"fps={FPS},format=yuv420p", *SEG_ENC, out)
    return secs


def name_card(k, out):
    """Number and kit name only, over the kit's own lineup, blurred and darkened."""
    files = dolly_files(k)
    fr = Image.open(files[len(files) // 2]).convert("RGB").resize((W, H), Image.LANCZOS)
    canvas = fr.filter(ImageFilter.GaussianBlur(18)).point(lambda v: int(v * 0.22))
    d = ImageDraw.Draw(canvas)
    num = font("bahnschrift.ttf", 30)
    big = font("segoeuib.ttf", 80)
    y = (H - 30 - 30 - 80) // 2
    text_centered(d, y, f"{k['n']:02d} / {len(KITS):02d}", num, k["accent"])
    text_centered(d, y + 60, k["title"], big, INK)
    return still_video(canvas, CARD, out)


def dolly_clip(k, out):
    d = MOTION / f"run{k['n']}/dolly"
    ff("-framerate", FPS, "-i", d / "%04d.png", "-vf", f"scale={W}:{H},setsar=1,format=yuv420p", *SEG_ENC, out)
    return duration(out)


def fit(img, bw, bh):
    """Centre-crop img to bw:bh and resize."""
    r = bw / bh
    w, h = img.size
    if w / h > r:
        nw = int(h * r)
        img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = int(w / r)
        img = img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    return img.resize((bw, bh), Image.LANCZOS)


def grid_clip(k, ids, out):
    """Turntables spinning together: up to 6 as 3 over 2 (tiles cropped to the central square-ish part, where
    kit_motion keeps the item), 4 as 2 over 2 at full 16:9. Rendered frame by frame and piped to ffmpeg."""
    gap, vpad = 10, 56
    if len(ids) > 4:
        cols = 3
        tw = (W - 2 * 40 - gap * (cols - 1)) // cols
        th = (H - 2 * vpad - gap) // 2
    else:
        cols = 2
        th = (H - 2 * vpad - gap) // 2
        tw = th * 16 // 9
    rows = [ids[i:i + cols] for i in range(0, len(ids), cols)]
    slots = []
    for r, row in enumerate(rows):
        x0 = (W - (len(row) * tw + (len(row) - 1) * gap)) // 2
        y0 = (H - (len(rows) * th + (len(rows) - 1) * gap)) // 2
        for c, iid in enumerate(row):
            slots.append((iid, x0 + c * (tw + gap), y0 + r * (th + gap)))
    seqs = {iid: sorted((MOTION / f"run{k['n']}/turn/{iid}").glob("*.png")) for iid in ids}
    n = int(round(GRID * FPS))
    frames = OUT / f"_grid_{k['key']}_{len(ids)}_{ids[0]}"
    frames.mkdir(exist_ok=True)
    for f in range(n):
        png = frames / f"{f:04d}.png"
        if png.exists():
            continue
        fr = Image.new("RGB", (W, H), BG)
        for iid, x, y in slots:
            seq = seqs[iid]
            fr.paste(fit(Image.open(seq[f % len(seq)]).convert("RGB"), tw, th), (x, y))
        fr.save(png, compress_level=1)
    ff("-framerate", FPS, "-i", frames / "%04d.png", "-vf", "format=yuv420p", *SEG_ENC, out)
    return n / FPS


def open_frames(k, w, h, secs):
    """The kit's lineup dolly for its mosaic tile, as a list of PIL frames at FPS. A dolly shorter than secs is
    retimed (nearest frame, slightly slower) to span it, so the tile never freezes on its last frame."""
    files = dolly_files(k)
    n = int(secs * FPS)
    if len(files) < n:
        files = [files[min(len(files) - 1, int(i * len(files) / n))] for i in range(n)]
    cache = {}
    return [cache.setdefault(f, fit(Image.open(f).convert("RGB"), w, h)) for f in files[:n]]


def cold_open(out, secs=12.4):
    """"ANY REFERENCE IN": the five style references as a mosaic (3 over 2, each captioned with its kit), tiles fading
    in one by one. Then each tile wipes left to right to its kit's lineup dolly, already playing, and the header turns
    to "PROP KITS OUT". Text stays above and below the mosaic, never over the images."""
    gap, top, bottom, side, band = 14, 96, 40, 40, 46
    row_h = (H - top - bottom - gap - 2 * band) // 2
    rows = [KITS[:3], KITS[3:]]
    tiles = []  # (kit, x, y, w, h)
    for r, row in enumerate(rows):
        w = (W - 2 * side - gap * (len(row) - 1)) // len(row)
        for c, k in enumerate(row):
            tiles.append((k, side + c * (w + gap), top + r * (row_h + band + gap), w, row_h))
    refs = [fit(Image.open(k["ref"]).convert("RGB"), w, h) for k, _, _, w, h in tiles]
    wipe0, wipe_step, wipe_len = 2.7, 0.22, 0.75
    play = secs - wipe0 + 0.2
    sets = [open_frames(k, w, h, play) for k, _, _, w, h in tiles]
    head = font("bahnschrift.ttf", 40)
    n = int(round(secs * FPS))
    frames = OUT / "_open_frames"
    frames.mkdir(exist_ok=True)

    def ease(a):
        a = min(max(a, 0.0), 1.0)
        return a * a * (3 - 2 * a)

    def mix(c0, c1, a):
        return tuple(int(c0[j] + (c1[j] - c0[j]) * a) for j in range(3))

    for f in range(n):
        t = f / FPS
        fr = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(fr)
        a_in = ease((t - 0.1) / 0.5) * (1 - ease((t - wipe0) / 0.5))
        a_out = ease((t - wipe0 - 0.3) / 0.6)
        if a_in > 0:
            text_centered(d, 30, "ANY REFERENCE IN", head, mix(BG, BRASS, a_in))
        if a_out > 0:
            text_centered(d, 30, "PROP KITS OUT", head, mix(BG, BRASS, a_out))
        for i, ((k, x, y, w, h), ref, clipf) in enumerate(zip(tiles, refs, sets)):
            a = ease((t - 0.25 - i * 0.3) / 0.55)
            if a <= 0:
                continue
            tile = Image.blend(Image.new("RGB", ref.size, BG), ref, a)
            p = ease((t - wipe0 - i * wipe_step) / wipe_len)
            if p > 0:  # the kit's lineup, already moving, slides in from the left over the reference
                st = clipf[min(len(clipf) - 1, max(0, int((t - wipe0 - i * wipe_step) * FPS)))]
                cut = int(w * p)
                tile.paste(st.crop((0, 0, cut, h)), (0, 0))
                if 0 < cut < w:
                    ImageDraw.Draw(tile).line((cut, 0, cut, h), fill=BRASS, width=3)
            fr.paste(tile, (x, y))
            # caption below its own tile, never over the image
            txt, size = f"{k['n']:02d}  {k['title']}".upper(), 26
            while size > 16 and d.textlength(txt, font=font("bahnschrift.ttf", size)) > w - 8:
                size -= 1
            d.text((x + 2, y + h + 10 + (26 - size) // 2), txt, font=font("bahnschrift.ttf", size),
                   fill=mix(BG, INK, a))
        fr.save(frames / f"{f:04d}.png", compress_level=1)
    ff("-framerate", str(FPS), "-i", frames / "%04d.png", "-vf", "format=yuv420p", *SEG_ENC, out)
    return n / FPS


def end_card(out, secs=4.0):
    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)
    text_centered(d, (H - 120) // 2, "AnyKit", font("segoeuib.ttf", 110), INK)
    return still_video(canvas, secs, out)


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
    chain.append(f"{prev}fade=t=in:st=0:d=0.5,fade=t=out:st={offset - 0.8:.3f}:d=0.8[vout]")
    ff(*inputs, "-filter_complex", ";".join(chain), "-map", "[vout]", "-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq",
       "-multipass", "fullres", "-rc", "vbr", "-b:v", "30M", "-maxrate", "45M", "-bufsize", "60M", "-pix_fmt", "yuv420p",
       "-r", str(FPS), "-movflags", "+faststart", final)


def check(final, parts):
    """Contact sheet (frames from every part) + per-part black / frozen report."""
    starts, t = [], 0.0
    for i, (p, d) in enumerate(parts):
        starts.append((p.stem, t, d))
        t += d - (XF if i < len(parts) - 1 else 0)
    thumbs = []
    for name, st, d in starts:
        for frac in (0.25, 0.75) if d > 6 else (0.5,):
            png = OUT / f"_cs_{name}_{frac}.png"
            ff("-ss", f"{st + d * frac:.2f}", "-i", final, "-frames:v", "1", "-vf", "scale=480:-2", png)
            thumbs.append((f"{name} @ {st + d * frac:.1f}s", Image.open(png).convert("RGB")))
    cols = 5
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 480, rows * 300), (0, 0, 0))
    d = ImageDraw.Draw(sheet)
    for i, (lab, im) in enumerate(thumbs):
        x, y = (i % cols) * 480, (i // cols) * 300
        sheet.paste(im, (x, y))
        d.text((x + 8, y + 274), lab, font=font("consola.ttf", 18), fill=(230, 230, 230))
    sheet.save(OUT / "contact_sheet.jpg", quality=88)

    raw = subprocess.run([FF, "-v", "error", "-i", str(final), "-vf", "fps=4,scale=64:36,format=gray", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    n = len(raw) // (64 * 36)
    means, diffs = [], []
    for i in range(n):
        fr = raw[i * 2304:(i + 1) * 2304]
        means.append(sum(fr) / 2304)
        if i:
            prev = raw[(i - 1) * 2304:i * 2304]
            diffs.append(sum(abs(a - b) for a, b in zip(fr, prev)) / 2304)
    report = []
    for name, st, d in starts:
        a, b = int(st * 4), min(int((st + d) * 4), n)
        seg_m = means[a:b]
        seg_d = diffs[a:max(b - 1, a)]
        still_run, run = 0, 0
        for v in seg_d:
            run = run + 1 if v < 0.15 else 0
            still_run = max(still_run, run)
        report.append(dict(part=name, start=round(st, 2), secs=round(d, 2), min_luma=round(min(seg_m), 1),
                           mean_luma=round(sum(seg_m) / len(seg_m), 1), longest_static_s=round(still_run / 4, 2)))
    (OUT / "check.json").write_text(json.dumps(report, indent=1))
    for r in report:
        print(r)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for k in KITS:
        if not dolly_files(k) or not item_ids(k):
            raise SystemExit(f"missing motion for kit {k['n']}: {MOTION / ('run%d' % k['n'])}")
    parts = []
    p = OUT / "00_open.mp4"
    parts.append((p, cold_open(p)))
    for k in KITS:
        i = k["n"]
        p = OUT / f"{i}0_{k['key']}_card.mp4"
        parts.append((p, name_card(k, p)))
        p = OUT / f"{i}1_{k['key']}_dolly.mp4"
        parts.append((p, dolly_clip(k, p)))
        ids = item_ids(k)
        g = [iid for iid in k.get("grid", []) if iid in ids] or ids[:6]
        p = OUT / f"{i}2_{k['key']}_turn.mp4"
        parts.append((p, grid_clip(k, g, p)))
    p = OUT / "90_end.mp4"
    parts.append((p, end_card(p)))

    final = OUT / "anykit_supercut.mp4"
    xfade_join(parts, final)
    (OUT / "parts.json").write_text(json.dumps([[p.name, round(d, 2)] for p, d in parts], indent=1))
    print(f"wrote {final} ({duration(final):.1f} s, {final.stat().st_size / 1e6:.1f} MB)")
    if "--check" in sys.argv:
        check(final, parts)


if __name__ == "__main__":
    main()
