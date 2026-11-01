"use client";

import { useRef, useState } from "react";
import Dials from "./Dials";

export interface InputsState {
  file: File | null;
  previewUrl: string;
  prompt: string;
  dials: Record<string, number | string | undefined>;
  effort: string;
  tier: "draft" | "full";
}

interface Props {
  value: InputsState;
  onChange: (v: InputsState) => void;
  disabled: boolean;
  onPlan: () => void;
  canPlan: boolean;
  planning: boolean;
}

export default function Inputs({ value, onChange, disabled, onPlan, canPlan, planning }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const set = (patch: Partial<InputsState>) => onChange({ ...value, ...patch });

  const take = (f: File | undefined) => {
    if (!f || !f.type.startsWith("image/")) return;
    if (value.previewUrl.startsWith("blob:")) URL.revokeObjectURL(value.previewUrl);
    set({ file: f, previewUrl: URL.createObjectURL(f) });
  };

  return (
    <div className="inputs">
      <h3 className="sheet-h">Reference plate</h3>
      <div
        className={`drop ${over ? "over" : ""} ${value.previewUrl ? "has" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          if (!disabled) take(e.dataTransfer.files?.[0]);
        }}
        onClick={() => !disabled && fileRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && fileRef.current?.click()}
        aria-label="Reference image: drop or choose a file"
      >
        {value.previewUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={value.previewUrl} alt="Reference" />
        ) : (
          <div className="drop-empty">
            <span className="drop-title">Drop the reference plate</span>
            <span className="drop-hint">or click to choose. The look, the materials and the props come from here.</span>
          </div>
        )}
        {value.previewUrl && <span className="drop-change">Replace</span>}
        <input ref={fileRef} type="file" accept="image/*" hidden onChange={(e) => take(e.target.files?.[0])} />
      </div>
      <p className="cap">
        {value.previewUrl ? `plate 1 of 1: ${value.file ? value.file.name : "recorded reference"}` : "no plate loaded"}
      </p>
      <h3 className="sheet-h">Direction</h3>

      <label className="field">
        <span className="field-label">Prompt</span>
        <textarea
          rows={2}
          value={value.prompt}
          disabled={disabled}
          placeholder="Anything the image can’t show: it’s 1 AM, rain outside, twice as deep"
          onChange={(e) => set({ prompt: e.target.value })}
        />
      </label>

      <Dials
        value={value.dials}
        onChange={(dials) => set({ dials })}
        disabled={disabled}
        note="The old pipeline records dials but doesn't apply them; the scene builder does."
      />

      <div className="row2">
        <label className="field">
          <span className="field-label">Planning effort</span>
          <select value={value.effort} disabled={disabled} onChange={(e) => set({ effort: e.target.value })}>
            {["low", "medium", "high", "xhigh", "max"].map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </label>
        <div className="field">
          <span className="field-label">Build tier</span>
          <div className="seg" role="group" aria-label="Build tier">
            {(["draft", "full"] as const).map((t) => (
              <button key={t} className={value.tier === t ? "on" : ""} disabled={disabled} onClick={() => set({ tier: t })}>
                {t === "draft" ? "Draft" : "Full"}
              </button>
            ))}
          </div>
        </div>
      </div>

      <button className="primary" disabled={!canPlan} onClick={onPlan}>
        {planning ? "Planning…" : "Plan the scene"}
      </button>
    </div>
  );
}
