"use client";

import { useState } from "react";
import { PASS_MARK, SCORE_KEYS, SCORE_LABELS, type BuilderState } from "@/lib/builder";
import Stamp from "./Stamp";
import InfoTip, { HELP } from "./InfoTip";

/** The critic's rounds as a score sheet (categories down, rounds across), the latest verdict and its ranked fixes. */
export default function CriticPanel({ run }: { run: BuilderState }) {
  const [openRound, setOpenRound] = useState<number | null>(null);
  const rounds = run.critiques;
  const shownRounds = rounds.slice(-6);
  const last = rounds[rounds.length - 1];

  return (
    <div className="plan-panel critic">
      <h3 className="sheet-h">
        Critic&apos;s report <span className="sheet-h-sub">pass = none under 6, avg {PASS_MARK}+</span>{" "}
        <InfoTip label="the critic" text={HELP.critic} />
      </h3>

      {!rounds.length && (
        <p className="typed muted">
          {run.criticBusy
            ? "The critic is comparing the reference with the first stills."
            : run.status === "idle"
              ? "An independent critic judges each round of stills on eight lines: is this a good production base in the reference's world? The builder keeps going until it passes (none under 6, average 7+), for at most 8 rounds."
              : "No round yet. The builder calls the critic once it has finals to show."}
        </p>
      )}
      {run.criticBusy && (
        <div className="typing" aria-label="Critic reviewing">
          <span />
          <span />
        </div>
      )}

      {rounds.length > 0 && (
        <>
          <table className="scores">
            <thead>
              <tr>
                <th scope="col" />
                {shownRounds.map((c) => (
                  <th key={c.round} scope="col" className={c === last ? "cur" : ""}>
                    R{c.round}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {SCORE_KEYS.map((k) => (
                <tr key={k}>
                  <th scope="row">{SCORE_LABELS[k]}</th>
                  {shownRounds.map((c, i) => {
                    const v = c.scores?.[k];
                    const prev = i > 0 ? shownRounds[i - 1].scores?.[k] : undefined;
                    const d = v !== undefined && prev !== undefined ? v - prev : 0;
                    return (
                      <td key={c.round} className={`${v !== undefined && v < 6 ? "low" : ""} ${c === last ? "cur" : ""}`}>
                        {v ?? "-"}
                        {d !== 0 && <sup className={d > 0 ? "up" : "down"}>{d > 0 ? `+${d}` : d}</sup>}
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr className="total">
                <th scope="row">Total</th>
                {shownRounds.map((c) => (
                  <td key={c.round} className={c === last ? "cur" : ""}>
                    {Object.values(c.scores || {}).reduce((a, b) => a + b, 0)}
                  </td>
                ))}
              </tr>
              <tr className="verdicts">
                <th scope="row">Verdict</th>
                {shownRounds.map((c) => (
                  <td key={c.round} className={c.passed ? "pass" : "fail"}>
                    {c.passed ? "PASS" : "NOT YET"}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>

          <div className="verdict-head">
            <span className="verdict-round">Round {last.round}</span>
            <span key={last.round}>
              {last.passed ? <Stamp tilt={-7}>PASSED</Stamp> : <Stamp tilt={-4}>NOT YET</Stamp>}
            </span>
          </div>
          {last.summary && <p className="typed plan-summary">{last.summary}</p>}

          {last.fixes?.length > 0 && (
            <>
              <h3 className="sheet-h">{last.passed ? "Notes" : "Fixes, worst first"}</h3>
              <ol className="fixes">
                {last.fixes.map((f, i) => (
                  <li key={i}>{f}</li>
                ))}
              </ol>
            </>
          )}

          {rounds.length > 1 && (
            <div className="notes">
              {rounds
                .slice(0, -1)
                .reverse()
                .map((c) => (
                  <div key={c.round} className="old-round">
                    <button className="text-btn" onClick={() => setOpenRound(openRound === c.round ? null : c.round)} aria-expanded={openRound === c.round}>
                      Round {c.round} fixes ({c.fixes?.length ?? 0})
                    </button>
                    {openRound === c.round && (
                      <ol className="fixes old">
                        {c.fixes.map((f, i) => (
                          <li key={i}>{f}</li>
                        ))}
                      </ol>
                    )}
                  </div>
                ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
