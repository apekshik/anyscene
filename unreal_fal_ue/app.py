"""apek/unreal-build: headless Unreal Engine 5.8 on fal Serverless. Builds an AnyScene export (export_blend.py output:
scene.json + mesh/ + tex/ + world/ + grade/) into a level and renders it with Movie Render Queue, so the Unreal stages of
the Blender -> Unreal converter run off the local GPU. It is the core of the hosted /scene2unreal (TOGGLE.md).

    GHCR_USER=... GHCR_TOKEN=... fal deploy app.py::UnrealBuild --app-name unreal-build --auth private

Endpoints
  /smoke   engine version, GPU, Vulkan device and a 640x360 render of a lit cube (proves the RHI works headless).
  /build   export_url (zip of an export folder) -> content_url (zip of Content/AnyScene/<Scene> + Config), log, report.
  /render  content_url + camera names -> MRQ PNG stills (and an MP4 per camera when frames > 1).

Engine source (UE_SOURCE at deploy time):
  ghcr:<tag>   Epic's prebuilt dev image ghcr.io/epicgames/unreal-engine:<tag> (default dev-slim-5.8.0). Pulling needs
               a GitHub account linked to an Epic Games account and a PAT with read:packages (GHCR_USER / GHCR_TOKEN;
               fal strips registry credentials before pickling, they go only to the image builder).
  url:<url>    a Linux binary zip of the engine (Epic's "Linux_Unreal_Engine_5.8.x.zip"), downloaded at image build.
Either way the engine ends up at /opt/UnrealEngine in a python:3.13-slim image (the base the render farm already runs).

UnrealEditor refuses to run as root on Linux, so every engine process runs as the `ue` user (setpriv). Shaders and
derived data go to a shared DDC on /data (UE-SharedDataCachePath), so compiles are paid once across workers and jobs.
"""

import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

import fal
from fal.container import ContainerImage

from pydantic import BaseModel, Field

if os.name == "nt":
    # Deploying from Windows: ContainerImage's context_dir default is the cwd as a WindowsPath, evaluated at import.
    # It gets pickled along with the app and Linux can't unpickle a WindowsPath, so swap it for a POSIX path.
    _posix = PurePosixPath("/tmp")
    ContainerImage.__dataclass_fields__["context_dir"].default = _posix
    ContainerImage.context_dir = _posix
    ContainerImage.__init__.__defaults__ = tuple(
        _posix if isinstance(d, os.PathLike) else d for d in ContainerImage.__init__.__defaults__ or ()
    )

UE_SOURCE = os.environ.get("UE_SOURCE", "ghcr:dev-slim-5.8.4")  # the local editor is 5.8.4 (CL 58902052)
UE_USER = "ue4"  # Epic's images run as ue4 (uid 1000); the other modes create the same user

_ICD = ("mkdir -p /etc/vulkan/icd.d && printf "
        "'{\"file_format_version\":\"1.0.0\",\"ICD\":{\"library_path\":\"libGLX_nvidia.so.0\",\"api_version\":\"1.3\"}}' "
        "> /etc/vulkan/icd.d/nvidia_icd.json")
