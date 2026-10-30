"""Live LAN gallery of both scenes: stills, process passes and cinematic shots, rebuilt on every page load.
   python pipeline/lan_gallery.py [port]   ->  http://<lan-ip>:<port>/
Serves the project folder read-only (GET only); new renders show up on refresh."""
import html, os, socket, sys, time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
SCENES = ["repair", "ramen"]


def files(rel, exts, recursive=False, skip=()):
    base = os.path.join(ROOT, rel)
    out = []
    if not os.path.isdir(base):
        return out
    walker = os.walk(base) if recursive else [(base, [], os.listdir(base))]
    for d, _, names in walker:
        if any(s in d.replace("\\", "/") for s in skip):
            continue
        for n in names:
            if n.lower().endswith(exts):
                p = os.path.join(d, n)
                out.append((os.path.relpath(p, ROOT).replace("\\", "/"), os.path.getmtime(p)))
    return sorted(out, key=lambda x: x[0])


def ago(t):
    m = int((time.time() - t) // 60)
    return f"{m} min ago" if m < 120 else time.strftime("%b %d %H:%M", time.localtime(t))


def tile(rel, t, kind):
    url = "/" + quote(rel)
    name = html.escape(rel.split("/")[-1])
    media = (f'<video src="{url}" controls muted loop playsinline preload="metadata"></video>' if kind == "v"
             else f'<a href="{url}" target="_blank"><img src="{url}" loading="lazy"></a>')
    return f'<figure>{media}<figcaption>{name}<span>{ago(t)}</span></figcaption></figure>'


def section(title, items, kind, cls=""):
    if not items:
        return ""
    return f'<h3>{title} <small>{len(items)}</small></h3><div class="grid {cls}">' + "".join(tile(r, t, kind) for r, t in items) + "</div>"


def page():
    body = ""
    for s in SCENES:
        out = f"scenes/{s}/out"
        shots = [f for f in files(f"{out}/shots", (".mp4",), True) if "/frames/" not in f[0]]
        graded = [f for f in shots if "graded" in f[0]]
        shots = graded or shots
        heroes = [f for f in files(out, (".png",)) if f[0].split("/")[-1].startswith("hero")]
        process = files(out, (".png",)) if s == "repair" else files(f"{out}/process", (".png",))
        process = [f for f in process if not f[0].split("/")[-1].startswith("hero")]
        clips = files(out, (".mp4",))
        body += f'<section><h2>{s.title()} shop</h2>'
        body += section("Cinematic shots", sorted(shots, key=lambda x: -x[1]), "v", "big")
        body += section("Hero stills", sorted(heroes, key=lambda x: -x[1]), "i", "big")
        body += section("Clips", clips, "v")
        body += section("Process", process, "i")
        body += "</section>"
    return f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Night Shops — live</title><style>
body{{margin:0;background:#0f0e0d;color:#ece8df;font:14px/1.5 system-ui,sans-serif;padding:24px max(16px,3vw) 60px}}
h1{{margin:0 0 4px;font-size:28px}}h2{{font-size:24px;margin:40px 0 0;border-top:1px solid #2a2724;padding-top:24px}}
h3{{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#9a9385;margin:24px 0 10px}}small{{color:#ff5a3c}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}}.big{{grid-template-columns:repeat(auto-fill,minmax(560px,1fr))}}
@media(max-width:640px){{.big{{grid-template-columns:1fr}}}}
figure{{margin:0;min-width:0}}img,video{{width:100%;display:block;background:#000;border-radius:3px}}
figcaption{{font:12px ui-monospace,monospace;color:#9a9385;padding-top:6px;display:flex;justify-content:space-between;gap:8px;word-break:break-all}}
p{{color:#9a9385;margin:0}}</style>
<h1>Night Shops — live renders</h1><p>Rebuilt on each refresh · newest first · {time.strftime('%H:%M:%S')}</p>{body}"""


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            b = page().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        rng = self.headers.get("Range")
        path = self.translate_path(self.path)
        if not rng or not os.path.isfile(path):
            return super().do_GET()
        # Byte ranges, so video seeks and Safari/iOS playback work.
        size = os.path.getsize(path)
        a, _, b = rng.replace("bytes=", "").partition("-")
        start = int(a) if a else max(0, size - int(b))
        end = min(int(b), size - 1) if a and b else size - 1
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            try:
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (ConnectionResetError, BrokenPipeError):
                pass

    def list_directory(self, path):
        self.send_error(404)

    def log_message(self, *a):
        pass


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    finally:
        s.close()


if __name__ == "__main__":
    print(f"serving http://{lan_ip()}:{PORT}/", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
