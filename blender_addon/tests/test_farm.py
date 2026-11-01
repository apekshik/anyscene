"""End-to-end test of the fal Render Farm add-on, headless, against the real farm.

    blender -b --factory-startup --python-exit-code 1 --python test_farm.py -- <workdir> --app <your-fal-username>/blender-farm-2 [--chunk 12]

1. builds the test scene (make_test_scene.py) in <workdir>/scene/
2. enables the add-on from blender_addon/fal_render_farm (the folder, as an add-on module)
3. sets the fal key from FAL_SERVERLESS_KEY (Windows user env / registry) in this process only; never printed
4. registers the UI: calls every operator's poll() and draws the panel + status bar into a recording layout
5. renders the 48-frame animation through the add-on's operator, waits, and checks every frame file by name
6. checks the user's .blend was not modified, then resume: deletes 2 frames and re-renders (only those go out)
7. renders frame 1 locally on this GPU and compares it with the farm's frame 1 (PSNR)
8. "Render this frame" with OPEN_EXR output (needs the farm's `outputs` support)
Prints a TEST-SUMMARY json line at the end; exits 1 on any failure.
"""

import argparse
import hashlib
import json
import math
import os
import runpy
import shutil
import subprocess
import sys
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON_PARENT = os.path.dirname(HERE)  # blender_addon/
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("workdir")
ap.add_argument("--app", default=os.environ.get("ANYSHOT_FARM_APP"),
                help="fal app id of your farm, <your-fal-username>/blender-farm-2 (default: $ANYSHOT_FARM_APP)")
ap.add_argument("--chunk", type=int, default=12)
ap.add_argument("--concurrency", type=int, default=20)
ap.add_argument("--ffmpeg", default="", help="ffmpeg path for the MP4 step (else PATH)")
args = ap.parse_args(argv)
if not args.app:
    ap.error("pass --app <your-fal-username>/blender-farm-2 or set ANYSHOT_FARM_APP")
work = os.path.abspath(args.workdir)
summary = {"app": args.app, "chunk": args.chunk, "checks": {}}
failures = []


def check(name, ok, detail=""):
    summary["checks"][name] = {"ok": bool(ok), "detail": detail}
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)
    if not ok:
        failures.append(name)


def user_env(name):
    if os.environ.get(name):
        return os.environ[name]
    out = subprocess.run(["reg", "query", r"HKCU\Environment", "/v", name], capture_output=True, text=True).stdout
    parts = out.split()
    return parts[parts.index(name) + 2] if name in parts else None


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def wait(job, label):
    t0, last = time.time(), ""
    while not job.wait(timeout=5):
        s = job.snapshot()
        line = f"  [{label} {time.time() - t0:5.0f}s] {s['phase']}: {s['message'][:110]} | {s['counts']}"
        if line != last:
            print(line, flush=True)
            last = line
    return job.snapshot()


# 1. scene -------------------------------------------------------------------------------------------------------
scene_dir = os.path.join(work, "scene")
shutil.rmtree(scene_dir, ignore_errors=True)
subprocess.run([bpy.app.binary_path, "-b", "--factory-startup", "--python", os.path.join(HERE, "make_test_scene.py"),
                "--", scene_dir], check=True, capture_output=True)
blend = os.path.join(scene_dir, "test_scene.blend")
check("test scene built", os.path.exists(blend), blend)

# 2. add-on from its folder --------------------------------------------------------------------------------------
import addon_utils  # noqa: E402

sys.path.insert(0, ADDON_PARENT)
mod = addon_utils.enable("fal_render_farm", default_set=True, handle_error=None)  # --factory-startup: prefs are never saved
check("add-on enabled from folder", mod is not None and "fal_render_farm" in bpy.context.preferences.addons,
      getattr(mod, "__file__", ""))
import fal_render_farm as addon  # noqa: E402
from fal_render_farm import job as farm_job  # noqa: E402

# 3. key ---------------------------------------------------------------------------------------------------------
prefs = bpy.context.preferences.addons["fal_render_farm"].preferences
key = user_env("FAL_SERVERLESS_KEY")
check("FAL_SERVERLESS_KEY found", bool(key))
prefs.fal_key = key
prefs.app_id = args.app
prefs.chunk_size = args.chunk
prefs.concurrency = args.concurrency
prefs.encode_mp4 = True
prefs.ffmpeg_path = args.ffmpeg

