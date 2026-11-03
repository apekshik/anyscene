"""blend2unreal: the AnyScene Blender -> Unreal export stage (export_blend.py) on fal Serverless, sharded.

    fal deploy unreal_fal/app.py::Blend2Unreal --app-name blend2unreal --auth private

POST /export  {scene_url, options}  ->  a zip of the export folder (mesh/, tex/, world/, grade/, scene.json), scene.json
              (inline and as a URL) and a report (counts, warnings, what didn't convert, timings, worker seconds).
POST /shard   one shard of an export (called by /export on other workers of this app; callable directly for benches).

How an export runs (TOGGLE.md section 5):
  1. plan   on the /export worker: `export_blend.py --plan-out` names and hashes every unique mesh (evaluated mesh +
            material node trees + bake settings + exporter code) and estimates its bake cost. No baking.
  2. shards assets whose hash is not in the bake cache (/data/blend2unreal/cache) are dealt to N shards by cost (LPT).
            Shard 0 runs on the /export worker itself; the rest go to /shard requests on other workers. Each shard runs
            a few Blender processes (`--keys`), bakes on OptiX and writes every finished asset into the cache.
  3. merge  `export_blend.py --plan --cache --link-cache --no-bake`: every asset comes from the cache, then volumes,
            lights, cameras, world and grade, and scene.json. The folder is zipped and put on fal storage.
A re-export of a lightly changed scene only bakes the assets whose hash changed. Identical requests are retry-safe as
in AnyShot: an index keyed by the request's fingerprint returns a finished result, attaches to a live attempt
(heartbeat), or resumes a dead one, re-attaching to its shard requests.

The scene is a .blend or a .zip holding one (and, optionally, the scene's grade.sh). Pack external images and fonts
into the .blend first: the worker has none of your local files.
"""

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request
import zipfile
from pathlib import PurePosixPath

import fal
from fal.container import ContainerImage
from pydantic import BaseModel, Field

if os.name == "nt":
    # Deploying from Windows: ContainerImage's context_dir default is a WindowsPath Linux can't unpickle.
    _posix = PurePosixPath("/tmp")
    ContainerImage.__dataclass_fields__["context_dir"].default = _posix
    ContainerImage.context_dir = _posix
    ContainerImage.__init__.__defaults__ = tuple(
        _posix if isinstance(d, os.PathLike) else d for d in ContainerImage.__init__.__defaults__ or ()
    )

_HERE = os.path.dirname(os.path.abspath(__file__))
EXPORTER = open(os.path.join(_HERE, "export_blend.py"), encoding="utf-8").read()  # carried in the app at deploy time

BLENDER_VERSION = "5.0.1"
DOCKERFILE = f"""
FROM python:3.13-slim
# Expose the driver's graphics libraries too: OptiX (libnvoptix) ships with them, not with plain compute.
ENV NVIDIA_DRIVER_CAPABILITIES=all
RUN apt-get update && apt-get install -y --no-install-recommends \\
      curl ca-certificates xz-utils procps ffmpeg libxi6 libxxf86vm1 libxfixes3 libxrender1 libgl1 libegl1 \\
      libxkbcommon0 libsm6 libice6 libx11-6 libglib2.0-0 \\
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://download.blender.org/release/Blender{BLENDER_VERSION[:3]}/blender-{BLENDER_VERSION}-linux-x64.tar.xz \\
      | tar -xJ -C /opt \\
    && ln -s /opt/blender-{BLENDER_VERSION}-linux-x64/blender /usr/local/bin/blender
"""

