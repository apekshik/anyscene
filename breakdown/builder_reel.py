"""Posting videos for one scene-builder run, made from the run's own event log.

    uv run --with pillow python -I breakdown/builder_reel.py <run dir> --reference ref.png [--clips a.mp4 b.mp4]
           [--name "Maison Roussel"] [--out DIR]

<run dir> is a builder/client.py output folder: events.jsonl (every stage event, with the image of each one) and,
once the build has finished, build.json (stills, previews). Writes two videos:
  hero.mp4       the tweet: reference, wipe to the finished render, the walkthrough clips, end card
  breakdown.mp4  the thread reply: how it got there, chapter by chapter (plan, prop references, 3D comparisons, every
                 test render it looked at, each critic round with its scores, finals, scouting previews, walkthrough)
Images come from the fal URLs in the log (cached under <out>/img). Encoded with NVENC (the CapCut ffmpeg here has no
libx264 or drawtext, so every caption is drawn with PIL).
"""

import argparse
import hashlib
import json
import re
import sys
import textwrap
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assemble import BG, DIM, FPS, H, INK, W, ff, font  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

ACCENT = (226, 178, 92)  # warm brass, the AnyScene stamp colour on dark
ENC = ["-c:v", "h264_nvenc", "-preset", "p6", "-cq", "19", "-pix_fmt", "yuv420p", "-r", str(FPS)]
SCORE_KEYS = ["layout", "props", "screens_signage", "materials", "lighting", "atmosphere", "plausibility", "composition"]
SCORE_LABELS = ["Layout", "Props", "Screens/signs", "Materials", "Lighting", "Atmosphere", "Plausibility", "Composition"]


def clock(s):
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def fetch(url, cache):
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (hashlib.md5(url.encode()).hexdigest()[:12] + Path(url).suffix)
    if not path.exists():
        urllib.request.urlretrieve(url, path)
    return path


def fit(img, box_w, box_h):
    img = img.convert("RGB")
    s = min(box_w / img.width, box_h / img.height)
    return img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)


