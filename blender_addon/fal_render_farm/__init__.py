"""fal Render Farm: render the open scene on a fal Serverless Blender farm (farm/app.py, deployed on your own fal account) instead of the local GPU.

Properties > Render > fal Render Farm. The open file is copied (never re-saved), packed in a separate Blender, zipped
with a GPU script, uploaded to fal storage and rendered in chunks on up to N GPUs. Frames come back into the scene's
own output path with the names a local render would give them. Talks to fal over plain HTTPS (urllib) only.
"""

bl_info = {
    "name": "fal Render Farm",
    "author": "AnyScene contributors",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "Properties > Render > fal Render Farm",
    "description": "Render the open scene on a fal Serverless GPU render farm",
    "category": "Render",
}

import os
import time

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty

from . import fal_api, job as farm_job

PKG = __package__


def prefs():
    return bpy.context.preferences.addons[PKG].preferences


class FALRF_Preferences(bpy.types.AddonPreferences):
    bl_idname = PKG

    fal_key: StringProperty(
        name="fal key", subtype="PASSWORD", default="",
        description="fal API key of the account that owns the farm app (key_id:key_secret). Stored in Blender's "
                    "preferences; never printed or logged")
    app_id: StringProperty(
        name="Farm app", default="",
        description="fal app id of your render farm, <your-fal-username>/blender-farm-2 (farm/app.py deployed on your "
                    "account). An app deployed as blender-farm (the older build) returns PNG frames only; "
                    "blender-farm-2 also returns EXR, JPEG, TIFF and other image formats")
    chunk_size: IntProperty(name="Frames per chunk", default=24, min=1, max=1000,
                            description="Frames rendered by one farm request (one GPU)")
    concurrency: IntProperty(name="Concurrent chunks", default=100, min=1, max=200,
                             description="Requests in flight at once (the farm caps at its own max workers)")
    timeout_s: IntProperty(name="Chunk timeout (s)", default=3000, min=60, max=3500,
                           description="The farm kills Blender after this long on one chunk")
    encode_mp4: BoolProperty(name="Encode MP4 when done", default=True,
                             description="After an animation finishes, encode the frames to an H.264 MP4 next to "
                                         "them if ffmpeg is found (PNG/JPEG/TIFF/... frames only)")
    ffmpeg_path: StringProperty(name="ffmpeg", subtype="FILE_PATH", default="",
                                description="Path to ffmpeg; empty = look it up on PATH")

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "fal_key")
        col.prop(self, "app_id")
        row = col.row()
        row.prop(self, "chunk_size")
        row.prop(self, "concurrency")
        col.prop(self, "timeout_s")
        row = col.row()
        row.prop(self, "encode_mp4")
        row.prop(self, "ffmpeg_path", text="")
        col.operator(FALRF_OT_check_key.bl_idname, icon="KEY_HLT")


# -- operators --------------------------------------------------------------------------------------------------

def _busy():
    j = farm_job.CURRENT
    return j is not None and j.running


class FALRF_OT_render(bpy.types.Operator):
    """Render on the fal render farm instead of the local GPU"""

    bl_idname = "fal_render_farm.render"
    bl_label = "Render on fal"
    bl_options = {"REGISTER"}

    mode: bpy.props.EnumProperty(items=[("ANIMATION", "Animation", "The scene's frame range"),
                                        ("FRAME", "Frame", "The current frame")], default="ANIMATION")

    @classmethod
    def poll(cls, context):
        if _busy():
            cls.poll_message_set("A farm render is already running")
            return False
        if context.scene is None:
            return False
        return True

    @classmethod
    def description(cls, context, props):
        if props.mode == "FRAME":
            return "Render the current frame on the fal render farm; it is saved to the output path"
        return "Render the scene's frame range on the fal render farm, into the output path"

    def execute(self, context):
        try:
            p = farm_job.plan(context, self.mode, prefs())
            farm_job.save_copy(p)
        except farm_job.PlanError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        farm_job.CURRENT = farm_job.Job(p).start()
        _start_ui_timer()
        self.report({"INFO"}, f"fal render farm: {len(p.frames)} frame(s) of '{p.scene_name}' on {p.app}")
        return {"FINISHED"}


class FALRF_OT_cancel(bpy.types.Operator):
    """Cancel the running farm render (in-flight chunks are cancelled on fal; finished frames stay on disk)"""

    bl_idname = "fal_render_farm.cancel"
    bl_label = "Cancel"

    @classmethod
    def poll(cls, context):
        return _busy()

    def execute(self, context):
        farm_job.CURRENT.cancel()
        return {"FINISHED"}


