"""Effects classifier for the AnyScene -> Unreal exporter (NIAGARA.md §4): turns volume-shader effects and particle
systems into `scene.json["fx"]` entries (schema in NIAGARA.md §4.2) with a technique, an AnySceneFX template and its
User parameters filled in, so build_level.py only places and sets them.

Used two ways:
  * from export_blend.py:  `import fx_export; fx = fx_export.classify(sc, frame, emitters, volumes)`
  * standalone (no mesh bakes; patches an existing export):
      blender -b <copy>.blend --python unreal_fx/fx_export.py -- --scene <export>/scene.json --out <dir>/scene.json [--frame 60]
    writes the input scene.json + "fx" (and marks the volumes an fx entry claims) to --out.

Detection is evidence-based (material node tree, drivers, particle settings, names as a tie-breaker). Parameters
come from measurements: procedural volumes are baked on horizontal slices (density / emission per texel) to get
the plume's base, lean, spread and reach; driver expressions on mapping nodes give the scroll (rise) speed; particle
settings give rate, speed, size and lifetime; the ground under a drip line comes from a ray cast.
"""
import json
import math
import os
import re
import sys
import zlib

import bpy
import numpy as np
from mathutils import Vector

LM_PER_W = 683.0
TEMPLATES = "/Game/AnySceneFX/Systems/{0}.{0}"
TYPE_WORDS = {"fire": ("flame", "fire", "burner"), "steam": ("steam", "vapor", "vapour"), "smoke": ("smoke", "curl"),
              "haze": ("haze", "fog", "mist"), "rain": ("rain", "drizzle"), "drips": ("drip",), "dust": ("dust", "mote"),
              "sparks": ("spark",), "embers": ("ember",)}
PARAM_TYPES = None  # filled from templates.json when present


def log(*a):
    print("FXEXPORT", *a, flush=True)


def ue_vec(v, s=100.0):
    return [v[0] * s, -v[1] * s, v[2] * s]


def ue_dir(v, s=100.0):
    return [v[0] * s, -v[1] * s, v[2] * s]


def crc(s):
    return zlib.crc32(s.encode()) & 0x7FFFFFFF


def name_hint(name):
    n = name.lower()
    return {t for t, ws in TYPE_WORDS.items() if any(w in n for w in ws)}


# ------------------------------------------------------------------ node-tree evidence