bpy.ops.wm.open_mainfile(filepath=blend)
before = sha(blend)
dirty_before = bpy.data.is_dirty  # background Blender reports a freshly opened file as dirty; compare, don't assume
scene = bpy.context.scene


# 4. UI: polls + panel/status draw into a recording layout -------------------------------------------------------
class Rec:
    """Stands in for UILayout: accepts any call/attribute and records labels, ops and props."""

    def __init__(self, log):
        self._log = log

    def __getattr__(self, name):
        def fn(*a, **k):
            if name in ("label", "operator", "prop", "progress"):
                self._log.append((name, k.get("text") or (a[1] if name == "prop" and len(a) > 1 else (a[0] if a else ""))))
            return Rec(self._log)
        return fn

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)


def draw_panel():
    log = []
    fake = type("P", (), {})()
    fake.layout = Rec(log)
    addon.FALRF_PT_panel.draw(fake, bpy.context)
    addon.FALRF_PT_panel.draw_header(fake, bpy.context)
    addon.draw_status(fake, bpy.context)
    return log


try:
    ui = draw_panel()
    labels = [t for k, t in ui if k == "label"]
    check("panel draws (idle)", any("Estimate" in str(t) for t in labels), " | ".join(map(str, labels[:5])))
    summary["panel_idle"] = [str(t) for t in labels]
except Exception as e:  # noqa: BLE001
    check("panel draws (idle)", False, repr(e))

ctx = bpy.context
polls = {
    "render": addon.FALRF_OT_render.poll(ctx), "cancel(idle)": addon.FALRF_OT_cancel.poll(ctx),
    "retry(idle)": bool(addon.FALRF_OT_retry.poll(ctx)), "check_key": True,
}
check("operator polls (idle)", polls["render"] and not polls["cancel(idle)"] and not polls["retry(idle)"], str(polls))
check("fal accepts the key", fal_ok := addon.fal_api.check_key(key, args.app)[0])

# 5. animation on the farm ---------------------------------------------------------------------------------------
frames = list(range(scene.frame_start, scene.frame_end + 1))
targets = {f: os.path.abspath(bpy.path.abspath(scene.render.frame_path(frame=f))) for f in frames}
shutil.rmtree(os.path.dirname(targets[1]), ignore_errors=True)
est = farm_job.estimate(scene, len(frames), args.chunk, args.concurrency)
summary["estimate"] = {"cost_usd": [round(c, 3) for c in est["cost"]], "gpu_s": [round(g) for g in est["gpu_s"]],
                       "wall_s": [round(w) for w in est["wall"]], "sec_per_frame": est["sec_per_frame"]}

t0 = time.time()
res = bpy.ops.fal_render_farm.render(mode="ANIMATION")
check("render operator started", res == {"FINISHED"} and farm_job.CURRENT is not None, str(res))
job = farm_job.CURRENT
check("operator polls (running)", not addon.FALRF_OT_render.poll(ctx) and addon.FALRF_OT_cancel.poll(ctx))
time.sleep(1)
try:
    ui = draw_panel()
    check("panel draws (running)", any("Starting" in str(t) or "Packing" in str(t) or "Uploading" in str(t)
                                      or "Rendering" in str(t) for k, t in ui if k == "label"))
except Exception as e:  # noqa: BLE001
    check("panel draws (running)", False, repr(e))
s = wait(job, "anim")
wall = time.time() - t0
missing = [f for f in frames if not os.path.exists(targets[f])]
check("animation job done", s["phase"] == "done", s["message"])
check("all 48 frames on disk with local names", not missing,
      f"{len(frames) - len(missing)}/48 e.g. {os.path.basename(targets[1])} .. {os.path.basename(targets[48])}"
      + (f", missing {missing[:6]}" if missing else ""))
extra = sorted(set(os.listdir(os.path.dirname(targets[1]))) - {os.path.basename(t) for t in targets.values()})
check("no stray files in the output dir", all(e.endswith(".mp4") for e in extra), str(extra[:5]))
summary["anim"] = {"wall_s": round(wall, 1), "chunks": s["n_chunks"], "gpu_s": round(s["gpu_s"], 1),
                   "render_s": round(s["render_s"], 1), "cost_usd": round(s["gpu_s"] / 3600 * 4.0, 4),
                   "devices": sorted({c.device for c in job.chunks}), "mp4": s["mp4"],
                   "per_chunk_render_s": [c.render_s for c in job.chunks], "log": list(job.log)[-12:]}
