"""Call blend2unreal. FAL_KEY in the environment (the FAL_SERVERLESS_KEY user variable on the owner's box).

    python client.py upload <scene.zip|.blend>                       -> prints the fal storage URL
    python client.py export <scene_url> [--options '{"dof": {...}}'] [--out result.json] [--fresh] [--no-cache]
    python client.py shard <plan.json> <scene_url> --n 40 [--device cpu] [--procs 2]    (bench: no cache read/write)

Polls the queue (submit + status) instead of subscribe(), which hung in AnyShot's tests, and prints the app's
BLEND2UNREAL stage lines as they arrive.
"""
import argparse
import json
import os
import sys
import time

import fal_client

APP = os.environ.get("BLEND2UNREAL_APP", "apek/blend2unreal")


def run(path, payload, out=None):
    t0 = time.time()
    h = fal_client.submit(APP, arguments=payload, path=path)
    print("request", h.request_id, flush=True)
    seen = 0
    while True:
        st = h.status(with_logs=True)
        logs = getattr(st, "logs", None) or []
        for l in logs[seen:]:
            msg = l.get("message", "")
            if "BLEND2UNREAL" in msg or "blend2unreal" in msg:
                print(f"[{time.time() - t0:6.0f}s] {msg.strip()[:400]}", flush=True)
        seen = max(seen, len(logs))
        if isinstance(st, fal_client.Completed):
            break
        time.sleep(10)
    res = h.get()
    print(f"done in {time.time() - t0:.0f}s wall", flush=True)
    if out:
        json.dump({"request_id": h.request_id, "wall_s": round(time.time() - t0, 1), "result": res},
                  open(out, "w"), indent=1)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["upload", "export", "shard"])
    ap.add_argument("args", nargs="+")
    ap.add_argument("--options", default="{}")
    ap.add_argument("--out")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--device", default="gpu")
    ap.add_argument("--procs", type=int, default=0)
    a = ap.parse_args()
    if a.cmd == "upload":
        print(fal_client.upload_file(a.args[0]))
    elif a.cmd == "export":
        res = run("/export", {"scene_url": a.args[0], "options": json.loads(a.options), "fresh": a.fresh,
                              "use_cache": not a.no_cache, "inline_scene_json": False}, a.out)
        print(json.dumps({k: v for k, v in res.items() if k != "scene_json"}, indent=1)[:6000])
    else:
        plan = json.load(open(a.args[0]))
        rows = plan["assets"][: a.n]
        opts = {**json.loads(a.options), "device": a.device, "procs": a.procs}
        res = run("/shard", {"scene_url": a.args[1], "rows": rows, "options": opts, "use_cache": False,
                             "job_id": "bench"}, a.out)
        print(json.dumps(res, indent=1)[:4000])


if __name__ == "__main__":
    sys.exit(main())
