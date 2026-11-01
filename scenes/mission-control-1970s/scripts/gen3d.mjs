// Every mission-control prop through Tripo H3.1 and Meshy 7.1, 12 at a time. Skips props that already have model.glb.
// node scenes/mission-control-1970s/scripts/gen3d.mjs [id ...]   (ids limit the run). Never run two of these at once.
import { execFile } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
const S = 'scenes/mission-control-1970s';
const man = JSON.parse(readFileSync(`${S}/assets.json`, 'utf8'));
const only = process.argv.slice(2);
mkdirSync(`${S}/logs`, { recursive: true });
const jobs = [];
for (const a of man.generate) {
  if (only.length && !only.includes(a.id)) continue;
  const ref = a.ref ?? `refs/mission-control-1970s/props/${a.id}.json`;
  if (!existsSync(ref)) { console.log(`no ref ${a.id}`); continue; }
  for (const m of (a.models ?? ['tripo-h31', 'meshy'])) if (!existsSync(`assets/gen/${m}/${a.id}/model.glb`)) jobs.push([m, a.id, ref]);
}
console.log(`${jobs.length} jobs`);
const run = ([m, id, ref]) => new Promise((res) => execFile('node', ['generate/fal.mjs', '3d', '--model', m, '--ref', ref, '--out', `assets/gen/${m}/${id}`], { maxBuffer: 1e7, timeout: 40 * 60_000 }, (err, out, errout) => {
  writeFileSync(`${S}/logs/gen_${m}_${id}.log`, out + errout);
  console.log(`${err ? 'FAIL' : 'ok  '} ${m} ${id}${err ? ' ' + errout.slice(-200).replace(/\s+/g, ' ') : ''}`);
  res();
}));
let i = 0;
await Promise.all(Array.from({ length: +(process.env.POOL ?? 12) }, async () => { while (i < jobs.length) await run(jobs[i++]); }));
