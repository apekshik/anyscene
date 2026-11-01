"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { initialRun, runReducer, type RunState } from "@/lib/run";
import { APP_ID, LiveSource, ReplaySource, type Source } from "@/lib/sources";
import type { BuildResponse, PlanResponse, StageEvent } from "@/lib/types";
import Inputs, { type InputsState } from "./Inputs";
import Stages from "./Stages";
import Viewport, { type TabId } from "./Viewport";
import PropShelf from "./PropShelf";
import PlanPanel from "./PlanPanel";
import Stamp from "./Stamp";

export default function Studio() {
  const params = useSearchParams();
  const replayName = params.get("replay");
  const auto = params.get("auto") === "1";
  const initialSpeed = Math.max(0.25, Math.min(64, Number(params.get("speed")) || 1));

  const [source, setSource] = useState<Source | null>(null);
  const [sourceError, setSourceError] = useState<string>("");
  const [speed, setSpeed] = useState(initialSpeed);

  const [inputs, setInputs] = useState<InputsState>({
    file: null,
    previewUrl: "",
    prompt: "",
    dials: {},
    effort: "medium",
    tier: "draft",
  });

  const [planRun, dispatchPlan] = useReducer(runReducer, undefined, () => initialRun(null));
  const [buildRun, dispatchBuild] = useReducer(runReducer, undefined, () => initialRun(null));
  const [planRes, setPlanRes] = useState<PlanResponse | null>(null);
  const [buildRes, setBuildRes] = useState<BuildResponse | null>(null);
  const [planEnd, setPlanEnd] = useState<number | null>(null);
  const [buildEnd, setBuildEnd] = useState<number | null>(null);
  const [tab, setTab] = useState<TabId>("floor");
  const [take, setTake] = useState(0);
  const [follow, setFollow] = useState(true);
  const followRef = useRef(true);
  followRef.current = follow;
  const [selected, setSelected] = useState<string | null>(null);
  const [rightOpen, setRightOpen] = useState(true);
  const [, setTick] = useState(0);
  const refUrlRef = useRef<string>("");

  // ---- source: live through the proxy, or a recorded run
  useEffect(() => {
    let cancelled = false;
    if (replayName) {
      ReplaySource.load(replayName, initialSpeed)
        .then((s) => {
          if (cancelled) return;
          setSource(s);
          setInputs((i) => ({ ...i, previewUrl: s.referenceUrl, prompt: "" }));
          refUrlRef.current = s.referenceUrl;
        })
        .catch((e) => setSourceError(String(e.message || e)));
    } else {
      setSource(new LiveSource());
    }
    return () => {
      cancelled = true;
    };
  }, [replayName, initialSpeed]);

  useEffect(() => {
    if (source instanceof ReplaySource) source.speed = speed;
  }, [source, speed]);

  const activeKind: "plan" | "build" = buildRun.kind ? "build" : "plan";
  const run: RunState = activeKind === "build" ? buildRun : planRun;
  const running = planRun.status === "running" || buildRun.status === "running";

  // timer tick while anything runs
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setTick((n) => n + 1), 250);
    return () => clearInterval(id);
  }, [running]);

  const clock = source ? source.clock() : 0;
  const now = activeKind === "build" ? (buildEnd ?? clock) : (planEnd ?? (planRun.status === "idle" ? 0 : clock));

  const choose = useCallback((t: TabId, user = true) => {
    setTab(t);
    if (user) setFollow(false);
  }, []);

  // ---- follow mode: move the viewport to whatever just arrived
  const lastPreview = run.previews[run.previews.length - 1];
  useEffect(() => {
    if (!follow || !lastPreview) return;
    if (activeKind === "plan") {
      if (lastPreview.stage === "drawing_floor_plan") setTab("floor");
      else if (lastPreview.stage === "blockout") setTab("greybox");
    } else setTab("live");
  }, [follow, lastPreview, activeKind]);

  // ---- requests
  const doPlan = useCallback(
    async (edit?: string) => {
      if (!source) return;
      setFollow(true);
      setPlanEnd(null);
      dispatchPlan({ type: "start", kind: "plan" });
      if (!edit) {
        dispatchBuild({ type: "reset" });
        setBuildRes(null);
        setBuildEnd(null);
        setPlanRes(null);
        setSelected(null);
        setTab("floor");
      }
      const sink = { onEvent: (ev: StageEvent, t: number) => dispatchPlan({ type: "event", ev, t }) };
      try {
        let res: PlanResponse;
        if (edit && planRes) {
          res = await source.plan({ plan_id: planRes.plan_id, edit, effort: inputs.effort }, sink);
        } else {
          let url = refUrlRef.current;
          if (inputs.file && source.mode === "live") {
            url = await source.uploadReference(inputs.file);
            refUrlRef.current = url;
          }
          if (!url) throw new Error("Add a reference image first.");
          const dials = Object.fromEntries(Object.entries(inputs.dials).filter(([, v]) => v !== undefined && v !== null)) as Record<string, number | string>;
          res = await source.plan(
            { reference_image_urls: [url], prompt: inputs.prompt, effort: inputs.effort, ...(Object.keys(dials).length ? { dials } : {}) },
            sink,
          );
        }
        setPlanRes(res);
        dispatchPlan({ type: "finish", t: source.clock() });
        setPlanEnd(source.clock());
        if (followRef.current) setTab("greybox");
      } catch (e) {
        const msg = errorMessage(e);
        dispatchPlan({ type: "fail", message: msg, t: source.clock() });
        setPlanEnd(source.clock());
      }
    },
    [source, inputs, planRes],
  );

  const doBuild = useCallback(async () => {
    if (!source || !planRes) return;
    setFollow(true);
    setBuildEnd(null);
    setBuildRes(null);
    setTab("floor");
    setTake((n) => n + 1);
    dispatchBuild({ type: "start", kind: "build" });
    const sink = { onEvent: (ev: StageEvent, t: number) => dispatchBuild({ type: "event", ev, t }) };
    try {
      const res = await source.build({ plan_id: planRes.plan_id, tier: inputs.tier }, sink);
      setBuildRes(res);
      dispatchBuild({ type: "finish", t: source.clock() });
      setBuildEnd(source.clock());
      if (followRef.current) setTab("result");
    } catch (e) {
      dispatchBuild({ type: "fail", message: errorMessage(e), t: source.clock() });
      setBuildEnd(source.clock());
    }
  }, [source, planRes, inputs.tier]);

  // ---- auto mode for screen recordings: plan, pause on the result, build
  const autoState = useRef(0);
  useEffect(() => {
    if (!auto || !source) return;
    if (autoState.current === 0) {
      autoState.current = 1;
      setTimeout(() => doPlan(), 1200);
    } else if (autoState.current === 1 && planRes && planRun.status === "done") {
      autoState.current = 2;
      setTimeout(() => doBuild(), 3500);
    }
  }, [auto, source, planRes, planRun.status, doPlan, doBuild]);

  const selectProp = useCallback(
    (id: string) => {
      setSelected(id);
      choose("3d");
    },
    [choose],
  );

  const replay = source instanceof ReplaySource ? source : null;
  const stagesMeta = useMemo(
    () =>
      activeKind === "build" && planRun.status === "done"
        ? { label: "Plan approved", time: planEnd ?? undefined }
        : null,
    [activeKind, planRun.status, planEnd],
  );

  return (
    <div className={`studio ${rightOpen ? "" : "right-closed"}`}>
      <header className="topbar">
        <div className="slate" role="group" aria-label="Slate">
          <div className="slate-cell">
            <small>Production</small>
            <b>AnyScene</b>
          </div>
          <div className="slate-cell">
            <small>Scene</small>
            <b>{sceneCode(planRes?.plan?.name, planRes?.plan?.objects.length)}</b>
          </div>
          <div className="slate-cell">
            <small>Take</small>
            <b>{String(take).padStart(2, "0")}</b>
          </div>
          <div className="slate-cell">
            <small>Roll</small>
            <b>{inputs.tier === "full" ? "FULL" : "DRAFT"}</b>
          </div>
          <div className="slate-cell">
            <small>Clock</small>
            <b className="clock">{clockText(now)}</b>
          </div>
          <div className="slate-stripe" aria-hidden />
          {buildRun.status === "done" && (
            <span className="slate-wrap">
              <Stamp big tilt={-6}>WRAPPED</Stamp>
            </span>
          )}
        </div>
        <div className="toolbar">
          {replay ? (
            <div className="replay-ctl" title="Replaying a recorded run">
              <span>Replay: {replay.manifest.name}</span>
              <div className="speeds" role="group" aria-label="Replay speed">
                {[1, 2, 4, 8, 16].map((s) => (
                  <button key={s} className={speed === s ? "on" : ""} onClick={() => setSpeed(s)} aria-pressed={speed === s}>
                    {s}x
                  </button>
                ))}
              </div>
            </div>
          ) : (
            source && <span className="live-pill">Live: {APP_ID || "no app set (NEXT_PUBLIC_ANYSCENE_APP)"}</span>
          )}
          <span className="mode-switch">
            <a href="/" className="text-btn">
              builder
            </a>{" "}
            <span aria-hidden>/</span> Plan + build pipeline
          </span>
          {planRes?.plan?.name && <span className="scene-name">{planRes.plan.name.replace(/-/g, " ")}</span>}
          <button className="text-btn" onClick={() => setRightOpen((o) => !o)} aria-expanded={rightOpen}>
            {rightOpen ? "Hide breakdown" : "Show breakdown"}
          </button>
        </div>
      </header>

      <aside className="left">
        <Inputs
          value={inputs}
          onChange={(v) => {
            setInputs(v);
            if (v.file !== inputs.file) refUrlRef.current = v.file ? "" : refUrlRef.current;
          }}
          disabled={running}
          onPlan={() => doPlan()}
          canPlan={!!(inputs.file || refUrlRef.current) && !running}
          planning={planRun.status === "running"}
        />
        <Stages run={run} now={now} kind={activeKind} previous={stagesMeta} />
        {sourceError && <p className="error-note">{sourceError}</p>}
      </aside>

      <main className="center">
        <Viewport
          tab={tab}
          onTab={(t) => choose(t)}
          follow={follow}
          onFollow={() => setFollow(true)}
          planRun={planRun}
          buildRun={buildRun}
          planRes={planRes}
          buildRes={buildRes}
          referenceUrl={inputs.previewUrl}
          selected={selected}
          onSelect={selectProp}
          now={now}
          activeKind={activeKind}
        />
      </main>

      <section className="shelf-wrap">
        <PropShelf run={buildRun} plan={planRes?.plan ?? null} selected={selected} onSelect={selectProp} />
      </section>

      <aside className="right" aria-hidden={!rightOpen}>
        <PlanPanel
          planRes={planRes}
          planRun={planRun}
          buildRun={buildRun}
          buildRes={buildRes}
          onEdit={(t) => doPlan(t)}
          onBuild={doBuild}
          tier={inputs.tier}
          busy={running}
        />
      </aside>
    </div>
  );
}

/** A short slate code from the plan name and object count: apollo-era-mission-control-night, 70 -> AEM-70. */
function sceneCode(name?: string, n?: number) {
  if (!name) return "--";
  const words = name.split(/[-_\s]+/).filter((w) => w && !/^(the|a|an|of|and|at|in)$/i.test(w));
  return `${words.slice(0, 3).map((w) => w[0].toUpperCase()).join("")}${n ? "-" + n : ""}`;
}

function clockText(s: number) {
  s = Math.max(0, Math.floor(s));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function errorMessage(e: unknown): string {
  if (!e) return "Request failed";
  const anyE = e as { body?: { detail?: unknown }; message?: string };
  const d = anyE.body?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d[0]?.msg) return String(d[0].msg);
  return anyE.message || String(e);
}
