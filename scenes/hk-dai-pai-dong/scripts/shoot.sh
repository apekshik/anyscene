#!/usr/bin/env bash
# camrig on hk.blend through the GPU queue with OptiX on.  bash scenes/hk-dai-pai-dong/scripts/shoot.sh [shoot.py args...]
cd "$(dirname "$0")/../../.."
. pipeline/env.sh
bash pipeline/gpu_run.sh "$BLENDER" -b ${BLEND:-scenes/hk-dai-pai-dong/hk.blend} \
  --python scenes/hk-dai-pai-dong/scripts/gpu_prefs.py --python camera/shoot.py -- \
  --shots $ANYSCENE_ROOT/scenes/hk-dai-pai-dong/shots.json --out $ANYSCENE_ROOT/scenes/hk-dai-pai-dong/out/shots "$@"
