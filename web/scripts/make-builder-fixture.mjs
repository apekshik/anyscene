// A short synthetic builder recording (fixtures/builder/) that follows the real schema, for building
// and demoing the UI until a real run is dropped in with scripts/import-builder-run.mjs.
// Images reuse the pipeline recording in fixtures/ (served at /replay/demo/...), so nothing is copied.
//   node scripts/make-builder-fixture.mjs
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const dir = path.join(root, "fixtures", "builder");
mkdirSync(dir, { recursive: true });

const D = "/replay/demo/";
const img = {
  floor: D + "floor_plan.png",
  overview: D + "blockout_overview.png",
  greyRef: D + "blockout_reference.png",
  layout: "https://v3b.fal.media/files/b/0ab08ded/4D56g-JZtrjm9g2ElyEml_0001.png",
  dressed: "https://v3b.fal.media/files/b/0ab08df7/jQQ2vHPFNHpNlUC_bgakY_0001.png",
  prop: "https://v3b.fal.media/files/b/0ab08da2/eIx9Y9z-uor3zqn87R7F9_9aWSSyyo.png",
  s0: D + "still_0.png",
  s1: D + "still_1.png",
  s2: D + "still_2.png",
};

const ev = [];
let t = 0;
const at = (dt) => (t = Math.round((t + dt) * 10) / 10);
const e = (stage, message, extra = {}) => ev.push({ t, stage, status: "running", message, ...extra });
const log = (dt, tool, message) => (at(dt), e("log", message, { tool }));
const say = (dt, message) => (at(dt), e("thinking", message));
const report = (dt, stage, message, preview_url) => (at(dt), e(stage, message, preview_url ? { preview_url } : {}));

