#!/usr/bin/env bash
# Grade in ffmpeg (not the Blender compositor): lifted teal shadows, warm highlights, a touch of desaturation,
# slight chromatic fringe, vignette, temporal grain. Checks the frame count before encoding (a gap = short clip).
#   bash scenes/hk-dai-pai-dong/scripts/grade.sh still <in.png> <out.png>
#   bash scenes/hk-dai-pai-dong/scripts/grade.sh clip  <shot_dir> <out.mp4> <expected_frames>
cd "$(dirname "$0")/../../.."
. pipeline/env.sh
FF="$FFMPEG"

GRADE="curves=r='0/0.03 0.25/0.23 0.6/0.635 1/0.985':g='0/0.034 0.25/0.245 0.6/0.615 1/0.965':b='0/0.05 0.25/0.27 0.6/0.6 1/0.93',hue=s=0.88,rgbashift=rh=-1:bh=1:edge=smear,vignette=angle=PI/4.4"
case "$1" in
  still) "$FF" -v error -y -i "$2" -vf "$GRADE,noise=alls=5:allf=u" -frames:v 1 "$3" ;;
  clip)
    n=$(ls "$2"/frames/*.png 2>/dev/null | wc -l)
    last=$(printf "%04d" "$4")
    if [ "$n" -ne "$4" ] || [ ! -f "$2/frames/$last.png" ]; then echo "grade: $2 has $n frames, expected $4 — not encoding"; exit 2; fi
    "$FF" -v error -y -framerate 24 -start_number 1 -i "$2/frames/%04d.png" -vf "$GRADE,noise=alls=7:allf=t+u,format=yuv420p" \
      -c:v h264_nvenc -preset p7 -rc vbr -cq 18 -b:v 0 -movflags +faststart "$3"
    got=$("$FF" -v error -i "$3" -map 0:v:0 -c copy -f null - 2>&1; "$FF" -i "$3" 2>&1 | grep -o "Duration: [0-9:.]*")
    echo "graded $3 ($n frames) $got" ;;
  *) echo "usage: grade.sh still|clip ..." ; exit 1 ;;
esac
