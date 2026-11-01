"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { loadEquirect } from "@/lib/three-util";

/** Drag-to-look viewer for one equirectangular render: the texture on the inside of a sphere. */
export default function Pano360({ url }: { url: string }) {
  const host = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    const el = host.current!;
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xefe8d6);
    const cam = new THREE.PerspectiveCamera(75, 1, 0.1, 100);
    let tex: THREE.Texture | null = null;
    let disposed = false;
    setState("loading");
    loadEquirect(url)
      .then((t) => {
        if (disposed) return t.dispose();
        tex = t;
        scene.background = t; // equirect background renders as the inside of a sphere
        setState("ready");
      })
      .catch(() => !disposed && setState("error"));

    // look state: yaw 0 looks at the centre of the image (u = 0.5)
    let yaw = 0;
    let pitch = 0;
    let fov = 75;
    let dragging = false;
    let idle = true;
    let lx = 0;
    let ly = 0;
    const down = (e: PointerEvent) => {
      dragging = true;
      idle = false;
      lx = e.clientX;
      ly = e.clientY;
      el.setPointerCapture(e.pointerId);
    };
    const move = (e: PointerEvent) => {
      if (!dragging) return;
      const k = (fov / el.clientHeight) * (Math.PI / 180);
      yaw += (e.clientX - lx) * k;
      pitch = Math.max(-1.45, Math.min(1.45, pitch + (e.clientY - ly) * k));
      lx = e.clientX;
      ly = e.clientY;
    };
    const up = () => (dragging = false);
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      fov = Math.max(30, Math.min(100, fov + e.deltaY * 0.04));
      cam.fov = fov;
      cam.updateProjectionMatrix();
    };
    const key = (e: KeyboardEvent) => {
      const step = 0.08;
      if (e.key === "ArrowLeft") yaw += step;
      else if (e.key === "ArrowRight") yaw -= step;
      else if (e.key === "ArrowUp") pitch = Math.min(1.45, pitch + step);
      else if (e.key === "ArrowDown") pitch = Math.max(-1.45, pitch - step);
      else return;
      idle = false;
      e.preventDefault();
    };
    el.addEventListener("pointerdown", down);
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
    el.addEventListener("wheel", wheel, { passive: false });
    el.addEventListener("keydown", key);

    const resize = () => {
      renderer.setSize(el.clientWidth, el.clientHeight);
      cam.aspect = el.clientWidth / Math.max(1, el.clientHeight);
      cam.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();
    let raf = 0;
    const dir = new THREE.Vector3();
    const loop = () => {
      raf = requestAnimationFrame(loop);
      if (idle) yaw -= 0.0007;
      // three maps u = 0.5 of an equirect background to -Z
      dir.set(-Math.sin(yaw) * Math.cos(pitch), Math.sin(pitch), -Math.cos(yaw) * Math.cos(pitch));
      cam.lookAt(dir);
      renderer.render(scene, cam);
    };
    loop();
    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      ro.disconnect();
      el.removeEventListener("pointerdown", down);
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", up);
      el.removeEventListener("wheel", wheel);
      el.removeEventListener("keydown", key);
      tex?.dispose();
      renderer.dispose();
      el.removeChild(renderer.domElement);
    };
  }, [url]);

  return (
    <div className="pano">
      <div className="pano-canvas" ref={host} tabIndex={0} aria-label="360 view: drag or use arrow keys to look around, scroll to zoom" role="img" />
      {state === "loading" && <div className="viewer3d-load">Loading 360 plate</div>}
      {state === "error" && <div className="viewer3d-load">This panorama couldn&apos;t be loaded.</div>}
      <p className="viewer-hint">drag to look around, scroll to zoom</p>
    </div>
  );
}
