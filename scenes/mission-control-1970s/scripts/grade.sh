#!/usr/bin/env bash
# Final look in post (deterministic, no re-render): lifted teal-green shadows, warm lamp highlights, slightly
# desaturated, a touch of chromatic aberration, vignette, temporal grain.
#   scenes/mission-control-1970s/scripts/grade.sh still <in.png> <out.png>
#   scenes/mission-control-1970s/scripts/grade.sh clip  <frames_dir> <out.mp4>     (frames_dir/####.png)
cd "$(dirname "$0")/../../.."
. pipeline/env.sh
GRADE="curves=r='0/0.028 0.25/0.22 0.6/0.62 1/0.98':g='0/0.034 0.25/0.245 0.6/0.61 1/0.96':b='0/0.045 0.25/0.255 0.6/0.58 1/0.9',hue=s=0.86,rgbashift=rh=-1:bh=1:edge=smear,vignette=angle=PI/4.4"
case "$1" in
  still) "$FF" -v error -y -i "$2" -vf "$GRADE,noise=alls=5:allf=u" -frames:v 1 "$3" ;;
  clip)  "$FF" -v error -y -framerate 24 -start_number 1 -i "$2/%04d.png" -vf "$GRADE,noise=alls=7:allf=t+u,format=yuv420p" \
           -c:v h264_nvenc -preset p7 -rc vbr -cq 18 -b:v 0 -movflags +faststart "$3" ;;
  *) echo "usage: grade.sh still|clip ..." ; exit 1 ;;
esac