if UE_SOURCE.startswith("ghcr:"):
    # Build on Epic's image itself: its ~30 engine layers are pulled as they are (copying the engine into another base
    # would re-pack ~60 GB into one layer). fal's isolate needs a Python matching the deploying one, so add 3.13.
    UE = "/home/ue4/UnrealEngine"
    _REGISTRIES = {"ghcr.io": {"username": os.environ.get("GHCR_USER", ""), "password": os.environ.get("GHCR_TOKEN", "")}}
    DOCKERFILE = f"""FROM ghcr.io/epicgames/unreal-engine:{UE_SOURCE[5:]}
USER root
ENV NVIDIA_DRIVER_CAPABILITIES=all NVIDIA_VISIBLE_DEVICES=all
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates unzip zip ffmpeg util-linux libvulkan1 vulkan-tools \
    && rm -rf /var/lib/apt/lists/* && {_ICD}
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv
RUN UV_PYTHON_INSTALL_DIR=/opt/python uv python install 3.13 \
    && ln -sf "$(UV_PYTHON_INSTALL_DIR=/opt/python uv python find 3.13)" /usr/local/bin/python3.13 \
    && ln -sf /usr/local/bin/python3.13 /usr/local/bin/python \
    && ln -sf /usr/local/bin/python3.13 /usr/local/bin/python3 \
    && rm -f /opt/python/*/lib/python3.13/EXTERNALLY-MANAGED && python -m ensurepip
"""
else:
    UE = "/opt/UnrealEngine"
    _REGISTRIES = {}
    if UE_SOURCE == "none":  # probe deploy without an engine: checks the base image, GPU and Vulkan on fal
        _ENGINE = ""
    else:  # url:<Linux binary zip>
        _ENGINE = (
            f"RUN curl -fsSL '{UE_SOURCE[4:]}' -o /tmp/ue.zip && mkdir -p /tmp/ue && unzip -q /tmp/ue.zip -d /tmp/ue"
            f" && rm /tmp/ue.zip && mv \"$(dirname \"$(find /tmp/ue -maxdepth 3 -type d -name Engine | head -1)\")\" {UE}"
            f" && chown -R {UE_USER}:{UE_USER} {UE} && rm -rf /tmp/ue\n"
        )
    DOCKERFILE = f"""FROM python:3.13-slim-bookworm
ENV NVIDIA_DRIVER_CAPABILITIES=all NVIDIA_VISIBLE_DEVICES=all
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates unzip zip ffmpeg util-linux libvulkan1 vulkan-tools \
      libgl1 libegl1 libx11-6 libxcursor1 libxrandr2 libxi6 libxinerama1 libxss1 libxcomposite1 libxdamage1 \
      libxext6 libxfixes3 libxrender1 libxkbcommon0 libnss3 libasound2 libpulse0 libsm6 libice6 libglib2.0-0 \
      libfontconfig1 libfreetype6 libicu72 xdg-user-dirs \
    && rm -rf /var/lib/apt/lists/* && useradd -m -u 1000 {UE_USER} && {_ICD}
{_ENGINE}"""
EDITOR = f"{UE}/Engine/Binaries/Linux/UnrealEditor"
EDITOR_CMD = f"{UE}/Engine/Binaries/Linux/UnrealEditor-Cmd"


