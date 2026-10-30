// Generate missing GPT Image 2.5 Sunburst refs for the repair manifest, 10 at a time.
import { execFile } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
const REF = 'No real-world brand names or logos. Product reference photograph for 3D scanning. The entire object fully visible and centered, three-quarter front view from slightly above, plain seamless light-grey background, soft even diffuse studio lighting, no harsh shadows, no other objects, no hands, realistic used and worn condition, sharp focus, true-to-life materials.';
const man = JSON.parse(readFileSync('scenes/tokyo-electronics-repair/assets.json', 'utf8'));
const jobs = man.generate.filter((a) => a.prompt !== 'existing' && !existsSync(`refs/tokyo-electronics-repair/props/${a.id}.json`))
  .map((a) => ['--variant', 'sunburst', '--quality', 'high', '--size', 'square_hd', '--out', `refs/tokyo-electronics-repair/props/${a.id}`, '--prompt', `${a.prompt} ${REF}`]);
const extra = JSON.parse(process.argv[2] ?? '[]');
for (const e of extra) if (!existsSync(`${e.out}.json`)) jobs.push(['--variant', 'sunburst', '--quality', 'high', '--size', e.size, '--out', e.out, '--prompt', e.prompt]);
const run = (args) => new Promise((res) => execFile('node', ['generate/fal.mjs', 'image', ...args], { maxBuffer: 1e7 }, (err, out, errout) => { console.log(err ? `FAIL ${args.at(-3)} ${errout.slice(-300)}` : out.trim().split('\n').at(-1)); res(); }));
let i = 0;
await Promise.all(Array.from({ length: 10 }, async () => { while (i < jobs.length) await run(jobs[i++]); }));
