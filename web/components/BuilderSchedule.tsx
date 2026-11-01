"use client";

import { clock, MILESTONE_LABELS, type BuilderState } from "@/lib/builder";
import Stamp from "./Stamp";
import InfoTip, { HELP } from "./InfoTip";

/** Milestones as a call-sheet schedule. The agent picks its milestones; the usual ones are listed up front so the
 *  shape of the day is visible, and any it adds are appended. */
export default function BuilderSchedule({ run, now }: { run: BuilderState; now: number }) {
  const idle = run.status === "idle";
  const ended = run.status === "done" || run.status === "failed" || run.doneAt !== undefined;
  const last = run.critiques[run.critiques.length - 1];
  let n = 0;
  return (
    <section className="schedule" aria-label="Schedule">
      <h3 className="sheet-h">
        Schedule <span className="sheet-h-sub">builder</span> <InfoTip label="the schedule" text={HELP.schedule} />
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
          <tr className={run.received !== undefined ? "done" : "pending"}>
            <td>{n++}</td>
            <td>Call received</td>
            <td className="st">{run.received !== undefined ? <span className="wrapped">WRAPPED {clock(run.received)}</span> : <span className="standby">STANDBY</span>}</td>
          </tr>
          {run.order.map((stage) => {
            const m = run.milestones[stage];
            const isCur = run.current === stage && !ended;
            const status = idle ? "pending" : !m ? (ended ? "skipped" : "pending") : isCur ? "running" : "done";
            return (
              <tr key={stage} className={status}>
                <td>{n++}</td>
                <td>
                  <div className="dept">
                    {MILESTONE_LABELS[stage] ?? stage.replace(/_/g, " ")}
                    {m && m.takes > 1 ? <span className="take"> take {m.takes}</span> : null}
                  </div>
                  {isCur && m.message && <div className="dept-msg">{m.message}</div>}
                </td>
                <td className="st">
                  {status === "running" && (
                    <>
                      <Stamp tilt={-5}>ROLLING</Stamp>
                      <span className="st-sub">{clock(now - m.start)}</span>
                    </>
                  )}
                  {status === "done" && <span className="wrapped">WRAPPED {clock((m.end ?? now) - m.start)}</span>}
                  {status === "pending" && <span className="standby">STANDBY</span>}
                  {status === "skipped" && <span className="standby">N/A</span>}
                </td>
              </tr>
            );
          })}
          <tr className={run.criticBusy ? "running" : last ? "done" : "pending"}>
            <td>{n++}</td>
            <td>
              <div className="dept">Critic review</div>
              {last && <div className="dept-msg">round {last.round}</div>}
            </td>
            <td className="st">
              {run.criticBusy ? (
                <Stamp tilt={-5}>IN REVIEW</Stamp>
              ) : last ? (
                last.passed ? (
                  <span className="wrapped">PASSED</span>
                ) : (
                  <span className="wrapped notyet">NOT YET</span>
                )
              ) : (
                <span className="standby">STANDBY</span>
              )}
            </td>
          </tr>
          <tr className={run.packagedAt !== undefined ? "done" : run.doneAt !== undefined ? "running" : "pending"}>
            <td>{n++}</td>
            <td>Package</td>
            <td className="st">
              {run.packagedAt !== undefined ? (
                <span className="wrapped">WRAPPED {clock(run.packagedAt - (run.doneAt ?? run.packagedAt))}</span>
              ) : run.doneAt !== undefined && run.status === "running" ? (
                <Stamp tilt={-5}>ROLLING</Stamp>
              ) : (
                <span className="standby">STANDBY</span>
              )}
            </td>
          </tr>
        </tbody>
      </table>
      {run.status === "failed" && run.error && <p className="error-note">{run.error}</p>}
    </section>
  );
}
