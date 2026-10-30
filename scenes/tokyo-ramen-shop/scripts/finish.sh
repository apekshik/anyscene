#!/usr/bin/env bash
# Finishing pass (ffmpeg): split-tone grade (warm highlights, cool shadows), gentle S-curve, soft vignette, film grain.
#   scenes/tokyo-ramen-shop/scripts/finish.sh still in.png out.png
#   scenes/tokyo-ramen-shop/scripts/finish.sh clip frames/%04d.png out.mp4
# Uses curves + hue for tone (no eq) and h264_nvenc for encoding.
. "$(dirname "$0")/../../../pipeline/env.sh"

GRADE="colorbalance=rs=-0.03:bs=0.05:rm=0.02:bm=-0.02:rh=0.05:gh=0.01:bh=-0.05,curves=all='0/0.012 0.25/0.22 0.6/0.63 1/0.98',hue=s=0.92,vignette=angle=PI/4.6:mode=forward"
case "$1" in
  still) "$FF" -v error -y -i "$2" -vf "$GRADE,noise=alls=6:allf=u" "$3" ;;
  clip)  "$FF" -v error -y -framerate 24 -i "$2" -vf "$GRADE,noise=alls=7:allf=t+u,format=yuv420p" -c:v h264_nvenc -preset p7 -rc vbr -cq 17 -b:v 0 "$3" ;;
  *) echo "usage: finish.sh still|clip in out"; exit 1 ;;
esac
