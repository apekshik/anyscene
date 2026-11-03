"use client";

import { useRef, useState } from "react";
import Dials, { type DialValues } from "./Dials";
import InfoTip, { HELP } from "./InfoTip";
import SamplePicker from "./SamplePicker";

export interface BuilderInputsState {
  file: File | null;
  previewUrl: string;
  prompt: string;
  effort: string;
  dials: DialValues;
  floorPlan: File | null;
}

interface Props {
  value: BuilderInputsState;
  onChange: (v: BuilderInputsState) => void;
  disabled: boolean;
  canBuild: boolean;
  building: boolean;
  onBuild: () => void;
  /** Under the button: what a build costs, how many are left today. */
  note?: React.ReactNode;
  /** Mock build: replay a recorded build instead of calling fal. Undefined hides the switch (plain replays). */
  mock?: boolean;
  onMock?: (on: boolean) => void;
}

export default function BuilderInputs({ value, onChange, disabled, canBuild, building, onBuild, note, mock, onMock }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const set = (patch: Partial<BuilderInputsState>) => onChange({ ...value, ...patch });
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
            <span className="drop-hint">or click to choose. The builder matches its look, props and light.</span>
          </div>
        )}
        {value.previewUrl && <span className="drop-change">Replace</span>}
        <input ref={fileRef} type="file" accept="image/*" hidden onChange={(e) => take(e.target.files?.[0])} />
      </div>
      <p className="cap">
        {value.previewUrl ? `plate 1 of 1: ${value.file ? value.file.name : "recorded reference"}` : "no plate loaded"}
      </p>

      <SamplePicker current={value.file?.name} disabled={disabled} onPick={take} />

      <label className="field">
        <span className="field-label">
          Floor plan <span className="dim">optional</span>{" "}
          <InfoTip label="the floor plan" text="A sketch, photo or drawing of the layout. It decides the room's shape and where things go; the reference decides how they look." />
        </span>
        <input
          id="floor-plan"
          type="file"
          accept="image/*"
          disabled={disabled}
          onChange={(e) => set({ floorPlan: e.target.files?.[0] ?? null })}
        />
      </label>

      <h3 className="sheet-h">Direction</h3>
      <label className="field">
        <span className="field-label">Prompt</span>
        <textarea
          rows={3}
          value={value.prompt}
          disabled={disabled}
          placeholder="Anything the image can't show: it's 1 AM, rain outside, twice as deep"
          onChange={(e) => set({ prompt: e.target.value })}
        />
      </label>
      <Dials
        value={value.dials}
        onChange={(dials) => set({ dials })}
        disabled={disabled}
        note="Set a dial to override the reference; AUTO reads it from the image. The scene is delivered as a rig, so dials can be changed after the build."
      />
      <label className="field">
        <span className="field-label">Builder effort <InfoTip label="builder effort" text={HELP.effort} /></span>
        <select value={value.effort} disabled={disabled} onChange={(e) => set({ effort: e.target.value })}>
          {["low", "medium", "high", "xhigh", "max"].map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </label>
      {mock !== undefined && (
        <label className="mock-switch">
          <input type="checkbox" checked={mock} disabled={disabled} onChange={(e) => onMock?.(e.target.checked)} />
          <span>
            <b>Mock build</b> <span className="dim">free: replays a recorded build through the UI, nothing runs on fal</span>
          </span>
        </label>
      )}
      <button className="primary" disabled={!canBuild} onClick={onBuild}>
        {building ? "Building" : mock ? "Build the scene (mock)" : "Build the scene"}
      </button>
      <p className="fine">
        {mock
          ? "Plays at 16x; change the speed in the toolbar. The frames and results are from a recorded build, not your plate."
          : <>One agent builds it end to end and loops with a critic. Up to 2 hours.{note ? <> {note}</> : null}</>}
      </p>
    </div>
  );
}
