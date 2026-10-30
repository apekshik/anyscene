#!/usr/bin/env bash
# Isolated prop reference shots (GPT Image 2.5 Sunburst) to feed image-to-3D, as in the video.
cd "$(dirname "$0")/.."
F="node generate/fal.mjs image --variant sunburst --quality high --size square_hd"
REF="Product reference photograph for 3D scanning. The entire object fully visible and centered, three-quarter front view from slightly above, plain seamless light-grey background, soft even diffuse studio lighting, no harsh shadows, no other objects, no hands, realistic used and worn condition, sharp focus, true-to-life materials."
declare -A P=(
  [oscilloscope]="A 1980s analog CRT oscilloscope with a beige and grey metal case, round-cornered green-tinted screen with graticule, rows of knobs, toggle switches and BNC connectors on the front panel, small printed labels, scuffed paint."
  [solder_station]="A worn analog soldering station: a grey control unit with a temperature dial, a soldering iron resting in its coiled-wire holder stand with a yellow brass-wool tip cleaner, the iron's cable connecting to the unit."
  [helping_hands]="A helping-hands soldering aid on a heavy cast-iron base, two articulated arms with alligator clips holding a small green circuit board, a round magnifying glass on an adjustable arm."
  [boombox_open]="A 1980s silver cassette boombox radio lying open for repair with its back cover removed, exposing circuit boards, wires and the tape mechanism; the removed back panel and a few screws lying next to it."
  [stockpot]="A large, heavily used aluminium ramen stockpot, about 40 cm tall, with two riveted side handles, dented sides, heat discoloration and dried broth stains, a slightly warped lid resting on top."
  [ticket_machine]="A Japanese restaurant meal-ticket vending machine (shokkenki), a tall white and grey metal cabinet with a grid of illuminated rectangular menu buttons with Japanese labels, coin slot, bill slot and ticket tray, scuffed and slightly yellowed."
  [condiment_caddy]="A small stainless-steel condiment tray from a ramen counter holding glass bottles of chili oil, soy sauce and vinegar with chrome caps, a shaker of white pepper, and a jar of chopped garlic, slightly greasy."
  [lantern]="A red Japanese paper lantern (akachochin) for a ramen shop with black brush-stroke kanji ラーメン painted on it, ribbed paper over a bamboo frame, black lacquered top and bottom rims, slightly weathered."
)
for k in "${!P[@]}"; do
  $F --out refs/props/$k --prompt "${P[$k]} $REF" &
done
wait
