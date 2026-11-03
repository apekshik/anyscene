"""Build one LevelSequence per baked camrig shot in the demo project (headless commandlet):

  UnrealEditor-Cmd.exe AnySceneHKDemo.uproject -run=pythonscript -script="<path>/make_seqs.py" -unattended -nosplash -nop4

Env:
  DEMO_CAMS    folder of <shot>.json from bake_cams.py (required)
  DEMO_SHOTS   comma list of shots (default: every json in DEMO_CAMS)
  DEMO_OUT     MRQ output folder on disk (frames land in <DEMO_OUT>/<SEQ name>/)
  DEMO_TS      MRQ temporal samples (default 6)
  DEMO_LEVEL   level path (default /Game/AnyScene/HK/L_HK)

Per shot: a CineCameraActor DEMO_<shot> in the level (filmback = Blender sensor width x width*h/w), and
/Game/AnySceneDemo/Sequences/SEQ_<shot> at the shot's fps with frames 0..N-1 (= Blender frames 1..N), a camera cut
over the whole range, and a key on every frame (linear) for location, rotation (unwrapped), CurrentFocalLength,
CurrentAperture and FocusSettings.ManualFocusDistance. Extra keys at -1 and N (Blender frames 0 and N+1) cover the
motion-blur subframes at the ends. The camera's own post-process sets motion blur to the shot's shutter (180 deg =
amount 0.5); the level's grade volume turns it off for its stills.
MRQ configs: /Game/AnySceneDemo/MRQ/MRQ_Demo (deferred, PNG, TSR, DEMO_TS temporal samples, 64 warm-up frames with
use_camera_cut_for_warm_up False) and MRQ_DemoCheck (same, 1 temporal sample, for the camera-match check).
"""
import json
import math
import os
import time

import unreal
import warnings

warnings.simplefilter("ignore", DeprecationWarning)

CAMS = os.environ["DEMO_CAMS"]
SHOTS = [s for s in os.environ.get("DEMO_SHOTS", "").split(",") if s] or \
    sorted(f[:-5] for f in os.listdir(CAMS) if f.endswith(".json"))
OUT = os.environ.get("DEMO_OUT", os.path.join(CAMS, "..", "mrq")).replace("\\", "/")
TS = int(os.environ.get("DEMO_TS", "6"))
LEVEL = os.environ.get("DEMO_LEVEL", "/Game/AnyScene/HK/L_HK")
DEST = "/Game/AnySceneDemo"
EAL = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
T0 = time.time()


def log(*a):
    unreal.log_warning("DEMO " + " ".join(str(x) for x in a))


def V(v):
    return unreal.Vector(v[0], v[1], v[2])


def unwrap(prev, cur):
    if prev is None:
        return cur
    while cur - prev > 180:
        cur -= 360
    while cur - prev < -180:
        cur += 360
    return cur


def channels(sec):
    for fn in ("get_all_channels", "get_channels"):
        if hasattr(sec, fn):
            return list(getattr(sec, fn)())
    return list(unreal.MovieSceneSectionExtensions.get_all_channels(sec))


def key(ch, f, v):
    ch.add_key(unreal.FrameNumber(f), float(v), 0.0, unreal.MovieSceneTimeUnit.DISPLAY_RATE,
               unreal.MovieSceneKeyInterpolation.LINEAR)


def float_track(binding, prop, path, n, vals):
    tr = binding.add_track(unreal.MovieSceneFloatTrack)
    tr.set_property_name_and_path(prop, path)
    sec = tr.add_section()
    sec.set_range(-1, n + 1)
    ch = channels(sec)[0]
    for f, v in vals:
        key(ch, f, v)
    return tr


les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les.load_level(LEVEL)
log("level", LEVEL, "actors", len(eas.get_all_level_actors()), "shots", SHOTS)

