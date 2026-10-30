#!/usr/bin/env bash
# Round 2 build: shell -> dress (round-1 layout, pass 4) -> validate -> dress2 <A|B|C> -> grime -> lights -> cameras.
#   scenes/tokyo-electronics-repair/scripts/rebuild2.sh C        -> scenes/tokyo-electronics-repair/repair_final.blend
cd "$(dirname "$0")/../../.."
. pipeline/env.sh

P=${1:-C}
"$B" -b --factory-startup --python scenes/tokyo-electronics-repair/scripts/build_shell.py 2>&1 | grep -E "Error|Traceback"
"$B" -b scenes/tokyo-electronics-repair/repair_shell.blend --python scenes/tokyo-electronics-repair/scripts/dress.py -- 4 2>&1 | grep -E "MISSING|Error|Traceback"
"$B" -b scenes/tokyo-electronics-repair/repair_dressed.blend --python scenes/tokyo-electronics-repair/scripts/validate.py 2>&1 | grep -E "^(FLOAT|CLIP|OUT|SCALE|FURNITURE|VALIDATE)|Error|Traceback"
"$B" -b scenes/tokyo-electronics-repair/repair_dressed.blend --python scenes/tokyo-electronics-repair/scripts/dress2.py -- $P scenes/tokyo-electronics-repair/repair_dressed2.blend 2>&1 | grep -E "dress2 pass|Error|Traceback|line [0-9]+"
"$B" -b scenes/tokyo-electronics-repair/repair_dressed2.blend --python scenes/tokyo-electronics-repair/scripts/validate.py 2>&1 | grep -E "^(FLOAT|CLIP|OUT|SCALE|FURNITURE|VALIDATE)" | sed "s/^/dress2: /"
"$B" -b scenes/tokyo-electronics-repair/repair_dressed2.blend --python scenes/tokyo-electronics-repair/scripts/grime.py -- scenes/tokyo-electronics-repair/repair_grimed.blend 2>&1 | grep -E "grime on|Error|Traceback|line [0-9]+"
"$B" -b scenes/tokyo-electronics-repair/repair_grimed.blend --python scenes/tokyo-electronics-repair/scripts/lights.py -- scenes/tokyo-electronics-repair/repair_lit.blend 2>&1 | grep -E "Error|Traceback|line [0-9]+"
"$B" -b scenes/tokyo-electronics-repair/repair_lit.blend --python scenes/tokyo-electronics-repair/scripts/cameras.py -- scenes/tokyo-electronics-repair/repair_final.blend 2>&1 | grep -E "Error|Traceback|line [0-9]+"
exit 0