def _read(name):
    """Scripts shipped to the worker as strings (no build context). Read at deploy time on the deploying machine."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


SCRIPTS = {n: _read(n) for n in ("build_level.py", "mrq_config.py", "smoke_shot.py")}
TEMPLATE = {
    "AnySceneUE.uproject": _read("template/AnySceneUE.uproject"),
    "Config/DefaultEngine.ini": _read("template/Config/DefaultEngine.ini"),
    "Config/DefaultGame.ini": _read("template/Config/DefaultGame.ini"),
}

# Fixed paths: build_level.py bakes some paths into assets, so the same layout on every worker keeps them valid.
ROOT = "/tmp/anyscene"
PROJECT = f"{ROOT}/AnySceneUE"
UPROJECT = f"{PROJECT}/AnySceneUE.uproject"
EXPORT = f"{ROOT}/export"
CACHE = "/tmp/anyscene-cache"  # local disk, per worker (see farm/app.py on /data contention)
DDC_SHARED = "/data/unreal/ddc/5.8"
DPCVARS = ("-dpcvars=Editor.AsyncAssetCompilation=0,Editor.AsyncTextureCompilation=0,"
           "Editor.AsyncStaticMeshCompilation=0,fx.Niagara.ForceWaitForCompilationOnActivate=1,r.TextureStreaming=0")
# Commandlets never log LogExit: their last word is "Execution of commandlet took" (the first HK build sat 100 min there).
EXIT_MARKERS = ("LogExit: Exiting.", "LogExit: Editor shut down", "LogExit: Game engine shut down",
                "Execution of commandlet took")
EXIT_GRACE = 60
COMMON = ["-unattended", "-nosplash", "-nop4", "-nosound", "-stdout", "-FullStdOutLogOutput", "-vulkan"]


def ue_env(extra=None):
    env = {
        "HOME": f"/home/{UE_USER}", "USER": UE_USER, "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
        "XDG_CONFIG_HOME": f"/home/{UE_USER}/.config",
        "LD_LIBRARY_PATH": "/usr/lib/x86_64-linux-gnu:/usr/local/nvidia/lib64:/usr/local/nvidia/lib",
        "UE-SharedDataCachePath": DDC_SHARED, "SDL_VIDEODRIVER": "offscreen",
        "NVIDIA_DRIVER_CAPABILITIES": "all",
    }
    env.update(extra or {})
    return env


def run_ue(args, log_path, timeout, env=None, watch=("ANYSCENE", "SMOKE", "MRQCFG", "Error:", "LogMovieRenderPipeline")):
    """Run an engine process as UE_USER, full output to log_path, interesting lines echoed to the fal log.

    The process gets its own process group, killed as a whole: ShaderCompileWorker children inherit stdout and keep
    the pipe open after the editor has exited (the first smoke run sat 20 min past "Editor shut down"). Once the
    engine logs its shutdown, the group gets EXIT_GRACE seconds before it is killed. The pipe is read on its own
    thread so nothing here waits for EOF, and every UE_USER process is killed at the end in case one left the group."""
    import signal

    cmd = ["setpriv", f"--reuid={UE_USER}", f"--regid={UE_USER}", "--init-groups", *args]
    t = time.time()
    exited = threading.Event()

    def kill():
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        subprocess.run(["pkill", "-9", "-u", UE_USER], check=False)

    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=ue_env(env), text=True,
                             errors="replace", start_new_session=True)

        def read():
            for line in p.stdout:
                log.write(line)
                if any(w in line for w in watch):
                    print(line.rstrip()[:400], flush=True)
                if not exited.is_set() and any(m in line for m in EXIT_MARKERS):
                    exited.set()

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        deadline = t + timeout
        while p.poll() is None and time.time() < deadline:
            if exited.is_set():
                deadline = min(deadline, time.time() + EXIT_GRACE)
            time.sleep(1)
        kill()
        p.wait()
        reader.join(10)
    return p.returncode, round(time.time() - t, 1)


def tail(path, n=6000):
    try:
        return Path(path).read_text(errors="replace")[-n:]
    except OSError:
        return ""


def chown_ue(path):
    subprocess.run(["chown", "-R", f"{UE_USER}:{UE_USER}", str(path)], check=False)


def fetch_zip(url, dest):
    """Download a zip once per worker (keyed by URL hash) and unpack it into dest (replacing it)."""
    key = hashlib.sha256(url.encode()).hexdigest()[:24]
    cached = Path(CACHE) / key
    if not (cached / ".ready").exists():
        shutil.rmtree(cached, ignore_errors=True)
        cached.mkdir(parents=True)
        zpath = cached / "in.zip"
        with urllib.request.urlopen(url, timeout=900) as r, open(zpath, "wb") as f:
            while chunk := r.read(16 << 20):
                f.write(chunk)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(cached / "x")
        zpath.unlink()
        (cached / ".ready").touch()
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(cached / "x", dest)
    return Path(dest)


def make_project(dest, level):
    """A fresh project from the template, with the scene's level as the startup/default map and Vulkan SM6 on Linux."""
    shutil.rmtree(PROJECT, ignore_errors=True)
    for rel, text in TEMPLATE.items():
        p = Path(PROJECT) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if rel == "Config/DefaultEngine.ini":
            if level:
                text = text.replace("/Game/AnyScene/HK/L_HK.L_HK", f"{dest}/{level}.{level}")
            else:  # no level yet (smoke): the engine's default empty map
                text = "\n".join(l for l in text.splitlines() if "StartupMap=" not in l and "DefaultMap=" not in l)
            text += ("\n[/Script/LinuxTargetPlatform.LinuxTargetSettings]\n-TargetedRHIs=SF_VULKAN_SM5\n"
                     "+TargetedRHIs=SF_VULKAN_SM6\n")
        p.write_text(text)
    (Path(PROJECT) / "Content").mkdir(exist_ok=True)


