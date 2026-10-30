#!/usr/bin/env bash
# Final Cycles renders for round 2, back to back through the GPU queue, after the ramen scene is done
# (waits for .gpu.ramen_done, or 16:30 local time at the latest).
cd "$(dirname "$0")/../../.."
. pipeline/env.sh
until [ -e .gpu.ramen_done ] || [ "$(date +%H%M)" -ge 1630 ]; do sleep 60; done
echo "start $(date +%H:%M) (ramen_done: $([ -e .gpu.ramen_done ] && echo yes || echo no, 16:30 fallback))"

for cam in cam_wide cam_bench; do
  bash pipeline/gpu_run.sh "$B" -b scenes/tokyo-electronics-repair/repair_final.blend --python scenes/tokyo-electronics-repair/scripts/preview.py -- scenes/tokyo-electronics-repair/out/raw $cam 384 100 full 2>&1 | grep -E "Traceback|wrote"
  bash scenes/tokyo-electronics-repair/scripts/grade.sh still scenes/tokyo-electronics-repair/out/raw/$cam.png scenes/tokyo-electronics-repair/out/hero_${cam#cam_}.png
done
echo "heroes done $(date +%H:%M)"
for s in s3_bench_rack_100 s4_scope_135_push s6_bench_dolly_zoom s2_shop_wide_drift s1_street_establish; do
  rm -rf scenes/tokyo-electronics-repair/out/shots/$s/frames scenes/tokyo-electronics-repair/out/shots/$s/$s.mp4 scenes/tokyo-electronics-repair/out/shots/$s/contact.png scenes/tokyo-electronics-repair/out/shots/${s}_graded.mp4
done
SHOTS="s3_bench_rack_100 s4_scope_135_push s6_bench_dolly_zoom s2_shop_wide_drift s1_street_establish" bash scenes/tokyo-electronics-repair/scripts/render_round2.sh
echo "finals done $(date +%H:%M)"
