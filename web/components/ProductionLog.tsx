"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { clock, MILESTONE_LABELS, type BuilderState, type LogLine } from "@/lib/builder";
import InfoTip, { HELP } from "./InfoTip";

type Filter = "all" | "notes" | "tools" | "milestones";
const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "notes", label: "Notes" },
  { id: "tools", label: "Tools" },
  { id: "milestones", label: "Milestones" },
];
const MAX_LINES = 500;

const keep = (f: Filter, l: LogLine) =>
  f === "all" ||
  (f === "notes" && l.kind === "note") ||
  (f === "tools" && l.kind === "tool") ||
  (f === "milestones" && (l.kind === "milestone" || l.kind === "critic" || l.kind === "system"));

/** The agent's work as a typed production log: every tool call, every note, milestones and critic rounds. */
export default function ProductionLog({ run }: { run: BuilderState }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [all, setAll] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const lines = run.lines.filter((l) => keep(filter, l));
  const hidden = all ? 0 : Math.max(0, lines.length - MAX_LINES);
  const shown = hidden ? lines.slice(-MAX_LINES) : lines;
  const tools = run.lines.filter((l) => l.kind === "tool").length;
  const notes = run.lines.filter((l) => l.kind === "note").length;

  // stay pinned to the newest line unless the reader has scrolled up
  useLayoutEffect(() => {
    const el = box.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [shown.length, filter]);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const onScroll = () => (stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40);
    el.addEventListener("scroll", onScroll);
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className="prodlog">
      <div className="shelf-head">
        <h3 className="sheet-h shelf-title">Production log <InfoTip label="the production log" text={HELP.log} /></h3>
        <span className="shelf-count">
          {run.status === "idle" ? (
            <span className="muted">Every tool call and note from the builder is typed up here.</span>
          ) : (
            <>
              <b>{tools}</b> tool calls, <b>{notes}</b> notes, <b>{run.critiques.length}</b> critic rounds
            </>
          )}
        </span>
        <span className="vp-spacer" />
        <div className="seg small" role="group" aria-label="Log filter">
          {FILTERS.map((f) => (
            <button key={f.id} className={filter === f.id ? "on" : ""} onClick={() => setFilter(f.id)} aria-pressed={filter === f.id}>
              {f.label}
            </button>
          ))}
        </div>
      </div>
      <div className="log-lines" ref={box} role="log" aria-live="off">
        {hidden > 0 && (
          <button className="text-btn earlier" onClick={() => setAll(true)}>
            {hidden} earlier lines
          </button>
        )}
        {shown.map((l) => (
          <div key={l.id} className={`ll ${l.kind}`}>
            <span className="ll-t">{clock(l.t)}</span>
            <span className="ll-k">{label(l)}</span>
            <span className="ll-x">
              {l.text}
              {l.image && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={l.image} alt="" loading="lazy" />
              )}
            </span>
          </div>
        ))}
        {run.status === "running" && (
          <div className="ll cursor" aria-hidden>
            <span className="ll-t" />
            <span className="ll-k" />
            <span className="ll-x">
              <i className="caret" />
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

function label(l: LogLine) {
  if (l.kind === "tool") return (l.tool || "tool").replace(/^mcp__\w+__/, "").toUpperCase();
  if (l.kind === "note") return "NOTE";
  if (l.kind === "critic") return "CRITIC";
  if (l.kind === "milestone") return (MILESTONE_LABELS[l.stage] ?? l.stage).toUpperCase();
  return l.stage === "failed" ? "HOLD" : l.stage.toUpperCase();
}
