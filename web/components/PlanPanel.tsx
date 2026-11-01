"use client";

import { useState } from "react";
import type { RunState } from "@/lib/run";
import type { BuildResponse, PlanResponse } from "@/lib/types";
import Stamp from "./Stamp";

interface Props {
  planRes: PlanResponse | null;
  planRun: RunState;
  buildRun: RunState;
  buildRes: BuildResponse | null;
  onEdit: (text: string) => void;
  onBuild: () => void;
  tier: "draft" | "full";
  busy: boolean;
}

/** The plan as a breakdown sheet, with the notes box and the one ink button. */
export default function PlanPanel({ planRes, planRun, buildRun, buildRes, onEdit, onBuild, tier, busy }: Props) {
  const [edit, setEdit] = useState("");
  const [notesOpen, setNotesOpen] = useState(false);
  const plan = planRes?.plan;

  if (!plan) {
    return (
      <div className="plan-panel">
        <h3 className="sheet-h">Breakdown</h3>
        <p className="typed muted">
          {planRun.status === "running"
            ? "The planner is reading the plate and laying out the whole space, including what the camera can't see."
            : "Room size, objects and lights are typed up here once a plan comes back. Revise it in words, then approve it to build."}
        </p>
        {planRun.status === "running" && (
          <div className="typing" aria-hidden>
            <span />
            <span />
            <span />
          </div>
        )}
      </div>
    );
  }

  const objects = plan.objects.length;
  const invented = plan.objects.filter((o) => o.source === "invented").length;
  const generated = plan.objects.filter((o) => o.generate).length;
  const inventedLights = plan.lights.filter((l) => l.source === "invented").length;
  const r = plan.room;
  const building = buildRun.kind !== null;

  return (
    <div className="plan-panel">
      <h3 className="sheet-h">Breakdown</h3>
      <div className="plan-head">
        <h2 className="plan-title">{plan.name.replace(/-/g, " ")}</h2>
        {building && (
          <span className="approved">
            <Stamp tilt={-9}>APPROVED</Stamp>
          </span>
        )}
      </div>
      <p className="typed plan-summary">{plan.summary}</p>

      <table className="breakdown">
        <tbody>
          <tr>
            <th scope="row">Room</th>
            <td>
              {fmtM(r.width)} x {fmtM(r.depth)} m, {fmtM(r.height)} m high
            </td>
          </tr>
          <tr>
            <th scope="row">Setting</th>
            <td>
              {plan.setting.replace(/_/g, " ")}
              {plan.time_of_day ? `, ${plan.time_of_day}` : ""}
            </td>
          </tr>
          <tr>
            <th scope="row">Objects</th>
            <td>
              <b>{objects}</b> ({invented} invented)
            </td>
          </tr>
          <tr>
            <th scope="row">To build</th>
            <td>{generated} generated props</td>
          </tr>
          <tr>
            <th scope="row">Lights</th>
            <td>
              <b>{plan.lights.length}</b>
              {inventedLights ? ` (${inventedLights} invented)` : ""}
              <span className="light-dots">
                {plan.lights.slice(0, 20).map((l) => (
                  <span key={l.id} style={{ background: l.color }} title={`${l.id}: ${l.kind}, ${l.power}`} />
                ))}
              </span>
            </td>
          </tr>
          {plan.mood && plan.mood.length > 0 && (
            <tr>
              <th scope="row">Mood</th>
              <td>{plan.mood.join(", ")}</td>
            </tr>
          )}
          {plan.palette && plan.palette.length > 0 && (
            <tr>
              <th scope="row">Palette</th>
              <td>
                <span className="palette" aria-label="Palette">
                  {plan.palette.map((c) => (
                    <span key={c} style={{ background: c }} title={c} />
                  ))}
                </span>
              </td>
            </tr>
          )}
          {plan.dials &&
            Object.entries(plan.dials).map(([k, d]) => (
              <tr key={k}>
                <th scope="row">{k.replace(/_/g, " ")}</th>
                <td>
                  <b>{String(d.value)}</b> {d.means}
                </td>
              </tr>
            ))}
        </tbody>
      </table>

      {plan.notes && plan.notes.length > 0 && (
        <div className="notes">
          <button className="text-btn" onClick={() => setNotesOpen((o) => !o)} aria-expanded={notesOpen}>
            {notesOpen ? "Hide planner notes" : `Planner notes (${plan.notes.length})`}
          </button>
          {notesOpen && (
            <ol>
              {plan.notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ol>
          )}
        </div>
      )}

      <div className="plan-actions">
        {!building && (
          <>
            <label className="field">
              <span className="field-label">Notes for a revision</span>
              <textarea
                className="notes-box"
                rows={3}
                value={edit}
                disabled={busy}
                placeholder="Move the wall display to the right wall. Add a second row of consoles."
                onChange={(e) => setEdit(e.target.value)}
              />
            </label>
            <button
              className="secondary"
              disabled={busy || !edit.trim()}
              onClick={() => {
                onEdit(edit.trim());
                setEdit("");
              }}
            >
              Revise plan
            </button>
          </>
        )}
        {buildRes?.package_url ? (
          <a className="primary as-link" href={buildRes.package_url} download>
            Download scene package
          </a>
        ) : buildRun.status === "failed" ? (
          <button className="primary" disabled={busy} onClick={onBuild}>
            Retry build
          </button>
        ) : (
          <button className="primary" disabled={busy || building} onClick={onBuild}>
            {buildRun.status === "running" ? "Building" : `Approve and build (${tier})`}
          </button>
        )}
        <p className="fine plan-id">plan {planRes.plan_id}</p>
      </div>
    </div>
  );
}

const fmtM = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));
