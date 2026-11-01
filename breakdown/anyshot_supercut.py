"""AnyShot supercut: four AnyScene sets shot by AnyShot (scene to video), for the launch post.

Every shot here was planned and rendered by the AnyShot endpoint from words. The caustics chamber was directed shot by
shot; riad, apothecary and submarine got one text brief each and the agent picked the shots. Each set runs establishing
wide -> first-person walk -> close dolly reveals, the same grammar as the brief.

    python breakdown/anyshot_supercut.py      -> breakdown/supercut/anyshot_supercut.mp4 (1920x1080, 24 fps)
"""

import glob
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if "FFMPEG" not in os.environ:
    capcut = sorted(glob.glob(os.path.expandvars(r"%LOCALAPPDATA%/CapCut/Apps/*/ffmpeg.exe")))
    os.environ["FFMPEG"] = capcut[-1] if capcut else "ffmpeg"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assemble import BG, DIM, FPS, H, INK, LETTERBOX, W, duration, ff, font  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

RUNS = Path(os.environ.get("ANYSCENE_RUNS", ROOT.parent / "anyscene-runs"))
OUT = ROOT / "breakdown/supercut"
XF = 0.5  # crossfade, seconds
CARD = 2.4  # name card length, including both crossfades
SEG_ENC = ["-an", "-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "16", "-b:v", "0", "-pix_fmt", "yuv420p"]
BRASS = (226, 178, 92)


def shot(folder, name):
    """An AnyShot output by shot name (the files carry a fal upload prefix)."""
    hits = sorted((RUNS / folder).glob(f"*{name}.mp4"))
    if not hits:
        raise FileNotFoundError(f"{folder}/*{name}.mp4")
    return hits[0]


C1, C2 = RUNS / "videos/caustic_shots", RUNS / "videos/caustic_shots2"
SCENES = [
    dict(key="chamber", kicker="Directed shot by shot", title="The caustics chamber", accent=BRASS, clips=[
        (C2 / "establishing_wide.mp4", 0.5, 5.0), (C2 / "walk_pov.mp4", 1.0, 9.0),
        (C2 / "reveal_from_sculpture.mp4", 0.5, 6.0), (C1 / "rack_desk_chair.mp4", 0.5, 6.5),
        (C1 / "zoom_out_reveal.mp4", 0.5, 7.5)]),
    dict(key="riad", kicker="One text brief", title="A Marrakech riad", accent=(214, 170, 112), clips=[
        (shot("shot_riad", "est_wide"), 0.5, 5.0), (shot("shot_riad", "walk_in"), 1.0, 9.0),
        (shot("shot_riad", "reveal_tea_court"), 0.3, 6.0), (shot("shot_riad", "reveal_lemon_salon"), 0.3, 6.0),
        (shot("shot_riad", "reveal_fountain"), 0.3, 6.2)]),
    dict(key="apothecary", kicker="One text brief", title="A Victorian apothecary", accent=(200, 140, 80), clips=[
        (shot("shot_apothecary", "establish_wide"), 0.5, 5.0), (shot("shot_apothecary", "walk_in"), 1.0, 9.0),
        (shot("shot_apothecary", "globes_reveal"), 0.0, 5.0), (shot("shot_apothecary", "register_reveal"), 0.0, 5.0),
        (shot("shot_apothecary", "bottle_wall_reveal"), 0.0, 5.0)]),
    dict(key="submarine", kicker="One text brief", title="A submarine control room", accent=(226, 96, 80), clips=[
        (shot("shot_submarine", "establish_wide"), 0.5, 5.0), (shot("shot_submarine", "walk_in"), 1.0, 9.0),
        (shot("shot_submarine", "reveal_chart"), 0.0, 5.25), (shot("shot_submarine", "reveal_planes"), 0.0, 5.25),
        (shot("shot_submarine", "reveal_depth"), 0.0, 5.25)]),
]


def text_centered(d, y, txt, fnt, fill):
    d.text(((W - d.textlength(txt, font=fnt)) / 2, y), txt, font=fnt, fill=fill)


def still_video(img, secs, out):
    png = out.with_suffix(".png")
    img.save(png)
    ff("-loop", "1", "-t", f"{secs:.3f}", "-i", png, "-vf", f"fps={FPS},format=yuv420p", *SEG_ENC, out)
    return secs


def blurred_frame(src, at, dim=0.38):
    png = OUT / f"_bg_{Path(src).stem}_{at:.1f}.png"
    ff("-ss", f"{at:.2f}", "-i", src, "-frames:v", "1", "-vf", f"scale={W}:-2", png)
    fr = Image.open(png).convert("RGB")
    canvas = Image.new("RGB", (W, H), BG)
    canvas.paste(fr.filter(ImageFilter.GaussianBlur(16)).point(lambda v: int(v * dim)), (0, (H - fr.height) // 2))
    return canvas


def name_card(i, s, out):
    src, ss, t = s["clips"][0]
    canvas = blurred_frame(src, ss + t * 0.5)
    d = ImageDraw.Draw(canvas)
    y = (H - 30 - 80) // 2
    text_centered(d, y, f"{i + 1:02d} / {len(SCENES):02d}   {s['kicker'].upper()}", font("bahnschrift.ttf", 30), s["accent"])
    text_centered(d, y + 30, s["title"], font("segoeuib.ttf", 80), INK)
    return still_video(canvas, CARD, out)


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


def tile_frames(sc, idx, w, h, secs):
    """secs of one of the scene's clips from its start point, cropped to a mosaic tile, as PIL frames at FPS."""
    src, ss, _ = sc["clips"][idx]
    d = OUT / f"_as_tile_{sc['key']}_{idx}"
    if not d.exists() or len(list(d.glob("*.png"))) < int(secs * FPS):
        d.mkdir(exist_ok=True)
        ff("-ss", ss, "-t", secs, "-i", src, "-vf", f"fps={FPS}", d / "%04d.png")
    return [fit(Image.open(f).convert("RGB"), w, h) for f in sorted(d.glob("*.png"))[: int(secs * FPS)]]


def cold_open(out, secs=11.0):
    """The overview before the details: the four sets' establishing frames as a 2x2 mosaic ("ANY SCENE IN"), tiles
    fading in one by one, then each tile wipes left to right to its first-person walkthrough, already playing
    ("DIRECTED SHOTS OUT"); all four keep walking until the cut. Text stays above the mosaic, never over the footage."""
    gap, top, bottom, side = 14, 96, 40, 40
    tw, th = (W - 2 * side - gap) // 2, (H - top - bottom - gap) // 2
    tiles = [(sc, side + (i % 2) * (tw + gap), top + (i // 2) * (th + gap), tw, th) for i, sc in enumerate(SCENES)]
    wipe0, wipe_step, wipe_len = 2.6, 0.25, 0.8
    stills = [tile_frames(sc, 0, tw, th, 1.0 / FPS)[0] for sc, *_ in tiles]  # the establishing wide's first frame
    walks = [tile_frames(sc, 1, tw, th, secs - wipe0 + 0.2) for sc, *_ in tiles]
    head = font("bahnschrift.ttf", 40)
    n = int(round(secs * FPS))
    frames = OUT / "_as_open_frames"
    frames.mkdir(exist_ok=True)
    ease = lambda a: (lambda a: a * a * (3 - 2 * a))(min(max(a, 0.0), 1.0))
    mix = lambda c0, c1, a: tuple(int(c0[j] + (c1[j] - c0[j]) * a) for j in range(3))
    for f in range(n):
        t = f / FPS
        fr = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(fr)
        a_in = ease((t - 0.1) / 0.5) * (1 - ease((t - wipe0) / 0.5))
        a_out = ease((t - wipe0 - 0.3) / 0.6)
        if a_in > 0:
            text_centered(d, 30, "ANY SCENE IN", head, mix(BG, BRASS, a_in))
        if a_out > 0:
            text_centered(d, 30, "DIRECTED SHOTS OUT", head, mix(BG, BRASS, a_out))
        for i, ((sc, x, y, w, h), still, walk) in enumerate(zip(tiles, stills, walks)):
            a = ease((t - 0.25 - i * 0.3) / 0.55)
            if a <= 0:
                continue
            tile = Image.blend(Image.new("RGB", still.size, BG), still, a)
            p = ease((t - wipe0 - i * wipe_step) / wipe_len)
            if p > 0:  # the walkthrough, already playing, slides in from the left over the establishing frame
                st = walk[min(len(walk) - 1, max(0, int((t - wipe0 - i * wipe_step) * FPS)))]
                cut = int(w * p)
                tile.paste(st.crop((0, 0, cut, h)), (0, 0))
                if 0 < cut < w:
                    ImageDraw.Draw(tile).line((cut, 0, cut, h), fill=BRASS, width=3)
            fr.paste(tile, (x, y))
            band = Image.new("RGB", (w, 44), (0, 0, 0))
            fr.paste(Image.blend(fr.crop((x, y + h - 44, x + w, y + h)), band, 0.55 * a), (x, y + h - 44))
            d.text((x + 16, y + h - 37), sc["title"].upper(), font=font("bahnschrift.ttf", 26), fill=mix(BG, INK, a))
        fr.save(frames / f"{f:04d}.png", compress_level=1)
    ff("-framerate", str(FPS), "-i", frames / "%04d.png", "-vf", "format=yuv420p", *SEG_ENC, out)
    return n / FPS


def title_card(out, secs=3.0):
    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)
    y = (H - 128 - 36) // 2
    text_centered(d, y, "AnyShot", font("segoeuib.ttf", 96), INK)
    text_centered(d, y + 128, "SCENE TO VIDEO", font("bahnschrift.ttf", 36), BRASS)
    return still_video(canvas, secs, out)


def end_card(out, secs=4.5):
    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)
    lines = [(font("segoeuib.ttf", 96), INK, "AnyShot", 128),
             (font("bahnschrift.ttf", 36), BRASS, "OPEN SOURCE  ·  github.com/apekshik/anyshot", 92),
             (font("segoeuisl.ttf", 30), DIM, "AnyScene builds the set. AnyShot shoots it.", 0)]
    y = (H - sum(g for *_, g in lines) - 30) // 2
    for fnt, col, txt, g in lines:
        text_centered(d, y, txt, fnt, col)
        y += g
    return still_video(canvas, secs, out)


def clip(src, ss, t, out):
    ff("-ss", f"{ss:.3f}", "-t", f"{t:.3f}", "-i", src, "-vf", f"{LETTERBOX},fps={FPS},setsar=1,format=yuv420p",
       *SEG_ENC, out)
    return duration(out)


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
    return offset


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    parts = [(OUT / "_as_open.mp4", cold_open(OUT / "_as_open.mp4"))]
    for i, s in enumerate(SCENES):
        card = OUT / f"_as_card_{s['key']}.mp4"
        parts.append((card, name_card(i, s, card)))
        for j, (src, ss, t) in enumerate(s["clips"]):
            seg = OUT / f"_as_{s['key']}_{j}.mp4"
            parts.append((seg, clip(src, ss, t, seg)))
    parts.append((OUT / "_as_end.mp4", end_card(OUT / "_as_end.mp4")))
    final = OUT / "anyshot_supercut.mp4"
    total = xfade_join(parts, final)
    print(f"{final}  {total:.1f} s, {len(parts)} parts")


if __name__ == "__main__":
    main()
