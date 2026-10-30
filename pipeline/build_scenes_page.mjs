// Build out/scenes/index.html: one tab per scene (shots, stills, assets, process) plus an overview.
// Every derived file lands in out/scenes/img and is rebuilt only when its source is newer.
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync, existsSync, statSync, readdirSync } from "node:fs";
import { join, sep } from "node:path";

const ROOT = join(import.meta.dirname, "..");
const OUT = join(ROOT, "out/scenes");
const IMG = join(OUT, "img");
const FF = process.env.FFMPEG || "ffmpeg";
mkdirSync(IMG, { recursive: true });

// Rebuild a derived file when it's missing or older than any of its sources (renders get replaced in place).
const stale = (srcs, dst) => !existsSync(dst) || [srcs].flat().some((s) => existsSync(s) && statSync(dst).mtimeMs < statSync(s).mtimeMs);
const ff = (args) => execFileSync(FF, ["-v", "error", "-y", ...args]);
const jpg = (src, name, w) => {
  const dst = join(IMG, name + ".jpg");
  if (stale(src, dst)) ff(["-i", src, "-vf", `scale=${w}:-2`, "-q:v", "3", dst]);
  return `img/${name}.jpg`;
};
const mp4 = (src, name) => {
  const dst = join(IMG, name + ".mp4");
  // The clips are already H.264 yuv420p, so copy with faststart.
  if (stale(src, dst)) ff(["-i", src, "-an", "-c:v", "copy", "-movflags", "+faststart", dst]);
  return `img/${name}.mp4`;
};
const poster = (src, name) => {
  const dst = join(IMG, name + "_poster.jpg");
  if (stale(src, dst)) ff(["-ss", "1.2", "-i", src, "-frames:v", "1", "-vf", "scale=960:-2", "-q:v", "4", dst]);
  return `img/${name}_poster.jpg`;
};

// One sprite per prop: reference | Tripo beauty | Tripo clay | Meshy beauty | Meshy clay, 360 px tiles.
// The page shows single tiles via background-position, which keeps the artifact under its file-count limit.
const TILE = 360;
const sprite = (name, tiles) => {
  const dst = join(IMG, `a_${name}.jpg`);
  if (!stale(tiles.filter(Boolean), dst)) return `img/a_${name}.jpg`;
  const args = [], chains = [];
  tiles.forEach((t, i) => {
    if (t) args.push("-i", t);
    else args.push("-f", "lavfi", "-i", `color=c=0x1d1b19:s=${TILE}x${TILE}:d=1`);
    chains.push(`[${i}:v]scale=${TILE}:${TILE}:force_original_aspect_ratio=decrease,pad=${TILE}:${TILE}:-1:-1:color=0x1d1b19,setsar=1,format=yuv420p[t${i}]`);
  });
  ff([...args, "-filter_complex", `${chains.join(";")};${tiles.map((_, i) => `[t${i}]`).join("")}hstack=inputs=${tiles.length}`, "-frames:v", "1", "-q:v", "4", dst]);
  return `img/a_${name}.jpg`;
};

const REFS = readdirSync(join(ROOT, "refs"), { recursive: true }).map((f) => String(f).split(sep).join("/")).filter((f) => f.endsWith("_0.png"));
const findRef = (ids) => { const r = REFS.find((f) => ids.some((id) => f.endsWith("/" + id + "_0.png"))); return r && join(ROOT, "refs", r); };
const findRender = (scene, model, ids, view) => {
  for (const dir of [`scenes/${FOLDER[scene]}/compare/${model}`, `out/compare/${model}`])
    for (const id of ids) { const f = join(ROOT, dir, `${id}_${view}.png`); if (existsSync(f)) return f; }
};

const spendRows = readFileSync(join(ROOT, "generate/spend.jsonl"), "utf8").trim().split("\n").map((l) => JSON.parse(l));
const spendFor = (id) => spendRows.filter((r) => (r.out || "").includes(id)).reduce((s, r) => s + r.est_usd, 0);
const spendShared = spendRows.filter((r) => !/ramen|repair/.test(r.out || "")).reduce((s, r) => s + r.est_usd, 0);

// Scene id (the prefix on its asset ids) -> its folder under scenes/.
const FOLDER = { repair: "tokyo-electronics-repair", ramen: "tokyo-ramen-shop" };

