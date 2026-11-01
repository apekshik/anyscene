"""Call the AnyScene endpoint and print its stage events live.

    uv run --with fal-client python endpoint/client.py plan <image path or url> [...] [--prompt "..."] [--out DIR]
    uv run --with fal-client python endpoint/client.py edit <plan_id> "move the counter to the left wall" [--out DIR]

Local image paths are uploaded to fal storage first. Outputs (plan.json and the images) are saved to --out.
Uses FAL_SERVERLESS_KEY (the Serverless account the app is deployed under), falling back to FAL_KEY.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

# The fal app id, <owner>/<app>: set ANYSCENE_APP=<your-fal-username>/anyscene, or pass --app. No default.
APP_ENV = "ANYSCENE_APP"
PREFIX = "ANYSCENE_STAGE "


def user_env(name):
    if os.environ.get(name):
        return os.environ[name]
    if sys.platform == "win32":
        parts = subprocess.run(["reg", "query", r"HKCU\Environment", "/v", name], capture_output=True, text=True).stdout.split()
        if name in parts:
            return parts[parts.index(name) + 2]
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["plan", "edit", "build"])
    p.add_argument("--tier", default="draft")
    p.add_argument("--events", help="also write every stage event (JSON lines) here, e.g. to drive a UI replay")
    p.add_argument("args", nargs="+")
    p.add_argument("--prompt", default="")
    p.add_argument("--effort", default="high")
    p.add_argument("--floor-plan")
    p.add_argument("--out", default="anyscene_out")
    p.add_argument("--app", help="fal app id (default: $ANYSCENE_APP)")
    a = p.parse_args()
    app = (a.app or user_env(APP_ENV) or "").strip().strip("/")
    if not app:
        p.error(f"set {APP_ENV}=<your-fal-username>/anyscene or pass --app")
    sys.stdout.reconfigure(encoding="utf-8")  # stage marks (✓ ✗) on a Windows console
    os.environ["FAL_KEY"] = user_env("FAL_SERVERLESS_KEY") or user_env("FAL_KEY")
    import fal_client

    up = lambda s: s if s.startswith("http") else fal_client.upload_file(s)
    if a.cmd == "plan":
        payload = {"reference_image_urls": [up(s) for s in a.args], "prompt": a.prompt, "effort": a.effort}
        if a.floor_plan:
            payload["floor_plan_url"] = up(a.floor_plan)
    elif a.cmd == "edit":
        payload = {"plan_id": a.args[0], "edit": " ".join(a.args[1:]), "effort": a.effort}
    else:
        payload = {"plan_id": a.args[0], "tier": a.tier}

    t0 = time.time()
    seen = set()
    events = open(a.events, "w", encoding="utf-8") if a.events else None

    def on_update(update):
        for log in getattr(update, "logs", None) or []:
            msg = log.get("message", "")
            if PREFIX not in msg or msg in seen:
                continue
            seen.add(msg)
            ev = json.loads(msg.split(PREFIX, 1)[1])
            if events:
                events.write(json.dumps({"t": round(time.time() - t0, 1), **ev}) + "\n")
                events.flush()
            mark = {"running": "…", "done": "✓", "failed": "✗"}.get(ev["status"], "·")
            if ev.get("prop") and ev["prop"].get("status") == "meshing":
                continue  # one line per prop is enough: print it when its mesh lands
            line = f"[{time.time() - t0:6.1f}s] {mark} {ev['stage']:<20} {ev.get('message', '')}"
            if ev.get("preview_url"):
                line += f"\n{'':32}preview: {ev['preview_url']}"
            print(line, flush=True)

    route = "build" if a.cmd == "build" else "plan"
    res = fal_client.subscribe(f"{app}/{route}", arguments=payload, with_logs=True, on_queue_update=on_update)
    os.makedirs(a.out, exist_ok=True)
    if route == "build":
        with open(os.path.join(a.out, "build.json"), "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1)
        for i, url in enumerate(res["stills"]):
            urllib.request.urlretrieve(url, os.path.join(a.out, f"still_{i}.png"))
        print(f"\nscene_id {res['scene_id']}  timings {res['timings']}\npackage {res['package_url']}\n"
              f"stand-ins left: {res['standins_left']}\nsaved to {a.out}")
        return
    with open(os.path.join(a.out, "plan.json"), "w", encoding="utf-8") as f:
        json.dump(res["plan"], f, indent=1, ensure_ascii=False)
    for key in ("floor_plan_url", "blockout_reference_url", "blockout_overview_url", "comparison_url"):
        urllib.request.urlretrieve(res[key], os.path.join(a.out, key.replace("_url", ".png")))
    print(f"\nplan_id {res['plan_id']}  timings {res['timings']}  saved to {a.out}")


if __name__ == "__main__":
    main()
