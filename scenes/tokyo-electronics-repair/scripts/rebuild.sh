#!/usr/bin/env bash
# shell -> dress (pass) -> validate -> lights. Usage: scenes/tokyo-electronics-repair/scripts/rebuild.sh [pass=3]
cd "$(dirname "$0")/../../.."
. pipeline/env.sh

"$B" -b --factory-startup --python scenes/tokyo-electronics-repair/scripts/build_shell.py 2>&1 | grep -E "Error|Traceback" 
"$B" -b scenes/tokyo-electronics-repair/repair_shell.blend --python scenes/tokyo-electronics-repair/scripts/dress.py -- ${1:-3} 2>&1 | grep -E "MISSING|Error|Traceback"
"$B" -b scenes/tokyo-electronics-repair/repair_dressed.blend --python scenes/tokyo-electronics-repair/scripts/validate.py 2>&1 | grep -E "^(FLOAT|CLIP|OUT|SCALE|VALIDATE)|Error|Traceback"
"$B" -b scenes/tokyo-electronics-repair/repair_dressed.blend --python scenes/tokyo-electronics-repair/scripts/lights.py -- scenes/tokyo-electronics-repair/repair_lit.blend 2>&1 | grep -E "Error|Traceback"
"$B" -b scenes/tokyo-electronics-repair/repair_lit.blend --python scenes/tokyo-electronics-repair/scripts/cameras.py -- scenes/tokyo-electronics-repair/repair_final.blend 2>&1 | grep -E "Error|Traceback"
exit 0
