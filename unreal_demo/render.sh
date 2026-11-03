#!/usr/bin/env bash
# Headless MRQ render of demo sequences (no editor window), one UE process per shot (GPU_QUEUE=1: through pipeline/gpu_run.sh).
#   bash unreal_demo/render.sh s1_street_crane,h1_walk_in_to_wok [MRQ_Demo|MRQ_DemoCheck]
# Frames: unreal_demo/mrq/SEQ_<shot>/####.png (0-based, = Blender frame - 1). Log: unreal_demo/logs/mrq_<shot>.log
export MSYS_NO_PATHCONV=1
A="$(cd "$(dirname "$0")/.." && pwd)"
UE="/c/Program Files/Epic Games/UE_5.8/Engine/Binaries/Win64/UnrealEditor-Cmd.exe"
PROJ="C:/Users/apek-anna/Developer/anyscene-unreal/AnySceneHKDemo/AnySceneHKDemo.uproject"
CFG=${2:-MRQ_Demo}
mkdir -p "$A/unreal_demo/logs"
IFS=, read -ra SHOTS <<< "$1"
for s in "${SHOTS[@]}"; do
  t0=$(date +%s)
  ${GPU_QUEUE:+bash "$A/pipeline/gpu_run.sh"} "$UE" "$PROJ" /Game/AnyScene/HK/L_HK -game \
    "-LevelSequence=/Game/AnySceneDemo/Sequences/SEQ_$s.SEQ_$s" \
    "-MoviePipelineConfig=/Game/AnySceneDemo/MRQ/$CFG.$CFG" \
    -RenderOffscreen -windowed -resx=1920 -resy=804 -unattended -nosplash -nop4 -nosound -notexturestreaming \
    "-dpcvars=Editor.AsyncAssetCompilation=0,Editor.AsyncTextureCompilation=0,Editor.AsyncStaticMeshCompilation=0,fx.Niagara.ForceWaitForCompilationOnActivate=1,r.TextureStreaming=0" \
    "-abslog=$(cd "$A" && pwd -W)/unreal_demo/logs/mrq_${s}_$CFG.log" > /dev/null 2>&1
  rc=$?
  echo "RENDER $s $CFG rc=$rc $(( $(date +%s) - t0 ))s"
done
