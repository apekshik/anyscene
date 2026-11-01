// Dai pai dong generation: refs (GPT Image 2.5 Sunburst) then Tripo H3.1 + Meshy 7.1 for every prop, plus flat textures.
//   node scenes/hk-dai-pai-dong/scripts/gen.mjs [--only id,id] [--models tripo-h31,meshy] [--stage refs|3d|all] [--pool 12]
// Skips anything already on disk; re-run to fill gaps. Never run two of these at once (in-flight jobs get double-submitted).
// Props with "replaces" (the _nb regenerations) are generated like any other prop.
import { execFile } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { promisify } from 'node:util';

const run = promisify(execFile);
const ROOT = new URL('../../..', import.meta.url).pathname.replace(/^\/([A-Z]:)/, '$1');
const SC = 'hk-dai-pai-dong';
const M = JSON.parse(readFileSync(`${ROOT}/scenes/${SC}/assets.json`, 'utf8'));
const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, arr) => (v.startsWith('--') ? [...a, [v.slice(2), arr[i + 1]]] : a), []));
const only = args.only?.split(',');
const models = (args.models ?? 'tripo-h31,meshy').split(',');
const stage = args.stage ?? 'all';

const fal = (...a) => run('node', ['generate/fal.mjs', ...a], { cwd: ROOT, maxBuffer: 1 << 24 });

async function pool(tasks, n) {
  let i = 0;
  let fails = 0;
  await Promise.all(Array.from({ length: n }, async () => {
    while (i < tasks.length) {
      const t = tasks[i++];
      try { await t(); } catch (e) { fails++; console.log('FAIL', e.message.split('\n').slice(-3).join(' | ')); }
    }
  }));
  return fails;
}

const refJson = (id) => `refs/${SC}/props/${id}.json`;
const props = M.generate.filter((p) => !only || only.includes(p.id));

if (stage !== '3d') {
  const imgTasks = [
    ...M.textures.filter((t) => (!only || only.includes(t.id)) && !existsSync(`${ROOT}/refs/${SC}/tex/${t.id}_0.png`)).map((t) => async () => {
      await fal('image', '--variant', 'sunburst', '--quality', 'high', '--size', t.size, '--out', `refs/${SC}/tex/${t.id}`, '--prompt', t.prompt);
      console.log('tex', t.id);
    }),
    ...props.filter((p) => !existsSync(`${ROOT}/${refJson(p.id)}`)).map((p) => async () => {
      await fal('image', '--variant', 'sunburst', '--quality', 'high', '--size', 'square_hd', '--out', `refs/${SC}/props/${p.id}`, '--prompt', `${p.prompt} ${M.scan_template}`);
      console.log('ref', p.id);
    }),
  ];
  console.log('image jobs', imgTasks.length);
  console.log('image fails', await pool(imgTasks, 10));
}

if (stage !== 'refs') {
  // Branded originals (a later "_nb" prop replaces them) are not sent to 3D.
  const replaced = new Set(M.generate.filter((p) => p.replaces).map((p) => p.replaces));
  const genTasks = props.filter((p) => !replaced.has(p.id) && existsSync(`${ROOT}/${refJson(p.id)}`)).flatMap((p) =>
    models.filter((m) => !existsSync(`${ROOT}/assets/gen/${m}/${p.id}/model.glb`)).map((m) => async () => {
      const t0 = Date.now();
      await fal('3d', '--model', m, '--ref', refJson(p.id), '--out', `assets/gen/${m}/${p.id}`);
      console.log('3d', m, p.id, Math.round((Date.now() - t0) / 1000) + 's');
    }));
  console.log('3d jobs', genTasks.length);
  console.log('3d fails', await pool(genTasks, +(args.pool ?? 12)));
}
console.log('all done');
