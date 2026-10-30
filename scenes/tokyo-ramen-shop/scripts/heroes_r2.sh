#!/usr/bin/env bash
cd "$(dirname "$0")/../../.."
. pipeline/env.sh

for k in ${HEROES:-wide counter}; do
  bash pipeline/gpu_run.sh "$B" -b scenes/tokyo-ramen-shop/ramen_r2.blend --python scenes/tokyo-ramen-shop/scripts/gpu_prefs.py --python scenes/tokyo-ramen-shop/scripts/render.py -- stills $k --samples 320 2>&1 | grep -E "STILL|Error|Traceback"
  bash scenes/tokyo-ramen-shop/scripts/finish.sh still scenes/tokyo-ramen-shop/out/raw/hero_$k.png scenes/tokyo-ramen-shop/out/hero_$k.png && echo "FINISHED $k"
done
