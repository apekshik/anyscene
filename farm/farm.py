"""Render a scene's shots on the fal farm (farm/app.py) instead of the local GPU.

    uv run --with fal-client --with boto3 python farm/farm.py bundle <scene>            pack + upload, prints the bundle id
    uv run --with fal-client --with boto3 python farm/farm.py render <scene> --app <owner/app> [--shots a,b] [--frames 1-24]
                                                      [--chunk 24] [--out DIR]

<scene> is a folder under scenes/; its farm settings live in farm/jobs/<scene>.json:
    {"blend": "mc.blend",                     the scene file (never modified; packed into a copy)
     "scripts": ["scripts/gpu_prefs.py"],     run before camera/shoot.py, in order (paths relative to the scene)
     "per_shot_scripts": {"scripts/nocurl.py": {"except": ["orbital_push"]}}}
Frames land in <out>/<shot>/frames/####.png, the same layout camera/shoot.py writes locally, so the scene's grade
step runs on them unchanged. Existing frames are skipped, so a render can be resumed or topped up.
"""

import argparse
import concurrent.futures as cf
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "farm" / ".bundles.json"  # scene -> last uploaded bundle (id, key)
BUCKET = "anyscene-packs"  # private; bundles are fetched through presigned links


def user_env(name):
    if os.environ.get(name):
        return os.environ[name]
    if sys.platform == "win32":
        out = subprocess.run(["reg", "query", r"HKCU\Environment", "/v", name], capture_output=True, text=True).stdout
        parts = out.split()
        if name in parts:
            return parts[parts.index(name) + 2]
    return None


def s3():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3", region_name="auto", endpoint_url=f"https://{user_env('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        aws_access_key_id=user_env("R2_ACCESS_KEY_ID"), aws_secret_access_key=user_env("R2_SECRET_ACCESS_KEY"),
        config=Config(signature_version="s3v4"),
    )


def blender():
    exe = os.environ.get("BLENDER") or shutil.which("blender") or r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"
    if not Path(exe).exists() and not shutil.which(exe):
        sys.exit("Blender not found; set BLENDER")
    return exe


def job_config(scene):
    return json.loads((ROOT / "farm" / "jobs" / f"{scene}.json").read_text())


