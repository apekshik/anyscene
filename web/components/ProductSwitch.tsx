"use client";

/** The AnyAll products, picked from the slate's PRODUCTION cell. Each is its own fal app behind the same call sheet. */
const PRODUCTS = [
  { id: "anyscene", label: "AnyScene", href: "/", ready: true },
  { id: "anykit", label: "AnyKit", href: "/?product=anykit", ready: false },
] as const;

export default function ProductSwitch({ current }: { current: string }) {
  return (
    <label className="product-switch">
      <span className="sr-only">Product</span>
      <select
        id="product-switch"
        value={current}
        onChange={(e) => {
          const p = PRODUCTS.find((x) => x.id === e.target.value);
          if (p && p.ready) window.location.href = p.href;
        }}
      >
        {PRODUCTS.map((p) => (
          <option key={p.id} value={p.id} disabled={!p.ready}>
            {p.label}
            {p.ready ? "" : " (soon)"}
          </option>
        ))}
      </select>
    </label>
  );
}
