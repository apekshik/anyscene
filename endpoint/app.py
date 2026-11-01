"""AnyScene reference-to-scene, as a fal Serverless app (see docs/ENDPOINT.md).

    fal deploy endpoint/app.py::AnyScene --app-name anyscene --auth private
    python endpoint/client.py plan <reference image url or path> [...]      streams the stage events

POST /plan   reference images (+ optional floor plan, prompt), or plan_id + edit/plan  ->  plan, floor plan, blockout
             renders, side-by-side comparison. Plans are kept under /data so /build and later edits can reload them.
Each request prints stage events (stages.py) that the fal queue streams to the caller as logs.
"""

import json
import os
import subprocess
import sys
import uuid
from pathlib import PurePosixPath

import fal
from fal.container import ContainerImage
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import floorplan  # noqa: E402
import planner  # noqa: E402
import props  # noqa: E402  (bundled by value, so it must be imported here, not inside a route)
import refine  # noqa: E402
from schema import Plan  # noqa: E402
from stages import Stages  # noqa: E402

if os.name == "nt":
    # Deploying from Windows: ContainerImage's context_dir default is a WindowsPath that Linux can't unpickle
    # (same workaround as farm/app.py).
    _posix = PurePosixPath("/tmp")
    ContainerImage.__dataclass_fields__["context_dir"].default = _posix
    ContainerImage.context_dir = _posix
    ContainerImage.__init__.__defaults__ = tuple(
        _posix if isinstance(d, os.PathLike) else d for d in ContainerImage.__init__.__defaults__ or ()
    )

BLENDER_VERSION = "5.0.1"
# The Blender side runs as script files; carry their source in the app so the worker can write them out.
_HERE = os.path.dirname(os.path.abspath(__file__))
_read = lambda *p: open(os.path.join(_HERE, *p), encoding="utf-8").read()
BLENDER_SCRIPTS = {
    "blockout.py": _read("blockout.py"),
    "assemble.py": _read("assemble.py"),
    "refine_blender.py": _read("refine_blender.py"),
    "camera/camrig.py": _read("..", "camera", "camrig.py"),
    "camera/shoot.py": _read("..", "camera", "shoot.py"),
    "gpu_prefs.py": '''import bpy
prefs = bpy.context.preferences.addons["cycles"].preferences
for kind in ("OPTIX", "CUDA"):
    try:
        prefs.compute_device_type = kind
        prefs.get_devices()
        if any(d.type == kind for d in prefs.devices):
            for d in prefs.devices:
                d.use = d.type == kind
            break
    except TypeError:
        continue
for sc in bpy.data.scenes:
    sc.cycles.device = "GPU"
''',
}
SCRIPTS_DIR = "/tmp/anyscene_scripts"
SCENES_DIR = "/data/anyscene/scenes"

DOCKERFILE = f"""
FROM python:3.13-slim
ENV NVIDIA_DRIVER_CAPABILITIES=all
RUN apt-get update && apt-get install -y --no-install-recommends \\
      curl ca-certificates xz-utils fonts-dejavu-core libxi6 libxxf86vm1 libxfixes3 libxrender1 libgl1 libegl1 \\
      libxkbcommon0 libsm6 libice6 libx11-6 libglib2.0-0 \\
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://download.blender.org/release/Blender{BLENDER_VERSION[:3]}/blender-{BLENDER_VERSION}-linux-x64.tar.xz \\
      | tar -xJ -C /opt \\
    && ln -s /opt/blender-{BLENDER_VERSION}-linux-x64/blender /usr/local/bin/blender
"""

PLANS_DIR = "/data/anyscene/plans"


class PlanRequest(BaseModel):
    reference_image_urls: list[str] = Field(default_factory=list, description="1-4 reference images (the look).")
    floor_plan_url: str | None = Field(None, description="Optional sketch/photo/drawing of the layout.")
    prompt: str = Field("", description="Anything the images can't show.")
    plan_id: str | None = Field(None, description="Revise this plan instead of starting a new one.")
    edit: str = Field("", description="With plan_id: a change to apply, in words.")
    plan: dict | None = Field(None, description="With plan_id: a full replacement plan (edited JSON).")
    effort: str = Field("high", description="Claude effort for planning: low, medium, high, xhigh, max (fast mode is on).")


class PlanResponse(BaseModel):
    plan_id: str
    plan: dict
    floor_plan_url: str
    blockout_reference_url: str
    blockout_overview_url: str
    comparison_url: str
    timings: dict


