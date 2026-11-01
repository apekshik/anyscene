// Contract with the AnyScene builder app, NEXT_PUBLIC_ANYSCENE_APP (builder/app.py, builder/scene_builder.py) and the UI state folded from its
// stage events. One request runs the whole build: an agent works, reports milestones, and loops with a critic.

export { BUILDER_APP } from "./apps";

export interface BuilderRequest {
  reference_image_urls: string[];
  prompt: string;
  effort: string;
  scene: string;
  /** Only the dials the user set; the builder reads the rest from the reference. */
  dials?: Record<string, number | string>;
  floor_plan_url?: string;
}

/** /shots: scene to images or scene to video, on a finished build. */
export interface ShotsRequest {
  build_id: string;
  mode: "images" | "video";
  shots: { name?: string; description?: string }[];
  settings?: { seconds?: number; handheld?: "none" | "walk" | "subtle"; lens_mm?: number; look?: string; res?: [number, number] };
  dials?: Record<string, number | string>;
  effort?: string;
}

export interface ShotsResponse {
  job_id: string;
  stills: string[];
  videos: string[];
  result: Record<string, unknown>;
  missing: string[];
  agent_cost_usd: number | null;
  minutes: number;
}

export const SCORE_KEYS = [
  "layout",
  "props",
  "screens_signage",
  "materials",
  "lighting",
  "atmosphere",
  "plausibility",
  "composition",
] as const;
export type ScoreKey = (typeof SCORE_KEYS)[number];
export const SCORE_LABELS: Record<ScoreKey, string> = {
  layout: "Layout",
  props: "Props",
  screens_signage: "Screens + signs",
  materials: "Materials",
  lighting: "Lighting",
  atmosphere: "Atmosphere",
  plausibility: "Plausibility",
  composition: "Composition",
};
export const PASS_MARK = 7;

export interface Critique {
  round: number;
  scores: Record<ScoreKey, number>;
  fixes: string[];
  summary: string;
  passed: boolean;
  stills?: string[];
}

export interface BuilderEvent {
  t: number; // seconds since the builder started (server clock)
  stage: string;
  status: "running" | "done" | "failed";
  message: string;
  preview_url?: string;
  tool?: string;
  critique?: Critique;
  package_url?: string;
  missing?: string[];
  critiques?: number;
  // heartbeat (every 20 s): the tool call in progress and every milestone so far
  working?: string | null;
  working_s?: number | null;
  milestones?: { t: number; stage: string; status: string; message: string; preview_url?: string }[];
}

export interface BuilderResponse {
  build_id: string;
  stills: string[];
  scene_blend_url: string | null;
  scene_glb_url: string | null;
  panorama_urls: string[];
  /** The scouting previews; each name is a camera usable in a /shots order. */
  previews?: { name: string; url: string }[];
  package_url: string | null;
  critiques: Critique[];
  missing: string[];
  /** Every dial as built (out/dials.json); the agent decides each entry's shape. */
  dials?: Record<string, unknown>;
  agent_cost_usd: number | null;
  minutes: number;
}

/** The milestones the agent usually reports (it picks its own; unknown ones are added in arrival order). */
export const MILESTONES = ["plan", "props", "layout", "dressing", "screens", "materials", "lighting", "atmosphere", "cameras", "finals"];
export const MILESTONE_LABELS: Record<string, string> = {
  plan: "Plan",
  props: "Props",
  layout: "Layout",
  dressing: "Set dressing",
  screens: "Screens",
  materials: "Materials",
  lighting: "Lighting",
  atmosphere: "Atmosphere",
  cameras: "Cameras",
  finals: "Finals",
};
const NON_MILESTONES = new Set(["received", "log", "thinking", "critique", "done", "packaged", "heartbeat", "error"]);

export interface LogLine {
  id: number;
  t: number;
  kind: "tool" | "note" | "milestone" | "critic" | "system";
  tool?: string;
  stage: string;
  text: string;
  image?: string;
}

export interface Milestone {
  stage: string;
  start: number;
  end?: number;
  message: string;
  takes: number;
  preview?: string;
}

export interface BuilderState {
  status: "idle" | "running" | "done" | "failed" | "ended"; // ended: a replay recording that stops mid-run
  buildId?: string;
  lines: LogLine[];
  milestones: Record<string, Milestone>;
  order: string[]; // MILESTONES plus extras the agent picked, in display order
  current?: string; // milestone being worked on
  previews: { url: string; stage: string; message: string; t: number }[];
  critiques: Critique[];
  criticBusy: boolean;
  received?: number;
  doneAt?: number;
  packagedAt?: number;
  packageUrl?: string;
  missing?: string[];
  lastT: number;
  error?: string;
  thought?: string; // the agent's latest note, for the caption
  working?: { what: string; since: number }; // the tool call in progress (heartbeat), what a long render looks like
}

export function initialBuilder(status: BuilderState["status"] = "idle"): BuilderState {
  return { status, lines: [], milestones: {}, order: [...MILESTONES], previews: [], critiques: [], criticBusy: false, lastT: 0 };
}

export type BuilderAction =
  | { type: "start" }
  | { type: "event"; ev: BuilderEvent }
  | { type: "result"; res: BuilderResponse }
  | { type: "fail"; message: string }
  | { type: "ended" }
  | { type: "reset" };