at(0.2); e("received", "build b_synthetic01: 1 reference image(s)");
at(0.1); e("received", "scene builder starting");
say(2.8, "I'll start by reading the skill docs and the inputs.");
log(0.2, "Bash", "ls && cat SKILL.md && ls input && cat input/brief.md");
log(1.1, "Bash", "cat CRAFT.md; ls docs endpoint camera pipeline generate");
log(0.1, "Read", "looking at input/reference_1.png");
say(9, "A 1960s mission control room at night: tiered console rows, a giant orbit-tracking wall display, tall windows on the left onto a floodlit pad. Lots of desk clutter. The screens are the hero; they need to read as green CRT phosphor, not flat emissive cards.");
log(6, "Bash", "sed -n 80,400p generate/fal.mjs; which blender; blender --version");
log(4, "Write", "writing scenes/scene/plan.json");
log(22, "Bash", "python pipeline/floorplan.py scenes/scene/plan.json out/floor_plan.png");
log(5, "Read", "looking at out/floor_plan.png");
report(3, "plan", "70 objects (18 invented), 16 lights, 16 x 14 m interior; consoles in three tiers facing the wall display", img.floor);
log(8, "Write", "writing scenes/scene/scripts/shell.py");
log(3, "Bash", "blender -b --factory-startup --python scenes/scene/scripts/shell.py -- out/scene.blend");
log(41, "Bash", "blender -b out/scene.blend --python camera/shoot.py -- --shots out/shots.json --preview");
log(36, "Read", "looking at out/preview/ref_view.png");
say(4, "Proportions are right but the camera is a little high; the reference is shot from seated eye level, about 1.25 m.");
log(3, "Edit", "editing scenes/scene/shots.json");
log(30, "Bash", "blender -b out/scene.blend --python camera/shoot.py -- --shots out/shots.json --preview");
log(34, "Read", "looking at out/preview/overview.png");
report(2, "layout", "shell, tiers and console rows blocked out; reference camera matched at 28 mm", img.overview);
say(5, "Props next. 19 unique assets cover 45 placements: references cropped from the plate and cleaned, then meshes from Tripo H3.1, Meshy for the small items.");
log(3, "Bash", "node generate/fal.mjs refs scenes/scene/props.json --out scenes/scene/props");
log(48, "Read", "looking at scenes/scene/props/console_bank_ref.png");
log(3, "Read", "looking at scenes/scene/props/teleprinter_ref.png");
log(2, "Read", "looking at scenes/scene/props/rotary_phone_ref.png");
report(4, "props", "19 prop references in; meshes generating (15 Tripo H3.1, 4 Meshy)", img.prop);
log(5, "Bash", "node generate/fal.mjs meshes scenes/scene/props.json --wait");
say(180, "Meshes are landing. Swapping them in as they arrive and checking scale against the plan.");
log(3, "Write", "writing scenes/scene/scripts/dress.py");
log(6, "Bash", "blender -b out/scene.blend --python scenes/scene/scripts/dress.py");
log(52, "Bash", "python pipeline/collide.py out/scene.blend --drop");
log(14, "Bash", "blender -b out/scene.blend --python camera/shoot.py -- --shots out/shots.json --preview");
log(38, "Read", "looking at out/preview/ref_view.png");
report(2, "dressing", "45 placements dressed; 1 ashtray dropped onto its desk, nothing floating", img.layout);
say(4, "The consoles' CRTs are blank. Each scope needs its own phosphor content: sine traces, polar plots, telemetry columns.");
log(3, "Write", "writing scenes/scene/scripts/screens.py");
log(5, "Bash", "python scenes/scene/scripts/screens.py --make-textures out/screens");
log(26, "Read", "looking at out/screens/scope_04.png");
log(4, "Bash", "blender -b out/scene.blend --python scenes/scene/scripts/screens.py -- --apply");
report(18, "screens", "14 CRT textures and the wall map with ground tracks; no repeated text", img.dressed);
log(5, "Write", "writing scenes/scene/scripts/materials.py");
log(8, "Bash", "blender -b out/scene.blend --python scenes/scene/scripts/materials.py");
log(40, "Read", "looking at out/preview/close_console.png");
report(3, "materials", "grey-green enamel with edge wear, linoleum floor, acoustic ceiling tiles, smoked glass", img.dressed);
log(5, "Write", "writing scenes/scene/scripts/lighting.py");
log(7, "Bash", "blender -b out/scene.blend --python scenes/scene/scripts/lighting.py");
log(44, "Read", "looking at out/preview/ref_view.png");
say(3, "Too bright overall; the reference is lit mostly by the screens and the wall display. Dropping the ceiling panels by 60%.");
log(3, "Edit", "editing scenes/scene/scripts/lighting.py");
log(41, "Bash", "blender -b out/scene.blend --python scenes/scene/scripts/lighting.py");
report(2, "lighting", "screens and wall display carry the room; ceiling panels at 40%; sodium floods outside", img.s2);
log(5, "Edit", "editing scenes/scene/scripts/lighting.py");
report(36, "atmosphere", "cigarette haze (volume density 0.012), slight bloom, Kodak 5219-style grade", img.s2);
log(4, "Write", "writing scenes/scene/shots.json");
report(30, "cameras", "reference angle plus two open views down the console rows", img.s1);
log(3, "Bash", "blender -b out/scene.blend --python camera/shoot.py -- --shots out/shots.json --finals --samples 256");
log(96, "Read", "looking at out/stills/ref.png");
report(3, "finals", "3 stills at 1920 x 804, 256 samples", img.s0);

