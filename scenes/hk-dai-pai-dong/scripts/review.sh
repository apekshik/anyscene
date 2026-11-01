#!/usr/bin/env bash
# Review sheets (ref | H3.1 front/back/clay | Meshy ...) for compared props NOT yet in picks.json, 8 per sheet:
#   bash scenes/hk-dai-pai-dong/scripts/review.sh <tag>   -> compare/todo_<tag>_<n>.png
cd "$(dirname "$0")/../../.."
SC=scenes/hk-dai-pai-dong
C=$SC/compare
P=()
for f in $C/meshy/hk_*_clay.png; do id=$(basename $f _clay.png)
  [ -f $C/tripo-h31/${id}_clay.png ] || continue
  grep -q "\"$id\"" $SC/picks.json && continue
  P+=($id); done
echo "to review: ${P[*]}"
n=0; args=()
for id in "${P[@]}"; do
  args+=("$id=refs/hk-dai-pai-dong/props/${id}_0.png|$C/tripo-h31/${id}_beauty.png|$C/meshy/${id}_beauty.png|$C/tripo-h31/${id}_back.png|$C/meshy/${id}_back.png|$C/tripo-h31/${id}_clay.png|$C/meshy/${id}_clay.png")
  if [ ${#args[@]} -eq 8 ]; then uv run --no-project --with pillow python -I $SC/scripts/sheet.py $C/todo_$1_$n.png 7 300 "${args[@]}" | tail -1; args=(); n=$((n+1)); fi
done
[ ${#args[@]} -gt 0 ] && uv run --no-project --with pillow python -I $SC/scripts/sheet.py $C/todo_$1_$n.png 7 300 "${args[@]}" | tail -1
