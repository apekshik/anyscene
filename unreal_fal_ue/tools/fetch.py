"""Status and result of an earlier request (e.g. after the local watcher died).

    python fetch.py <app> <request_id> [out.json] [--wait]
--wait polls every 30 s until the request completes (restartable: only the request id is needed)."""
import json
import sys
import time

import fal_client

WAIT = "--wait" in sys.argv
sys.argv = [a for a in sys.argv if a != "--wait"]
app, rid = sys.argv[1], sys.argv[2]
st = fal_client.status(app, rid, with_logs=True)
while WAIT and not isinstance(st, fal_client.Completed):
    time.sleep(30)
    st = fal_client.status(app, rid, with_logs=True)
logs = getattr(st, "logs", None) or []
print(type(st).__name__, "log lines", len(logs))
for l in logs[-40:]:
    print(l.get("timestamp", ""), l.get("message", "")[:300])
if isinstance(st, fal_client.Completed):
    try:
        res = fal_client.result(app, rid)
    except Exception as e:  # noqa: BLE001
        res = {"error": str(e)[:6000]}
    print(json.dumps(res, indent=1)[:8000])
    if len(sys.argv) > 3:
        json.dump({"result": res, "metrics": getattr(st, "metrics", None)}, open(sys.argv[3], "w"), indent=1)
    print("metrics", getattr(st, "metrics", None))
