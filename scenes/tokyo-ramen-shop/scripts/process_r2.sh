#!/usr/bin/env bash
# Round-2 process images: wide + counter, lit and clay, after each densify pass (no steam), via the GPU queue.
cd "$(dirname "$0")/../../.."
. pipeline/env.sh

base="shell,dress"
for p in passA passB passC grime; do
  base="$base,$p"
  for clay in "" "--clay"; do
    tag="_r2_${p}${clay:+_clay}"
    bash pipeline/gpu_run.sh "$B" -b --factory-startup --python scenes/tokyo-ramen-shop/scripts/build.py -- --stages "$base,light,post" --preview wide,counter --samples 40 --res 960 --tag "$tag" $clay 2>&1 | grep -E "rendered|Error|Traceback"
  done
done

P=scenes/tokyo-ramen-shop/out/prev; O=scenes/tokyo-ramen-shop/out/process
for p in passA passB passC grime; do
  "$FF" -v error -y -i $P/wide_r2_$p.png -i $P/counter_r2_$p.png -i $P/wide_r2_${p}_clay.png -i $P/counter_r2_${p}_clay.png \
    -filter_complex "[0][1]hstack[a];[2][3]hstack[b];[a][b]vstack" $O/r2_$p.png && echo "sheet $p"
done
