#!/usr/bin/env bash
# Re-apply round-2 generated assets to the pre-gen backup (steam caches untouched), preview, heroes, changed shots.
cd "$(dirname "$0")/../../.."
. pipeline/env.sh

cp scenes/tokyo-ramen-shop/ramen_r2_pre_gen.blend scenes/tokyo-ramen-shop/ramen_r2.blend
"$B" -b scenes/tokyo-ramen-shop/ramen_r2.blend --python-expr "
import sys; sys.path.insert(0, __import__('os').environ['ANYSCENE_ROOT'] + '/scenes/tokyo-ramen-shop/scripts')
import r2gen, bpy; r2gen.apply(); bpy.ops.wm.save_mainfile(); print('PATCHED r2gen')" 2>&1 | grep -E "PATCHED|VALIDATE|^   |Traceback"
bash pipeline/gpu_run.sh "$B" -b scenes/tokyo-ramen-shop/ramen_r2.blend --python scenes/tokyo-ramen-shop/scripts/gpu_prefs.py --python scenes/tokyo-ramen-shop/scripts/render.py -- prev wide,counter,door,kitchen --tag _gen2 --samples 48 2>&1 | grep -cE "STILL"

P=scenes/tokyo-ramen-shop/out/prev
"$FF" -v error -y -i $P/wide_gen2.png -i $P/counter_gen2.png -i $P/door_gen2.png -i $P/kitchen_gen2.png -filter_complex "[0][1]hstack[a];[2][3]hstack[b];[a][b]vstack" scenes/tokyo-ramen-shop/out/process/r2_generated_props.png && echo PREVIEW
for k in wide counter; do [ -f scenes/tokyo-ramen-shop/out/hero_${k}_r2a.png ] || cp scenes/tokyo-ramen-shop/out/hero_$k.png scenes/tokyo-ramen-shop/out/hero_${k}_r2a.png; done
HEROES="wide counter" bash scenes/tokyo-ramen-shop/scripts/heroes_r2.sh
for s in lantern_rain exterior_establish counter_push door_dolly_zoom; do rm -rf scenes/tokyo-ramen-shop/out/shots/$s/frames; done
SHOTS="lantern_rain:96 exterior_establish:120 counter_push:120 door_dolly_zoom:96" bash scenes/tokyo-ramen-shop/scripts/shots_r2.sh
echo ALLDONE
