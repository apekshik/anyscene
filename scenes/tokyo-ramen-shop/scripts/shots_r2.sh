#!/usr/bin/env bash
# Final camrig renders, 24-frame chunks per GPU-queue call; then my grade/vignette/grain pass → <shot>_graded.mp4.
cd "$(dirname "$0")/../../.."
. pipeline/env.sh

J=$ROOT_ABS/scenes/tokyo-ramen-shop/shots.json
O=$ROOT_ABS/scenes/tokyo-ramen-shop/out/shots
for spec in ${SHOTS:-bowl_insert:96 stockpot_insert:120 lantern_rain:96 exterior_establish:120 counter_push:120 door_dolly_zoom:96}; do
  s=${spec%%:*}; n=${spec##*:}
  for ((a=1; a<=n; a+=24)); do
    b=$((a+23)); [ $b -gt $n ] && b=$n
    bash pipeline/gpu_run.sh "$B" -b scenes/tokyo-ramen-shop/ramen_r2.blend --python scenes/tokyo-ramen-shop/scripts/gpu_prefs.py --python camera/shoot.py -- --shots $J --out $O --only $s --frames $a-$b 2>&1 | grep -E "camrig: (final|$s)|Error:|Traceback" | grep -v "Not freed"
  done
  bash scenes/tokyo-ramen-shop/scripts/finish.sh clip "scenes/tokyo-ramen-shop/out/shots/$s/frames/%04d.png" "scenes/tokyo-ramen-shop/out/shots/$s/${s}_graded.mp4" && echo "GRADED $s"
done
