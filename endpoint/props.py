"""/build stages 1-2: a product reference and a 3D mesh for every unique generated prop in a Plan, all submitted at once.

Objects that share a prompt share one asset (two identical chairs are generated once and placed twice). A prop that is
visible in reference image 0 gets its reference by cropping it out and cleaning the crop into a product shot with
GPT Image 2.5 edit, so it keeps the reference's look; the rest come from their prompt via text-to-image.
"""

import asyncio
import io
import json
import os
import re
import time
import urllib.request

import fal_client
from PIL import Image

from schema import Plan

REF_EDIT = "openai/gpt-image-2.5/sunburst/edit"
REF_T2I = "openai/gpt-image-2.5/sunburst/text-to-image"
MESH = {
    "tripo-h31": ("tripo3d/h3.1/image-to-3d", {"pbr": True, "texture": True, "geometry_quality": "detailed",
                                               "texture_quality": "detailed", "auto_size": True, "orientation": "align_image"}),
    "meshy": ("meshy/v7.1/image-to-3d", {"enable_pbr": True, "should_texture": True, "geometry_resolution": "4k",
                                         "topology": "triangle", "should_remesh": True, "target_polycount": 150000,
                                         "symmetry_mode": "auto"}),
}
SCAN = ("No real-world brand names or logos. Product reference photograph for 3D scanning. The entire object fully "
        "visible and centered, three-quarter front view from slightly above, plain seamless light-grey background, soft "
        "even diffuse studio lighting, no harsh shadows, no other objects, no hands, sharp focus, true-to-life materials.")


def assets_for(plan: Plan) -> dict[str, dict]:
    """Unique generated assets keyed by asset id, each with the objects that use it and the best crop to start from."""
    out = {}
    for ob in plan.objects:
        if not ob.generate or ob.w <= 0 or ob.h <= 0:
            continue
        # The plan's asset key groups identical objects; older plans without one group by the id's stem.
        key = getattr(ob, "asset", "") or re.sub(r"(_(\d+|left|right|fg|bg|front|back|[a-z]))+$", "", ob.id)
        a = out.setdefault(key, {"id": key, "prompt": ob.prompt or ob.label,
                                 "label": ob.label, "category": ob.category, "objects": [], "crop": None, "size": 0})
        a["objects"].append(ob.id)
        size = max(ob.w, ob.d, ob.h)
        a["size"] = max(a["size"], size)
        if ob.crop and (a["crop"] is None or (ob.crop[2] - ob.crop[0]) * (ob.crop[3] - ob.crop[1]) > a["crop_area"]):
            a["crop"], a["crop_area"] = ob.crop, (ob.crop[2] - ob.crop[0]) * (ob.crop[3] - ob.crop[1])
    # make asset ids unique
    seen = {}
    for a in out.values():
        n = seen.get(a["id"], 0)
        seen[a["id"]] = n + 1
        if n:
            a["id"] = f"{a['id']}_{n + 1}"
    return {a["id"]: a for a in out.values()}


def pick_model(a: dict, tier: str) -> list[str]:
    """Draft: one model per prop, Tripo by default since it finishes in ~3.5 min against Meshy's 8-10; Meshy only for
    small consumer items (under ~30 cm), where its sharper printed labels won in the reference scenes.
    Full: both, and the builder picks."""
    if tier == "full":
        return ["tripo-h31", "meshy"]
    small_item = a["category"] in ("prop", "clutter") and a["size"] < 0.3
    return ["meshy"] if small_item else ["tripo-h31"]


def _crop(ref: Image.Image, box: list[float]) -> Image.Image:
    w, h = ref.size
    x0, y0, x1, y1 = box
    pad_x, pad_y = 0.15 * (x1 - x0), 0.15 * (y1 - y0)
    return ref.crop((max(0, int((x0 - pad_x) * w)), max(0, int((y0 - pad_y) * h)),
                     min(w, int((x1 + pad_x) * w)), min(h, int((y1 + pad_y) * h))))


async def _run(endpoint: str, args: dict, retries: int = 2) -> dict:
    for attempt in range(retries + 1):
        try:
            h = await fal_client.submit_async(endpoint, args)
            return await h.get()
        except Exception:
            if attempt == retries:
                raise
            await asyncio.sleep(5 * (attempt + 1))