const SCENES = [
  {
    id: "repair", title: "Electronics repair, late night", short: "Repair shop", kicker: "Scene 01",
    dir: "scenes/tokyo-electronics-repair/out", shotDir: (n) => `${n}_graded.mp4`,
    blurb: "A narrow Tokyo repair counter after hours: racks of tagged jobs, a parts-drawer wall, one clamp lamp on at the bench and rain on the storefront.",
    heroes: [["hero_wide.png", "hero_wide_v1.png", "The shop from the back — rain on the storefront, one lamp on at the bench"], ["hero_bench.png", "hero_bench_v1.png", "The bench — scripted CRT graticule, helping-hands lens rebuilt as glass"]],
    clip: ["clip.mp4", "Round 1 handheld push, back of the shop to the bench (1080p)"],
    r2: [
      ["process_r2_passA_wide.png", "Pass A — mid props: boxed jobs, parts cart, second station"],
      ["process_r2_passA_wide_clay.png", "Pass A, clay"],
      ["process_r2_passB_wide.png", "Pass B — small clutter: screws, PCBs, cups, tape"],
      ["process_r2_passB_wide_clay.png", "Pass B, clay"],
      ["process_r2_passC_wide.png", "Pass C — cables, notes, flyers, price tags"],
      ["process_r2_passC_bench.png", "Pass C at the bench"],
    ],
    r1: [
      ["process_01_shell_clay.png", "Scripted shell, clay"],
      ["process_02_dress_pass1.png", "Dress pass 1 — benches, racks"],
      ["process_02_dress_pass3.png", "Dress pass 3 — small props"],
      ["process_04_bench_repairs.png", "Script repairs on the bench"],
      ["process_03_lighting_first_pass.png", "Lighting, first pass"],
      ["process_05_lighting_balanced.png", "Lighting, balanced"],
      ["process_00_prop_refs.png", "GPT Image 2.5 prop references"],
      ["process_00_compare_tripo_vs_meshy.png", "Tripo H3.1 vs Meshy pick sheet"],
    ],
    weak: [
      "The two TVs left on still show a flat no-signal blue.",
      "s1's interior through the glass is busy and low-contrast at 18 mm.",
      "In the bench still the lamp arm cuts into the right edge of frame.",
      "A few generated props were picked but not placed (magnifier lamp, parts bins, ribbon cables).",
    ],
  },
  {
    id: "ramen", title: "Ramen shop, after close", short: "Ramen shop", kicker: "Scene 02",
    dir: "scenes/tokyo-ramen-shop/out", shotDir: (n) => `${n}/${n}_graded.mp4`,
    blurb: "An eight-stool ramen counter at closing: stockpots still steaming, the ticket machine glowing by the door, rain on the street outside.",
    heroes: [["hero_wide.png", "hero_wide_v1.png", "Down the aisle — 食券 machine, ラーメン lantern against the rain"], ["hero_counter.png", "hero_counter_v1.png", "Seated at the counter — last bowl, steam rolling off the pass"]],
    clip: ["clip.mp4", "Round 1 handheld push down the aisle (720p)"],
    r2: [
      ["process/r2_passA.png", "Pass A — mid props: pots, bowl stacks, kitchen gear"],
      ["process/r2_passB.png", "Pass B — small clutter: ladles, towels, slips"],
      ["process/r2_passC.png", "Pass C — micro: cords, flyers, stickers"],
      ["process/r2_grime.png", "Grime — grease film, stains, worn edges"],
      ["process/r2_steam.png", "Steam — Mantaflow plumes off pots and bowl"],
      ["process/r2_exterior_from_inside.png", "Exterior relit — street through the door"],
      ["process/r2_generated_props.png", "Generated props swapped in"],
    ],
    r1: [
      ["process/01_shell_clay.png", "Scripted shell, clay"],
      ["process/02_shell_lit.png", "Shell, first light"],
      ["process/03_dressing_partial.png", "Dressing — big props first"],
      ["process/04_dressing_full_plus_top.png", "Fully dressed + top view"],
      ["process/08_clay_dressed.png", "Dressed, clay check"],
      ["process/05_lighting_fixed.png", "Night lighting fixed"],
      ["process/06_lookdev_graded.png", "Look-dev, graded"],
      ["process/00_prop_refs.png", "GPT Image 2.5 prop references"],
    ],
    weak: [
      "First second of exterior_establish: a band of out-of-focus rain streaks (fix queued).",
      "Steam volumes don't motion-blur; the kitchen haze can read as a flat wall from the counter.",
      "A few small props float 2–8 cm above their surface.",
      "Round-1 props still carry real brands (Kirin crate and fridge, Sapporo poster, Kikkoman).",
    ],
  },
];

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
const pretty = (k, id) => k.replace(new RegExp(`^${id}_`), "").replace(/_nb$/, "").replace(/_/g, " ");
const MODEL = { "tripo-h31": "Tripo H3.1", meshy: "Meshy 7.1", none: "Not used" };

