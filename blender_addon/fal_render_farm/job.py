"""A farm render job: everything that touches bpy happens in plan() on the main thread; Job.run() is pure Python on a
background thread (pack in a separate Blender, zip, upload, fan chunks out to the queue, download frames), so the UI
never blocks. The UI reads Job.snapshot() from a timer."""

import concurrent.futures as cf
import hashlib
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import zipfile
from collections import deque
from dataclasses import dataclass, field

from . import fal_api

HERE = os.path.dirname(os.path.abspath(__file__))
GPU_RATE_PER_HOUR = 4.00  # RTX PRO 6000 on fal
REF_PIXELS = 1920 * 804
REF_SAMPLES = 48
REF_SEC_PER_FRAME = (5.0, 7.0)  # measured on mission control at 1920x804 / 48 spp
CHUNK_OVERHEAD_S = 20.0  # Blender start + scene load + zip/upload of the frames, per request
COLD_START_S = 90.0  # first workers when the app has scaled to zero
VIDEO_SAFE = {"PNG", "JPEG", "TIFF", "TARGA", "TARGA_RAW", "BMP", "WEBP"}
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW: no console flashing up per subprocess

_uploads = {}  # bundle sha256 -> fal storage URL, so a retry or re-render of an unchanged file skips the upload
CURRENT = None  # the job the panel shows


class PlanError(Exception):
    pass


NO_APP_MSG = ("Set the farm app in Preferences > Add-ons > fal Render Farm: the fal app id of your render farm, "
              "<your-fal-username>/blender-farm-2 (deploy farm/app.py on your own fal account)")


# -- estimate ---------------------------------------------------------------------------------------------------

def samples_of(scene):
    eng = scene.render.engine
    if eng == "CYCLES":
        return scene.cycles.samples, "spp"
    if eng.startswith("BLENDER_EEVEE"):
        return scene.eevee.taa_render_samples, "samples"
    return None, ""


def frame_list(scene, mode):
    if mode == "FRAME":
        return [scene.frame_current]
    return list(range(scene.frame_start, scene.frame_end + 1, max(1, scene.frame_step)))


def estimate(scene, n_frames, chunk, concurrency):
    """Rough cost/time from the reference rate, scaled by pixels x samples. An estimate, not a quote."""
    r = scene.render
    pixels = r.resolution_x * r.resolution_y * (r.resolution_percentage / 100.0) ** 2
    samples, _ = samples_of(scene)
    scale = pixels / REF_PIXELS * ((samples or REF_SAMPLES * 0.05) / REF_SAMPLES)
    spf = [max(0.3, s * scale) for s in REF_SEC_PER_FRAME]
    n_chunks = max(1, math.ceil(n_frames / max(1, chunk))) if n_frames else 0
    gpu_s = [n_frames * s + n_chunks * CHUNK_OVERHEAD_S for s in spf]
    waves = math.ceil(n_chunks / max(1, min(concurrency, n_chunks or 1))) if n_chunks else 0
    per = min(chunk, n_frames)
    wall = [waves * (per * s + CHUNK_OVERHEAD_S) for s in spf]
    return {
        "sec_per_frame": spf, "chunks": n_chunks, "gpu_s": gpu_s, "cost": [g / 3600 * GPU_RATE_PER_HOUR for g in gpu_s],
        "wall": wall, "cold_start": COLD_START_S, "pixels": int(pixels), "samples": samples,
    }


def fmt_s(s):
    s = int(round(s))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


# -- plan (main thread) -----------------------------------------------------------------------------------------

@dataclass
class Plan:
    mode: str
    scene_name: str
    frames: list
    step: int
    targets: dict  # frame -> absolute local path, exactly as a local render names it
    farm_pattern: str  # the filename part of render.filepath, with its # padding
    file_format: str
    fps: float
    key: str
    app: str
    chunk_size: int
    concurrency: int
    timeout_s: int
    encode_mp4: bool
    ffmpeg: str
    blender_bin: str
    workdir: str = ""
    copy_path: str = ""
    skipped: list = field(default_factory=list)