def card(out, image=None, chapter="", sub="", when=None, scores=None, big=None):
    """One 1920x1080 frame: the image fitted in the middle, a chapter line on top, the agent's note under it."""
    c = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(c)
    top, bottom = 190, 60
    if image is not None:
        im = fit(Image.open(image), W - 120, H - top - bottom - (0 if not scores else 0))
        if scores:
            im = fit(Image.open(image), W - 120 - 520, H - top - bottom)
        x = 60 if scores else (W - im.width) // 2
        c.paste(im, (x, top + (H - top - bottom - im.height) // 2))
    if chapter:
        d.text((60, 46), chapter.upper(), font=font("bahnschrift.ttf", 44), fill=ACCENT)
    if when is not None:
        d.text((W - 60, 52), f"T+{clock(when)}", font=font("consola.ttf", 34), fill=DIM, anchor="ra")
    if sub:
        lines = textwrap.wrap(sub, 120)[:3]
        for i, ln in enumerate(lines):
            d.text((60, 100 + i * 28), ln, font=font("segoeui.ttf", 23), fill=INK)
    if scores:
        x0, y0 = W - 60 - 460, top + 20
        d.text((x0, y0), "CRITIC SCORES", font=font("bahnschrift.ttf", 30), fill=DIM)
        for i, (k, lab) in enumerate(zip(SCORE_KEYS, SCORE_LABELS)):
            v = scores.get(k, 0)
            y = y0 + 60 + i * 64
            d.text((x0, y), lab, font=font("segoeui.ttf", 26), fill=INK)
            d.text((x0 + 460, y), str(v), font=font("consolab.ttf", 30), fill=ACCENT if v >= 6 else (214, 96, 80), anchor="ra")
            d.rectangle((x0, y + 38, x0 + 460, y + 46), fill=(40, 38, 35))
            d.rectangle((x0, y + 38, x0 + int(460 * v / 10), y + 46), fill=ACCENT if v >= 6 else (214, 96, 80))
            d.line((x0 + int(460 * 0.6), y + 34, x0 + int(460 * 0.6), y + 50), fill=DIM, width=2)
    if big:
        f = font("bahnschrift.ttf", 84)
        for i, ln in enumerate(big):
            d.text((W // 2, H // 2 - 70 * (len(big) - 1) // 2 + i * 90 - 40), ln, font=f if i == 0 else font("segoeui.ttf", 40),
                   fill=INK if i == 0 else DIM, anchor="mm")
    c.save(out)
    return out


def slideshow(cards, out):
    """cards: [(png, seconds)] -> mp4 (hard cuts; the cards already carry their own titles)."""
    lst = out.with_suffix(".txt")
    with open(lst, "w", encoding="utf-8") as f:
        for png, s in cards:
            f.write(f"file '{Path(png).as_posix()}'\nduration {s:.3f}\n")
        f.write(f"file '{Path(cards[-1][0]).as_posix()}'\n")
    ff("-f", "concat", "-safe", "0", "-i", lst, "-vf", f"fps={FPS},format=yuv420p", *ENC, "-an", out)
    return out


def clip_with_caption(src, cap_png, out, seconds=None):
    """A walkthrough clip letterboxed to 1920x1080 with a caption band drawn on top."""
    trim = ["-t", str(seconds)] if seconds else []
    ff("-i", src, "-i", cap_png, *trim, "-filter_complex",
       f"[0]scale={W}:-2:flags=lanczos,pad={W}:{H}:0:(oh-ih)/2:color=black,fps={FPS}[v];[v][1]overlay=0:0",
       *ENC, "-an", out)
    return out


def caption_band(out, chapter, sub=""):
    c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(c)
    d.rectangle((0, 0, W, 130), fill=(14, 13, 12, 200))
    d.text((60, 30), chapter.upper(), font=font("bahnschrift.ttf", 44), fill=ACCENT)
    if sub:
        d.text((60, 86), sub, font=font("segoeui.ttf", 24), fill=INK)
    c.save(out)
    return out


def concat(parts, out):
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{Path(p).as_posix()}'\n" for p in parts), encoding="utf-8")
    ff("-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("run")
    p.add_argument("--reference", required=True)
    p.add_argument("--clips", nargs="*", default=[])
    p.add_argument("--name", default="")
    p.add_argument("--out")
    a = p.parse_args()
    run = Path(a.run)
    out = Path(a.out or run / "reel")
    tmp = out / "cards"
    tmp.mkdir(parents=True, exist_ok=True)
    cache = out / "img"

    events = [json.loads(l) for l in open(run / "events.jsonl", encoding="utf-8")]
    build = json.loads((run / "build.json").read_text(encoding="utf-8")) if (run / "build.json").exists() else {}
    seen, imgs = set(), []
    for e in events:
        u = e.get("preview_url")
        if u and u not in seen:
            seen.add(u)
            imgs.append(e)
    first_critic = next((e["t"] for e in imgs if e["stage"] == "critique"), 1e9)
    end_t = max(e["t"] for e in events)
    stills = build.get("stills", [])
    previews = build.get("previews", [])
    n = 0

    def nxt():
        nonlocal n
        n += 1
        return tmp / f"{n:03d}.png"

    # ------------------------------------------------------------------ breakdown
    cards = [(card(nxt(), big=[a.name or "One image in", "a 3D set out, built by an agent, nobody steering"]), 2.2),
             (card(nxt(), a.reference, "Input", "One reference image. No prompt, no floor plan, no human in the loop."), 2.6)]
    plan = next((e for e in imgs if e["stage"] == "plan"), None)
    if plan:
        cards.append((card(nxt(), fetch(plan["preview_url"], cache), "01  Plan", plan["message"], plan["t"]), 3.2))
    sheets = [e for e in imgs if e["t"] < first_critic and re.search(r"ref_sheet|refsheet|imgsheet|sheet\.png", e.get("message", ""))]
    for e in sheets[:2]:
        cards.append((card(nxt(), fetch(e["preview_url"], cache), "02  Prop references",
                           "Every prop gets a product-shot reference first, checked for real brands.", e["t"]), 2.0))
    compares = [e for e in imgs if e["t"] < first_critic and re.search(r"compar|pick|tripo|meshy", e.get("message", ""), re.I)]
    for e in compares[:6]:
        cards.append((card(nxt(), fetch(e["preview_url"], cache), "03  3D models",
                           "Tripo and Meshy both build every prop; the agent compares them under the same light and picks.",
                           e["t"]), 0.9))
    shown = {plan["preview_url"]} if plan else set()
    tests, paths = [], set()
    for e in imgs:  # each file once (the agent re-opens the same render), and never the plan again
        key = e.get("message", "")
        if (e["t"] < first_critic and e not in sheets and e not in compares and e["preview_url"] not in shown
                and "floor_plan" not in key and key not in paths
                and e["stage"] in ("log", "layout", "props", "dressing", "lighting", "screens", "materials")):
            paths.add(key)
            tests.append(e)
    step = max(1, len(tests) // 28)
    for e in tests[::step]:
        cards.append((card(nxt(), fetch(e["preview_url"], cache), "04  Building it",
                           "Every test render the agent looked at, in order. It writes a script to fix whatever it sees.",
                           e["t"]), 0.45))
    rounds = [e for e in events if e["stage"] == "critique" and e.get("critique")]
    for e in rounds:
        c = e["critique"]
        img = e.get("preview_url")
        fix = (c.get("fixes") or [""])[0]
        cards.append((card(nxt(), fetch(img, cache) if img else None, f"05  Critic, round {c['round']}",
                           ("PASS. " if c.get("passed") else "Not yet. Top fix: ") + fix, e["t"], scores=c["scores"]), 1.6))
    for i, u in enumerate(stills):
        cards.append((card(nxt(), fetch(u, cache), "06  Finals", f"Graded still {i + 1} of {len(stills)}", end_t), 1.8))
    for pv in previews[:16]:
        cards.append((card(nxt(), fetch(pv["url"], cache), "07  Scouting previews",
                           pv["name"].replace("_", " "), end_t), 0.8))
    parts = [slideshow(cards, out / "breakdown_a.mp4")]
    for k, clip in enumerate(a.clips):
        cap = caption_band(tmp / f"clipcap_{k}.png", "08  Walkthrough",
                           "Shot by the shots agent on the finished set, rendered on the render farm.")
        parts.append(clip_with_caption(clip, cap, out / f"breakdown_clip_{k}.mp4"))
    total = clock(end_t)
    parts.append(slideshow([(card(nxt(), big=[f"{total} start to finish", "AnyScene"]), 2.5)], out / "breakdown_end.mp4"))
    concat(parts, out / "breakdown.mp4")

    # ------------------------------------------------------------------ hero
    hero_still = stills[0] if stills else (rounds[-1].get("preview_url") if rounds else None)
    if hero_still:
        ref = card(tmp / "hero_ref.png", a.reference, "Reference", "")
        fin = card(tmp / "hero_final.png", fetch(hero_still, cache), "AnyScene · 3D set", "")
        ff("-loop", "1", "-t", "2.6", "-i", ref, "-loop", "1", "-t", "3.4", "-i", fin, "-filter_complex",
           f"[0]fps={FPS},format=yuv420p[a];[1]fps={FPS},format=yuv420p[b];[a][b]xfade=transition=wiperight:duration=0.8:offset=1.8",
           *ENC, "-an", out / "hero_a.mp4")
        hparts = [out / "hero_a.mp4"]
        for k, clip in enumerate(a.clips):
            cap = caption_band(tmp / f"herocap_{k}.png", "Walkthrough", "")
            hparts.append(clip_with_caption(clip, cap, out / f"hero_clip_{k}.mp4"))
        hparts.append(slideshow([(card(tmp / "hero_end.png", big=["Reference in. 3D set out.", f"{total}, fully automated · AnyScene"]), 2.4)],
                                out / "hero_end.mp4"))
        concat(hparts, out / "hero.mp4")
    print("wrote", out / "breakdown.mp4", "and", out / "hero.mp4", f"({len(cards)} breakdown cards)")


if __name__ == "__main__":
    main()
