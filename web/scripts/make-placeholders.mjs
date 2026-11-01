// Placeholder 360 assets for replay, until the endpoint emits real ones (see README):
//   fixtures/panorama_ref.png, fixtures/panorama_mid.png   procedural equirectangular "grey room" renders (2:1)
//   fixtures/scene.glb                                      the plan as boxes + KHR_lights_punctual lights
// Both are built from fixtures/plan.json so they line up with the recorded scene's layout. No dependencies.
//   node scripts/make-placeholders.mjs [fixturesDir]
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import { fileURLToPath } from "node:url";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const dir = process.argv[2] || path.join(root, "fixtures");
const plan = JSON.parse(readFileSync(path.join(dir, "plan.json"), "utf8"));
const { width: W, depth: D, height: H } = plan.room;

// ---------------------------------------------------------------- PNG
const crcTable = new Uint32Array(256).map((_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
const crc32 = (buf) => {
  let c = 0xffffffff;
  for (const b of buf) c = crcTable[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
};
function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
}
function png(w, h, rgb) {
  const raw = Buffer.alloc((w * 3 + 1) * h);
  for (let y = 0; y < h; y++) rgb.copy(raw, y * (w * 3 + 1) + 1, y * w * 3, (y + 1) * w * 3);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0);
  ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8;
  ihdr[9] = 2;
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk("IHDR", ihdr),
    chunk("IDAT", zlib.deflateSync(raw, { level: 6 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

// ---------------------------------------------------------------- equirectangular grey room
const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
const lights = plan.lights.map((l) => ({ p: [l.x, l.y, l.z], c: hex(l.color), k: l.power === "high" ? 2.2 : l.power === "medium" ? 1.2 : 0.6 }));
const objects = plan.objects.filter((o) => o.h > 0.05);

function shade(o, d) {
  // ray from o (plan coords, Z up) along d against the room box and object footprints (as axis-aligned boxes)
  let tBest = Infinity, n = null, kind = "";
  for (let a = 0; a < 3; a++) {
    if (Math.abs(d[a]) < 1e-9) continue;
    const lim = [W, D, H][a];
    const t = d[a] > 0 ? (lim - o[a]) / d[a] : -o[a] / d[a];
    if (t > 0 && t < tBest) { tBest = t; n = a; kind = a === 2 ? (d[2] > 0 ? "ceiling" : "floor") : "wall"; }
  }
  for (const ob of objects) {
    const hw = Math.max(ob.w, ob.d) / 2;
    const lo = [ob.x - hw, ob.y - hw, ob.z], hi = [ob.x + hw, ob.y + hw, ob.z + ob.h];
    let t0 = 0, t1 = tBest, axis = -1;
    for (let a = 0; a < 3; a++) {
      const inv = 1 / (d[a] || 1e-9);
      let ta = (lo[a] - o[a]) * inv, tb = (hi[a] - o[a]) * inv;
      if (ta > tb) [ta, tb] = [tb, ta];
      if (ta > t0) { t0 = ta; axis = a; }
      t1 = Math.min(t1, tb);
      if (t0 > t1) { axis = -2; break; }
    }
    if (axis >= 0 && t0 < tBest) { tBest = t0; n = axis; kind = "object"; }
  }
  const p = [o[0] + d[0] * tBest, o[1] + d[1] * tBest, o[2] + d[2] * tBest];
  let base = kind === "floor" ? [0.23, 0.22, 0.2] : kind === "ceiling" ? [0.32, 0.32, 0.3] : kind === "object" ? [0.42, 0.44, 0.4] : [0.36, 0.38, 0.35];
  // window openings glow (night: deep blue)
  if (kind === "wall") {
    for (const op of plan.openings) {
      const along = op.wall === "front" || op.wall === "back" ? p[0] : p[1];
      const onWall = (op.wall === "left" && p[0] < 0.01) || (op.wall === "right" && p[0] > W - 0.01) || (op.wall === "front" && p[1] < 0.01) || (op.wall === "back" && p[1] > D - 0.01);
      if (onWall && Math.abs(along - op.center) < op.width / 2 && p[2] > op.sill && p[2] < op.sill + op.height)
        base = op.kind === "window" ? [0.08, 0.12, 0.22] : [0.05, 0.05, 0.05];
    }
    // 1 m grid lines, like a set under construction
    const u = n === 0 ? p[1] : p[0];
    if (Math.abs(u - Math.round(u)) < 0.012 || Math.abs(p[2] - Math.round(p[2])) < 0.012) base = base.map((c) => c * 0.8);
  }
  if (kind === "floor" && (Math.abs(p[0] - Math.round(p[0])) < 0.01 || Math.abs(p[1] - Math.round(p[1])) < 0.01)) base = base.map((c) => c * 0.75);
  let col = base.map((c) => c * 0.25);
  for (const l of lights) {
    const v = [l.p[0] - p[0], l.p[1] - p[1], l.p[2] - p[2]];
    const dist2 = v[0] * v[0] + v[1] * v[1] + v[2] * v[2] + 0.4;
    const f = (l.k * 2.2) / dist2;
    col = col.map((c, i) => c + base[i] * l.c[i] * f);
  }
  // practical bulbs seen directly
  for (const l of lights) {
    const v = [l.p[0] - o[0], l.p[1] - o[1], l.p[2] - o[2]];
    const len = Math.hypot(...v);
    const cos = (v[0] * d[0] + v[1] * d[1] + v[2] * d[2]) / len;
    if (len < tBest + 0.1 && cos > 0.99985) col = l.c.map((c) => c * 1.4);
  }
  return col.map((c) => Math.min(1, Math.pow(c / (1 + c), 1 / 2.2) * 0.95));
}

function panorama(origin, w = 2048) {
  const h = w / 2;
  const rgb = Buffer.alloc(w * h * 3);
  for (let y = 0; y < h; y++) {
    const lat = Math.PI / 2 - ((y + 0.5) / h) * Math.PI;
    for (let x = 0; x < w; x++) {
      // u = 0.5 looks along +Y (into the room), the way three.js maps an equirect onto a sphere
      const lon = ((x + 0.5) / w - 0.5) * 2 * Math.PI;
      const d = [Math.sin(lon) * Math.cos(lat), Math.cos(lon) * Math.cos(lat), Math.sin(lat)];
      const c = shade(origin, d);
      const i = (y * w + x) * 3;
      rgb[i] = c[0] * 255;
      rgb[i + 1] = c[1] * 255;
      rgb[i + 2] = c[2] * 255;
    }
  }
  return png(w, h, rgb);
}

const cam = plan.reference_camera?.position ?? [W / 2, 1, 1.6];
const refPos = [Math.min(W - 0.2, Math.max(0.2, cam[0])), Math.min(D - 0.2, Math.max(1.0, cam[1])), Math.min(H - 0.2, Math.max(0.3, cam[2]))];
writeFileSync(path.join(dir, "panorama_ref.png"), panorama(refPos));
writeFileSync(path.join(dir, "panorama_mid.png"), panorama([W / 2, D / 2, 1.6]));
console.log("wrote panorama_ref.png, panorama_mid.png");

// ---------------------------------------------------------------- scene.glb
// glTF is Y up, -Z forward: plan (x, y, z) -> (x, z, -y). Plan rotation about Z -> rotation about Y.
const pos = [], nor = [], idx = [];
const faces = [
  [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [[-1, 0, 0], [0, 1, 0], [0, 0, -1]],
  [[0, 1, 0], [0, 0, 1], [1, 0, 0]], [[0, -1, 0], [0, 0, -1], [1, 0, 0]],
  [[0, 0, 1], [1, 0, 0], [0, 1, 0]], [[0, 0, -1], [-1, 0, 0], [0, 1, 0]],
];
for (const [nrm, u, v] of faces) {
  const b = pos.length / 3;
  for (const [su, sv] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) {
    pos.push(...[0, 1, 2].map((i) => 0.5 * nrm[i] + 0.5 * su * u[i] + 0.5 * sv * v[i]));
    nor.push(...nrm);
  }
  idx.push(b, b + 1, b + 2, b, b + 2, b + 3);
}
const posBuf = Buffer.from(new Float32Array(pos).buffer);
const norBuf = Buffer.from(new Float32Array(nor).buffer);
const idxBuf = Buffer.from(new Uint16Array(idx).buffer);
const bin = Buffer.concat([posBuf, norBuf, idxBuf, Buffer.alloc((4 - (idxBuf.length % 4)) % 4)]);

const catColor = { furniture: [0.36, 0.4, 0.35], fixture: [0.3, 0.33, 0.3], prop: [0.6, 0.56, 0.48], clutter: [0.66, 0.6, 0.5], structure: [0.45, 0.45, 0.43] };
const cats = [...new Set(plan.objects.map((o) => o.category))];
const materials = [
  { name: "shell", pbrMetallicRoughness: { baseColorFactor: [0.4, 0.41, 0.39, 1], metallicFactor: 0, roughnessFactor: 0.9 }, doubleSided: true },
  ...cats.map((c) => ({ name: c, pbrMetallicRoughness: { baseColorFactor: [...(catColor[c] ?? [0.5, 0.5, 0.5]), 1], metallicFactor: 0.1, roughnessFactor: 0.6 } })),
];
const meshes = materials.map((_, m) => ({ primitives: [{ attributes: { POSITION: 0, NORMAL: 1 }, indices: 2, material: m }] }));
const nodes = [];
const q = (deg) => [0, Math.sin((deg * Math.PI) / 360), 0, Math.cos((deg * Math.PI) / 360)];
const box = (name, mesh, x, y, z, w, d, h, rot = 0) =>
  nodes.push({ name, mesh, translation: [x, z + h / 2, -y], rotation: q(rot), scale: [Math.max(w, 0.02), Math.max(h, 0.02), Math.max(d, 0.02)] });
box("floor", 0, W / 2, D / 2, -0.05, W, D, 0.05);
box("ceiling", 0, W / 2, D / 2, H, W, D, 0.05);
box("wall_back", 0, W / 2, D + 0.05, 0, W, 0.1, H);
box("wall_left", 0, -0.05, D / 2, 0, 0.1, D, H);
box("wall_right", 0, W + 0.05, D / 2, 0, 0.1, D, H);
for (const o of plan.objects) box(o.id, 1 + cats.indexOf(o.category), o.x, o.y, o.z, o.w, o.d, o.h, o.rot);
const power = { low: 15, medium: 40, high: 120 };
const lightsExt = plan.lights.map((l) => ({ type: "point", color: hex(l.color), intensity: power[l.power] ?? 30, range: 12, name: l.id }));
plan.lights.forEach((l, i) => nodes.push({ name: l.id, translation: [l.x, l.z, -l.y], extensions: { KHR_lights_punctual: { light: i } } }));
const gltf = {
  asset: { version: "2.0", generator: "anyscene web placeholder" },
  extensionsUsed: ["KHR_lights_punctual"],
  extensions: { KHR_lights_punctual: { lights: lightsExt } },
  scene: 0,
  scenes: [{ nodes: nodes.map((_, i) => i) }],
  nodes,
  meshes,
  materials,
  buffers: [{ byteLength: bin.length }],
  bufferViews: [
    { buffer: 0, byteOffset: 0, byteLength: posBuf.length, target: 34962 },
    { buffer: 0, byteOffset: posBuf.length, byteLength: norBuf.length, target: 34962 },
    { buffer: 0, byteOffset: posBuf.length + norBuf.length, byteLength: idxBuf.length, target: 34963 },
  ],
  accessors: [
    { bufferView: 0, componentType: 5126, count: pos.length / 3, type: "VEC3", min: [-0.5, -0.5, -0.5], max: [0.5, 0.5, 0.5] },
    { bufferView: 1, componentType: 5126, count: nor.length / 3, type: "VEC3" },
    { bufferView: 2, componentType: 5123, count: idx.length, type: "SCALAR" },
  ],
};
let json = Buffer.from(JSON.stringify(gltf));
json = Buffer.concat([json, Buffer.alloc((4 - (json.length % 4)) % 4, 0x20)]);
const header = Buffer.alloc(12);
header.writeUInt32LE(0x46546c67, 0);
header.writeUInt32LE(2, 4);
header.writeUInt32LE(12 + 8 + json.length + 8 + bin.length, 8);
const ch = (len, type) => {
  const b = Buffer.alloc(8);
  b.writeUInt32LE(len, 0);
  b.writeUInt32LE(type, 4);
  return b;
};
writeFileSync(path.join(dir, "scene.glb"), Buffer.concat([header, ch(json.length, 0x4e4f534a), json, ch(bin.length, 0x004e4942), bin]));
console.log(`wrote scene.glb (${nodes.length} nodes, ${lightsExt.length} lights)`);