for shot in SHOTS:
    d = json.load(open(os.path.join(CAMS, shot + ".json")))
    n, fps = d["frames_n"], d["fps"]
    label = "DEMO_" + shot
    for a in eas.get_all_level_actors():
        if a.get_actor_label() == label:
            eas.destroy_actor(a)
    fr = d["frames"]  # blender frames 0..n+1 -> UE frames -1..n
    f1 = fr[1]
    cam = eas.spawn_actor_from_class(unreal.CineCameraActor, V(f1["loc"]),
                                     unreal.MathLibrary.make_rot_from_xz(V(f1["forward"]), V(f1["up"])))
    cam.set_actor_label(label)
    cam.set_folder_path("DemoCameras")
    cc = cam.get_cine_camera_component()
    fb = cc.get_editor_property("filmback")
    fb.set_editor_property("sensor_width", d["sensor_width_mm"])
    fb.set_editor_property("sensor_height", d["sensor_height_mm"])
    cc.set_editor_property("filmback", fb)
    lens = cc.get_editor_property("lens_settings")
    lens.set_editor_property("min_f_stop", 0.7)
    lens.set_editor_property("max_f_stop", 32.0)
    cc.set_editor_property("lens_settings", lens)
    cc.set_editor_property("current_focal_length", f1["lens_mm"])
    cc.set_editor_property("current_aperture", f1["fstop"])
    fs = cc.get_editor_property("focus_settings")
    fs.set_editor_property("focus_method", unreal.CameraFocusMethod.MANUAL if d["dof"] else unreal.CameraFocusMethod.DISABLE)
    fs.set_editor_property("manual_focus_distance", f1["focus_cm"] or 100000.0)
    cc.set_editor_property("focus_settings", fs)
    pp = cc.get_editor_property("post_process_settings")
    pp.set_editor_property("override_motion_blur_amount", True)
    pp.set_editor_property("motion_blur_amount", d["shutter_deg"] / 360.0)
    pp.set_editor_property("override_motion_blur_max", True)
    pp.set_editor_property("motion_blur_max", 100.0)
    cc.set_editor_property("post_process_settings", pp)
    cc.set_editor_property("post_process_blend_weight", 1.0)

    sp = f"{DEST}/Sequences/SEQ_{shot}"
    if EAL.does_asset_exist(sp):
        EAL.delete_asset(sp)
    seq = AT.create_asset(f"SEQ_{shot}", f"{DEST}/Sequences", unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
    seq.set_display_rate(unreal.FrameRate(fps, 1))
    seq.set_playback_start(0)
    seq.set_playback_end(n)
    b = seq.add_possessable(cam)
    cb = seq.add_possessable(cc)
    try:
        if not cb.get_parent().is_valid():
            cb.set_parent(b)
    except Exception:
        cb.set_parent(b)

    # Transform: one key per frame, rotation unwrapped so subframes never spin through +-180.
    tr = b.add_track(unreal.MovieScene3DTransformTrack)
    sec = tr.add_section()
    sec.set_range(-1, n + 1)
    ch = channels(sec)
    prev = [None, None, None]
    for i, F in enumerate(fr):
        f = F["blender_frame"] - 1
        r = unreal.MathLibrary.make_rot_from_xz(V(F["forward"]), V(F["up"]))
        rpy = [unwrap(prev[0], r.roll), unwrap(prev[1], r.pitch), unwrap(prev[2], r.yaw)]
        prev = rpy
        for c, v in zip(ch[0:6], F["loc"] + rpy):
            key(c, f, v)
    for c in ch[6:9]:
        key(c, -1, 1.0)
    float_track(cb, "CurrentFocalLength", "CurrentFocalLength", n, [(F["blender_frame"] - 1, F["lens_mm"]) for F in fr])
    if d["dof"]:
        float_track(cb, "CurrentAperture", "CurrentAperture", n, [(F["blender_frame"] - 1, F["fstop"]) for F in fr])
        float_track(cb, "ManualFocusDistance", "FocusSettings.ManualFocusDistance", n,
                    [(F["blender_frame"] - 1, F["focus_cm"]) for F in fr])

    try:
        cut = seq.add_track(unreal.MovieSceneCameraCutTrack)
    except Exception:
        cut = seq.add_master_track(unreal.MovieSceneCameraCutTrack)
    cs = cut.add_section()
    cs.set_range(0, n)
    cs.set_camera_binding_id(seq.get_binding_id(b) if hasattr(seq, "get_binding_id")
                             else unreal.MovieSceneSequenceExtensions.get_binding_id(seq, b))
    EAL.save_loaded_asset(seq, False)
    log("sequence", sp, n, "frames @", fps, "keys/channel", len(fr), "tracks", [t.get_display_name() for t in cb.get_tracks()])

if not les.save_current_level():
    log("save_current_level returned False")

for name, ts in (("MRQ_Demo", TS), ("MRQ_DemoCheck", 1)):
    cp = f"{DEST}/MRQ/{name}"
    if EAL.does_asset_exist(cp):
        EAL.delete_asset(cp)
    cfg = AT.create_asset(name, f"{DEST}/MRQ", unreal.MoviePipelinePrimaryConfig, None)
    cfg.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPassBase)
    png = cfg.find_or_add_setting_by_class(unreal.MoviePipelineImageSequenceOutput_PNG)
    cfg.find_or_add_setting_by_class(unreal.MoviePipelineGameOverrideSetting)
    out = cfg.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
    out.output_directory = unreal.DirectoryPath(OUT + ("" if ts > 1 else "/check"))
    out.file_name_format = "{sequence_name}/{frame_number}"
    out.output_resolution = unreal.IntPoint(1920, 804)
    out.zero_pad_frame_numbers = 4
    out.override_existing_output = True
    aa = cfg.find_or_add_setting_by_class(unreal.MoviePipelineAntiAliasingSetting)
    aa.override_anti_aliasing = True
    aa.anti_aliasing_method = unreal.AntiAliasingMethod.AAM_TSR
    aa.spatial_sample_count = 1
    aa.temporal_sample_count = ts
    aa.engine_warm_up_count = 64
    aa.render_warm_up_frames = True
    aa.use_camera_cut_for_warm_up = False
    EAL.save_loaded_asset(cfg, False)
    log("config", cp, "temporal", ts, "out", out.output_directory.path)
log("done", f"{time.time() - T0:.0f}s")