APP_ENV = "BLEND2UNREAL_APP"  # this app's own id, for the shard requests (default below)
DEFAULT_APP = "apek/blend2unreal"
LOCAL = "/tmp/blend2unreal"  # per-worker disk: scenes (never read from /data by many workers at once), job folders
EXPORT_PY = LOCAL + "/export_blend.py"
DATA = "/data/blend2unreal"
CACHE = DATA + "/cache"  # <hash[:2]>/<hash>/{mesh.glb, meta.json, base.png, orm.png, normal.png, emit.png(.json), ready}
INDEX = DATA + "/_index"  # <fingerprint>.json: the retry index
JOBS = DATA + "/jobs"  # <job_id>/{plan.json, .alive, logs}
# OptiX kernels compiled by the same Blender build on the same GPU model: shared with the render farm app.
OPTIX_CACHE_LOCAL_DIR = "/var/tmp/OptixCache_root"
OPTIX_CACHE_SHARED_DIR = "/data/anyscene-farm/optix"
WARMUP = """import bpy
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "OPTIX"
prefs.get_devices()
for d in prefs.devices:
    d.use = d.type == "OPTIX"
s = bpy.context.scene
s.render.engine = "CYCLES"; s.cycles.device = "GPU"; s.cycles.samples = 4
s.render.resolution_x = s.render.resolution_y = 64
bpy.ops.mesh.primitive_uv_sphere_add()
o = bpy.context.object
m = bpy.data.materials.new("m"); m.use_nodes = True; o.data.materials.append(m)
nt = m.node_tree; p = nt.nodes["Principled BSDF"]
# AO and Bevel nodes need OptiX's separate "shader raytrace" kernels: without them in the warm-up, the first bake of
# each Blender process on a fresh worker compiled them for ~230 s (19 of 32 HK shards).
ao = nt.nodes.new("ShaderNodeAmbientOcclusion"); bev = nt.nodes.new("ShaderNodeBevel")
nt.links.new(ao.outputs["Color"], p.inputs["Base Color"]); nt.links.new(bev.outputs["Normal"], p.inputs["Normal"])
img = bpy.data.images.new("t", 64, 64); n = nt.nodes.new("ShaderNodeTexImage"); n.image = img
nt.nodes.active = n
bpy.ops.render.render()
bpy.ops.object.bake(type="EMIT")
bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT")
print("WARMUP done")
"""

# Shard sizing. Cost model per Blender process from a 36-asset HK bench on an RTX 5090 worker (6 cores, 2 processes
# x 3 threads, OptiX): ~4 s of per-asset overhead (unwrap, scene sync, BVH, PNG writes: CPU-bound) plus ~1 s per
# 3.5 Mpx-channel baked. The same bench on the CPU device took 6x longer (median 17 s per asset; 354 s for the road).
ASSET_OVERHEAD_S = 4.0
PX_PER_S = 3.5e6
TARGET_SHARD_S = 120  # each Blender process gets ~2 min of baking: worker boot + scene fetch + load is ~1.5-2.5 min
DONE_MARK = {"plan": "EXPORT plan written", "shard": "EXPORT shard done", "merge": "EXPORT wrote"}


def stage(name, msg, **kw):
    print("BLEND2UNREAL " + json.dumps({"t": round(time.time(), 1), "stage": name, "message": msg, **kw}), flush=True)


def cost_s(row):
    return ASSET_OVERHEAD_S + row.get("est_px", 0) / PX_PER_S


def deal(rows, n):
    """Longest-processing-time first: rows split into n lists of about equal estimated cost."""
    bins = [[0.0, i, []] for i in range(max(1, n))]
    for r in sorted(rows, key=cost_s, reverse=True):
        b = min(bins, key=lambda b: (b[0], b[1]))
        b[0] += cost_s(r)
        b[2].append(r)
    return [b[2] for b in bins if b[2]]


def cache_ready(h, cache=CACHE):
    return os.path.exists(os.path.join(cache, h[:2], h, "ready"))


def cache_root(ns):
    """The shared bake cache, or (use_cache=False) a job-private one under /data/blend2unreal/scratch: a forced re-bake
    neither reads nor deletes shared entries (deleting 627 of them on /data took ~250 s)."""
    if not ns:
        return CACHE
    if not ns.replace("_", "").isalnum():
        raise ValueError("bad cache namespace")
    return f"{DATA}/scratch/{ns}"


def write_json(path, obj):
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


def _safe_extract(zpath, dest):
    with zipfile.ZipFile(zpath) as z:
        for m in z.infolist():
            name = m.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/") or ":" in name.split("/")[0] or "__MACOSX" in name:
                continue
            target = os.path.join(dest, *name.split("/"))
            if m.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(m) as src, open(target, "wb") as out:
                while chunk := src.read(8 << 20):
                    out.write(chunk)


def fetch_scene(scene_url):
    """Download a scene once per worker into local disk: a .blend as is, a .zip unpacked. Concurrent requests on the
    same worker wait on a lock. Returns the folder."""
    import fcntl  # Linux-only; `fal deploy` imports this module on Windows too

    sid = hashlib.sha256(scene_url.encode()).hexdigest()[:16]
    root = os.path.join(LOCAL, "inputs")  # not "scenes": export_blend.py refuses scenes/<id>/hk.blend
    dest = os.path.join(root, sid)
    if os.path.exists(os.path.join(dest, ".ready")):
        return dest
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, sid + ".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if os.path.exists(os.path.join(dest, ".ready")):
            return dest
        tmp = dest + ".part"
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp)
        raw = os.path.join(tmp, "download")
        with urllib.request.urlopen(scene_url, timeout=900) as r, open(raw, "wb") as f:
            while chunk := r.read(8 << 20):
                f.write(chunk)
        with open(raw, "rb") as f:
            head = f.read(8)
        unpacked = os.path.join(tmp, "scene")
        os.makedirs(unpacked)
        if head.startswith(b"PK\x03\x04"):
            _safe_extract(raw, unpacked)
            os.remove(raw)
        elif head.startswith((b"BLENDER", b"\x28\xb5\x2f\xfd", b"\x1f\x8b")):  # plain, zstd- or gzip-compressed
            os.replace(raw, os.path.join(unpacked, "scene.blend"))
        else:
            raise ValueError("scene_url must point to a .blend or a .zip holding one")
        shutil.rmtree(dest, ignore_errors=True)
        os.rename(unpacked, dest)
        shutil.rmtree(tmp, ignore_errors=True)
        open(os.path.join(dest, ".ready"), "w").close()
    return dest


