"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { SAMPLES, sampleFile, sampleThumb, type Sample } from "@/lib/samples";

const narrow = () => typeof window !== "undefined" && window.innerWidth < 760;

/** "Try a sample plate": one button in the sidebar; the plates open in a panel floating just right of the sidebar
 *  (full width on a phone), so the inputs below stay in view. Closes on a pick, Escape or a click outside. */
export default function SamplePicker({ current, disabled, onPick }: { current?: string; disabled: boolean; onPick: (f: File) => void }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number; width: number } | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState("");
  const btn = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  // anchor beside the sidebar, level with the button, kept inside the window
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const b = btn.current?.getBoundingClientRect();
      const side = btn.current?.closest("aside")?.getBoundingClientRect();
      if (!b) return;
      if (narrow()) return setPos(null);
      // as wide as the space right of the sidebar allows (up to 1200 px), level with the button, inside the window
      const left = (side?.right ?? b.right) + 12;
      const width = Math.min(1200, window.innerWidth - left - 24);
      const h = panel.current?.offsetHeight ?? 0;
      setPos({ top: Math.max(12, Math.min(b.top - 12, window.innerHeight - h - 12)), left, width });
    };
    place();
    // again whenever its size changes (floating width applied, thumbnails loaded)
    const ro = new ResizeObserver(place);
    if (panel.current) ro.observe(panel.current);
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const down = (e: PointerEvent) => {
      const t = e.target as Node;
      if (!panel.current?.contains(t) && !btn.current?.contains(t)) setOpen(false);
    };
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", down);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("pointerdown", down);
      document.removeEventListener("keydown", key);
    };
  }, [open]);

  const pick = async (s: Sample) => {
    setLoading(s.id);
    setError("");
    try {
      onPick(await sampleFile(s));
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(null);
    }
  };

  return (
    <>
      <button ref={btn} type="button" className="secondary sample-open" disabled={disabled} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        Try a sample plate <span aria-hidden>{open ? "◂" : "▸"}</span>
      </button>
      {open && (
        <div
          ref={panel}
          className={`sample-panel ${pos || !narrow() ? "" : "docked"}`}
          style={pos ? { top: pos.top, left: pos.left, width: pos.width } : undefined}
          role="dialog"
          aria-label="Sample reference plates"
        >
          <div className="sample-panel-head">
            <span className="field-label">Sample plates</span>
            <button type="button" className="text-btn" onClick={() => setOpen(false)}>
              Close
            </button>
          </div>
          <div className="samples-grid">
            {SAMPLES.map((s) => (
              <button
                key={s.id}
                type="button"
                className={`sample ${current === `${s.id}.jpg` ? "on" : ""}`}
                disabled={loading !== null}
                aria-label={`Use the sample reference: ${s.label}`}
                onClick={() => pick(s)}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={sampleThumb(s.id)} alt="" />
                <span>{loading === s.id ? "Loading" : s.label}</span>
              </button>
            ))}
          </div>
          {error && <p className="error-note">{error}</p>}
        </div>
      )}
    </>
  );
}
