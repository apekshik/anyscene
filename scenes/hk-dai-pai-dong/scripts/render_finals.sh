#!/usr/bin/env bash
# Final Cycles renders of every shot in 24-frame chunks (each its own GPU-queue call, so the other scene can
# interleave), then an ffmpeg grade per shot with a frame-count check, then the reel.
#   bash scenes/hk-dai-pai-dong/scripts/render_finals.sh [shot,shot] > logs/hk_finals.log 2>&1
cd "$(dirname "$0")/../../.."
. pipeline/env.sh
SC=scenes/hk-dai-pai-dong
O=$SC/out/shots
ORDER=${1:-h1_walk_in_to_wok,h2_walk_tables_neon,s1_street_crane,s2_teapot_wok_rack,s3_wok_push,s4_neon_tilt}
frames() { uv run --no-project python -I -c "import json;print(next(s['frames'] for s in json.load(open('$SC/shots.json'))['shots'] if s['name']=='$1'))"; }
IFS=, read -ra SHOTS <<< "$ORDER"
for s in "${SHOTS[@]}"; do
  n=$(frames $s)
  for ((a = 1; a <= n; a += 24)); do
    b=$((a + 23)); [ $b -gt $n ] && b=$n
    have=0; for ((f = a; f <= b; f++)); do [ -f $O/$s/frames/$(printf %04d $f).png ] && have=$((have + 1)); done
    [ $have -eq $((b - a + 1)) ] && continue
    t0=$(date +%s)
    bash $SC/scripts/shoot.sh --only $s --frames $a-$b --no-encode 2>&1 | grep -E "camrig: final|Error|Traceback"
    echo "CHUNK $s $a-$b $(( $(date +%s) - t0 ))s"
  done
  bash $SC/scripts/grade.sh clip $O/$s $O/${s}_graded.mp4 $n
done
echo FINALS_DONE