def plan(context, mode, prefs):
    import bpy

    scene = context.scene
    r = scene.render
    if not prefs.fal_key.strip():
        raise PlanError("Set your fal key in Preferences > Add-ons > fal Render Farm")
    if not prefs.app_id.strip().strip("/"):
        raise PlanError(NO_APP_MSG)
    if r.image_settings.file_format == "FFMPEG" or getattr(r.image_settings, "media_type", "") == "VIDEO":
        raise PlanError("Output is a video format; the farm renders frame sequences in chunks. Pick an image format "
                        "(PNG, EXR...) and enable 'Encode MP4' in the add-on preferences instead")
    if scene.camera is None:
        raise PlanError("The scene has no active camera")
    if r.filepath.startswith("//") and not bpy.data.filepath:
        raise PlanError("The output path is relative (//) but this file has never been saved; save it first "
                        "or set an absolute output path")
    frames = frame_list(scene, mode)
    if not frames:
        raise PlanError("The frame range is empty")
    targets = {f: os.path.abspath(bpy.path.abspath(r.frame_path(frame=f))) for f in frames}
    pattern = re.split(r"[\\/]", r.filepath)[-1]
    if pattern in ("", ".", ".."):
        pattern = ""
    ffmpeg = prefs.ffmpeg_path.strip() or shutil.which("ffmpeg") or ""
    return Plan(
        mode=mode, scene_name=scene.name, frames=frames, step=max(1, scene.frame_step) if mode == "ANIMATION" else 1,
        targets=targets, farm_pattern=pattern, file_format=r.image_settings.file_format,
        fps=r.fps / (r.fps_base or 1.0), key=prefs.fal_key.strip(), app=prefs.app_id.strip().strip("/"),
        chunk_size=max(1, prefs.chunk_size), concurrency=max(1, prefs.concurrency), timeout_s=prefs.timeout_s,
        encode_mp4=prefs.encode_mp4 and mode == "ANIMATION", ffmpeg=ffmpeg, blender_bin=bpy.app.binary_path,
    )


def save_copy(p):
    """Write the open file, unsaved edits included, to a temp dir. copy=True leaves the user's file, its path and its
    dirty state alone; relative_remap keeps // paths pointing at the same files from the new location."""
    import bpy

    p.workdir = tempfile.mkdtemp(prefix="fal_farm_")
    p.copy_path = os.path.join(p.workdir, "copy.blend")
    bpy.ops.wm.save_as_mainfile(filepath=p.copy_path, copy=True, relative_remap=True, compress=False,
                                check_existing=False)
    if not os.path.exists(p.copy_path):
        raise PlanError("Could not save a temporary copy of the file")


# -- job (background thread) ------------------------------------------------------------------------------------

@dataclass
class Chunk:
    frames: list
    step: int
    status: str = "pending"  # pending queued rendering downloading done failed cancelled
    error: str = ""
    attempts: int = 0
    render_s: float = 0.0
    gpu_s: float = 0.0
    device: str = ""
    handle: dict = None

    @property
    def label(self):
        a, b = self.frames[0], self.frames[-1]
        return f"{a}" if a == b else f"{a}-{b}"


