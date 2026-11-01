#!/usr/bin/env bash
# Re-render the clay passes (a_layout, b_props, c_clay) after the clay exposure fix, then re-encode all clips.
cd "$(dirname "$0")/../../.."
. pipeline/env.sh
SC=scenes/hk-dai-pai-dong
R=breakdown/hk-dai-pai-dong
S=$ANYSCENE_ROOT/$SC/scripts
run() { bash pipeline/gpu_run.sh "$BLENDER" -b "$1" --python $S/gpu_prefs.py --python $S/bts.py -- "${@:2}" 2>&1 | grep -E "BTS rendered|Error:|Traceback"; }
rm -rf $R/clips/a_layout $R/clips/b_props $R/work/c_clay
run $SC/hk.blend a_layout
for r in 1-120 121-240; do run $SC/hk.blend b_props --frames $r; done
run $SC/hk.blend c_materials --pass clay --frames 1-48 --out $ANYSCENE_ROOT/$R/work/c_clay
bash $SC/scripts/bts_encode.sh
echo CLAY_REDO_DONE
