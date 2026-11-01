"""Launch supercut: all five AnyScene scenes in one ~75 s cut, crossfaded, 1920x1080 @ 24 fps.

    uv run --python 3.13 --with pillow python -I breakdown/supercut.py [--check]

Order: cold open (the five references) -> for each scene a name card, then one long uncut walkthrough -> end card.
The bakery section opens on the reference -> render wipe from its endpoint hero cut ("one image in").

Footage lives outside this repo (renders are not committed). Point the script at it with:
  ANYSCENE_TOKYO   folder holding the Tokyo scenes' renders   (default ../blender-scene/scenes)
  ANYSCENE_RUNS    folder holding the endpoint runs            (default ../anyscene-runs)
  ANYSCENE_APP     the endpoint's fal app id, shown on the slack end card
  FFMPEG           an ffmpeg with h264_nvenc                   (default: CapCut's bundled ffmpeg if found, else ffmpeg)
Cards and captions are drawn with Pillow because that ffmpeg has no drawtext.

Writes breakdown/supercut/anyscene_supercut_twitter.mp4 (the open-source repo) and _slack.mp4 (the endpoint),
identical but for the end card, full quality,
plus parts.json (segment lengths) and, with --check, a contact sheet and a black/frozen-frame report.
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
from assemble import BG, DIM, FF, FPS, H, INK, LETTERBOX, W, duration, ff, font  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

TOKYO = Path(os.environ.get("ANYSCENE_TOKYO", ROOT.parent / "blender-scene/scenes"))
RUNS = Path(os.environ.get("ANYSCENE_RUNS", ROOT.parent / "anyscene-runs"))
OUT = ROOT / "breakdown/supercut"
XF = 0.6  # crossfade, seconds
CARD = 2.6  # name card length, including both crossfades
SEG_ENC = ["-an", "-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "16", "-b:v", "0", "-pix_fmt", "yuv420p"]
BRASS = (226, 178, 92)


def mc_clips():
    """The hand-built mission control (Apek's pick over the endpoint build): its long uncut handheld walk down the rows."""
    return [(ROOT / "scenes/mission-control-1970s/out/graded/walk_rows.mp4", 0.0, 16.5)]


BAKERY_CLOSEUPS = ["croissant_macro", "tarts_low", "chalkboard", "window_letters", "overhead_vitrine"]


def push_in(img, secs, out):
    """A scouting preview as a slow push-in (Ken Burns), 1920x804 at 24 fps. Upscaled first so zoompan moves smoothly."""
    if not out.exists():
        n = int(round(secs * FPS))
        ff("-loop", "1", "-i", img, "-vf",
           f"scale=3840:-2:flags=lanczos,zoompan=z='1+0.07*on/{n}':d={n}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
           f":s=1920x804:fps={FPS}", "-frames:v", n, *SEG_ENC, out)
    return out


def bakery_clips():
    """The walkthrough, the pastry push, then the scouting previews' close-ups as slow push-ins."""
    # the walk only while it is in the shop: from 4 s it turns toward the bakehouse
    clips = [(RUNS / "bakery_walk_2/walkthrough.mp4", 0.0, 4.0), (RUNS / "bakery_walk_2/pastry_push.mp4", 0.0, 10.0)]
    pv = RUNS / "fal_bakery_1/pkg/out/previews"
    OUT.mkdir(parents=True, exist_ok=True)
    for name in BAKERY_CLOSEUPS:
        src = pv / f"pv_{name}.png"
        if src.exists():
            clips.append((push_in(src, 2.6, OUT / f"_pv_{name}.mp4"), 0.0, 2.6))
    return clips


SCENES = [
    dict(key="bakery", kicker="Paris · present day", title="Maison Roussel, a bakery",
         line="One reference image in. No human input. Under two hours, start to finish.", accent=BRASS,
         ref=RUNS / "refs/bakery_0.png",
         clips=bakery_clips(), tile_clip=1),
    dict(key="mc", kicker="Launch centre · 1970s", title="Mission control",
         line="03:40 on a long shift. Green phosphor, cigarette haze, a floodlit pad outside.", accent=(132, 212, 150),
         ref=ROOT / "refs/mission-control-1970s/concept_wide_0.png",
         clips=mc_clips()),
    dict(key="repair", kicker="Tokyo · present day", title="Electronics repair shop",
         line="1 AM, rain on the glass. 86 generated props, none modelled by hand.", accent=(122, 200, 168),
         ref=TOKYO.parent / "refs/repair/concept_wide_sunburst_0.png",
         clips=[(TOKYO / "repair/out/shots/h2_shop_walkaround_graded.mp4", 0.4, 12.0)]),
    dict(key="ramen", kicker="Tokyo · present day", title="Ramen shop",
         line="Last orders. Through the noren to a counter of steam and clutter.", accent=(232, 150, 92),
         ref=TOKYO.parent / "refs/ramen/concept_wide_sunburst_0.png",
         clips=[(TOKYO / "ramen/out/shots/h1_door_to_counter/h1_door_to_counter_graded.mp4", 0.0, 11.0)],
         tile_ss=5.0, tile_slow=1.65),
    dict(key="hk", kicker="Hong Kong · present day", title="Dai pai dong",
         line="An open-air street kitchen at 1:30 AM, just after the rain.", accent=(228, 98, 86),
         ref=ROOT / "refs/hk-dai-pai-dong/concept_wide_0.png",
         clips=[(ROOT / "scenes/hk-dai-pai-dong/out/shots/h1_walk_in_to_wok_graded.mp4", 7.5, 12.5)]),
]


def text_centered(d, y, txt, fnt, fill):
    d.text(((W - d.textlength(txt, font=fnt)) / 2, y), txt, font=fnt, fill=fill)


def blurred_frame(src, at, dim=0.38):
    """One frame of src, letterboxed onto the card background, blurred and darkened."""
    png = OUT / f"_bg_{Path(src).stem}_{at:.1f}.png"
    ff("-ss", f"{at:.2f}", "-i", src, "-frames:v", "1", "-vf", f"scale={W}:-2", png)
    fr = Image.open(png).convert("RGB")
    canvas = Image.new("RGB", (W, H), BG)
    canvas.paste(fr.filter(ImageFilter.GaussianBlur(16)).point(lambda v: int(v * dim)), (0, (H - fr.height) // 2))
    return canvas


def still_video(img, secs, out):
    png = out.with_suffix(".png")
    img.save(png)
    ff("-loop", "1", "-t", f"{secs:.3f}", "-i", png, "-vf", f"fps={FPS},format=yuv420p", *SEG_ENC, out)
    return secs


def name_card(i, s, out):
    src, ss, t = s["clips"][s.get("card_bg", 0)]
    canvas = blurred_frame(src, ss + t * 0.5)
    d = ImageDraw.Draw(canvas)
    k = font("bahnschrift.ttf", 30)
    num = f"{i + 1:02d} / 05"
    lines = [(k, s["accent"], f"{num}   {s['kicker'].upper()}"), (font("segoeuib.ttf", 80), INK, s["title"])]
    gaps = [30, 0]
    y = (H - 30 - 80) // 2
    for (fnt, col, txt), g in zip(lines, gaps):
        text_centered(d, y, txt, fnt, col)
        y += g
    return still_video(canvas, CARD, out)


def clip(src, ss, t, out, hold=0.0):
    """One stretch of footage, letterboxed to 1920x1080; hold freezes its first frame for that many extra seconds."""
    vf = f"{LETTERBOX},fps={FPS},setsar=1,format=yuv420p"
    if hold:
        vf = f"tpad=start_duration={hold}:start_mode=clone,{vf}"
    ff("-ss", f"{ss:.3f}", "-t", f"{t:.3f}", "-i", src, "-vf", vf, *SEG_ENC, out)
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


def set_frames(sc, w, h, secs):
    """The scene's own footage for its mosaic tile: secs of its first clip from the start, cropped to the tile
    (letterbox bars removed), as a list of PIL frames at FPS."""
    src, ss, t = sc["clips"][sc.get("tile_clip", 0)]
    ss = sc.get("tile_ss", ss)  # where in the clip the tile's few seconds start, if not at the clip start
    d = OUT / f"_tile_{sc['key']}"
    if not d.exists() or len(list(d.glob("*.png"))) < int(secs * FPS):
        d.mkdir(exist_ok=True)
        slow = sc.get("tile_slow", 1.0)  # stretch a short good stretch to fill the mosaic (slow motion)
        ff("-ss", ss, "-t", secs / slow, "-i", src, "-vf", f"setpts={slow}*PTS,fps={FPS}", d / "%04d.png")
    files = sorted(d.glob("*.png"))[: int(secs * FPS)]
    first = Image.open(files[0]).convert("RGB")
    bbox = first.point(lambda v: 255 if v > 12 else 0).convert("L").getbbox() or (0, 0, *first.size)
    return [fit(Image.open(f).convert("RGB").crop(bbox), w, h) for f in files]


def cold_open(out, secs=12.4):
    """"ANY REFERENCE IN": the five references as a mosaic (3 over 2, each captioned with its place), tiles fading in
    one by one. Then each tile wipes left to right to its finished set, already playing, and the header turns to
    "BLENDER SETS OUT"; all five keep playing for 8 s after the last wipe lands.
    Text stays above and below the mosaic, never over it. Rendered frame by frame and piped to ffmpeg."""
    gap, top, bottom, side = 14, 96, 84, 40
    row_h = (H - top - bottom - gap) // 2
    rows = [SCENES[:3], SCENES[3:]]
    tiles = []  # (scene, x, y, w, h)
    for r, row in enumerate(rows):
        w = (W - 2 * side - gap * (len(row) - 1)) // len(row)
        for c, sc in enumerate(row):
            tiles.append((sc, side + c * (w + gap), top + r * (row_h + gap), w, row_h))
    refs = [fit(Image.open(sc["ref"]).convert("RGB"), w, h) for sc, _, _, w, h in tiles]
    wipe0, wipe_step, wipe_len = 2.7, 0.22, 0.75  # tile i wipes from wipe0 + i * wipe_step, over wipe_len
    play = secs - wipe0 + 0.2
    sets = [set_frames(sc, w, h, play) for sc, _, _, w, h in tiles]
    head = font("bahnschrift.ttf", 40)
    small = font("segoeuisl.ttf", 30)
    n = int(round(secs * FPS))
    frames = OUT / "_open_frames"
    frames.mkdir(exist_ok=True)

    def ease(a):
        a = min(max(a, 0.0), 1.0)
        return a * a * (3 - 2 * a)

    def mix(c0, c1, a):
        return tuple(int(c0[j] + (c1[j] - c0[j]) * a) for j in range(3))

    def centred(d, y, txt, fnt, fill):
        d.text(((W - d.textlength(txt, font=fnt)) / 2, y), txt, font=fnt, fill=fill)

    for f in range(n):
        t = f / FPS
        fr = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(fr)
        # header: ANY REFERENCE IN -> BLENDER SETS OUT, crossfading as the wipes start
        a_in = ease((t - 0.1) / 0.5) * (1 - ease((t - wipe0) / 0.5))
        a_out = ease((t - wipe0 - 0.3) / 0.6)
        if a_in > 0:
            centred(d, 30, "ANY REFERENCE IN", head, mix(BG, BRASS, a_in))
        if a_out > 0:
            centred(d, 30, "BLENDER SETS OUT", head, mix(BG, BRASS, a_out))
        for i, ((sc, x, y, w, h), ref, clipf) in enumerate(zip(tiles, refs, sets)):
            a = ease((t - 0.25 - i * 0.3) / 0.55)
            if a <= 0:
                continue
            tile = Image.blend(Image.new("RGB", ref.size, BG), ref, a)
            p = ease((t - wipe0 - i * wipe_step) / wipe_len)
            if p > 0:  # the finished set, already playing, slides in from the left over the reference
                st = clipf[min(len(clipf) - 1, max(0, int((t - wipe0 - i * wipe_step) * FPS)))]
                cut = int(w * p)
                tile.paste(st.crop((0, 0, cut, h)), (0, 0))
                if 0 < cut < w:
                    ImageDraw.Draw(tile).line((cut, 0, cut, h), fill=BRASS, width=3)
            fr.paste(tile, (x, y))
            band = Image.new("RGB", (w, 44), (0, 0, 0))
            fr.paste(Image.blend(fr.crop((x, y + h - 44, x + w, y + h)), band, 0.55 * a), (x, y + h - 44))
            txt, size = f"{sc['title']}  ·  {sc['kicker']}".upper(), 26
            while size > 16 and d.textlength(txt, font=font("bahnschrift.ttf", size)) > w - 32:
                size -= 1  # keep the caption inside its own tile
            d.text((x + 16, y + h - 37 + (26 - size) // 2), txt, font=font("bahnschrift.ttf", size), fill=mix(BG, INK, a))
        fr.save(frames / f"{f:04d}.png", compress_level=1)
    ff("-framerate", str(FPS), "-i", frames / "%04d.png", "-vf", "format=yuv420p", *SEG_ENC, out)
    return n / FPS


# The slack end card names the endpoint: ANYSCENE_APP=<your-fal-username>/anyscene (the app the builder runs as).
ENDPOINT = (os.environ.get("ANYSCENE_APP", "").strip().strip("/") or "<your-fal-username>/anyscene") + "/ref2scene"
END_CARDS = {  # the only difference between the versions
    "twitter": [(font("segoeuib.ttf", 96), INK, "AnyScene", 128),
                (font("bahnschrift.ttf", 36), BRASS, "OPEN SOURCE  ·  github.com/apekshik/anyscene", 92),
                (font("segoeuisl.ttf", 30), DIM, "Build your own worlds with Claude Code, Blender and fal.", 0)],
    "slack": [(font("segoeuib.ttf", 96), INK, "AnyScene", 128),
              (font("bahnschrift.ttf", 36), BRASS, ENDPOINT, 92),
              (font("segoeuisl.ttf", 30), DIM, "Reference images in, a production-ready 3D set out. Fully automated.", 0)],
}


def end_card(out, version, secs=5.0):
    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)
    lines = END_CARDS[version]
    y = (H - sum(g for *_, g in lines) - 30) // 2
    for fnt, col, txt, g in lines:
        text_centered(d, y, txt, fnt, col)
        y += g
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
       "-multipass", "fullres", "-rc", "vbr", "-b:v", "24M", "-maxrate", "36M", "-bufsize", "48M", "-pix_fmt", "yuv420p",
       "-r", str(FPS), "-movflags", "+faststart", final)


def check(final, parts):
    """Contact sheet (one frame from the middle of every part) + per-second black / frozen report."""
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
    cols = 4
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 480, rows * 300), (0, 0, 0))
    d = ImageDraw.Draw(sheet)
    for i, (lab, im) in enumerate(thumbs):
        x, y = (i % cols) * 480, (i // cols) * 300
        sheet.paste(im, (x, y))
        d.text((x + 8, y + 274), lab, font=font("consola.ttf", 18), fill=(230, 230, 230))
    sheet.save(OUT / "contact_sheet.jpg", quality=88)

    # 4 fps greyscale 64x36 samples: mean luma (black) and frame-to-frame change (frozen)
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
    parts = []
    p = OUT / "00_open.mp4"
    parts.append((p, cold_open(p)))
    for i, s in enumerate(SCENES):
        p = OUT / f"{i + 1}0_{s['key']}_card.mp4"
        parts.append((p, name_card(i, s, p)))
        for j, (src, ss, t) in enumerate(s["clips"]):
            if not Path(src).exists():
                raise SystemExit(f"missing footage: {src}")
            p = OUT / f"{i + 1}{j + 1}_{s['key']}_clip.mp4"
            parts.append((p, clip(src, ss, t, p, s.get("hold", 0.0) if j == 0 else 0.0)))
    body = list(parts)
    for version in END_CARDS:
        p = OUT / f"90_end_{version}.mp4"
        parts = body + [(p, end_card(p, version))]
        final = OUT / f"anyscene_supercut_{version}.mp4"
        xfade_join(parts, final)
        print(f"wrote {final} ({duration(final):.1f} s, {final.stat().st_size / 1e6:.1f} MB)")
    (OUT / "parts.json").write_text(json.dumps([[p.name, round(d, 2)] for p, d in parts], indent=1))
    if "--check" in sys.argv:
        check(final, parts)


if __name__ == "__main__":
    main()
