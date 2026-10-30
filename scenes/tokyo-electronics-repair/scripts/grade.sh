#!/usr/bin/env bash
# Final look in post (deterministic, no re-render): cool-night grade, slight chromatic aberration, vignette, grain.
#   scenes/tokyo-electronics-repair/scripts/grade.sh still <in.png> <out.png>
#   scenes/tokyo-electronics-repair/scripts/grade.sh clip  <frames_dir> <out.mp4>
cd "$(dirname "$0")/../../.."
. pipeline/env.sh

# lift + tint the shadows toward teal, keep warm highlights from the lamp, pull saturation slightly
GRADE="curves=r='0/0.03 0.25/0.235 0.6/0.63 1/0.98':g='0/0.035 0.25/0.25 0.6/0.62 1/0.97':b='0/0.055 0.25/0.28 0.6/0.61 1/0.94',hue=s=0.88,rgbashift=rh=-1:bh=1:edge=smear,vignette=angle=PI/4.6"
case "$1" in
  still) "$FF" -v error -y -i "$2" -vf "$GRADE,noise=alls=5:allf=u" -frames:v 1 "$3" ;;
  clip)  "$FF" -v error -y -framerate 24 -i "$2/f%04d.png" -vf "$GRADE,noise=alls=7:allf=t+u,format=yuv420p" -c:v h264_nvenc -preset p7 -rc vbr -cq 18 -b:v 0 -movflags +faststart "$3" ;;
  *) echo "usage: grade.sh still|clip ..." ; exit 1 ;;
esac
