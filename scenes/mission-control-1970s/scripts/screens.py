"""Screen content textures: green-phosphor CRT pages and the three wall-display panels, all invented text.

blender -b --factory-startup --python scenes/mission-control-1970s/scripts/screens.py -- [name ...]
Each screen is a little 2D scene (real font text objects, polyline curves, the generated world map for the big display)
rendered with Eevee through an ortho camera, then given a phosphor bloom in numpy. Output:
refs/mission-control-1970s/tex/screens/<name>.png. Coordinates below are in screen units: x 0..aspect, y 0..1 (top = 1).
"""
import math
import os
import random
import sys

import bpy
import numpy as np

ROOT = os.environ.get("ANYSCENE_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUT = os.path.join(ROOT, "refs", "mission-control-1970s", "tex", "screens")
MAP = os.path.join(ROOT, "refs", "mission-control-1970s", "tex", "world_map_0.png")
MONO = "C:/Windows/Fonts/lucon.ttf"
BOLD = "C:/Windows/Fonts/arialbd.ttf"
GREEN = (0.35, 1.0, 0.45)
DIM = (0.1, 0.38, 0.14)
AMBER = (1.0, 0.62, 0.12)
CYAN = (0.4, 1.0, 0.85)
WHITE = (0.85, 1.0, 0.9)
only = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
os.makedirs(OUT, exist_ok=True)


class Page:
    def __init__(self, name, px=(1024, 768), tint=GREEN):
        self.name, self.px, self.tint = name, px, tint
        self.aspect = px[0] / px[1]
        bpy.ops.wm.read_factory_settings(use_empty=True)
        sc = self.sc = bpy.context.scene
        sc.render.engine = "BLENDER_EEVEE"
        sc.render.resolution_x, sc.render.resolution_y = px
        sc.render.resolution_percentage = 100
        sc.view_settings.view_transform = "Standard"
        sc.eevee.taa_render_samples = 16
        w = bpy.data.worlds.new("w")
        w.use_nodes = True
        w.node_tree.nodes["Background"].inputs["Color"].default_value = (0, 0, 0, 1)
        sc.world = w
        cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = self.aspect
        cam.location = (self.aspect / 2, 0.5, 5)
        sc.collection.objects.link(cam)
        sc.camera = cam
        self.mats = {}
        self.fonts = {}

    def mat(self, col, k=1.0):
        key = (tuple(round(c, 3) for c in col), k)
        if key not in self.mats:
            m = bpy.data.materials.new("e")
            nt = m.node_tree
            nt.nodes.clear()
            em = nt.nodes.new("ShaderNodeEmission")
            em.inputs["Color"].default_value = (*col, 1)
            em.inputs["Strength"].default_value = k
            o = nt.nodes.new("ShaderNodeOutputMaterial")
            nt.links.new(em.outputs[0], o.inputs[0])
            self.mats[key] = m
        return self.mats[key]

    def text(self, s, x, y, size=0.04, col=None, font=MONO, align="LEFT", k=1.0):
        if font not in self.fonts:
            self.fonts[font] = bpy.data.fonts.load(font)
        cu = bpy.data.curves.new("t", "FONT")
        cu.body = s
        cu.font = self.fonts[font]
        cu.size = size
        cu.align_x = align
        cu.align_y = "TOP"
        cu.materials.append(self.mat(col or self.tint, k))
        ob = bpy.data.objects.new("t", cu)
        ob.location = (x, y, 0)
        self.sc.collection.objects.link(ob)
        return ob

    def lines(self, rows, x, y, size=0.04, lead=1.35, col=None, k=1.0):
        for i, r in enumerate(rows):
            if r:
                self.text(r, x, y - i * size * lead, size, col, k=k)

    def poly(self, pts, width=0.003, col=None, closed=False, k=1.0):
        cu = bpy.data.curves.new("p", "CURVE")
        cu.dimensions = "3D"
        cu.extrude = 0
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for p, (px, py) in zip(sp.points, pts):
            p.co = (px, py, 0, 1)
        sp.use_cyclic_u = closed
        cu.bevel_mode = "ROUND"
        cu.dimensions = "3D"
        cu.bevel_depth = width / 2
        cu.materials.append(self.mat(col or self.tint, k))
        ob = bpy.data.objects.new("p", cu)
        self.sc.collection.objects.link(ob)
        return ob

    def rect(self, x0, y0, x1, y1, **kw):
        return self.poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], closed=True, **kw)

    def fill(self, x0, y0, x1, y1, col, k=1.0):
        me = bpy.data.meshes.new("f")
        me.from_pydata([(x0, y0, -0.01), (x1, y0, -0.01), (x1, y1, -0.01), (x0, y1, -0.01)], [], [(0, 1, 2, 3)])
        me.materials.append(self.mat(col, k))
        ob = bpy.data.objects.new("f", me)
        self.sc.collection.objects.link(ob)

    def circle(self, cx, cy, r, n=64, **kw):
        return self.poly([(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)], closed=True, **kw)

    def image(self, path, x0, y0, x1, y1, k=1.0):
        me = bpy.data.meshes.new("img")
        me.from_pydata([(x0, y0, -0.02), (x1, y0, -0.02), (x1, y1, -0.02), (x0, y1, -0.02)], [], [(0, 1, 2, 3)])
        uv = me.uv_layers.new()
        for i, l in enumerate(me.loops):
            uv.data[i].uv = [(0, 0), (1, 0), (1, 1), (0, 1)][l.vertex_index]
        m = bpy.data.materials.new("img")
        nt = m.node_tree
        nt.nodes.clear()
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(path)
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Strength"].default_value = k
        o = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(t.outputs["Color"], em.inputs["Color"])
        nt.links.new(em.outputs[0], o.inputs[0])
        me.materials.append(m)
        ob = bpy.data.objects.new("img", me)
        self.sc.collection.objects.link(ob)

    def render(self, bloom=0.55, raster=True):
        path = os.path.join(OUT, f"{self.name}.png")
        self.sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(path)
        w, h = img.size
        a = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(a)
        a = a.reshape(h, w, 4)[..., :3]
        glow = a.copy()
        for r in (3, 7, 15):  # three box-blur passes per radius ~ a soft phosphor halo
            g = a.copy()
            for _ in range(3):
                g = box(g, r)
            glow = glow + g * (bloom / 3)
        out = glow
        if raster:  # faint raster lines baked in (the scene shader adds the real scanlines)
            rows = (np.arange(h) % 3 == 0)[:, None, None]
            out = np.where(rows, out * 0.82, out)
        out = np.clip(out, 0, 1)
        rgba = np.concatenate([out, np.ones((h, w, 1), np.float32)], axis=2)
        img.pixels.foreach_set(rgba.ravel())
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
        print("SCREEN", self.name, w, h, flush=True)


