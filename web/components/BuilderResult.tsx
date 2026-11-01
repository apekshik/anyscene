"use client";

import { useState } from "react";
import { clock, type BuilderResponse, type BuilderState } from "@/lib/builder";

/** Dailies: the stills, the package, and what the build cost. */
export default function BuilderResult({ res, run, onOpen }: { res: BuilderResponse; run: BuilderState; onOpen?: (i: number) => void }) {
  const [i, setI] = useState(0);
  const still = res.stills[i];
  const last = res.critiques[res.critiques.length - 1] ?? run.critiques[run.critiques.length - 1];
  const tools = run.lines.filter((l) => l.kind === "tool").length;
  return (
    <div className="result">
      <div className="result-main">
        {still ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img className="result-still" src={still} alt={`Still ${i + 1}`} onClick={() => onOpen?.(i)} style={{ cursor: onOpen ? "zoom-in" : undefined }} />
        ) : (
          <div className="empty">
            <p>No stills came back.</p>
          </div>
        )}
        {res.stills.length > 1 && (
          <div className="result-thumbs">
            {res.stills.map((s, k) => (
              <button key={s} className={k === i ? "on" : ""} onClick={() => setI(k)} aria-label={`Still ${k + 1}`}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={s} alt="" />
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="result-side">
        <div className="result-head">
          <span className="serif">{res.build_id || run.buildId}</span>
          <span className="muted">
            {res.stills.length} stills, {res.panorama_urls?.length ?? 0} panoramas{res.scene_glb_url ? ", scene glTF" : ""}
          </span>
        </div>
        {res.package_url ? (
          <a className="primary as-link" href={res.package_url} download>
            Download scene package
          </a>
        ) : (
          <span className="muted">No package in this build.</span>
        )}
        {res.scene_blend_url && (
          <a className="secondary as-link" href={res.scene_blend_url} download>
            scene.blend only
          </a>
        )}
        {res.scene_glb_url && (
          <a className="secondary as-link" href={res.scene_glb_url} download>
            scene.glb
          </a>
        )}
        <table className="timings">
          <caption>Wrap report</caption>
          <tbody>
            <tr>
              <th>Agent cost</th>
              <td>{res.agent_cost_usd != null ? `$${res.agent_cost_usd.toFixed(2)}` : "n/a"}</td>
            </tr>
            <tr>
              <th>Minutes</th>
              <td>{res.minutes != null ? res.minutes.toFixed(1) : clock(run.lastT)}</td>
            </tr>
            <tr>
              <th>Critic rounds</th>
              <td>{res.critiques.length || run.critiques.length}</td>
            </tr>
            <tr>
              <th>Last verdict</th>
              <td className={last?.passed ? "" : "bad"}>{last ? (last.passed ? "PASS" : "NOT YET") : "none"}</td>
            </tr>
            <tr className="server">
              <th>Tool calls</th>
              <td>{tools}</td>
            </tr>
            <tr className="server">
              <th>Frames reported</th>
              <td>{run.previews.length}</td>
            </tr>
          </tbody>
        </table>
        {res.missing?.length > 0 && (
          <div className="missing">
            <b>Missing</b>
            <ul>
              {res.missing.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          </div>
        )}
        {res.dials && Object.keys(res.dials).length > 0 && (
          <table className="kv dials-built">
            <caption>Dials as built</caption>
            <tbody>
              {Object.entries(res.dials).map(([k, v]) => {
                // the agent decides the shape: a bare value, or {value, ...what it controls}
                const o = v && typeof v === "object" ? (v as Record<string, unknown>) : { value: v };
                const rest = Object.entries(o).filter(([kk]) => kk !== "value");
                return (
                  <tr key={k}>
                    <th>{k.replace(/_/g, " ")}</th>
                    <td>
                      <b>{String(o.value ?? "")}</b>
                      {rest.map(([kk, vv]) => (
                        <span className="dial-note" key={kk}>
                          {typeof vv === "string" ? vv : JSON.stringify(vv)}
                        </span>
                      ))}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
