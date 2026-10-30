#!/usr/bin/env bash
# camrig through the GPU queue with OptiX enabled.  scenes/tokyo-electronics-repair/scripts/shoot.sh [shoot.py args...]
cd "$(dirname "$0")/../../.."
. pipeline/env.sh
bash pipeline/gpu_run.sh "$B" -b ${BLEND:-scenes/tokyo-electronics-repair/repair_final.blend} \
  --python scenes/tokyo-electronics-repair/scripts/gpu_prefs.py --python camera/shoot.py -- \
  --shots $ROOT_ABS/scenes/tokyo-electronics-repair/shots.json \
  --out $ROOT_ABS/scenes/tokyo-electronics-repair/out/shots "$@"