def box(a, r):
    c = np.cumsum(np.pad(a, ((r + 1, r), (0, 0), (0, 0)), mode="edge"), axis=0)
    a = (c[2 * r + 1:] - c[:-2 * r - 1]) / (2 * r + 1)
    c = np.cumsum(np.pad(a, ((0, 0), (r + 1, r), (0, 0)), mode="edge"), axis=1)
    return (c[:, 2 * r + 1:] - c[:, :-2 * r - 1]) / (2 * r + 1)


R = random.Random(7)


def num(lo, hi, d=2):
    return f"{R.uniform(lo, hi):.{d}f}"


def header(p, title, sub="PERSEUS 7   REV 112"):
    p.text(title, 0.05, 0.96, 0.045)
    p.text(sub, p.aspect - 0.05, 0.96, 0.045, align="RIGHT")
    p.text(f"GMT 303:03:{R.randint(36, 44):02d}:{R.randint(0, 59):02d}", 0.05, 0.9, 0.034, DIM)
    p.text(f"MET 007:14:{R.randint(10, 50):02d}:{R.randint(0, 59):02d}", p.aspect - 0.05, 0.9, 0.034, DIM, align="RIGHT")
    p.poly([(0.05, 0.85), (p.aspect - 0.05, 0.85)], 0.003, DIM)


def crt_telemetry(name="crt_telemetry", tint=GREEN):
    p = Page(name, tint=tint)
    header(p, "TLM  ENVIRONMENTAL")
    rows = [("CABIN PRESS", num(4.9, 5.1), "PSIA"), ("CABIN TEMP", num(68, 74, 1), "DEG F"), ("O2 FLOW", num(0.2, 0.4), "LB/HR"),
            ("CO2 PART PR", num(1.2, 2.4, 1), "MMHG"), ("SUIT LOOP DP", num(0.2, 0.5), "IN H2O"), ("H2O ACCUM", num(10, 40, 0), "PCT"),
            ("GLYCOL IN", num(44, 49, 1), "DEG F"), ("GLYCOL OUT", num(52, 58, 1), "DEG F"), ("RAD OUT TEMP", num(30, 45, 1), "DEG F"),
            ("SURGE TK PR", num(880, 900, 0), "PSIA"), ("O2 TK 1 QTY", num(71, 74, 1), "PCT"), ("O2 TK 2 QTY", num(70, 73, 1), "PCT")]
    for i, (k, v, u) in enumerate(rows):
        y = 0.8 - i * 0.058
        p.text(f"{i + 101:03d}", 0.05, y, 0.038, DIM)
        p.text(k, 0.17, y, 0.038)
        p.text(v.rjust(7), 0.72, y, 0.038, WHITE if i == 3 else None)
        p.text(u, 0.98, y, 0.038, DIM)
        p.text("OK" if i != 3 else "WTCH", 1.2, y, 0.038, None if i != 3 else WHITE)
    p.text("> _", 0.05, 0.07, 0.04)
    p.render()


