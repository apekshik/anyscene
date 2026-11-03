"""Call apek/unreal-build (or the probe) and wait by polling the submit handle (subscribe() has hung on long jobs).

    python call.py <app> <route> '<json args>' | @args.json [out.json]
Prints queue/log lines as they arrive, the timings (queued, running) and the result; writes the result to out.json."""
import json
import sys
import time

import fal_client

app, route, a = sys.argv[1], sys.argv[2], sys.argv[3]
args = json.load(open(a[1:])) if a.startswith("@") else json.loads(a)  # @file: PowerShell 5.1 strips quotes in args
out = sys.argv[4] if len(sys.argv) > 4 else None
t0 = time.time()
h = fal_client.submit(f"{app}/{route}", arguments=args)
print("request", h.request_id, flush=True)
seen, t_run = 0, None
while True:
    st = h.status(with_logs=True)
    logs = getattr(st, "logs", None) or []
    for l in logs[seen:]:
        print(f"[{time.time() - t0:6.0f}s] {l.get('message', '')[:300]}", flush=True)
    seen = len(logs)
    if isinstance(st, fal_client.InProgress) and t_run is None:
        t_run = time.time()
        print(f"running after {t_run - t0:.0f}s in queue", flush=True)
    if isinstance(st, fal_client.Completed):
        break
    time.sleep(5)
try:
    res = h.get()
except Exception as e:  # noqa: BLE001
    res = {"error": str(e)[:6000]}
t1 = time.time()
timing = {"queued_s": round((t_run or t1) - t0, 1), "running_s": round(t1 - (t_run or t1), 1), "total_s": round(t1 - t0, 1),
          "request_id": h.request_id}
print(json.dumps(timing))
print(json.dumps(res, indent=1)[:8000])
if out:
    json.dump({"timing": timing, "result": res}, open(out, "w"), indent=1)