def pick_blend(scene_dir, name=None):
    blends = sorted(os.path.relpath(os.path.join(r, n), scene_dir) for r, _, ns in os.walk(scene_dir)
                    for n in ns if n.lower().endswith(".blend"))
    if name:
        if name not in blends:
            raise ValueError(f"{name} is not in the scene zip ({blends[:10]})")
        return os.path.join(scene_dir, name)
    if not blends:
        raise ValueError("the scene holds no .blend file")
    # several: the biggest is the set (the others are usually linked props or backups)
    return max((os.path.join(scene_dir, b) for b in blends), key=os.path.getsize)


def run_blender(blend, args, log_path, mode, tries=6, timeout=3600, threads=0):
    """export_blend.py in Blender, resumed after crashes: Blender 5.0.1's Cycles bake segfaults about once per 250
    bakes (OpenImageIO ustring in ccl::create_mesh), and the exporter skips the assets it already finished."""
    for i in range(tries):
        start = os.path.getsize(log_path) if os.path.exists(log_path) else 0
        t = time.time()
        with open(log_path, "a") as lf:
            lf.write(f"\n=== {mode} try {i + 1}: blender -b {blend} -- {' '.join(args)}\n")
            lf.flush()
            try:
                t_args = ["-t", str(threads)] if threads else []
                p = subprocess.run(["blender", "-b", *t_args, blend, "--python", EXPORT_PY, "--", *args], stdout=lf,
                                   stderr=subprocess.STDOUT, timeout=timeout)
                rc = p.returncode
            except subprocess.TimeoutExpired:
                rc = "timeout"
        with open(log_path, errors="replace") as f:
            f.seek(start)
            out = f.read()
        if DONE_MARK[mode] in out:
            return out, round(time.time() - t, 1), i + 1
        if rc == 0:  # Blender exits 0 on a Python exception: a retry won't help
            raise RuntimeError(f"export_blend.py {mode} failed:\n{out[-3000:]}")
        print(f"blend2unreal: {mode} try {i + 1} ended rc={rc} without finishing; resuming", flush=True)
    raise RuntimeError(f"export_blend.py {mode} gave up after {tries} tries:\n{out[-3000:]}")


