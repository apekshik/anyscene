#!/usr/bin/env bash
# Every Blender run for this scene goes through here: shared GPU queue, GPU prefs first.
#   bash scenes/hk-dai-pai-dong/scripts/blend.sh [file.blend] --python script.py -- args...
#   bash scenes/hk-dai-pai-dong/scripts/blend.sh build -- --stages shell --preview street --clay
cd "$(dirname "$0")/../../.."
. pipeline/env.sh
S="$ANYSCENE_ROOT/scenes/hk-dai-pai-dong/scripts"
if [ "$1" = "build" ]; then
  shift
  exec bash pipeline/gpu_run.sh "$BLENDER" -b --factory-startup --python "$S/gpu_prefs.py" --python "$S/build.py" "$@"
fi
F="$1"; shift
exec bash pipeline/gpu_run.sh "$BLENDER" -b "$F" --python "$S/gpu_prefs.py" "$@"
