#!/usr/bin/env bash
# Round 2 finals: hero stills, then every shot in 48-frame GPU chunks (~7 min) (resumable), then a graded mp4 per shot.
cd "$(dirname "$0")/../../.."
. pipeline/env.sh

if false; then  # heroes rendered already; set to true to redo
  bash pipeline/gpu_run.sh "$B" -b scenes/tokyo-electronics-repair/repair_final.blend --python scenes/tokyo-electronics-repair/scripts/preview.py -- scenes/tokyo-electronics-repair/out/raw cam_wide 384 100 full 2>&1 | grep -E "Traceback|wrote"
  bash pipeline/gpu_run.sh "$B" -b scenes/tokyo-electronics-repair/repair_final.blend --python scenes/tokyo-electronics-repair/scripts/preview.py -- scenes/tokyo-electronics-repair/out/raw cam_bench 384 100 full 2>&1 | grep -E "Traceback|wrote"
  bash scenes/tokyo-electronics-repair/scripts/grade.sh still scenes/tokyo-electronics-repair/out/raw/cam_wide.png scenes/tokyo-electronics-repair/out/hero_wide.png
  bash scenes/tokyo-electronics-repair/scripts/grade.sh still scenes/tokyo-electronics-repair/out/raw/cam_bench.png scenes/tokyo-electronics-repair/out/hero_bench.png
  echo "heroes done"
fi
GRADE="curves=r='0/0.03 0.25/0.235 0.6/0.63 1/0.98':g='0/0.035 0.25/0.25 0.6/0.62 1/0.97':b='0/0.055 0.25/0.28 0.6/0.61 1/0.94',hue=s=0.88,vignette=angle=PI/4.6,noise=alls=6:allf=t+u,format=yuv420p"
for shot in ${SHOTS:-s3_bench_rack_100 s4_scope_135_push s6_bench_dolly_zoom s2_shop_wide_drift s5_counter_push s7_rack_tv_85 s1_street_establish}; do
  n=$(node -e "const j=require('./scenes/tokyo-electronics-repair/shots.json');console.log(j.shots.find(s=>s.name==='$shot').frames)")
  t0=$(date +%s)
  for a in $(seq 1 48 $n); do
    b=$((a + 47)); [ $b -gt $n ] && b=$n
    BLEND=${BLEND:-} bash scenes/tokyo-electronics-repair/scripts/shoot.sh --only $shot --frames $a-$b 2>&1 | grep -E "Traceback|Error:" | grep -v HIPEW
  done
  "$FF" -v error -y -framerate 24 -i scenes/tokyo-electronics-repair/out/shots/$shot/frames/%04d.png -vf "$GRADE" -c:v h264_nvenc -preset p7 -rc vbr -cq 18 -b:v 0 -movflags +faststart scenes/tokyo-electronics-repair/out/shots/${shot}_graded.mp4
  echo "$shot done ($n frames) in $(( ($(date +%s) - t0) / 60 )) min"
done
