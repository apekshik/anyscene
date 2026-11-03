#!/usr/bin/env bash
# Sample reference plates for the Studio's "try one" picker (web/public/samples). GPT Image 2.5 Sunburst, 16:9.
cd "$(dirname "$0")/.."
F="node generate/fal.mjs image --variant sunburst --quality high --size landscape_16_9"
STYLE="Candid photo, realistic, natural light falloff and sensor noise, no people, no text overlays."
declare -A P=(
  [apothecary]="Inside a narrow Victorian apothecary at dusk: floor-to-ceiling dark wood drawers with brass labels, glass jars of herbs and tinctures, a marble counter with brass scales and a mortar, gas lamps glowing amber, blue evening light through a bay window."
  [subway]="An abandoned 1980s subway platform at night: cracked white tile walls with graffiti, a single flickering fluorescent tube, puddles on the platform edge, rusted benches, an old route map, the dark tunnel mouth at the end."
  [cabin]="A small Scandinavian cabin kitchen on a winter morning: pale pine walls, a cast-iron wood stove with a kettle, open shelves of ceramics, a scrubbed table with bread and coffee, frost on the window and soft low sun across the floor."
  [arcade]="A 1985 video arcade at night: rows of upright cabinets with invented, unbranded game art (no real game titles or logos) glowing in the dark, patterned carpet, a change machine, neon strips on the ceiling, screens reflecting on glossy cabinet sides, haze in the air."
  [greenhouse]="An old Victorian glass greenhouse at golden hour: white-painted iron frames, overgrown ferns and palms, terracotta pots on slatted benches, a watering can, condensation on the glass, warm low sun streaming through."
  [noir]="A 1940s detective office at night: a heavy wooden desk with a green banker's lamp, typewriter, ashtray and files, a coat rack with a fedora, frosted glass door, venetian blinds casting stripes from a neon sign outside."
  [jazz]="A small basement jazz bar after hours: a grand piano under a single spotlight, round tables with candles in red glass, a brick back wall, a long bar with bottles lit from below, cigarette haze."
  [cargo]="Inside a worn sci-fi spaceship cargo bay: stacked hard-shell crates with stencils, a loading mech parked by the wall, grated metal floor, warning stripes, cold overhead strip lights and an amber beacon, steam venting from pipes."
  [diner]="A roadside desert diner at night: chrome counter with red vinyl stools, a pie case, a jukebox, checkered floor, neon OPEN sign glowing in the window, empty highway and dark desert outside."
  [forge]="A medieval blacksmith forge: a glowing coal hearth with bellows, an anvil with hammers and tongs, tools hanging on a timber wall, a quench barrel, sparks and smoke, daylight leaking through gaps in the plank door."
  [library]="An old university library reading room: tall arched windows, long oak tables with green glass lamps, endless shelves with rolling ladders, a spiral iron staircase, dust in shafts of afternoon light."
  [garage]="A cluttered home garage workshop at night: a half-restored vintage motorcycle on a stand, pegboard full of tools, oily concrete floor, a radio and coffee can of bolts on the workbench, a single bare bulb and the open door to a rainy driveway."
)
mkdir -p refs/samples
for k in "${!P[@]}"; do $F --force --out "refs/samples/$k" --prompt "${P[$k]} $STYLE" & done
wait