const totals = { "tripo-h31": 0, meshy: 0 };
const built = SCENES.map((s) => {
  // ---- assets
  const picks = JSON.parse(readFileSync(join(ROOT, `scenes/${FOLDER[s.id]}/picks.json`), "utf8"));
  const keys = Object.keys(picks).filter((k) => !k.startsWith("_") && picks[k]?.model);
  const assets = keys.map((k) => {
    const v = picks[k], ids = [k, `${s.id}_${k}`];
    const superseded = keys.includes(`${k}_nb`);
    const used = v.model !== "none" && !v.retired && !superseded;
    const tiles = [findRef(ids), findRender(s.id, "tripo-h31", ids, "beauty"), findRender(s.id, "tripo-h31", ids, "clay"), findRender(s.id, "meshy", ids, "beauty"), findRender(s.id, "meshy", ids, "clay")];
    if (used) totals[v.model] = (totals[v.model] || 0) + 1;
    return {
      k, name: pretty(k, s.id), model: v.model, used, why: v.why || v.reason || "",
      flags: [k.endsWith("_nb") || v.debranded ? "de-branded" : "", v.retired ? "retired" : "", superseded ? "replaced by de-branded" : ""].filter(Boolean),
      has: { t: !!tiles[1], m: !!tiles[3] }, src: sprite(`${s.id}_${k}`, tiles),
    };
  }).sort((a, b) => b.used - a.used || a.name.localeCompare(b.name));
  const n = { "tripo-h31": 0, meshy: 0, unused: 0 };
  assets.forEach((a) => (a.used ? n[a.model]++ : n.unused++));

  // ---- shots, from shots.json so unrendered ones still show up
  const def = JSON.parse(readFileSync(join(ROOT, `scenes/${FOLDER[s.id]}/shots.json`), "utf8"));
  const fps = def.defaults?.fps || 24;
  const shots = def.shots.map((sh) => {
    const src = join(ROOT, s.dir, "shots", s.shotDir(sh.name));
    const lenses = (sh.keys || []).map((k) => k.lens).filter(Boolean);
    const lens = lenses.length ? (lenses.at(-1) !== lenses[0] ? `${lenses[0]}→${lenses.at(-1)} mm` : `${lenses[0]} mm`) : "";
    const frames = sh.frames || def.defaults?.frames || 96;
    const handheld = /^h\d/.test(sh.name) || sh.handheld?.profile === "walk";
    const ready = existsSync(src);
    return {
      name: sh.name, handheld, ready,
      label: sh.name.replace(/^[sh]\d+_/, "").replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()), code: sh.name.match(/^[sh]\d+/)?.[0] || "",
      meta: [lens, `f/${sh.fstop ?? def.defaults?.fstop ?? 2.8}`, `${(frames / fps).toFixed(1)} s`, (sh.move || "").replace(/_/g, " "), sh.focus?.mode ? `${sh.focus.mode} focus` : ""].filter(Boolean),
      video: ready && mp4(src, `${s.id}_shot_${sh.name}`), poster: ready && poster(src, `${s.id}_shot_${sh.name}`),
    };
  });
  const clipSrc = join(ROOT, s.dir, s.clip[0]);
  const clip = { name: "round1_clip", label: "Round 1 clip", code: "r1", handheld: true, ready: true, meta: [s.clip[1]], video: mp4(clipSrc, `${s.id}_clip`), poster: poster(clipSrc, `${s.id}_clip`) };

  return {
    ...s, assets, n, shots, clip,
    spend: spendFor(s.id),
    heroes: s.heroes.map(([now, v1, cap], i) => ({ cap, now: jpg(join(ROOT, s.dir, now), `${s.id}_hero${i}`, 1920), v1: jpg(join(ROOT, s.dir, v1), `${s.id}_v1_${i}`, 1920) })),
    r2: s.r2.map(([f, cap], i) => ({ cap, src: jpg(join(ROOT, s.dir, f), `${s.id}_r2_${i}`, 1200) })),
    r1: s.r1.map(([f, cap], i) => ({ cap, src: jpg(join(ROOT, s.dir, f), `${s.id}_p${i}`, 1200) })),
  };
});

