// Copies recorded runs from web/fixtures/ into public/replay/ so `?replay=<name>` can stream them.
//   web/fixtures/*            -> public/replay/demo/
//   web/fixtures/<name>/*     -> public/replay/<name>/
// Each copy gets a manifest.json saying which pieces exist (plan events, plan, images, build events, stills).
import { cpSync, existsSync, mkdirSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const src = path.join(root, "fixtures");
const dst = path.join(root, "public", "replay");
rmSync(dst, { recursive: true, force: true });
mkdirSync(dst, { recursive: true });

function copyRun(from, name) {
  const to = path.join(dst, name);
  mkdirSync(to, { recursive: true });
  const files = readdirSync(from).filter((f) => statSync(path.join(from, f)).isFile());
  for (const f of files) cpSync(path.join(from, f), path.join(to, f));
  const has = (f) => files.includes(f);
  const manifest = {
    name,
    // a builder recording (builder/app.py) is events.jsonl + build.json; the old pipeline has plan/build events
    kind: has("events.jsonl") ? "builder" : "pipeline",
    events: has("events.jsonl"),
    plan_events: has("plan_events.jsonl"),
    plan: has("plan.json"),
    // a recording without its own reference borrows the root one (both demo runs use the same plate)
    reference: has("reference.png") ? "reference.png" : name !== "demo" && existsSync(path.join(src, "reference.png")) ? "/replay/demo/reference.png" : null,
    floor_plan: has("floor_plan.png") ? "floor_plan.png" : null,
    blockout_reference: has("blockout_reference.png") ? "blockout_reference.png" : null,
    blockout_overview: has("blockout_overview.png") ? "blockout_overview.png" : null,
    comparison: has("comparison.png") ? "comparison.png" : null,
    build_events: has("build_events.jsonl"),
    build: has("build.json"),
    // placeholders for the 360 tab (scripts/make-placeholders.mjs) until a recorded build carries real ones
    panoramas: files.filter((f) => /^panorama_.*\.(png|jpg|hdr)$/i.test(f)).sort((a, b) => (a.includes("ref") ? -1 : b.includes("ref") ? 1 : a.localeCompare(b))),
    scene_glb: has("scene.glb") ? "scene.glb" : null,
    stills: files.filter((f) => /^still_.*\.(png|jpg|webp)$/i.test(f)).sort(),
  };
  writeFileSync(path.join(to, "manifest.json"), JSON.stringify(manifest, null, 1));
  return manifest;
}

const runs = [];
if (existsSync(src)) {
  runs.push(copyRun(src, "demo").name);
  for (const d of readdirSync(src)) {
    if (statSync(path.join(src, d)).isDirectory()) runs.push(copyRun(path.join(src, d), d).name);
  }
}
writeFileSync(path.join(dst, "index.json"), JSON.stringify({ runs }));
console.log(`replay fixtures: ${runs.join(", ") || "none"}`);