def cmd_bundle(scene):
    cfg = job_config(scene)
    sdir = ROOT / "scenes" / scene
    stage = Path(tempfile.mkdtemp(prefix=f"farm-{scene}-"))
    print(f"packing {cfg['blend']} (the scene file is only read)...", flush=True)
    r = subprocess.run([blender(), "-b", str(sdir / cfg["blend"]), "--python", str(ROOT / "farm" / "pack.py"), "--",
                        str(stage / "scene.blend")], capture_output=True, text=True)
    for line in (r.stdout + r.stderr).splitlines():
        if line.startswith("pack:") or "Error" in line:
            print(" ", line)
    if r.returncode != 0 or not (stage / "scene.blend").exists():
        sys.exit("pack failed")
    shutil.copytree(ROOT / "camera", stage / "camera", ignore=shutil.ignore_patterns("__pycache__", "test", "examples"))
    shutil.copy(sdir / "shots.json", stage / "shots.json")
    for s in cfg.get("scripts", []) + list(cfg.get("per_shot_scripts", {})):
        shutil.copy(sdir / s, stage / Path(s).name)
    zpath = stage.with_suffix(".zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:  # the .blend is already compressed
        for p in sorted(stage.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(stage).as_posix())
    sha = hashlib.sha256(zpath.read_bytes()).hexdigest()
    bundle_id, key = sha[:16], f"farm/bundles/{scene}/{sha[:16]}.zip"
    print(f"uploading {zpath.stat().st_size / 1e6:.0f} MB as {BUCKET}/{key}", flush=True)
    s3().upload_file(str(zpath), BUCKET, key)
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    state[scene] = {"id": bundle_id, "key": key, "time": time.strftime("%Y-%m-%d %H:%M")}
    STATE.write_text(json.dumps(state, indent=1))
    shutil.rmtree(stage, ignore_errors=True)
    zpath.unlink()
    print("bundle", bundle_id)


def chunks(n, chunk, frames=None):
    a0, b0 = (map(int, frames.split("-")) if frames else (1, n))
    for a in range(a0, b0 + 1, chunk):
        yield a, min(a + chunk - 1, b0)


def cmd_render(scene, app, shots, frames, chunk, out, workers):
    # The farm app lives on a Serverless-enabled account, which may differ from the FAL_KEY used for generation.
    if user_env("FAL_SERVERLESS_KEY"):
        os.environ["FAL_KEY"] = user_env("FAL_SERVERLESS_KEY")
    import fal_client

    cfg = job_config(scene)
    bundle = json.loads(STATE.read_text())[scene]
    url = s3().generate_presigned_url("get_object", Params={"Bucket": BUCKET, "Key": bundle["key"]}, ExpiresIn=6 * 3600)
    defs = {s["name"]: s for s in json.loads((ROOT / "scenes" / scene / "shots.json").read_text())["shots"]}
    shots = shots.split(",") if shots else list(defs)
    out = Path(out or ROOT / "scenes" / scene / "out" / "shots")

    jobs = []
    for shot in shots:
        have = {int(p.stem) for p in (out / shot / "frames").glob("*.png")}
        for a, b in chunks(defs[shot]["frames"], chunk, frames):
            if all(f in have for f in range(a, b + 1)):
                continue
            pre = []
            for s in cfg.get("scripts", []):
                pre += ["--python", "{bundle}/" + Path(s).name]
            for s, rule in cfg.get("per_shot_scripts", {}).items():
                if shot not in rule.get("except", []):
                    pre += ["--python", "{bundle}/" + Path(s).name]
            args = ["{bundle}/scene.blend", *pre, "--python", "{bundle}/camera/shoot.py", "--",
                    "--shots", "{bundle}/shots.json", "--out", "{out}", "--only", shot, "--frames", f"{a}-{b}", "--no-encode"]
            jobs.append((shot, a, b, {"bundle_url": url, "bundle_id": bundle["id"], "blender_args": args}))
    print(f"{len(jobs)} chunks for {scene} on {app} (bundle {bundle['id']})", flush=True)

    def run(job):
        shot, a, b, payload = job
        t0 = time.time()
        res = fal_client.subscribe(app, arguments=payload)
        data = urllib.request.urlopen(res["frames_url"], timeout=600).read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():  # <shot>/frames/####.png
                dest = out / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(name))
        return (f"{shot} {a}-{b}: {res['frame_count']} frames, render {res['render_seconds']} s, bundle {res['bundle_seconds']} s,"
                f" wall {time.time() - t0:.0f} s on {res['device']}")

    t0 = time.time()
    with cf.ThreadPoolExecutor(workers) as pool:
        for fut in cf.as_completed([pool.submit(run, j) for j in jobs]):
            try:
                print(fut.result(), flush=True)
            except Exception as e:  # keep going; a rerun picks up missing chunks
                print("FAILED:", str(e)[:1500], flush=True)
    print(f"done in {time.time() - t0:.0f} s; frames in {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bundle")
    b.add_argument("scene")
    r = sub.add_parser("render")
    r.add_argument("scene")
    r.add_argument("--app", required=True)
    r.add_argument("--shots")
    r.add_argument("--frames")
    r.add_argument("--chunk", type=int, default=24)
    r.add_argument("--out")
    r.add_argument("--workers", type=int, default=20)
    a = p.parse_args()
    if a.cmd == "bundle":
        cmd_bundle(a.scene)
    else:
        cmd_render(a.scene, a.app, a.shots, a.frames, a.chunk, a.out, a.workers)
