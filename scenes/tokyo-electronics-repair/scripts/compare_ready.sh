#!/usr/bin/env bash
# Render compare views for every repair_* GLB that exists and has not been rendered yet (under the GPU lock).
cd "$(dirname "$0")/../../.."
. pipeline/env.sh
ids=$(ls -d assets/gen/tripo-h31/repair_* assets/gen/meshy/repair_* 2>/dev/null | xargs -n1 basename | sort -u | tr '\n' ',')
[ -z "$ids" ] && exit 0
bash pipeline/gpu_run.sh "$B" -b --factory-startup --python scenes/tokyo-electronics-repair/scripts/compare.py -- assets/gen scenes/tokyo-electronics-repair/compare "${ids%,}" 2>&1 | grep -E "^render|FAILED"
