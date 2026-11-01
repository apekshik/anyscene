// Captures the major UI states from a replay into web/screenshots/. Needs `npm run dev` running.
//   node scripts/screenshots.mjs [baseUrl] [replayName]
// Uses the installed Microsoft Edge (or Chrome) through playwright-core; no browser download.
import { chromium } from "playwright-core";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { mkdirSync } from "node:fs";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const out = path.join(root, "screenshots");
mkdirSync(out, { recursive: true });
const base = process.argv[2] || "http://localhost:3210";
const name = process.argv[3] || "demo";
const speed = 16;

let browser;
for (const channel of ["msedge", "chrome"]) {
  try {
    browser = await chromium.launch({ channel, args: ["--enable-gpu", "--ignore-gpu-blocklist"] });
    break;
  } catch {}
}
if (!browser) throw new Error("No Edge or Chrome found");

const page = await browser.newPage({ viewport: { width: 1600, height: 940 }, deviceScaleFactor: 1 });
page.on("pageerror", (e) => console.error("page error:", e.message));
const shot = async (file) => {
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(out, file) });
  console.log("saved", file);
};
const tab = (label) => page.getByRole("tab", { name: label, exact: true }).click();

await page.goto(`${base}/?replay=${name}&speed=${speed}`, { waitUntil: "networkidle" });
await page.waitForSelector(".drop img");
await shot("01-idle.png");

await page.getByRole("button", { name: "Plan the scene" }).click();
await page.waitForTimeout(1500);
await shot("02-planning.png");

await page.waitForSelector(".plan-title", { timeout: 120000 });
await shot("03-plan-ready-greybox.png");
await tab("Floor plan");
await shot("04-floor-plan.png");
await tab("Compare");
await shot("05-compare-greybox.png");

await page.getByRole("button", { name: /Approve and build/ }).click();
await page.waitForFunction(() => document.querySelectorAll(".tile:not(.ghost)").length >= 10, null, { timeout: 120000 });
await shot("06-build-references.png");
await page.waitForFunction(() => document.querySelectorAll(".tile.spinning").length >= 6, null, { timeout: 120000 }).catch(() => console.log("(few turntables ready yet)"));
await shot("07-build-meshes-prop-map.png");

await page.waitForFunction(() => [...document.querySelectorAll(".sched tr.running .dept")].some((d) => /Set dressing|Camera/.test(d.textContent || "")), null, { timeout: 300000 });
await tab("Live");
await shot("08-live-layout.png");

await page.locator(".tile:not(.ghost):not(:disabled)").first().click();
await page.waitForSelector(".viewer3d canvas");
await page.waitForFunction(() => !document.querySelector(".viewer3d-load"), null, { timeout: 180000 }).catch(() => {});
await page.waitForTimeout(1500);
await shot("09-prop-3d.png");

await page.waitForSelector(".slate-wrap .stamp", { timeout: 400000 });
await tab("Result");
await page.waitForTimeout(1200);
await shot("10-wrapped-result.png");
await tab("Compare");
await shot("11-compare-final.png");

await tab("360");
await page.waitForTimeout(2500);
await shot("12-360-plate.png");
await page.getByRole("button", { name: "Set model" }).click();
await page.waitForTimeout(3000);
await shot("13-360-set-model.png");

await page.locator(".tile:not(.ghost):not(:disabled)").nth(2).click();
await page.waitForFunction(() => !document.querySelector(".viewer3d-load"), null, { timeout: 180000 }).catch(() => {});
await page.waitForTimeout(2000);
await shot("14-prop-3d-scene-light.png");

await page.setViewportSize({ width: 390, height: 844 });
await page.evaluate(() => window.scrollTo(0, 0));
await shot("15-mobile.png");

await browser.close();
