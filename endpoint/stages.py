"""Stage events: one JSON object per line on stdout, prefixed so clients can pick them out of the fal queue logs."""

import json
import sys
import time

PREFIX = "ANYSCENE_STAGE "


class Stages:
    def __init__(self, request_id: str = ""):
        self.request_id = request_id
        self.t0 = time.time()
        self.current = None

    def emit(self, stage: str, status: str = "running", message: str = "", progress: float | None = None,
             preview_url: str | None = None, **extra):
        event = {"stage": stage, "status": status, "message": message, "elapsed_s": round(time.time() - self.t0, 1)}
        if progress is not None:
            event["progress"] = round(progress, 3)
        if preview_url:
            event["preview_url"] = preview_url
        event.update(extra)
        print(PREFIX + json.dumps(event), flush=True)
        sys.stdout.flush()
        self.current = stage

    def start(self, stage, message=""):
        self.emit(stage, "running", message)

    def done(self, stage, message="", **extra):
        self.emit(stage, "done", message, **extra)

    def fail(self, message):
        self.emit(self.current or "unknown", "failed", message)
