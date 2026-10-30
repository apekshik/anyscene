#!/usr/bin/env bash
# Same reference image through every 3D model, for the head-to-head.
cd "$(dirname "$0")/.."
F="node generate/fal.mjs 3d"
for ref in refs/props/*.json; do
  id=$(basename "$ref" .json)
  for m in tripo-h31 tripo-p2 meshy; do
    [ -f assets/gen/$m/$id/model.glb ] && continue
    ( $F --model $m --ref "$ref" --out assets/gen/$m/$id > logs/gen_${m}_$id.log 2>&1; echo "$m $id exit=$? $(tail -1 logs/gen_${m}_$id.log)" ) &
  done
done
wait
