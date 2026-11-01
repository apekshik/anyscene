/** A red rubber stamp. Thunks in (scale + rotate) the first time it renders. */
export default function Stamp({ children, tilt = -4, big = false, ink = false }: { children: React.ReactNode; tilt?: number; big?: boolean; ink?: boolean }) {
  return (
    <span className={`stamp ${big ? "big" : ""} ${ink ? "ink" : ""}`} style={{ ["--tilt" as string]: `${tilt}deg` } as React.CSSProperties}>
      {children}
    </span>
  );
}