class FALRF_OT_retry(bpy.types.Operator):
    """Re-submit the chunks that failed, reusing the uploaded bundle"""

    bl_idname = "fal_render_farm.retry"
    bl_label = "Retry failed chunks"

    @classmethod
    def poll(cls, context):
        j = farm_job.CURRENT
        return j is not None and not j.running and j.bundle_url and any(
            c.status in ("failed", "cancelled") for c in j.chunks)

    def execute(self, context):
        if farm_job.CURRENT.retry_failed():
            _start_ui_timer()
        return {"FINISHED"}


class FALRF_OT_check_key(bpy.types.Operator):
    """Check that fal accepts the key (a status read on the farm app; nothing is rendered)"""

    bl_idname = "fal_render_farm.check_key"
    bl_label = "Check key"

    def execute(self, context):
        pr = prefs()
        if not pr.fal_key.strip():
            self.report({"ERROR"}, "No key set")
            return {"CANCELLED"}
        if not pr.app_id.strip().strip("/"):
            self.report({"ERROR"}, farm_job.NO_APP_MSG)
            return {"CANCELLED"}
        ok, msg = fal_api.check_key(pr.fal_key.strip(), pr.app_id)
        self.report({"INFO"} if ok else {"ERROR"}, msg)
        return {"FINISHED"} if ok else {"CANCELLED"}


class FALRF_OT_open_output(bpy.types.Operator):
    """Open the folder the frames are written to"""

    bl_idname = "fal_render_farm.open_output"
    bl_label = "Open output folder"

    def execute(self, context):
        path = bpy.path.abspath(context.scene.render.frame_path(frame=context.scene.frame_start))
        folder = os.path.dirname(os.path.abspath(path))
        os.makedirs(folder, exist_ok=True)
        bpy.ops.wm.path_open(filepath=folder)
        return {"FINISHED"}


# -- panel ------------------------------------------------------------------------------------------------------

def _progress_text(s):
    c = s["counts"]
    done = c.get("done", 0)
    parts = [f"{done}/{s['n_chunks']} chunks", f"{s['frames_done']}/{s['frames_total']} frames",
             farm_job.fmt_s(s["elapsed"])]
    if s["gpu_s"]:
        parts.append(f"{s['gpu_s']:.0f} GPU-s (~${s['gpu_s'] / 3600 * farm_job.GPU_RATE_PER_HOUR:.2f})")
    return " · ".join(parts)


