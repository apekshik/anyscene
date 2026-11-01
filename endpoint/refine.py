"""/build refine stage, orchestration: what refine_blender.py `apply` needs, all of it requested at once.

1. Surfaces: Claude looks at each prop's straight-on front view and marks its screens, glass, lamps and glowing
   panels (normalised boxes), with what each screen should show in this scene.
2. Screen content: one generated image per screen (GPT Image 2.5), from Claude's description and the scene's look.
3. Box textures: one tileable texture per distinct material description on the plan's scripted objects.
Writes refine.json for refine_blender.py.
"""

import asyncio
import base64
import hashlib
import io
import json
import os
import urllib.request
from typing import Literal

import fal_client
from PIL import Image
from pydantic import BaseModel, Field

import planner
from schema import Plan

IMAGE = "openai/gpt-image-2.5/sunburst/text-to-image"


class Surface(BaseModel):
    kind: Literal["screen", "glass", "lamp", "glow"] = Field(
        description="screen: a display that should light up (CRT, monitor, TV, scope, readout). glass: a pane, lens, "
                    "cover or bottle that should be see-through. lamp: a bulb, tube or shade that emits light. "
                    "glow: a backlit sign, indicator bank or dial face that glows softly.")
    box: list[float] = Field(description="Normalised [x0, y0, x1, y1] in this image, y down, tight around the surface.")
    content: str = Field("", description="For screens: what it shows in this scene, e.g. 'green phosphor telemetry "
                                         "table with orbit numbers'. Empty otherwise.")
    color: str = Field("", description="For lamps: the light's hex colour, e.g. #ffc98a. Empty otherwise.")


class Surfaces(BaseModel):
    surfaces: list[Surface]


PROMPT = """This is a straight-on front view of a 3D prop, a {label}, for a scene: {summary}

Mark every surface on it that needs special treatment in a photoreal render: screens that should light up, glass that
should be see-through, lamps or bulbs that emit light, and backlit panels that glow. Boxes must be tight around each
surface and inside the prop. Mark nothing if the prop has none of these; most props have none. For each screen, say
what it should show in this scene, in the period and style of the scene."""


def _jpeg_b64(path: str) -> str:
    img = Image.open(path).convert("RGB")
    img.thumbnail((1024, 1024))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return base64.standard_b64encode(buf.getvalue()).decode()


def _surfaces(view_png: str, label: str, summary: str) -> list[dict]:
    client, model, extra = planner._client()
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _jpeg_b64(view_png)}},
               {"type": "text", "text": PROMPT.format(label=label, summary=summary)}]
    with client.beta.messages.stream(model=model, max_tokens=8000, thinking={"type": "adaptive"},
                                     output_config={"effort": "medium", "format": {"type": "json_schema",
                                                                                   "schema": planner.strict_schema(Surfaces)}},
                                     messages=[{"role": "user", "content": content}], **extra) as s:
        msg = s.get_final_message()
    if msg.stop_reason != "end_turn":
        return []
    out = Surfaces.model_validate_json(next(b.text for b in msg.content if b.type == "text")).surfaces
    return [x.model_dump() for x in out if len(x.box) == 4 and x.box[2] > x.box[0] and x.box[3] > x.box[1]]


async def _image(prompt: str, path: str, size: str = "landscape_4_3") -> str:
    h = await fal_client.submit_async(IMAGE, {"prompt": prompt, "image_size": size, "quality": "medium", "num_images": 1,
                                              "output_format": "png"})
    res = await h.get()
    await asyncio.to_thread(urllib.request.urlretrieve, res["images"][0]["url"], path)
    return path


async def build_refine(plan: Plan, assets: dict, views_dir: str, out_dir: str, report) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    meta = json.load(open(os.path.join(views_dir, "views.json")))
    summary = f"{plan.summary} ({plan.time_of_day}; mood: {', '.join(plan.mood)})"

    # 1. surfaces on every prop, in parallel
    ids = [aid for aid in meta if os.path.exists(os.path.join(views_dir, f"{aid}.png"))]
    labels = {a["id"]: a["label"] for a in assets.values()}
    report("refine", f"finding screens, glass and lamps on {len(ids)} props", 0.05)
    found = await asyncio.gather(*[asyncio.to_thread(_surfaces, os.path.join(views_dir, f"{aid}.png"),
                                                     labels.get(aid, aid), summary) for aid in ids],
                                 return_exceptions=True)
    surfaces = {aid: (r if isinstance(r, list) else []) for aid, r in zip(ids, found)}
    n = {k: sum(s["kind"] == k for v in surfaces.values() for s in v) for k in ("screen", "glass", "lamp", "glow")}
    report("refine", f"{n['screen']} screens, {n['glass']} glass, {n['lamp']} lamps, {n['glow']} glowing panels", 0.4)

    # 2 + 3. screen content and box textures, all at once
    jobs = []
    for aid, ss in surfaces.items():
        for k, s in enumerate(ss):
            if s["kind"] == "screen":
                p = os.path.join(out_dir, f"screen_{aid}_{k}.png")
                s["image"] = p
                jobs.append(_image(f"Flat, straight-on screen content to display on a {labels.get(aid, aid)}: "
                                   f"{s['content'] or 'a period-appropriate display'}. Fill the frame edge to edge with the "
                                   f"screen image only, no bezel, no device, no reflections. Fictional text only, no real "
                                   f"brands. Scene: {summary}", p))
    textures, materials = {}, {}
    for ob in plan.objects:
        if not ob.generate and getattr(ob, "material", "") and ob.category != "decal":
            key = hashlib.md5(ob.material.lower().encode()).hexdigest()[:10]
            if key not in materials:
                p = os.path.join(out_dir, f"tile_{key}.png")
                materials[key] = p
                jobs.append(_image(f"Seamless tileable texture, flat and evenly lit, straight-on, no perspective, no "
                                   f"objects, filling the whole frame: {ob.material}. Photographic surface detail.",
                                   p, "square_hd"))
            textures[ob.id] = {"image": materials[key], "tile_m": 0.8, "material": ob.material}
    report("refine", f"generating {len(jobs)} screen images and textures", 0.5)
    results = await asyncio.gather(*jobs, return_exceptions=True)
    failed = sum(isinstance(r, Exception) for r in results)
    for ss in surfaces.values():  # drop screens whose image failed
        for s in ss:
            if s["kind"] == "screen" and not os.path.exists(s.get("image", "")):
                s.pop("image", None)
    textures = {k: v for k, v in textures.items() if os.path.exists(v["image"])}
    report("refine", f"{len(jobs) - failed} of {len(jobs)} images ready", 0.8)
    spec = {"views": meta, "surfaces": surfaces, "textures": textures}
    json.dump(spec, open(os.path.join(out_dir, "refine.json"), "w"), indent=1)
    return spec
