#!/usr/bin/env bash
# Dai pai dong dollhouse clips (breakdown/SPEC.md). Every Blender run is its own pipeline/gpu_run.sh call.
#   bash scenes/hk-dai-pai-dong/scripts/render_bts.sh > logs/hk_bts.log 2>&1
cd "$(dirname "$0")/../../.."
. pipeline/env.sh
FF="$FFMPEG"
SC=scenes/hk-dai-pai-dong
R=breakdown/hk-dai-pai-dong
CL=$R/clips
WK=$R/work
S=$ANYSCENE_ROOT/$SC/scripts
run() { local t0=$(date +%s); bash pipeline/gpu_run.sh "$BLENDER" -b "$1" --python $S/gpu_prefs.py --python $S/bts.py -- "${@:2}" 2>&1 | grep -E "BTS rendered|Error:|Traceback|line [0-9]"; echo "GPU $(( $(date +%s)-t0 ))s: ${*:2}"; }
mp4() { "$FF" -v error -y -framerate 24 -start_number 1 -i "$CL/$1/%04d.png" -c:v h264_nvenc -preset p7 -rc vbr -cq 16 -b:v 0 -pix_fmt yuv420p "$CL/$1.mp4" && echo "MP4 $1 $(ls $CL/$1 | wc -l) frames"; }

# No-grime twin of the scene for c_materials (same build without the grime stage). Saved under breakdown/, never over hk.blend.
if [ ! -f $R/plain.blend ]; then
  bash pipeline/gpu_run.sh "$BLENDER" -b --factory-startup --python $S/gpu_prefs.py --python $S/build.py -- \
    --stages shell,dress,light,fx,post --save --out ../../$R/plain.blend 2>&1 | grep -E "SAVED|Error|Traceback"
fi

run $SC/hk.blend a_layout && mp4 a_layout
for r in 1-120 121-240; do run $SC/hk.blend b_props --frames $r; done; mp4 b_props

run $SC/hk.blend c_materials --pass clay --frames 1-48 --out $ANYSCENE_ROOT/$WK/c_clay
run $R/plain.blend c_materials --pass plain --frames 1-96 --out $ANYSCENE_ROOT/$WK/c_plain
run $SC/hk.blend c_materials --pass full --frames 49-144 --out $ANYSCENE_ROOT/$WK/c_full
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

for r in 1-48 49-96 97-144 145-192 193-240; do run $SC/hk.blend d_lighting --frames $r --samples 16; done
mp4 d_lighting
echo BTS_DONE