def _save(plan_id: str, plan: Plan, refs: list[str], parent: str | None):
    os.makedirs(PLANS_DIR, exist_ok=True)
    with open(f"{PLANS_DIR}/{plan_id}.json", "w", encoding="utf-8") as f:
        json.dump({"plan": plan.model_dump(), "reference_image_urls": refs, "parent": parent}, f)


def _load(plan_id: str) -> dict:
    if not plan_id.replace("_", "").isalnum():
        raise ValueError("bad plan_id")
    with open(f"{PLANS_DIR}/{plan_id}.json", encoding="utf-8") as f:
        return json.load(f)


class BuildRequest(BaseModel):
    plan_id: str = Field(description="An approved plan from /plan.")
    tier: str = Field("draft", description="draft: one 3D model per prop, mesh deadline; full: both models, no deadline.")
    mesh_deadline_s: float = Field(480, description="Draft: start assembling with stand-ins after this long.")
    late_mesh_wait_s: float = Field(240, description="Draft: extra time for late meshes before packaging.")
    still_samples: int = Field(128, description="Cycles samples for the stills.")
    include_glbs: bool = Field(False, description="Also put every prop's full-resolution GLB in the package.")
    refine: bool = Field(True, description="Light screens, lamps and glowing panels, make glass clear, texture scripted pieces.")
    panoramas: bool = Field(True, description="Equirectangular Cycles panoramas from each camera, for the 360 view.")
    scene_glb: bool = Field(True, description="A web-weight scene.glb (decimated, 1K textures, lights) for the 360 view.")


class BuildResponse(BaseModel):
    scene_id: str
    package_url: str
    scene_blend_url: str
    stills: list[str]
    panorama_urls: dict = Field(default_factory=dict)
    scene_glb_url: str | None = None
    props: list[dict]
    standins_left: list[str]
    timings: dict


