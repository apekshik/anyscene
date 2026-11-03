#!/usr/bin/env bash
# Scene-specific driver for the caustics chamber (AnySceneCaustic project). Stages: export, cycles, build, mrq, sbs.
#   bash run_chamber.sh build mrq sbs
set -e
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && (pwd -W 2>/dev/null || pwd))"
R=C:/Users/apek-anna/Developer/anyscene-unreal
W=$R/caustic
EXP=$W/export
B="C:/Program Files/Blender Foundation/Blender 5.0/blender.exe"
UE="C:/Program Files/Epic Games/UE_5.8/Engine/Binaries/Win64/UnrealEditor-Cmd.exe"
PROJ=$R/AnySceneCaustic/AnySceneCaustic.uproject
CAMS=hero_axial,hero_lounge,pv_bench_wall
FF="C:/Users/apek-anna/AppData/Local/CapCut/Apps/9.5.0.4050/ffmpeg.exe"
for st in "$@"; do
  t0=$(date +%s)
  case $st in
    export) bash "$(dirname "$0")/export.sh" "$W/work/chamber_copy.blend" "$EXP" --gpu --frame 60 ;;
    merge)  "$B" -b "$W/work/chamber_copy.blend" --python "$HERE/export_blend.py" -- --out "$EXP" --frame 60 --no-bake > "$W/export_merge.log" 2>&1
            grep "^EXPORT wrote\|EXPORT gobo" "$W/export_merge.log" ;;
    cycles) "$B" -b "$W/work/chamber_copy.blend" --python "$HERE/render_cycles_refs.py" -- --out "$W/cycles" --cams $CAMS \
              --frame 60 --res 1920x804 --spp 128 --gpu --dolly hero_axial:150:96 --dolly-res 960x402 --dolly-spp 24 > "$W/cycles.log" 2>&1
            grep "^REF\|^DOLLY 96" "$W/cycles.log" ;;
    build)  ANYSCENE_EXPORT=$EXP ANYSCENE_DEST=/Game/AnyScene/Chamber ANYSCENE_LEVEL=L_Chamber ANYSCENE_HERO=hero_axial \
            ANYSCENE_MRQ_RES=1920x804 ANYSCENE_MESH_BATCH=8 ANYSCENE_DOLLY="hero_axial>fwd150:96:dolly_axial" \
              "$UE" "$PROJ" -run=pythonscript -script="$HERE/build_level.py" -unattended -nosplash -nop4 -log=build.log > "$W/build_ue.log" 2>&1
            grep "ANYSCENE" "$W/build_ue.log" | grep -v LogInit | tail -25 ;;
    mrq)    powershell -NoProfile -File "$HERE/render_mrq.ps1" -Cams $CAMS -Config MRQ_Still
            powershell -NoProfile -File "$HERE/render_mrq.ps1" -Cams $CAMS -Config MRQ_Linear ;;
    clip)   powershell -NoProfile -File "$HERE/render_mrq.ps1" -Cams dolly_axial -Config MRQ_Clip ;;
    *) echo "unknown stage $st"; exit 1 ;;
  esac
  echo "STAGE $st $(( $(date +%s) - t0 ))s"
done