class Job:
    def __init__(self, p: Plan):
        self.p = p
        self.lock = threading.Lock()
        self.cancel_ev = threading.Event()
        self.phase = "starting"  # packing uploading rendering encoding done failed cancelled
        self.message = ""
        self.log = deque(maxlen=200)
        self.chunks = []
        self.bundle_url = self.bundle_id = None
        self.t0 = time.time()
        self.t_end = None
        self.mp4 = None
        self.thread = None
        self.finished_seen = False  # set by the UI once it has reacted to the end of the job

    # ---- public ----
    def start(self):
        self.thread = threading.Thread(target=self._run, name="fal-render-farm", daemon=True)
        self.thread.start()
        return self

    def cancel(self):
        self.cancel_ev.set()
        self._say("cancelling...")
        with self.lock:
            handles = [c.handle for c in self.chunks if c.handle and c.status in ("queued", "rendering")]
        for h in handles:
            threading.Thread(target=fal_api.cancel, args=(self.p.key, h), daemon=True).start()

    def retry_failed(self):
        if self.running:
            return False
        with self.lock:
            failed = [c for c in self.chunks if c.status in ("failed", "cancelled")]
            for c in failed:
                c.status, c.error, c.attempts, c.handle = "pending", "", 0, None
        if not failed:
            return False
        self.cancel_ev.clear()
        self.t0, self.t_end, self.phase = time.time(), None, "starting"
        self.finished_seen = False
        self.thread = threading.Thread(target=self._run, name="fal-render-farm", daemon=True)
        self.thread.start()
        return True

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def wait(self, timeout=None):
        if self.thread:
            self.thread.join(timeout)
        return not self.running

    def snapshot(self):
        with self.lock:
            counts = {}
            for c in self.chunks:
                counts[c.status] = counts.get(c.status, 0) + 1
            frames_done = sum(len(c.frames) for c in self.chunks if c.status == "done")
            return {
                "phase": self.phase, "message": self.message, "counts": counts, "n_chunks": len(self.chunks),
                "frames_done": frames_done + len(self.p.skipped), "frames_total": len(self.p.frames),
                "skipped": len(self.p.skipped), "elapsed": (self.t_end or time.time()) - self.t0,
                "gpu_s": sum(c.gpu_s for c in self.chunks), "render_s": sum(c.render_s for c in self.chunks),
                "failed": [(c.label, c.error) for c in self.chunks if c.status == "failed"],
                "mp4": self.mp4, "mode": self.p.mode, "app": self.p.app,
            }

    # ---- internals ----
    def _say(self, msg):
        with self.lock:
            self.message = msg
        self.log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
        print("fal render farm:", msg)

    def _set_phase(self, phase, msg=None):
        with self.lock:
            self.phase = phase
        if msg:
            self._say(msg)

    def _run(self):
        try:
            if not self.chunks:
                missing = [f for f in self.p.frames if not os.path.exists(self.p.targets[f])]
                self.p.skipped = [f for f in self.p.frames if f not in set(missing)]
                if self.p.skipped:
                    self._say(f"{len(self.p.skipped)} frames already on disk, skipped")
                self.chunks = self._split(missing)
                if not self.chunks:
                    self._finish()
                    return
            if not self.bundle_url:
                self._bundle()
            self._render()
            self._finish()
        except Exception as e:  # noqa: BLE001 - any failure lands in the panel, not a stack trace on stderr only
            if self.cancel_ev.is_set():
                self._set_phase("cancelled", "cancelled")
            else:
                self._set_phase("failed", f"failed: {fal_api._scrub(str(e), self.p.key)}")
                self.log.append(fal_api._scrub(traceback.format_exc(), self.p.key))
            self.t_end = time.time()
        finally:
            if self.p.workdir and not self.running_chunks():
                shutil.rmtree(self.p.workdir, ignore_errors=True)

    def running_chunks(self):
        return any(c.status in ("queued", "rendering", "downloading") for c in self.chunks)

    def _split(self, missing):
        """Contiguous runs (in steps of frame_step) of missing frames, cut into chunks of at most chunk_size."""
        step, out, run = self.p.step, [], []
        for f in missing:
            if run and (f != run[-1] + step or len(run) >= self.p.chunk_size):
                out.append(Chunk(run, step))
                run = []
            run.append(f)
        if run:
            out.append(Chunk(run, step))
        return out

    def _bundle(self):
        p = self.p
        self._set_phase("packing", "packing a copy of the file (textures, fonts, linked data)...")
        packed = os.path.join(p.workdir, "scene.blend")
        proc = subprocess.run(
            [p.blender_bin, "-b", "--factory-startup", p.copy_path, "--python", os.path.join(HERE, "pack_copy.py"),
             "--", packed],
            capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        out = proc.stdout + proc.stderr
        for line in out.splitlines():
            if line.startswith(("PACK-WARNING:", "PACK-INFO:")):
                self.log.append(line)
        problems = [l[len("PACK-PROBLEM:"):].strip() for l in out.splitlines() if l.startswith("PACK-PROBLEM:")]
        if problems:
            raise RuntimeError("the file references data that can't be packed: " + "; ".join(problems[:6]))
        if proc.returncode != 0 or not os.path.exists(packed):
            raise RuntimeError(f"packing failed (Blender exited {proc.returncode}): {out[-800:]}")
        os.remove(p.copy_path)
        if self.cancel_ev.is_set():
            raise RuntimeError("cancelled")

        zpath = os.path.join(p.workdir, "bundle.zip")
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:  # the .blend is saved compressed already
            z.write(packed, "scene.blend")
            z.write(os.path.join(HERE, "farm_gpu.py"), "farm_gpu.py")
        os.remove(packed)
        sha = hashlib.sha256()
        with open(zpath, "rb") as f:
            while b := f.read(8 << 20):
                sha.update(b)
        digest = sha.hexdigest()
        self.bundle_id = digest[:16]
        size = os.path.getsize(zpath)
        if digest in _uploads:
            self.bundle_url = _uploads[digest]
            self._say(f"bundle {self.bundle_id} ({size / 1e6:.1f} MB) already uploaded")
        else:
            self._set_phase("uploading", f"uploading bundle {self.bundle_id} ({size / 1e6:.1f} MB)...")

            def prog(sent, total):
                with self.lock:
                    self.message = f"uploading bundle {self.bundle_id}: {sent / 1e6:.0f}/{total / 1e6:.0f} MB"

            self.bundle_url = fal_api.upload_file(p.key, zpath, progress=prog)
            _uploads[digest] = self.bundle_url
            self._say(f"bundle {self.bundle_id} uploaded")
        os.remove(zpath)

    def _args(self, c):
        p = self.p
        return ["{bundle}/scene.blend", "-S", p.scene_name, "--python", "{bundle}/farm_gpu.py",
                "-o", "{out}/frames/" + p.farm_pattern,
                "-s", str(c.frames[0]), "-e", str(c.frames[-1]), "-j", str(c.step), "-a"]

    def _render(self):
        pending = [c for c in self.chunks if c.status == "pending"]
        n = len(pending)
        self._set_phase("rendering", f"rendering {sum(len(c.frames) for c in pending)} frames in {n} chunks "
                                     f"on {self.p.app} ({min(n, self.p.concurrency)} at a time)")
        with cf.ThreadPoolExecutor(max_workers=min(n, self.p.concurrency), thread_name_prefix="fal-chunk") as pool:
            list(pool.map(self._chunk, pending))

    def _chunk(self, c):
        p = self.p
        while not self.cancel_ev.is_set():
            c.attempts += 1
            try:
                self._chunk_once(c)
                return
            except Exception as e:  # noqa: BLE001
                err = fal_api._scrub(str(e), p.key)
                if "with 0 frames" in err and p.file_format != "PNG":
                    err = (f"the farm returned no {p.file_format} files. {p.app} may only return PNGs; "
                           f"set the farm app to your blender-farm-2 deployment. Blender said: {err[-600:]}")
                if c.handle and c.status in ("queued", "rendering"):
                    fal_api.cancel(p.key, c.handle)  # e.g. a status poll gave up: don't leave a twin rendering
                with self.lock:
                    c.error, c.handle = err, None
                if self.cancel_ev.is_set():
                    break
                if c.attempts >= 2:
                    with self.lock:
                        c.status = "failed"
                    self._say(f"chunk {c.label} failed: {err[:300]}")
                    return
                self._say(f"chunk {c.label} attempt {c.attempts} failed, retrying: {err[:200]}")
                time.sleep(3)
        with self.lock:
            c.status = "cancelled"

    def _chunk_once(self, c):
        p = self.p
        payload = {"bundle_url": self.bundle_url, "bundle_id": self.bundle_id, "blender_args": self._args(c),
                   "timeout_s": int(p.timeout_s), "outputs": ["frames/**/*"]}
        with self.lock:
            c.status = "queued"
        handle = fal_api.submit(p.key, p.app, payload)
        with self.lock:
            c.handle = handle
        delay = 1.0
        while True:
            if self.cancel_ev.is_set():
                fal_api.cancel(p.key, handle)
                raise RuntimeError("cancelled")
            st = fal_api.status(p.key, handle).get("status")
            if st == "IN_PROGRESS":
                with self.lock:
                    c.status = "rendering"
            elif st == "COMPLETED":
                break
            time.sleep(delay)
            delay = min(delay * 1.5, 4.0)
        res = fal_api.result(p.key, handle)
        if "frames_url" not in res:
            raise RuntimeError(f"unexpected farm response: {str(res)[:500]}")
        with self.lock:
            c.status = "downloading"
        zpath = os.path.join(tempfile.gettempdir(), f"fal_farm_{self.bundle_id}_{c.frames[0]}_{c.frames[-1]}.zip")
        fal_api.download(res["frames_url"], zpath)
        try:
            self._extract(zpath, c)
        finally:
            os.remove(zpath)
        with self.lock:
            c.status, c.error, c.handle = "done", "", None
            c.render_s = float(res.get("render_seconds", 0))
            c.gpu_s = c.render_s + float(res.get("bundle_seconds", 0))
            c.device = res.get("device", "")
        self._say(f"chunk {c.label}: {res.get('frame_count')} frames, render {c.render_s:.0f}s on "
                  f"{c.device.split(',')[0]}")

    def _extract(self, zpath, c):
        p = self.p
        by_name = {os.path.basename(p.targets[f]): p.targets[f] for f in c.frames}
        by_lower = {k.lower(): v for k, v in by_name.items()}
        fallback_dir = os.path.dirname(p.targets[c.frames[0]])
        with zipfile.ZipFile(zpath) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                name = info.filename.rsplit("/", 1)[-1]
                dest = by_name.get(name) or by_lower.get(name.lower()) or os.path.join(fallback_dir, name)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with z.open(info) as src, open(dest + ".part", "wb") as dst:
                    shutil.copyfileobj(src, dst, 4 << 20)
                os.replace(dest + ".part", dest)
        missing = [f for f in c.frames if not os.path.exists(p.targets[f])]
        if missing:
            got = ", ".join(n.rsplit("/", 1)[-1] for n in zipfile.ZipFile(zpath).namelist()[:4])
            raise RuntimeError(f"farm output is missing frames {missing[:8]} (got {got})")

    def _finish(self):
        if self.cancel_ev.is_set():
            self._set_phase("cancelled", "cancelled")
        elif any(c.status == "failed" for c in self.chunks):
            n = sum(c.status == "failed" for c in self.chunks)
            self._set_phase("failed", f"{n} chunk(s) failed; fix and press Retry failed chunks")
        else:
            if self.p.encode_mp4:
                self._encode()
            self._set_phase("done", f"done: {len(self.p.frames)} frames in "
                                    f"{os.path.dirname(self.p.targets[self.p.frames[0]])}")
        self.t_end = time.time()

    def _encode(self):
        p = self.p
        if not p.ffmpeg:
            self._say("ffmpeg not found; skipping the MP4 (set its path in the add-on preferences)")
            return
        if p.file_format not in VIDEO_SAFE:
            self._say(f"skipping the MP4: {p.file_format} frames are linear/HDR, encode them in your grade instead")
            return
        self._set_phase("encoding", "encoding MP4...")
        first, last = p.frames[0], p.frames[-1]
        stem = os.path.splitext(os.path.basename(p.targets[first]))[0]
        stem = re.sub(r"\d+$", "", stem).rstrip("_.- ") or "render"
        out = os.path.join(os.path.dirname(p.targets[first]), f"{stem}_{first:04d}-{last:04d}.mp4")
        listing = os.path.join(tempfile.gettempdir(), f"fal_farm_concat_{os.getpid()}.txt")
        with open(listing, "w", encoding="utf-8") as f:
            for fr in p.frames:
                f.write("file '%s'\nduration %.6f\n" % (p.targets[fr].replace("\\", "/").replace("'", r"'\''"), 1 / p.fps))
            f.write("file '%s'\n" % p.targets[last].replace("\\", "/").replace("'", r"'\''"))
        cmd = [p.ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listing,
               "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-r", f"{p.fps:g}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
               "-crf", "16", "-preset", "slow", out]
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW)
        os.remove(listing)
        if proc.returncode == 0:
            self.mp4 = out
            self._say(f"MP4: {out}")
        else:
            self._say(f"ffmpeg failed: {proc.stderr[-400:]}")