async def _reference(a: dict, ref_img: Image.Image | None, out_dir: str) -> dict:
    prompt = f"{a['prompt']}. {SCAN}"
    if a["crop"] and ref_img is not None:
        crop_url = await fal_client.upload_image_async(_crop(ref_img, a["crop"]), "jpeg")
        res = await _run(REF_EDIT, {"image_urls": [crop_url], "image_size": "square_hd", "quality": "high",
                                    "prompt": f"Recreate the {a['label']} shown in this crop as a clean, complete object. "
                                              f"Keep its exact design, colours, materials and condition. {prompt}"})
        a["ref_source"] = "crop"
    else:
        res = await _run(REF_T2I, {"prompt": prompt, "image_size": "square_hd", "quality": "high", "num_images": 1,
                                   "output_format": "png"})
        a["ref_source"] = "prompt"
    a["ref_url"] = res["images"][0]["url"]
    await asyncio.to_thread(urllib.request.urlretrieve, a["ref_url"], os.path.join(out_dir, f"{a['id']}_ref.png"))
    return a


async def _mesh(a: dict, model: str, out_dir: str) -> tuple[str, str]:
    endpoint, opts = MESH[model]
    res = await _run(endpoint, {**opts, "image_url": a["ref_url"]})
    glb = re.search(r"https://[^\"]+?\.glb[^\"]*", json.dumps(res)).group(0)
    a.setdefault("mesh_urls", {})[model] = glb
    path = os.path.join(out_dir, model, f"{a['id']}.glb")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Download beside the target and rename when complete, so a half-written file is never picked up.
    await asyncio.to_thread(urllib.request.urlretrieve, glb, path + ".part")
    with open(path + ".part", "rb") as f:
        if f.read(4) != b"glTF":
            raise RuntimeError(f"{a['id']}: {model} returned something that is not a GLB")
    os.replace(path + ".part", path)
    return model, path


class Generation:
    """Every prop's reference and mesh, all in flight at once. The build doesn't wait for all of them: it assembles with
    stand-in boxes straight away, calls wait() with a deadline, swaps in whatever has landed, and checks again before
    packaging. assets.json always reflects what is done; unfinished assets are marked "pending"."""

    def __init__(self, plan: Plan, reference_url: str, out_dir: str, tier: str, report):
        os.makedirs(out_dir, exist_ok=True)
        self.out_dir, self.tier, self.report = out_dir, tier, report
        self.assets = assets_for(plan)
        self.ref_img = None
        if reference_url.startswith("http"):
            with urllib.request.urlopen(reference_url, timeout=60) as r:
                self.ref_img = Image.open(io.BytesIO(r.read())).convert("RGB")
        elif reference_url:
            self.ref_img = Image.open(reference_url).convert("RGB")
        self.t0, self.done, self.tasks = time.time(), 0, {}

    def start(self):
        n_place = sum(len(a["objects"]) for a in self.assets.values())
        self.report("prop_references", f"{len(self.assets)} unique props ({n_place} placements)", 0.0)
        for a in self.assets.values():
            a["pending"] = True
            self.tasks[a["id"]] = asyncio.create_task(self._one(a))
        self.snapshot()

    async def _one(self, a):
        try:
            await _reference(a, self.ref_img, self.out_dir)
            # live UI: the prop shelf gets this prop's reference image as soon as it exists
            self.report("prop_references", f"{a['id']} reference ready", None,
                        prop={"id": a["id"], "label": a["label"], "ref_url": a["ref_url"], "status": "meshing"})
            a["meshes"] = dict(await asyncio.gather(*[_mesh(a, m, self.out_dir) for m in pick_model(a, self.tier)]))
        except Exception as e:
            a["failed"], a["error"] = True, str(e)[:200]
        a["pending"] = False
        self.done += 1
        model = next(iter(a.get("mesh_urls", {})), None)
        self.report("generating_meshes", f"{self.done} of {len(self.assets)} props have meshes",
                    self.done / len(self.assets),
                    prop={"id": a["id"], "label": a["label"], "ref_url": a.get("ref_url"), "model": model,
                          "mesh_url": a.get("mesh_urls", {}).get(model),
                          "status": "failed" if a.get("failed") else "done"})
        self.snapshot()

    async def wait(self, timeout_s: float | None) -> int:
        """Wait until everything is done or timeout_s passes; returns how many assets are still pending."""
        pending = [t for t in self.tasks.values() if not t.done()]
        if pending:
            await asyncio.wait(pending, timeout=timeout_s)
        left = sum(not t.done() for t in self.tasks.values())
        self.report("generating_meshes", f"{self.done} of {len(self.assets)} done after {time.time() - self.t0:.0f} s"
                    + (f", {left} still running (stand-ins for now)" if left else ""), self.done / len(self.assets))
        return left

    def snapshot(self):
        with open(os.path.join(self.out_dir, "assets.json"), "w", encoding="utf-8") as f:
            json.dump({"assets": self.assets}, f, indent=1)


async def generate(plan: Plan, reference_url: str, out_dir: str, tier: str, report) -> dict[str, dict]:
    """Everything at once and wait for all of it (used for tests and the full tier)."""
    g = Generation(plan, reference_url, out_dir, tier, report)
    g.start()
    await g.wait(None)
    return g.assets