def write_scripts():
    d = Path(ROOT) / "scripts"
    d.mkdir(parents=True, exist_ok=True)
    for n, s in SCRIPTS.items():
        (d / n).write_text(s)
    return d


def upload(path, content_type):
    from fal.toolkit import File  # not at module level: its Path constants pickle as WindowsPath from Windows

    return File.from_path(str(path), content_type=content_type).url


class SmokeRequest(BaseModel):
    render: bool = Field(True, description="Also render a lit cube offscreen (proves Vulkan rendering works).")


class SmokeResult(BaseModel):
    engine: str
    gpu: str
    vulkan: str
    image_url: str | None = None
    seconds: float
    log_tail: str


class BuildRequest(BaseModel):
    export_url: str = Field(description="Zip of an AnyScene export folder (scene.json at the zip root).")
    scene: str = Field("HK", description="Content folder name: assets go under /Game/AnyScene/<scene>.")
    level: str = Field("", description="Level name (default L_<scene>).")
    stages: str = Field("textures,meshes,materials,level,sequences", description="build_level.py stages.")
    nanite_tris: int = Field(2000)
    exposure_offset: float = Field(0.0)
    timeout_s: int = Field(5400)


class BuildResult(BaseModel):
    content_url: str = Field(description="Zip of Content/AnyScene/<scene>/ plus Config/ and the .uproject.")
    log_url: str
    report: dict
    build_seconds: float
    fetch_seconds: float
    content_mb: float


class RenderRequest(BaseModel):
    content_url: str = Field(description="content_url from /build.")
    scene: str = Field("HK")
    level: str = Field("")
    cameras: list[str] = Field(["cam_street", "cam_table", "cam_wok"])
    config: str = Field("MRQ_Still", description="Base MRQ config: MRQ_Still (PNG, UE tone curve) or MRQ_Linear (EXR).")
    resolution: list[int] = Field([1920, 804])
    frames: int = Field(1, description="Frames per camera; >1 renders a clip and also returns an MP4.")
    temporal_samples: int = Field(8)
    warmup_frames: int = Field(64)
    fps: int = Field(24)
    timeout_s: int = Field(3600)


class RenderedCamera(BaseModel):
    camera: str
    image_urls: list[str]
    video_url: str | None = None
    seconds: float
    returncode: int


class RenderResult(BaseModel):
    cameras: list[RenderedCamera]
    fetch_seconds: float
    config_seconds: float
    log_urls: list[str]