// ---------------------------------------------------------------- markup
const shotCard = (sh, id) => sh.ready
  ? `<figure class="shot"><video src="${sh.video}" poster="${sh.poster}" controls muted loop playsinline preload="none"></video>
      <figcaption><b><span>${esc(sh.code)}</span>${esc(sh.label)}</b><small>${sh.meta.map(esc).join(" · ")}</small></figcaption></figure>`
  : `<figure class="shot pending"><div class="ph"><span>In the render queue</span></div>
      <figcaption><b><span>${esc(sh.code)}</span>${esc(sh.label)}</b><small>${sh.meta.map(esc).join(" · ")}</small></figcaption></figure>`;

const assetCard = (a) => {
  const tile = (i, label, win, missing) => `<div class="tile${win ? " win" : ""}${missing ? " none" : ""}" data-i="${i}"><i data-bg="${a.src}"></i><span>${label}${win ? " · picked" : ""}</span>${missing ? "<em>no mesh</em>" : ""}</div>`;
  return `<article class="asset" data-model="${a.used ? a.model : "unused"}" data-name="${esc(a.name)}" data-src="${a.src}">
    <header><h4>${esc(a.name)}</h4><span class="tag ${a.used ? (a.model === "meshy" ? "m" : "t") : "u"}">${a.used ? MODEL[a.model] : "Not used"}</span></header>
    <div class="tiles">${tile(0, "Reference", false, false)}${tile(1, "Tripo H3.1", a.used && a.model === "tripo-h31", !a.has.t)}${tile(3, "Meshy 7.1", a.used && a.model === "meshy", !a.has.m)}</div>
    <p>${esc(a.why)}${a.flags.length ? ` <span class="flags">${a.flags.map(esc).join(" · ")}</span>` : ""}</p>
  </article>`;
};

const strip = (items, mark) => items.map((p, i) => `<figure><img src="${p.src}" alt="${esc(p.cap)}" loading="lazy" data-zoom><figcaption><span>${mark(i)}</span>${esc(p.cap)}</figcaption></figure>`).join("");

const sceneView = (s) => {
  const hand = [...s.shots.filter((x) => x.handheld), s.clip], cine = s.shots.filter((x) => !x.handheld);
  const readyCount = s.shots.filter((x) => x.ready).length;
  return `
<section class="view" id="v-${s.id}" data-view="${s.id}" hidden>
  <header class="shead">
    <div><p class="kicker">${s.kicker}</p><h2>${esc(s.title)}</h2><p class="lede">${esc(s.blurb)}</p></div>
    <dl class="facts">
      <div><dt>Shots</dt><dd>${readyCount}<small>/${s.shots.length}</small></dd></div>
      <div><dt>Props placed</dt><dd>${s.n["tripo-h31"] + s.n.meshy}</dd></div>
      <div><dt>Tripo H3.1</dt><dd class="t">${s.n["tripo-h31"]}</dd></div>
      <div><dt>Meshy 7.1</dt><dd class="m">${s.n.meshy}</dd></div>
      <div><dt>fal spend</dt><dd>$${s.spend.toFixed(0)}</dd></div>
    </dl>
  </header>
  <nav class="sub" aria-label="${esc(s.short)} sections"><a href="#${s.id}-shots">Shots</a><a href="#${s.id}-stills">Stills</a><a href="#${s.id}-assets">Assets <small>${s.assets.length}</small></a><a href="#${s.id}-process">Process</a></nav>

  <section id="${s.id}-shots" class="block">
    <h3>Handheld <small>walkthroughs — an operator moving through the room</small></h3>
    <div class="shots">${hand.map((x) => shotCard(x, s.id)).join("")}</div>
    <h3>Cinematic <small>camera rig — lens, focus pulls, dollies, dolly zooms · 2.39</small></h3>
    <div class="shots">${cine.map((x) => shotCard(x, s.id)).join("")}</div>
  </section>

  <section id="${s.id}-stills" class="block">
    <h3>Stills <small>drag to compare with round 1</small></h3>
    ${s.heroes.map((h) => `<figure class="ba" style="--x:50%">
      <img src="${h.now}" alt="${esc(h.cap)}" loading="lazy" data-zoom>
      <img class="before" src="${h.v1}" alt="Round 1 version" loading="lazy">
      <input type="range" min="0" max="100" value="50" aria-label="Compare with round 1">
      <span class="lab l">Round 1</span><span class="lab r">Round 2</span>
      <figcaption>${esc(h.cap)}</figcaption></figure>`).join("")}
  </section>

  <section id="${s.id}-assets" class="block assets-block">
    <h3>Assets <small>every prop generated by both Tripo H3.1 and Meshy 7.1 from one GPT Image 2.5 reference</small></h3>
    <div class="controls">
      <div class="seg" role="group" aria-label="Filter by winner">
        <button data-f="all" aria-pressed="true">All <small>${s.assets.length}</small></button>
        <button data-f="tripo-h31" aria-pressed="false">Tripo wins <small>${s.n["tripo-h31"]}</small></button>
        <button data-f="meshy" aria-pressed="false">Meshy wins <small>${s.n.meshy}</small></button>
        <button data-f="unused" aria-pressed="false">Not used <small>${s.n.unused}</small></button>
      </div>
      <div class="seg" role="group" aria-label="Render view">
        <button data-v="beauty" aria-pressed="true">Textured</button><button data-v="clay" aria-pressed="false">Clay</button>
      </div>
      <input type="search" placeholder="Find a prop" aria-label="Find a prop">
    </div>
    <div class="agrid">${s.assets.map(assetCard).join("")}</div>
  </section>

  <section id="${s.id}-process" class="block">
    <h3>Round 2 <small>coarse → fine dressing passes, grime, effects</small></h3>
    <div class="strip">${strip(s.r2, (i) => String(i + 1).padStart(2, "0"))}</div>
    <h3>Round 1 <small>the original build</small></h3>
    <div class="strip">${strip(s.r1, (i) => String(i + 1).padStart(2, "0"))}</div>
    <div class="weak"><h3>Still weak</h3><ul>${s.weak.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></div>
  </section>
</section>`;
};

