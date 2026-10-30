#!/usr/bin/env bash
# Render the four BTS dollhouse clips in short GPU-queue chunks, build the C wipe, encode mp4s and contact sheets.
cd "$(dirname "$0")/../../.."
. pipeline/env.sh

C=breakdown/tokyo-electronics-repair/clips
run() {  # clip first last [clay]
  local t0=$(date +%s)
  bash pipeline/gpu_run.sh "$B" -b breakdown/tokyo-electronics-repair/bts.blend --python scenes/tokyo-electronics-repair/scripts/bts.py -- "$@" 2>&1 | grep -E "Traceback|Error:" | grep -v HIPEW
  echo "$* : $(( $(date +%s) - t0 )) s"
}
for r in "1 72" "73 144"; do run a_layout $r; done
for r in "1 80" "81 160" "161 240"; do run b_props $r; done
run c_materials 1 48 clay
for r in "1 72" "73 144"; do run c_materials $r; done
for r in "1 60" "61 120" "121 180" "181 240"; do run d_lighting $r; done
# C: soft diagonal wipe clay -> materials over frames 1-48 (frame files are the source of truth; mp4 is made from them)
mkdir -p $C/c_tmp
"$FF" -v error -y -framerate 24 -i $C/c_materials_clayplate/%04d.png -framerate 24 -i $C/c_materials/%04d.png -frames:v 48 \
  -filter_complex "[0:v][1:v]blend=all_expr='A*(1-clip((N/47*1.25-(X/W*0.8+Y/H*0.2))/0.25,0,1))+B*clip((N/47*1.25-(X/W*0.8+Y/H*0.2))/0.25,0,1)'" \
  -start_number 1 $C/c_tmp/%04d.png
for f in $C/c_tmp/*.png; do mv -f "$f" $C/c_materials/; done
rmdir $C/c_tmp
for c in a_layout b_props c_materials d_lighting; do
  "$FF" -v error -y -framerate 24 -i $C/$c/%04d.png -c:v h264_nvenc -preset p7 -rc vbr -cq 16 -b:v 0 -pix_fmt yuv420p -movflags +faststart $C/$c.mp4
  n=$(ls $C/$c | wc -l)
  "$FF" -v error -y -i $C/$c.mp4 -vf "select='not(mod(n\,$(( n / 8 ))))',scale=480:-1,tile=4x2" -frames:v 1 $C/${c}_contact.png
  echo "$c: $n frames"
done
echo BTS DONE
