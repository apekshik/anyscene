#!/usr/bin/env bash
# Render the handheld clip in 20-frame chunks, each holding the GPU lock only for its chunk, then grade + encode.
cd "$(dirname "$0")/../../.."
. pipeline/env.sh

for s in 1 21 41 61 81 101; do
  t0=$(date +%s)
  bash pipeline/gpu_run.sh "$B" -b scenes/tokyo-electronics-repair/repair_final.blend --python scenes/tokyo-electronics-repair/scripts/render_frames.py -- $s $((s + 19)) ${1:-64} 100 2>&1 | grep -E "Error|Traceback"
  echo "chunk $s done in $(( $(date +%s) - t0 )) s"
  sleep 8  # let a waiting render from the other scene take the lock
done
bash scenes/tokyo-electronics-repair/scripts/grade.sh clip scenes/tokyo-electronics-repair/out/clip_frames scenes/tokyo-electronics-repair/out/clip.mp4 && echo "clip encoded"