def machine_info():
    """(cores this container may use, RAM GB). os.cpu_count() is the host's (512 on fal's RTX 5090 nodes); the
    container's CPU quota is far smaller, and Blender sized to the host count ran 12x slower than locally."""
    cores = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)
    for path in ("/sys/fs/cgroup/cpu.max", "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"):
        try:
            v = open(path).read().split()
            if path.endswith("cpu.max"):
                q, per = v[0], int(v[1])
            else:
                q, per = v[0], int(open("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read())
            if q not in ("max", "-1"):
                cores = min(cores, max(1, int(q) // per))
            break
        except Exception:  # noqa: BLE001
            pass
    mem_gb = 0
    try:
        mem_gb = int(open("/proc/meminfo").read().split("MemTotal:")[1].split()[0]) // (1 << 20)
        for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
            if os.path.exists(path):
                v = open(path).read().strip()
                if v.isdigit():
                    mem_gb = min(mem_gb, int(v) >> 30)
                break
    except Exception:  # noqa: BLE001
        pass
    return cores, mem_gb


def auto_procs(device, blend):
    """Blender processes per worker: each holds the whole set in RAM (~4x the .blend on disk). Per-asset time is mostly
    CPU (OptiX bakes are short), so ~3 cores per process: 2 on the 6-core RTX 5090 workers (122 s for the 36-asset
    bench vs 196 s with 1 process of 6 threads)."""
    cores, mem_gb = machine_info()
    per = max(4, 4 * os.path.getsize(blend) / 1e9 + 2)
    if device == "cpu":
        return max(1, min(2, int(mem_gb // per)))
    return max(1, min(4, cores // 3, int(mem_gb // per)))


def common_args(o):
    a = ["--frame", str(o.frame), "--density", str(o.density), "--max-res", str(o.max_res)]
    return a


def run_shard(scene_dir, blend, rows, opts, device, procs, work, use_cache=True, cache=CACHE):
    """Bake and export `rows` (plan rows) with `procs` Blender processes on this worker. Returns stats."""
    os.makedirs(work, exist_ok=True)
    write_json(os.path.join(work, "plan.json"), {"assets": rows})
    out = os.path.join(work, "out")
    procs = max(1, min(procs or auto_procs(device, blend), len(rows)))
    parts = deal(rows, procs)
    results, errors = [None] * len(parts), []
    threads = max(1, machine_info()[0] // len(parts))

    def one(i, part):
        kp = os.path.join(work, f"keys_{i}.json")
        write_json(kp, [r["key"] for r in part])
        args = ["--out", out, "--plan", os.path.join(work, "plan.json"), "--keys", kp, "--cpu-threads", str(threads),
                *common_args(opts)]
        if device == "gpu":
            args.append("--gpu")
        if use_cache:
            args += ["--cache", cache]
        try:
            log, secs, tries = run_blender(blend, args, os.path.join(work, f"blender_{i}.log"), "shard",
                                           threads=threads)
            per = json.load(open(os.path.join(out, f"shard_keys_{i}.json")))
            results[i] = {"seconds": secs, "tries": tries, "assets": per}
        except Exception as e:  # noqa: BLE001
            errors.append(f"process {i}: {type(e).__name__}: {str(e)[-1500:]}")

    workers = [threading.Thread(target=one, args=(i, p)) for i, p in enumerate(parts)]
    for t in workers:
        t.start()
    for t in workers:
        t.join()
    per = [a for r in results if r for a in r["assets"]]
    missing = [r["key"] for r in rows if use_cache and not cache_ready(r["hash"], cache)]
    return {"assets": len(rows), "done": len(per), "from_cache": sum(a["cached"] for a in per),
            "bake_s": round(sum(a["bake_s"] for a in per), 1), "procs": len(parts),
            "process_s": [r["seconds"] if r else None for r in results], "threads": threads,
            "asset_s": {a["asset"]: a["bake_s"] for a in per}, "tries": [r["tries"] if r else None for r in results],
            "missing": missing, "errors": errors}


class ExportOptions(BaseModel):
    frame: int = Field(60, description="Scene frame to export at (animated materials and transforms are sampled here).")
    density: float = Field(1024, description="Bake texel density, px per metre (halved over 2 m2, quartered over 50 m2).")
    max_res: int = Field(4096, description="Largest bake texture side.")
    dof: dict[str, list[float]] = Field(default_factory=dict, description=(
        "Per-camera depth-of-field overrides {camera: [focus_m, fstop]} (the stills script's values, which the .blend "
        "does not hold)."))
    grade_sh: str | None = Field("grade.sh", description=(
        "Path inside the scene zip of the scene's grade.sh (its GRADE= ffmpeg chain becomes a colour LUT). Ignored "
        "when the file is not there; null skips it."))
    blend: str | None = Field(None, description="Which .blend in the zip is the set (default: the largest).")
    device: str = Field("gpu", description="Bake device: gpu (OptiX) or cpu. Does not change the result.")
    shards: int = Field(0, description="Worker count for the bake (0 = sized from the plan's estimated cost).")
    procs: int = Field(0, description="Blender processes per worker (0 = from cores and RAM).")


class ExportRequest(BaseModel):
    scene_url: str = Field(description="The scene: a .blend, or a .zip holding one (plus grade.sh). Pack external "
                                       "images and fonts into the .blend first.")
    options: ExportOptions = Field(default_factory=ExportOptions)
    use_cache: bool = Field(True, description=(
        "Reuse cached bakes (by content hash). False re-bakes everything into a job-private cache that is "
        "deleted afterwards; the shared cache is neither read nor changed."))
    fresh: bool = Field(False, description="Export again even if an identical request already has a result.")
    inline_scene_json: bool = Field(True, description="Also return scene.json inline (dropped when over 8 MB).")


class ExportResponse(BaseModel):
    job_id: str
    zip_url: str = Field(description="Zip of the export folder: scene.json, mesh/, tex/, world/, grade/, report.json.")
    scene_json_url: str
    scene_json: dict | None
    report: dict
    minutes: float


class ShardRequest(BaseModel):
    scene_url: str
    rows: list[dict] = Field(description="Plan rows (key, asset, hash, est_px) of the assets to bake.")
    options: ExportOptions = Field(default_factory=ExportOptions)
    job_id: str = ""
    cache_ns: str = Field("", description="Empty: the shared bake cache. Otherwise a job-private cache (use_cache=False).")
    use_cache: bool = Field(True, description="False (benchmarks): bake without reading or writing any cache.")


class Blend2Unreal(fal.App):
    machine_type = "GPU-RTX5090"
    image = ContainerImage.from_dockerfile_str(DOCKERFILE, context_dir=PurePosixPath("/tmp"))
    requirements = ["pydantic", "fal==1.84.0", "fal-client"]
    min_concurrency = 0  # set 1 (owner-approved while testing) to keep a warm worker: /export then starts at once
    keep_alive = 60  # was 300: 32 shard workers idling 5 min each was ~half of the first HK export's bill
    max_concurrency = 32
    request_timeout = 3600
    startup_timeout = 1800

    def setup(self):
        os.makedirs(LOCAL, exist_ok=True)
        with open(EXPORT_PY, "w", encoding="utf-8") as f:
            f.write(EXPORTER)
        smi = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
                             capture_output=True, text=True)
        self.device = smi.stdout.strip() or "unknown GPU"
        slug = "".join(c if c.isalnum() else "_" for c in self.device)[:80]
        self.optix_shared = f"{OPTIX_CACHE_SHARED_DIR}/{slug}"
        if os.path.isdir(self.optix_shared):
            shutil.copytree(self.optix_shared, OPTIX_CACHE_LOCAL_DIR, dirs_exist_ok=True)
        t = time.time()
        r = subprocess.run(["blender", "-b", "--factory-startup", "--python-expr", WARMUP], capture_output=True,
                           text=True, timeout=900)
        self.save_optix_cache()
        cores, mem = machine_info()
        print(f"blend2unreal ready: {self.device} | {cores} cores, {mem} GB RAM | OptiX warm-up "
              f"{'ok' if 'WARMUP done' in r.stdout else 'FAILED: ' + (r.stdout + r.stderr)[-500:]} in {time.time() - t:.0f} s",
              flush=True)

    def save_optix_cache(self):
        if not os.path.isdir(OPTIX_CACHE_LOCAL_DIR):
            return
        os.makedirs(self.optix_shared, exist_ok=True)
        for name in os.listdir(OPTIX_CACHE_LOCAL_DIR):
            a, b = os.path.join(OPTIX_CACHE_LOCAL_DIR, name), os.path.join(self.optix_shared, name)
            if os.path.isfile(a) and (not os.path.exists(b) or os.path.getsize(a) > os.path.getsize(b)):
                tmp = f"{b}.{os.getpid()}.tmp"
                shutil.copy(a, tmp)
                os.replace(tmp, b)

    # ------------------------------------------------------------------ /shard
    @fal.endpoint("/shard")
    def shard(self, req: ShardRequest) -> dict:
        t0 = time.time()
        scene_dir = fetch_scene(req.scene_url)
        blend = pick_blend(scene_dir, req.options.blend)
        t1 = time.time()
        work = os.path.join(LOCAL, "shards", f"{req.job_id or 'x'}_{os.getpid()}_{int(t0 * 1000)}")
        res = run_shard(scene_dir, blend, req.rows, req.options, req.options.device, req.options.procs, work,
                        use_cache=req.use_cache, cache=cache_root(req.cache_ns))
        self.save_optix_cache()
        cores, mem = machine_info()
        res.update(fetch_s=round(t1 - t0, 1), seconds=round(time.time() - t0, 1), device=self.device,
                   machine={"cores": cores, "mem_gb": mem}, bake_device=req.options.device)
        if res["errors"] or res["missing"]:
            res["log_tail"] = "".join(open(os.path.join(work, f), errors="replace").read()[-1500:]
                                      for f in sorted(os.listdir(work)) if f.endswith(".log"))[-4000:]
        if req.use_cache:
            shutil.rmtree(work, ignore_errors=True)
        return res

    # ------------------------------------------------------------------ /export
    @fal.endpoint("/export")
    async def export(self, req: ExportRequest) -> ExportResponse:
        import uuid

        t0 = time.time()
        o = req.options
        if o.device not in ("gpu", "cpu"):
            raise ValueError("options.device must be gpu or cpu")
        # Retry-safe like AnyShot: one job per identical order (device/shards/procs don't change the result).
        order = {"scene_url": req.scene_url, "use_cache": req.use_cache,
                 "options": o.model_dump(exclude={"device", "shards", "procs"})}
        fp = hashlib.sha256(json.dumps(order, sort_keys=True).encode()).hexdigest()[:20]
        index = os.path.join(INDEX, fp + ".json")
        os.makedirs(INDEX, exist_ok=True)
        rec = None
        if not req.fresh and os.path.exists(index):
            told = False
            while True:
                rec = json.load(open(index))
                if rec.get("response"):
                    stage("done", f"identical request: returning finished job {rec['job_id']}")
                    return ExportResponse(**rec["response"])
                alive = os.path.join(JOBS, rec["job_id"], ".alive")
                if not os.path.exists(alive) or time.time() - os.path.getmtime(alive) > 90:
                    break  # its attempt died: resume it
                if not told:
                    stage("received", f"identical request: attached to job {rec['job_id']}, still running")
                    told = True
                await asyncio.sleep(20)
            stage("received", f"resuming job {rec['job_id']}")
        else:
            rec = {"job_id": "x_" + uuid.uuid4().hex[:10], "fingerprint": fp, "order": order, "started": t0, "shards": {}}
            write_json(index, rec)
        job_dir = os.path.join(JOBS, rec["job_id"])
        os.makedirs(job_dir, exist_ok=True)

        async def heartbeat():
            while True:
                open(os.path.join(job_dir, ".alive"), "w").close()
                await asyncio.sleep(20)

        hb = asyncio.create_task(heartbeat())
        try:
            return await self._export(req, rec, index, job_dir, t0)
        finally:
            hb.cancel()

    async def _export(self, req, rec, index, job_dir, t0):
        import fal_client
        from fal.toolkit import File

        o = req.options
        T = {}
        stage("fetch", "downloading the scene")
        scene_dir = await asyncio.to_thread(fetch_scene, req.scene_url)
        blend = pick_blend(scene_dir, o.blend)
        T["fetch_s"] = round(time.time() - t0, 1)
        local = os.path.join(LOCAL, "jobs", rec["job_id"])
        os.makedirs(local, exist_ok=True)

        # 1. plan
        plan_path = os.path.join(job_dir, "plan.json")
        t = time.time()
        if not os.path.exists(plan_path):
            stage("plan", f"planning {os.path.basename(blend)} ({os.path.getsize(blend) / 1e9:.2f} GB)")
            lp = os.path.join(local, "plan.json")
            await asyncio.to_thread(run_blender, blend, ["--out", os.path.join(local, "plan_out"), "--plan-out", lp,
                                                         *common_args(o)], os.path.join(local, "plan.log"), "plan")
            shutil.copy(lp, plan_path + ".tmp")
            os.replace(plan_path + ".tmp", plan_path)
        plan = json.load(open(plan_path))
        T["plan_s"] = round(time.time() - t, 1)
        rows = plan["assets"]
        ns = "" if req.use_cache else rec["job_id"]
        cache = cache_root(ns)
        todo = [r for r in rows if not cache_ready(r["hash"], cache)]
        hits = len(rows) - len(todo)
        stage("plan", f"{len(rows)} assets ({plan['placements']} placements): {hits} cached, {len(todo)} to bake, "
                      f"~{sum(cost_s(r) for r in todo) / 60:.0f} process-minutes", plan_s=plan.get("plan_s"))

        # 2. shards: shard 0 here, the rest on other workers of this app
        t = time.time()
        shard_stats = []
        if todo:
            procs = o.procs or auto_procs(o.device, blend)
            n = o.shards or max(1, min(32, round(sum(cost_s(r) for r in todo) / (procs * TARGET_SHARD_S))))
            app = os.environ.get(APP_ENV, DEFAULT_APP)
            client = fal_client.AsyncClient(key=os.environ.get("FAL_SERVERLESS_KEY") or os.environ.get("FAL_KEY"))
            for rnd in range(2):  # a second round re-deals whatever the first one left unbaked
                todo = [r for r in rows if not cache_ready(r["hash"], cache)]
                if not todo:
                    break
                parts = deal(todo, n if rnd == 0 else max(1, min(n, len(todo) // 4 or 1)))
                stage("shards", f"round {rnd + 1}: {len(todo)} assets in {len(parts)} shards ({o.device}, "
                                f"{procs} Blender processes per worker)")

                async def remote(i, part):
                    sid = f"r{rnd}s{i}"
                    payload = {"scene_url": req.scene_url, "rows": part, "options": o.model_dump(), "job_id": rec["job_id"],
                               "cache_ns": ns}
                    old = rec["shards"].get(sid)
                    handle = None
                    if old and old.get("request_id") and not old.get("result"):
                        handle = await client.get_handle(app, old["request_id"])  # a resumed job re-attaches
                    for attempt in range(2):
                        if handle is None:
                            handle = await client.submit(app, arguments=payload, path="/shard")
                            rec["shards"][sid] = {"request_id": handle.request_id, "assets": len(part), "submitted": time.time()}
                            write_json(index, rec)
                        try:
                            while not isinstance(await handle.status(), fal_client.Completed):
                                await asyncio.sleep(10)
                            res = await handle.get()
                            res["shard"] = sid
                            rec["shards"][sid]["result"] = {k: res.get(k) for k in ("seconds", "done", "missing")}
                            write_json(index, rec)
                            stage("shards", f"{sid} done: {res['done']}/{res['assets']} assets in {res['seconds']:.0f}s "
                                            f"(scene fetch {res['fetch_s']:.0f}s)", **{k: res.get(k) for k in ("process_s", "errors")})
                            return res
                        except Exception as e:  # noqa: BLE001
                            stage("shards", f"{sid} attempt {attempt + 1} failed: {type(e).__name__}: {str(e)[:300]}")
                            handle = None
                    return {"shard": sid, "assets": len(part), "done": 0, "errors": ["request failed twice"], "seconds": 0}

                async def here(part):
                    tt = time.time()
                    res = await asyncio.to_thread(run_shard, scene_dir, blend, part, o, o.device, procs,
                                                  os.path.join(local, f"shard_r{rnd}"), True, cache)
                    res.update(shard=f"r{rnd}s0 (orchestrator)", seconds=round(time.time() - tt, 1), fetch_s=0)
                    stage("shards", f"local shard done: {res['done']}/{res['assets']} in {res['seconds']:.0f}s")
                    return res

                shard_stats += await asyncio.gather(here(parts[0]), *(remote(i, p) for i, p in enumerate(parts[1:], 1)))
                self.save_optix_cache()
        T["shards_s"] = round(time.time() - t, 1)
        unbaked = [r["key"] for r in rows if not cache_ready(r["hash"], cache)]

        # 3. merge
        t = time.time()
        out = os.path.join(local, "export")
        shutil.rmtree(out, ignore_errors=True)
        args = ["--out", out, "--plan", plan_path, "--cache", cache, "--link-cache", "--no-bake", "--ffmpeg", "ffmpeg",
                *common_args(o)]
        if o.device == "gpu":
            args.append("--gpu")  # volume sampling bakes
        if o.dof:
            args += ["--dof", json.dumps(o.dof)]
        grade = os.path.join(scene_dir, o.grade_sh) if o.grade_sh else None
        if grade and os.path.isfile(grade) and os.path.realpath(grade).startswith(os.path.realpath(scene_dir)):
            args += ["--grade-sh", grade]
        else:
            grade = None
        stage("merge", f"writing scene.json ({len(unbaked)} assets left unbaked)")
        merge_log, _, _ = await asyncio.to_thread(run_blender, blend, args, os.path.join(local, "merge.log"), "merge")
        T["merge_s"] = round(time.time() - t, 1)

        scene = json.load(open(os.path.join(out, "scene.json"), encoding="utf-8"))
        report = self._report(plan, scene, out, unbaked, merge_log, grade, shard_stats, hits)
        write_json(os.path.join(out, "report.json"), report)

        # 4. package
        t = time.time()
        stage("package", "zipping and uploading")
        zpath = os.path.join(local, f"{rec['job_id']}.zip")
        await asyncio.to_thread(localize, out)
        T["copy_s"] = round(time.time() - t, 1)
        size = await asyncio.to_thread(zip_dir, out, zpath)
        T["zip_s"] = round(time.time() - t - T["copy_s"], 1)
        zip_url = await asyncio.to_thread(lambda: File.from_path(zpath, content_type="application/zip").url)
        sj_url = await asyncio.to_thread(lambda: File.from_path(os.path.join(out, "scene.json"),
                                                                content_type="application/json").url)
        T["package_s"] = round(time.time() - t, 1)
        T["total_s"] = round(time.time() - t0, 1)
        report["timings"] = T
        report["zip_bytes"] = size
        sec = [s.get("seconds") or 0 for s in shard_stats if "orchestrator" not in str(s.get("shard"))]
        report["worker_seconds"] = {"export_worker": T["total_s"], "shard_workers": round(sum(sec), 1),
                                    "total": round(T["total_s"] + sum(sec), 1)}
        js = json.dumps(scene)
        res = ExportResponse(job_id=rec["job_id"], zip_url=zip_url, scene_json_url=sj_url,
                             scene_json=scene if req.inline_scene_json and len(js) < 8 << 20 else None,
                             report=report, minutes=round((time.time() - t0) / 60, 2))
        stage("done", f"{len(scene['assets'])} assets, {len(scene['placements'])} placements in {res.minutes:.1f} min",
              zip_url=zip_url)
        rec = json.load(open(index))
        rec.update(response=res.model_dump(), finished=time.time())
        write_json(index, rec)
        shutil.rmtree(local, ignore_errors=True)
        if ns:  # the job-private cache of a use_cache=False export: delete it in the background
            threading.Thread(target=shutil.rmtree, args=(cache, True), daemon=True).start()
        await asyncio.sleep(2)  # let the last stage lines reach the queue logs before COMPLETED
        return res

    def _report(self, plan, scene, out, unbaked, merge_log, grade, shard_stats, hits):
        tex = {}
        tex_bytes = 0
        for f in os.listdir(os.path.join(out, "tex")):
            if f.endswith(".png"):
                c = f.rsplit("_", 1)[-1][:-4]
                tex[c] = tex.get(c, 0) + 1
                tex_bytes += os.path.getsize(os.path.join(out, "tex", f))
        glb_bytes = sum(os.path.getsize(os.path.join(out, "mesh", f)) for f in os.listdir(os.path.join(out, "mesh"))
                        if f.endswith(".glb"))
        need = {r["key"] for r in plan["assets"] if r.get("channels")}
        no_tex = [a["asset"] for a in scene["assets"] if a["key"] in need and "base" not in a.get("tex", {})]
        warnings = [l.split("EXPORT ", 1)[1] for l in merge_log.splitlines() if l.startswith("EXPORT") and "WARNING" in l]
        warnings += [f"light {l['name']}: {l['note']}" for l in scene["lights"] if l.get("note")]
        od = [a["asset"] for a in scene["assets"] if a.get("object_dependent") and a.get("instances", 1) > 1]
        if od:
            warnings.append(f"{len(od)} instanced assets have object-dependent materials (Object Info, object coords, "
                            f"AO, ...): baked once on a representative instance, so instances share one look: {od[:12]}")
        anim = [a["asset"] for a in scene["assets"] if a.get("animated_materials")]
        if anim:
            warnings.append(f"{len(anim)} assets have animated materials, baked at frame {scene['frame']}: {anim[:12]}")
        if unbaked:
            warnings.append(f"{len(unbaked)} assets failed to bake on every try and were exported without textures")
        if grade is None:
            warnings.append("no grade.sh: grade/lut_grade.png not written (Unreal gets the AgX view + exposure only)")
        not_converted = [{"name": n, "why": w} for n, w in scene.get("skipped", [])]
        not_converted += [{"name": v, "why": "volume: exported as sampled density/emission (scene.json volumes), "
                                             "not geometry"} for v in scene.get("volumes", {})]
        not_converted += [{"name": f["name"], "why": f"{f['kind']} fx: exported as a description (scene.json fx) "
                                                    "for the Niagara stage"} for f in scene.get("fx", [])]
        return {
            "counts": {"objects": plan["objects"], "assets": len(scene["assets"]), "placements": len(scene["placements"]),
                       "lights": len(scene["lights"]), "cameras": len(scene["cameras"]),
                       "volumes": len(scene.get("volumes", {})), "fx": len(scene.get("fx", [])),
                       "converted_to_mesh": len(scene.get("converted", [])), "glass_assets":
                           sum(1 for a in scene["assets"] if a.get("glass")),
                       "textures": tex, "texture_bytes": tex_bytes, "glb_bytes": glb_bytes},
            "cache": {"hits": hits, "baked": len(plan["assets"]) - hits - len(unbaked), "unbaked": unbaked},
            "not_baked": no_tex,
            "not_converted": not_converted,
            "converted": scene.get("converted", []),
            "warnings": warnings,
            "shards": shard_stats,
            "plan": {"code": plan["code"], "blender": plan["blender"], "plan_s": plan.get("plan_s"),
                     "est_mpx": round(sum(r["est_px"] for r in plan["assets"]) / 1e6)},
        }


def localize(src, workers=16):
    """Replace the merge's symlinks into the /data cache with local copies, many files at once: one reader on /data
    managed ~20 MB/s (220 s to zip HK's 4.4 GB straight off the symlinks)."""
    from concurrent.futures import ThreadPoolExecutor

    links = [os.path.join(r, f) for r, _, fs in os.walk(src) for f in fs if os.path.islink(os.path.join(r, f))]

    def one(p):
        target = os.path.realpath(p)
        tmp = p + ".copy"
        shutil.copyfile(target, tmp)
        os.replace(tmp, p)

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, links))
    return len(links)


def zip_dir(src, zpath):
    """The export folder as a zip; images stored, the rest deflated."""
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for root, _, files in os.walk(src):
            for f in sorted(files):
                p = os.path.join(root, f)
                arc = os.path.relpath(p, src).replace(os.sep, "/")
                ct = zipfile.ZIP_STORED if f.endswith((".png", ".exr")) else zipfile.ZIP_DEFLATED
                z.write(p, arc, compress_type=ct)
    return os.path.getsize(zpath)