def crt_trajectory(name="crt_trajectory", tint=GREEN):
    p = Page(name, tint=tint)
    header(p, "TRAJ  ALT / RANGE")
    x0, x1, y0, y1 = 0.16, 1.25, 0.14, 0.78
    p.rect(x0, y0, x1, y1, width=0.003, col=DIM)
    for i in range(1, 6):
        p.poly([(x0 + (x1 - x0) * i / 6, y0), (x0 + (x1 - x0) * i / 6, y1)], 0.0015, DIM)
        p.poly([(x0, y0 + (y1 - y0) * i / 6), (x1, y0 + (y1 - y0) * i / 6)], 0.0015, DIM)
    pts = [(x0 + (x1 - x0) * t, y0 + (y1 - y0) * (0.5 + 0.38 * math.sin(2 * math.pi * (t * 1.1 + 0.1)) * (1 - 0.15 * t))) for t in np.linspace(0, 1, 120)]
    p.poly(pts[:84], 0.006)
    for x, y in pts[84::4]:
        p.poly([(x - 0.002, y), (x + 0.002, y)], 0.005, DIM)
    p.text("+", pts[83][0] - 0.012, pts[83][1] + 0.022, 0.05, WHITE)
    for i, v in enumerate(("160", "140", "120", "100")):
        p.text(v, 0.05, y1 - i * (y1 - y0) / 3 + 0.015, 0.03, DIM)
    p.text("NM", 0.05, y0 - 0.02, 0.03, DIM)
    p.text(f"HA {num(158, 162, 1)}  HP {num(141, 145, 1)}  INC {num(32, 33, 2)}", 0.16, 0.08, 0.036)
    p.render()


def crt_events(name="crt_events", tint=GREEN):
    p = Page(name, tint=tint)
    header(p, "EVENT LOG")
    evs = ["AOS KESTREL", "TLM LOCK KESTREL", "CMD UPLINK 4471 VERIFIED", "LOS KESTREL", "AOS OSPREY", "S-BAND HI GAIN",
           "PTC ROLL INITIATED", "LOS OSPREY", "AOS HARRIER", "STATE VECTOR UPDATE", "FUEL CELL 2 PURGE", "LOS HARRIER",
           "AOS MERLIN", "CREW STATUS NOMINAL"]
    t = 3 * 3600 + 2 * 60
    for i, e in enumerate(evs):
        t += R.randint(90, 260)
        y = 0.8 - i * 0.052
        p.text(f"{t // 3600:02d}:{t // 60 % 60:02d}:{t % 60:02d}", 0.05, y, 0.036, DIM)
        p.text(e, 0.36, y, 0.036, WHITE if i == len(evs) - 1 else None)
    p.text("\u2588", 0.05, 0.07, 0.04)
    p.render()


def crt_guidance(name="crt_guidance", tint=GREEN):
    p = Page(name, tint=tint)
    header(p, "GNC  STATE VECTOR")
    p.lines(["        X            Y            Z",
             f"R  {num(-4e6, 4e6, 0):>11} {num(-4e6, 4e6, 0):>12} {num(-4e6, 4e6, 0):>12}",
             f"V  {num(-7e3, 7e3, 1):>11} {num(-7e3, 7e3, 1):>12} {num(-7e3, 7e3, 1):>12}", "",
             "ATTITUDE      ROLL    PITCH     YAW",
             f"  CMD       {num(0, 360, 1):>7} {num(0, 360, 1):>8} {num(0, 360, 1):>8}",
             f"  ACT       {num(0, 360, 1):>7} {num(0, 360, 1):>8} {num(0, 360, 1):>8}",
             f"  ERR       {num(-1, 1, 2):>7} {num(-1, 1, 2):>8} {num(-1, 1, 2):>8}", "",
             f"GDC ALIGN   {num(0, 1, 3)}     IMU TEMP {num(125, 127, 1)}",
             f"PIPA BIAS   {num(-0.01, 0.01, 4)}   DRIFT  {num(-0.02, 0.02, 4)}", "",
             "NEXT BURN   TIG 008:02:14:30  DV 12.4"], 0.05, 0.8, 0.036)
    p.render()


