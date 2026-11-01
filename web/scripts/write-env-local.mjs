// Writes web/.env.local with FAL_KEY taken from the Windows user env var FAL_SERVERLESS_KEY (HKCU\Environment).
// The key is never printed.
import { execFileSync } from "node:child_process";
import { writeFileSync, existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const out = path.join(root, ".env.local");
let key = process.env.FAL_SERVERLESS_KEY;
if (!key && process.platform === "win32") {
  try {
    const txt = execFileSync("reg", ["query", String.raw`HKCU\Environment`, "/v", "FAL_SERVERLESS_KEY"], { encoding: "utf8" });
    const m = txt.match(/FAL_SERVERLESS_KEY\s+REG_\w+\s+(\S+)/);
    if (m) key = m[1];
  } catch {}
}
if (!key) {
  console.error("FAL_SERVERLESS_KEY not found in the environment or HKCU/Environment; .env.local not written.");
  process.exit(1);
}
let lines = existsSync(out) ? readFileSync(out, "utf8").split(/\r?\n/).filter((l) => l && !l.startsWith("FAL_KEY=")) : [];
lines.push(`FAL_KEY=${key}`);
writeFileSync(out, lines.join("\n") + "\n");
console.log(`wrote FAL_KEY (${key.length} chars) to .env.local`);
