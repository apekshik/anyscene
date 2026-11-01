#!/usr/bin/env bash
# Reel of the graded shots (concat, stream copy) + a compressed copy under 30 MB for chat. Checks durations.
cd "$(dirname "$0")/../../.."
. pipeline/env.sh
O=scenes/hk-dai-pai-dong/out/shots
L=$O/reel_list.txt
: > $L
for s in s1_street_crane h1_walk_in_to_wok s2_teapot_wok_rack s3_wok_push h2_walk_tables_neon s4_neon_tilt; do
  f=$O/${s}_graded.mp4
  [ -f $f ] || { echo "missing $f"; exit 2; }
  echo "$s $("$FF" -i $f 2>&1 | grep -o 'Duration: [0-9:.]*')"
  echo "file '${s}_graded.mp4'" >> $L
done
"$FF" -v error -y -f concat -safe 0 -i $L -c copy $O/hk_dai_pai_dong_reel.mp4
dur=$("$FF" -i $O/hk_dai_pai_dong_reel.mp4 2>&1 | grep -o 'Duration: [0-9:.]*' | cut -d' ' -f2)
secs=$(echo $dur | awk -F: '{print $1*3600+$2*60+$3}')
kbps=$(awk -v s=$secs 'BEGIN{printf "%d", 28*8192/s}')
"$FF" -v error -y -i $O/hk_dai_pai_dong_reel.mp4 -vf scale=1280:-2 -c:v h264_nvenc -preset p7 -b:v ${kbps}k -maxrate ${kbps}k -bufsize $((kbps*2))k -an $O/hk_dai_pai_dong_reel_small.mp4
ls -la $O/hk_dai_pai_dong_reel*.mp4
echo "REEL $dur"
