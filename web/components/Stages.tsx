"use client";

import { fmtTime, type RunState } from "@/lib/run";
import { STAGE_LABELS } from "@/lib/types";
import Stamp from "./Stamp";

interface Props {
  run: RunState;
  now: number;
  kind: "plan" | "build";
  previous: { label: string; time?: number } | null;
}

/** The stages as a call-sheet schedule: #, department, status. */
export default function Stages({ run, now, kind, previous }: Props) {
  const rows = run.order.filter((s) => s !== "done");
  return (
    <section className="schedule" aria-label="Schedule">
      <h3 className="sheet-h">
        Schedule <span className="sheet-h-sub">{kind === "build" ? "build" : "plan"}</span>
      </h3>
      <table className="sched">
        <thead>
          <tr>
            <th scope="col">#</th>
            <th scope="col">Dept</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {previous && (
            <tr className="prev">
              <td>0</td>
              <td>{previous.label}</td>
              <td className="wrapped">WRAPPED {fmtTime(previous.time)}</td>
            </tr>
          )}
          {rows.map((s, i) => {
            const st = run.stages[s];
            const status = run.status === "idle" ? "pending" : st.status;
            const dur = st.start === undefined ? undefined : (st.end ?? now) - st.start;
            const counts = s === "generating_meshes" || s === "prop_references";
            const pct = st.progress !== undefined ? st.progress : undefined;
            return (
              <tr key={s} className={status}>
                <td>{i + 1}</td>
                <td>
                  <div className="dept">{STAGE_LABELS[s] ?? s}</div>
                  {status === "running" && st.message && <div className="dept-msg">{st.message}</div>}
                  {status === "running" && pct !== undefined && (
                    <div className="tick" aria-hidden>
                      <span style={{ width: `${Math.max(2, pct * 100)}%` }} />
                    </div>
                  )}
                </td>
                <td className="st">
                  {status === "done" && (
                    <span className="wrapped">
                      WRAPPED {fmtTime(dur)}
                      {counts && run.totalProps ? <span className="st-sub">{Math.round((pct ?? 1) * run.totalProps)} / {run.totalProps}</span> : null}
                    </span>
                  )}
                  {status === "running" && (
                    <>
                      <Stamp tilt={-5}>ROLLING</Stamp>
                      <span className="st-sub">
                        {fmtTime(dur)}
                        {counts && run.totalProps && pct !== undefined ? `  ${Math.round(pct * run.totalProps)} / ${run.totalProps}` : ""}
                      </span>
                    </>
                  )}
                  {status === "failed" && <Stamp tilt={3}>HOLD</Stamp>}
                  {status === "pending" && <span className="standby">STANDBY</span>}
                  {status === "skipped" && <span className="standby">N/A</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {run.status === "failed" && run.error && <p className="error-note">{run.error}</p>}
    </section>
  );
}