def out_node(nt):
    outs = [n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"]
    return next((n for n in outs if n.is_active_output), outs[0] if outs else None)


def volume_material(o):
    for s in o.material_slots:
        m = s.material
        if m and m.node_tree:
            o_ = out_node(m.node_tree)
            if o_ and o_.inputs["Volume"].is_linked and not o_.inputs["Surface"].is_linked:
                return m
    return None


def principled_volume(m):
    return next((n for n in m.node_tree.nodes if n.type == "PRINCIPLED_VOLUME"), None)


def drivers(m):
    ad = m.node_tree.animation_data if m.node_tree else None
    return list(ad.drivers) if ad else []


def driver_rate(d, fps):
    """Per-second rate of a driver expression that is linear in `frame` (e.g. "-frame * 0.055")."""
    ex = d.driver.expression
    try:
        f = lambda fr: eval(ex, {"__builtins__": {}}, {"frame": fr, "sin": math.sin, "cos": math.cos})  # noqa: E731
        return (f(101.0) - f(100.0)) * fps
    except Exception:
        return None


def mapping_scroll(m, fps):
    """Pattern velocity in object space (m/s) from Mapping-node Location drivers: the pattern moves by -dL/scale."""
    v = [0.0, 0.0, 0.0]
    found = False
    for d in drivers(m):
        mt = re.match(r'nodes\["([^"]+)"\]\.inputs\[(\d+)\]\.default_value', d.data_path)
        if not mt:
            continue
        nd = m.node_tree.nodes.get(mt.group(1))
        if not nd or nd.type != "MAPPING" or int(mt.group(2)) != 1:  # inputs[1] = Location
            continue
        r = driver_rate(d, fps)
        if r is None:
            continue
        sc = nd.inputs["Scale"].default_value[d.array_index] or 1.0
        v[d.array_index] = -r / sc
        found = True
    return v if found else None


def noise_evolution(m, fps):
    """Fastest 4D-noise W rate (1/s): how quickly the pattern re-forms (flicker / boil)."""
    rates = []
    for d in drivers(m):
        mt = re.match(r'nodes\["([^"]+)"\]\.inputs\[\d+\]\.default_value', d.data_path)
        if mt and m.node_tree.nodes.get(mt.group(1)) and m.node_tree.nodes[mt.group(1)].type == "TEX_NOISE":
            r = driver_rate(d, fps)
            if r is not None:
                rates.append(abs(r))
    return max(rates) if rates else 0.0


def emission_colour(m, levels_z, weights):
    """Emission-weighted mean colour. Handles a ColorRamp on Emission Color (evaluated at each level's generated z
    when its factor comes from a generated/Z chain; otherwise at 0.6)."""
    pv = principled_volume(m)
    s = pv.inputs["Emission Color"]
    if not s.is_linked:
        return list(s.default_value)[:3]
    n0 = s.links[0].from_node
    if n0.type != "VALTORGB":
        return [1.0, 0.5, 0.1]
    fac = n0.inputs[0]
    by_z = fac.is_linked and fac.links[0].from_node.type == "SEPXYZ" and fac.links[0].from_socket.name == "Z"
    if not by_z:
        return list(n0.color_ramp.evaluate(0.6))[:3]
    acc, w = np.zeros(3), 0.0
    for z, wt in zip(levels_z, weights):
        acc += np.array(n0.color_ramp.evaluate(float(z))[:3]) * wt
        w += wt
    return list(acc / max(w, 1e-9))


# ------------------------------------------------------------------ slice sampling (Cycles EMIT bakes)

_BS = None


def bake_scene(frame):
    global _BS
    if _BS is None:
        bs = bpy.data.scenes.new("__fxbake")
        bs.render.engine = "CYCLES"
        bs.cycles.device = "CPU"
        bs.cycles.samples = 1
        bs.cycles.use_denoising = False
        bs.render.bake.target = "IMAGE_TEXTURES"
        bs.frame_current = frame
        _BS = bs
    return _BS


def sample_slices(o, m, frame, n=32, levels=12):
    """Bake Density and Emission Strength of a volume material on `levels` horizontal slices through the object's box
    (sharing its object and texture space). Returns lo, hi (object space) and arrays [levels, n, n] per channel."""
    me0 = o.data
    xs = [v.co for v in me0.vertices]
    lo = Vector([min(c[i] for c in xs) for i in range(3)])
    hi = Vector([max(c[i] for c in xs) for i in range(3)])
    pv = principled_volume(m)
    zs = [lo.z + (k + 0.5) / levels * (hi.z - lo.z) for k in range(levels)]
    out = {"density": np.zeros((levels, n, n)), "emission": np.zeros((levels, n, n))}
    bs = bake_scene(frame)
    for li, z in enumerate(zs):
        me = bpy.data.meshes.new("__fxslice")
        me.from_pydata([(lo.x, lo.y, z), (hi.x, lo.y, z), (hi.x, hi.y, z), (lo.x, hi.y, z)], [], [(0, 1, 2, 3)])
        uv = me.uv_layers.new(name="UVMap")
        for i, c in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
            uv.data[i].uv = c
        me.use_auto_texspace = False
        me.texspace_location = me0.texspace_location
        me.texspace_size = me0.texspace_size
        sl = bpy.data.objects.new("__fxslice", me)
        bs.collection.objects.link(sl)
        sl.matrix_world = o.matrix_world.copy()
        mc = m.copy()
        me.materials.append(mc)
        nt = mc.node_tree
        pvc = next(nd for nd in nt.nodes if nd.type == "PRINCIPLED_VOLUME")
        on = out_node(nt)
        for l in list(on.inputs["Volume"].links):
            nt.links.remove(l)
        for key, sock in (("density", "Density"), ("emission", "Emission Strength")):
            s = pvc.inputs[sock]
            if not s.is_linked and s.default_value == 0:
                continue
            em = nt.nodes.new("ShaderNodeEmission")
            if s.is_linked:
                nt.links.new(s.links[0].from_socket, em.inputs["Color"])
            else:
                em.inputs["Color"].default_value = (s.default_value,) * 3 + (1,)
            nt.links.new(em.outputs[0], on.inputs["Surface"])
            img = bpy.data.images.new("__fxvol", n, n, alpha=False, float_buffer=True)
            img.colorspace_settings.name = "Non-Color"
            tx = nt.nodes.new("ShaderNodeTexImage")
            tx.image = img
            nt.nodes.active = tx
            with bpy.context.temp_override(scene=bs, view_layer=bs.view_layers[0], object=sl, active_object=sl,
                                           selected_objects=[sl], selected_editable_objects=[sl]):
                bpy.ops.object.bake(type="EMIT", margin=0, use_clear=True)
            px = np.empty(n * n * 4, np.float32)
            img.pixels.foreach_get(px)
            out[key][li] = px.reshape(n, n, 4)[:, :, 0]  # [row = y, col = x]
            nt.nodes.remove(tx)
            nt.nodes.remove(em)
            bpy.data.images.remove(img)
        bpy.data.objects.remove(sl)
        bpy.data.meshes.remove(me)
        bpy.data.materials.remove(mc)
    return lo, hi, zs, out


def plume_stats(o, lo, hi, zs, field, n):
    """Per-level weighted centroid (world), radial spread (m) and peak, from a [levels, n, n] field."""
    mw = o.matrix_world
    xs = np.linspace(lo.x, hi.x, n, endpoint=False) + (hi.x - lo.x) / (2 * n)
    ys = np.linspace(lo.y, hi.y, n, endpoint=False) + (hi.y - lo.y) / (2 * n)
    X, Y = np.meshgrid(xs, ys)
    sx, sy, sz = mw.to_scale()
    rows = []
    for k, z in enumerate(zs):
        f = np.clip(field[k], 0, None)
        tot = f.sum()
        if tot <= 1e-9:
            rows.append(None)
            continue
        cx, cy = (f * X).sum() / tot, (f * Y).sum() / tot
        r = np.sqrt(((X - cx) * sx) ** 2 + ((Y - cy) * sy) ** 2)
        rows.append({"c": mw @ Vector((cx, cy, z)), "spread": float((f * r).sum() / tot), "r_peak": float(r[np.unravel_index(np.argmax(f), f.shape)]),
                     "peak": float(np.percentile(f, 98)), "mean": float(f.mean()), "sum": float(tot)})
    return rows


# ------------------------------------------------------------------ entries

def template_for(typ, default):
    """Template whose recipe lists this fx type (templates.json "fx_types"), so a recipe an agent adds for a new type
    is picked up without code changes; falls back to the built-in default."""
    for name, t in (PARAM_TYPES or {}).items():
        if typ in t.get("fx_types", []):
            return name
    return default


def base_entry(fid, typ, conf, kind, objs, mat, evidence, center_ue, extent_ue, technique, template, fps, preroll):
    template = template_for(typ, template) if template else template
    if technique == "niagara" and template is None:
        technique = "agent"  # no template for this type yet: queued for the look-match agent (FX_AGENT.md)
    return {"id": re.sub(r"[^A-Za-z0-9_]", "_", fid), "type": typ, "confidence": round(conf, 2),
            "source": {"kind": kind, "objects": objs, "material": mat, "evidence": evidence},
            "transform": {"loc": center_ue, "quat": [0, 0, 0, 1], "scale": [1, 1, 1]},
            "bounds_ue": {"center": center_ue, "extent": extent_ue},
            "technique": technique, "template": TEMPLATES.format(template) if template else None,
            "params": {}, "param_types": {}, "physical": {}, "time": {"preroll_s": preroll, "fps": fps},
            "seed": crc(fid), "notes": []}


def set_params(e, params):
    tpl = e["template"].split("/")[-1].split(".")[0] if e["template"] else None
    types = (PARAM_TYPES or {}).get(tpl, {}).get("params", {})
    for k, v in params.items():
        if types and k not in types:
            e["notes"].append(f"param {k} not on {tpl}: dropped")
            continue
        e["params"][k] = [round(x, 4) for x in v] if isinstance(v, (list, tuple)) else round(float(v), 4)
        e["param_types"][k] = types.get(k) or ("color" if k == "Color" else "vec3" if isinstance(v, (list, tuple)) else "float")


def nearest_light(sc, p_world, radius=1.0):
    """The dominant light near the effect (highest energy within radius), so fire never double-lights."""
    best = None
    for o in sc.objects:
        if o.type == "LIGHT" and not o.hide_render:
            d = (o.matrix_world.translation - p_world).length
            if d <= radius and (best is None or o.data.energy > best[0]):
                best = (o.data.energy, o.name)
    return best[1] if best else None


def flicker(sc, light_name, frame, n, fps):
    o = sc.objects.get(light_name)
    if not o or not (o.data.animation_data and o.data.animation_data.drivers):
        return None
    vals = []
    for f in range(frame, frame + n):
        sc.frame_set(f)
        vals.append(o.data.energy)
    sc.frame_set(frame)
    base = vals[0] or 1.0
    return {"target": light_name, "property": "intensity", "fps": fps, "start_frame": frame,
            "values": [round(v / base, 4) for v in vals], "note": "multiplier on the light's exported intensity"}


def classify_volume(sc, o, m, frame, fps):
    pv = principled_volume(m)
    ev, score = [], {}
    emit_linked = pv.inputs["Emission Strength"].is_linked or pv.inputs["Emission Strength"].default_value > 0
    bb = pv.inputs["Blackbody Intensity"].default_value > 0
    if emit_linked or bb:
        score["fire"] = score.get("fire", 0) + 4
        ev.append("principled volume emission")
    scroll = mapping_scroll(m, fps)
    has_noise = any(n.type == "TEX_NOISE" for n in m.node_tree.nodes)
    alb = list(pv.inputs["Color"].default_value)[:3]
    dims = o.dimensions
    if not emit_linked:
        if has_noise and scroll and scroll[2] > 0.3:
            score["steam" if min(alb) > 0.85 else "smoke"] = 4
            ev.append(f"noise scrolling up {scroll[2]:.2f} m/s, albedo {min(alb):.2f}")
        if max(dims) > 3.0 and (not scroll or abs(scroll[2]) < 0.05 * fps):
            score["haze"] = score.get("haze", 0) + 3
            ev.append(f"large box {max(dims):.1f} m")
    for t in name_hint(o.name) | name_hint(m.name):
        score[t] = score.get(t, 0) + 2
        ev.append(f"name hint {t}")
    if not score:
        return None, ev, 0.0
    ranked = sorted(score.items(), key=lambda kv: -kv[1])
    top = ranked[0]
    runner = ranked[1][1] if len(ranked) > 1 else 0
    return top[0], ev, top[1] / (top[1] + runner)


def seen_from(sc, dg, p, cams, skip):
    """True if the world point p has an unobstructed line to any camera (volume-only objects are see-through)."""
    for cpos in cams:
        d = cpos - p
        dist = d.length
        d.normalize()
        q, left = p.copy(), dist
        for _ in range(16):
            hit, loc, _n, _i, ob, _m = sc.ray_cast(dg, q, d, distance=left)
            if not hit:
                return True
            if ob is not None and (getattr(ob, "original", ob).name in skip or volume_material(getattr(ob, "original", ob))):
                step = (loc - q).length + 1e-3
                q, left = loc + d * 1e-3, left - step
                continue
            break
    return False


def visible_field(sc, o, lo, hi, zs, field, n, rel=0.02):
    """Mask each slice of `field` to the samples some scene camera can see, which is what Cycles shows: burner jets
    under a wok, flame inside a collar, a fire behind fireplace walls are hidden by opaque geometry. Samples under
    `rel` x the field's peak are dropped. Returns the masked field and the visible fraction per level."""
    cams = [c.matrix_world.translation.copy() for c in sc.objects if c.type == "CAMERA"]
    mw = o.matrix_world
    if not cams:
        return field.copy(), [1.0] * len(zs)
    dg = bpy.context.evaluated_depsgraph_get()
    xs = np.linspace(lo.x, hi.x, n, endpoint=False) + (hi.x - lo.x) / (2 * n)
    ys = np.linspace(lo.y, hi.y, n, endpoint=False) + (hi.y - lo.y) / (2 * n)
    thr = rel * float(np.clip(field, 0, None).max())
    out, frac = np.zeros_like(field), []
    for k, z in enumerate(zs):
        f = np.clip(field[k], 0, None)
        for j, i in zip(*np.nonzero(f > thr)):
            if seen_from(sc, dg, mw @ Vector((xs[i], ys[j], z)), cams, {o.name}):
                out[k, j, i] = f[j, i]
        frac.append(float(out[k].sum() / f.sum()) if f.sum() > 1e-9 else 0.0)
    return out, frac


def view_radiance(sc, o, lo, hi, zs, field, vis, n):
    """Line integral of `field` (emission per metre) along each camera's view ray through every camera-visible sample:
    the radiance Cycles shows there (a ray grazing a ring of flame crosses far more than one tongue's width).
    Returns the 90th percentile over samples and cameras, in the field's units x metres."""
    cams = [c.matrix_world.translation.copy() for c in sc.objects if c.type == "CAMERA"]
    if not cams:
        return 0.0
    mw = o.matrix_world
    inv = mw.inverted()
    levels = len(zs)
    dz = (zs[1] - zs[0]) if levels > 1 else (hi.z - lo.z)
    sx, sy, sz = mw.to_scale()
    step = 0.5 * min((hi.x - lo.x) / n, (hi.y - lo.y) / n, dz)
    step_m = step * (sx + sy + sz) / 3
    span = (hi - lo).length
    xs = np.linspace(lo.x, hi.x, n, endpoint=False) + (hi.x - lo.x) / (2 * n)
    ys = np.linspace(lo.y, hi.y, n, endpoint=False) + (hi.y - lo.y) / (2 * n)
    out = []
    for k, j, i in zip(*np.nonzero(vis > 0)):
        p = Vector((xs[i], ys[j], zs[k]))
        best = 0.0
        for c in cams:
            d = (p - inv @ c).normalized()
            ts = np.arange(-span, span, step)
            P = np.array(p)[None] + ts[:, None] * np.array(d)[None]
            ii = np.floor((P[:, 0] - lo.x) / (hi.x - lo.x) * n).astype(int)
            jj = np.floor((P[:, 1] - lo.y) / (hi.y - lo.y) * n).astype(int)
            kk = np.floor((P[:, 2] - lo.z) / (hi.z - lo.z) * levels).astype(int)
            ok = (ii >= 0) & (ii < n) & (jj >= 0) & (jj < n) & (kk >= 0) & (kk < levels)
            best = max(best, float(np.clip(field[kk[ok], jj[ok], ii[ok]], 0, None).sum() * step_m))
        out.append(best)
    return float(np.percentile(out, 90)) if out else 0.0


def visible_rz(em, R, zw):
    w = np.clip(em, 0, None)
    if w.sum() <= 0:
        return None
    rr = np.broadcast_to(R[None], w.shape).ravel()
    zz = np.broadcast_to(np.array(zw)[:, None, None], w.shape).ravel()
    ww = w.ravel()
    o = np.argsort(rr)
    c = np.cumsum(ww[o]) / ww.sum()
    return {"r": round(float((rr * ww).sum() / ww.sum()), 3), "z": round(float((zz * ww).sum() / ww.sum()), 3),
            "r10": round(float(rr[o][np.searchsorted(c, 0.1)]), 3), "r90": round(float(rr[o][np.searchsorted(c, 0.9)]), 3)}


def fire_entry(sc, o, m, frame, fps, ev, conf):
    n = 32
    lo, hi, zs, f = sample_slices(o, m, frame, n=n, levels=12)
    em_all = f["emission"]
    st_all = plume_stats(o, lo, hi, zs, em_all, n)
    pk_all = max(x["peak"] for x in st_all if x)
    # Only what a scene camera can see counts (Cycles hides the rest the same way): burner jets under a wok, flame
    # inside a collar, a fire behind fireplace walls. Measure the visible part; fall back to the upper half of the band
    # when nothing is visible (a fire inside a closed box is still worth a glow).
    em, vfrac = visible_field(sc, o, lo, hi, zs, em_all, n)
    st = plume_stats(o, lo, hi, zs, em, n)
    # A visible arc covers few texels: compare per-level maxima, not the slice-wide percentile in plume_stats.
    mx_vis = em.reshape(len(zs), -1).max(axis=1)
    occluded = bool(mx_vis.max() < 0.01 * float(em_all.max()))
    lev = [k for k in range(len(zs)) if st[k] and mx_vis[k] > 0.08 * mx_vis.max()] if not occluded else []
    if occluded:
        em, st = em_all, st_all
        lev = [k for k, r in enumerate(st) if r and r["peak"] > 0.08 * pk_all]
    mw = o.matrix_world
    zw = [(mw @ Vector((0, 0, zs[k]))).z for k in range(len(zs))]
    vis = (lev[len(lev) // 2:] if len(lev) > 3 else lev) if occluded else lev
    z0, z1 = zw[vis[0]], zw[lev[-1]]
    dz = (zw[1] - zw[0]) if len(zw) > 1 else 0.05
    # The ring is the emission-weighted radius of the visible part about the whole flame's axis (only the arc facing
    # the camera is visible, so the visible centroid itself is off-axis).
    axis = st_all[lev[0]]["c"] if st_all[lev[0]] else st[lev[0]]["c"]
    ax, ay = (mw.inverted() @ axis).xy
    sx, sy, _ = mw.to_scale()
    gx = np.linspace(lo.x, hi.x, n, endpoint=False) + (hi.x - lo.x) / (2 * n)
    gy = np.linspace(lo.y, hi.y, n, endpoint=False) + (hi.y - lo.y) / (2 * n)
    GX, GY = np.meshgrid(gx, gy)
    R = np.hypot((GX - ax) * sx, (GY - ay) * sy)
    wv = np.clip(em[vis], 0, None)
    ring = float((wv * R[None]).sum() / wv.sum()) if not occluded else float(max(st[k]["r_peak"] for k in vis))
    base = {"c": Vector((axis.x, axis.y, z0))}
    width = max(0.01, float(np.average([st_all[k]["spread"] for k in vis if st_all[k]])) * 0.5)
    E = float(np.percentile(em[lev][em[lev] > 0], 99)) if (em[lev] > 0).any() else float(np.percentile(em_all, 99))
    # Colour from the visible upper part of the flame (the blue base is the Core emitter's job).
    # The licking tips (faint, above the 8% body threshold) carry the flame colour; the blue base is the Core emitter.
    pk = max(x["peak"] for x in st_all if x)
    faint = [k for k, r in enumerate(st_all) if r and r["peak"] > 0.01 * pk]
    upper = set(faint[-3:])
    weights = [st_all[k]["sum"] if st_all[k] and k in upper else 0 for k in range(len(zs))]
    gz = [(k + 0.5) / len(zs) for k in range(len(zs))]
    # Flame body colour = the warmest colour among emitting levels (the blue base is drawn by the Core emitter).
    cands = [emission_colour(m, [gz[k]], [1.0]) for k in faint]
    col = max(cands, key=lambda c: c[0] / (c[2] + 0.05)) if cands else emission_colour(m, gz, weights)
    if max(col) < 1e-3:  # an emissive flame is never black: fall back to the whole flame's emission-weighted colour
        col = emission_colour(m, gz, [st_all[k]["sum"] if st_all[k] else 0 for k in range(len(zs))])
    mx = max(col) or 1.0
    height = max(0.03, z1 - z0 + dz)
    scroll = mapping_scroll(m, fps) or [0, 0, 1.0]
    boil = noise_evolution(m, fps)
    life = float(np.clip(height / max(scroll[2], 0.3), 0.18, 0.5))
    c = Vector((base["c"].x, base["c"].y, z0))
    e = base_entry(o.name, "fire", conf, "volume_shader", [o.name], m.name, ev, ue_vec(c),
                   [(hi.x - lo.x) * 50 * mw.to_scale()[0], (hi.y - lo.y) * 50 * mw.to_scale()[1], (height + 0.1) * 100],
                   "niagara", "NS_Fire", fps, 1.0)
    e["bounds_local"] = {"min": [-(ring + 0.15) * 100, -(ring + 0.15) * 100, -10], "max": [(ring + 0.15) * 100, (ring + 0.15) * 100, (height + 0.25) * 100]}
    e["emitter_shape"] = {"kind": "ring", "extent_cm": [ring * 100, ring * 100, 2]}
    tongue = max(height, 0.08) * 100
    # What Cycles shows is the emission integrated along the view ray, through the whole flame in front of and behind
    # the visible sample (the hidden core still glows through the gap). Sprites overlap ~2x (see SpawnRate).
    L = view_radiance(sc, o, lo, hi, zs, em_all, em if not occluded else em_all, n)
    nits = LM_PER_W * (L if L > 0 else E * 0.45 * tongue / 100) * 0.5
    set_params(e, {
        "RingRadius": ring * 100, "BoxExtent": [ring * 100, ring * 100, 2],
        "Velocity": [0, 0, tongue / life], "LifetimeMin": life * 0.7, "LifetimeMax": life * 1.1,
        # Tongue sprites: ~1/4 of the flame height wide, 2.5x as tall (the slice spread of a ring is ~ its radius,
        # so it cannot give the tongue width).
        "SizeMin": max(2.0, tongue * 0.35), "SizeMax": max(3.0, tongue * 0.55), "Aspect": 2.5,
        # Enough tongues for a continuous ring: circumference / tongue width, refreshed every lifetime, x2 overlap.
        "SpawnRate": float(np.clip(2 * (2 * math.pi * ring * 100) / max(tongue * 0.32, 1) / life, 30, 600)),
        "Color": [col[0] / mx, col[1] / mx, col[2] / mx, 1.0], "Intensity": nits, "Opacity": 1.0,
        "NoiseStrength": 300 + 30 * boil, "NoiseFreq": 0.06, "Drag": 2.0, "VelocityJitter": 0.3, "Grow": -0.5,
        "CoreIntensity": 0.35, "LightIntensity": 0.0, "LightRadius": max(100.0, tongue * 6), "LightOffset": [0, 0, tongue * 0.5],
    })
    e["physical"] = {"emission_nits": round(nits, 1), "view_radiance_p90": round(L, 4), "emission_color": col, "emission_per_m_p99": E, "ring_radius_m": ring,
                     "height_m": height, "tongue_halfwidth_m": width,
                     "profile": [[round(zw[k], 3), round(st[k]["r_peak"], 3), round(st[k]["peak"], 2)] for k in lev], "scroll_m_s": scroll, "noise_w_rate": boil,
                     # [z, emission seen by a scene camera / total] per emitting level
                     "visibility": [[round(zw[k], 3), round(vfrac[k], 3)] for k in range(len(zs)) if st_all[k]],
                     "occluded_fallback": occluded,
                     # where the camera-visible emission sits: weighted r (m, about the axis) and z (m, world), r 10/90 %
                     "visible_rz": visible_rz(em, R, zw)}
    e["time"]["preroll_s"] = round(life * 3, 2)
    L = nearest_light(sc, c, 1.0)
    e["light_link"] = L
    if L:
        e["notes"].append(f"practical light {L} lights the set; Niagara LightIntensity left at 0 (no double lighting)")
        fl = flicker(sc, L, frame, 240, fps)
        if fl:
            e["flicker"] = fl
    return e


def steam_entry(sc, o, m, frame, fps, typ, ev, conf):
    n = 32
    lo, hi, zs, f = sample_slices(o, m, frame, n=n, levels=12)
    d = f["density"]
    st = plume_stats(o, lo, hi, zs, d, n)
    mw = o.matrix_world
    good = [k for k, r in enumerate(st) if r and r["peak"] > 0.05 * max(x["peak"] for x in st if x)]
    if not good:
        return None
    b, t = st[good[0]], st[good[-1]]
    z0 = (mw @ Vector((0, 0, lo.z))).z
    ztop = t["c"].z
    height = max(0.2, ztop - z0)
    scroll = mapping_scroll(m, fps) or [0, 0, 0.5]
    rise = max(0.15, scroll[2])
    # The 4D noise scrolls fast but the plume body is only ~height/rise old at the top: lifetime = reach / rise.
    life = float(np.clip(height / rise, 1.0, 6.0))
    lean = (t["c"] - b["c"]) / life                  # m/s horizontal drift of the centroid
    sigma = float(np.percentile(d[good], 95))        # 1/m in the wisps
    width = 2 * float(np.mean([st[k]["spread"] for k in good]))
    tau = sigma * width                              # optical depth across the plume in the dense wisps
    base_r = max(0.04, b["spread"])
    alb = list(principled_volume(m).inputs["Color"].default_value)[:3]
    # Sprites: start ~2 x base radius, grow so the top spread matches.
    s0 = base_r * 2 * 100
    grow = float(np.clip((2 * t["spread"] * 100) / max(s0, 1) - 1, 1.0, 6.0))
    rate = float(np.clip(60.0 * height, 40, 160))     # puffs per second: ~100-300 alive per plume
    alive = rate * life
    overlap = max(1.0, alive * (s0 * (1 + grow / 2)) ** 2 / max((width * 100) * (height * 100), 1))
    alpha = float(np.clip(1 - math.exp(-tau / overlap), 0.02, 0.6))
    c = Vector((b["c"].x, b["c"].y, z0))
    e = base_entry(o.name, typ, conf, "volume_shader", [o.name], m.name, ev, ue_vec(c),
                   [(hi.x - lo.x) * 50 * mw.to_scale()[0], (hi.y - lo.y) * 50 * mw.to_scale()[1], height * 50 + 30],
                   "niagara", "NS_Steam" if typ == "steam" else "NS_Steam", fps, round(life * 1.5, 2))
    ext = [(hi.x - lo.x) * mw.to_scale()[0] * 100, (hi.y - lo.y) * mw.to_scale()[1] * 100]
    e["bounds_local"] = {"min": [-ext[0], -ext[1], -20], "max": [ext[0], ext[1], height * 100 + 80]}
    e["emitter_shape"] = {"kind": "disc", "extent_cm": [base_r * 100, base_r * 100, 2]}
    set_params(e, {
        "SpawnRate": rate, "LifetimeMin": life * 0.8, "LifetimeMax": life * 1.1,
        "SizeMin": s0 * 0.8, "SizeMax": s0 * 1.3, "Grow": grow,
        "Velocity": [0, 0, rise * 100], "Wind": ue_dir(Vector((lean.x, lean.y, 0))), "Drag": 1.2, "VelocityJitter": 0.3,
        "BoxExtent": [base_r * 100, base_r * 100, 2], "Color": alb + [1.0], "Opacity": alpha, "Intensity": 0.0,
        "NoiseStrength": 40 + 30 * rise, "NoiseFreq": 0.02,
    })
    e["physical"] = {"density_per_m": sigma, "optical_depth": tau, "albedo": alb,
                     "anisotropy": principled_volume(m).inputs["Anisotropy"].default_value, "lifetime_s": [life],
                     "drift_cm_s": [x * 100 for x in lean], "noise_scale_cm": None, "height_m": height, "width_m": width,
                     "base_radius_m": base_r, "scroll_m_s": scroll}
    e["notes"].append(f"alive ~{alive:.0f} sprites, est. overlap {overlap:.1f}")
    return e


def particle_entry(sc, o, frame, fps, shutter):
    md = next(md for md in o.modifiers if md.type == "PARTICLE_SYSTEM")
    ps = md.particle_system.settings
    span = max(1, ps.frame_end - ps.frame_start)
    life_s = ps.lifetime / fps
    v = Vector(ps.object_align_factor)
    speed = v.length
    g = ps.effector_weights.gravity
    ev = [f"particles count {ps.count} over {span} frames, life {life_s:.2f}s, velocity {tuple(round(x, 2) for x in v)}, gravity {g}"]
    inst = ps.instance_object
    radius, length = 0.001, 0.02
    if inst:
        dims = sorted(inst.dimensions)
        radius, length = dims[0] / 2, dims[2]
    score = {}
    if speed >= 3 and v.z < 0 and g < 0.5:
        score["rain"] = 4
    if speed < 1 and g >= 0.5:
        score["drips"] = 4
    if speed < 0.2 and g < 0.1:
        score["dust"] = 3
    if v.z > 0.5 and g >= 0.5:
        score["fountain"] = 3                        # launched upward, falls back: jets, sprinklers
    if g >= 0.3 and life_s < 1.5 and speed >= 1:
        score["sparks"] = score.get("sparks", 0) + 2  # short-lived ballistic bits (+ emissive instance below)
    for t in name_hint(o.name):
        score[t] = score.get(t, 0) + 2
    if not score:
        return unknown_entry(o, "particles", ev, fps)
    ranked = sorted(score.items(), key=lambda kv: -kv[1])
    typ = ranked[0][0]
    conf = ranked[0][1] / (ranked[0][1] + (ranked[1][1] if len(ranked) > 1 else 0))
    corners = [o.matrix_world @ Vector(c) for c in o.bound_box]
    lo = Vector([min(c[i] for c in corners) for i in range(3)])
    hi = Vector([max(c[i] for c in corners) for i in range(3)])
    ctr = (lo + hi) / 2
    half = [(hi[i] - lo[i]) * 50 for i in range(3)]
    rate = ps.count / span * fps
    # Drop material: emission strength + alpha of the instance (Principled).
    emis, alpha, colr = 0.0, 1.0, [0.8, 0.85, 0.9]
    if inst and inst.material_slots and inst.material_slots[0].material and inst.material_slots[0].material.node_tree:
        b = next((n for n in inst.material_slots[0].material.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if b:
            emis = b.inputs["Emission Strength"].default_value
            alpha = b.inputs["Alpha"].default_value
            colr = list(b.inputs["Emission Color"].default_value)[:3] if emis > 0 else list(b.inputs["Base Color"].default_value)[:3]
    width_cm = max(0.15, radius * 2 * 100)
    preroll = max(0.0, -ps.frame_start / fps)
    if typ == "rain":
        # Streak = drop length + distance travelled during the shutter (Cycles renders the drops motion-blurred).
        streak = length + speed * shutter / fps
        fall_h = hi.z - ground_z(sc, ctr, lo.z)
        life = min(life_s, fall_h / max(speed, 0.1) + 0.05)
        e = base_entry(o.name, "rain", conf, "particles", [o.name], inst.name if inst else None, ev, ue_vec(ctr), half, "niagara", "NS_Rain", fps, round(life * 1.5, 2))
        e["bounds_local"] = {"min": [-half[0] - 50, -half[1] - 50, -fall_h * 100 - 50], "max": [half[0] + 50, half[1] + 50, 50]}
        e["emitter_shape"] = {"kind": "box", "extent_cm": half}
        # Same alive density as Blender (count over its own lifetime), but only for the part above the ground.
        set_params(e, {"SpawnRate": rate, "LifetimeMin": life * 0.95, "LifetimeMax": life,
                       "Velocity": ue_dir(v), "VelocityJitter": ps.factor_random * 0.2, "BoxExtent": half,
                       "SizeMin": width_cm * (1 - ps.size_random), "SizeMax": width_cm, "Aspect": streak * 100 / width_cm,
                       "Color": colr + [1.0], "Intensity": LM_PER_W * emis * length / streak, "Opacity": alpha, "Gravity": 0.0, "Drag": 0.0})
        e["physical"] = {"count": ps.count, "lifetime_s": [life_s], "velocity_cm_s": ue_dir(v), "size_cm": [width_cm, streak * 100],
                         "emission_nits": LM_PER_W * emis, "fall_m": fall_h}
        e["notes"].append(f"streak {streak * 100:.1f} cm = drop {length * 100:.1f} cm + {speed:.1f} m/s x {shutter / fps * 1000:.0f} ms shutter")
    else:
        gz = ground_z(sc, ctr, lo.z)
        fall_h = max(0.05, lo.z - gz)
        v0 = -v.z
        t_fall = (-v0 + math.sqrt(v0 * v0 + 2 * 9.81 * g * fall_h)) / (9.81 * g) if g > 0 else fall_h / max(v0, 0.1)
        life = min(life_s, t_fall)
        e = base_entry(o.name, typ, conf, "particles", [o.name], inst.name if inst else None, ev, ue_vec(ctr), half, "niagara",
                       {"drips": "NS_Drips", "dust": "NS_DustMotes", "sparks": "NS_Sparks", "fountain": "NS_FountainJet"}.get(typ, "NS_Drips"),
                       fps, round(life * 2, 2))
        e["bounds_local"] = {"min": [-half[0] - 30, -half[1] - 30, -fall_h * 100 - 30], "max": [half[0] + 30, half[1] + 30, 30]}
        e["emitter_shape"] = {"kind": "line" if min(half[0], half[1]) < 5 else "box", "extent_cm": half}
        streak = length + (v0 + 9.81 * g * life * 0.5) * shutter / fps * 0.5
        set_params(e, {"SpawnRate": rate, "LifetimeMin": life, "LifetimeMax": life, "Velocity": ue_dir(v), "Gravity": g, "Drag": 0.0,
                       "VelocityJitter": ps.factor_random * 0.2, "BoxExtent": half, "SizeMin": width_cm * (1 - ps.size_random),
                       "SizeMax": width_cm, "Aspect": max(1.0, streak * 100 / width_cm), "Color": colr + [1.0],
                       "Intensity": LM_PER_W * emis * length / max(streak, length), "Opacity": alpha})
        e["physical"] = {"count": ps.count, "lifetime_s": [life_s], "gravity": g, "size_cm": [width_cm, length * 100], "fall_m": fall_h,
                         "ground_z_m": gz}
    e["notes"].append("Intensity = 683 x drop emission x drop / streak length: Cycles smears the drop's radiance over its motion-blurred"
                      " streak; sub-pixel streaks keep their energy through the sprite renderer's pixel coverage")
    return e


def unknown_entry(o, kind, ev, fps, mat=None):
    """Something animated we could not classify: keep its box and evidence, queue it for the agent (FX_AGENT.md)."""
    corners = [o.matrix_world @ Vector(c) for c in o.bound_box]
    lo = Vector([min(c[i] for c in corners) for i in range(3)])
    hi = Vector([max(c[i] for c in corners) for i in range(3)])
    e = base_entry(o.name, "unknown", 0.0, kind, [o.name], mat, ev, ue_vec((lo + hi) / 2), [(hi[i] - lo[i]) * 50 for i in range(3)],
                   "agent", None, fps, 0.0)
    e["notes"].append("unclassified: pick or author a template (fx_recipes), then set technique/template/params")
    return e


def ground_z(sc, p, below):
    dg = bpy.context.evaluated_depsgraph_get()
    hit, loc, *_ = sc.ray_cast(dg, Vector((p.x, p.y, below - 0.01)), Vector((0, 0, -1)), distance=50.0)
    return loc.z if hit else 0.0


def classify(sc, frame, emitter_names, volume_objects, templates_json=None):
    """Return the fx list for the scene. `volume_objects`: names of volume-only mesh objects; `emitter_names`: objects
    with particle systems. Entries claiming a volume carry source.objects = [name]."""
    global PARAM_TYPES
    if templates_json and os.path.exists(templates_json):
        PARAM_TYPES = json.load(open(templates_json))
    fps = sc.render.fps / sc.render.fps_base
    shutter = sc.render.motion_blur_shutter if sc.render.use_motion_blur else 0.0
    sc.frame_set(frame)
    out = []
    for name in volume_objects:
        o = sc.objects[name]
        m = volume_material(o)
        if not m:
            continue
        typ, ev, conf = classify_volume(sc, o, m, frame, fps)
        log("volume", name, typ, round(conf, 2), ev)
        if typ == "fire":
            out.append(fire_entry(sc, o, m, frame, fps, ev, conf))
        elif typ in ("steam", "smoke"):
            e = steam_entry(sc, o, m, frame, fps, typ, ev, conf)
            if e:
                out.append(e)
        elif typ is None:
            out.append(unknown_entry(o, "volume_shader", ev, fps, m.name))
        # haze stays on the fog path (height fog / local fog volumes)
    for name in emitter_names:
        o = sc.objects[name]
        e = particle_entry(sc, o, frame, fps, shutter)
        if e:
            out.append(e)
            log("particles", name, e["type"], e["confidence"])
    sc.frame_set(frame)
    return out


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    a = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    scene_in, out = a("--scene"), a("--out")
    frame = int(a("--frame", "60"))
    sc = bpy.context.scene
    vols = [o.name for o in sc.objects if o.type == "MESH" and not o.hide_render and volume_material(o)
            and all((s.material is None) or s.material == volume_material(o) or True for s in o.material_slots)]
    ems = [o.name for o in sc.objects if not o.hide_render and any(md.type == "PARTICLE_SYSTEM" for md in o.modifiers)]
    fx = classify(sc, frame, ems, vols, a("--templates", os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates.json")))
    scene = json.load(open(scene_in, encoding="utf-8")) if scene_in else {}
    scene["fx"] = fx
    claimed = {o for e in fx for o in e["source"]["objects"]}
    for k, v in scene.get("volumes", {}).items():
        if k in claimed:
            v["claimed_by_fx"] = True
    json.dump(scene, open(out, "w", encoding="utf-8"), indent=1)
    log("wrote", out, len(fx), "fx entries", [(e["id"], e["type"]) for e in fx])


if __name__ == "__main__":
    main()
