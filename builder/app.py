"""AnyScene scene builder as a fal Serverless app: one request = one Claude agent building the whole scene on a GPU worker.

    fal deploy builder/app.py::SceneBuilderApp --app-name anyscene-builder --auth private
    python builder/client.py <reference image path or url> [...] [--prompt "..."]

POST /build  reference images (+ prompt)  ->  stills, scene.blend, scene.glb, panoramas, package, critic rounds.
The agent (scene_builder.py) streams ANYSCENE_STAGE lines that the fal queue relays to the caller as logs: every tool
call, every report with its image, every critique. There is no time budget: it ends when the critic passes (or stalls).
"""

import json
import os
import sys
from pathlib import PurePosixPath

import fal
from fal.container import ContainerImage
from pydantic import BaseModel, Field

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "endpoint"))
import planner  # noqa: E402  (the critic's Claude client; bundled by value)
import scene_builder  # noqa: E402
import shots  # noqa: E402
import gallery  # noqa: E402  (the shared builds gallery: /builds, /build_events)
import schema  # noqa: E402,F401

if os.name == "nt":
    # Deploying from Windows: ContainerImage's context_dir default is a WindowsPath Linux can't unpickle.
    _posix = PurePosixPath("/tmp")
    ContainerImage.__dataclass_fields__["context_dir"].default = _posix
    ContainerImage.context_dir = _posix
    ContainerImage.__init__.__defaults__ = tuple(
        _posix if isinstance(d, os.PathLike) else d for d in ContainerImage.__init__.__defaults__ or ()
    )

TOOLKIT = scene_builder.toolkit_files()  # SKILL.md, CRAFT.md, prompt, shared tools: carried in the app
BLENDER_GPU = open(os.path.join(_HERE, "blender_gpu.py"), encoding="utf-8").read()
# `blender` on the worker: every launch loads blender_gpu.py first, so Cycles is on the GPU however it is called
# OptiX compiles its kernels on a worker's first Cycles render (~2 min on a 5090) into a local sqlite cache. Keep that
# cache on /data so new workers start with it, and warm it in setup() so no build waits for it.
OPTIX_CACHE_LOCAL = "/var/tmp/OptixCache_root/optix7cache.db"
OPTIX_CACHE_SHARED = "/data/anyscene/cache/optix7cache.db"
WARMUP = """import bpy
s = bpy.context.scene
s.render.engine = "CYCLES"; s.cycles.samples = 4; s.render.resolution_x = s.render.resolution_y = 64
for name, kind in (("glass", "BSDF_GLASS"), ("emit", "EMISSION")):
    m = bpy.data.materials.new(name); m.use_nodes = True
    m.node_tree.nodes.new("ShaderNodeEmission" if kind == "EMISSION" else "ShaderNodeBsdfGlass")
bpy.ops.mesh.primitive_cube_add(size=4)
haze = bpy.data.materials.new("haze"); haze.use_nodes = True
out = haze.node_tree.nodes["Material Output"]
vol = haze.node_tree.nodes.new("ShaderNodeVolumePrincipled")
haze.node_tree.links.new(vol.outputs[0], out.inputs["Volume"])
bpy.context.object.data.materials.append(haze)
bpy.ops.mesh.primitive_uv_sphere_add(location=(0, 0, 0.5))
bpy.context.object.data.materials.append(bpy.data.materials["glass"])
bpy.ops.render.render()
print("WARMUP done")
"""


def save_optix_cache():
    """Copy this worker's OptiX cache to /data if it has grown (atomic replace; concurrent workers just race)."""
    import shutil
    if os.path.exists(OPTIX_CACHE_LOCAL) and (not os.path.exists(OPTIX_CACHE_SHARED)
                                              or os.path.getsize(OPTIX_CACHE_LOCAL) > os.path.getsize(OPTIX_CACHE_SHARED)):
        os.makedirs(os.path.dirname(OPTIX_CACHE_SHARED), exist_ok=True)
        tmp = f"{OPTIX_CACHE_SHARED}.{os.getpid()}.tmp"
        shutil.copy(OPTIX_CACHE_LOCAL, tmp)
        os.replace(tmp, OPTIX_CACHE_SHARED)


