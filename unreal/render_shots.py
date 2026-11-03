"""Lit stills of the scene's own cameras from a running editor with no window:

  UnrealEditor.exe <project>.uproject "-ExecCmds=py <path>/render_shots.py" -RenderOffscreen
                   "-dpcvars=Editor.AsyncAssetCompilation=0,Editor.AsyncTextureCompilation=0,Editor.AsyncStaticMeshCompilation=0,r.TextureStreaming=0"
                   -unattended -nosplash -nop4 -nosound

The -dpcvars are required. With async asset compilation (the default) an offscreen editor never finishes compiling
the imported meshes/textures: ~70% of the scene (every prop, sign, the ground) stays invisible and the rest shows
placeholder textures, with no log line saying so. r.TextureStreaming=0 avoids low-mip signage in a 20 s session.

Use -ExecCmds=py, not -ExecutePythonScript: the latter issues QUIT_EDITOR right after the script returns (frame 3),
before any tick callback has run, unless the script happens to block (a load_level inside it did, which is why the
first test worked). The project's EditorStartupMap is the level; ANYSCENE_MAP can load another one (in Git Bash set
MSYS_NO_PATHCONV=1, or /Game/... is rewritten to C:/Program Files/Git/Game/...).
Movie Render Queue (render_mrq.ps1) gives better frames (8 temporal samples, DOF) at ~50-65 s per still with startup.

Uses a SceneCapture2D per CineCameraActor (same transform, FOV from filmback/focal length, DOF and the unbound
post-process volume's grade copied over), lets Lumen/VSM converge for WARM frames with the capture ticking, then
writes <out>/<camera>.png (tone-mapped + LUT) and <out>/<camera>_hdr.exr (scene-linear, pre-tonemap, for an AgX
pass). Quits the editor when done. Env: ANYSCENE_SHOTS (comma list of camera labels), ANYSCENE_SHOT_DIR,
ANYSCENE_SHOT_RES (WxH, default 1920x804), ANYSCENE_WARM (frames, default 90), ANYSCENE_WARM_S (wall-clock seconds
before the first capture, default 0), ANYSCENE_QUIT (default 1).
"""
import os
import time
import warnings

import unreal

warnings.simplefilter("ignore", DeprecationWarning)

SHOTS = [s for s in os.environ.get("ANYSCENE_SHOTS", "cam_street,cam_table,cam_wok").split(",") if s]
OUT = os.environ.get("ANYSCENE_SHOT_DIR", os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "Shots"))
W, H = (int(x) for x in os.environ.get("ANYSCENE_SHOT_RES", "1920x804").split("x"))
WARM = int(os.environ.get("ANYSCENE_WARM", "90"))
# Wall-clock minimum before the FIRST capture: on a cold DDC the editor renders the default material and skips
# meshes whose shaders are still compiling (150 frames pass in ~3 s), so frame counts alone are not enough.
WARM_S = float(os.environ.get("ANYSCENE_WARM_S", "0"))
T_START = time.time()
QUIET_S = float(os.environ.get("ANYSCENE_QUIET_S", "20"))
_LOG = {"path": None, "pos": 0, "last": time.time(), "n": 0}


def compile_quiet():
    """True once the editor log has shown no texture-build / shader-compile line for QUIET_S seconds. There is no
    Python API for the asset/shader compiling managers, and a fresh import spends minutes encoding textures in the
    background (props render with placeholders, or not at all, until it is done)."""
    if _LOG["path"] is None:
        d = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_log_dir())
        logs = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".log")]
        _LOG["path"] = max(logs, key=os.path.getmtime)
    try:
        with open(_LOG["path"], "rb") as f:
            f.seek(_LOG["pos"])
            chunk = f.read()
            _LOG["pos"] = f.tell()
    except OSError:
        return True
    hits = sum(chunk.count(k) for k in (b"Building texture", b"Building static mesh", b"shaders remaining",
                                         b"Compiling shader", b"Waiting for static meshes", b"LogShaderCompilers: Display: Compiled"))
    if hits:
        _LOG["last"] = time.time()
        _LOG["n"] += hits
    return time.time() - _LOG["last"] >= QUIET_S
QUIT = os.environ.get("ANYSCENE_QUIT", "1") == "1"
MOVABLE = os.environ.get("ANYSCENE_MOVABLE", "0") == "1"
os.makedirs(OUT, exist_ok=True)


def log(*a):
    unreal.log_warning("SHOTS " + " ".join(str(x) for x in a))


eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
STATE = {"i": 0, "frame": 0, "cap": None, "t0": time.time(), "handle": None, "rt": None, "rt_hdr": None, "cap_hdr": None}


def actors():
    return eas.get_all_level_actors()




