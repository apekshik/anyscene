#!/usr/bin/env bash
# Same-light compare renders (ref | Tripo | Meshy, front/back/clay) for mc_* props that have GLBs, in GPU-queue chunks
# of N props (default 10, ~5 min each) so no single gpu_run call holds the card for long.
#   scenes/mission-control-1970s/scripts/compare_batch.sh [N]
cd "$(dirname "$0")/../../.."
. pipeline/env.sh
N=${1:-10}
S=scenes/mission-control-1970s
todo=()
for d in assets/gen/tripo-h31/mc_* assets/gen/meshy/mc_*; do
  [ -f "$d/model.glb" ] || continue
  m=$(basename "$(dirname "$d")"); id=$(basename "$d")
  c="$S/compare/$m/${id}_clay.png"
  [ -f "$c" ] && [ "$c" -nt "$d/model.glb" ] && continue
  todo+=("$id")
done
ids=($(printf '%s\n' "${todo[@]}" | sort -u))
echo "compare: ${#ids[@]} props to render"
for ((i = 0; i < ${#ids[@]}; i += N)); do
  chunk=$(IFS=,; echo "${ids[*]:i:N}")
  bash pipeline/gpu_run.sh "$B" -b --factory-startup --python $S/scripts/compare.py -- "$ROOT_ABS/assets/gen" "$ROOT_ABS/$S/compare" "$chunk" 2>&1 | grep -E "^render|FAILED"
done
