"""Imperfections pass (runs after the mirror; everything here is position-agnostic or uses object-local masks).

overlay() injects dirt into any Principled material in place, keeping whatever drives its Base Color:
  ao     crevice / contact dirt from Ambient Occlusion (corners, under rims, around buttons)
  dust   grey dust on upward-facing surfaces (top shelves, hood top, appliance tops)
  grease amber oily film + lower roughness + streaks running down (hood, backsplash, range)
  sticky patchy glossy coat (ticket machine buttons, counter caddies)
  scorch blackened bottoms (stockpots), from object-local height
Plus: greasy stainless drips on the hood front, stained grout, worn counter edges, curled posters."""
import math

import bmesh
import bpy
from mathutils import Vector

from lib import L, mathn, mix, noise, ramp, texcoord


def _bsdf(m):
    return next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if m and m.node_tree else None


def _source(nt, sock):
    """Current driver of a socket as an output socket (creates an RGB/Value node for a default value)."""
    if sock.is_linked:
        out = sock.links[0].from_socket
        nt.links.remove(sock.links[0])
        return out
    if sock.type == "RGBA":
        n = nt.nodes.new("ShaderNodeRGB")
        n.outputs[0].default_value = sock.default_value
    else:
        n = nt.nodes.new("ShaderNodeValue")
        n.outputs[0].default_value = sock.default_value
    return n.outputs[0]


def overlay(m, ao=0.0, dust=0.0, grease=0.0, sticky=0.0, scorch=0.0, ao_dist=0.06):
    b = _bsdf(m)
    if b is None or m.get("grimed"):
        return
    m["grimed"] = True
    nt = m.node_tree
    col = _source(nt, b.inputs["Base Color"])
    rough = _source(nt, b.inputs["Roughness"])
    co = texcoord(nt, "Object")
    blot = noise(nt, 7.0, 6, 0.6, co)
    if ao:
        a = nt.nodes.new("ShaderNodeAmbientOcclusion")
        a.inputs["Distance"].default_value = ao_dist
        a.samples = 8
        dirt = mathn(nt, "MULTIPLY", mathn(nt, "SUBTRACT", 1.0, a.outputs["AO"]), mathn(nt, "ADD", 0.5, blot.outputs["Fac"]))
        col = mix(nt, mathn(nt, "MULTIPLY", dirt, ao, clamp=True), col, (0.09, 0.065, 0.04, 1), "MULTIPLY")
    if grease:
        mp = nt.nodes.new("ShaderNodeMapping")
        L(nt, co, mp.inputs["Vector"])
        mp.inputs["Scale"].default_value = (18.0, 18.0, 1.2)        # vertical streaks
        streak = noise(nt, 1.0, 5, 0.6, mp.outputs[0])
        g = ramp(nt, [(0.38, (0, 0, 0)), (0.68, (1, 1, 1))], mix(nt, 0.5, streak.outputs["Fac"], blot.outputs["Fac"]))
        gk = mathn(nt, "MULTIPLY", g.outputs["Color"], grease, clamp=True)
        col = mix(nt, gk, col, (0.22, 0.13, 0.04, 1), "MULTIPLY")
        rough = mix(nt, gk, rough, (0.08, 0.08, 0.08, 1))
        b.inputs["Coat Weight"].default_value = max(b.inputs["Coat Weight"].default_value, 0.35 * grease)
        b.inputs["Coat Roughness"].default_value = 0.08
    if sticky:
        s = ramp(nt, [(0.45, (0, 0, 0)), (0.62, (1, 1, 1))], noise(nt, 11.0, 4, 0.5, co).outputs["Fac"])
        sk = mathn(nt, "MULTIPLY", s.outputs["Color"], sticky)
        rough = mix(nt, sk, rough, (0.06, 0.06, 0.06, 1))
        col = mix(nt, mathn(nt, "MULTIPLY", sk, 0.5), col, (0.55, 0.42, 0.25, 1), "MULTIPLY")
        b.inputs["Coat Weight"].default_value = max(b.inputs["Coat Weight"].default_value, 0.5 * sticky)
    if scorch:
        gen = nt.nodes.new("ShaderNodeSeparateXYZ")
        L(nt, texcoord(nt, "Generated"), gen.inputs[0])
        low = ramp(nt, [(0.0, (1, 1, 1)), (0.22, (0.4, 0.4, 0.4)), (0.4, (0, 0, 0))], gen.outputs["Z"])
        sc = mathn(nt, "MULTIPLY", mathn(nt, "MULTIPLY", low.outputs["Color"], mathn(nt, "ADD", 0.4, blot.outputs["Fac"])), scorch, clamp=True)
        col = mix(nt, sc, col, (0.025, 0.018, 0.012, 1))
        rough = mix(nt, sc, rough, (0.75, 0.75, 0.75, 1))
    if dust:
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        L(nt, geo.outputs["Normal"], sep.inputs[0])
        up = ramp(nt, [(0.55, (0, 0, 0)), (0.85, (1, 1, 1))], sep.outputs["Z"])
        fine = noise(nt, 60.0, 4, 0.7, co)
        dk = mathn(nt, "MULTIPLY", mathn(nt, "MULTIPLY", up.outputs["Color"], mathn(nt, "ADD", 0.35, fine.outputs["Fac"])), dust, clamp=True)
        col = mix(nt, dk, col, (0.32, 0.3, 0.27, 1))
        rough = mix(nt, dk, rough, (1, 1, 1, 1))
    L(nt, col, b.inputs["Base Color"])
    L(nt, rough, b.inputs["Roughness"])


