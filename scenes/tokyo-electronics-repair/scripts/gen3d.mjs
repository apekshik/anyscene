// Run every repair prop through tripo-h31 and meshy, 12 at a time. Skips props that already have model.glb.
// node scenes/tokyo-electronics-repair/scripts/gen3d.mjs [id ...]   (ids limit the run, e.g. for regenerations)
import { execFile } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
const man = JSON.parse(readFileSync('scenes/tokyo-electronics-repair/assets.json', 'utf8'));
const only = process.argv.slice(2);
mkdirSync('scenes/tokyo-electronics-repair/logs', { recursive: true });
const jobs = [];
for (const a of man.generate) {
  if (only.length && !only.includes(a.id)) continue;
  const ref = a.ref ?? `refs/tokyo-electronics-repair/props/${a.id}.json`;
  for (const m of (a.models ?? ['tripo-h31', 'meshy'])) if (!existsSync(`assets/gen/${m}/${a.id}/model.glb`)) jobs.push([m, a.id, ref]);
}
console.log(`${jobs.length} jobs`);
const run = ([m, id, ref]) => new Promise((res) => execFile('node', ['generate/fal.mjs', '3d', '--model', m, '--ref', ref, '--out', `assets/gen/${m}/${id}`], { maxBuffer: 1e7, timeout: 40 * 60_000 }, (err, out, errout) => {
  writeFileSync(`scenes/tokyo-electronics-repair/logs/gen_${m}_${id}.log`, out + errout);
  console.log(`${err ? 'FAIL' : 'ok  '} ${m} ${id}${err ? ' ' + errout.slice(-200).replace(/\s+/g, ' ') : ''}`);
  res();
}));
let i = 0;
await Promise.all(Array.from({ length: +(process.env.POOL ?? 14) }, async () => { while (i < jobs.length) await run(jobs[i++]); }));
