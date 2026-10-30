// Builds out/page/index.html + jpgs from out/compare (render_compare.py) and out/compare/verdicts.json.
//   node pipeline/build_compare_page.mjs
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const FF = process.env.FFMPEG || 'ffmpeg';
const CMP = 'out/compare';
const PAGE = 'out/page';
const MODELS = [
  ['tripo-h31', 'Tripo H3.1', 'detailed geometry + texture'],
  ['tripo-p2', 'Tripo P2', 'extreme texture, delit'],
  ['meshy', 'Meshy 7.1', '4k geometry, PBR'],
];
const PROPS = [
  ['oscilloscope', 'CRT oscilloscope', 'repair', 'hard surface, panel labels'],
  ['solder_station', 'Soldering station', 'repair', 'thin cable, coiled holder'],
  ['helping_hands', 'Helping hands', 'repair', 'wiry arms, glass lens'],
  ['boombox_open', 'Open boombox', 'repair', 'exposed internals'],
  ['stockpot', 'Stockpot', 'ramen', 'dented metal'],
  ['ticket_machine', 'Ticket machine', 'ramen', 'dense printed buttons'],
  ['condiment_caddy', 'Condiment caddy', 'ramen', 'glass and liquid'],
  ['lantern', 'Akachochin lantern', 'ramen', 'ribbed paper, kanji'],
];
const VIEWS = ['beauty', 'back', 'clay'];

const stats = JSON.parse(readFileSync(join(CMP, 'stats.json'), 'utf8'));
const verdicts = existsSync(join(CMP, 'verdicts.json')) ? JSON.parse(readFileSync(join(CMP, 'verdicts.json'), 'utf8')) : {};
const files = {};
const jpg = (src, dst, w) => {
  mkdirSync(join(PAGE, 'img'), { recursive: true });
  execFileSync(FF, ['-v', 'error', '-y', '-i', src, '-vf', `scale=${w}:-1`, '-q:v', '4', join(PAGE, dst)]);
  files[dst] = join(PAGE, dst);
};

const CONCEPTS = [
  ['repair', 'wide', 'Repair shop, wide'], ['repair', 'detail', 'Repair bench, close'],
  ['ramen', 'wide', 'Ramen shop, wide'], ['ramen', 'detail', 'Ramen counter, close'],
];
for (const [s, k] of CONCEPTS) jpg(`refs/${s}/concept_${k}_sunburst_0.png`, `img/concept_${s}_${k}.jpg`, 1100);

for (const [p] of PROPS) {
  jpg(`refs/props/${p}_0.png`, `img/${p}_ref.jpg`, 640);
  for (const [m] of MODELS) for (const v of VIEWS) {
    const src = join(CMP, m, `${p}_${v}.png`);
    if (existsSync(src)) jpg(src, `img/${p}_${m}_${v}.jpg`, 640);
  }
}

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const kfmt = (n) => (n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? Math.round(n / 1e3) + 'k' : n);
// Texture maps named by the glTF image name prefix (Color / ORM / NormalGL / ...), with the largest edge size.
const texSummary = (imgs = {}) => {
  const ents = Object.entries(imgs);
  if (!ents.length) return 'no textures';
  return ents.map(([name, i]) => `${name.split(/[_.]/)[0].replace('NormalGL', 'Normal').replace('Color', 'Albedo')} ${i.size[0] / 1024}K`).join(' · ');
};
const gen = existsSync(join(CMP, 'gen.json')) ? JSON.parse(readFileSync(join(CMP, 'gen.json'), 'utf8')) : {};

const score = { 'tripo-h31': 0, 'tripo-p2': 0, meshy: 0 };
for (const v of Object.values(verdicts.props ?? {})) if (v.winner in score) score[v.winner]++;

