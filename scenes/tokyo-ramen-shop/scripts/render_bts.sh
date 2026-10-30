#!/usr/bin/env bash
# Ramen BTS dollhouse clips (breakdown/SPEC.md). Every Blender run is its own pipeline/gpu_run.sh call (GPU released between).
#   bash scenes/tokyo-ramen-shop/scripts/render_bts.sh > logs/ramen_bts.log 2>&1
cd "$(dirname "$0")/../../.."
. pipeline/env.sh

R=breakdown/tokyo-ramen-shop
CL=$R/clips
WK=$R/work
run() { local t0=$(date +%s); bash pipeline/gpu_run.sh "$B" -b "$1" --python scenes/tokyo-ramen-shop/scripts/gpu_prefs.py --python scenes/tokyo-ramen-shop/scripts/bts.py -- "${@:2}" 2>&1 | grep -E "BTS rendered|Error:|Traceback|line [0-9]"; echo "GPU $(( $(date +%s)-t0 ))s: ${*:2}"; }
mp4() { "$FF" -v error -y -framerate 24 -i "$CL/$1/%04d.png" -c:v h264_nvenc -preset p7 -rc vbr -cq 16 -b:v 0 -pix_fmt yuv420p "$CL/$1.mp4" && echo "MP4 $1 $(ls $CL/$1 | wc -l) frames"; }

# No-grime twin of the scene for c_materials (same build, grime overlays stubbed out, no steam).
if [ ! -f $R/plain.blend ]; then
  bash pipeline/gpu_run.sh "$B" -b --factory-startup --python-expr "
import sys; sys.path.insert(0, __import__('os').environ['ANYSCENE_ROOT'] + '/scenes/tokyo-ramen-shop/scripts')
import grime; grime.overlay = lambda *a, **k: None; grime.build = lambda: None" \
    --python scenes/tokyo-ramen-shop/scripts/build.py -- --stages shell,dress,passA,passB,passC,grime,r2gen,light,post --blend ../../breakdown/tokyo-ramen-shop/plain.blend --save 2>&1 | grep -E "saved|Error|Traceback"
fi

run $R/bts.blend a_layout && mp4 a_layout
run $R/bts.blend b_props && mp4 b_props

run $R/bts.blend c_materials --pass clay --frames 1-48 --out $WK/c_clay
run $R/plain.blend c_materials --pass plain --frames 1-96 --out $WK/c_plain
run $R/bts.blend c_materials --pass full --frames 49-144 --out $WK/c_full
rm -rf $CL/c_materials $WK/c_seg; mkdir -p $CL/c_materials $WK/c_seg
"$FF" -v error -y -framerate 24 -start_number 1 -i $WK/c_clay/%04d.png -framerate 24 -start_number 1 -i $WK/c_plain/%04d.png \
  -filter_complex "[0][1]xfade=transition=wiperight:duration=2:offset=0,format=rgb24" -frames:v 48 -start_number 1 $WK/c_seg/a%04d.png
"$FF" -v error -y -framerate 24 -start_number 49 -i $WK/c_plain/%04d.png -framerate 24 -start_number 49 -i $WK/c_full/%04d.png \
  -filter_complex "[0][1]xfade=transition=fade:duration=2:offset=0,format=rgb24" -frames:v 48 -start_number 1 $WK/c_seg/b%04d.png
i=1
for f in $WK/c_seg/a*.png $WK/c_seg/b*.png $(for n in $(seq 97 144); do printf "$WK/c_full/%04d.png " $n; done); do
  cp "$f" $CL/c_materials/$(printf %04d $i).png; i=$((i+1))
done
mp4 c_materials

for r in 1-60 61-120 121-180 181-240; do run $R/bts.blend d_lighting --frames $r --samples 12; done
mp4 d_lighting
echo BTS_DONE