def mats_of(names, prefix=False):
    out = []
    for o in bpy.data.objects:
        base = o.name.split(".")[0]
        if (base in names) or (prefix and any(base.startswith(n) for n in names)):
            if o.type in ("MESH", "CURVE", "FONT"):
                out += [m for m in o.data.materials if m]
    return list(dict.fromkeys(out))


def split_mat(objs, suffix):
    """Give these objects their own copy of their materials so an overlay does not hit shared ones."""
    for o in objs:
        for i, m in enumerate(o.data.materials):
            if m and not m.name.endswith(suffix):
                o.data.materials[i] = bpy.data.materials.get(m.name + suffix) or m.copy()
                o.data.materials[i].name = m.name + suffix


def curl_plane(o, amount=0.05, corner=(1, 1), res=10):
    """Subdivide a 4-vertex wall poster and peel one corner off the wall (local -Y is its front)."""
    me = o.data
    if len(me.vertices) != 4:
        return
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=res, use_grid_fill=True)
    xs = [v.co.x for v in bm.verts]
    zs = [v.co.z for v in bm.verts]
    for v in bm.verts:
        u = (v.co.x - min(xs)) / (max(xs) - min(xs))
        w = (v.co.z - min(zs)) / (max(zs) - min(zs))
        du = u if corner[0] else 1 - u
        dw = w if corner[1] else 1 - w
        k = max(0.0, (du + dw - 1.25) / 0.75)
        v.co.y -= amount * k * k
    bm.to_mesh(me)
    bm.free()


def build():
    # Greasy stainless: hood, duct, backsplash heavy; shelves, counter tops and the range light.
    heavy = [bpy.data.objects[n] for n in ("hood", "hood_duct", "backsplash") if n in bpy.data.objects]
    split_mat(heavy, "_greasy")
    for m in mats_of(["hood", "hood_duct", "backsplash"]):
        overlay(m, ao=0.6, grease=1.0, dust=0.5)
    light = [o for o in bpy.data.objects if o.name.startswith(("shelf_", "back_counter", "prep_top"))]
    split_mat(light, "_used")
    for m in mats_of(["shelf_", "back_counter", "prep_top"], prefix=True):
        overlay(m, ao=0.7, grease=0.35, dust=0.9)
    # Appliances and props.
    for m in mats_of(["ramen_gas_range", "ramen_noodle_boiler"]):
        overlay(m, ao=0.8, grease=0.8)
    for m in mats_of(["stockpot"]):
        overlay(m, ao=0.5, scorch=0.9)
    for m in mats_of(["ticket_machine"]):
        overlay(m, ao=0.9, sticky=0.8, dust=0.6)
    for m in mats_of(["ramen_drink_fridge", "ramen_crt_tv_bracket", "ramen_wall_fan", "ramen_rice_cooker", "ramen_cash_register", "ramen_kettle_pot"]):
        overlay(m, ao=0.7, dust=0.8, grease=0.25)
    for m in mats_of(["condiment_caddy", "ramen_soy_bottles", "ramen_tare_containers", "ramen_water_pitcher"]):
        overlay(m, ao=0.4, sticky=0.5)
    for m in mats_of(["ramen_bowl_stack", "ramen_dish_rack", "ramen_stool", "ramen_beer_crate", "ramen_square_cans", "ramen_noodle_crates", "ramen_trash_bin"]):
        overlay(m, ao=0.6, dust=0.3)
    # Room surfaces: crevice dirt everywhere it meets something; dust on the plaque beam and pendant shades.
    for m in mats_of(["floor"]):
        overlay(m, ao=1.0, ao_dist=0.15)
    for m in mats_of(["wall_L", "wall_back", "wall_R_up", "front_a", "wainscot_L", "counter_base_long", "pass_long"]):
        overlay(m, ao=0.7, ao_dist=0.12)
    for m in mats_of(["wall_R_tile"]):
        overlay(m, ao=0.8, grease=0.7, ao_dist=0.1)
    for m in mats_of(["plaque_beam", "pendant_shade_"], prefix=True):
        overlay(m, dust=1.0, grease=0.2)
    for m in mats_of(["counter_top_long", "pass_top"]):
        overlay(m, ao=0.5, sticky=0.25)
    # Peeling posters / calendar / notice.
    for name, amt, corner in (("poster_beer", 0.06, (1, 1)), ("calendar", 0.03, (0, 0)), ("handwritten_notice", 0.04, (1, 1))):
        o = bpy.data.objects.get(name)
        if o:
            curl_plane(o, amt, corner)
