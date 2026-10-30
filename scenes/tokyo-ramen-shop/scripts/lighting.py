"""Night lighting for the ramen shop (design coordinates; build.py mirrors everything afterwards).

Key: warm 2700 K pendants over the counter. Kitchen: dimmer 3200 K hood strip + one ceiling tube.
Accents: ticket machine and drink fridge glow (cool), red akachochin outside, cool street fill through the glass.
Atmosphere: low-density room haze + steam volumes over the stockpots."""
import math

import bpy

import shell as S
from lib import L, area, blackbody, box, m_simple, mathn, new_mat, node, noise, point, spot, texcoord

WARM = blackbody(2600)
KITCHEN = blackbody(3300)
STREET = (0.5, 0.62, 1.0)


def haze_material(density):
    m, nt = new_mat("haze")
    if nt:
        nt.nodes.remove(nt.nodes["Principled BSDF"])
        v = nt.nodes.new("ShaderNodeVolumePrincipled")
        v.inputs["Density"].default_value = density
        v.inputs["Anisotropy"].default_value = 0.45
        v.inputs["Color"].default_value = (0.9, 0.9, 0.92, 1)
        L(nt, v.outputs[0], nt.nodes["Material Output"].inputs["Volume"])
    return m


def steam_material():
    """Wispy steam: noise density, thinning with height, drifting with the frame via the 4D W coordinate."""
    m, nt = new_mat("steam")
    if nt:
        nt.nodes.remove(nt.nodes["Principled BSDF"])
        co = texcoord(nt, "Generated")
        n = noise(nt, 4.0, 6, 0.6, co, dim="4D")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        L(nt, co, sep.inputs[0])
        fade = mathn(nt, "SUBTRACT", 1.0, sep.outputs["Z"])
        radial = mathn(nt, "POWER", fade, 1.5)
        dens = mathn(nt, "MULTIPLY", mathn(nt, "MAXIMUM", mathn(nt, "SUBTRACT", n.outputs["Fac"], 0.45), 0.0), 30.0)
        dens = mathn(nt, "MULTIPLY", dens, radial)
        v = nt.nodes.new("ShaderNodeVolumePrincipled")
        v.inputs["Color"].default_value = (0.95, 0.95, 0.95, 1)
        v.inputs["Anisotropy"].default_value = 0.6
        L(nt, dens, v.inputs["Density"])
        L(nt, v.outputs[0], nt.nodes["Material Output"].inputs["Volume"])
        # Animate the noise W with the frame so steam drifts in the clip.
        fc = n.inputs["W"].driver_add("default_value")
        fc.driver.expression = "frame * 0.025"
    return m


def build(c, haze=0.006, steam_spots=()):
    sc = bpy.context.scene
    # Pendants: a downward spot (the pool on the counter) + a weak point inside the shade for its glow.
    for i, y in enumerate(S.PENDANT_Y):
        x, z = S.CX + 0.22, 1.74
        spot(f"pendant_spot_{i}", c, (x, y, z), (0, 0, 0), 70, WARM, angle=125, blend=0.8, radius=0.03)
        point(f"pendant_glow_{i}", c, (x, y, z + 0.09), 6, WARM, radius=0.03)
    # Kitchen: strip under the hood and a single ceiling tube over the cook's aisle.
    area("hood_strip", c, (S.W - 0.38, 4.4, 1.83), (0, 0, 0), 0.12, 35, KITCHEN, size_y=1.6)
    area("kitchen_tube", c, (2.75, 4.0, 2.55), (0, 0, 0), 0.08, 14, KITCHEN, size_y=1.2)
    area("kitchen_tube_front", c, (2.75, 1.6, 2.55), (0, 0, 0), 0.08, 6, KITCHEN, size_y=1.0)
    # Ticket machine face glow (machine on the left wall near the door, facing +X).
    # Area lights shine along their local -Z: rot x +90 points +Y, rot y -90 points +X.
    area("ticket_glow", c, (0.31, 0.52, 1.15), (math.radians(90), 0, 0), 0.5, 10, (0.85, 0.92, 1.0), size_y=0.8)
    # Drink fridge glow.
    area("fridge_glow", c, (0.66, 6.68, 1.0), (0, math.radians(-90), 0), 0.45, 8, (0.88, 0.95, 1.0), size_y=1.2)
    # Red lantern outside: light source inside the paper body.
    lx, ly, lz = S.LANTERN
    point("lantern_light", c, (lx, ly, lz + 0.3), 35, (1.0, 0.22, 0.08), radius=0.12)
    # Cool street fill through the door and window, plus a faint sky.
    area("street_fill", c, (S.W / 2, -2.0, 2.2), (math.radians(70), 0, 0), 3.0, 30, STREET, size_y=1.5)
    area("street_bounce", c, (S.W / 2, -1.0, 0.1), (math.radians(100), 0, 0), 3.0, 6, (0.6, 0.65, 0.8), size_y=0.8)
    sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.006, 0.008, 0.013, 1)

    # Atmosphere: haze box filling the shop interior (kept inside so the backdrop stays crisp).
    if haze:
        hz = box("haze_volume", (0.02, 0.02, 0.01), (S.W - 0.02, S.D - 0.02, S.H - 0.01), c, haze_material(haze), bevel=0)
        hz.visible_shadow = False
    sm = steam_material()
    for i, (x, y, z, r) in enumerate(steam_spots):
        bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=0.9, vertices=24, location=(x, y, z + 0.45))
        o = bpy.context.object
        o.name = f"steam_{i}"
        for uc in list(o.users_collection):
            uc.objects.unlink(o)
        c.objects.link(o)
        o.data.materials.append(sm)
        o.visible_shadow = False

    # Render settings tuned for a dark interior with volumes.
    cy = sc.cycles
    cy.max_bounces = 8
    cy.diffuse_bounces = 4
    cy.glossy_bounces = 4
    cy.transmission_bounces = 8
    cy.volume_bounces = 1
    cy.transparent_max_bounces = 8
    cy.volume_step_rate = 4.0
    cy.sample_clamp_indirect = 8.0
    cy.blur_glossy = 1.0
