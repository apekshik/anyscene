#!/usr/bin/env bash
# Every shot in 24-frame chunks through the GPU queue (existing frames skipped, so this resumes), then a graded mp4
# per shot with a frame-count check, then the reel and a <30 MB chat copy.
#   scenes/mission-control-1970s/scripts/render_finals.sh [shot ...]
cd "$(dirname "$0")/../../.."
. pipeline/env.sh
S=scenes/mission-control-1970s
O=$S/out/shots
CHUNK=${CHUNK:-24}
shots=${*:-$(node -e "console.log(require('./$S/shots.json').shots.map(s=>s.name).join(' '))")}
for s in $shots; do
  n=$(node -e "console.log(require('./$S/shots.json').shots.find(x=>x.name=='$s').frames)")
  for ((a = 1; a <= n; a += CHUNK)); do
    b=$((a + CHUNK - 1)); [ $b -gt $n ] && b=$n
    have=$(ls $O/$s/frames 2>/dev/null | awk -v a=$a -v b=$b '{f=$0+0} f>=a && f<=b' | wc -l)
    [ "$have" -eq $((b - a + 1)) ] && continue
    t0=$(date +%s)
    if [ "$s" = orbital_push ]; then nc=; else nc=1; fi  # smoke curls only in the push-in (see nocurl.py)
    NOCURL=$nc bash $S/scripts/shoot.sh --only $s --frames $a-$b --no-encode > $S/logs/final_${s}_$a.log 2>&1
    echo "$s $a-$b: $(( $(date +%s) - t0 )) s"
  done
  got=$(ls $O/$s/frames | wc -l)
  if [ "$got" -ne "$n" ]; then echo "SHORT $s: $got/$n frames"; continue; fi
  bash $S/scripts/grade.sh clip $O/$s/frames $S/out/graded/$s.mp4
  echo "graded $s: $("$FF" -i $S/out/graded/$s.mp4 2>&1 | grep -o 'Duration: [0-9:.]*')"
done
