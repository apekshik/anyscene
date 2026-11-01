// three.js helpers: a shared GLB cache, the 3D-tab viewer setup, and the prop shelf's turntable sprites.
//
// Prop GLBs from Tripo/Meshy are 10-60 MB each with 4K PBR textures, so the shelf can't keep 20 live WebGL scenes.
// Each prop is loaded once, rendered into a 48-frame turntable strip on one shared offscreen renderer, then freed;
// tiles animate the strip with CSS. Only the 3D tab keeps a live model.
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

export const SPRITE_FRAMES = 48;
export const SPRITE_SIZE = 176;

const loader = new GLTFLoader();

export function loadGlb(url: string, onProgress?: (f: number) => void): Promise<THREE.Group> {
  return new Promise((resolve, reject) => {
    loader.load(
      url,
      (g) => resolve(g.scene),
      (e) => onProgress && e.total && onProgress(e.loaded / e.total),
      (err) => reject(err),
    );
  });
}

/** Centre on the ground and scale so the largest side is 1 unit; returns the bounding size. */
export function normalize(obj: THREE.Object3D) {
  const box = new THREE.Box3().setFromObject(obj);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const s = 1 / Math.max(size.x, size.y, size.z, 1e-6);
  obj.position.set(-center.x * s, -box.min.y * s, -center.z * s);
  obj.scale.setScalar(s);
  const pivot = new THREE.Group();
  pivot.add(obj);
  return { pivot, size: size.multiplyScalar(s) };
}

export function disposeObject(obj: THREE.Object3D) {
  obj.traverse((o) => {
    const m = o as THREE.Mesh;
    if (m.geometry) m.geometry.dispose();
    const mats = Array.isArray(m.material) ? m.material : m.material ? [m.material] : [];
    for (const mat of mats) {
      for (const v of Object.values(mat)) if (v instanceof THREE.Texture) v.dispose();
      mat.dispose();
    }
  });
}

export function envFor(renderer: THREE.WebGLRenderer) {
  const pmrem = new THREE.PMREMGenerator(renderer);
  const env = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  pmrem.dispose();
  return env;
}

// ---------------------------------------------------------------- turntable sprites

let shared: { renderer: THREE.WebGLRenderer; env: THREE.Texture } | null = null;
function sharedRenderer() {
  if (!shared) {
    const canvas = document.createElement("canvas");
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(1);
    renderer.setSize(SPRITE_SIZE, SPRITE_SIZE, false);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    shared = { renderer, env: envFor(renderer) };
  }
  return shared;
}

const spriteCache = new Map<string, Promise<string>>();
const queue: (() => Promise<void>)[] = [];
let active = 0;
const MAX_CONCURRENT = 2;

function pump() {
  while (active < MAX_CONCURRENT && queue.length) {
    const job = queue.shift()!;
    active++;
    job().finally(() => {
      active--;
      pump();
    });
  }
}

/** A blob URL of a horizontal strip of SPRITE_FRAMES turntable frames for this GLB (queued, cached). */
export function turntableSprite(url: string): Promise<string> {
  let p = spriteCache.get(url);
  if (!p) {
    p = new Promise<string>((resolve, reject) => {
      queue.push(async () => {
        try {
          resolve(await renderSprite(url));
        } catch (e) {
          reject(e);
        }
      });
      pump();
    });
    spriteCache.set(url, p);
  }
  return p;
}

async function renderSprite(url: string): Promise<string> {
  const model = await loadGlb(url);
  const { renderer, env } = sharedRenderer();
  const scene = new THREE.Scene();
  scene.environment = env;
  const { pivot, size } = normalize(model);
  scene.add(pivot);
  const key = new THREE.DirectionalLight(0xfff1e0, 1.6);
  key.position.set(2, 3, 2);
  scene.add(key, new THREE.HemisphereLight(0xdfe6ff, 0x1a1712, 0.5));
  const cam = new THREE.PerspectiveCamera(30, 1, 0.01, 50);
  const h = size.y;
  const dist = 2.35;
  const strip = document.createElement("canvas");
  strip.width = SPRITE_SIZE * SPRITE_FRAMES;
  strip.height = SPRITE_SIZE;
  const ctx = strip.getContext("2d")!;
  for (let i = 0; i < SPRITE_FRAMES; i++) {
    const a = (i / SPRITE_FRAMES) * Math.PI * 2 + Math.PI * 0.25;
    cam.position.set(Math.sin(a) * dist, h * 0.5 + 0.55, Math.cos(a) * dist);
    cam.lookAt(0, h * 0.45, 0);
    renderer.render(scene, cam);
    ctx.drawImage(renderer.domElement, i * SPRITE_SIZE, 0);
    if (i % 12 === 11) await new Promise((r) => requestAnimationFrame(r));
  }
  disposeObject(model);
  renderer.renderLists.dispose();
  const blob: Blob = await new Promise((r) => strip.toBlob((b) => r(b!), "image/webp", 0.9));
  return URL.createObjectURL(blob);
}

// ---------------------------------------------------------------- equirectangular environments

/** Load an equirectangular image (.hdr, or PNG/JPG) as a texture three can use as background or environment. */
export async function loadEquirect(url: string): Promise<THREE.Texture> {
  let tex: THREE.Texture;
  if (/\.hdr(\?|$)/i.test(url)) {
    const { HDRLoader } = await import("three/examples/jsm/loaders/HDRLoader.js");
    tex = await new HDRLoader().loadAsync(url);
  } else {
    tex = await new THREE.TextureLoader().loadAsync(url);
    tex.colorSpace = THREE.SRGBColorSpace;
  }
  tex.mapping = THREE.EquirectangularReflectionMapping;
  return tex;
}

/** Prefiltered environment for PBR lighting from an equirect texture. */
export function pmremFrom(renderer: THREE.WebGLRenderer, tex: THREE.Texture) {
  const pmrem = new THREE.PMREMGenerator(renderer);
  const env = pmrem.fromEquirectangular(tex).texture;
  pmrem.dispose();
  return env;
}
