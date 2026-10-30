#!/usr/bin/env bash
# Review sheet: one row per prop = ref | H3.1 front | Meshy front | H3.1 back | Meshy back | H3.1 clay | Meshy clay.
#   scenes/tokyo-electronics-repair/scripts/sheet.sh <out.png> <id> [id ...]   (up to 4 ids)
cd "$(dirname "$0")/../../.."
. pipeline/env.sh

out=$1; shift
img() {  # compare render for a model/prop/view: repair renders first, then the original head-to-head
  local f="scenes/tokyo-electronics-repair/compare/$1/$2_$3.png"
  [ -f "$f" ] || f="out/compare/$1/$2_$3.png"
  [ -f "$f" ] || f="scenes/tokyo-electronics-repair/compare/missing.png"
  echo "$f"
}
[ -f scenes/tokyo-electronics-repair/compare/missing.png ] || "$FF" -v error -f lavfi -i color=c=black:s=300x300 -frames:v 1 scenes/tokyo-electronics-repair/compare/missing.png
args=(); f=""; rows=""; n=0; r=0
for id in "$@"; do
  ref="refs/tokyo-electronics-repair/props/${id}_0.png"; [ -f "$ref" ] || ref="refs/props/${id}_0.png"
  tiles=("$ref" "$(img tripo-h31 $id beauty)" "$(img meshy $id beauty)" "$(img tripo-h31 $id back)" "$(img meshy $id back)" "$(img tripo-h31 $id clay)" "$(img meshy $id clay)")
  row=""
  for t in "${tiles[@]}"; do args+=(-i "$t"); f+="[$n]scale=300:300[s$n];"; row+="[s$n]"; n=$((n+1)); done
  f+="${row}hstack=7[r$r];"; rows+="[r$r]"; r=$((r+1))
done
if [ $r -gt 1 ]; then f+="${rows}vstack=$r"; else f="${f%;}"; f="${f%\[r0\]}"; fi
"$FF" -v error -y "${args[@]}" -filter_complex "$f" "$out"
