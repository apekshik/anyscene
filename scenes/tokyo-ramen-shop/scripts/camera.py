"""Handheld phone-camera feel: a slow push with noise-driven shake (low-freq sway + high-freq jitter),
DOF on a focus target, motion blur and a slight exposure drift."""
import math

import bpy
from mathutils import Vector


def _noise(fc, scale, strength, phase, depth=1):
    m = fc.modifiers.new("NOISE")
    m.scale = scale
    m.strength = strength
    m.phase = phase
    m.depth = depth
    return m


def handheld(cam, start, end, target, frames=120, seed=3, sway=0.012, jitter=0.0025, rot_deg=0.55, fstop=2.2):
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, frames
    cam.animation_data_clear()
    for f, p in ((1, start), (frames, end)):
        cam.location = p
        cam.rotation_euler = (Vector(target) - Vector(p)).to_track_quat("-Z", "Y").to_euler()
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
    act = cam.animation_data.action
    fcurves = act.fcurves if hasattr(act, "fcurves") else act.layers[0].strips[0].channelbag(act.slots[0]).fcurves
    for fc in fcurves:
        for k in fc.keyframe_points:
            k.interpolation = "BEZIER"
            k.easing = "EASE_IN_OUT"
        i = fc.array_index
        if fc.data_path == "location":
            _noise(fc, 38, sway, seed * 10 + i * 3.1, depth=1)
            _noise(fc, 5, jitter, seed * 20 + i * 7.3, depth=0)
        else:
            _noise(fc, 45, math.radians(rot_deg), seed * 30 + i * 5.7, depth=1)
            _noise(fc, 6, math.radians(rot_deg * 0.18), seed * 40 + i * 2.9, depth=0)
    d = cam.data
    d.dof.use_dof = True
    d.dof.aperture_fstop = fstop
    d.dof.focus_distance = (Vector(target) - Vector(start)).length
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = 0.5
    # Exposure breathing like a phone's auto-exposure.
    vs = sc.view_settings
    base = vs.exposure
    for f, ev in ((1, base - 0.05), (frames * 0.45, base + 0.12), (frames, base - 0.02)):
        vs.exposure = ev
        vs.keyframe_insert("exposure", frame=int(f))


def still_dof(cam, target, fstop=2.8):
    d = cam.data
    d.dof.use_dof = True
    d.dof.aperture_fstop = fstop
    d.dof.focus_distance = (Vector(target) - cam.matrix_world.translation).length
