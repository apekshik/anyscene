"""What each scene route starts from, turned into what the scene builder works with: reference PNGs, the brief, the
dials and, for kit2scene / scene2scene, the kit or the earlier build copied into the workspace.

    /image2scene  the images are the references
    /text2scene   a reference is generated from the words first (GPT Image 2.5 Sunburst)
    /video2scene  stills spread across the clip are the references; smaller frames of the whole clip go in input/video/
    /kit2scene    the kit goes in input/kit/; its style references stand in when no images are given
    /scene2scene  the earlier build's workspace is copied in and the agent changes it instead of starting over
    /ref2scene    any mix of the above
"""

import glob
import json
import os
import re
import shutil
import subprocess
import urllib.request

BUILDS_DIR = "/data/anyscene/builder"
KITS_DIR = "/data/anyscene/kit"  # AnyKit's kits: a separate app, same fal account, same /data
REF_MODEL = "openai/gpt-image-2.5/sunburst/text-to-image"
REF_PROMPT = ("A wide photographic film still of the place below, showing the whole space and what fills it. Real "
              "materials with believable wear, motivated practical light, no people, no captions or watermarks, no "
              "real brands.\n\n{}")
VIDEO_REFS = 4  # full-resolution stills from a video that serve as its references
VIDEO_FRAMES = 24  # smaller frames across the whole clip, for the agent to read the space from

TEXT_NOTE = """## Reference (generated)
The customer gave only words. input/reference_1.png was generated from them as a starting point. Where the words and
the image disagree, the words decide what the place is."""

VIDEO_NOTE = """## Video
The references are stills from the customer's video, and input/video/ holds frames from across the whole clip (each
named with its time). Read them all before planning: what the camera passes, how the spaces connect, what is behind
it. Build the place the video shows."""

KIT_NOTE = """## Kit
Dress the set with the AnyKit kit in input/kit/. kit.json lists every prop with its real size in metres; each one's
GLB is in items/<id>/<id>.glb (with a lighter <id>_lod1.glb), and renders/lineup.png shows them side by side. They
are already at real scale and in one style: use them as they are wherever they fit, and generate new props only for
what the kit doesn't have, matching its style."""

EDIT_ASK = """This workspace already holds a finished scene, build {build}: its scripts in scenes/{scene}/scripts/, its
generated assets, scenes/{scene}/NOTES.md, and its deliverables in input/source/ (scene.blend, stills/, plan.json,
shots.json, dials.json). The customer wants it changed. The change is at the end of input/brief.md, under "Changes
requested", and input/dials.json holds the dials to build to. Read SKILL.md, then the NOTES.md and the scripts.
Change the existing scene rather than starting over: edit its scripts, keep everything the change doesn't touch as it
was (layout, props, materials, cameras), and generate new assets only for what the change needs. Then deliver
everything the endpoint asks for into out/ again, from the changed scene."""


def check(req):
    """Reject a request that can't start, before it gets a build id."""
    if not (req.reference_image_urls or req.prompt.strip() or req.video_url or req.kit_id or req.source_build_id):
        raise ValueError("Give at least one source: reference_image_urls, prompt, video_url, kit_id or source_build_id.")
    if len(req.reference_image_urls) > 4:
        raise ValueError("At most 4 reference images.")
    for name, value, prefix in (("kit_id", req.kit_id, "k_"), ("source_build_id", req.source_build_id, "b_")):
        if value and not re.fullmatch(prefix + r"[0-9a-f]{6,32}", value):
            raise ValueError(f"{name} should look like {prefix}..., not {value!r}")
    if req.kit_id and not os.path.exists(os.path.join(KITS_DIR, req.kit_id, "out", "kit.json")):
        raise ValueError(f"kit {req.kit_id}: no finished kit with that id on this account")
    if req.source_build_id and not os.path.exists(os.path.join(BUILDS_DIR, req.source_build_id, "out", "scene.blend")):
        raise ValueError(f"build {req.source_build_id}: no finished scene.blend to change")


def prepare(req, work):
    """Fetch and convert the request's sources into `work`. Returns (reference PNGs, brief, dials, ask or None).
    May set req.scene (scene2scene keeps the earlier build's scene folder)."""
    stage = os.path.join(work, ".sources")
    os.makedirs(stage, exist_ok=True)
    os.makedirs(os.path.join(work, "input"), exist_ok=True)
    refs, prompt, dials, ask, notes = [], req.prompt, dict(req.dials), None, []
    if req.source_build_id:
        refs, prompt, dials, ask = from_build(req, work)
    for i, url in enumerate(req.reference_image_urls[:4]):
        refs.append(as_png(download(url, f"{stage}/image_{i + 1}"), f"{stage}/image_{i + 1}.png"))
    if req.video_url:
        refs += video_refs(req.video_url, work, stage, max(1, VIDEO_REFS - len(refs)))
        notes.append(VIDEO_NOTE)
    if req.kit_id:
        kit_refs = copy_kit(req.kit_id, work)
        refs = refs or kit_refs
        notes.append(KIT_NOTE)
    if not refs:
        refs = [text_ref(prompt, stage)]
        notes.append(TEXT_NOTE)
    if notes:
        prompt = (prompt.strip() or "(no prompt: match the reference)") + "\n\n" + "\n\n".join(notes) + "\n"
    return refs[:4], prompt, dials, ask