def reregister_meshes():
    """Force every static mesh component to rebuild its render state (set the mesh to None and back)."""
    n = 0
    for a in actors():
        if isinstance(a, unreal.StaticMeshActor):
            c = a.static_mesh_component
            sm = c.static_mesh
            if sm:
                if MOVABLE:
                    c.set_mobility(unreal.ComponentMobility.MOVABLE)
                c.set_static_mesh(None)
                c.set_static_mesh(sm)
                n += 1
    log("re-registered", n, "mesh components")


def setup(label):
    world = ues.get_editor_world()
    cam = next((a for a in actors() if a.get_actor_label() == label), None)
    if cam is None:
        log("missing camera", label)
        return False
    cc = cam.get_cine_camera_component()
    fb = cc.filmback.sensor_width
    fov = 2 * unreal.MathLibrary.radians_to_degrees(unreal.MathLibrary.atan(fb / 2 / cc.current_focal_length))
    ppv = next((a for a in actors() if isinstance(a, unreal.PostProcessVolume) and a.get_editor_property("unbound")), None)
    caps = []
    for kind in ("ldr", "hdr"):
        if kind == "ldr":
            rt = unreal.RenderingLibrary.create_render_target2d(world, W, H, unreal.TextureRenderTargetFormat.RTF_RGBA8_SRGB)
        else:
            rt = unreal.RenderingLibrary.create_render_target2d(world, W, H, unreal.TextureRenderTargetFormat.RTF_RGBA16F)
        cap = eas.spawn_actor_from_class(unreal.SceneCapture2D, cam.get_actor_location(), cam.get_actor_rotation())
        c = cap.capture_component2d
        c.set_editor_property("fov_angle", fov)
        c.set_editor_property("texture_target", rt)
        c.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_TONE_CURVE_HDR if kind == "ldr" else unreal.SceneCaptureSource.SCS_SCENE_COLOR_HDR)
        c.set_editor_property("capture_every_frame", True)
        c.set_editor_property("always_persist_rendering_state", True)
        if ppv:
            s = ppv.settings
            # Cine camera DOF onto the capture (captures don't read the camera component).
            fs = cc.focus_settings
            if fs.focus_method == unreal.CameraFocusMethod.MANUAL:
                s.set_editor_property("override_depth_of_field_fstop", True)
                s.set_editor_property("depth_of_field_fstop", cc.current_aperture)
                s.set_editor_property("override_depth_of_field_focal_distance", True)
                s.set_editor_property("depth_of_field_focal_distance", fs.manual_focus_distance)
                s.set_editor_property("override_depth_of_field_sensor_width", True)
                s.set_editor_property("depth_of_field_sensor_width", fb)
            c.set_editor_property("post_process_settings", s)
            c.set_editor_property("post_process_blend_weight", 1.0)
        caps.append((cap, rt))
    STATE["caps"] = caps
    return True


def finish(label):
    world = ues.get_editor_world()
    (cap, rt), (cap_h, rt_h) = STATE["caps"]
    unreal.RenderingLibrary.export_render_target(world, rt, OUT, label + ".png")
    unreal.RenderingLibrary.export_render_target(world, rt_h, OUT, label + "_hdr.exr")
    eas.destroy_actor(cap)
    eas.destroy_actor(cap_h)
    log("wrote", os.path.join(OUT, label + ".png"), f"{time.time() - STATE['t0']:.1f}s")


def tick(dt):
    i = STATE["i"]
    if i >= len(SHOTS):
        unreal.unregister_slate_post_tick_callback(STATE["handle"])
        log("done")
        if QUIT:
            unreal.SystemLibrary.quit_editor()
        return
    label = SHOTS[i]
    if STATE["frame"] == 0:
        STATE["t0"] = time.time()
        if not setup(label):
            STATE["i"] += 1
            return
    STATE["frame"] += 1
    # capture_every_frame only keeps ticking for the first capture of the session (later ones export all-black
    # frames), so drive every capture explicitly each frame.
    for cap, _ in STATE["caps"]:
        cap.capture_component2d.capture_scene()
    if STATE["frame"] >= WARM and (STATE["i"] > 0 or (time.time() - T_START >= WARM_S and compile_quiet())):
        if STATE["i"] == 0:
            log("compile quiet after", f"{time.time() - T_START:.0f}s", "build lines seen", _LOG["n"])
        finish(label)
        STATE["frame"] = 0
        STATE["i"] += 1


log("start", SHOTS, OUT, f"{W}x{H}", "warm", WARM, "world", ues.get_editor_world().get_path_name(), "actors", len(actors()))
if os.environ.get("ANYSCENE_MAP"):
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(os.environ["ANYSCENE_MAP"])
    log("loaded", ues.get_editor_world().get_path_name(), len(actors()), [a.get_actor_label() for a in actors()][:8])
if os.environ.get("ANYSCENE_REREGISTER", "0") == "1":  # debugging aid; did not fix invisible props (async compile did)
    reregister_meshes()
STATE["handle"] = unreal.register_slate_post_tick_callback(tick)
