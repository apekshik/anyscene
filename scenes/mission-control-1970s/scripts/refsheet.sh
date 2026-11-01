#!/usr/bin/env bash
# Grid of reference images (brand check gate): refsheet.sh <out.png> <id> [id ...]  -> 6 per row, 256 px, id order.
cd "$(dirname "$0")/../../.."
. pipeline/env.sh
out=$1; shift
args=(); f=""; n=0; rows=""; r=0; row=""; k=0
for id in "$@"; do
  args+=(-i "refs/mission-control-1970s/props/${id}_0.png"); f+="[$n]scale=256:256[s$n];"; row+="[s$n]"; n=$((n+1)); k=$((k+1))
  if [ $k -eq 6 ]; then f+="${row}hstack=6[r$r];"; rows+="[r$r]"; r=$((r+1)); row=""; k=0; fi
done
while [ $k -gt 0 ] && [ $k -lt 6 ]; do args+=(-f lavfi -i color=c=black:s=256x256:d=1); f+="[$n]null[s$n];"; row+="[s$n]"; n=$((n+1)); k=$((k+1)); done
[ -n "$row" ] && { f+="${row}hstack=6[r$r];"; rows+="[r$r]"; r=$((r+1)); }
if [ $r -gt 1 ]; then f+="${rows}vstack=$r"; else f="${f%;}"; f="${f%\[r0\]}"; fi
"$FF" -v error -y "${args[@]}" -filter_complex "$f" -frames:v 1 "$out"
