"use client";

import { useEffect, useState } from "react";

/** Crossfades to a new image once it has loaded, so arriving renders dissolve in rather than pop. */
export default function Fade({ src, alt, className = "" }: { src: string; alt: string; className?: string }) {
  const [layers, setLayers] = useState<{ src: string; key: number; shown: boolean }[]>([]);
  useEffect(() => {
    if (!src) return;
    const key = Date.now() + Math.random();
    setLayers((l) => (l[l.length - 1]?.src === src ? l : [...l.slice(-1), { src, key, shown: false }]));
  }, [src]);
  const loaded = (key: number) => {
    setLayers((l) => l.map((x) => (x.key === key ? { ...x, shown: true } : x)));
    setTimeout(() => setLayers((l) => (l[l.length - 1]?.key === key ? l.filter((x) => x.key === key) : l)), 700);
  };
  return (
    <div className={`fade ${className}`}>
      {layers.map((l) => (
        // eslint-disable-next-line @next/next/no-img-element
        <img key={l.key} src={l.src} alt={alt} className={l.shown ? "shown" : ""} onLoad={() => loaded(l.key)} />
      ))}
    </div>
  );
}
