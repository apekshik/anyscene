// Round 2: append debranded replacements (*_nb) and pass A / pass B props to scenes/tokyo-electronics-repair/assets.json.
import { readFileSync, writeFileSync } from 'node:fs';
const P = 'scenes/tokyo-electronics-repair/assets.json';
const man = JSON.parse(readFileSync(P, 'utf8'));
const have = new Set(man.generate.map((a) => a.id));
const orig = Object.fromEntries(man.generate.map((a) => [a.id, a]));
const promptOf = (id) => orig[id].prompt === 'existing'
  ? JSON.parse(readFileSync(`refs/props/${id}.json`, 'utf8')).input.prompt.split(' Product reference')[0]
  : orig[id].prompt;
const NB = {
  oscilloscope: 'KOSEI', solder_station: 'HANDA-YA', boombox_open: 'SONICA', repair_multimeter_yellow: 'VOLTEK', repair_multimeter_red: 'VOLTEK',
  repair_bench_psu: 'DENKO', repair_tool_chest: 'IRONSIDE', repair_spray_cans: 'none', repair_cup_noodle: 'none', repair_boxes_b: 'none',
  repair_vcr_open: 'MIRAVISION', repair_tissue_box: 'none', repair_rice_cooker: 'HARUKA', repair_vintage_radio: 'AOZORA', repair_receiver: 'SOUNDHILL',
  repair_solder_junk: 'none', repair_laptop_broken: 'none', repair_crt_stack: 'none', repair_crt_tv: 'MIRAVISION', repair_turntable: 'SOUNDHILL',
  repair_desk_fan: 'KAZEMARU', repair_kerosene_heater: 'none',
};
const add = (a) => { if (!have.has(a.id)) { man.generate.push(a); have.add(a.id); } };
for (const [id, brand] of Object.entries(NB)) {
  const nb = id.startsWith('repair_') ? `${id}_nb` : `repair_${id}_nb`;
  const tag = brand === 'none'
    ? 'All printing and labels are generic or plain, with no real-world brand names, product names or logos.'
    : `The only brand name visible is the fictional brand "${brand}"; no real-world brand names, model names or logos anywhere.`;
  add({ id: nb, replaces: id, fit: orig[id].fit, size: orig[id].size, hero: orig[id].hero, pass: 'nb', models: ['tripo-h31', 'meshy'], prompt: `${promptOf(id)} ${tag}` });
}
const A = [
  ['repair_cassette_deck', 'max', 0.43, 'A 1980s black stereo cassette tape deck with a single tape door, VU meters and piano-key transport buttons, dusty.'],
  ['repair_amp_black', 'max', 0.43, 'A black 1990s integrated stereo amplifier with a large volume knob, small input selector knobs and a row of push buttons, scratched top.'],
  ['repair_crt_monitor_beige', 'h', 0.38, 'A beige 1990s computer CRT monitor with a deep back, curved dark screen, small tilt-swivel base, yellowed plastic, a paper repair tag taped to the side.'],
  ['repair_portable_tv', 'h', 0.24, 'A small 1980s portable black-and-white TV with a carry handle, telescopic antenna folded down and a small round speaker grille, red plastic case.'],
  ['repair_tv_wood', 'h', 0.45, 'A 1970s CRT television in a wood-grain cabinet with a rounded screen, two rotary channel dials on the right and four short legs.'],
  ['repair_speaker_pair', 'h', 0.4, 'A pair of small vintage bookshelf speakers in walnut veneer cabinets, one with its grille cloth removed showing the woofer and tweeter.'],
  ['repair_camcorder', 'max', 0.3, 'A 1990s VHS-C camcorder with a shoulder pad, side viewfinder and a cracked lens hood, black and grey plastic.'],
  ['repair_microwave', 'max', 0.5, 'A small white household microwave oven with a dial timer and a dirty glass door, a paper repair ticket taped to the door.'],
  ['repair_pc_tower', 'h', 0.42, 'A yellowed beige 1990s PC tower computer with a floppy drive and CD drive bay, side panel removed showing the motherboard and cables.'],
  ['repair_dotmatrix_printer', 'max', 0.45, 'A beige dot-matrix printer with tractor-feed perforated paper coming out the top, dusty, lid slightly open.'],
  ['repair_fax_phone', 'max', 0.32, 'A beige 1990s home fax telephone with a corded handset, a keypad and thermal paper roll slot.'],
  ['repair_radio_cassette', 'max', 0.35, 'A small silver radio cassette player with a carry handle, one round speaker, a tuning dial and a cassette door, worn.'],
  ['repair_karaoke_machine', 'h', 0.4, 'A home karaoke machine: a black box with two microphone inputs, a small built-in screen, colourful buttons, with a wired microphone resting on top.'],
  ['repair_electric_kettle', 'h', 0.25, 'A white electric hot-water pot dispenser with a push-button top and a cord, Japanese style, slightly stained.'],
  ['repair_job_bin', 'max', 0.45, 'A blue plastic storage bin holding a disassembled DVD player, loose screws in a sandwich bag and a paper repair ticket clipped to the rim.'],
  ['repair_cable_crate', 'max', 0.45, 'A black plastic milk crate overflowing with tangled power cords, AV cables, AC adapters and remote controls.'],
  ['repair_parts_bins', 'h', 0.45, 'A stack of small blue and red plastic stackable parts bins with open fronts, filled with screws, knobs and small components, handwritten labels.'],
  ['repair_parts_cart', 'h', 0.85, 'A grey steel three-tier rolling utility cart loaded with a disassembled stereo, a box of parts, cables and a coffee cup, on casters, worn.'],
  ['repair_hot_air_station', 'max', 0.3, 'A hot-air rework station: a grey control box with two digital displays and knobs, the hot-air gun resting in its holder with a coiled hose.'],
  ['repair_magnifier_lamp', 'h', 0.55, 'A white ring-light magnifier lamp on a heavy desk base with a spring arm, the round lens head tilted down, scuffed.'],
  ['repair_pcb_vise', 'max', 0.22, 'A small PCB holder vise on a weighted base clamping a green circuit board with components partly desoldered.'],
  ['repair_fume_extractor', 'h', 0.25, 'A small black desktop solder fume extractor fan with a square carbon filter on the front, on a tilting stand.'],
  ['repair_cash_register', 'max', 0.4, 'A small old electronic cash register with a cash drawer, a receipt printer, rows of keys and a small green display, plain, no brand.'],
  ['repair_desk_phone', 'max', 0.22, 'A beige office desk telephone with a coiled cord handset and a large-key keypad, yellowed.'],
  ['repair_counter_lamp', 'h', 0.42, 'A small green-shaded metal desk lamp with a weighted round base and a pull chain, worn paint.'],
  ['repair_display_case', 'max', 0.7, 'A small countertop glass display showcase with a wooden frame and sliding back doors, holding used portable cassette players, old mobile phones and calculators with price tags.'],
  ['repair_calculator', 'max', 0.17, 'A grey desktop printing calculator with a paper roll and large keys, tape curling out.'],
  ['repair_umbrella_stand', 'h', 0.7, 'A metal umbrella stand by a shop door holding three wet transparent plastic umbrellas and one black umbrella, water pooled at the base.'],
  ['repair_shop_vac', 'h', 0.55, 'A small grey wet-dry shop vacuum with a coiled hose wrapped around it, dusty.'],
  ['repair_step_stool', 'h', 0.5, 'A small aluminium two-step folding step ladder, open, paint drips on the steps.'],
  ['repair_floor_fan', 'h', 0.9, 'A tall cream-coloured pedestal electric fan with a round metal cage, standing, the cord coiled at the base.'],
  ['repair_storage_boxes_flat', 'max', 0.6, 'A stack of four flat cardboard boxes of different sizes tied with plastic string, labelled in marker, slightly crushed corners.'],
];
for (const [id, fit, size, prompt] of A) add({ id, fit, size, pass: 'A', models: ['tripo-h31', 'meshy'], prompt: `${prompt} No real-world brand names or logos.` });
const B = [
  ['repair_pcbs_loose', 'max', 0.25, 'A small pile of four loose salvaged green and brown circuit boards with components, one with burnt marks.'],
  ['repair_screw_jar', 'h', 0.11, 'A glass jar with a dented metal lid full of assorted screws, nuts and washers.'],
  ['repair_screwdriver_case', 'max', 0.24, 'An open plastic case with a precision screwdriver set and interchangeable bits, a few bits missing.'],
  ['repair_tweezers', 'max', 0.14, 'Three stainless steel precision tweezers of different tip shapes lying side by side.'],
  ['repair_ashtray', 'max', 0.14, 'A round glass ashtray with several crushed cigarette butts and ash.'],
  ['repair_tape_rolls', 'max', 0.14, 'A roll of black electrical tape, a roll of yellow kapton tape and a half-used roll of masking tape stacked loosely.'],
  ['repair_receipts', 'max', 0.22, 'A messy pile of small paper receipts and handwritten repair slips held with a black binder clip.'],
  ['repair_cable_bundle', 'max', 0.35, 'A loosely coiled bundle of black power cords tied with a red twist tie, lying on a table.'],
  ['repair_canned_coffee', 'h', 0.12, 'Two empty steel canned-coffee drink cans, one crushed, plain dark brown labels with no logos.'],
  ['repair_desolder_pump', 'max', 0.2, 'A blue and silver spring-loaded desoldering pump with a white tip.'],
  ['repair_flux_bottles', 'h', 0.11, 'Two small plastic flux dispenser bottles with needle tips and a jar of rosin flux paste, generic labels.'],
  ['repair_component_bag', 'max', 0.15, 'A small zip-lock plastic bag of electrolytic capacitors and resistors with a handwritten paper label.'],
  ['repair_ribbon_cables', 'max', 0.3, 'A few grey flat ribbon cables with black connectors, loosely folded.'],
  ['repair_extension_block', 'max', 0.32, 'A white power strip extension block with six sockets, several plugs inserted, cord coiled, dirty.'],
  ['repair_sticky_notes', 'max', 0.09, 'A pad of yellow sticky notes with handwriting on the top note and a ballpoint pen.'],
  ['repair_remote_controls', 'max', 0.22, 'Three old TV and VCR remote controls of different sizes lying together, one with its battery cover missing.'],
];
for (const [id, fit, size, prompt] of B) add({ id, fit, size, pass: 'B', models: ['tripo-p2', 'meshy'], prompt: `${prompt} No real-world brand names or logos.` });
writeFileSync(P, JSON.stringify(man, null, 1));
console.log(man.generate.length, 'props in manifest;', man.generate.filter((a) => a.pass).length, 'round-2');
