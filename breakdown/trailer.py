"""AnyScene trailer (X, ~70 s) and the anyscene.org hero loop, 1920x1080 @ 24 fps.

    node breakdown/site_rec.mjs http://127.0.0.1:4331 breakdown/trailer/site     # screen recordings of the site first
    uv run --python 3.13 --with pillow python -I breakdown/trailer.py [trailer] [hero] [--check]

Trailer, made to read on a phone in a feed: few words, big and bold, on cards between the footage, never over it.
  ONE IMAGE IN. -> the submarine and the bakery wiping from their reference to the set, the caustic chamber between
  (its reference is a film still, so it is not shown); about 5 s each -> 9 SCENES. -> all nine walkthroughs at once
  -> 5 PROP KITS. -> a kit lineup and turntables -> FREE ON ANYSCENE.ORG -> screen recordings of the site (landing,
  the catalogue, a scene page down to its downloads, a kit) -> end card.
Counts are the catalogue's (anyscene-org/data/catalog.json). Every scene and kit there downloads free (CC BY 4.0).

Hero loop: the three highlights only, no text, no bars (native 2.39:1, 1920x804), crossfaded and seamless (the last
shot crossfades into the first). Web encodes: h264 1080p, HEVC 1080p, h264 960 for phones, and a poster (its first frame).

  ANYSCENE_RUNS    folder holding the endpoint runs and videos (default ../anyscene-runs)
  FFMPEG           an ffmpeg with h264_nvenc                   (default: CapCut's bundled ffmpeg if found, else ffmpeg)

Writes ANYSCENE_RUNS/videos/anyscene_trailer.mp4 and breakdown/trailer/hero/*, plus parts.json and, with --check,
a contact sheet and a black/frozen-frame report per part in breakdown/trailer/.
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
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

RUNS = Path(os.environ.get("ANYSCENE_RUNS", ROOT.parent / "anyscene-runs"))
V = RUNS / "videos"
SUB = RUNS / "shot_submarine"
KIT = ROOT / "breakdown/kit_supercut"  # kit_supercut.py's full-quality segments (lineup dollies, turntable grids)
OUT = ROOT / "breakdown/trailer"
FINAL = V / "anyscene_trailer.mp4"
XF = 0.6  # crossfade, seconds
SEG_ENC = ["-an", "-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "15", "-b:v", "0", "-pix_fmt", "yuv420p"]
BRASS = (226, 178, 92)
BAR = (H - 804) // 2  # letterbox bar height for 2.39:1 footage

# (src, start, secs); a section's first shot carries its title in the bottom bar. Numbers are the catalogue's.
CAUSTIC = dict(kicker="Travertine hall  ·  built in 30 min", title="The Caustic Chamber", shots=[
    (V / "caustic_shots/zoom_out_reveal.mp4", 0.0, 8.0),       # caustics on the travertine, pulling back to the room
    (V / "caustic_shots2/reveal_from_sculpture.mp4", 1.6, 5.4),
    (V / "caustic_shots/rack_desk_chair.mp4", 0.0, 5.5),       # 85 mm rack focus, sculpture to chair
    (V / "caustic_shots2/reveal_from_desk_chair.mp4", 1.8, 5.2),
])
BAKERY = dict(kicker="Paris  ·  1 reference image  ·  48 props", title="Maison Roussel", ref=RUNS / "refs/bakery_0.png",
              shots=[
    (V / "bakery_walkthrough.mp4", 0.0, 4.2),  # the walk only while it is in the shop: from ~4.5 s it heads for the bakehouse
    (V / "bakery_pastry_push.mp4", 1.5, 7.0),
    (V / "bakery_closeup_croissant_macro.mp4", 0.0, 5.0),
    (V / "bakery_closeup_tarts.mp4", 0.5, 5.0),
    (V / "bakery_closeup_window_lettering.mp4", 0.5, 4.5),
])
SUBMARINE = dict(kicker="Control room  ·  1 reference image  ·  36 props", title="Submarine H-27",
                 ref=RUNS / "refs/submarine_0.png", shots=[
    (next(SUB.glob("*_walk_in.mp4")), 0.0, 7.0),
    (next(SUB.glob("*_reveal_depth.mp4")), 0.5, 4.75),
    (next(SUB.glob("*_reveal_sonar.mp4")), 0.0, 5.25),
    (next(SUB.glob("*_reveal_planes.mp4")), 0.0, 5.25),
])
# Unreal Engine section, between the highlights and the kits: Apek's own editor recordings, (src, start, secs) each,
# letterboxed like the rest; the first carries this title. Empty -> no section.
UNREAL = dict(kicker="Same set  ·  Unreal Engine 5.8", title="In Unreal", shots=[])
KITS = [(KIT / "41_daipaidong_dolly.mp4", 0.0, 6.5), (KIT / "12_orbital_turn.mp4", 0.0, 4.0),
        (KIT / "31_ramen_dolly.mp4", 0.0, 6.0)]
HOLD = 1.8  # seconds on the reference before it wipes
WIPE = 1.0

SITE = OUT / "site"  # site_rec.mjs frames, one folder per segment
WALKS = ROOT.parent / "anyscene-org-staging/web/scenes"  # the site's walkthrough encodes, one per scene
BARLOW = ROOT.parent / "anyscene-org/node_modules/@fontsource/barlow-condensed/files/barlow-condensed-latin-800-normal.woff"
GRID = ["caustic-chamber", "submarine-control-room", "mission-control-1970s", "hk-dai-pai-dong", "riad-tea-salon",
        "tokyo-ramen-shop", "tokyo-electronics-repair", "halloway-chemist", "maison-roussel"]
XF_X = 0.4  # the X cut's crossfades: quicker than the reel's

HERO = [  # (src, start, secs) at native 2.39:1; the loop starts (and its poster is) on the first shot
    (V / "bakery_pastry_push.mp4", 2.0, 5.0),
    (V / "caustic_shots/zoom_out_reveal.mp4", 0.5, 5.5),
    (next(SUB.glob("*_walk_in.mp4")), 1.0, 5.0),
    (V / "bakery_closeup_croissant_macro.mp4", 0.5, 4.5),
    (V / "caustic_shots2/reveal_from_desk_chair.mp4", 2.0, 4.5),
    (next(SUB.glob("*_reveal_depth.mp4")), 1.0, 4.25),
]


def ease(a):
    a = min(max(a, 0.0), 1.0)
    return a * a * (3 - 2 * a)


def mix(c0, c1, a):
    return tuple(int(c0[j] + (c1[j] - c0[j]) * a) for j in range(3))


def centred(d, y, txt, fnt, fill):
    d.text(((W - d.textlength(txt, font=fnt)) / 2, y), txt, font=fnt, fill=fill)


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


KICK, TITLE, TOP = font("bahnschrift.ttf", 24), font("segoeuib.ttf", 44), font("bahnschrift.ttf", 30)


def draw_bar_title(d, kicker, title, a):
    """Kicker over title, centred in the bottom letterbox bar, at opacity a (drawn onto a black bar)."""
    if a <= 0:
        return
    centred(d, H - BAR + 20, kicker.upper(), KICK, mix((0, 0, 0), BRASS, a))
    centred(d, H - BAR + 52, title, TITLE, mix((0, 0, 0), INK, a))


def bar_title_png(path, kicker, title, top=None):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    centred(d, H - BAR + 20, kicker.upper(), KICK, BRASS + (255,))
    centred(d, H - BAR + 52, title, TITLE, INK + (255,))
    if top:
        centred(d, (BAR - 30) // 2 - 2, top, TOP, BRASS + (255,))
    img.save(path)


def clip(src, ss, t, out, title=None, letterbox=True):
    """One stretch of footage at 1920x1080 (letterboxed) or native; title=(kicker, title[, top]) fades in the bars."""
    vf = f"{LETTERBOX if letterbox else f'scale={W}:-2:flags=lanczos'},fps={FPS},setsar=1,format=yuv420p"
    if not title:
        ff("-ss", f"{ss:.3f}", "-t", f"{t:.3f}", "-i", src, "-vf", vf, *SEG_ENC, out)
        return duration(out)
    png = out.with_suffix(".title.png")
    bar_title_png(png, *title)
    fade = f"fade=t=in:st=0.7:d=0.6:alpha=1,fade=t=out:st={t - 1.4:.2f}:d=0.6:alpha=1"
    ff("-ss", f"{ss:.3f}", "-t", f"{t:.3f}", "-i", src, "-loop", "1", "-t", f"{t:.3f}", "-i", png, "-filter_complex",
       f"[0:v]{vf}[v];[1:v]format=rgba,{fade}[c];[v][c]overlay=0:0:format=auto,format=yuv420p", *SEG_ENC, out)
    return duration(out)


def wipe_shot(sec, out, shot=None, labels=True, hold=HOLD, wipe=WIPE):
    """The section's reference, letterboxed, with a slow push; then it wipes left to right to the finished set,
    already playing. With labels, top bar: ANY REFERENCE IN -> BLENDER SET OUT; bottom bar: the section title once the
    set is in. Rendered frame by frame with Pillow."""
    HOLD, WIPE = hold, wipe  # noqa: N806 (shadow the defaults for this shot)
    src, ss, t = shot or sec["shots"][0]
    frames = OUT / f"_wipe_{out.stem}"
    src_dir = frames / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    for f in src_dir.glob("*.png"):
        f.unlink()
    ff("-ss", f"{ss:.3f}", "-t", f"{t:.3f}", "-i", src, "-vf", f"scale={W}:804:flags=lanczos,fps={FPS}", src_dir / "%04d.png")
    foot = sorted(src_dir.glob("*.png"))
    ref = fit(Image.open(sec["ref"]).convert("RGB"), W, 804)
    secs = HOLD + t
    n = int(round(secs * FPS))
    for f in range(n):
        tt = f / FPS
        z = 1 + 0.035 * ease(min(tt, HOLD + WIPE) / (HOLD + WIPE))  # push on the reference until it is gone
        cw, chh = int(W / z), int(804 / z)
        r = ref.crop(((W - cw) // 2, (804 - chh) // 2, (W - cw) // 2 + cw, (804 - chh) // 2 + chh)).resize((W, 804), Image.LANCZOS)
        a_ref = ease(tt / 0.5)
        pic = Image.blend(Image.new("RGB", (W, 804), (0, 0, 0)), r, a_ref) if a_ref < 1 else r
        p = ease((tt - HOLD) / WIPE)
        if p > 0:
            st = Image.open(foot[min(len(foot) - 1, int((tt - HOLD) * FPS))]).convert("RGB")
            cut = int(W * p)
            pic.paste(st.crop((0, 0, cut, 804)), (0, 0))
            if cut < W:
                ImageDraw.Draw(pic).line((cut, 0, cut, 804), fill=BRASS, width=3)
        fr = Image.new("RGB", (W, H), (0, 0, 0))
        fr.paste(pic, (0, BAR))
        if not labels:
            fr.save(frames / f"{f:04d}.png", compress_level=1)
            continue
        d = ImageDraw.Draw(fr)
        a_in = ease((tt - 0.2) / 0.5) * (1 - ease((tt - HOLD) / 0.4))
        a_out = ease((tt - HOLD - 0.3) / 0.5) * (1 - ease((tt - HOLD - 3.2) / 0.6))
        ty = (BAR - 30) // 2 - 2
        if a_in > 0:
            centred(d, ty, "ANY REFERENCE IN", TOP, mix((0, 0, 0), BRASS, a_in))
        if a_out > 0:
            centred(d, ty, "BLENDER SET OUT", TOP, mix((0, 0, 0), BRASS, a_out))
        draw_bar_title(d, sec["kicker"], sec["title"], ease((tt - HOLD - WIPE - 0.1) / 0.6) * (1 - ease((tt - secs + 1.4) / 0.6)))
        fr.save(frames / f"{f:04d}.png", compress_level=1)
    ff("-framerate", FPS, "-i", frames / "%04d.png", "-vf", "format=yuv420p", *SEG_ENC, out)
    return n / FPS


def still_video(img, secs, out):
    png = out.with_suffix(".png")
    img.save(png)
    ff("-loop", "1", "-t", f"{secs:.3f}", "-i", png, "-vf", f"fps={FPS},format=yuv420p", *SEG_ENC, out)
    return secs


def big_card(out, lines, secs=1.6):
    """Words only, big and bold (the site's Barlow Condensed 800), centred on the dark ground. lines: [(text, size,
    colour)], a word wrapped in *stars* is drawn in brass."""
    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)
    gap = 28
    y = (H - sum(s for _, s, _ in lines) - gap * (len(lines) - 1)) // 2 - 12
    for text, size, col in lines:
        f = ImageFont.truetype(str(BARLOW), size)
        words = text.split(" ")
        x = (W - d.textlength(text.replace("*", ""), font=f)) / 2
        for i, w in enumerate(words):
            c = BRASS if w.startswith("*") else col
            w = w.strip("*") + (" " if i < len(words) - 1 else "")
            d.text((x, y), w, font=f, fill=c)
            x += d.textlength(w, font=f)
        y += size + gap
    return still_video(canvas, secs, out)


def grid9(out, secs=4.6):
    """All nine scenes' walkthroughs at once, 3 x 3, from the site's own encodes (6 px gaps)."""
    tw, th, g = 636, 356, 6
    inputs, chain = [], []
    for i, slug in enumerate(GRID):
        inputs += ["-ss", "2", "-t", f"{secs:.3f}", "-i", WALKS / slug / "walk.mp4"]
        chain.append(f"[{i}:v]scale={tw}:{th}:force_original_aspect_ratio=increase:flags=lanczos,crop={tw}:{th},setsar=1,fps={FPS}[t{i}]")
    layout = "|".join(f"{(i % 3) * (tw + g)}_{(i // 3) * (th + g)}" for i in range(9))
    chain.append("".join(f"[t{i}]" for i in range(9)) + f"xstack=inputs=9:layout={layout}:fill=0x0e0d0c,format=yuv420p")
    ff(*inputs, "-filter_complex", ";".join(chain), "-t", f"{secs:.3f}", *SEG_ENC, out)
    return duration(out)


def site_clip(name, out):
    """One site_rec.mjs recording (1920x1080 PNG frames) as a segment."""
    ff("-framerate", FPS, "-i", SITE / name / "%04d.png", "-vf", "format=yuv420p", *SEG_ENC, out)
    return duration(out)


def xfade_chain(parts, xf=XF):
    chain, prev, offset = [], "[0:v]", parts[0][1]
    for i in range(1, len(parts)):
        chain.append(f"{prev}[{i}:v]xfade=transition=fade:duration={xf}:offset={offset - xf:.3f}[x{i}]")
        offset += parts[i][1] - xf
        prev = f"[x{i}]"
    return chain, prev, offset


def trailer():
    OUT.mkdir(parents=True, exist_ok=True)
    parts = []

    def add(name, fn):
        p = OUT / f"x{len(parts):02d}_{name}.mp4"
        parts.append((p, fn(p)))
        print(f"  {p.name}: {parts[-1][1]:.2f} s", flush=True)

    big, mid = 210, 120
    add("card_in", lambda p: big_card(p, [("ONE IMAGE IN.", big, INK)], 1.5))
    sub_walk = SUBMARINE["shots"][0][0]
    add("sub_wipe", lambda p: wipe_shot(SUBMARINE, p, (sub_walk, 0.0, 3.6), labels=False, hold=1.1, wipe=0.8))
    add("caustic", lambda p: clip(V / "caustic_shots2/establishing_wide.mp4", 0.5, 4.6, p))
    add("bakery_wipe", lambda p: wipe_shot(BAKERY, p, (V / "bakery_walkthrough.mp4", 0.0, 3.6), labels=False, hold=1.1, wipe=0.8))
    for i, (src, ss, t) in enumerate(UNREAL["shots"]):
        add(f"unreal{i}", lambda p, a=(src, ss, t): clip(*a, p))
    add("card_scenes", lambda p: big_card(p, [("*9* SCENES.", big, INK)], 1.3))
    add("grid", grid9)
    add("card_kits", lambda p: big_card(p, [("*5* PROP KITS.", big, INK)], 1.3))
    add("kit_dolly", lambda p: clip(KIT / "41_daipaidong_dolly.mp4", 0.0, 4.2, p, letterbox=False))
    add("kit_turn", lambda p: clip(KIT / "12_orbital_turn.mp4", 0.0, 3.0, p, letterbox=False))
    add("card_free", lambda p: big_card(p, [("ALL *FREE*", big, INK), ("ANYSCENE.ORG", mid, INK)], 1.9))
    for name in ("home", "scenes", "scene", "kits", "kit"):
        add(f"site_{name}", lambda p, n=name: site_clip(n, p))
    add("end", lambda p: big_card(p, [("ANYSCENE.ORG", big, INK), ("*FREE* BLENDER SCENES + KITS", 78, DIM)], 4.0))

    inputs = [x for p, _ in parts for x in ("-i", p)]
    chain, prev, total = xfade_chain(parts, XF_X)
    chain.append(f"{prev}fade=t=in:st=0:d=0.5,fade=t=out:st={total - 0.8:.3f}:d=0.8[vout]")
    ff(*inputs, "-filter_complex", ";".join(chain), "-map", "[vout]", "-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq",
       "-multipass", "fullres", "-rc", "vbr", "-b:v", "24M", "-maxrate", "36M", "-bufsize", "48M", "-pix_fmt", "yuv420p",
       "-r", str(FPS), "-movflags", "+faststart", FINAL)
    (OUT / "parts.json").write_text(json.dumps([[p.name, round(d, 2)] for p, d in parts], indent=1))
    print(f"wrote {FINAL} ({duration(FINAL):.1f} s, {FINAL.stat().st_size / 1e6:.1f} MB)")
    return parts


def hero():
    """Seamless loop: shot 1 from XF on, the rest crossfaded, then the last shot crossfades into shot 1's first XF
    seconds, so the last frame runs straight into the first."""
    d = OUT / "hero"
    d.mkdir(parents=True, exist_ok=True)
    parts = []
    for i, (src, ss, t) in enumerate(HERO):
        p = d / f"_h{i}.mp4"
        parts.append((p, clip(src, ss, t, p, letterbox=False)))
    first, d0 = parts[0]
    head, tail = d / "_h0_tail.mp4", d / "_h0_head.mp4"
    ff("-ss", f"{XF:.3f}", "-i", first, "-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "15", head)
    ff("-t", f"{XF:.3f}", "-i", first, "-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "15", tail)
    seq = [(head, duration(head))] + parts[1:] + [(tail, XF)]
    inputs = [x for p, _ in seq for x in ("-i", p)]
    chain, prev, total = xfade_chain(seq)
    master = d / "_hero_master.mp4"
    ff(*inputs, "-filter_complex", ";".join(chain), "-map", prev, *SEG_ENC, "-r", str(FPS), master)
    web = ["-an", "-pix_fmt", "yuv420p", "-r", str(FPS), "-g", "48", "-movflags", "+faststart"]
    nv = ["-preset", "p7", "-tune", "hq", "-multipass", "fullres", "-rc", "vbr"]
    outs = {
        "hero_1080.mp4": ["-c:v", "h264_nvenc", *nv, "-b:v", "1.9M", "-maxrate", "3.2M", "-bufsize", "4M", "-profile:v", "high"],
        "hero_1080_hevc.mp4": ["-c:v", "hevc_nvenc", *nv, "-b:v", "1.2M", "-maxrate", "2.2M", "-bufsize", "3M", "-tag:v", "hvc1"],
        "hero_960.mp4": ["-vf", "scale=960:-2:flags=lanczos", "-c:v", "h264_nvenc", *nv, "-b:v", "0.75M", "-maxrate", "1.3M",
                         "-bufsize", "1.6M", "-profile:v", "high"],
    }
    for name, enc in outs.items():
        ff("-i", master, *enc, *web, d / name)
        print(f"  {name}: {duration(d / name):.2f} s, {(d / name).stat().st_size / 1e6:.2f} MB")
    ff("-i", master, "-frames:v", "1", d / "hero_poster.png")
    print(f"hero loop {total:.2f} s -> {d}")


def check(final, parts, out_dir, xf=XF_X):
    """Contact sheet (frames from every part) + per-part black / frozen report."""
    starts, t = [], 0.0
    for i, (p, d) in enumerate(parts):
        starts.append((Path(p).stem, t, d))
        t += d - (xf if i < len(parts) - 1 else 0)
    thumbs = []
    for name, st, d in starts:
        for frac in (0.2, 0.5, 0.85) if d > 6 else (0.3, 0.75):
            png = out_dir / f"_cs_{name}_{frac}.png"
            ff("-ss", f"{st + d * frac:.2f}", "-i", final, "-frames:v", "1", "-vf", "scale=400:-2", png)
            thumbs.append((f"{name} {st + d * frac:.1f}s", Image.open(png).convert("RGB")))
    cols = 6
    th = thumbs[0][1].height
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 400, rows * (th + 26)), (0, 0, 0))
    dr = ImageDraw.Draw(sheet)
    for i, (lab, im) in enumerate(thumbs):
        x, y = (i % cols) * 400, (i // cols) * (th + 26)
        sheet.paste(im, (x, y))
        dr.text((x + 6, y + th + 3), lab, font=font("consola.ttf", 17), fill=(230, 230, 230))
    sheet.save(out_dir / "contact_sheet.jpg", quality=88)

    raw = subprocess.run([FF, "-v", "error", "-i", str(final), "-vf", "fps=8,scale=64:36,format=gray", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    n = len(raw) // 2304
    means, diffs = [], [0.0]
    for i in range(n):
        fr = raw[i * 2304:(i + 1) * 2304]
        means.append(sum(fr) / 2304)
        if i:
            diffs.append(sum(abs(a - b) for a, b in zip(fr, raw[(i - 1) * 2304:i * 2304])) / 2304)
    report = []
    for name, st, d in starts:
        a, b = int(st * 8), min(int((st + d) * 8), n)
        run = best = 0
        for v in diffs[a + 1:b]:
            run = run + 1 if v < 0.12 else 0
            best = max(best, run)
        report.append(dict(part=name, start=round(st, 2), secs=round(d, 2), min_luma=round(min(means[a:b]), 1),
                           mean_luma=round(sum(means[a:b]) / (b - a), 1), longest_static_s=round(best / 8, 2)))
    (out_dir / "check.json").write_text(json.dumps(report, indent=1))
    for r in report:
        print(r)


def main():
    todo = [a for a in sys.argv[1:] if not a.startswith("--")] or ["trailer", "hero"]
    for sec in (CAUSTIC, BAKERY, SUBMARINE):
        for src, _, _ in sec["shots"]:
            if not Path(src).exists():
                raise SystemExit(f"missing footage: {src}")
    if "trailer" in todo:
        parts = trailer()
        if "--check" in sys.argv:
            check(FINAL, parts, OUT)
    if "hero" in todo:
        hero()


if __name__ == "__main__":
    main()
