// De-branded (_nb) regenerations of round-2 props/textures whose references carried real brands or characters.
import { readFileSync, writeFileSync } from 'node:fs';
const f = new URL('../assets.json', import.meta.url);
const m = JSON.parse(readFileSync(f, 'utf8'));
const NB = 'All labels use fictional Japanese brand names only; no real-world brand names, logos, store chains or trademarks anywhere.';
const props = {
  ramen_shelf_jars: 'A cluttered row of kitchen pantry items on a shelf: glass jars of pickled garlic and chili oil, a can of white pepper, a sesame oil bottle, a big jar of sesame seeds, plastic tubs of seasoning, all greasy and dusty, with fictional Japanese labels such as 山田食品 and 丸金, isolated group.',
  ramen_spice_tins: 'A cluster of round red and gold shichimi togarashi spice tins labelled 七味, a garlic chips jar labelled にんにく, a small white pepper shaker and a tub of minced garlic with a spoon, fictional maker name 丸金.',
  ramen_cardboard_boxes: 'A stack of three worn cardboard supply boxes printed with fictional Japanese food supplier names (山田食品, 丸金醤油, 大和製麺), one open with packets visible, tape peeling, slightly crushed.',
  ramen_flour_sacks: 'Two heavy brown paper 25 kg flour sacks for noodles leaning against each other, printed with the fictional mill name 大和製粉 and 中華麺用, flour dust, slumped and folded tops.',
  ramen_beer_bottle_glass: 'A large brown Japanese beer bottle with a paper label of the fictional brewery 富士ビール, next to a small beer glass with a little flat beer left in it.',
  ramen_lighter_cigs: 'A crumpled cigarette pack of the fictional brand 銀河 (plain design with Japanese health warning text) and a cheap transparent plastic lighter lying on a counter.',
  ramen_vending_machine: 'A Japanese outdoor drink vending machine with a brightly backlit front showing rows of canned and bottled drinks with fictional labels, white and red body with the fictional brand name さくら飲料, buttons glowing, rain-wet, at night.',
  ramen_radio: 'An old silver and black portable AM/FM radio cassette player with a telescopic antenna and the fictional brand name KOSEI, dusty and greasy.',
  ramen_tape_roll: 'A roll of brown packing tape and an unbranded black permanent marker lying next to it.',
  ramen_hook_items: 'A short wall rail with three hooks holding a ring of keys, a green fly swatter and a plain white plastic shopping bag with no printing.',
  ramen_coat_hooks: 'A dark wooden wall-mounted coat hook board with five metal hooks, a navy work jacket, a beige rain jacket, a plain baseball cap and a plain white plastic bag hanging on it, no logos.',
};
const tex = {
  stickers_sheet: 'A flat lay of eight assorted faded worn Japanese stickers spaced apart: a cartoon ramen bowl mascot, a generic QR code payment sticker reading QR決済, a cash only sticker 現金のみ, a no smoking sign, a fictional local baseball team sticker 商店街ファイターズ, a fictional beer sticker 富士ビール, a cute original cartoon cat mascot, a generic credit card icons strip with no real card logos, on a pure white background.',
  street_backdrop2: 'Wide realistic night photograph straight across a narrow rainy Tokyo back street toward the shops opposite: a lit izakaya with red lanterns and a glowing noren, a bright drink vending machine, vertical neon signs in pink and cyan with fictional shop names, a lit small convenience store with a fictional sign, wet asphalt with long colourful reflections and puddles, rain visible in the light, no people, slightly soft focus, vivid but realistic exposure.',
};
const ids = new Set(m.generate.map((p) => p.id));
for (const [id, prompt] of Object.entries(props)) {
  const base = m.generate.find((p) => p.id === id);
  if (!ids.has(id + '_nb')) m.generate.push({ ...base, id: id + '_nb', replaces: id, pass: 'nb', prompt: `${prompt} ${NB}` });
}
const tids = new Set(m.textures.map((t) => t.id));
for (const [id, prompt] of Object.entries(tex)) {
  const base = m.textures.find((t) => t.id === id);
  if (!tids.has(id + '_nb')) m.textures.push({ ...base, id: id + '_nb', prompt: `${prompt} ${NB}` });
}
writeFileSync(f, JSON.stringify(m, null, 2));
console.log([...Object.keys(props), ...Object.keys(tex)].map((k) => k + '_nb').join(','));
