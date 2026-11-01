"use client";

import { useState } from "react";
import { fmtTime, type RunState } from "@/lib/run";
import { STAGE_LABELS, type BuildResponse } from "@/lib/types";

const TIMING_LABELS: Record<string, string> = {
  meshes_s: "Meshes, to deadline",
  assemble_s: "Assembly",
  render_s: "Final stills",
  package_s: "Package upload",
  total_s: "Total",
};

/** End state: stills, timings, package. */
export default function Result({ res, run, planRun }: { res: BuildResponse; run: RunState; planRun: RunState }) {
  const [i, setI] = useState(0);
  const still = res.stills[i];
  const stageRows = run.order
    .filter((s) => s !== "done" && run.stages[s].start !== undefined)
    .map((s) => ({ s, d: (run.stages[s].end ?? run.lastAt) - (run.stages[s].start ?? 0) }));
  const planTotal = planRun.stages.done?.end ?? planRun.lastAt;
  const meshed = Object.values(run.props).filter((p) => p.mesh_url).length;
  const total = run.totalProps ?? run.propOrder.length;

  return (
    <div className="result">
      <div className="result-main">
        {still ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img className="result-still" src={still} alt={`Still ${i + 1}`} />
        ) : (
          <div className="empty">
            <p>No stills were returned.</p>
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
          <span className="serif">{res.scene_id}</span>
          <span className="muted">
            {meshed} of {total} props meshed{res.standins_left.length ? `, ${res.standins_left.length} stand-ins` : ""}
          </span>
        </div>
        {res.package_url ? (
          <a className="primary as-link" href={res.package_url} download>
            Download scene package
          </a>
        ) : (
          <span className="muted">No package URL in this run.</span>
        )}
        {res.scene_blend_url && (
          <a className="secondary as-link" href={res.scene_blend_url} download>
            scene.blend only
          </a>
        )}
        <table className="timings">
          <caption>Timings</caption>
          <tbody>
            {planTotal > 0 && (
              <tr>
                <th>Plan</th>
                <td>{fmtTime(planTotal)}</td>
              </tr>
            )}
            {stageRows.map((r) => (
              <tr key={r.s}>
                <th>{STAGE_LABELS[r.s] ?? r.s}</th>
                <td>{fmtTime(r.d)}</td>
              </tr>
            ))}
            {Object.entries(res.timings).map(([k, v]) => (
              <tr key={k} className={k === "total_s" ? "total" : "server"}>
                <th>{TIMING_LABELS[k] ?? k.replace(/_s$/, "").replace(/_/g, " ")}</th>
                <td>{fmtTime(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {res.standins_left.length > 0 && (
          <p className="fine">Still stand-in boxes: {res.standins_left.join(", ").replace(/_/g, " ")}</p>
        )}
      </div>
    </div>
  );
}
