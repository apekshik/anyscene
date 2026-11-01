"""Call the scene builder and print its live log.

    uv run --python 3.13 --with fal-client python builder/client.py build <image path or url> [...] [--prompt "..."]
    uv run --python 3.13 --with fal-client python builder/client.py smoke

Local images are uploaded to fal storage first. Every stage event goes to --events (JSON lines, for UI replay); the
response and the stills are saved to --out. Uses FAL_SERVERLESS_KEY (the account the app is deployed under).
"""

import argparse
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "endpoint"))
from client import user_env  # noqa: E402

# /ref2scene, /scene2image, /scene2video (/build, /shots kept as aliases); ANYSCENE_APP=<owner>/<app> for your own
APP = os.environ.get("ANYSCENE_APP")
PREFIX = "ANYSCENE_STAGE "


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["build", "smoke", "shots"])
    p.add_argument("refs", nargs="*")
    p.add_argument("--prompt", default="")
    p.add_argument("--effort", default="medium")
    p.add_argument("--out", default="builder_out")
    p.add_argument("--events")
    p.add_argument("--app", default=APP, help="fal app id (default: $ANYSCENE_APP)")
    p.add_argument("--build-id", help="shots: the finished build to shoot")
    p.add_argument("--mode", default="images", choices=["images", "video"])
    p.add_argument("--shot", action="append", default=[],
                   help="shots: a camera name from the build's shots.json, or a description in words (repeatable)")
    p.add_argument("--settings", default="{}", help='shots: JSON, e.g. {"seconds": 8, "handheld": "subtle"}')
    a = p.parse_args()
    if not a.app:
        p.error("set ANYSCENE_APP=<your-fal-username>/anyscene or pass --app")
    sys.stdout.reconfigure(encoding="utf-8")
    os.environ["FAL_KEY"] = user_env("FAL_SERVERLESS_KEY") or user_env("FAL_KEY")
    import fal_client

    up = lambda s: s if s.startswith("http") else fal_client.upload_file(s)
    payload = {"reference_image_urls": [up(s) for s in a.refs], "prompt": a.prompt, "effort": a.effort}
    if a.cmd == "shots":
        shots = [{"name": x} if " " not in x else {"description": x} for x in a.shot]
        payload = {"build_id": a.build_id, "mode": a.mode, "shots": shots, "settings": json.loads(a.settings),
                   "effort": a.effort}
    os.makedirs(a.out, exist_ok=True)
    events = open(a.events or os.path.join(a.out, "events.jsonl"), "w", encoding="utf-8")
    t0, seen = time.time(), set()

    def on_update(update):
        for log in getattr(update, "logs", None) or []:
            msg = log.get("message", "")
            if msg in seen:
                continue
            if PREFIX not in msg:
                if any(k in msg for k in ("Traceback", "Error", "error:", "Exception")):
                    seen.add(msg)
                    print(f"[worker] {msg[:600]}", flush=True)
                continue
            seen.add(msg)
            ev = json.loads(msg.split(PREFIX, 1)[1])
            events.write(json.dumps(ev) + "\n")
            events.flush()
            line = f"[{(time.time() - t0) / 60:6.1f}m] {ev['stage']:<10} {ev.get('message', '')[:160]}"
            if ev.get("preview_url"):
                line += f"\n{'':20}image: {ev['preview_url']}"
            print(line, flush=True)

    on_enqueue = lambda rid: print(f"request {rid}\nwatch: http://localhost:3210/?watch={rid}", flush=True)
    res = fal_client.subscribe(f"{a.app}/{a.cmd}", arguments=payload, with_logs=True, on_queue_update=on_update,
                               on_enqueue=on_enqueue, client_timeout=3 * 3600) if a.cmd != "smoke" else \
        fal_client.subscribe(f"{a.app}/smoke", arguments=payload or {"reference_image_urls": []})
    with open(os.path.join(a.out, f"{a.cmd}.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    if a.cmd == "shots":
        for url in res["stills"] + res["videos"]:
            urllib.request.urlretrieve(url, os.path.join(a.out, url.rsplit("/", 1)[-1]))
    if a.cmd == "build":
        for i, url in enumerate(res["stills"]):
            urllib.request.urlretrieve(url, os.path.join(a.out, f"still_{i}.png"))
    print(json.dumps({k: v for k, v in res.items() if k != "critiques"}, indent=1)[:3000])


if __name__ == "__main__":
    main()
