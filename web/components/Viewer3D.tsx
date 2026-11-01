"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { disposeObject, envFor, loadEquirect, loadGlb, pmremFrom } from "@/lib/three-util";

export const modelName = (m?: string | null) => (!m ? "" : m.startsWith("tripo") ? "Tripo" : m.startsWith("meshy") ? "Meshy" : m);

interface Props {
  url: string;
  label: string;
  model?: string | null;
  refUrl?: string | null;
  /** The plan's size for this prop in metres (w, d, h); the mesh is scaled so its largest side matches. */
  size?: { w: number; d: number; h: number } | null;
  /** Equirectangular HDR/PNG of the scene's lighting; a neutral studio environment until there is one. */
  envUrl?: string | null;
  no?: number;
}

/** Orbitable view of one prop GLB at real scale, with its bounds, a ground shadow and the scene's light if known. */
export default function Viewer3D({ url, label, model, refUrl, size, envUrl, no }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<{ renderer: THREE.WebGLRenderer; scene: THREE.Scene; studio: THREE.Texture } | null>(null);
  const [progress, setProgress] = useState(0);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [dims, setDims] = useState<THREE.Vector3 | null>(null);
  const [envState, setEnvState] = useState<"studio" | "scene">("studio");

  useEffect(() => {
    const el = host.current!;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const studio = envFor(renderer);
    scene.environment = studio;
    sceneRef.current = { renderer, scene, studio };
    const cam = new THREE.PerspectiveCamera(32, 1, 0.01, 200);
    const controls = new OrbitControls(cam, renderer.domElement);
    controls.enableDamping = true;
    controls.autoRotate = true;
    controls.autoRotateSpeed = 1.0;
    controls.addEventListener("start", () => (controls.autoRotate = false));
    const key = new THREE.DirectionalLight(0xfff4e6, 1.4);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.radius = 5;
    scene.add(key, key.target);
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.ShadowMaterial({ opacity: 0.32 }));
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);

    let model: THREE.Object3D | null = null;
    let disposed = false;
    setState("loading");
    setProgress(0);
    setDims(null);
    loadGlb(url, setProgress)
      .then((g) => {
        if (disposed) return disposeObject(g);
        g.traverse((o) => {
          if ((o as THREE.Mesh).isMesh) o.castShadow = true;
        });
        // real scale: largest side = the plan's largest side (Tripo/Meshy meshes come in arbitrary units)
        const box = new THREE.Box3().setFromObject(g);
        const raw = box.getSize(new THREE.Vector3());
        const target = size ? Math.max(size.w, size.d, size.h) : Math.max(raw.x, raw.y, raw.z);
        const s = target / Math.max(raw.x, raw.y, raw.z, 1e-6);
        const c = box.getCenter(new THREE.Vector3());
        g.scale.setScalar(s);
        g.position.set(-c.x * s, -box.min.y * s, -c.z * s);
        const pivot = new THREE.Group();
        pivot.add(g);
        scene.add(pivot);
        model = pivot;
        const d = raw.clone().multiplyScalar(s);
        setDims(d);
        // dashed bounding box in ink
        const edges = new THREE.LineSegments(
          new THREE.EdgesGeometry(new THREE.BoxGeometry(d.x, d.y, d.z)),
          new THREE.LineDashedMaterial({ color: 0x1f1d1a, dashSize: Math.max(d.x, d.y, d.z) * 0.03, gapSize: Math.max(d.x, d.y, d.z) * 0.02, transparent: true, opacity: 0.55 }),
        );
        edges.position.y = d.y / 2;
        edges.computeLineDistances();
        scene.add(edges);
        const r = Math.max(d.x, d.y, d.z);
        ground.scale.setScalar(r * 6);
        key.position.set(r * 1.5, r * 3, r * 1.8);
        const sc = key.shadow.camera as THREE.OrthographicCamera;
        sc.left = sc.bottom = -r * 1.5;
        sc.right = sc.top = r * 1.5;
        sc.near = 0.01;
        sc.far = r * 10;
        sc.updateProjectionMatrix();
        controls.target.set(0, d.y * 0.45, 0);
        cam.position.set(r * 1.4, r * 0.9, r * 1.9);
        cam.near = r / 200;
        cam.far = r * 50;
        cam.updateProjectionMatrix();
        controls.minDistance = r * 0.4;
        controls.maxDistance = r * 8;
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
      studio.dispose();
      renderer.dispose();
      el.removeChild(renderer.domElement);
      sceneRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, size?.w, size?.d, size?.h]);

  // the scene's own lighting, when the endpoint provides it
  useEffect(() => {
    const ctx = sceneRef.current;
    if (!ctx) return;
    if (!envUrl) {
      ctx.scene.environment = ctx.studio;
      setEnvState("studio");
      return;
    }
    let live = true;
    let env: THREE.Texture | null = null;
    loadEquirect(envUrl)
      .then((tex) => {
        if (!live || !sceneRef.current) return tex.dispose();
        env = pmremFrom(ctx.renderer, tex);
        tex.dispose();
        ctx.scene.environment = env;
        setEnvState("scene");
      })
      .catch(() => setEnvState("studio"));
    return () => {
      live = false;
      if (sceneRef.current) sceneRef.current.scene.environment = sceneRef.current.studio;
      env?.dispose();
    };
  }, [envUrl, url]);

  return (
    <div className="viewer3d">
      <div className="viewer3d-canvas" ref={host} />
      {state === "loading" && (
        <div className="viewer3d-load">
          <div className="tick">
            <span style={{ width: `${Math.max(2, progress * 100)}%` }} />
          </div>
          <span>Loading mesh {Math.round(progress * 100)}%</span>
        </div>
      )}
      {state === "error" && <div className="viewer3d-load">This mesh couldn&apos;t be loaded.</div>}
      <div className="viewer3d-info">
        {refUrl && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={refUrl} alt={`${label} reference`} />
        )}
        <div>
          {no ? <div className="v3-no">P-{String(no).padStart(3, "0")}</div> : null}
          <div className="v3-label">{label}</div>
          {dims && (
            <div className="v3-dims">
              {dims.x.toFixed(2)} x {dims.z.toFixed(2)} x {dims.y.toFixed(2)} m
            </div>
          )}
          <div className="v3-meta">
            {model && <span className={`badge ${modelName(model).toLowerCase()}`}>{modelName(model)}</span>}
            <span className="v3-env">{envState === "scene" ? "lit by the scene" : "studio light"}</span>
          </div>
        </div>
      </div>
      <p className="viewer-hint">drag to orbit, scroll to zoom</p>
    </div>
  );
}