const all = totals.meshy + totals["tripo-h31"];
const spendTotal = built.reduce((t, s) => t + s.spend, 0) + spendShared;
const overview = `
<section class="view" id="v-overview" data-view="overview">
  <p class="lede big">Two late-night Tokyo interiors built end to end by two agents in parallel. Rooms, counters and fixtures are scripted in Blender; every prop was generated by both Tripo H3.1 and Meshy 7.1 from a GPT Image 2.5 reference, and the better mesh was kept.</p>
  <ol class="pipe"><li>concept</li><li>scripted shell</li><li>refs per prop</li><li>Tripo + Meshy</li><li>pick &amp; script-repair</li><li>dress big → small</li><li>grime</li><li>night light + haze</li><li>camera rig</li><li>grade</li></ol>
  <div class="cards">${built.map((s) => `
    <a class="scard" href="#${s.id}">
      <img src="${s.heroes[0].now}" alt="${esc(s.heroes[0].cap)}">
      <div><p class="kicker">${s.kicker}</p><h2>${esc(s.title)}</h2>
      <p class="mono">${s.shots.filter((x) => x.ready).length} shots · ${s.n["tripo-h31"] + s.n.meshy} props · $${s.spend.toFixed(0)} fal</p></div>
    </a>`).join("")}
  </div>
  <div class="verdicts">
    <div class="verdict"><p class="kicker">Generator verdict</p><p><strong>Across ${all} placed props: Meshy ${totals.meshy}, Tripo H3.1 ${totals["tripo-h31"]}.</strong> Tripo keeps the big hard-surface heroes where real geometry matters (oscilloscope, stockpots, ticket machine, cash register). Meshy wins most small consumer items because its textures and printed labels are sharper. Glass came back opaque from both and was rebuilt by script.</p></div>
    <div class="verdict"><p class="kicker">Round 2</p><p>Both rooms re-dressed in coarse → fine passes, with grime and grease, Mantaflow steam in the ramen kitchen, relit streets, a validator that catches mesh collisions, real brands painted out or regenerated, and a camera rig with per-shot lenses, focus pulls and dolly zooms. Handheld walkthroughs are rendering now. Total fal spend so far: <strong>$${spendTotal.toFixed(0)}</strong>.</p></div>
  </div>
</section>`;