BLENDER_WRAPPER = '#!/bin/sh\nexec /usr/local/bin/blender.real --python /opt/anyscene/blender_gpu.py "$@"\n'
BUILDS_DIR = "/data/anyscene/builder"
# /ref2scene's optional `shots` go to the AnyShot app (anyshot/app.py) named by ANYSHOT_APP, a fal secret on your own
# account (e.g. <your-fal-username>/anyshot). No default: an unset name says so instead of calling someone else's app.
ANYSHOT_APP_ENV = "ANYSHOT_APP"
SHOTS_WAIT_S = 7200 - 300  # wait for AnyShot until 5 min before this request's cap, then return its request_id
BLENDER_VERSION = "5.0.1"

DOCKERFILE = f"""
FROM python:3.13-slim
ENV NVIDIA_DRIVER_CAPABILITIES=all
RUN apt-get update && apt-get install -y --no-install-recommends \\
      curl ca-certificates xz-utils git procps fonts-dejavu-core libxi6 libxxf86vm1 libxfixes3 libxrender1 libgl1 \\
      libegl1 libxkbcommon0 libsm6 libice6 libx11-6 libglib2.0-0 ffmpeg nodejs ripgrep zip \\
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://download.blender.org/release/Blender{BLENDER_VERSION[:3]}/blender-{BLENDER_VERSION}-linux-x64.tar.xz \\
      | tar -xJ -C /opt \\
    && ln -s /opt/blender-{BLENDER_VERSION}-linux-x64/blender /usr/local/bin/blender.real
"""


class Shot(BaseModel):
    name: str = Field("", description="A camera or move from the build's shots.json (its scouting previews), or a new name.")
    description: str = Field("", description="The shot in words, e.g. 'slow push along the pastry case, ending close on "
                                             "the croissants'. With a name, it adjusts that camera.")


class BuildShots(BaseModel):
    """/ref2scene's optional shots order: once the build passes, the AnyShot app shoots it."""
    mode: str = Field("images", description="images: finished stills. video: camera moves, rendered on the farm.")
    shots: list[Shot] = Field(description="The shots to make: scouting camera names or descriptions in words.")
    settings: dict = Field(default_factory=dict, description="As /scene2video's settings (res, fps, seconds, ...).")
    dials: dict[str, float | str] = Field(default_factory=dict, description="Changes for these shots only.")


class BuildRequest(BaseModel):
    reference_image_urls: list[str] = Field(description="1-4 reference images: the look to build.")
    prompt: str = Field("", description="Anything the images can't show.")
    floor_plan_url: str | None = Field(None, description="Optional floor plan: a sketch, photo or drawing of the layout.")
    fresh: bool = Field(False, description="Build again from scratch even if an identical request already has a build.")
    effort: str = Field("medium", description="Claude effort for the builder: low, medium, high, xhigh, max.")
    scene: str = Field("scene", description="Folder name for the scene inside the build.")
    dials: dict[str, float | str] = Field(default_factory=dict, description=(
        "Scene dials (docs/ENDPOINT.md); any left out are read from the reference. density, tidiness, wear, wetness, "
        "atmosphere, power: 0-1. warmth: -1 (cold) to 1 (warm). time_of_day: dawn|day|dusk|night. "
        "weather: clear|overcast|rain|fog|snow. look: clean|cinematic|gritty|vintage."))
    shots: BuildShots | None = Field(None, description=(
        "Optional: shots of the finished set. When the build passes its critic, the AnyShot app (ANYSHOT_APP) shoots "
        "them and the stills/videos come back in shot_stills / shot_videos."))


class BuildResponse(BaseModel):
    build_id: str
    stills: list[str]
    scene_blend_url: str | None
    scene_glb_url: str | None
    panorama_urls: list[str]
    previews: list[dict] = Field(default_factory=list, description="The scouting previews: name (a camera in shots.json, usable in /shots), url.")
    package_url: str | None
    critiques: list[dict]
    dials: dict = Field(default_factory=dict, description="Every dial as built, with what it controls (out/dials.json).")
    missing: list[str]
    agent_cost_usd: float | None
    minutes: float
    shot_stills: list[str] = Field(default_factory=list, description="With `shots`: the stills AnyShot made.")
    shot_videos: list[str] = Field(default_factory=list, description="With `shots`: the videos AnyShot made.")
    shots_job: dict | None = Field(None, description=(
        "With `shots`: the AnyShot request (app, route, request_id, status, job_id, missing, error). If it was still "
        "running when this request had to return, fetch its result from the fal queue with request_id."))


