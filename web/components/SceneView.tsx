"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { disposeObject, envFor, loadEquirect, loadGlb, pmremFrom } from "@/lib/three-util";

/** Free-orbit view of the assembled scene glTF (KHR_lights_punctual lights come in with it), lit by the
 *  reference-camera panorama so it approximates Blender's lighting. */
export default function SceneView({
  url,
  envUrl,
  camera,
}: {
  url: string;
  envUrl?: string | null;
  camera?: { position: number[]; look_at: number[]; lens_mm: number } | null;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [progress, setProgress] = useState(0);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [info, setInfo] = useState("");

  useEffect(() => {
    const el = host.current!;
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xefe8d6);
    const studio = envFor(renderer);
    scene.environment = studio;
    let env: THREE.Texture | null = null;
    const cam = new THREE.PerspectiveCamera(45, 1, 0.05, 500);
    const controls = new OrbitControls(cam, renderer.domElement);
    controls.enableDamping = true;
    let model: THREE.Object3D | null = null;
    let disposed = false;
    setState("loading");

    if (envUrl) {
      loadEquirect(envUrl)
        .then((tex) => {
          if (disposed) return tex.dispose();
          env = pmremFrom(renderer, tex);
          tex.dispose();
          scene.environment = env;
          scene.environmentIntensity = 0.8;
        })
        .catch(() => {});
    }

    loadGlb(url, setProgress)
      .then((g) => {
        if (disposed) return disposeObject(g);
        scene.add(g);
        model = g;
        let lights = 0;
        let meshes = 0;
        g.traverse((o) => {
          if ((o as THREE.Light).isLight) lights++;
          if ((o as THREE.Mesh).isMesh) meshes++;
        });
        setInfo(`${meshes} meshes, ${lights} lights`);
        const box = new THREE.Box3().setFromObject(g);
        const size = box.getSize(new THREE.Vector3());
        const c = box.getCenter(new THREE.Vector3());
        const r = Math.max(size.x, size.z);
        controls.target.set(c.x, size.y * 0.25 + box.min.y, c.z);
        // high three-quarter view from the entrance side (glTF +Z is the plan's front wall)
        cam.position.set(c.x + r * 0.35, box.min.y + r * 0.75, box.max.z + r * 0.55);
        if (!camera) {
          // no camera from the build: stand inside the set at eye height, looking down its length
          cam.position.set(c.x, box.min.y + Math.min(1.7, size.y * 0.5), c.z + size.z * 0.35);
          controls.target.set(c.x, box.min.y + Math.min(1.2, size.y * 0.35), c.z - size.z * 0.2);
        } else {
          // start where the reference camera stands (plan x, y, z -> glTF x, z, -y), inside the set
          const [px, py, pz] = camera.position;
          const [lx, ly, lz] = camera.look_at;
          const inside = (v: number, lo: number, hi: number) => Math.min(hi - 0.3, Math.max(lo + 0.3, v));
          cam.position.set(inside(px, box.min.x, box.max.x), inside(pz, box.min.y, box.max.y), inside(-py, box.min.z, box.max.z));
          controls.target.set(lx, lz, -ly);
          cam.fov = (2 * Math.atan(12 / camera.lens_mm) * 180) / Math.PI;
          cam.updateProjectionMatrix();
        }
        controls.maxDistance = r * 3;
        setState("ready");
      })
      .catch(() => !disposed && setState("error"));

    const resize = () => {
      renderer.setSize(el.clientWidth, el.clientHeight);
      cam.aspect = el.clientWidth / Math.max(1, el.clientHeight);
      cam.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();
    let raf = 0;
    const loop = () => {
      raf = requestAnimationFrame(loop);
      controls.update();
      renderer.render(scene, cam);
    };
    loop();
    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      ro.disconnect();
      controls.dispose();
      if (model) disposeObject(model);
      env?.dispose();
      studio.dispose();
      renderer.dispose();
      el.removeChild(renderer.domElement);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, envUrl]);

  return (
    <div className="viewer3d">
      <div className="viewer3d-canvas" ref={host} />
      {state === "loading" && (
        <div className="viewer3d-load">
          <div className="tick">
            <span style={{ width: `${Math.max(2, progress * 100)}%` }} />
          </div>
          <span>Loading set model {Math.round(progress * 100)}%</span>
        </div>
      )}
      {state === "error" && <div className="viewer3d-load">The set model couldn&apos;t be loaded.</div>}
      {info && <span className="live-tag">{info}{envUrl ? ", lit by the 360 plate" : ""}</span>}
      <p className="viewer-hint">drag to orbit, right-drag to pan, scroll to zoom</p>
    </div>
  );
}
