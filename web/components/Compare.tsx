"use client";

import { useRef, useState } from "react";

/** Reference on the left, render on the right, split by a draggable line. Both fill the render's frame. */
export default function Compare({ left, right, rightLabel }: { left: string; right: string; rightLabel: string }) {
  const [pos, setPos] = useState(0.5);
  const [aspect, setAspect] = useState(16 / 9);
  const box = useRef<HTMLDivElement>(null);
  const drag = (clientX: number) => {
    const r = box.current?.getBoundingClientRect();
    if (r) setPos(Math.min(1, Math.max(0, (clientX - r.left) / r.width)));
  };
  return (
    <div className="compare-wrap">
      <div
        className="compare"
        ref={box}
        style={{ aspectRatio: String(aspect) }}
        onPointerDown={(e) => {
          (e.target as HTMLElement).setPointerCapture(e.pointerId);
          drag(e.clientX);
        }}
        onPointerMove={(e) => e.buttons && drag(e.clientX)}
        role="slider"
        aria-label="Compare reference and render"
        aria-valuenow={Math.round(pos * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") setPos((p) => Math.max(0, p - 0.05));
          if (e.key === "ArrowRight") setPos((p) => Math.min(1, p + 0.05));
        }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={right}
          alt={rightLabel}
          onLoad={(e) => setAspect(e.currentTarget.naturalWidth / e.currentTarget.naturalHeight)}
          draggable={false}
        />
        <div className="compare-left" style={{ clipPath: `inset(0 ${(1 - pos) * 100}% 0 0)` }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={left} alt="Reference" draggable={false} />
        </div>
        <div className="compare-line" style={{ left: `${pos * 100}%` }}>
          <span />
        </div>
        <span className="compare-tag l">Reference</span>
        <span className="compare-tag r">{rightLabel}</span>
      </div>
    </div>
  );
}
