#!/usr/bin/env bash
cd "$(dirname "$0")/../../.."
. pipeline/env.sh

HEROES=counter bash scenes/tokyo-ramen-shop/scripts/heroes_r2.sh
bash pipeline/gpu_run.sh "$B" -b scenes/tokyo-ramen-shop/ramen_r2.blend --python scenes/tokyo-ramen-shop/scripts/gpu_prefs.py --python scenes/tokyo-ramen-shop/scripts/render.py -- prev door --tag _r2 --samples 96 --res 1280 2>&1 | grep -E "STILL|Error"
cp scenes/tokyo-ramen-shop/out/prev/door_r2.png scenes/tokyo-ramen-shop/out/process/r2_exterior_from_inside.png
bash scenes/tokyo-ramen-shop/scripts/shots_r2.sh
