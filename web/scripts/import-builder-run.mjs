// Drop a real builder run (builder/app.py) into the replay fixtures.
//   node scripts/import-builder-run.mjs <run dir> [name=builder] [reference image]
// <run dir> is what builder/client.py writes: events.jsonl, build.json and still_*.png (e.g. anyscene-runs/fal_mc_1).
// The result replaces fixtures/<name>/ and is served at ?replay=<name>.
import { copyFileSync, existsSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const [run, name = "builder", ref] = process.argv.slice(2);
if (!run || !existsSync(path.join(run, "events.jsonl"))) {
  console.error("usage: node scripts/import-builder-run.mjs <run dir with events.jsonl> [name] [reference image]");
  process.exit(1);
}
const out = path.join(root, "fixtures", name);
rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });
const files = readdirSync(run).filter((f) => f === "events.jsonl" || f === "build.json" || /^still_\d+\.(png|jpg)$/i.test(f));
for (const f of files) copyFileSync(path.join(run, f), path.join(out, f));
const refSrc = ref || [path.join(run, "reference.png"), path.join(root, "fixtures", "reference.png")].find((p) => existsSync(p));
if (refSrc) copyFileSync(refSrc, path.join(out, "reference.png"));
if (!files.includes("build.json")) console.warn("no build.json yet: the replay ends after the last event (run still going?)");
console.log(`fixtures/${name}: ${files.join(", ")}${refSrc ? ", reference.png" : ""}. Run npm run fixtures (or restart dev).`);
