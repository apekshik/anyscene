#!/usr/bin/env bash
# Concept shots for both scenes, each prompt through both GPT Image 2.5 variants.
cd "$(dirname "$0")/.."
F="node generate/fal.mjs image --quality high --size landscape_16_9"
STYLE="Candid photo taken on a phone at night, realistic, slightly underexposed, natural sensor noise, no people, no text overlays."

REPAIR_WIDE="Inside a cramped, cluttered electronics repair shop in a Tokyo back street, late at night after closing. A long wooden workbench runs along the wall under a single articulated work lamp; on it a vintage CRT oscilloscope, a soldering station with helping hands, multimeters, a disassembled cassette radio and a VCR with its lid off, coiled wires, parts trays, solder spools and handwritten repair tags. Above the bench, small-parts drawer cabinets and shelves of boxed devices waiting for pickup. Overhead fluorescent tubes switched off; the room lit by the work lamp, a green oscilloscope glow and cold blue street light through a rain-streaked shop window with blurred neon outside. $STYLE"
REPAIR_DETAIL="Close-up of a well-worn electronics repair workbench late at night: a soldering iron resting in its stand with a thin curl of smoke, an open circuit board held in helping hands with a magnifier, a CRT oscilloscope showing a green waveform, a multimeter with probes, a small tray of salvaged capacitors and screws, flux bottle, solder wick, a mug of cold coffee and a handwritten repair ticket. Warm pool of light from an articulated lamp, the rest of the shop falling into darkness. $STYLE"
RAMEN_WIDE="Inside a tiny old ramen shop in Tokyo late at night just after closing. A narrow L-shaped wooden counter with eight worn stools faces an open kitchen: dented aluminium stockpots on gas burners with faint steam, ladles and strainers hanging, stacked ceramic bowls, tare containers, a cutting board with green onions. Handwritten wooden menu tags on the wall, a meal-ticket vending machine glowing by the sliding door, a red paper lantern outside throwing light through the noren curtain, rain on the street. Warm tungsten light over the counter, everything else dim. $STYLE"
RAMEN_DETAIL="Close-up of a ramen shop counter late at night after closing: an unfinished bowl of ramen pushed aside, chopsticks resting on the rim, a condiment caddy with chili oil, vinegar and soy bottles, a tissue box, a glass of water, wiped wooden counter with old stains, behind it the kitchen pass with a dented stockpot still steaming under a single warm hanging light. $STYLE"

for v in flare sunburst; do
  $F --variant $v --out refs/tokyo-electronics-repair/concept_wide_$v --prompt "$REPAIR_WIDE" &
  $F --variant $v --out refs/tokyo-electronics-repair/concept_detail_$v --prompt "$REPAIR_DETAIL" &
  $F --variant $v --out refs/tokyo-ramen-shop/concept_wide_$v --prompt "$RAMEN_WIDE" &
  $F --variant $v --out refs/tokyo-ramen-shop/concept_detail_$v --prompt "$RAMEN_DETAIL" &
done
wait
