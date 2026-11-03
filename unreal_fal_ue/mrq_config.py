"""Per-request Movie Render Queue config: duplicate a saved config (build_level.py's MRQ_Still / MRQ_Linear) with this
request's output folder, resolution, frame range and sample counts, and stretch the camera sequences to cover the range.
build_level.py bakes the output folder relative to the export folder, which differs per worker, so /render always
writes a fresh config. Runs in a commandlet (no rendering needed):

  UnrealEditor-Cmd <project> -run=pythonscript -script=<path>/mrq_config.py -unattended -nosplash -nop4
Env: ANYSCENE_DEST, ANYSCENE_MRQ_BASE (MRQ_Still), ANYSCENE_MRQ_NAME (MRQ_Req), ANYSCENE_MRQ_OUT, ANYSCENE_MRQ_RES (WxH),
ANYSCENE_MRQ_FRAMES (start,end; end exclusive), ANYSCENE_MRQ_SAMPLES (temporal), ANYSCENE_MRQ_WARMUP (engine warm-up
frames), ANYSCENE_CAMS (comma list of camera names whose SEQ_<cam> gets its playback end extended).
"""
import os
import warnings

import unreal

warnings.simplefilter("ignore", DeprecationWarning)

DEST = os.environ.get("ANYSCENE_DEST", "/Game/AnyScene/HK")
BASE = os.environ.get("ANYSCENE_MRQ_BASE", "MRQ_Still")
NAME = os.environ.get("ANYSCENE_MRQ_NAME", "MRQ_Req")
OUT = os.environ["ANYSCENE_MRQ_OUT"]
W, H = (int(x) for x in os.environ.get("ANYSCENE_MRQ_RES", "1920x804").split("x"))
F0, F1 = (int(x) for x in os.environ.get("ANYSCENE_MRQ_FRAMES", "0,1").split(","))
SAMPLES = int(os.environ.get("ANYSCENE_MRQ_SAMPLES", "8"))
WARMUP = int(os.environ.get("ANYSCENE_MRQ_WARMUP", "64"))
CAMS = [c for c in os.environ.get("ANYSCENE_CAMS", "").split(",") if c]
EAL = unreal.EditorAssetLibrary

src = f"{DEST}/MRQ/{BASE}"
dst = f"{DEST}/MRQ/{NAME}"
if EAL.does_asset_exist(dst):
    EAL.delete_asset(dst)
cfg = EAL.duplicate_asset(src, dst)
out = cfg.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
out.output_directory = unreal.DirectoryPath(OUT)
out.output_resolution = unreal.IntPoint(W, H)
out.use_custom_playback_range = True
out.custom_start_frame, out.custom_end_frame = F0, F1
aa = cfg.find_or_add_setting_by_class(unreal.MoviePipelineAntiAliasingSetting)
aa.temporal_sample_count = SAMPLES
aa.engine_warm_up_count = WARMUP
aa.render_warm_up_frames = True
aa.use_camera_cut_for_warm_up = False
EAL.save_loaded_asset(cfg, False)

for cam in CAMS:
    sp = f"{DEST}/Sequences/SEQ_{cam}"
    seq = unreal.load_asset(sp)
    if seq is None:
        unreal.log_warning(f"MRQCFG missing sequence {sp}")
        continue
    if seq.get_playback_end() < F1:
        seq.set_playback_end(F1)
        for track in seq.get_tracks() if hasattr(seq, "get_tracks") else seq.get_master_tracks():
            if isinstance(track, unreal.MovieSceneCameraCutTrack):
                for sec in track.get_sections():
                    sec.set_range(0, F1)
        EAL.save_loaded_asset(seq, False)
unreal.log_warning(f"MRQCFG wrote {dst} out={OUT} {W}x{H} frames {F0}-{F1} samples {SAMPLES} warmup {WARMUP}")
