// Ramen scene generation: refs (GPT Image 2.5 Sunburst) then Tripo H3.1 + Meshy 7.1 for every prop, plus flat textures.
//   node scenes/tokyo-ramen-shop/scripts/gen.mjs [--only id,id] [--models tripo-h31,meshy]
// Skips anything already on disk; re-run to fill gaps. Uses generate/fal.mjs (shared) via child processes.
import { execFile } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { promisify } from 'node:util';

const run = promisify(execFile);
const ROOT = new URL('../../..', import.meta.url).pathname.replace(/^\/([A-Z]:)/, '$1');
const M = JSON.parse(readFileSync(`${ROOT}/scenes/tokyo-ramen-shop/assets.json`, 'utf8'));
const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, arr) => (v.startsWith('--') ? [...a, [v.slice(2), arr[i + 1]]] : a), []));
const only = args.only?.split(',');
const models = (args.models ?? 'tripo-h31,meshy').split(',');
const REF = 'Product reference photograph for 3D scanning. The entire object fully visible and centered, three-quarter front view from slightly above, plain seamless light-grey background, soft even diffuse studio lighting, no harsh shadows, no other objects, no hands, realistic used and worn condition, sharp focus, true-to-life materials.';

const fal = (...a) => run('node', ['generate/fal.mjs', ...a], { cwd: ROOT, maxBuffer: 1 << 24 });

async function pool(tasks, n) {
  const out = [];
  let i = 0;
  await Promise.all(Array.from({ length: n }, async () => {
    while (i < tasks.length) {
      const t = tasks[i++];
      try { out.push(await t()); } catch (e) { console.log('FAIL', e.message.split('\n').slice(-3).join(' | ')); }
    }
  }));
  return out;
}

const refPath = (id) => (existsSync(`${ROOT}/refs/props/${id}.json`) ? `refs/props/${id}.json` : `refs/tokyo-ramen-shop/props/${id}.json`);
const props = M.generate.filter((p) => !only || only.includes(p.id));

// Textures + refs first (fast), then 3D.
const imgTasks = [
  ...M.textures.filter((t) => (!only || only.includes(t.id)) && !existsSync(`${ROOT}/refs/tokyo-ramen-shop/tex/${t.id}_0.png`)).map((t) => async () => {
    await fal('image', '--variant', 'sunburst', '--quality', 'high', '--size', t.size, '--out', `refs/tokyo-ramen-shop/tex/${t.id}`, '--prompt', t.prompt);
    console.log('tex', t.id);
  }),
  ...props.filter((p) => p.prompt !== 'existing' && !existsSync(`${ROOT}/${refPath(p.id)}`)).map((p) => async () => {
    await fal('image', '--variant', 'sunburst', '--quality', 'high', '--size', 'square_hd', '--out', `refs/tokyo-ramen-shop/props/${p.id}`, '--prompt', `${p.prompt} ${REF}`);
    console.log('ref', p.id);
  }),
];
await pool(imgTasks, 10);

const genTasks = props.flatMap((p) => models.filter((m) => !existsSync(`${ROOT}/assets/gen/${m}/${p.id}/model.glb`)).map((m) => async () => {
  const t0 = Date.now();
  await fal('3d', '--model', m, '--ref', refPath(p.id), '--out', `assets/gen/${m}/${p.id}`);
  console.log('3d', m, p.id, Math.round((Date.now() - t0) / 1000) + 's');
}));
await pool(genTasks, +(args.pool ?? 14));
console.log('all done');