class UnrealBuild(fal.App):
    machine_type = "GPU-RTX5090"
    image = ContainerImage.from_dockerfile_str(DOCKERFILE, context_dir=PurePosixPath("/tmp"), registries=_REGISTRIES)
    # 24 GB compressed image plus a ~5 GB export and its build: the RTX PRO 6000 has more local disk if this fills up.
    requirements = ["pydantic", "fal==1.84.0"]
    # Owner-approved warm worker: the image is tens of GB, so a cold start is minutes of pull plus engine start.
    min_concurrency = int(os.environ.get("UE_MIN_CONCURRENCY", "1"))
    keep_alive = 3600  # fal caps this at 3600 without a support request
    max_concurrency = 4
    request_timeout = 7200
    startup_timeout = 3600
    # A timed-out request is otherwise re-run on a fresh runner: the first HK build hung after finishing and was retried
    # every 2 h for 14 h. Timeouts here mean a bug, not a transient error.
    skip_retry_conditions = ["timeout"]

    def setup(self):
        for d in (ROOT, CACHE, DDC_SHARED):
            os.makedirs(d, exist_ok=True)
        chown_ue(ROOT)
        try:
            chown_ue(DDC_SHARED)
        except Exception:
            pass
        os.chmod(DDC_SHARED, 0o777)
        smi = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
                             capture_output=True, text=True)
        self.gpu = smi.stdout.strip() or smi.stderr.strip()[-300:]
        vk = subprocess.run(["setpriv", f"--reuid={UE_USER}", f"--regid={UE_USER}", "--init-groups", "vulkaninfo", "--summary"],
                            capture_output=True, text=True, env=ue_env())
        lines = [l.strip() for l in vk.stdout.splitlines() if "deviceName" in l or "driverInfo" in l or "apiVersion" in l]
        self.vulkan = "; ".join(lines[:6]) or (vk.stderr or vk.stdout)[-400:]
        try:
            v = json.load(open(f"{UE}/Engine/Build/Build.version"))
            self.engine = f"{v['MajorVersion']}.{v['MinorVersion']}.{v['PatchVersion']} CL{v.get('Changelist')} {v.get('BranchName', '')}"
        except Exception as e:
            self.engine = f"unknown ({e})"
        print("unreal-build ready:", self.engine, "|", self.gpu, "|", self.vulkan, flush=True)

    @fal.endpoint("/smoke")
    def smoke(self, req: SmokeRequest) -> SmokeResult:
        t = time.time()
        url, log = None, ""
        if req.render:
            scripts = write_scripts()
            make_project("/Game/Smoke", "")
            out = Path(ROOT) / "smoke"
            shutil.rmtree(out, ignore_errors=True)
            chown_ue(ROOT)
            lp = f"{ROOT}/smoke.log"
            rc, _ = run_ue([EDITOR, UPROJECT, f"-ExecCmds=py {scripts}/smoke_shot.py", "-RenderOffscreen", DPCVARS,
                            *COMMON], lp, 1800, {"ANYSCENE_SMOKE_OUT": str(out)})
            log = tail(lp)
            png = out / "smoke.png"
            if png.exists():
                url = upload(png, "image/png")
        return SmokeResult(engine=self.engine, gpu=self.gpu, vulkan=self.vulkan, image_url=url,
                           seconds=round(time.time() - t, 1), log_tail=log[-3000:])

    @fal.endpoint("/build")
    def build(self, req: BuildRequest) -> BuildResult:
        if not req.scene.isidentifier():
            raise ValueError("scene must be an identifier")
        level = req.level or f"L_{req.scene}"
        dest = f"/Game/AnyScene/{req.scene}"
        t0 = time.time()
        fetch_zip(req.export_url, EXPORT)
        t1 = time.time()
        scripts = write_scripts()
        make_project(dest, level)
        chown_ue(ROOT)
        lp = f"{ROOT}/build.log"
        env = {"ANYSCENE_EXPORT": EXPORT, "ANYSCENE_DEST": dest, "ANYSCENE_LEVEL": level, "ANYSCENE_STAGES": req.stages,
               "ANYSCENE_NANITE_TRIS": str(req.nanite_tris), "ANYSCENE_EXPOSURE_OFFSET": str(req.exposure_offset)}
        rc, secs = run_ue([EDITOR_CMD, UPROJECT, "-run=pythonscript", f"-script={scripts}/build_level.py", DPCVARS,
                           *COMMON], lp, req.timeout_s, env)
        log_url = upload(lp, "text/plain")
        rp = Path(EXPORT) / "build_report.json"
        report = json.loads(rp.read_text()) if rp.exists() else {}
        content = Path(PROJECT) / "Content" / "AnyScene" / req.scene
        if not (content / f"{level}.umap").exists():
            raise RuntimeError(f"build failed (exit {rc}, no {level}.umap); log {log_url}\n{tail(lp, 3000)}")
        print(f"build done in {secs}s (exit {rc}); zipping content", flush=True)
        t2 = time.time()
        zpath = Path(ROOT) / f"{req.scene}_content.zip"
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as z:
            for p in content.rglob("*"):
                if p.is_file():
                    z.write(p, p.relative_to(PROJECT).as_posix())
            for p in (Path(PROJECT) / "Config").rglob("*"):
                if p.is_file():
                    z.write(p, p.relative_to(PROJECT).as_posix())
            z.write(UPROJECT, "AnySceneUE.uproject")
        report["exit_code"] = rc
        t3 = time.time()
        print(f"zipped {zpath.stat().st_size / 1e6:.0f} MB in {t3 - t2:.0f}s; uploading", flush=True)
        content_url = upload(zpath, "application/zip")
        report["zip_s"], report["upload_s"] = round(t3 - t2, 1), round(time.time() - t3, 1)
        print(f"uploaded in {report['upload_s']}s", flush=True)
        res = BuildResult(content_url=content_url, log_url=log_url, report=report,
                          build_seconds=secs, fetch_seconds=round(t1 - t0, 1),
                          content_mb=round(zpath.stat().st_size / 1e6, 1))
        zpath.unlink(missing_ok=True)
        return res

    @fal.endpoint("/render")
    def render(self, req: RenderRequest) -> RenderResult:
        if not req.scene.isidentifier() or not all(c.isidentifier() for c in req.cameras):
            raise ValueError("scene and camera names must be identifiers")
        level = req.level or f"L_{req.scene}"
        dest = f"/Game/AnyScene/{req.scene}"
        t0 = time.time()
        make_project(dest, level)
        staged = fetch_zip(req.content_url, f"{ROOT}/content_in")
        shutil.copytree(staged / "Content", Path(PROJECT) / "Content", dirs_exist_ok=True)
        t1 = time.time()
        scripts = write_scripts()
        out = Path(ROOT) / "mrq"
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        chown_ue(ROOT)
        W, H = req.resolution
        lp = f"{ROOT}/mrq_config.log"
        rc, cfg_s = run_ue([EDITOR_CMD, UPROJECT, "-run=pythonscript", f"-script={scripts}/mrq_config.py", *COMMON], lp,
                           900, {"ANYSCENE_DEST": dest, "ANYSCENE_MRQ_BASE": req.config, "ANYSCENE_MRQ_NAME": "MRQ_Req",
                                 "ANYSCENE_MRQ_OUT": str(out), "ANYSCENE_MRQ_RES": f"{W}x{H}",
                                 "ANYSCENE_MRQ_FRAMES": f"0,{req.frames}", "ANYSCENE_MRQ_SAMPLES": str(req.temporal_samples),
                                 "ANYSCENE_MRQ_WARMUP": str(req.warmup_frames), "ANYSCENE_CAMS": ",".join(req.cameras)})
        logs = [upload(lp, "text/plain")]
        if "MRQCFG wrote" not in tail(lp, 2_000_000):  # the exit code is -9 when the group is killed after shutdown
            raise RuntimeError(f"MRQ config failed (exit {rc})\n{tail(lp, 3000)}")
        results = []
        for cam in req.cameras:
            clp = f"{ROOT}/mrq_{cam}.log"
            seq = f"{dest}/Sequences/SEQ_{cam}.SEQ_{cam}"
            rc, secs = run_ue([EDITOR_CMD, UPROJECT, f"{dest}/{level}", "-game", f"-LevelSequence={seq}",
                               f"-MoviePipelineConfig={dest}/MRQ/MRQ_Req.MRQ_Req", "-RenderOffscreen", "-windowed",
                               f"-resx={W}", f"-resy={H}", "-notexturestreaming", DPCVARS, *COMMON],
                              clp, req.timeout_s)
            logs.append(upload(clp, "text/plain"))
            files = sorted(p for p in out.glob(f"SEQ_{cam}*") if p.suffix.lower() in (".png", ".exr"))
            video = None
            if req.frames > 1 and files and files[0].suffix.lower() == ".png":
                mp4 = out / f"{cam}.mp4"
                lst = out / f"{cam}.txt"
                lst.write_text("".join(f"file '{p}'\nduration {1 / req.fps}\n" for p in files))
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                                "-r", str(req.fps), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", str(mp4)],
                               check=False)
                if mp4.exists():
                    video = upload(mp4, "video/mp4")
            ctype = "image/png" if not files or files[0].suffix.lower() == ".png" else "image/x-exr"
            results.append(RenderedCamera(camera=cam, image_urls=[upload(p, ctype) for p in files], video_url=video,
                                          seconds=secs, returncode=rc))
            print(f"MRQ {cam}: {len(files)} frames in {secs}s (exit {rc})", flush=True)
        return RenderResult(cameras=results, fetch_seconds=round(t1 - t0, 1), config_seconds=cfg_s, log_urls=logs)
