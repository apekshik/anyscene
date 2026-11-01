#!/usr/bin/env bash
# camrig through the GPU queue with OptiX enabled.  scenes/mission-control-1970s/scripts/shoot.sh [shoot.py args...]
cd "$(dirname "$0")/../../.."
. pipeline/env.sh
bash pipeline/gpu_run.sh "$B" -b ${BLEND:-scenes/mission-control-1970s/mc.blend} \
  --python scenes/mission-control-1970s/scripts/gpu_prefs.py ${NOCURL:+--python scenes/mission-control-1970s/scripts/nocurl.py} --python camera/shoot.py -- \
  --shots $ROOT_ABS/scenes/mission-control-1970s/shots.json \
  --out $ROOT_ABS/scenes/mission-control-1970s/out/shots "$@"