const rows = PROPS.map(([p, name, scene, stress]) => {
  const v = verdicts.props?.[p] ?? {};
  const cells = MODELS.map(([m, label]) => {
    const s = stats[m]?.[p];
    const imgs = VIEWS.map((view) => `<img data-view="${view}" ${view === 'beauty' ? '' : 'hidden'} src="img/${p}_${m}_${view}.jpg" alt="${esc(label)} ${esc(name)}, ${view}" loading="lazy">`).join('');
    const meta = !s ? '<span class="bad">not generated</span>' : s.error ? `<span class="bad">import failed</span>` :
      `<span>${kfmt(s.tris)} tris · ${gen[m]?.[p]?.mb ?? '?'} MB GLB · ${gen[m]?.[p]?.sec ?? '?'} s</span><span>${esc(texSummary(s.images))}</span><span>${s.size_m.map((x) => x.toFixed(2)).join(' × ')} m${m === 'meshy' ? ' (unscaled)' : ''}</span>`;
    const win = v.winner === m;
    return `<figure class="cell${win ? ' win' : ''}"><div class="frame">${imgs}${win ? '<span class="chip">pick</span>' : ''}</div>
      <figcaption><b>${esc(label)}</b>${meta}${v.notes?.[m] ? `<p>${esc(v.notes[m])}</p>` : ''}</figcaption></figure>`;
  }).join('');
  return `<section class="prop" id="${p}">
    <header><h2>${esc(name)}</h2><span class="tag ${scene}">${scene === 'repair' ? 'Repair bench' : 'Ramen shop'}</span><span class="stress">stress: ${esc(stress)}</span></header>
    <div class="grid"><figure class="cell ref"><div class="frame"><img src="img/${p}_ref.jpg" alt="${esc(name)} reference"></div><figcaption><b>Reference</b><span>GPT Image 2.5 Sunburst</span></figcaption></figure>${cells}</div>
  </section>`;
}).join('\n');