const crit = (round, scores, fixes, summary, preview) => {
  at(4);
  e("critique", "critic is looking at 3 stills");
  at(58);
  const passed = Object.values(scores).every((v) => v >= 7);
  ev.push({
    t, stage: "critique", status: passed ? "done" : "running",
    message: `round ${round}: ${passed ? "PASS" : "not yet"} - ` + Object.entries(scores).map(([k, v]) => `${k} ${v}`).join(", "),
    preview_url: preview,
    critique: { round, scores, fixes, summary, passed, stills: ["out/stills/ref.png", "out/stills/view_1.png", "out/stills/view_2.png"] },
  });
};
crit(1, { layout: 7, props: 6, screens_signage: 5, materials: 6, lighting: 7, atmosphere: 6, plausibility: 8, composition: 7 }, [
  "Console CRTs: all 14 scopes show the same sine trace; the reference has varied content (polar plots, columns of telemetry, a radar sweep). Give each scope its own texture.",
  "Wall display: the world map is too bright and flat; it should glow from behind with darker ocean areas and thin orbit ground tracks.",
  "Desk clutter: binders and teleprinter paper read as clean grey boxes; add page edges, curl and print.",
  "Haze is too uniform; the reference has denser smoke near the ceiling lit by the screens.",
  "Chairs: three swivel chairs intersect the console fronts in the second row.",
], "Right room, right layout and camera. It falls down on the screens, which carry this reference, and on generic clutter.", img.s0);
say(4, "Screens first, they cost the most points. Then the clutter and the chairs.");
log(3, "Edit", "editing scenes/scene/scripts/screens.py");
log(6, "Bash", "python scenes/scene/scripts/screens.py --make-textures out/screens --vary 14");
log(30, "Read", "looking at out/screens/contact_sheet.png");
report(4, "screens", "14 distinct scope textures: polar plots, telemetry columns, radar sweep; wall map darkened", img.dressed);
log(5, "Edit", "editing scenes/scene/scripts/dress.py");
log(31, "Bash", "python pipeline/collide.py out/scene.blend --fix chairs");
report(3, "dressing", "chairs pulled back from the consoles; binders and printouts swapped for detailed meshes", img.layout);
log(4, "Edit", "editing scenes/scene/scripts/lighting.py");
report(40, "atmosphere", "haze layered: denser under the ceiling, lit by the scopes", img.s2);
log(3, "Bash", "blender -b out/scene.blend --python camera/shoot.py -- --shots out/shots.json --finals --samples 256");
log(98, "Read", "looking at out/stills/ref.png");
report(2, "finals", "3 stills re-rendered after round 1 fixes", img.s0);
crit(2, { layout: 7, props: 7, screens_signage: 6, materials: 7, lighting: 8, atmosphere: 7, plausibility: 8, composition: 7 }, [
  "Wall display: ground tracks are there but the telemetry panels either side are blank; the reference has columns of stencilled data.",
  "Two scopes on the hero console are out of focus compared with the rest; sharpen or raise their emission.",
  "Window reflections: the glass shows no reflection of the room; add a faint reflection so it reads as glass at night.",
], "Big improvement on the screens and the haze. The side panels of the wall display are the last thing that reads as unfinished.", img.s0);
say(4, "Filling the wall display's side panels with stencilled data columns and adding reflection to the window glass.");
log(3, "Edit", "editing scenes/scene/scripts/screens.py");
log(22, "Bash", "python scenes/scene/scripts/screens.py --wall-panels out/screens");
log(4, "Edit", "editing scenes/scene/scripts/materials.py");
log(3, "Bash", "blender -b out/scene.blend --python camera/shoot.py -- --shots out/shots.json --finals --samples 256");
log(97, "Read", "looking at out/stills/view_1.png");
report(2, "finals", "3 stills with the wall panels and window glass fixed", img.s0);
crit(3, { layout: 8, props: 7, screens_signage: 7, materials: 7, lighting: 8, atmosphere: 8, plausibility: 8, composition: 8 }, [
  "Optional: a little more variation in console paint wear between rows.",
  "Optional: one or two lit cigarettes in the ashtrays would add life to the haze.",
], "Passes. A faithful, photoreal version of the reference; the screens and the wall display now carry it.", img.s0);
log(5, "Bash", "blender -b out/scene.blend --python pipeline/export_glb.py -- out/scene.glb --decimate 0.25");
log(40, "Bash", "blender -b out/scene.blend --python camera/panorama.py -- --at ref_view,room_centre --out out/panoramas");
at(70);
ev.push({ t, stage: "done", status: "done", message: "scene builder finished after 33 min, agent cost $27.40", missing: [], critiques: 3 });
at(48);
ev.push({ t, stage: "packaged", status: "done", message: "package ready after 34 min", package_url: "https://v3b.fal.media/files/b/0ab08e00/m4GTss3UapWdQmO9PaFiw_scene_package.zip" });

writeFileSync(path.join(dir, "events.jsonl"), ev.map((x) => JSON.stringify(x)).join("\n") + "\n");
const critiques = ev.filter((x) => x.critique).map((x) => {
  const { stills, ...c } = x.critique;
  return c;
});
const build = {
  build_id: "b_synthetic01",
  stills: [img.s0, img.s1, img.s2],
  scene_blend_url: null,
  scene_glb_url: D + "scene.glb",
  panorama_urls: [D + "panorama_ref.png", D + "panorama_mid.png"],
  package_url: ev[ev.length - 1].package_url,
  critiques,
  missing: [],
  agent_cost_usd: 27.4,
  minutes: Math.round((t / 60) * 10) / 10,
  _synthetic: "made by scripts/make-builder-fixture.mjs; images and package are from the earlier pipeline run",
};
writeFileSync(path.join(dir, "build.json"), JSON.stringify(build, null, 1));
console.log(`fixtures/builder: ${ev.length} events over ${(t / 60).toFixed(1)} min`);
