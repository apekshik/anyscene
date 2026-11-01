// Captures the builder UI from the builder replay into web/screenshots/builder-*.png. Needs `npm run dev` running.
//   node scripts/screenshots-builder.mjs [baseUrl] [replayName=builder]
import { chromium } from "playwright-core";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { mkdirSync } from "node:fs";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const out = path.join(root, "screenshots");
mkdirSync(out, { recursive: true });
const base = process.argv[2] || "http://localhost:3210";
const name = process.argv[3] || "builder";

let browser;
for (const channel of ["msedge", "chrome"]) {
  try {
    browser = await chromium.launch({ channel, args: ["--enable-gpu", "--ignore-gpu-blocklist"] });
    break;
  } catch {}
}
if (!browser) throw new Error("No Edge or Chrome found");
const page = await browser.newPage({ viewport: { width: 1600, height: 940 } });
page.on("pageerror", (e) => console.error("page error:", e.message));
const shot = async (file) => {
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(out, file) });
  console.log("saved", file);
};
const tab = (label) => page.getByRole("tab", { name: label, exact: true }).click();
const until = (fn, arg, timeout = 300000) => page.waitForFunction(fn, arg, { timeout });

await page.goto(`${base}/?replay=${name}&speed=32`, { waitUntil: "networkidle" });
await page.waitForSelector(".drop img");
await shot("builder-01-idle.png");

await page.getByRole("button", { name: "Build the scene" }).click();
await until(() => document.querySelectorAll(".ll.milestone").length >= 1);
await shot("builder-02-plan-milestone.png");
await until(() => document.querySelectorAll(".ll.milestone").length >= 4);
await shot("builder-03-props-dressing.png");
await until(() => document.querySelectorAll(".scores tbody tr").length > 0);
await shot("builder-04-critic-round-1.png");
await until(() => [...document.querySelectorAll(".scores thead th")].length >= 3);
await tab("Contact sheet");
await shot("builder-05-contact-sheet-round-2.png");
await page.getByRole("button", { name: "Notes", exact: true }).click();
await shot("builder-06-log-notes-filter.png");
await page.getByRole("button", { name: "All", exact: true }).click();
await page.getByRole("button", { name: "Follow" }).click();
await until(() => !!document.querySelector(".slate-wrap .stamp"));
await page.waitForTimeout(1500);
await shot("builder-07-wrapped-stills.png");
await tab("Compare");
await shot("builder-08-compare.png");
await tab("360");
await page.waitForTimeout(2500);
await shot("builder-09-360-plate.png");
await page.getByRole("button", { name: "Set model" }).click();
await page.waitForTimeout(3000);
await shot("builder-10-360-set-model.png");
await page.setViewportSize({ width: 390, height: 844 });
await shot("builder-11-mobile.png");
await page.setViewportSize({ width: 1600, height: 940 });
await page.goto(`${base}/?mode=pipeline`, { waitUntil: "networkidle" });
await shot("builder-12-pipeline-toggle.png");
await browser.close();
