"use client";

import { useCallback, useEffect, useRef } from "react";

export interface LightboxItem {
  url: string;
  caption?: string;
}

/** Full-screen viewer for a set of images: chevrons or ←/→ to move, Esc or a click outside to close. */
export default function Lightbox({ items, index, onIndex, onClose }: {
  items: LightboxItem[];
  index: number;
  onIndex: (i: number) => void;
  onClose: () => void;
}) {
  const n = items.length;
  const go = useCallback((d: number) => onIndex((index + d + n) % n), [index, n, onIndex]);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") go(1);
      else if (e.key === "ArrowLeft") go(-1);
      else if (e.key === "Escape") onClose();
      else if (e.key === "Home") onIndex(0);
      else if (e.key === "End") onIndex(n - 1);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [go, onClose, onIndex, n]);

  // swipe on touch screens
  const touchX = useRef<number | null>(null);
  const item = items[index];
  if (!item) return null;

  return (
    <div
      className="lightbox"
      role="dialog"
      aria-modal="true"
      aria-label={`Image ${index + 1} of ${n}`}
      onClick={onClose}
      onTouchStart={(e) => (touchX.current = e.touches[0].clientX)}
      onTouchEnd={(e) => {
        if (touchX.current === null) return;
        const dx = e.changedTouches[0].clientX - touchX.current;
        if (Math.abs(dx) > 50) go(dx < 0 ? 1 : -1);
        touchX.current = null;
      }}
    >
      <div className="lightbox-top" onClick={(e) => e.stopPropagation()}>
        <span className="lightbox-count">
          {String(index + 1).padStart(2, "0")} / {String(n).padStart(2, "0")}
        </span>
        <span className="lightbox-keys">← → to move · Esc to close</span>
        <a className="text-btn" href={item.url} target="_blank" rel="noreferrer">
          Open full size
        </a>
        <button ref={closeRef} className="lightbox-close" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>
      {n > 1 && (
        <button className="lightbox-nav prev" aria-label="Previous image" onClick={(e) => { e.stopPropagation(); go(-1); }}>
          <span aria-hidden>‹</span>
        </button>
      )}
      <figure className="lightbox-figure" onClick={(e) => e.stopPropagation()}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img key={item.url} src={item.url} alt={item.caption || `Image ${index + 1}`} />
        {item.caption && <figcaption>{item.caption}</figcaption>}
      </figure>
      {n > 1 && (
        <button className="lightbox-nav next" aria-label="Next image" onClick={(e) => { e.stopPropagation(); go(1); }}>
          <span aria-hidden>›</span>
        </button>
      )}
      {n > 1 && (
        <div className="lightbox-strip" onClick={(e) => e.stopPropagation()}>
          {items.map((x, i) => (
            <button key={x.url + i} className={i === index ? "on" : ""} onClick={() => onIndex(i)} aria-label={`Image ${i + 1}`}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={x.url} alt="" loading="lazy" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
