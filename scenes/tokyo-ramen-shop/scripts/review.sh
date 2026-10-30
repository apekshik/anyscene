#!/usr/bin/env bash
# Review sheet per prop: ref | H3.1 front | Meshy front | H3.1 back | Meshy back | H3.1 clay | Meshy clay.
#   scenes/tokyo-ramen-shop/scripts/review.sh out.png id id id ...
cd "$(dirname "$0")/../../.."
. pipeline/env.sh

OUT=$1; shift
C=scenes/tokyo-ramen-shop/compare
rows=()
i=0
for p in "$@"; do
  ref=refs/tokyo-ramen-shop/props/${p}_0.png; [ -f "$ref" ] || ref=refs/props/${p}_0.png
  args=(-i "$ref")
  for v in beauty back clay; do for m in tripo-h31 meshy; do
    f=$C/$m/${p}_$v.png; [ -f "$f" ] || f=$ref; args+=(-i "$f"); done; done
  "$FF" -v error -y "${args[@]}" -filter_complex "[0]scale=300:300[a];[1]scale=300:300[b];[2]scale=300:300[c];[3]scale=300:300[d];[4]scale=300:300[e];[5]scale=300:300[f];[6]scale=300:300[g];[a][b][c][d][e][f][g]hstack=7" "/tmp/ramen_row_$i.png"
  rows+=(-i "/tmp/ramen_row_$i.png"); i=$((i+1))
done
if [ $i -eq 1 ]; then cp /tmp/ramen_row_0.png "$OUT"; else "$FF" -v error -y "${rows[@]}" -filter_complex "vstack=$i" "$OUT"; fi