const html = `<title>Tripo vs Meshy Props</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: a lookdev review board. Reference on the left, three generators across; one view toggle drives every row. */
:root{
  --bg:#ecebe8;--panel:#f7f6f3;--line:#d3d1cb;--fg:#1d1e20;--mute:#66676b;--accent:#c4421a;--good:#2f7d4f;--ramen:#9a2a1c;--repair:#2a5a73;
  --display:"Archivo",system-ui,sans-serif;--mono:"IBM Plex Mono",ui-monospace,Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#17181a;--panel:#202124;--line:#34363a;--fg:#e9e8e4;--mute:#9a9ba0;--accent:#f0753f;--good:#5cc488;--ramen:#e0705f;--repair:#6fb0d2;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#17181a;--panel:#202124;--line:#34363a;--fg:#e9e8e4;--mute:#9a9ba0;--accent:#f0753f;--good:#5cc488;--ramen:#e0705f;--repair:#6fb0d2;color-scheme:dark}
body{background:var(--bg);color:var(--fg);font:14px/1.5 var(--mono);padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:28px 64px}
main{max-width:1400px;margin:0 auto;display:grid;gap:36px}
h1{font:800 clamp(28px,4vw,44px)/1.05 var(--display);letter-spacing:-.02em;margin:0;text-wrap:balance}
h2{font:700 20px/1.2 var(--display);margin:0}
.intro{display:grid;gap:14px;max-width:72ch}.intro p{margin:0;color:var(--mute)}
.board{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.score{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:14px 16px;display:grid;gap:4px}
.score b{font:800 32px/1 var(--display);font-variant-numeric:tabular-nums}.score span{color:var(--mute);font-size:12px}
.score.lead{border-color:var(--accent)}.score.lead b{color:var(--accent)}
.summary{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:16px 18px;max-width:90ch}.summary p{margin:.4em 0}
.bar{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--bg);padding-block:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;border-bottom:1px solid var(--line)}
body::before{content:"";position:fixed;inset:0 0 auto;height:env(safe-area-inset-top,0px);z-index:10;background:var(--bg)}
.bar span{color:var(--mute);font-size:12px;letter-spacing:.06em;text-transform:uppercase;margin-right:4px}
.bar button{font:500 13px var(--mono);background:var(--panel);color:var(--fg);border:1px solid var(--line);border-radius:4px;padding:6px 12px;cursor:pointer}
.bar button[aria-pressed="true"]{background:var(--fg);color:var(--bg);border-color:var(--fg)}
.bar button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.prop{display:grid;gap:12px}
.prop header{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}
.tag{font-size:11px;letter-spacing:.08em;text-transform:uppercase;font-weight:500}.tag.repair{color:var(--repair)}.tag.ramen{color:var(--ramen)}
.stress{color:var(--mute);font-size:12px}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
@media (max-width:900px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
.cell{margin:0;display:grid;gap:8px;align-content:start;min-width:0}
.frame{position:relative;aspect-ratio:1;max-width:100%;background:var(--panel);border:1px solid var(--line);border-radius:4px;overflow:hidden}
.frame img{width:100%;height:100%;object-fit:cover;display:block}
.cell.win .frame{border:2px solid var(--good)}
.chip{position:absolute;top:8px;left:8px;background:var(--good);color:var(--bg);font:500 11px var(--mono);letter-spacing:.08em;text-transform:uppercase;padding:2px 8px;border-radius:3px}
figcaption{display:grid;gap:2px;font-size:12px;color:var(--mute);font-variant-numeric:tabular-nums;min-width:0}
figcaption b{color:var(--fg);font:700 14px var(--display)}
figcaption p{margin:4px 0 0;color:var(--fg);font-size:12.5px;line-height:1.45}
.bad{color:var(--accent)}
.concepts{display:grid;gap:10px}.concepts p{margin:0;color:var(--mute);max-width:72ch}
.cgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
@media (max-width:700px){.cgrid{grid-template-columns:1fr}}
.cframe{aspect-ratio:16/9;max-width:100%;border:1px solid var(--line);border-radius:4px;overflow:hidden;background:var(--panel)}
.cframe img{width:100%;height:100%;object-fit:cover;display:block}
@media (prefers-reduced-motion:no-preference){.frame img{transition:opacity .15s}}
</style>
<main>
  <div class="intro">
    <h1>Tripo vs Meshy on late-night props</h1>
    <p>Eight props for the repair bench and ramen shop. Each one is the same GPT Image 2.5 reference through Tripo H3.1, Tripo P2 and Meshy 7.1 at their highest settings, rendered in Blender Cycles under one studio light and camera fit. Use the toggle to see the back (the side the generator had to invent) and clay with wireframe.</p>
  </div>
  <section class="concepts"><h2>Concept shots</h2><p>GPT Image 2.5 Sunburst, picked over Flare for legible Japanese signage and a more natural grade. These are the targets each scene is built toward.</p>
    <div class="cgrid">${CONCEPTS.map(([s, k, label]) => `<figure class="cell"><div class="cframe"><img src="img/concept_${s}_${k}.jpg" alt="${esc(label)} concept"></div><figcaption><b>${esc(label)}</b></figcaption></figure>`).join('')}</div>
  </section>
  <h2>Generator results</h2>
  <div class="board">${MODELS.map(([m, label, how]) => `<div class="score${score[m] === Math.max(...Object.values(score)) && score[m] > 0 ? ' lead' : ''}"><b>${score[m]}</b><span>${esc(label)} picks · ${esc(how)}</span></div>`).join('')}</div>
  ${verdicts.summary ? `<div class="summary">${verdicts.summary.map((s) => `<p>${esc(s)}</p>`).join('')}</div>` : ''}
  <div class="bar" role="group" aria-label="View"><span>View</span>
    <button id="v-beauty" data-v="beauty" aria-pressed="true">Front · textured</button>
    <button id="v-back" data-v="back" aria-pressed="false">Back · textured</button>
    <button id="v-clay" data-v="clay" aria-pressed="false">Clay + wire</button>
  </div>
  ${rows}
</main>
<script>
document.querySelectorAll('.bar button').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('.bar button').forEach(x=>x.setAttribute('aria-pressed',x===b));
  document.querySelectorAll('img[data-view]').forEach(i=>i.hidden=i.dataset.view!==b.dataset.v);
}));
</script>
`;
writeFileSync(join(PAGE, 'index.html'), html);
writeFileSync(join(PAGE, 'files.json'), JSON.stringify(files, null, 2));
console.log(`wrote ${PAGE}/index.html + ${Object.keys(files).length} images`);
