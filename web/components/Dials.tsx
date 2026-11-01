"use client";

import { useState } from "react";
import { DIALS } from "@/lib/types";
import InfoTip, { HELP } from "./InfoTip";

export type DialValues = Record<string, number | string | undefined>;

/** Only the dials the user set; the endpoint reads the rest from the reference. */
export const setDials = (d: DialValues) =>
  Object.fromEntries(Object.entries(d).filter(([, v]) => v !== undefined)) as Record<string, number | string>;

interface Props {
  value: DialValues;
  onChange: (v: DialValues) => void;
  disabled: boolean;
  note: string;
}

export default function Dials({ value, onChange, disabled, note }: Props) {
  const [open, setOpen] = useState(false);
  const setDial = (k: string, v: number | string | undefined) => onChange({ ...value, [k]: v });
  const count = Object.values(value).filter((v) => v !== undefined).length;

  return (
    <div className="dials">
      <button className="dials-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span>Dials <InfoTip label="dials" text={HELP.dials} /></span>
        <span className="dials-sum">{count ? `${count} set` : "read from the image"}</span>
        <span className={`chev ${open ? "open" : ""}`} aria-hidden />
      </button>
      {open && (
        <div className="dials-body">
          {DIALS.map((d) => {
            const v = value[d.key];
            const isSet = v !== undefined;
            return (
              <div className={`dial ${isSet ? "set" : ""}`} key={d.key}>
                <div className="dial-top">
                  <span className="dial-name">{d.label}</span>
                  {isSet ? (
                    <button className="dial-reset" onClick={() => setDial(d.key, undefined)} disabled={disabled}>
                      {d.kind === "range" ? Number(v).toFixed(2) : String(v)} <span aria-hidden>×</span>
                    </button>
                  ) : (
                    <span className="dial-auto">AUTO</span>
                  )}
                </div>
                {d.kind === "range" ? (
                  <div className="dial-range">
                    <span>{d.lo}</span>
                    <input
                      type="range"
                      min={d.min}
                      max={d.max}
                      step={0.05}
                      disabled={disabled}
                      value={isSet ? Number(v) : (d.min + d.max) / 2}
                      onChange={(e) => setDial(d.key, Number(e.target.value))}
                      aria-label={d.label}
                    />
                    <span>{d.hi}</span>
                  </div>
                ) : (
                  <div className="chips" role="group" aria-label={d.label}>
                    {d.options.map((o) => (
                      <button
                        key={o}
                        className={v === o ? "on" : ""}
                        disabled={disabled}
                        onClick={() => setDial(d.key, v === o ? undefined : o)}
                      >
                        {o}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
          <p className="fine">{note}</p>
        </div>
      )}
    </div>
  );
}
