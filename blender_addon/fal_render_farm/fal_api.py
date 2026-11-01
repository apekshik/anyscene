"""fal over plain HTTPS (urllib only, nothing Blender doesn't ship): the queue API and CDN storage uploads.

Queue:   POST https://queue.fal.run/<app>  -> {request_id, status_url, response_url, cancel_url}
         GET  status_url                  -> {status: IN_QUEUE | IN_PROGRESS | COMPLETED, queue_position?}
         GET  response_url                -> the app's result (or an HTTP error with the app's exception)
         PUT  cancel_url
Storage: the same CDN v3 flow fal_client uses: a short-lived upload token from rest.fal.ai, then a single POST
         (small files) or a multipart upload (big ones) to the token's base URL. Returns a public access URL.

The key is only ever put in an Authorization header; it never appears in an error message or a log line.
"""

import json
import os
import time
import urllib.error
import urllib.request

QUEUE_URL = "https://queue.fal.run"
REST_URL = "https://rest.fal.ai"
USER_AGENT = "fal-render-farm-blender/1.0"
MULTIPART_THRESHOLD = 90 * 1024 * 1024
PART_SIZE = 10 * 1024 * 1024
TRANSIENT = {408, 409, 425, 429, 500, 502, 503, 504}


class FalError(RuntimeError):
    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


def _scrub(text, key):
    text = text or ""
    if key:
        text = text.replace(key, "[key]")
    return text


def _request(method, url, *, key=None, auth=None, body=None, headers=None, timeout=60, retries=3, raw=False):
    """One HTTP call with retries on transient failures. `auth` is a full Authorization header value."""
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if key:
        hdrs["Authorization"] = f"Key {key}"
    if auth:
        hdrs["Authorization"] = auth
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=body, method=method, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                if raw:
                    return data, dict(r.headers)
                return json.loads(data) if data else {}
        except urllib.error.HTTPError as e:
            detail = _scrub(e.read().decode("utf-8", "replace"), key)
            last = FalError(f"HTTP {e.code} from {method} {url.split('?')[0]}: {detail[:2000]}", e.code)
            if e.code not in TRANSIENT:
                raise last from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last = FalError(f"{method} {url.split('?')[0]} failed: {_scrub(str(e), key)}")
        time.sleep(1.5 * (attempt + 1))
    raise last


# -- storage ----------------------------------------------------------------------------------------------------

def _cdn_token(key):
    data = _request("POST", f"{REST_URL}/storage/auth/token?storage_type=fal-cdn-v3", key=key, body={})
    return f"{data['token_type']} {data['token']}", data["base_url"]


def upload_file(key, path, content_type="application/zip", expires_s=7 * 86400, progress=None):
    """Upload a local file to fal storage and return its public URL. progress(bytes_sent, total) is optional."""
    size = os.path.getsize(path)
    name = os.path.basename(path)
    auth, base = _cdn_token(key)
    lifecycle = json.dumps({"expiration_duration_seconds": int(expires_s)})
    if size <= MULTIPART_THRESHOLD:
        with open(path, "rb") as f:
            data = f.read()
        res = _request("POST", f"{base}/files/upload", auth=auth, body=data, timeout=600, headers={
            "Content-Type": content_type, "X-Fal-File-Name": name, "X-Fal-Object-Lifecycle": lifecycle})
        if progress:
            progress(size, size)
        return res["access_url"]

    res = _request("POST", f"{base}/files/upload/multipart", auth=auth, headers={
        "Content-Type": content_type, "X-Fal-File-Name": name, "X-Fal-Object-Lifecycle": lifecycle})
    access, upload_id = res["access_url"], res["uploadId"]
    parts, sent = [], 0
    with open(path, "rb") as f:
        n = 1
        while chunk := f.read(PART_SIZE):
            _, hdrs = _request("PUT", f"{access}/multipart/{upload_id}/{n}", auth=auth, body=chunk, timeout=600,
                               raw=True, headers={"Content-Type": content_type, "Accept-Encoding": "identity"})
            etag = {k.lower(): v for k, v in hdrs.items()}.get("etag")
            parts.append({"partNumber": n, "etag": etag})
            sent += len(chunk)
            if progress:
                progress(sent, size)
            n += 1
    _request("POST", f"{access}/multipart/{upload_id}/complete", auth=auth, body={"parts": parts})
    return access


def download(url, dest, timeout=600):
    """Stream a URL to a file (written to dest.part, then renamed)."""
    tmp = dest + ".part"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
                while chunk := r.read(4 << 20):
                    f.write(chunk)
            os.replace(tmp, dest)
            return dest
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            err = e
            time.sleep(2 * (attempt + 1))
    raise FalError(f"download failed: {err}")


# -- queue ------------------------------------------------------------------------------------------------------

def submit(key, app, payload):
    return _request("POST", f"{QUEUE_URL}/{app.strip('/')}", key=key, body=payload)


def status(key, handle):
    return _request("GET", handle["status_url"], key=key)


def result(key, handle):
    return _request("GET", handle["response_url"], key=key, timeout=120)


def cancel(key, handle):
    try:
        _request("PUT", handle["cancel_url"], key=key, retries=1, timeout=15)
    except FalError:
        pass  # already finished, or never started: nothing to cancel


def check_key(key, app):
    """Cheap auth probe: a status read of a request id that doesn't exist. 401/403 means a bad key."""
    try:
        _request("GET", f"{QUEUE_URL}/{app.strip('/')}/requests/00000000-0000-0000-0000-000000000000/status",
                 key=key, retries=1, timeout=15)
    except FalError as e:
        if e.status in (401, 403):
            return False, "fal rejected the key (HTTP %s)" % e.status
        return True, "key accepted"
    return True, "key accepted"
