#!/usr/bin/env bash
# Build ramen.blend (CPU, no GPU lock needed), bake steam (CPU), then optional GPU preview via the queue.
#   scenes/tokyo-ramen-shop/scripts/rebuild.sh [preview cams] [tag] [samples]
cd "$(dirname "$0")/../../.."
. pipeline/env.sh

"$B" -b --factory-startup --python scenes/tokyo-ramen-shop/scripts/build.py -- --samples 256 --save --final 2>&1 | grep -E "VALIDATE|^   |Error|Traceback|line [0-9]|saved|MISSING"
"$B" -b scenes/tokyo-ramen-shop/ramen_r2.blend --python scenes/tokyo-ramen-shop/scripts/bake_steam.py 2>&1 | grep -E "BAKE|Error|Traceback|SAVED"
if [ -n "$1" ]; then
  bash pipeline/gpu_run.sh "$B" -b scenes/tokyo-ramen-shop/ramen_r2.blend --python scenes/tokyo-ramen-shop/scripts/gpu_prefs.py --python scenes/tokyo-ramen-shop/scripts/render.py -- prev "$1" --tag "${2:-_x}" --samples "${3:-48}" 2>&1 | grep -E "STILL|Error|Traceback"
fi