class ShotsRequest(BaseModel):
    build_id: str = Field(description="A finished build from /build.")
    mode: str = Field("images", description="images: finished stills. video: animated shots, rendered on the farm.")
    shots: list[Shot] = Field(description="The shots to make.")
    settings: dict = Field(default_factory=dict, description=(
        "Optional: res [w, h], samples, fps, seconds (per video shot), lens_mm, handheld (none|walk|subtle), "
        "look (clean|cinematic|gritty|vintage). Missing ones are chosen per shot."))
    dials: dict[str, float | str] = Field(default_factory=dict, description=(
        "Optional changes to the set for this order only (time_of_day, atmosphere, power, warmth, wetness, ...); "
        "the build itself is never changed."))
    effort: str = Field("medium", description="Claude effort for the shots agent.")


class SceneShotsRequest(BaseModel):
    """/scene2image and /scene2video: a ShotsRequest whose route sets the mode."""
    build_id: str = Field(description="A finished build from /ref2scene.")
    shots: list[Shot] = Field(description="The shots to make.")
    settings: dict = Field(default_factory=dict, description=(
        "Optional: res [w, h], samples, fps, seconds (per video shot), lens_mm, handheld (none|walk|subtle), "
        "look (clean|cinematic|gritty|vintage). Missing ones are chosen per shot."))
    dials: dict[str, float | str] = Field(default_factory=dict, description=(
        "Optional changes to the set for this order only; the build itself is never changed."))
    effort: str = Field("medium", description="Claude effort for the shots agent.")


class ShotsResponse(BaseModel):
    job_id: str
    stills: list[str]
    videos: list[str]
    result: dict
    missing: list[str]
    agent_cost_usd: float | None
    minutes: float


class GalleryRequest(BaseModel):
    limit: int = Field(200, description="Most builds to list, newest first.")


class BuildEventsRequest(BaseModel):
    build_id: str = Field(description="A build id (b_...) from /builds.")
    after: int = Field(0, description="Byte offset into the build's event stream: 0, then the previous call's `next`.")
    heartbeats: bool = Field(False, description="Include every heartbeat (default: only the newest in each page).")


