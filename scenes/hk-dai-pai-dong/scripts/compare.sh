#!/usr/bin/env bash
# Same-light compare renders (ref | H3.1 | Meshy, front/back/clay) for props whose two GLBs both exist, in GPU-queue
# chunks of 12 props (each chunk ~5 min), then one review sheet per 8 props in compare/review_<n>.png.
#   bash scenes/hk-dai-pai-dong/scripts/compare.sh [id,id,...]   (default: every hk_ prop with both GLBs)
cd "$(dirname "$0")/../../.."
. pipeline/env.sh
SC=scenes/hk-dai-pai-dong
C=$SC/compare
mkdir -p $C
if [ -n "$1" ]; then IFS=, read -ra P <<< "$1"; else
  P=(); for d in assets/gen/meshy/hk_*; do id=$(basename $d)
    [ -f assets/gen/meshy/$id/model.glb ] && [ -f assets/gen/tripo-h31/$id/model.glb ] && P+=($id); done
fi
echo "compare ${#P[@]} props"
for ((i = 0; i < ${#P[@]}; i += 12)); do
  chunk=$(IFS=,; echo "${P[*]:$i:12}")
  PROPS=$chunk bash pipeline/gpu_run.sh "$BLENDER" -b --factory-startup --python $SC/scripts/compare.py -- "$ANYSCENE_ROOT/assets/gen" "$ANYSCENE_ROOT/$C" 2>&1 | grep -E "^render|FAILED"
done
args=()
n=0
for id in "${P[@]}"; do
  args+=("$id=refs/hk-dai-pai-dong/props/${id}_0.png|$C/tripo-h31/${id}_beauty.png|$C/meshy/${id}_beauty.png|$C/tripo-h31/${id}_back.png|$C/meshy/${id}_back.png|$C/tripo-h31/${id}_clay.png|$C/meshy/${id}_clay.png")
  if [ ${#args[@]} -eq 8 ]; then
    uv run --no-project --with pillow python -I $SC/scripts/sheet.py $C/review_$n.png 7 300 "${args[@]}" | tail -1; args=(); n=$((n + 1)); fi
done
[ ${#args[@]} -gt 0 ] && uv run --no-project --with pillow python -I $SC/scripts/sheet.py $C/review_$n.png 7 300 "${args[@]}" | tail -1
echo COMPARED
