#!/usr/bin/env bash
# Encode the dollhouse clips (and composite c_materials) from rendered frames. No Blender.
#   bash scenes/hk-dai-pai-dong/scripts/bts_encode.sh
cd "$(dirname "$0")/../../.."
. pipeline/env.sh
R=breakdown/hk-dai-pai-dong
CL=$R/clips
WK=$R/work
mp4() { "$FF" -v error -y -framerate 24 -start_number 1 -i "$CL/$1/%04d.png" -c:v h264_nvenc -preset p7 -rc vbr -cq 16 -b:v 0 -pix_fmt yuv420p "$CL/$1.mp4" && echo "MP4 $1 $(ls $CL/$1 | wc -l) frames"; }
rm -rf $CL/c_materials $WK/c_seg; mkdir -p $CL/c_materials $WK/c_seg
"$FF" -v error -y -framerate 24 -start_number 1 -i $WK/c_clay/%04d.png -framerate 24 -start_number 1 -i $WK/c_plain/%04d.png \
  -filter_complex "[0][1]xfade=transition=wiperight:duration=2:offset=0,format=rgb24" -frames:v 48 -start_number 1 $WK/c_seg/a%04d.png
"$FF" -v error -y -framerate 24 -start_number 49 -i $WK/c_plain/%04d.png -framerate 24 -start_number 49 -i $WK/c_full/%04d.png \
  -filter_complex "[0][1]xfade=transition=fade:duration=2:offset=0,format=rgb24" -frames:v 48 -start_number 1 $WK/c_seg/b%04d.png
i=1
for f in $WK/c_seg/a*.png $WK/c_seg/b*.png $(for n in $(seq 97 144); do printf "$WK/c_full/%04d.png " $n; done); do
  cp "$f" $CL/c_materials/$(printf %04d $i).png; i=$((i+1))
done
for c in a_layout b_props c_materials d_lighting; do mp4 $c; done
