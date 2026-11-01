"use client";

import { useState } from "react";
import type { BuilderEvent, BuilderResponse, ShotsResponse } from "@/lib/builder";
import { LiveSource } from "@/lib/sources";
import Dials, { setDials, type DialValues } from "./Dials";
import InfoTip, { HELP } from "./InfoTip";

type Line = { t: number; stage: string; text: string; image?: string };

/** Order shots of a finished build: pick scouting previews or describe new ones, as stills or as video
 *  (the builder app's /scene2image, /scene2video). The shots agent's events stream into a short log; results land below. */
export default function ShotsOrder({ res, source }: { res: BuilderResponse; source: LiveSource | null }) {
  const [picked, setPicked] = useState<string[]>([]);
  const [described, setDescribed] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState<"images" | "video">("images");
  const [seconds, setSeconds] = useState(6);
  const [handheld, setHandheld] = useState<"none" | "walk" | "subtle">("subtle");
  const [dials, setDialValues] = useState<DialValues>({});
  const [lines, setLines] = useState<Line[]>([]);
  const [busy, setBusy] = useState(false);
  const [out, setOut] = useState<ShotsResponse | null>(null);
  const [error, setError] = useState("");

  const previews = res.previews ?? [];
  const count = picked.length + described.length;
  const toggle = (n: string) => setPicked((p) => (p.includes(n) ? p.filter((x) => x !== n) : [...p, n]));

  const order = async () => {
    if (!source || !count) return;
    setBusy(true);
    setOut(null);
    setError("");
    setLines([]);
    try {
      const r = await source.shots(
        {
          build_id: res.build_id,
          mode,
          shots: [...picked.map((name) => ({ name })), ...described.map((description) => ({ description }))],
          settings: mode === "video" ? { seconds, handheld } : {},
          dials: setDials(dials),
        },
        {
          onEvent: (ev: BuilderEvent) => {
            if (ev.stage === "heartbeat" || ev.stage === "log") return;
            setLines((l) => [...l, { t: ev.t, stage: ev.stage, text: ev.message, image: ev.preview_url }]);
          },
        },
      );
      setOut(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="shots-order">
      <h3 className="sheet-h">
        Order shots <span className="sheet-h-sub">scene to {mode === "images" ? "images" : "video"}</span>{" "}
        <InfoTip label="shot orders" text={HELP.shots} />
      </h3>
      {!source && <p className="fine">Shot orders run on a live build. Open a finished build without ?replay.</p>}

      {previews.length > 0 && (
        <div className="shots-previews" role="group" aria-label="Scouting previews">
          {previews.map((p) => (
            <button key={p.name} className={picked.includes(p.name) ? "on" : ""} onClick={() => toggle(p.name)}
              aria-pressed={picked.includes(p.name)} disabled={busy}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={p.url} alt="" />
              <span>{p.name.replace(/_/g, " ")}</span>
            </button>
          ))}
        </div>
      )}

      <div className="shots-describe">
        <input id="shot-describe" value={draft} disabled={busy} onChange={(e) => setDraft(e.target.value)}
          placeholder="Describe a shot: slow push along the pastry case, ending close on the croissants"
          onKeyDown={(e) => {
            if (e.key === "Enter" && draft.trim()) {
              setDescribed((d) => [...d, draft.trim()]);
              setDraft("");
            }
          }} />
        <button className="secondary" disabled={busy || !draft.trim()}
          onClick={() => { setDescribed((d) => [...d, draft.trim()]); setDraft(""); }}>Add</button>
      </div>
      {described.length > 0 && (
        <ul className="shots-list">
          {described.map((d, i) => (
            <li key={i}>
              {d}{" "}
              <button className="text-btn" disabled={busy} onClick={() => setDescribed((x) => x.filter((_, k) => k !== i))}>
                remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="shots-settings">
        <div className="seg small" role="group" aria-label="Output">
          {(["images", "video"] as const).map((m) => (
            <button key={m} className={mode === m ? "on" : ""} onClick={() => setMode(m)} disabled={busy}>
              {m === "images" ? "Stills" : "Video"}
            </button>
          ))}
        </div>
        {mode === "video" && (
          <>
            <label className="field inline">
              <span className="field-label">Seconds</span>
              <input id="shot-seconds" type="number" min={2} max={30} value={seconds} disabled={busy}
                onChange={(e) => setSeconds(Number(e.target.value) || 6)} />
            </label>
            <div className="seg small" role="group" aria-label="Camera">
              {(["none", "subtle", "walk"] as const).map((h) => (
                <button key={h} className={handheld === h ? "on" : ""} onClick={() => setHandheld(h)} disabled={busy}>
                  {h === "none" ? "Locked off" : h === "subtle" ? "Subtle handheld" : "Walk"}
                </button>
              ))}
            </div>
          </>
        )}
      </div>
      <Dials value={dials} onChange={setDialValues} disabled={busy}
        note="Changes the set for this order only; the build stays as it is." />
      <button className="primary" disabled={!source || !count || busy} onClick={order}>
        {busy ? "Shooting" : `Shoot ${count || ""} ${mode === "images" ? "still" : "clip"}${count === 1 ? "" : "s"}`}
      </button>
      {error && <p className="error-note">{error}</p>}

      {lines.length > 0 && (
        <ol className="shots-log">
          {lines.map((l, i) => (
            <li key={i}>
              <b>{l.stage}</b> {l.text}
              {l.image && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={l.image} alt="" />
              )}
            </li>
          ))}
        </ol>
      )}

      {out && (
        <div className="shots-out">
          {out.stills.map((u) => (
            // eslint-disable-next-line @next/next/no-img-element
            <a key={u} href={u} target="_blank" rel="noreferrer"><img src={u} alt="Still" /></a>
          ))}
          {out.videos.map((u) => (
            <video key={u} src={u} controls playsInline muted loop />
          ))}
          <p className="fine">
            {out.minutes.toFixed(0)} min{out.agent_cost_usd != null ? `, agent $${out.agent_cost_usd.toFixed(2)}` : ""}
            {out.missing.length ? `. Missing: ${out.missing.join("; ")}` : ""}
          </p>
        </div>
      )}
    </section>
  );
}