class AnyScene(fal.App):
    machine_type = ["GPU-RTX5090", "GPU-RTXPRO6000"]
    image = ContainerImage.from_dockerfile_str(DOCKERFILE)
    requirements = ["pydantic", "anthropic", "pillow", "fal==1.84.0", "fal-client"]
    local_python_modules = ["schema", "planner", "floorplan", "stages", "props", "refine"]
    min_concurrency = 0
    max_concurrency = 10
    request_timeout = 3600
    startup_timeout = 1200

    def setup(self):
        for rel, src in BLENDER_SCRIPTS.items():
            path = os.path.join(SCRIPTS_DIR, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(src)
        self.blockout_path = os.path.join(SCRIPTS_DIR, "blockout.py")

    @fal.endpoint("/build")
    async def build(self, req: BuildRequest) -> BuildResponse:
        import asyncio
        import shutil
        import time
        import zipfile

        from fal.toolkit import File


        st = Stages()
        t0 = time.time()
        timings = {}
        upload = lambda path, ctype: File.from_path(path, content_type=ctype).url

        async def blender(*args, timeout=1800):
            proc = await asyncio.to_thread(subprocess.run, ["blender", "-b", *args], capture_output=True, text=True,
                                           timeout=timeout)
            out = proc.stdout + proc.stderr
            if proc.returncode != 0:
                raise RuntimeError(f"blender failed ({proc.returncode}):\n{out[-2000:]}")
            return out

        try:
            st.start("received", f"build {req.plan_id} ({req.tier})")
            saved = _load(req.plan_id)
            plan = Plan.model_validate(saved["plan"])
            scene_id = "s_" + uuid.uuid4().hex[:10]
            work = os.path.join(SCENES_DIR, scene_id)
            os.makedirs(work, exist_ok=True)
            with open(f"{work}/plan.json", "w", encoding="utf-8") as f:
                json.dump(plan.model_dump(), f)

            # 1-2: every prop reference and mesh at once; per-prop events feed the UI's prop shelf
            report = lambda stage, msg, prog, **extra: st.emit(stage, "running", msg, prog, **extra)
            gen = props.Generation(plan, saved["reference_image_urls"][0], f"{work}/props", req.tier, report)
            gen.start()
            left = await gen.wait(req.mesh_deadline_s if req.tier == "draft" else None)
            timings["meshes_s"] = round(time.time() - t0, 1)
            st.done("generating_meshes", f"{gen.done} of {len(gen.assets)} props ready, {left} still running")

            # 3-4: assemble from the plan, stand-ins for anything not here yet
            st.start("layout", "building the scene from the plan")
            t1 = time.time()
            await blender("--factory-startup", "--python", f"{SCRIPTS_DIR}/assemble.py", "--",
                          "build", f"{work}/plan.json", f"{work}/props/assets.json", work)
            timings["assemble_s"] = round(time.time() - t1, 1)

            async def preview(name):
                # quick lit look from the reference camera for the live view
                cfg = json.load(open(f"{work}/shots.json"))
                cfg["defaults"].update(samples=16, res=[960, 402])
                cfg["shots"] = cfg["shots"][:1]
                json.dump(cfg, open(f"{work}/preview_shots.json", "w"))
                shutil.rmtree(f"{work}/preview", ignore_errors=True)
                await blender(f"{work}/scene.blend", "--python", f"{SCRIPTS_DIR}/gpu_prefs.py", "--python",
                              f"{SCRIPTS_DIR}/camera/shoot.py", "--", "--shots", f"{work}/preview_shots.json", "--out",
                              f"{work}/preview", "--frames", "1-1", "--no-encode")
                return upload(f"{work}/preview/ref_view/frames/0001.png", "image/png")

            st.done("layout", f"{len(plan.objects)} objects placed, {left} stand-ins", preview_url=await preview("layout"))

            # 5: give late meshes a little longer, then swap them in
            if left and req.tier == "draft":
                st.start("dressing", f"waiting up to {req.late_mesh_wait_s:.0f} s for {left} late meshes")
                left = await gen.wait(req.late_mesh_wait_s)
            gen.snapshot()
            out = await blender(f"{work}/scene.blend", "--python", f"{SCRIPTS_DIR}/assemble.py", "--",
                                "swap", f"{work}/props/assets.json", work)
            swap_line = next((l for l in out.splitlines() if l.startswith("assemble: swapped")), "")
            st.done("dressing", swap_line.replace("assemble: ", ""), preview_url=await preview("dressed"))

            # 5b: refine: Claude marks screens, glass, lamps and glowing panels on each prop's front view; screen
            # content and box textures are generated; Blender applies them
            if req.refine:
                st.start("refine", "finding screens, glass and lamps")
                t5 = time.time()
                await blender(f"{work}/scene.blend", "--python", f"{SCRIPTS_DIR}/refine_blender.py", "--",
                              "views", f"{work}/refine/views")
                await refine.build_refine(plan, gen.assets, f"{work}/refine/views", f"{work}/refine", report)
                out = await blender(f"{work}/scene.blend", "--python", f"{SCRIPTS_DIR}/refine_blender.py", "--",
                                    "apply", f"{work}/refine/refine.json", f"{work}/refined")
                os.replace(f"{work}/refined/scene.blend", f"{work}/scene.blend")
                line = next((l for l in out.splitlines() if l.startswith("refine: applied")), "refine: applied")
                timings["refine_s"] = round(time.time() - t5, 1)
                st.done("refine", line.replace("refine: ", ""), preview_url=await preview("refined"))

            # 6: final stills on this worker's GPU
            st.start("rendering", "stills from the reference camera and two open views")
            t2 = time.time()
            cfg = json.load(open(f"{work}/shots.json"))
            cfg["defaults"]["samples"] = req.still_samples
            json.dump(cfg, open(f"{work}/shots.json", "w"))
            await blender(f"{work}/scene.blend", "--python", f"{SCRIPTS_DIR}/gpu_prefs.py", "--python",
                          f"{SCRIPTS_DIR}/camera/shoot.py", "--", "--shots", f"{work}/shots.json", "--out",
                          f"{work}/renders", "--frames", "1-1", "--no-encode", timeout=1200)
            stills = []
            for shot in cfg["shots"]:
                src = f"{work}/renders/{shot['name']}/frames/0001.png"
                if os.path.exists(src):
                    url = upload(src, "image/png")
                    stills.append(url)
                    st.emit("rendering", "running", f"{shot['name']} done", preview_url=url)
            timings["render_s"] = round(time.time() - t2, 1)
            st.done("rendering", f"{len(stills)} stills")

            # 6b: panoramas (GPU) and the web scene.glb (CPU) side by side, for the 360 view
            panorama_urls, scene_glb_url = {}, None

            async def panoramas():
                await blender(f"{work}/scene.blend", "--python", f"{SCRIPTS_DIR}/gpu_prefs.py", "--python",
                              f"{SCRIPTS_DIR}/refine_blender.py", "--", "pano", f"{work}/shots.json", f"{work}/pano",
                              "--samples", "64", "--res", "2048", timeout=1200)
                for shot in cfg["shots"]:
                    src = f"{work}/pano/pano_{shot['name']}.png"
                    if os.path.exists(src):
                        panorama_urls[shot["name"]] = upload(src, "image/png")
                        st.emit("panoramas", "running", f"360 from {shot['name']}",
                                panorama_url=panorama_urls[shot["name"]], viewpoint=shot["name"])

            async def web_glb():
                nonlocal scene_glb_url
                await blender(f"{work}/scene.blend", "--python", f"{SCRIPTS_DIR}/refine_blender.py", "--", "glb",
                              f"{work}/web", "--tris", "60000", "--tex", "1024", timeout=1200)
                scene_glb_url = upload(f"{work}/web/scene.glb", "model/gltf-binary")
                st.emit("panoramas", "running", "scene.glb ready", scene_glb_url=scene_glb_url)

            if req.panoramas or req.scene_glb:
                st.start("panoramas", "360 panoramas and a web scene.glb")
                t6 = time.time()
                res = await asyncio.gather(*([panoramas()] if req.panoramas else []),
                                           *([web_glb()] if req.scene_glb else []), return_exceptions=True)
                errs = [str(r)[:200] for r in res if isinstance(r, Exception)]
                timings["panoramas_s"] = round(time.time() - t6, 1)
                st.done("panoramas", f"{len(panorama_urls)} panoramas, scene.glb {'ready' if scene_glb_url else 'skipped'}"
                        + (f" ({'; '.join(errs)})" if errs else ""))

            # 7: package
            st.start("packaging")
            t3 = time.time()
            pkg = f"{work}/scene_package.zip"
            with zipfile.ZipFile(pkg, "w", zipfile.ZIP_STORED) as z:
                z.write(f"{work}/scene.blend", "scene.blend")
                z.write(f"{work}/plan.json", "plan.json")
                z.write(f"{work}/props/assets.json", "manifest.json")
                z.write(f"{work}/shots.json", "shots.json")
                for shot in cfg["shots"]:
                    src = f"{work}/renders/{shot['name']}/frames/0001.png"
                    if os.path.exists(src):
                        z.write(src, f"renders/{shot['name']}.png")
                for a in gen.assets.values():
                    ref = f"{work}/props/{a['id']}_ref.png"
                    if os.path.exists(ref):
                        z.write(ref, f"props/{a['id']}_ref.png")
                    if req.include_glbs:
                        for path in (a.get("meshes") or {}).values():
                            if os.path.exists(path):
                                z.write(path, f"props/{a['id']}.glb")
                for name in ("web/scene.glb", "refine/refine.json"):
                    if os.path.exists(f"{work}/{name}"):
                        z.write(f"{work}/{name}", os.path.basename(name))
                for name in os.listdir(f"{work}/pano") if os.path.isdir(f"{work}/pano") else []:
                    z.write(f"{work}/pano/{name}", f"panoramas/{name}")
                z.writestr("README.md", f"# {plan.name}\n\n{plan.summary}\n\nBuilt by AnyScene reference-to-scene "
                                        f"({req.tier}). Open scene.blend in Blender 5.0+. plan.json is the layout; "
                                        f"manifest.json lists every prop, its reference and which 3D model made it.\n")
            package_url = upload(pkg, "application/zip")
            blend_url = upload(f"{work}/scene.blend", "application/octet-stream")
            timings["package_s"] = round(time.time() - t3, 1)
            timings["total_s"] = round(time.time() - t0, 1)
            standins = [a["id"] for a in gen.assets.values() if not a.get("meshes")]
            st.done("done", f"scene {scene_id} in {timings['total_s']:.0f} s", package_url=package_url)
            await asyncio.sleep(2)  # let the last stage lines reach the queue logs before COMPLETED
            return BuildResponse(
                scene_id=scene_id, package_url=package_url, scene_blend_url=blend_url, stills=stills,
                panorama_urls=panorama_urls, scene_glb_url=scene_glb_url,
                props=[{"id": a["id"], "label": a["label"], "ref_url": a.get("ref_url"),
                        "mesh_urls": a.get("mesh_urls", {}), "placements": a["objects"]} for a in gen.assets.values()],
                standins_left=standins, timings=timings)
        except Exception as e:
            st.fail(str(e)[:500])
            raise

    @fal.endpoint("/plan")
    def plan(self, req: PlanRequest) -> PlanResponse:
        import time

        from fal.toolkit import File
        from PIL import Image

        st = Stages()
        t = {}
        st.start("received", "plan request")
        try:
            t0 = time.time()
            parent = None
            if req.plan_id:
                prev = _load(req.plan_id)
                refs, parent = prev["reference_image_urls"], req.plan_id
                st.start("planning", "revising the plan")
                if req.plan:
                    plan = Plan.model_validate(req.plan)
                else:
                    plan = planner.edit_plan(Plan.model_validate(prev["plan"]), req.edit, refs, req.effort)
            else:
                if not req.reference_image_urls:
                    raise ValueError("reference_image_urls is required for a new plan")
                refs = req.reference_image_urls
                st.start("reading_reference", f"{len(refs)} reference image(s)"
                         + (" + floor plan" if req.floor_plan_url else ""))
                st.start("planning", f"laying out the whole space (effort {req.effort})")
                plan = planner.make_plan(refs, req.floor_plan_url, req.prompt, req.effort)
            t["planning_s"] = round(time.time() - t0, 1)
            n_inv = sum(o.source == "invented" for o in plan.objects)
            st.done("planning", f"{len(plan.objects)} objects ({n_inv} invented), {len(plan.lights)} lights, "
                                f"{plan.room.width:g} x {plan.room.depth:g} m {plan.setting}")

            plan_id = "p_" + uuid.uuid4().hex[:10]
            _save(plan_id, plan, refs, parent)
            work = f"/tmp/{plan_id}"
            os.makedirs(work, exist_ok=True)
            with open(f"{work}/plan.json", "w", encoding="utf-8") as f:
                json.dump(plan.model_dump(), f)

            st.start("drawing_floor_plan")
            floorplan.draw(plan, f"{work}/floor_plan.png", px_per_m=70 if max(plan.room.width, plan.room.depth) > 10 else 110)
            fp_url = File.from_path(f"{work}/floor_plan.png", content_type="image/png").url
            st.done("drawing_floor_plan", preview_url=fp_url)

            st.start("blockout", "grey-box renders from the reference camera and an overview")
            t1 = time.time()
            proc = subprocess.run(["blender", "-b", "--factory-startup", "--python", self.blockout_path, "--",
                                   f"{work}/plan.json", work, "--samples", "32", "--res", "1280"],
                                  capture_output=True, text=True, timeout=900)
            if proc.returncode != 0 or not os.path.exists(f"{work}/blockout_overview.png"):
                raise RuntimeError("blockout failed:\n" + (proc.stdout + proc.stderr)[-2000:])
            t["blockout_s"] = round(time.time() - t1, 1)
            ref_url = File.from_path(f"{work}/blockout_reference.png", content_type="image/png").url
            ov_url = File.from_path(f"{work}/blockout_overview.png", content_type="image/png").url

            # Side by side: the first reference image next to the grey-box from the reference camera.
            comp_path = f"{work}/comparison.png"
            right = Image.open(f"{work}/blockout_reference.png").convert("RGB")
            left = _fetch_image(refs[0]).convert("RGB").resize(right.size)
            comp = Image.new("RGB", (right.width * 2, right.height))
            comp.paste(left, (0, 0))
            comp.paste(right, (right.width, 0))
            comp.save(comp_path)
            comp_url = File.from_path(comp_path, content_type="image/png").url
            st.done("blockout", preview_url=comp_url)
            t["total_s"] = round(time.time() - t0, 1)
            st.done("done", f"plan {plan_id}")
            time.sleep(2)  # let the last stage lines reach the queue logs before COMPLETED
            return PlanResponse(plan_id=plan_id, plan=plan.model_dump(), floor_plan_url=fp_url,
                                blockout_reference_url=ref_url, blockout_overview_url=ov_url, comparison_url=comp_url,
                                timings=t)
        except Exception as e:
            st.fail(str(e)[:500])
            raise


def _fetch_image(url: str):
    import base64
    import io
    import urllib.request

    from PIL import Image

    if url.startswith("data:"):
        return Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
    with urllib.request.urlopen(url, timeout=60) as r:
        return Image.open(io.BytesIO(r.read()))
