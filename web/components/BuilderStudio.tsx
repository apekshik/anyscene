"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { builderReducer, clock, initialBuilder, type BuilderResponse } from "@/lib/builder";
import { LiveSource, ReplaySource, getAccessKey, setAccessKey, type Source } from "@/lib/sources";
import { BUILDER_APP } from "@/lib/apps";
import { galleryApp, galleryEvents, toBuilderResponse, type GalleryItem, type GalleryKind } from "@/lib/gallery";
import BuilderInputs, { type BuilderInputsState } from "./BuilderInputs";
import { setDials } from "./Dials";
import BuilderSchedule from "./BuilderSchedule";
import ShotsOrder from "./ShotsOrder";
import ProductSwitch from "./ProductSwitch";
import BuilderViewport, { type BTab } from "./BuilderViewport";
import ProductionLog from "./ProductionLog";
import CriticPanel from "./CriticPanel";
import Stamp from "./Stamp";

const SPEEDS = [1, 4, 16, 32, 64];

/** The agent builder (NEXT_PUBLIC_ANYSCENE_APP): one request builds the whole scene; the agent's log streams in, its
 *  milestones fill the schedule, the critic scores each round. */
export default function BuilderStudio() {
  const params = useSearchParams();
  const replayName = params.get("replay");
  const watchId = params.get("watch");
  // ?open=<build id>: a build from the gallery, read from storage (anyone's build, running or finished)
  const openId = params.get("open");
  const openKind: GalleryKind = params.get("kind") === "kit" ? "kit" : "scene";
  const galleryOverride = params.get("gallery_app");
  const openApp = galleryApp(openKind, galleryOverride);
  const galleryHref = `/?${new URLSearchParams({ view: "gallery", ...(openKind === "kit" ? { kind: "kit" } : {}), ...(galleryOverride ? { gallery_app: galleryOverride } : {}) })}`;
  const [opened, setOpened] = useState<GalleryItem | null>(null);
  const auto = params.get("auto") === "1";
  const initialSpeed = Math.max(0.25, Math.min(256, Number(params.get("speed")) || 1));

  const [source, setSource] = useState<Source | null>(null);
  const [sourceError, setSourceError] = useState("");
  const [speed, setSpeed] = useState(initialSpeed);
  const [inputs, setInputs] = useState<BuilderInputsState>({ file: null, previewUrl: "", prompt: "", effort: "medium", dials: {}, floorPlan: null });
  const [run, dispatch] = useReducer(builderReducer, undefined, () => initialBuilder());
  const [res, setRes] = useState<BuilderResponse | null>(null);
  const [endAt, setEndAt] = useState<number | null>(null);
  const [tab, setTab] = useState<BTab>("live");
  const [follow, setFollow] = useState(true);
  const followRef = useRef(true);
  followRef.current = follow;
  const [rightOpen, setRightOpen] = useState(true);
  const [keyOpen, setKeyOpen] = useState(false);
  const [keyDraft, setKeyDraft] = useState("");
  const [needsKey, setNeedsKey] = useState(false);
  const [, tick] = useState(0);
  const refUrl = useRef("");
  // event times are the builder's own clock (from when the worker started); the slate clock counts from the click
  const offset = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (replayName) {
      ReplaySource.load(replayName, initialSpeed)
        .then((s) => {
          if (cancelled) return;
          setSource(s);
          setInputs((i) => ({ ...i, previewUrl: s.referenceUrl }));
          refUrl.current = s.referenceUrl;
        })
        .catch((e) => setSourceError(String(e.message || e)));
    } else setSource(new LiveSource());
    return () => {
      cancelled = true;
    };
  }, [replayName, initialSpeed]);

  useEffect(() => {
    if (source instanceof ReplaySource) source.speed = speed;
  }, [source, speed]);

  const running = run.status === "running";
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => tick((n) => n + 1), 250);
    return () => clearInterval(id);
  }, [running]);
  const now = endAt ?? (run.status === "idle" || !source ? 0 : source.clock());
  const serverNow = offset.current === null ? run.lastT : Math.max(run.lastT, now - offset.current);

  // follow: the newest image goes to the live view; the result to the stills
  const lastPreview = run.previews[run.previews.length - 1]?.url;
  useEffect(() => {
    if (followRef.current && lastPreview) setTab("live");
  }, [lastPreview]);

  const doBuild = useCallback(async () => {
    if (!source) return;
    setFollow(true);
    setRes(null);
    setEndAt(null);
    setTab("live");
    offset.current = null;
    dispatch({ type: "start" });
    try {
      let url = refUrl.current;
      if (inputs.file && source.mode === "live") {
        url = await source.uploadReference(inputs.file);
        refUrl.current = url;
      }
      if (!url) throw new Error("Add a reference image first.");
      const floorPlanUrl = inputs.floorPlan && source.mode === "live" ? await source.uploadReference(inputs.floorPlan) : undefined;
      const r = await source.builder(
        { reference_image_urls: [url], prompt: inputs.prompt, effort: inputs.effort, scene: "scene", dials: setDials(inputs.dials), floor_plan_url: floorPlanUrl },
        {
          onEvent: (ev) => {
            if (offset.current === null && typeof ev.t === "number") offset.current = source.clock() - ev.t;
            dispatch({ type: "event", ev });
          },
        },
      );
      if ((r as { _partial?: boolean })._partial) {
        dispatch({ type: "ended" });
        setEndAt(source.clock());
        return;
      }
      setRes(r);
      dispatch({ type: "result", res: r });
      setEndAt(source.clock());
      if (followRef.current) setTab("stills");
    } catch (e) {
      const msg = errorMessage(e);
      if (/access key|proxy is closed/i.test(msg)) setNeedsKey(true);
      dispatch({ type: "fail", message: msg });
      setEndAt(source.clock());
    }
  }, [source, inputs]);

  // ?watch=<fal request id>: follow a build started elsewhere. Its "received" event carries the request's inputs
  // (reference, prompt, dials, effort), which fill the form so the page shows what the build was given.
  const watchStarted = useRef(false);
  useEffect(() => {
    if (!watchId || !(source instanceof LiveSource) || watchStarted.current) return;
    watchStarted.current = true;
    setFollow(true);
    offset.current = null;
    dispatch({ type: "start" });
    source
      .watchBuilder(watchId, {
        onEvent: (ev) => {
          if (typeof ev.t === "number") offset.current = source.clock() - ev.t;
          const given = ev as unknown as { reference_urls?: string[]; prompt?: string; dials?: Record<string, number | string>; effort?: string };
          if (given.reference_urls?.length)
            setInputs((i) => ({
              ...i,
              previewUrl: given.reference_urls![0],
              prompt: given.prompt ?? i.prompt,
              effort: given.effort ?? i.effort,
              dials: given.dials ?? i.dials,
            }));
          dispatch({ type: "event", ev });
        },
      })
      .then((r) => {
        setRes(r);
        dispatch({ type: "result", res: r });
        setEndAt(source.clock());
        if (followRef.current) setTab("stills");
      })
      .catch((e) => {
        const msg = errorMessage(e);
        if (/access key|proxy is closed/i.test(msg)) setNeedsKey(true);
        dispatch({ type: "fail", message: msg });
        setEndAt(source.clock());
      });
  }, [watchId, source]);
  // ?open=<id>: replay the build's stored events, then (while it runs) poll for new ones every few seconds
  const openStarted = useRef(false);
  useEffect(() => {
    if (!openId || !(source instanceof LiveSource) || openStarted.current) return;
    openStarted.current = true;
    let stop = false;
    setFollow(true);
    offset.current = null;
    dispatch({ type: "start" });
    (async () => {
      let after = 0;
      let given = false;
      for (;;) {
        let page;
        try {
          page = await galleryEvents(openKind, openApp, openId, after);
        } catch (e) {
          if (stop) return;
          const msg = errorMessage(e);
          if (/access key|proxy is closed/i.test(msg)) setNeedsKey(true);
          dispatch({ type: "fail", message: msg });
          setEndAt(source.clock());
          return;
        }
        if (stop) return;
        const s = page.summary;
        setOpened(s);
        if (!given) {
          given = true;
          setInputs((i) => ({
            ...i,
            previewUrl: s.reference_urls?.[0] || i.previewUrl,
            prompt: s.prompt ?? i.prompt,
            effort: s.effort || i.effort,
            dials: s.dials ?? i.dials,
          }));
        }
        for (const ev of page.events) dispatch({ type: "event", ev });
        const lastT = page.events.length ? page.events[page.events.length - 1].t : undefined;
        if (s.status === "running" && typeof lastT === "number") offset.current = source.clock() - lastT;
        after = page.next;
        if (page.more) continue;
        if (s.status !== "running") {
          offset.current = null;
          const r = toBuilderResponse(openKind, page.response, openId);
          if (r) {
            setRes(r);
            dispatch({ type: "result", res: r });
          }
          if (s.status === "stopped") dispatch({ type: "fail", message: "This build stopped before it delivered (its worker went away). What it made is here." });
          setEndAt(source.clock());
          // a finished build opens on its results; follow off, or the replayed frames would pull the view back to live
          if (followRef.current) {
            setFollow(false);
            setTab(r?.stills.length ? "stills" : r?.previews?.length ? "previews" : "live");
          }
          return;
        }
        await new Promise((r) => setTimeout(r, 4000));
        if (stop) return;
      }
    })();
    return () => {
      stop = true;
      openStarted.current = false;
    };
  }, [openId, openKind, openApp, source]);

  useEffect(() => {
    const ref = params.get("ref");
    if (watchId && ref) setInputs((i) => (i.previewUrl ? i : { ...i, previewUrl: ref }));
  }, [watchId, params]);

  const autoDone = useRef(false);
  useEffect(() => {
    if (auto && source && !autoDone.current) {
      autoDone.current = true;
      setTimeout(() => doBuild(), 1200);
    }
  }, [auto, source, doBuild]);

  const replay = source instanceof ReplaySource ? source : null;
  const round = run.critiques.length;
  const passed = run.critiques[run.critiques.length - 1]?.passed;

  return (
    <div className={`studio builder ${rightOpen ? "" : "right-closed"}`}>
      <header className="topbar">
        <div className="slate" role="group" aria-label="Slate">
          <div className="slate-cell">
            <small>Production</small>
            <ProductSwitch current="anyscene" />
          </div>
          <div className="slate-cell">
            <small>Scene</small>
            <b>{run.buildId ? run.buildId.replace(/^[bk]_/, "").slice(0, 6).toUpperCase() : "--"}</b>
          </div>
          <div className="slate-cell">
            <small>Take</small>
            <b title="critic round">{String(round).padStart(2, "0")}</b>
          </div>
          <div className="slate-cell">
            <small>Roll</small>
            <b>{inputs.effort.toUpperCase()}</b>
          </div>
          <div className="slate-cell">
            <small>Clock</small>
            <b className="clock">{clock(watchId || openId ? serverNow : now)}</b>
          </div>
          <div className="slate-stripe" aria-hidden />
          {run.status === "done" && (
            <span className="slate-wrap">
              <Stamp big tilt={-6}>WRAPPED</Stamp>
            </span>
          )}
          {run.status === "failed" && (
            <span className="slate-wrap">
              <Stamp big tilt={-4}>HOLD</Stamp>
            </span>
          )}
        </div>
        <div className="toolbar">
          {replay ? (
            <div className="replay-ctl" title="Replaying a recorded build">
              <span>Replay: {replay.manifest.name}</span>
              <div className="speeds" role="group" aria-label="Replay speed">
                {SPEEDS.map((s) => (
                  <button key={s} className={speed === s ? "on" : ""} onClick={() => setSpeed(s)} aria-pressed={speed === s}>
                    {s}x
                  </button>
                ))}
              </div>
            </div>
          ) : (
            source && (
              <span className="live-pill">
                {openId ? `${opened?.status === "running" ? "Following" : "From storage"}: ${openApp} · ${openId}` : `Live: ${BUILDER_APP || "no app set (NEXT_PUBLIC_ANYSCENE_APP)"}`}
              </span>
            )
          )}
          {!replay && (
            <a className="text-btn" href={galleryHref}>
              {openId ? "Back to gallery" : "Gallery"}
            </a>
          )}
          {!replay && (
            <span className="key-ctl">
              {keyOpen ? (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    setAccessKey(keyDraft.trim());
                    setKeyOpen(false);
                    setNeedsKey(false);
                  }}
                >
                  <input
                    type="password"
                    autoComplete="off"
                    aria-label="Access key"
                    placeholder="access key"
                    value={keyDraft}
                    onChange={(e) => setKeyDraft(e.target.value)}
                  />
                  <button className="text-btn" type="submit">
                    Save
                  </button>
                </form>
              ) : (
                <button className={`text-btn ${needsKey ? "bad" : ""}`} onClick={() => setKeyOpen(true)}>
                  {needsKey ? "Access key needed" : getAccessKey() ? "Access key set" : "Access key"}
                </button>
              )}
            </span>
          )}
          <button className="text-btn" onClick={() => setRightOpen((o) => !o)} aria-expanded={rightOpen}>
            {rightOpen ? "Hide critic" : "Show critic"}
          </button>
        </div>
      </header>

      <aside className="left">
        <BuilderInputs
          value={inputs}
          onChange={(v) => {
            if (v.file !== inputs.file) refUrl.current = "";
            setInputs(v);
          }}
          disabled={running}
          canBuild={!!(inputs.file || refUrl.current) && !running && !!source}
          building={running}
          onBuild={doBuild}
        />
        {res && res.build_id && openKind === "scene" && <ShotsOrder res={res} source={source instanceof LiveSource ? source : null} />}
        <BuilderSchedule run={run} now={serverNow} />
        {sourceError && <p className="error-note">{sourceError}</p>}
      </aside>

      <main className="center">
        <BuilderViewport
          tab={tab}
          onTab={(t) => {
            setTab(t);
            setFollow(false);
          }}
          follow={follow}
          onFollow={() => setFollow(true)}
          run={run}
          res={res}
          referenceUrl={inputs.previewUrl}
          now={serverNow}
          passed={passed}
        />
      </main>

      <section className="shelf-wrap">
        <ProductionLog run={run} />
      </section>

      <aside className="right" aria-hidden={!rightOpen}>
        <CriticPanel run={run} />
      </aside>
    </div>
  );
}

function errorMessage(e: unknown): string {
  if (!e) return "Request failed";
  const anyE = e as { body?: { detail?: unknown }; message?: string; status?: number };
  const d = anyE.body?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d[0]?.msg) return String(d[0].msg);
  return anyE.message || String(e);
}
