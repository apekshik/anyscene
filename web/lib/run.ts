// Folds the stage-event stream of one /plan or /build request into UI state.
import { BUILD_STAGES, PLAN_STAGES, type RunKind, type StageEvent } from "./types";

export type StageUiStatus = "pending" | "running" | "done" | "failed" | "skipped";

export interface StageState {
  status: StageUiStatus;
  start?: number; // run seconds
  end?: number;
  message: string;
  progress?: number;
}

export interface PropTile {
  id: string;
  label: string;
  ref_url?: string | null;
  model?: string | null;
  mesh_url?: string | null;
  status: "meshing" | "done" | "failed";
  arrivedAt: number;
  meshAt?: number;
}

export interface Preview {
  url: string;
  stage: string;
  message: string;
  at: number;
}

export interface RunState {
  kind: RunKind | null;
  status: "idle" | "running" | "done" | "failed";
  order: string[];
  stages: Record<string, StageState>;
  caption: { stage: string; message: string };
  previews: Preview[];
  props: Record<string, PropTile>;
  propOrder: string[];
  totalProps?: number;
  totalPlacements?: number;
  packageUrl?: string;
  panoramas: { url: string; label: string }[];
  sceneGlbUrl?: string;
  envUrl?: string;
  error?: string;
  lastAt: number;
  events: number;
}

export function initialRun(kind: RunKind | null = null): RunState {
  const order = kind === "build" ? [...BUILD_STAGES] : [...PLAN_STAGES];
  return {
    kind,
    status: kind ? "running" : "idle",
    order,
    stages: Object.fromEntries(order.map((s) => [s, { status: "pending", message: "" } as StageState])),
    caption: { stage: "", message: "" },
    previews: [],
    panoramas: [],
    props: {},
    propOrder: [],
    lastAt: 0,
    events: 0,
  };
}

export type RunAction =
  | { type: "start"; kind: RunKind }
  | { type: "event"; ev: StageEvent; t: number }
  | { type: "fail"; message: string; t: number }
  | { type: "finish"; t: number }
  | { type: "reset" };

const closed = (s: StageState) => s.status === "done" || s.status === "failed" || s.status === "skipped";

export function runReducer(state: RunState, action: RunAction): RunState {
  switch (action.type) {
    case "reset":
      return initialRun(null);
    case "start":
      return initialRun(action.kind);
    case "fail": {
      const stages = { ...state.stages };
      const cur = state.order.find((s) => stages[s].status === "running");
      if (cur) stages[cur] = { ...stages[cur], status: "failed", end: action.t, message: action.message };
      return { ...state, stages, status: "failed", error: action.message, caption: { stage: cur ?? "", message: action.message } };
    }
    case "finish": {
      if (state.status !== "running") return state;
      const stages = { ...state.stages };
      for (const s of state.order) {
        if (stages[s].status === "running") stages[s] = { ...stages[s], status: "done", end: action.t };
        else if (stages[s].status === "pending") stages[s] = { ...stages[s], status: "skipped" };
      }
      return { ...state, stages, status: "done" };
    }
    case "event":
      return applyEvent(state, action.ev, action.t);
  }
}