if args.ffmpeg or shutil.which("ffmpeg"):
    check("MP4 encoded", bool(s["mp4"]) and os.path.getsize(s["mp4"]) > 10000, str(s["mp4"]))
check("user's .blend untouched (bytes and dirty flag)", sha(blend) == before and bpy.data.is_dirty == dirty_before,
      f"sha {sha(blend)[:12]} vs {before[:12]}, dirty {bpy.data.is_dirty} vs {dirty_before}")
ui = draw_panel()
check("panel draws (done)", any("Done" in str(t) for k, t in ui if k == "label"))
check("operator polls (done)", addon.FALRF_OT_render.poll(ctx) and not addon.FALRF_OT_cancel.poll(ctx))

# 6. resume --------------------------------------------------------------------------------------------------------
for f in (5, 30):
    os.remove(targets[f])
t0 = time.time()
bpy.ops.fal_render_farm.render(mode="ANIMATION")
s2 = wait(farm_job.CURRENT, "resume")
check("resume re-renders only the missing frames",
      s2["phase"] == "done" and s2["skipped"] == 46 and s2["n_chunks"] == 2 and all(os.path.exists(targets[f]) for f in frames),
      f"skipped {s2['skipped']}, chunks {s2['n_chunks']}, {time.time() - t0:.0f}s")
summary["resume"] = {"wall_s": round(time.time() - t0, 1), "chunks": s2["n_chunks"], "skipped": s2["skipped"],
                     "log": list(farm_job.CURRENT.log)[-4:]}

# 7. parity: local GPU render of frame 1 vs the farm's ------------------------------------------------------------
runpy.run_path(os.path.join(ADDON_PARENT, "fal_render_farm", "farm_gpu.py"))  # same device setup as the farm
local = os.path.join(work, "local_0001.png")
saved_fp = scene.render.filepath
scene.frame_set(1)
scene.render.filepath = local
t0 = time.time()
bpy.ops.render.render(write_still=True)
local_s = time.time() - t0
scene.render.filepath = saved_fp


def pixels(path):
    import numpy as np

    img = bpy.data.images.load(path, check_existing=False)
    a = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    size = tuple(img.size)
    bpy.data.images.remove(img)
    return a.reshape(-1, 4), size


import numpy as np  # noqa: E402

a, sa = pixels(local)
b, sb = pixels(targets[1])
mse = float(np.mean((a[:, :3] - b[:, :3]) ** 2))
psnr = 99.0 if mse == 0 else 10 * math.log10(1.0 / mse)
maxdiff = float(np.max(np.abs(a - b)))
check("local vs farm frame 1: same size", sa == sb, f"{sa} vs {sb}")
check("local vs farm frame 1: PSNR >= 30 dB", psnr >= 30, f"PSNR {psnr:.2f} dB, max abs diff {maxdiff:.3f}")
summary["parity"] = {"psnr_db": round(psnr, 2), "max_abs_diff": round(maxdiff, 4), "local_render_s": round(local_s, 1),
                     "local": local, "farm": targets[1], "local_device": bpy.context.preferences.addons["cycles"].preferences.compute_device_type}

# 8. single frame, EXR -------------------------------------------------------------------------------------------
scene.render.image_settings.file_format = "OPEN_EXR"
scene.render.filepath = "//renders/exr/still_###"
scene.frame_set(17)
exr = os.path.abspath(bpy.path.abspath(scene.render.frame_path(frame=17)))
shutil.rmtree(os.path.dirname(exr), ignore_errors=True)
t0 = time.time()
bpy.ops.fal_render_farm.render(mode="FRAME")
s3 = wait(farm_job.CURRENT, "exr")
ok = s3["phase"] == "done" and os.path.exists(exr)
check("render this frame (OPEN_EXR) lands as " + os.path.basename(exr), ok, s3["message"])
if ok:
    with open(exr, "rb") as f:
        check("EXR file is a real OpenEXR", f.read(4) == b"\x76\x2f\x31\x01")
summary["exr_frame"] = {"wall_s": round(time.time() - t0, 1), "path": exr, "gpu_s": round(s3["gpu_s"], 1)}

# unregister cleanly
addon_utils.disable("fal_render_farm", default_set=True)
check("add-on unregisters", "fal_render_farm" not in bpy.context.preferences.addons)

summary["failures"] = failures
print("TEST-SUMMARY " + json.dumps(summary), flush=True)
sys.exit(1 if failures else 0)