def download(url, path):
    urllib.request.urlretrieve(url, path)
    return path


def as_png(src, dst):
    from PIL import Image
    Image.open(src).convert("RGB").save(dst)
    return dst


def text_ref(prompt, stage):
    import fal_client
    r = fal_client.subscribe(REF_MODEL, arguments={"prompt": REF_PROMPT.format(prompt.strip()), "num_images": 1,
                                                   "image_size": "landscape_16_9", "quality": "high",
                                                   "output_format": "png"})
    return as_png(download(r["images"][0]["url"], f"{stage}/text_ref"), f"{stage}/text_ref_1.png")


def video_refs(url, work, stage, n):
    src = download(url, f"{stage}/video")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src],
                           capture_output=True, text=True)
    try:
        dur = float(probe.stdout.strip())
    except ValueError:
        raise ValueError(f"couldn't read the video ({probe.stderr.strip()[:200] or 'no duration'})") from None

    def grab(t, out, width=None):
        scale = ["-vf", f"scale={width}:-2"] if width else []
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1", *scale, out],
                       check=True)

    frames = os.path.join(work, "input", "video")
    os.makedirs(frames, exist_ok=True)
    for i in range(VIDEO_FRAMES):
        t = dur * (i + 0.5) / VIDEO_FRAMES
        grab(t, os.path.join(frames, f"frame_{i + 1:02d}_{t:06.2f}s.jpg"), 1280)
    # the references: spread from 5% to 95% of the clip (cuts and fades sit at the ends), full resolution
    times = [dur / 2] if n == 1 else [dur * (0.05 + 0.9 * j / (n - 1)) for j in range(n)]
    refs = []
    for j, t in enumerate(times):
        grab(t, f"{stage}/video_ref_{j + 1}.png")
        refs.append(f"{stage}/video_ref_{j + 1}.png")
    return refs


def copy_kit(kit_id, work):
    kit = os.path.join(KITS_DIR, kit_id)
    shutil.copytree(os.path.join(kit, "out"), os.path.join(work, "input", "kit"), dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("*.zip", ".alive", "critique", "events.jsonl", "builder.log"))
    return sorted(glob.glob(os.path.join(kit, "input", "reference_*.png")))


def from_build(req, work):
    """scene2scene: copy the earlier build's workspace in (scripts, assets, notes), its deliverables to input/source/
    so this build must make its own, and carry over its references, floor plan, brief and dials."""
    src = os.path.join(BUILDS_DIR, req.source_build_id)
    scenes = [d for d in os.listdir(os.path.join(src, "scenes")) if os.path.isdir(os.path.join(src, "scenes", d))]
    if len(scenes) == 1:
        req.scene = scenes[0]
    skip = lambda d, names: [n for n in names if n.endswith(".zip") or n == ".alive"
                             or (os.path.samefile(d, src) and n in ("input", "out", ".builder", ".sources"))]
    shutil.copytree(src, work, ignore=skip, dirs_exist_ok=True)
    # scripts and notes may spell out the old workspace's path
    for path in glob.glob(os.path.join(work, "**", "*"), recursive=True):
        if path.endswith((".py", ".sh", ".json", ".md", ".mjs")) and os.path.isfile(path):
            text = open(path, encoding="utf-8", errors="surrogateescape").read()
            if src in text:
                with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
                    f.write(text.replace(src, work))
    prev = os.path.join(work, "input", "source")
    os.makedirs(prev, exist_ok=True)
    for f in ("scene.blend", "plan.json", "shots.json", "dials.json", "floor_plan.png"):
        if os.path.exists(os.path.join(src, "out", f)):
            shutil.copy2(os.path.join(src, "out", f), prev)
    if os.path.isdir(os.path.join(src, "out", "stills")):
        shutil.copytree(os.path.join(src, "out", "stills"), os.path.join(prev, "stills"), dirs_exist_ok=True)
    if os.path.exists(os.path.join(src, "input", "floor_plan.png")):
        shutil.copy2(os.path.join(src, "input", "floor_plan.png"), os.path.join(work, "input", "floor_plan.png"))
    read = lambda f, default: open(os.path.join(src, "input", f), encoding="utf-8").read() \
        if os.path.exists(os.path.join(src, "input", f)) else default
    dials = {**json.loads(read("dials.json", "{}")), **req.dials}
    prompt = read("brief.md", "").rstrip() + "\n\n## Changes requested (scene to scene)\n\n" + req.prompt.strip() + "\n"
    refs = sorted(glob.glob(os.path.join(src, "input", "reference_*.png")))
    return refs, prompt, dials, EDIT_ASK.format(build=req.source_build_id, scene=req.scene)