class FALRF_PT_panel(bpy.types.Panel):
    bl_label = "fal Render Farm"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "render"

    def draw_header(self, context):
        self.layout.label(icon="WORLD")

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        pr = prefs()

        frames = farm_job.frame_list(scene, "ANIMATION")
        est = farm_job.estimate(scene, len(frames), pr.chunk_size, pr.concurrency)
        samples, unit = farm_job.samples_of(scene)
        r = scene.render
        w = int(r.resolution_x * r.resolution_percentage / 100)
        h = int(r.resolution_y * r.resolution_percentage / 100)

        box = layout.box()
        col = box.column(align=True)
        col.label(text=f"Frames {scene.frame_start}-{scene.frame_end}"
                       + (f" step {scene.frame_step}" if scene.frame_step > 1 else "")
                       + f": {len(frames)} · {est['chunks']} chunks of {pr.chunk_size}", icon="RENDER_ANIMATION")
        col.label(text=f"{w}x{h}" + (f" · {samples} {unit}" if samples else "")
                       + f" · {r.engine.replace('BLENDER_', '').title()} · {r.image_settings.file_format}")
        lo, hi = est["cost"], est["wall"]
        col.label(text=f"Estimate: ${lo[0]:.2f}-{lo[1]:.2f} · {farm_job.fmt_s(est['gpu_s'][0])}-"
                       f"{farm_job.fmt_s(est['gpu_s'][1])} of GPU time", icon="INFO")
        col.label(text=f"   ~{farm_job.fmt_s(hi[0])}-{farm_job.fmt_s(hi[1])} wall at {pr.concurrency} GPUs, "
                       f"+ ~{farm_job.fmt_s(est['cold_start'])} cold start")
        col.label(text=f"   {est['sec_per_frame'][0]:.1f}-{est['sec_per_frame'][1]:.1f} s/frame, "
                       f"${farm_job.GPU_RATE_PER_HOUR:.2f}/GPU-h (RTX PRO 6000); an estimate")

        if not pr.fal_key.strip():
            layout.label(text="Set your fal key in the add-on preferences", icon="ERROR")
        if not pr.app_id.strip().strip("/"):
            layout.label(text="Set the farm app (<your-fal-username>/blender-farm-2) below", icon="ERROR")
        if r.image_settings.file_format != "PNG" and pr.app_id.strip().strip("/").endswith("/blender-farm"):
            layout.label(text=f"{pr.app_id} returns PNG only; use a blender-farm-2 deployment for "
                              f"{r.image_settings.file_format}", icon="ERROR")
        if r.image_settings.file_format == "FFMPEG":
            layout.label(text="Video output: pick an image format (MP4 is encoded after)", icon="ERROR")

        row = layout.row(align=True)
        row.scale_y = 1.4
        row.operator(FALRF_OT_render.bl_idname, text="Render animation on fal", icon="RENDER_ANIMATION").mode = "ANIMATION"
        row = layout.row(align=True)
        row.operator(FALRF_OT_render.bl_idname, text="Render this frame on fal", icon="RENDER_STILL").mode = "FRAME"
        row.operator(FALRF_OT_cancel.bl_idname, text="Cancel", icon="CANCEL")

        sub = layout.column(align=True)
        sub.prop(pr, "app_id")
        row = sub.row(align=True)
        row.prop(pr, "chunk_size", text="Chunk")
        row.prop(pr, "concurrency", text="GPUs")
        sub.prop(pr, "encode_mp4")
        layout.label(text="Output: " + (r.filepath or "(blend file folder)"), icon="FILE_FOLDER")

        j = farm_job.CURRENT
        if j is None:
            return
        s = j.snapshot()
        box = layout.box()
        icon = {"done": "CHECKMARK", "failed": "ERROR", "cancelled": "CANCEL"}.get(s["phase"], "SORTTIME")
        box.label(text=f"{s['phase'].title()} · {s['app']}", icon=icon)
        if s["n_chunks"]:
            box.progress(factor=s["frames_done"] / max(1, s["frames_total"]), text=_progress_text(s))
            c = s["counts"]
            box.label(text=f"queued {c.get('queued', 0) + c.get('pending', 0)} · rendering {c.get('rendering', 0)} "
                           f"· downloading {c.get('downloading', 0)} · done {c.get('done', 0)} "
                           f"· failed {c.get('failed', 0)}" + (f" · {s['skipped']} frames already on disk"
                                                                if s["skipped"] else ""))
        if s["message"]:
            box.label(text=s["message"][:160])
        for label, err in s["failed"][:8]:
            box.label(text=f"chunk {label}: {err[:140]}", icon="ERROR")
        if s["mp4"]:
            box.label(text=f"MP4: {s['mp4']}", icon="FILE_MOVIE")
        row = box.row()
        row.operator(FALRF_OT_retry.bl_idname, icon="FILE_REFRESH")
        row.operator(FALRF_OT_open_output.bl_idname, icon="FILE_FOLDER")


def draw_status(self, context):
    j = farm_job.CURRENT
    if j is None or (not j.running and j.finished_seen and time.time() - (j.t_end or 0) > 30):
        return
    s = j.snapshot()
    text = f"fal farm: {s['phase']}"
    if s["n_chunks"]:
        text += " · " + _progress_text(s)
    self.layout.separator()
    self.layout.label(text=text, icon="WORLD")


# -- UI timer: redraws while a job runs, then reacts once to its end --------------------------------------------

def _redraw():
    wm = bpy.context.window_manager
    if wm is None:
        return
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type in ("PROPERTIES", "STATUSBAR"):
                area.tag_redraw()


def _tick():
    j = farm_job.CURRENT
    if j is None:
        return None
    try:
        _redraw()
    except Exception:  # noqa: BLE001 - never let a redraw problem kill the timer
        pass
    if j.running:
        return 0.5
    if not j.finished_seen:
        j.finished_seen = True
        if j.p.mode == "FRAME" and j.phase == "done":
            _show_frame(j)
    return None


def _show_frame(j):
    path = j.p.targets[j.p.frames[0]]
    if not os.path.exists(path):
        return
    img = bpy.data.images.load(path, check_existing=True)
    img.reload()
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == "IMAGE_EDITOR":
                area.spaces.active.image = img
                area.tag_redraw()
                return


def _start_ui_timer():
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=0.5, persistent=True)


classes = (FALRF_Preferences, FALRF_OT_render, FALRF_OT_cancel, FALRF_OT_retry, FALRF_OT_check_key,
           FALRF_OT_open_output, FALRF_PT_panel)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.STATUSBAR_HT_header.append(draw_status)


def unregister():
    if farm_job.CURRENT is not None and farm_job.CURRENT.running:
        farm_job.CURRENT.cancel()
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    bpy.types.STATUSBAR_HT_header.remove(draw_status)
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