let lineId = 0;

export function builderReducer(s: BuilderState, a: BuilderAction): BuilderState {
  switch (a.type) {
    case "reset":
      return initialBuilder();
    case "start":
      return initialBuilder("running");
    case "fail":
      return {
        ...s,
        status: "failed",
        error: a.message,
        lines: [...s.lines, { id: ++lineId, t: s.lastT, kind: "system", stage: "failed", text: a.message }],
      };
    case "ended":
      return { ...s, status: "ended", criticBusy: false };
    case "result": {
      // the response is authoritative for critiques (the events can miss the last ones)
      const critiques = a.res.critiques?.length ? a.res.critiques : s.critiques;
      return {
        ...s,
        status: s.status === "failed" ? "failed" : "done",
        buildId: a.res.build_id || s.buildId,
        critiques,
        criticBusy: false,
        packageUrl: a.res.package_url ?? s.packageUrl,
        missing: a.res.missing ?? s.missing,
        doneAt: s.doneAt ?? s.lastT,
        milestones: closeAll(s, s.lastT),
        current: undefined,
      };
    }
    case "event":
      return applyEvent(s, a.ev);
  }
}

function closeAll(s: BuilderState, t: number) {
  const ms = { ...s.milestones };
  for (const k of Object.keys(ms)) if (ms[k].end === undefined) ms[k] = { ...ms[k], end: t };
  return ms;
}

function applyEvent(s: BuilderState, ev: BuilderEvent): BuilderState {
  const t = typeof ev.t === "number" ? ev.t : s.lastT;
  const next: BuilderState = { ...s, lastT: Math.max(s.lastT, t) };
  const line = (kind: LogLine["kind"], text: string, extra: Partial<LogLine> = {}) =>
    (next.lines = [...next.lines, { id: ++lineId, t, kind, stage: ev.stage, text, ...extra }]);

  if (ev.preview_url && !s.previews.some((p) => p.url === ev.preview_url)) {
    next.previews = [...s.previews, { url: ev.preview_url, stage: ev.stage, message: ev.message, t }];
  }
  if (ev.status === "failed") {
    next.status = "failed";
    next.error = ev.message;
  }

  switch (ev.stage) {
    case "received": {
      next.received = next.received ?? t;
      const id = /build ([bk]_\w+)/.exec(ev.message)?.[1]; // b_ scene builds, k_ kits
      if (id) next.buildId = id;
      line("system", ev.message);
      break;
    }
    case "log":
      next.working = undefined;
      line("tool", ev.message, { tool: ev.tool || "Tool" });
      break;
    case "heartbeat": {
      next.working = ev.working ? { what: ev.working, since: t - (ev.working_s ?? 0) } : undefined;
      // a page that attached late missed the early milestones: the heartbeat carries them all
      let filled: BuilderState = next;
      for (const m of ev.milestones ?? []) {
        if (!filled.milestones[m.stage]) filled = applyEvent(filled, { ...m, status: "running" } as BuilderEvent);
      }
      if (filled !== next) return { ...filled, current: filled.current, working: next.working, lastT: next.lastT };
      break;
    }
    case "error":
      line("system", ev.message);
      break;
    case "thinking":
      next.thought = ev.message;
      line("note", ev.message);
      break;
    case "critique":
      if (ev.critique) {
        const c = ev.critique;
        next.critiques = [...s.critiques.filter((x) => x.round !== c.round), c].sort((a, b) => a.round - b.round);
        next.criticBusy = false;
        line("critic", `round ${c.round}: ${c.passed ? "PASS" : "not yet"}. ${c.summary || ""}`.trim(), { image: ev.preview_url });
      } else {
        next.criticBusy = true;
        line("critic", ev.message);
      }
      break;
    case "done":
      next.doneAt = t;
      next.missing = ev.missing ?? s.missing;
      next.milestones = closeAll(next, t);
      next.current = undefined;
      line("system", ev.message);
      break;
    case "packaged":
      next.packagedAt = t;
      next.packageUrl = ev.package_url ?? s.packageUrl;
      if (next.status !== "failed") next.status = "done";
      line("system", ev.message);
      break;
    default: {
      if (NON_MILESTONES.has(ev.stage)) break;
      // a milestone the agent reported: it is now the current one; the previous one wraps
      const ms = { ...s.milestones };
      if (s.current && s.current !== ev.stage && ms[s.current] && ms[s.current].end === undefined) {
        ms[s.current] = { ...ms[s.current], end: t };
      }
      const old = ms[ev.stage];
      const retake = !!old && s.current !== ev.stage;
      ms[ev.stage] = {
        stage: ev.stage,
        start: old && !retake ? old.start : t,
        end: undefined,
        message: ev.message || old?.message || "",
        takes: (old?.takes ?? 0) + (retake || !old ? 1 : 0),
        preview: ev.preview_url ?? old?.preview,
      };
      next.milestones = ms;
      next.current = ev.stage;
      if (!s.order.includes(ev.stage)) next.order = [...s.order, ev.stage];
      line("milestone", ev.message, { image: ev.preview_url });
    }
  }
  return next;
}

export const clock = (s: number | undefined) => {
  if (s === undefined || !isFinite(s)) return "";
  s = Math.max(0, Math.floor(s));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(sec).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
};