def crt_power(name="crt_power", tint=GREEN):
    p = Page(name, tint=tint)
    header(p, "EPS  BUS STATUS")
    labels = ["MAIN A", "MAIN B", "BAT C", "FC 1", "FC 2", "FC 3", "AC 1", "AC 2"]
    for i, l in enumerate(labels):
        y = 0.78 - i * 0.082
        v = R.uniform(0.55, 0.92)
        p.text(l, 0.05, y, 0.036)
        p.rect(0.33, y - 0.045, 1.05, y - 0.005, width=0.002, col=DIM)
        p.fill(0.335, y - 0.04, 0.335 + 0.71 * v, y - 0.01, p.tint, 0.85 if i != 4 else 1.0)
        p.text(f"{26 + v * 6:.1f} V", 1.08, y, 0.036, WHITE if i == 4 else None)
    p.render()


def crt_comms(name="crt_comms", tint=GREEN):
    p = Page(name, tint=tint)
    header(p, "NETWORK  STATIONS")
    p.text("STA       STATUS   AOS       LOS       EL", 0.05, 0.8, 0.036, DIM)
    rows = [("MERLIN", "TRACK", "03:40:42", "03:48:57", "55.9"), ("OSPREY", "READY", "04:01:52", "04:10:31", "41.0"),
            ("HARRIER", "STBY", "04:39:05", "04:46:12", "22.7"), ("KESTREL", "READY", "05:12:44", "05:21:30", "68.3"),
            ("FALCON", "MAINT", "--:--:--", "--:--:--", " --"), ("CONDOR", "READY", "05:58:10", "06:04:02", "17.2")]
    for i, r in enumerate(rows):
        p.text(f"{r[0]:<9} {r[1]:<8} {r[2]}  {r[3]}  {r[4]}", 0.05, 0.72 - i * 0.07, 0.036, WHITE if i == 0 else None)
    p.text("UPLINK  2287.5 MHZ   DNLINK  2106.4 MHZ", 0.05, 0.24, 0.034, DIM)
    p.text("VOICE LOOP  FD  NET 1  NET 2  CREW", 0.05, 0.17, 0.034, DIM)
    p.render()


def crt_orbit(name="crt_orbit", tint=GREEN):
    p = Page(name, tint=tint)
    header(p, "GROUND TRACK  PREDICT")
    x0, x1, y0, y1 = 0.06, 1.27, 0.08, 0.8
    p.rect(x0, y0, x1, y1, width=0.003, col=DIM)
    for i in range(1, 12):
        p.poly([(x0 + (x1 - x0) * i / 12, y0), (x0 + (x1 - x0) * i / 12, y1)], 0.0012, DIM)
    for i in range(1, 6):
        p.poly([(x0, y0 + (y1 - y0) * i / 6), (x1, y0 + (y1 - y0) * i / 6)], 0.0012, DIM)
    for k, ph in enumerate((0.0, 0.26, 0.52)):
        pts = [(x0 + (x1 - x0) * t, (y0 + y1) / 2 + (y1 - y0) * 0.36 * math.sin(2 * math.pi * (t - ph))) for t in np.linspace(0, 1, 160)]
        p.poly(pts, 0.005 if k == 1 else 0.003, None if k == 1 else DIM)
    p.circle(x0 + (x1 - x0) * 0.47, (y0 + y1) / 2 + (y1 - y0) * 0.36 * math.sin(2 * math.pi * (0.47 - 0.26)), 0.018, col=WHITE, width=0.005)
    p.render()


def crt_amber(name="crt_amber_status"):
    p = Page(name, tint=AMBER)
    p.text("PROP  RCS QUADS", 0.05, 0.96, 0.045)
    p.text("PERSEUS 7", p.aspect - 0.05, 0.96, 0.045, align="RIGHT")
    p.poly([(0.05, 0.88), (p.aspect - 0.05, 0.88)], 0.003, (0.45, 0.25, 0.04))
    for q, (cx, cy) in enumerate(((0.35, 0.62), (0.98, 0.62), (0.35, 0.27), (0.98, 0.27))):
        p.rect(cx - 0.27, cy - 0.15, cx + 0.27, cy + 0.17, width=0.003)
        p.text(f"QUAD {'ABCD'[q]}", cx - 0.24, cy + 0.14, 0.036)
        p.lines([f"HE  {num(4000, 4200, 0)}", f"PRP {num(150, 180, 0)}  PCT {num(60, 90, 0)}", f"PKG T {num(120, 140, 0)} F"],
                cx - 0.24, cy + 0.07, 0.034)
    p.render()