function applyEvent(state: RunState, ev: StageEvent, t: number): RunState {
  const stages = { ...state.stages };
  const order = state.order.includes(ev.stage) ? state.order : [...state.order.slice(0, -1), ev.stage, "done"];
  if (!stages[ev.stage]) stages[ev.stage] = { status: "pending", message: "" };
  const idx = order.indexOf(ev.stage);
  const isPropRefs = (s: string) => s === "prop_references";

  // A stage that starts implies the ones before it are finished (the endpoint doesn't emit "done" for every stage).
  // prop_references overlaps generating_meshes, so it closes on its own count or when layout starts.
  if (ev.status !== "failed") {
    order.slice(0, idx).forEach((s) => {
      const st = stages[s];
      if (isPropRefs(s) && order.indexOf("layout") > idx) return;
      if (st.status === "running") stages[s] = { ...st, status: "done", end: t, progress: st.progress !== undefined ? 1 : undefined };
      else if (st.status === "pending") stages[s] = { ...st, status: "skipped" };
    });
  }

  const cur = stages[ev.stage];
  const next: StageState = { ...cur };
  if (cur.start === undefined) next.start = t;
  const msg = ev.message || cur.message;
  if (ev.status === "failed") {
    next.status = "failed";
    next.end = t;
    next.message = ev.message;
  } else if (ev.status === "done") {
    if (!closed(cur) || cur.status === "done") {
      next.status = "done";
      next.end = cur.end ?? t;
    }
    next.message = msg;
    if (cur.progress !== undefined || ev.progress !== undefined) next.progress = ev.progress ?? 1;
  } else {
    // running: an already-closed stage (late meshes after generating_meshes "done") only updates its numbers
    if (!closed(cur)) next.status = "running";
    next.message = msg;
    if (ev.progress !== undefined) next.progress = ev.progress;
  }
  stages[ev.stage] = next;

  // props
  let { props, propOrder, totalProps, totalPlacements } = state;
  const m = ev.stage === "prop_references" && /(\d+) unique props \((\d+) placements\)/.exec(ev.message || "");
  if (m) {
    totalProps = +m[1];
    totalPlacements = +m[2];
  }
  if (ev.prop) {
    const p = ev.prop;
    const old = props[p.id];
    const tile: PropTile = {
      id: p.id,
      label: p.label || old?.label || p.id,
      ref_url: p.ref_url ?? old?.ref_url,
      model: p.model ?? old?.model,
      mesh_url: p.mesh_url ?? old?.mesh_url,
      status: p.status,
      arrivedAt: old?.arrivedAt ?? t,
      meshAt: p.mesh_url ? (old?.meshAt ?? t) : old?.meshAt,
    };
    props = { ...props, [p.id]: tile };
    if (!old) propOrder = [...propOrder, p.id];
  }
  if (totalProps && stages.prop_references && stages.prop_references.status !== "done") {
    const n = propOrder.length;
    const pr = stages.prop_references;
    stages.prop_references = { ...pr, progress: Math.min(1, n / totalProps) };
    if (n >= totalProps) stages.prop_references = { ...stages.prop_references, status: "done", end: t };
  }

  let status = state.status;
  if (ev.status === "failed") status = "failed";
  if (ev.stage === "done" && ev.status === "done") {
    status = "done";
    for (const s of order) {
      if (stages[s].status === "running") stages[s] = { ...stages[s], status: "done", end: t };
      if (stages[s].status === "pending") stages[s] = { ...stages[s], status: "skipped" };
    }
  }

  const previews = ev.preview_url
    ? [...state.previews.filter((p) => p.url !== ev.preview_url), { url: ev.preview_url, stage: ev.stage, message: ev.message, at: t }]
    : state.previews;

  // The caption follows the newest non-prop message (prop events are many and quick; they read on the shelf).
  const caption =
    ev.message && !(ev.prop && ev.prop.status === "meshing")
      ? { stage: ev.stage, message: ev.message }
      : state.caption.stage
        ? state.caption
        : { stage: ev.stage, message: ev.message };

  return {
    ...state,
    order,
    stages,
    props,
    propOrder,
    totalProps,
    totalPlacements,
    previews,
    caption,
    status,
    packageUrl: ev.package_url ?? state.packageUrl,
    panoramas:
      ev.panorama_url && !state.panoramas.some((p) => p.url === ev.panorama_url)
        ? [...state.panoramas, { url: ev.panorama_url, label: ev.viewpoint || `viewpoint ${state.panoramas.length + 1}` }]
        : state.panoramas,
    sceneGlbUrl: ev.scene_glb_url ?? state.sceneGlbUrl,
    envUrl: ev.environment_url ?? state.envUrl,
    error: ev.status === "failed" ? ev.message : state.error,
    lastAt: t,
    events: state.events + 1,
  };
}

/** Parse every stage event out of fal queue log lines. `seen` dedupes across polls (fal resends all logs). */
export function parseLogs(logs: { message?: string }[] | undefined, seen: Set<string>, prefix: string): StageEvent[] {
  const out: StageEvent[] = [];
  for (const log of logs ?? []) {
    const msg = log.message ?? "";
    const i = msg.indexOf(prefix);
    if (i < 0 || seen.has(msg)) continue;
    seen.add(msg);
    try {
      out.push(JSON.parse(msg.slice(i + prefix.length)));
    } catch {
      /* partial line */
    }
  }
  return out;
}

/** Which plan objects a prop asset stands for (props.py assets_for: the `asset` key, or the id's stem). */
export function assetKey(o: { id: string; asset?: string }) {
  return o.asset || o.id.replace(/(_(\d+|left|right|fg|bg|front|back|[a-z]))+$/, "");
}

export function fmtTime(s: number | undefined) {
  if (s === undefined || !isFinite(s)) return "";
  s = Math.max(0, s);
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}
