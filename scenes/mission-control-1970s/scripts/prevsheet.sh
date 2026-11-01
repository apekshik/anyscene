#!/usr/bin/env bash
# 2-column sheet of preview stills: prevsheet.sh <tag> [cams]  -> out/prev/<tag>_sheet.png
cd "$(dirname "$0")/../../.."
. pipeline/env.sh
P=scenes/mission-control-1970s/out/prev
cams=${2:-cam_back_wide,cam_row_a,cam_windows,cam_printer,cam_display}
IFS=, read -ra cs <<< "$cams"
args=(); f=""; n=0
for c in "${cs[@]}"; do args+=(-i "$P/${1}_$c.png"); f+="[$n]scale=960:402[s$n];"; n=$((n+1)); done
if [ $((n % 2)) -eq 1 ]; then args+=(-f lavfi -i color=c=black:s=960x402:d=1); f+="[$n]null[s$n];"; n=$((n+1)); fi
rows=""
for ((i = 0; i < n; i += 2)); do f+="[s$i][s$((i+1))]hstack=2[r$i];"; rows+="[r$i]"; done
f+="${rows}vstack=$((n / 2))"
"$FF" -v error -y "${args[@]}" -filter_complex "$f" -frames:v 1 "$P/${1}_sheet.png"
echo "$P/${1}_sheet.png"
