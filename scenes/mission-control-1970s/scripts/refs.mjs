// GPT Image 2.5 Sunburst references for the mission-control manifest (props + textures), 10 at a time; skips existing.
// node scenes/mission-control-1970s/scripts/refs.mjs [id ...]
import { execFile } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
const S = 'scenes/mission-control-1970s', R = 'refs/mission-control-1970s';
const REF = 'No real-world brand names or logos. Product reference photograph for 3D scanning. The entire object fully visible and centered, three-quarter front view from slightly above, plain seamless light-grey background, soft even diffuse studio lighting, no harsh shadows, no other objects, no hands, realistic used and worn condition, sharp focus, true-to-life materials.';
const man = JSON.parse(readFileSync(`${S}/assets.json`, 'utf8'));
const only = process.argv.slice(2);
const want = (id) => !only.length || only.includes(id);
const jobs = [];
for (const a of man.generate) {
  const out = `${R}/props/${a.id}`;
  if (!want(a.id) || a.ref || existsSync(`${out}.json`)) continue;
  jobs.push(['--variant', 'sunburst', '--quality', 'high', '--size', 'square_hd', '--out', out, '--prompt', `${a.prompt.replace('{console}', man.style.console)} ${REF}`]);
}
for (const t of man.textures ?? []) {
  const out = t.id.startsWith('concept') ? `${R}/${t.id}` : `${R}/tex/${t.id}`;
  if (!want(t.id) || existsSync(`${out}.json`)) continue;
  jobs.push(['--variant', t.variant ?? 'sunburst', '--quality', 'high', '--size', t.size, '--out', out, '--prompt', t.prompt]);
}
console.log(`${jobs.length} image jobs`);
const run = (args) => new Promise((res) => execFile('node', ['generate/fal.mjs', 'image', ...args], { maxBuffer: 1e7 }, (err, out, errout) => {
  console.log(err ? `FAIL ${args[args.indexOf('--out') + 1]} ${errout.slice(-300)}` : out.trim().split('\n').at(-1)); res();
}));
let i = 0;
await Promise.all(Array.from({ length: 10 }, async () => { while (i < jobs.length) await run(jobs[i++]); }));
