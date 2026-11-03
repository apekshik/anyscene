// Frame-accurate screen recordings of anyscene.org for the trailer: headless Chrome at 1280x720 CSS px, device scale
// 1.5 (so 1920x1080 frames), stepped 1/24 s at a time. Scrolls, the cursor and every page video are set to the exact
// frame time before each screenshot, so motion is smooth regardless of how long a screenshot takes. The cursor is
// drawn into the page; clicks are shown (a ring), never performed, so nothing is downloaded or navigated mid-shot.
//
//   node breakdown/site_rec.mjs <base url> <out dir> [segment ...]
// Needs playwright-core (any install) and Chrome; writes <out dir>/<segment>/%04d.png.
import { mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(process.env.PLAYWRIGHT_FROM || import.meta.url);
const { chromium } = require('playwright-core');
const [base = 'http://127.0.0.1:4331', outDir = 'site_rec', ...only] = process.argv.slice(2);
const FPS = 24;
const ease = (a) => (a <= 0 ? 0 : a >= 1 ? 1 : a * a * (3 - 2 * a));
const lerp = (a, b, k) => a + (b - a) * k;
// keyframed value: [[t, v], ...] eased between keys
const track = (keys) => (t) => {
  if (t <= keys[0][0]) return keys[0][1];
  for (let i = 1; i < keys.length; i++) if (t <= keys[i][0]) {
    const [t0, v0] = keys[i - 1], [t1, v1] = keys[i];
    return Array.isArray(v0) ? v0.map((x, j) => lerp(x, v1[j], ease((t - t0) / (t1 - t0)))) : lerp(v0, v1, ease((t - t0) / (t1 - t0)));
  }
  return keys.at(-1)[1];
};

// Cursor and scroll targets are element selectors resolved on the page (centre of the element, page coordinates).
const SEGMENTS = {
  home: { path: '/', secs: 6.5, waitReel: true, reelAt: 17.4, // the reel from its second caustic chamber shot, then the submarine
    scroll: [[0, 0]], cursor: [[0, [1180, 760]], [2.2, [1180, 760]], [4.6, '.hero-copy a[href="/scenes/"]']], click: 5.4 },
  scenes: { path: '/scenes/', secs: 7.5,
    scroll: [[0, 0], [2.4, 250]], cursor: [[0, [700, 640]], [2.6, '.card[href="/scenes/submarine-control-room/"] .media'], [5.0, '.card[href="/scenes/submarine-control-room/"] .media']],
    hover: 2.6, click: 6.6 },
  scene: { path: '/scenes/submarine-control-room/', secs: 9.5,
    scroll: [[0, 0], [3.2, 0], [6.8, '#downloads']], cursor: [[0, [900, 560]], [6.4, [900, 560]], [8.0, '#downloads .btn']], click: 8.7, scrollPad: 120 },
  kits: { path: '/kits/', secs: 6.0, scroll: [[0, 0], [5.6, 1500]], cursor: [[0, [1240, 760]]] },
  kit: { path: '/kits/dai-pai-dong-street-kitchen/', secs: 7.0, scroll: [[0, 0], [1.6, '.item']], scrollPad: 140,
    cursor: [[0, [900, 600]], [2.0, '.item .media'], [4.4, '.item .media'], [5.6, '.item:nth-of-type(3) .media']], hover: 2.0 },
};

const CURSOR = `<svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 24 24"><path d="M3 2l7.5 19 2.6-7.6L21 10.8z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>`;

async function record(page, name, seg) {
  const dir = join(outDir, name);
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  await page.goto(base + seg.path, { waitUntil: 'load' });
  await page.evaluate(() => document.querySelectorAll('img[loading="lazy"]').forEach((i) => (i.loading = 'eager')));
  await page.waitForLoadState('networkidle');
  if (seg.waitReel) await page.waitForSelector('[data-reel] video.on', { timeout: 30000 });
  if (seg.reelAt != null) await page.evaluate((at) => new Promise((ok) => {
    const v = document.querySelector('[data-reel] video');
    v.pause();
    v.addEventListener('seeked', ok, { once: true });
    v.currentTime = at;
  }), seg.reelAt);
  await page.waitForTimeout(1500); // walkthrough players start 300 ms after load
  await page.evaluate((svg) => {
    const c = document.createElement('div');
    c.id = '__cur';
    c.innerHTML = svg + '<i></i>';
    c.style.cssText = 'position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;width:44px;height:44px';
    const ring = c.querySelector('i');
    ring.style.cssText = 'position:absolute;left:-26px;top:-26px;width:52px;height:52px;border:4px solid #b3261e;border-radius:50%;opacity:0';
    document.body.append(c);
  }, CURSOR);
  // resolve selectors to page coordinates once, at scroll 0
  const at = async (v, pad = 0) => (typeof v === 'string'
    ? page.$eval(v, (el, pad) => { const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + scrollY - pad, r.top + scrollY + r.height / 2]; }, pad)
    : v);
  const scrollKeys = [];
  for (const [t, v] of seg.scroll) scrollKeys.push([t, typeof v === 'string' ? (await at(v, seg.scrollPad ?? 0))[1] : v]);
  const curKeys = [];
  for (const [t, v] of seg.cursor) curKeys.push([t, typeof v === 'string' ? await at(v) : [...v, null]]);
  const scrollAt = track(scrollKeys);
  const n = Math.round(seg.secs * FPS);
  for (let f = 0; f < n; f++) {
    const t = f / FPS;
    const y = Math.round(scrollAt(t));
    // cursor keys with a selector are in page coordinates (x, -, centreY); plain ones are viewport coordinates
    const key = (k) => (k[1][2] == null ? [k[1][0], k[1][1]] : [k[1][0], k[1][2] - y]);
    let cx, cy;
    const keys = curKeys.map((k) => [k[0], key(k)]);
    [cx, cy] = track(keys)(t);
    await page.mouse.move(cx, cy);
    const ring = seg.click != null && t >= seg.click ? Math.min(1, (t - seg.click) / 0.45) : -1;
    await page.evaluate(async ({ y, cx, cy, ring, t }) => {
      scrollTo(0, y);
      const c = document.getElementById('__cur');
      c.style.transform = `translate(${cx - 6}px, ${cy - 3}px)`;
      const r = c.querySelector('i');
      r.style.opacity = ring < 0 ? 0 : String(1 - ring);
      r.style.transform = `scale(${ring < 0 ? 0.4 : 0.4 + ring})`;
      // every video with a source runs on its own clock from the first frame it is seen
      const clocks = (window.__clocks ||= new Map());
      const vids = [...document.querySelectorAll('video')].filter((v) => v.currentSrc || v.src);
      await Promise.all(vids.map(async (v) => {
        if (v.readyState < 2 && !v.dataset.waited) {
          v.dataset.waited = '1'; // once per video: one that never loads must not stall every frame
          await new Promise((ok) => { v.addEventListener('loadeddata', ok, { once: true }); setTimeout(ok, 4000); });
        }
        if (v.readyState < 1) return;
        if (!clocks.has(v)) clocks.set(v, t - v.currentTime);
        if (!v.paused) v.pause();
        if (v.closest('.card, .item')) v.classList.add('on'); // their play() promise is pre-empted by the pause
        const want = v.duration ? (t - clocks.get(v)) % v.duration : 0;
        if (Math.abs(v.currentTime - want) > 0.001) {
          const done = new Promise((ok) => { v.addEventListener('seeked', ok, { once: true }); setTimeout(ok, 1500); });
          v.currentTime = want;
          await done;
        }
      }));
      // images that just scrolled into view
      await Promise.all([...document.images].filter((i) => !i.complete).map((i) => new Promise((ok) => { i.onload = i.onerror = ok; setTimeout(ok, 3000); })));
    }, { y, cx, cy, ring, t });
    await page.screenshot({ path: join(dir, `${String(f).padStart(4, '0')}.png`) });
  }
  console.log(`${name}: ${n} frames`);
}

const browser = await chromium.launch({ executablePath: process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--autoplay-policy=no-user-gesture-required', '--hide-scrollbars'] });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 });
for (const [name, seg] of Object.entries(SEGMENTS)) if (!only.length || only.includes(name)) await record(page, name, seg);
await browser.close();
