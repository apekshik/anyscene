#!/usr/bin/env bash
# Render the 120-frame handheld clip in 30-frame chunks, each holding the shared GPU lock, then encode.
cd "$(dirname "$0")/../../.."
. pipeline/env.sh

for a in 1 31 61 91; do
  bash pipeline/gpu_run.sh "$B" -b scenes/tokyo-ramen-shop/ramen.blend --python scenes/tokyo-ramen-shop/scripts/gpu_prefs.py --python scenes/tokyo-ramen-shop/scripts/render.py -- clip $a $((a + 29)) --samples ${SAMPLES:-40} 2>&1 | grep -E "FRAME|Error|Traceback"
done
bash scenes/tokyo-ramen-shop/scripts/finish.sh clip "scenes/tokyo-ramen-shop/out/frames/%04d.png" scenes/tokyo-ramen-shop/out/clip.mp4 && echo ENCODED