def wall_left():
    p = Page("wall_left", px=(1024, 1024), tint=GREEN)
    p.text("PERSEUS 7", 0.06, 0.95, 0.075, WHITE, BOLD)
    p.text("ORBITAL ELEMENTS", 0.06, 0.85, 0.045, DIM)
    rows = [("REV", "112"), ("APOGEE", "312 KM"), ("PERIGEE", "298 KM"), ("INCLINATION", "51.6\u00b0"), ("PERIOD", "90.2 MIN"),
            ("VELOCITY", "7.72 KM/S"), ("BETA ANGLE", "-14.8\u00b0"), ("NEXT AOS", "04:01:52"), ("NEXT LOS", "04:10:31")]
    for i, (k, v) in enumerate(rows):
        y = 0.75 - i * 0.075
        p.text(k, 0.06, y, 0.048)
        p.text(v, 0.94, y, 0.048, WHITE, align="RIGHT")
    p.poly([(0.06, 0.07), (0.94, 0.07)], 0.004, DIM)
    p.render(bloom=0.7, raster=False)


def wall_right():
    p = Page("wall_right", px=(1024, 1024), tint=GREEN)
    p.text("AOS   03:40:42", 0.06, 0.95, 0.06, WHITE)
    p.text("LOS   03:48:57", 0.06, 0.87, 0.06, WHITE)
    p.text("MAX EL  55.9\u00b0", 0.06, 0.79, 0.06)
    p.poly([(0.06, 0.71), (0.94, 0.71)], 0.004, DIM)
    p.text("NETWORK", 0.06, 0.66, 0.045, DIM)
    for i, (s, st) in enumerate((("KESTREL", "ONLINE"), ("OSPREY", "ONLINE"), ("HARRIER", "STANDBY"), ("MERLIN", "TRACK"),
                                 ("FALCON", "MAINT"), ("CONDOR", "ONLINE"))):
        y = 0.58 - i * 0.075
        p.text(s, 0.06, y, 0.05)
        p.text(st, 0.94, y, 0.05, AMBER if st in ("STANDBY", "MAINT") else WHITE, align="RIGHT")
    p.render(bloom=0.7, raster=False)


def wall_map():
    p = Page("wall_map", px=(2048, 1024), tint=CYAN)
    a = p.aspect
    p.image(MAP, 0.0, 0.0, a, 1.0, k=0.75)
    # three revolutions of ground track (sinusoid drifting west), the current one bright
    for k, ph in enumerate((0.0, 0.25, 0.5)):
        pts = [(a * t, 0.5 + 0.31 * math.sin(2 * math.pi * (t - ph))) for t in np.linspace(0, 1, 300)]
        p.poly(pts, 0.006 if k == 1 else 0.0035, WHITE if k == 1 else (0.25, 0.75, 0.6), k=1.0)
    t = 0.8
    x, y = a * t, 0.5 + 0.31 * math.sin(2 * math.pi * (t - 0.25))
    p.circle(x, y, 0.016, col=WHITE, width=0.007, k=1.6)
    p.circle(x, y, 0.08, col=(0.4, 1, 0.8), width=0.003, n=96)  # acquisition circle
    for (sx, sy, n) in ((0.32, 0.67, "KESTREL"), (0.62, 0.35, "OSPREY"), (1.05, 0.72, "HARRIER"), (1.62, 0.3, "MERLIN"), (1.38, 0.62, "CONDOR")):
        p.circle(sx, sy, 0.1, col=(0.2, 0.55, 0.45), width=0.0025, n=96)
        p.poly([(sx - 0.01, sy), (sx + 0.01, sy)], 0.004, AMBER)
        p.poly([(sx, sy - 0.01), (sx, sy + 0.01)], 0.004, AMBER)
        p.text(n, sx + 0.02, sy - 0.02, 0.03, AMBER)
    p.text("REV 112", 0.03, 0.06, 0.03, WHITE)
    p.render(bloom=0.6, raster=False)


ALL = {"crt_telemetry": crt_telemetry, "crt_trajectory": crt_trajectory, "crt_events": crt_events, "crt_guidance": crt_guidance,
       "crt_power": crt_power, "crt_comms": crt_comms, "crt_orbit": crt_orbit, "crt_amber_status": crt_amber,
       "wall_left": wall_left, "wall_right": wall_right, "wall_map": wall_map}
for k, fn in ALL.items():
    if not only or k in only:
        fn()
