#!/usr/bin/env bash
# Wait for generation, then compare the remaining placed round-2 props and build one review sheet.
cd "$(dirname "$0")/../../.."
. pipeline/env.sh
until grep -q "all done" logs/ramen_gen_fix.log; do sleep 30; done
P=ramen_vending_machine_nb,ramen_radio_nb,ramen_tape_roll_nb,ramen_hook_items_nb,ramen_coat_hooks_nb,ramen_napkins_used,ramen_towel_crumpled,ramen_junction_box,ramen_kamidana,ramen_daruma,ramen_beni_shoga_pot
PROPS=$P bash pipeline/gpu_run.sh "$B" -b --factory-startup --python scenes/tokyo-ramen-shop/scripts/gpu_prefs.py --python scenes/tokyo-ramen-shop/scripts/compare.py -- assets/gen scenes/tokyo-ramen-shop/compare 2>&1 | grep -cE "^render"
IFS=, read -ra A <<< "$P"
bash scenes/tokyo-ramen-shop/scripts/review.sh scenes/tokyo-ramen-shop/compare/review_r2_5.png "${A[@]:0:6}"
bash scenes/tokyo-ramen-shop/scripts/review.sh scenes/tokyo-ramen-shop/compare/review_r2_6.png "${A[@]:6:6}"
echo "COMPARED"; grep -c FAIL logs/ramen_gen_fix.log