const DARK = "--bg:#0f0e0d;--fg:#ece8df;--mute:#9a9385;--line:#2a2724;--card:#171513;--accent:#ff6a48;--tripo:#8fb8e4;--meshy:#f0a868;--tbg:#1b2733;--mbg:#33241a;--ubg:#26231f;--tile:#1d1b19;color-scheme:dark";
const html = `<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Night Shops</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;800&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{--bg:#f3f1ec;--fg:#1b1a18;--mute:#6b665c;--line:#d9d4c8;--card:#fbfaf6;--accent:#c2361f;--tripo:#2c5d8f;--meshy:#a3591a;--tbg:#e3ecf5;--mbg:#f6e8da;--ubg:#ebe7de;--tile:#1d1b19}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){${DARK}}}
:root[data-theme="dark"]{${DARK}}
body{background:var(--bg);color:var(--fg);font:15px/1.55 Archivo,system-ui,sans-serif}
body::before{content:"";position:fixed;inset:0 0 auto;height:env(safe-area-inset-top,0px);z-index:10;background:var(--bg)}
.wrap{max-width:1280px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:28px 80px}
.mono,.kicker,dt,figcaption span,.tag,.seg,.sub,.tile span,h3 small,.flags{font-family:"IBM Plex Mono",ui-monospace,monospace}
h1{font-size:clamp(30px,5vw,52px);font-weight:800;letter-spacing:-.02em;line-height:1;margin:0;text-wrap:balance}
h2{font-size:clamp(24px,3.4vw,38px);font-weight:800;letter-spacing:-.01em;margin:0;line-height:1.1;text-wrap:balance}
h3{font-size:13px;text-transform:uppercase;letter-spacing:.12em;color:var(--fg);margin:40px 0 14px;font-weight:600;display:flex;flex-wrap:wrap;gap:4px 12px;align-items:baseline}
h3 small{color:var(--mute);letter-spacing:0;text-transform:none;font-weight:400;font-size:12px}
.lede{max-width:66ch;color:var(--mute);margin:10px 0 0}.lede.big{font-size:17px;margin:0}
.kicker{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);margin:0 0 6px}
/* top bar */
.top{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--bg);border-bottom:1px solid var(--line);margin-bottom:28px}
.top .in{max-width:1280px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:14px;display:flex;flex-wrap:wrap;gap:12px 28px;align-items:center;justify-content:space-between}
.tabs{display:flex;flex-wrap:wrap;gap:4px}
.tabs a{color:var(--mute);text-decoration:none;padding:7px 12px;border-radius:6px;font-weight:600;font-size:14px}
.tabs a[aria-current="page"]{background:var(--fg);color:var(--bg)}
.tabs a:not([aria-current="page"]):hover{color:var(--fg)}
.tabs a.ext{font-weight:400}
@media (max-width:700px){.top{position:static}.top .kicker{display:none}.block{scroll-margin-top:16px}}
/* overview */
.pipe{display:flex;flex-wrap:wrap;gap:6px;margin:18px 0 0;padding:0;list-style:none;font:12px "IBM Plex Mono",monospace;color:var(--mute)}
.pipe li:not(:last-child)::after{content:"→";margin-left:6px;color:var(--line)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:20px;margin-top:28px}
.scard{display:grid;gap:14px;color:inherit;text-decoration:none;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden;padding-bottom:18px}
.scard img{width:100%;aspect-ratio:16/9;object-fit:cover;display:block;max-width:100%}
.scard>div{padding-inline:18px}.scard .mono{font-size:12px;color:var(--mute);margin:8px 0 0}
.scard:hover{border-color:var(--accent)}
.verdicts{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,440px),1fr));gap:20px;margin-top:20px}
.verdict{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--accent);padding:16px 18px;border-radius:6px}
.verdict p{margin:0}.verdict .kicker{margin-bottom:8px}
/* scene header */
.shead{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:end;gap:20px}
.shead>div{min-width:0;flex:1 1 420px}
.facts{display:flex;flex-wrap:wrap;gap:22px;margin:0}
dt{font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:var(--mute)}dd{margin:0;font-size:26px;font-weight:800}
dd small{font-size:14px;color:var(--mute);font-weight:400}dd.t{color:var(--tripo)}dd.m{color:var(--meshy)}
.sub{display:flex;flex-wrap:wrap;gap:6px;margin:26px 0 0;font-size:13px}
.sub a{color:var(--fg);text-decoration:none;border:1px solid var(--line);padding:6px 12px;border-radius:999px}
.sub a:hover{border-color:var(--accent)}.sub small{color:var(--mute)}
.block{scroll-margin-top:150px}
figure{margin:0}
figcaption{font-size:13px;color:var(--mute);padding-top:8px}
figcaption span{color:var(--accent);margin-right:8px}
/* shots */
.shots{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,480px),1fr));gap:22px 18px}
.shot video,.ph{width:100%;display:block;border-radius:6px;background:#000;aspect-ratio:2.39;max-width:100%}
.shot figcaption{display:grid;gap:2px}.shot b{color:var(--fg);font-weight:600}
.shot small{font:12px "IBM Plex Mono",monospace}
.ph{display:grid;place-items:center;background:repeating-linear-gradient(135deg,var(--card) 0 10px,var(--bg) 10px 20px);border:1px dashed var(--line)}
.ph span{font:12px "IBM Plex Mono",monospace;color:var(--mute)}
/* before / after */
.ba{position:relative;margin-bottom:26px}
.ba img{width:100%;display:block;border-radius:6px;aspect-ratio:16/9;object-fit:cover;max-width:100%}
.ba .before{position:absolute;inset:0;clip-path:inset(0 calc(100% - var(--x)) 0 0);height:auto;pointer-events:none}
.ba::after{content:"";position:absolute;top:0;left:var(--x);width:2px;margin-left:-1px;background:#fff;opacity:.85;pointer-events:none;aspect-ratio:auto;height:calc(100% - 2.6em)}
.ba input{position:absolute;inset:0 0 auto;width:100%;aspect-ratio:16/9;margin:0;opacity:0;cursor:ew-resize}
.ba .lab{position:absolute;top:10px;font:11px "IBM Plex Mono",monospace;color:#fff;background:rgba(0,0,0,.55);padding:3px 7px;border-radius:3px;pointer-events:none}
.ba .l{left:10px}.ba .r{right:10px}
/* assets */
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:16px}
.seg{display:inline-flex;flex-wrap:wrap;border:1px solid var(--line);border-radius:6px;overflow:hidden;font-size:12px}
.seg button{all:unset;cursor:pointer;padding:7px 11px;color:var(--mute)}
.seg button small{opacity:.7}
.seg button[aria-pressed="true"]{background:var(--fg);color:var(--bg)}
.seg button:focus-visible,.controls input:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.controls input{font:inherit;font-size:13px;padding:7px 10px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);min-width:0;flex:1 1 160px;max-width:260px}
.agrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,330px),1fr));gap:14px}
.asset{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;display:grid;gap:10px;align-content:start;cursor:zoom-in}
.asset:hover{border-color:var(--mute)}
.asset header{display:flex;justify-content:space-between;align-items:start;gap:8px}
.asset h4{margin:0;font-size:15px;font-weight:600;text-transform:capitalize;min-width:0}
.asset p{margin:0;font-size:13px;color:var(--mute);line-height:1.45}
.flags{display:block;margin-top:4px;font-size:11px;color:var(--accent)}
.tiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}
.tile{position:relative;border-radius:5px;overflow:hidden;background:var(--tile);outline:2px solid transparent;outline-offset:-2px}
.tile i{display:block;aspect-ratio:1;background-size:500% 100%;background-repeat:no-repeat;background-position:var(--p,0) 0}
.tile[data-i="1"] i{--p:25%}.tile[data-i="3"] i{--p:75%}
.clay .tile[data-i="1"] i{--p:50%}.clay .tile[data-i="3"] i{--p:100%}
.tile span{position:absolute;left:0;right:0;bottom:0;font-size:10px;padding:3px 5px;color:#fff;background:linear-gradient(transparent,rgba(0,0,0,.7));white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tile.win{outline-color:var(--accent)}
.tile.win span{background:var(--accent)}
.tile.none em{position:absolute;inset:0;display:grid;place-items:center;font:11px "IBM Plex Mono",monospace;color:#8a8379;font-style:normal}
.tag{font-size:11px;padding:2px 7px;border-radius:3px;white-space:nowrap}
.tag.t{background:var(--tbg);color:var(--tripo)}.tag.m{background:var(--mbg);color:var(--meshy)}.tag.u{background:var(--ubg);color:var(--mute)}
.asset[hidden]{display:none}
/* process */
.strip{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,280px),1fr));gap:14px}
.strip img{width:100%;border-radius:4px;display:block;aspect-ratio:16/9;object-fit:cover;cursor:zoom-in;max-width:100%}
.weak ul{margin:0;padding-left:18px;display:grid;gap:8px;max-width:80ch}
dialog{border:0;padding:0;background:transparent;max-width:96vw}dialog::backdrop{background:rgba(0,0,0,.9)}
dialog img{max-width:96vw;max-height:88vh;display:block;margin:auto}
dialog p{color:#ddd;font:12px "IBM Plex Mono",monospace;text-align:center;margin:10px 0 0}
</style>
<div class="top"><div class="in">
  <div><p class="kicker" style="margin:0 0 2px">Blender 5.0 · Cycles · GPT Image 2.5 · Tripo H3.1 + Meshy 7.1</p><h1>Night Shops</h1></div>
  <nav class="tabs" aria-label="Scenes"><a href="#overview">Overview</a>${built.map((s) => `<a href="#${s.id}">${esc(s.short)}</a>`).join("")}<a class="ext" href="https://claude.ai/artifact/5mk8VH8hkEbYfucp57z3FJ">Generator test ↗</a></nav>
</div></div>
<div class="wrap">
${overview}
${built.map(sceneView).join("")}
</div>
<dialog id="lb"><img alt=""><p></p></dialog>
<script>
const views=[...document.querySelectorAll(".view")];
function route(){
  const h=location.hash.slice(1)||"overview";
  const scene=h.split("-")[0];
  const v=views.find(x=>x.dataset.view===scene)||views[0];
  views.forEach(x=>x.hidden=x!==v);
  document.querySelectorAll(".tabs a").forEach(a=>a.getAttribute("href")==="#"+v.dataset.view?a.setAttribute("aria-current","page"):a.removeAttribute("aria-current"));
  if(h.includes("-")){const t=document.getElementById(h);if(t)requestAnimationFrame(()=>t.scrollIntoView())}else scrollTo(0,0);
  v.querySelectorAll("video").forEach(()=>{});
  lazy(v);
}
// sprite backgrounds load only when a card scrolls near the viewport
const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){const i=e.target;i.style.backgroundImage="url("+i.dataset.bg+")";io.unobserve(i)}}),{rootMargin:"400px"});
function lazy(v){v.querySelectorAll(".tile i[data-bg]").forEach(i=>{if(!i.style.backgroundImage)io.observe(i)})}
addEventListener("hashchange",route);route();
// pause other videos when one plays
document.addEventListener("play",e=>document.querySelectorAll("video").forEach(v=>v!==e.target&&v.pause()),true);
// before/after
document.querySelectorAll(".ba input").forEach(r=>r.addEventListener("input",()=>r.parentElement.style.setProperty("--x",r.value+"%")));
// asset filters
document.querySelectorAll(".assets-block").forEach(b=>{
  let f="all",q="";
  const cards=[...b.querySelectorAll(".asset")],grid=b.querySelector(".agrid");
  const apply=()=>{cards.forEach(c=>c.hidden=!((f==="all"||c.dataset.model===f)&&c.dataset.name.includes(q)));lazy(b)};
  b.querySelectorAll("[data-f]").forEach(x=>x.onclick=()=>{f=x.dataset.f;b.querySelectorAll("[data-f]").forEach(y=>y.setAttribute("aria-pressed",y===x));apply()});
  b.querySelectorAll("[data-v]").forEach(x=>x.onclick=()=>{grid.classList.toggle("clay",x.dataset.v==="clay");b.querySelectorAll("[data-v]").forEach(y=>y.setAttribute("aria-pressed",y===x))});
  b.querySelector("input[type=search]").oninput=e=>{q=e.target.value.trim().toLowerCase();apply()};
});
// lightbox: stills and process images, or a prop's full sheet
const lb=document.getElementById("lb"),li=lb.querySelector("img"),lp=lb.querySelector("p");
document.addEventListener("click",e=>{
  const z=e.target.closest("[data-zoom]"),a=e.target.closest(".asset");
  if(z&&!z.closest(".ba")){li.src=z.src;lp.textContent=z.alt;lb.showModal()}
  else if(a){li.src=a.dataset.src;lp.textContent=a.dataset.name+" — reference · Tripo textured · Tripo clay · Meshy textured · Meshy clay";lb.showModal()}
});
lb.addEventListener("click",()=>lb.close());
</script>`;
writeFileSync(join(OUT, "index.html"), html);
const files = readdirSync(IMG);
console.log("ok", totals, `${files.length} img files`, `${(files.reduce((t, f) => t + statSync(join(IMG, f)).size, 0) / 1e6).toFixed(1)} MB`);
