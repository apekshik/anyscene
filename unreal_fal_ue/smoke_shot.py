"""Smoke render for the fal UE worker: a lit cube in an empty level, captured with a SceneCapture2D (no viewport needed),
written to $ANYSCENE_SMOKE_OUT/smoke.png, then the editor quits. Run inside a windowless editor:

  UnrealEditor <project> "-ExecCmds=py <path>/smoke_shot.py" -RenderOffscreen -unattended -nosplash -nop4 -nosound
"""
import os
import warnings

import unreal

warnings.simplefilter("ignore", DeprecationWarning)

OUT = os.environ.get("ANYSCENE_SMOKE_OUT", "/tmp/anyscene/smoke")
FRAMES = int(os.environ.get("ANYSCENE_SMOKE_FRAMES", "120"))
os.makedirs(OUT, exist_ok=True)

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
world = ues.get_editor_world()

cube = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 50), unreal.Rotator(0, 0, 30))
cube.static_mesh_component.set_static_mesh(unreal.load_asset("/Engine/BasicShapes/Cube.Cube"))
floor = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
floor.static_mesh_component.set_static_mesh(unreal.load_asset("/Engine/BasicShapes/Plane.Plane"))
floor.set_actor_scale3d(unreal.Vector(20, 20, 1))
sun = eas.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 500), unreal.Rotator(0, -40, 30))
eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 300))
eas.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0))

rt = unreal.RenderingLibrary.create_render_target2d(world, 640, 360, unreal.TextureRenderTargetFormat.RTF_RGBA8_SRGB)
cap = eas.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(-400, -250, 250), unreal.Rotator(0, -25, 32))
c = cap.capture_component2d
c.set_editor_property("texture_target", rt)
c.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_TONE_CURVE_HDR)
STATE = {"n": 0, "h": None}


def tick(dt):
    STATE["n"] += 1
    c.capture_scene()
    if STATE["n"] < FRAMES:
        return
    unreal.unregister_slate_post_tick_callback(STATE["h"])
    unreal.RenderingLibrary.export_render_target(world, rt, OUT, "smoke.png")
    unreal.log_warning("SMOKE wrote " + os.path.join(OUT, "smoke.png"))
    unreal.SystemLibrary.quit_editor()


STATE["h"] = unreal.register_slate_post_tick_callback(tick)
