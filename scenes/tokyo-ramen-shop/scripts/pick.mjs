// node scenes/tokyo-ramen-shop/scripts/pick.mjs id model "reason" [id model "reason" ...]  -> merges into scenes/tokyo-ramen-shop/picks.json
import { readFileSync, writeFileSync } from 'node:fs';
const f = new URL('../picks.json', import.meta.url);
const p = JSON.parse(readFileSync(f, 'utf8'));
const a = process.argv.slice(2);
for (let i = 0; i < a.length; i += 3) p[a[i]] = { model: a[i + 1], reason: a[i + 2] };
writeFileSync(f, JSON.stringify(p, null, 2));
console.log(Object.keys(p).length, 'picks');