class SceneBuilderApp(fal.App):
    machine_type = ["GPU-RTX5090", "GPU-RTXPRO6000"]
    image = ContainerImage.from_dockerfile_str(DOCKERFILE)
    requirements = ["pydantic", "anthropic", "pillow", "fal==1.84.0", "fal-client", "claude-agent-sdk==0.2.176"]
    local_python_modules = ["scene_builder", "shots", "planner", "schema", "gallery"]
    min_concurrency = 0
    max_concurrency = 10
    request_timeout = 7200  # fal's cap; longer builds resume in a second request
    startup_timeout = 1200

    def setup(self):
        os.makedirs("/opt/anyscene", exist_ok=True)
        with open("/opt/anyscene/blender_gpu.py", "w") as f:
            f.write(BLENDER_GPU)
        with open("/usr/local/bin/blender", "w") as f:
            f.write(BLENDER_WRAPPER)
        os.chmod("/usr/local/bin/blender", 0o755)
        import shutil
        import subprocess
        import time
        if os.path.exists(OPTIX_CACHE_SHARED):
            os.makedirs(os.path.dirname(OPTIX_CACHE_LOCAL), exist_ok=True)
            shutil.copy(OPTIX_CACHE_SHARED, OPTIX_CACHE_LOCAL)
        t = time.time()
        r = subprocess.run(["blender", "-b", "--factory-startup", "--python-expr", WARMUP], capture_output=True, text=True,
                           timeout=900)
        print(f"setup: OptiX warm-up {'ok' if 'WARMUP done' in r.stdout else 'FAILED'} in {time.time() - t:.0f} s", flush=True)
        save_optix_cache()

    # Public routes follow fal's <owner>/<app>/<route> naming (target: fal-ai/anyscene/ref2scene, /scene2image,
    # /scene2video); /build and /shots stay as aliases for existing clients.
    @fal.endpoint("/ref2scene")
    async def ref2scene(self, req: BuildRequest) -> BuildResponse:
        """Reference images (+ optional floor plan, prompt, dials, shots) -> a production-ready 3D set."""
        return await self._build_and_shoot(req)

    @fal.endpoint("/build")
    async def build(self, req: BuildRequest) -> BuildResponse:
        return await self._build_and_shoot(req)

    async def _build_and_shoot(self, req: BuildRequest) -> BuildResponse:
        import time
        t0 = time.time()
        res = await self._build(req)  # the build's fingerprint leaves out `shots`: one build serves any shots order
        if req.shots and req.shots.shots:
            await self._anyshot(req, res, t0)
        return res

    async def _anyshot(self, req: BuildRequest, res: BuildResponse, t0: float):
        """Hand a passed build to the AnyShot app and wait for it while this request has time left. AnyShot is
        retry-safe on its side, so a retry of this request attaches to the same shots job instead of a second one."""
        import asyncio
        import time

        import fal_client

        app = os.environ.get(ANYSHOT_APP_ENV, "").strip().strip("/")
        route = "scene2video" if req.shots.mode == "video" else "scene2image"
        res.shots_job = {"app": app, "route": route, "status": "skipped"}
        if not app:
            res.shots_job["error"] = (f"no AnyShot app configured: set the fal secret {ANYSHOT_APP_ENV}="
                                      "<your-fal-username>/anyshot and redeploy")
            return
        last = res.critiques[-1] if res.critiques else {}
        if not (last.get("passed") and res.scene_blend_url):
            res.shots_job["error"] = "the build did not pass its critic (or has no scene.blend): no shots"
            return
        say = lambda status, msg, **kw: print(scene_builder.PREFIX + json.dumps(
            {"t": round(time.time() - t0, 1), "stage": "shots", "status": status, "message": msg, **kw}), flush=True)
        try:
            client = fal_client.AsyncClient(key=os.environ.get("FAL_SERVERLESS_KEY") or os.environ.get("FAL_KEY"))
            handle = await client.submit(f"{app}/{route}", arguments={
                "build_id": res.build_id, "shots": [s.model_dump() for s in req.shots.shots],
                "settings": req.shots.settings, "dials": req.shots.dials, "effort": req.effort})
            res.shots_job.update(request_id=handle.request_id, status="running")
            say("running", f"AnyShot {route}: {len(req.shots.shots)} shot(s) on {res.build_id}",
                request_id=handle.request_id)
            deadline = t0 + SHOTS_WAIT_S
            seen = set()
            while time.time() < deadline:
                st = await handle.status(with_logs=True)
                for log in getattr(st, "logs", None) or []:  # relay AnyShot's stage lines into this build's log
                    msg = log.get("message", "")
                    if scene_builder.PREFIX in msg and msg not in seen:
                        seen.add(msg)
                        print(msg, flush=True)
                if isinstance(st, fal_client.Completed):
                    out = await handle.get()
                    res.shot_stills, res.shot_videos = out.get("stills", []), out.get("videos", [])
                    res.shots_job.update(status="done", job_id=out.get("job_id"), missing=out.get("missing", []))
                    say("done", f"AnyShot: {len(res.shot_stills)} stills, {len(res.shot_videos)} videos")
                    return
                await asyncio.sleep(15)
            say("running", f"AnyShot is still running; fetch request {handle.request_id} from {app} when it finishes")
        except Exception as e:  # the build itself is delivered either way
            res.shots_job.update(status="failed", error=f"{type(e).__name__}: {str(e)[:300]}")
            say("running", f"AnyShot call failed: {res.shots_job['error']}")

    @fal.endpoint("/scene2image")
    async def scene2image(self, req: SceneShotsRequest) -> ShotsResponse:
        """Finished stills of a built scene: picked scouting previews or shots described in words."""
        return await self._shots(ShotsRequest(**req.model_dump(), mode="images"))

    @fal.endpoint("/scene2video")
    async def scene2video(self, req: SceneShotsRequest) -> ShotsResponse:
        """Camera moves through a built scene, rendered on the render farm."""
        return await self._shots(ShotsRequest(**req.model_dump(), mode="video"))

    async def _build(self, req: BuildRequest) -> BuildResponse:
        import time
        import urllib.request
        import uuid
        import zipfile

        from fal.toolkit import File

        import asyncio
        import hashlib

        t0 = time.time()
        # Retry-safe: fal's queue re-runs a request that times out or loses its worker. Each identical request maps
        # to one build; a repeat returns the finished result, waits for a live attempt, or resumes a dead one in the
        # same workspace, where nothing already generated is paid for again (generate/fal.mjs skips and resumes).
        fp = hashlib.sha256(json.dumps({"refs": req.reference_image_urls, "prompt": req.prompt, "dials": req.dials,
                                        "floor_plan": req.floor_plan_url, "scene": req.scene, "effort": req.effort},
                                       sort_keys=True).encode()).hexdigest()[:20]
        index = os.path.join(BUILDS_DIR, "_index", fp + ".json")
        os.makedirs(os.path.dirname(index), exist_ok=True)
        resume = False
        if not req.fresh and os.path.exists(index):
            told = False
            while True:
                rec = json.load(open(index))
                if rec.get("response"):
                    print(scene_builder.PREFIX + json.dumps({"t": 0, "stage": "done", "status": "done", "message":
                          f"identical request: returning finished build {rec['build_id']}"}), flush=True)
                    return BuildResponse(**rec["response"])
                alive = os.path.join(BUILDS_DIR, rec["build_id"], "out", ".alive")
                if not os.path.exists(alive) or time.time() - os.path.getmtime(alive) > 90:
                    break  # its attempt died: resume it below
                if not told:
                    print(scene_builder.PREFIX + json.dumps({"t": 0, "stage": "received", "status": "running", "message":
                          f"identical request: attached to build {rec['build_id']}, still running"}), flush=True)
                    told = True
                await asyncio.sleep(20)
            build_id, resume = rec["build_id"], True
        else:
            build_id = "b_" + uuid.uuid4().hex[:10]
            json.dump({"build_id": build_id, "fingerprint": fp, "started": time.time()}, open(index, "w"))
        work = os.path.join(BUILDS_DIR, build_id)
        os.makedirs(os.path.join(work, "out"), exist_ok=True)

        async def keep_alive():  # proves this attempt is alive to any retry of the same request
            while True:
                open(os.path.join(work, "out", ".alive"), "w").close()
                await asyncio.sleep(20)
        alive_task = asyncio.create_task(keep_alive())
        try:
            return await self._build_in(req, build_id, work, index, resume, t0)
        finally:
            alive_task.cancel()

    async def _build_in(self, req, build_id, work, index, resume, t0) -> BuildResponse:
        import time
        import urllib.request
        import zipfile

        from fal.toolkit import File

        os.makedirs(os.path.join(work, "input"), exist_ok=True)
        upload = lambda p: File.from_path(p).url
        refs = []
        if resume:  # the workspace is there: refresh the shared tools, keep the scene's own scripts and assets
            for rel, text in TOOLKIT.items():
                path = os.path.join(work, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
        for i, url in enumerate([] if resume else req.reference_image_urls[:4]):
            path = os.path.join(work, "input", f"src_{i + 1}")
            urllib.request.urlretrieve(url, path)
            refs.append(path)
        # references as PNG whatever came in
        from PIL import Image
        pngs = []
        for i, p in enumerate(refs):
            out = os.path.join(work, f"ref_{i + 1}.png")
            Image.open(p).convert("RGB").save(out)
            pngs.append(out)
        if not resume:
            scene_builder.make_workspace(work, pngs, req.prompt, req.scene, TOOLKIT, req.dials)
        if req.floor_plan_url and not resume:  # the agent reads it as input/floor_plan.png
            fp = os.path.join(work, "input", "floor_plan_src")
            urllib.request.urlretrieve(req.floor_plan_url, fp)
            Image.open(fp).convert("RGB").save(os.path.join(work, "input", "floor_plan.png"))
        refs = sorted(os.path.join(work, "input", f) for f in os.listdir(os.path.join(work, "input"))
                      if f.startswith("reference_"))

        b = scene_builder.SceneBuilder(work, refs, req.scene, uploader=upload, effort=req.effort)
        if resume:
            b.ASK = ("This build was cut off (its request was retried) and is resuming in the same workspace. Read "
                     "out/builder.log, out/events.jsonl and scenes/*/NOTES.md to see how far it got. Everything already "
                     "generated is on disk, and generate/fal.mjs skips finished outputs and picks up jobs that were in "
                     "flight, so re-running your batch scripts costs nothing for done items. Don't start over: continue "
                     "from the current state to the deliverables.")
        b.emit("received", "running", f"{'resuming' if resume else 'build'} {build_id}: {len(refs)} reference image(s)",
               reference_urls=req.reference_image_urls, prompt=req.prompt, dials=req.dials, effort=req.effort,
               floor_plan_url=req.floor_plan_url)
        result = None
        try:
            result = await b.run(scene_builder.agent_env())
        except Exception as e:  # deliver whatever exists rather than a bare 500
            import traceback
            print(traceback.format_exc(), flush=True)
            b.emit("error", "failed", f"build stopped: {type(e).__name__}: {str(e)[:300]}")

        out = os.path.join(work, "out")
        stills = [upload(os.path.join(out, "stills", f)) for f in sorted(os.listdir(os.path.join(out, "stills")))
                  if f.lower().endswith((".png", ".jpg"))]
        url_if = lambda p: upload(p) if os.path.exists(p) else None
        pano_dir = os.path.join(out, "panoramas")
        panos = [upload(os.path.join(pano_dir, f)) for f in sorted(os.listdir(pano_dir))] if os.path.isdir(pano_dir) else []
        prev_dir = os.path.join(out, "previews")
        previews = [{"name": os.path.splitext(f)[0], "url": upload(os.path.join(prev_dir, f))}
                    for f in sorted(os.listdir(prev_dir)) if f.lower().endswith((".png", ".jpg"))]             if os.path.isdir(prev_dir) else []
        pkg = os.path.join(work, f"{build_id}.zip")
        with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as z:
            for root, dirs, names in os.walk(out):
                # shot jobs (frames, their own copies of the set) and ungraded raw renders are not the deliverable
                dirs[:] = [d for d in dirs if d not in ("shots", "raw")]
                for n in names:
                    z.write(os.path.join(root, n), os.path.relpath(os.path.join(root, n), work))
            scripts = os.path.join(work, "scenes", req.scene)
            for root, _, names in os.walk(scripts):
                for n in names:
                    if n.endswith((".py", ".json", ".md", ".sh")):
                        z.write(os.path.join(root, n), os.path.relpath(os.path.join(root, n), work))
        res = BuildResponse(
            build_id=build_id, stills=stills, scene_blend_url=url_if(os.path.join(out, "scene.blend")),
            scene_glb_url=url_if(os.path.join(out, "scene.glb")), panorama_urls=panos, previews=previews, package_url=upload(pkg),
            critiques=[{k: c[k] for k in ("round", "scores", "passed", "summary", "fixes")} for c in b.critiques],
            dials=json.load(open(os.path.join(out, "dials.json"))) if os.path.exists(os.path.join(out, "dials.json")) else {},
            missing=b.missing(), agent_cost_usd=getattr(result, "total_cost_usd", None),
            minutes=round((time.time() - t0) / 60, 1))
        save_optix_cache()
        b.emit("packaged", "done", f"package ready after {res.minutes:.0f} min", package_url=res.package_url)
        rec = json.load(open(index))  # a repeat of this request now gets this result instead of a new build
        rec.update(response=res.model_dump(), finished=time.time())
        json.dump(rec, open(index, "w"))
        await __import__("asyncio").sleep(2)  # let the last stage lines reach the queue logs before COMPLETED
        return res

    @fal.endpoint("/shots")
    async def shots(self, req: ShotsRequest) -> ShotsResponse:
        return await self._shots(req)

    async def _shots(self, req: ShotsRequest) -> ShotsResponse:
        """Scene to images / scene to video: an agent shoots a finished build (see builder/SHOTS.md)."""
        import time
        import uuid

        from fal.toolkit import File

        t0 = time.time()
        if not req.build_id.replace("_", "").isalnum():
            raise ValueError("bad build_id")
        work = os.path.join(BUILDS_DIR, req.build_id)
        try:
            scene = shots.build_scene_name(work)
        except ValueError as e:
            raise ValueError(f"build {req.build_id}: {e}")
        # older builds carry older tools: refresh the toolkit (never the scene's own scripts or outputs)
        shots.write_toolkit(work, TOOLKIT)
        job_id = "j_" + uuid.uuid4().hex[:8]
        upload = lambda p: File.from_path(p).url
        # the same agent and tools as the AnyShot app (anyshot/app.py), on the build's own workspace
        request = {**req.model_dump(), "source": {"kind": "build", "build_id": req.build_id}}
        d, out = await shots.shoot(work, scene, job_id, request, upload, effort=req.effort)
        res = ShotsResponse(**out, minutes=round((time.time() - t0) / 60, 1))
        save_optix_cache()
        d.emit("packaged", "done", f"{len(res.stills)} stills, {len(res.videos)} videos after {res.minutes:.0f} min",
               stills=res.stills, videos=res.videos)
        await __import__("asyncio").sleep(2)
        return res

    # The shared builds gallery: every build anyone ran, read from storage (the fal queue only shows a request to the
    # key that submitted it). Light and read-only; see builder/gallery.py.
    @fal.endpoint("/builds")
    async def builds(self, req: GalleryRequest) -> dict:
        """Every build on this app's storage, newest first: status, inputs, critic, cover and preview URLs."""
        import asyncio
        return await asyncio.to_thread(gallery.list_builds, BUILDS_DIR, "scene", max(1, min(req.limit, 1000)))

    @fal.endpoint("/build_events")
    async def build_events(self, req: BuildEventsRequest) -> dict:
        """One build's stage events from byte offset `after` (poll with `next` to follow a running build), its summary,
        and on the first page of a finished build its response."""
        import asyncio

        from fal.toolkit import File
        return await asyncio.to_thread(gallery.build_events, BUILDS_DIR, req.build_id, req.after, "scene",
                                       req.heartbeats, 8 << 20, lambda p: File.from_path(p).url)

    @fal.endpoint("/smoke")
    async def smoke(self, req: BuildRequest) -> dict:
        """Container check: tools present, the agent starts, can run Bash/Blender/node and see an image."""
        import subprocess
        vers = {c[0]: subprocess.run(c, capture_output=True, text=True).stdout.splitlines()[:1]
                for c in (["blender", "--version"], ["node", "--version"], ["ffmpeg", "-version"], ["nvidia-smi", "-L"])}
        from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, TextBlock
        work = "/tmp/smoke"
        os.makedirs(work, exist_ok=True)
        said, cost = [], None
        opts = ClaudeAgentOptions(model=scene_builder.MODEL, effort="low", permission_mode="bypassPermissions", cwd=work,
                                  setting_sources=[], settings='{"fastMode": true}', env=scene_builder.agent_env())
        async with ClaudeSDKClient(opts) as c:
            await c.query("Run `blender -b --python-expr \"import bpy; print('BPY', bpy.app.version_string)\"` and "
                          "`node -e \"console.log(typeof fetch)\"`, then reply with both outputs in one line.")
            async for m in c.receive_response():
                if isinstance(m, AssistantMessage):
                    said += [b.text for b in m.content if isinstance(b, TextBlock)]
                elif isinstance(m, ResultMessage):
                    cost = m.total_cost_usd
        # the critic runs in this process (not the agent's): check it imports and answers here too
        from PIL import Image
        Image.new("RGB", (256, 128), (40, 60, 50)).save(f"{work}/plate.png")
        try:
            crit = scene_builder.run_critic([f"{work}/plate.png"], [f"{work}/plate.png"])
            critic = {"ok": True, "scores": crit["scores"]}
        except Exception as e:
            critic = {"ok": False, "error": f"{type(e).__name__}: {e}"[:300]}
        return {"versions": vers, "agent": said[-1] if said else None, "cost": cost, "critic": critic}
