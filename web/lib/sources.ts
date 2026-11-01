// Where stage events come from: the live fal app (through the Next.js proxy) or a recorded run in public/replay/.
import { fal } from "@fal-ai/client";
import {
  STAGE_PREFIX,
  type BuildRequest,
  type BuildResponse,
  type Plan,
  type PlanRequest,
  type PlanResponse,
  type StageEvent,
} from "./types";
import { assetKey, parseLogs } from "./run";
import { type BuilderEvent, type BuilderRequest, type BuilderResponse, type ShotsRequest, type ShotsResponse } from "./builder";

import { BUILDER_APP, PIPELINE_APP, requireApp } from "./apps";

export const APP_ID = PIPELINE_APP;

export interface Sink {
  onEvent: (ev: StageEvent, t: number) => void;
}

export interface BuilderSink {
  onEvent: (ev: BuilderEvent) => void;
}

export interface Source {
  readonly mode: "live" | "replay";
  /** Seconds since the current request was submitted (replay: virtual seconds at the replay speed). */
  clock(): number;
  uploadReference(file: File): Promise<string>;
  plan(req: PlanRequest, sink: Sink): Promise<PlanResponse>;
  build(req: BuildRequest, sink: Sink): Promise<BuildResponse>;
  builder(req: BuilderRequest, sink: BuilderSink): Promise<BuilderResponse>;
}

// ---------------------------------------------------------------- live

// The proxy can require a shared access key (ANYSCENE_ACCESS_KEY on the server). The viewer types it once; it is kept
// in this browser's localStorage and sent as x-anyscene-key to our own proxy only (the proxy never forwards it to fal).
export const ACCESS_KEY_STORAGE = "anyscene.access-key";
export function getAccessKey(): string {
  try {
    return localStorage.getItem(ACCESS_KEY_STORAGE) || "";
  } catch {
    return "";
  }
}
export function setAccessKey(k: string) {
  try {
    if (k) localStorage.setItem(ACCESS_KEY_STORAGE, k);
    else localStorage.removeItem(ACCESS_KEY_STORAGE);
  } catch {
    /* private window: the key lasts for this page only */
  }
  sessionKey = k;
}
let sessionKey = "";

let falConfigured = false;
export function configureFal() {
  if (falConfigured) return;
  fal.config({
    proxyUrl: "/api/fal/proxy",
    requestMiddleware: async (req) => {
      const key = sessionKey || getAccessKey();
      return key ? { ...req, headers: { ...(req.headers || {}), "x-anyscene-key": key } } : req;
    },
  });
  falConfigured = true;
}

export class LiveSource implements Source {
  readonly mode = "live" as const;
  private t0 = performance.now();

  clock() {
    return (performance.now() - this.t0) / 1000;
  }

  async uploadReference(file: File) {
    configureFal();
    return fal.storage.upload(file);
  }

  private async call<O>(endpoint: string, input: object, onEvent: (ev: StageEvent) => void, pollInterval = 1000): Promise<O> {
    configureFal();
    this.t0 = performance.now();
    const seen = new Set<string>();
    const take = (logs: unknown) => {
      for (const ev of parseLogs(logs as { message?: string }[] | undefined, seen, STAGE_PREFIX)) onEvent(ev);
    };
    const res = await fal.subscribe(endpoint, {
      input,
      logs: true,
      pollInterval,
      onQueueUpdate: (update) => take("logs" in update ? update.logs : undefined),
    });
    // The last poll that sees COMPLETED usually carries no logs, so the closing events ("blockout done" with the
    // comparison, "done" with package_url) would be lost. Ask for the logs once more.
    try {
      const st = await fal.queue.status(endpoint, { requestId: res.requestId, logs: true });
      take("logs" in st ? st.logs : undefined);
    } catch {
      /* the response itself still has everything the UI needs */
    }
    return res.data as O;
  }

  plan(req: PlanRequest, sink: Sink) {
    return this.call<PlanResponse>(`${requireApp(APP_ID, "pipeline")}/plan`, req, (ev) => sink.onEvent(ev, this.clock()));
  }

  build(req: BuildRequest, sink: Sink) {
    return this.call<BuildResponse>(`${requireApp(APP_ID, "pipeline")}/build`, req, (ev) => sink.onEvent(ev, this.clock()));
  }

  /** The agent builder: one request, up to fal's 2 h cap. Logs grow with every tool call, so poll every 2 s. */
  builder(req: BuilderRequest, sink: BuilderSink) {
    return this.call<BuilderResponse>(`${requireApp(BUILDER_APP, "builder")}/ref2scene`, req, (ev) => sink.onEvent(ev as unknown as BuilderEvent), 2000);
  }

  /** Scene to images / video on a finished build: same event stream as a build (the shots agent reports blocking,
   *  farm progress and finals). */
  shots(req: ShotsRequest, sink: BuilderSink) {
    return this.call<ShotsResponse>(`${requireApp(BUILDER_APP, "builder")}/shots`, req, (ev) => sink.onEvent(ev as unknown as BuilderEvent), 2000);
  }

  /** Attach to a build that is already running (started elsewhere: the CLI client, another tab) by its fal request id.
   *  The queue keeps the request's whole log, so the page catches up from the start and then follows it live. */
  async watchBuilder(requestId: string, sink: BuilderSink): Promise<BuilderResponse> {
    configureFal();
    this.t0 = performance.now();
    const endpoint = `${requireApp(BUILDER_APP, "builder")}/ref2scene`;
    const seen = new Set<string>();
    const take = (logs: unknown) => {
      for (const ev of parseLogs(logs as { message?: string }[] | undefined, seen, STAGE_PREFIX))
        sink.onEvent(ev as unknown as BuilderEvent);
    };
    for (;;) {
      const st = await fal.queue.status(endpoint, { requestId, logs: true });
      take("logs" in st ? st.logs : undefined);
      if (st.status === "COMPLETED") break;
      await new Promise((r) => setTimeout(r, 3000));
    }
    const res = await fal.queue.result(endpoint, { requestId });
    return res.data as BuilderResponse;
  }
}

// ---------------------------------------------------------------- replay

export interface ReplayManifest {
  name: string;
  plan_events: boolean;
  plan: boolean;
  reference: string | null;
  floor_plan: string | null;
  blockout_reference: string | null;
  blockout_overview: string | null;
  comparison: string | null;
  build_events: boolean;
  build: boolean;
  stills: string[];
  panoramas?: string[];
  scene_glb?: string | null;
  kind?: "pipeline" | "builder";
  events?: boolean; // builder: events.jsonl
}

type Recorded = StageEvent & { t: number };

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export class ReplaySource implements Source {
  readonly mode = "replay" as const;
  speed: number;
  paused = false;
  private vt = 0;
  private last = performance.now();
  private base: string;
  private planCache?: Plan;

  constructor(
    readonly manifest: ReplayManifest,
    speed = 1,
  ) {
    this.speed = speed;
    this.base = `/replay/${manifest.name}/`;
  }

  static async load(name: string, speed: number): Promise<ReplaySource> {
    let res = await fetch(`/replay/${encodeURIComponent(name)}/manifest.json`);
    if (!res.ok) res = await fetch(`/replay/demo/manifest.json`);
    if (!res.ok) throw new Error(`No replay named "${name}" in web/fixtures (run npm run fixtures).`);
    return new ReplaySource(await res.json(), speed);
  }

  url(file: string | null | undefined) {
    if (!file) return "";
    return /^(https?:|data:|blob:|\/)/.test(file) ? file : this.base + file;
  }

  get referenceUrl() {
    return this.url(this.manifest.reference);
  }

  clock() {
    this.tick();
    return this.vt;
  }

  private tick() {
    const now = performance.now();
    if (!this.paused) this.vt += ((now - this.last) / 1000) * this.speed;
    this.last = now;
  }

  private reset() {
    this.vt = 0;
    this.last = performance.now();
  }

  private async lines(file: string): Promise<Recorded[]> {
    const txt = await (await fetch(this.base + file)).text();
    return txt
      .split(/\r?\n/)
      .filter((l) => l.trim())
      .map((l) => JSON.parse(l));
  }

  /** Play recorded events on the virtual clock, starting the first one at ~0.6 s. */
  private async play(events: Recorded[], sink: Sink, remap: (ev: Recorded) => Recorded) {
    const t0 = (events[0]?.t ?? 0) - 0.6;
    this.reset();
    for (const ev of events) {
      const at = ev.t - t0;
      while (this.clock() < at) await sleep(Math.min(100, Math.max(16, ((at - this.vt) * 1000) / this.speed)));
      const { t: _t, ...rest } = remap(ev);
      sink.onEvent(rest as StageEvent, at);
    }
  }

  async uploadReference(file: File) {
    return URL.createObjectURL(file);
  }

  /** Builder replay: events.jsonl on its own server clock (t), build.json as the response. Recorded still URLs are
   *  swapped for local still_*.png copies when the fixture has them. */
  async builder(_req: BuilderRequest, sink: BuilderSink): Promise<BuilderResponse> {
    const events = (await this.lines("events.jsonl")) as unknown as BuilderEvent[];
    const res: BuilderResponse = this.manifest.build
      ? await (await fetch(this.base + "build.json")).json()
      : { build_id: "", stills: [], scene_blend_url: null, scene_glb_url: null, panorama_urls: [], package_url: null, critiques: [], missing: [], agent_cost_usd: null, minutes: 0 };
    const local = new Map<string, string>();
    (res.stills ?? []).forEach((u, i) => this.manifest.stills[i] && local.set(u, this.url(this.manifest.stills[i])));
    const fix = (u?: string | null) => (u ? (local.get(u) ?? this.url(u)) : (u ?? undefined));
    this.reset();
    const t0 = (events[0]?.t ?? 0) - 0.6;
    for (const ev of events) {
      const at = ev.t - t0;
      while (this.clock() < at) await sleep(Math.min(100, Math.max(16, ((at - this.vt) * 1000) / this.speed)));
      sink.onEvent({ ...ev, preview_url: fix(ev.preview_url) ?? undefined, package_url: fix(ev.package_url) ?? undefined });
    }
    if (!this.manifest.build) return { ...res, _partial: true } as BuilderResponse;
    return {
      ...res,
      stills: (res.stills ?? []).map((u) => fix(u)!),
      panorama_urls: (res.panorama_urls ?? []).map((u) => fix(u)!),
      scene_glb_url: fix(res.scene_glb_url) ?? null,
      scene_blend_url: fix(res.scene_blend_url) ?? null,
      package_url: fix(res.package_url) ?? null,
    };
  }

  async loadPlan(): Promise<Plan> {
    if (!this.planCache) this.planCache = await (await fetch(this.base + "plan.json")).json();
    return this.planCache!;
  }

  async plan(req: PlanRequest, sink: Sink): Promise<PlanResponse> {
    const plan = await this.loadPlan();
    const m = this.manifest;
    let recordedId: string | undefined;
    if (req.plan_id && req.edit) {
      // A recorded edit isn't available: play a short revision and return the same plan.
      const n = plan.objects.length;
      const inv = plan.objects.filter((o) => o.source === "invented").length;
      const fake: Recorded[] = [
        { t: 0, stage: "received", status: "running", message: "plan request", elapsed_s: 0 },
        { t: 0.2, stage: "planning", status: "running", message: "revising the plan", elapsed_s: 0.2 },
        { t: 24, stage: "planning", status: "done", message: `${n} objects (${inv} invented), ${plan.lights.length} lights, ${plan.room.width} x ${plan.room.depth} m ${plan.setting}`, elapsed_s: 24 },
        { t: 24.3, stage: "drawing_floor_plan", status: "running", message: "", elapsed_s: 24.3 },
        { t: 25, stage: "drawing_floor_plan", status: "done", message: "", elapsed_s: 25, preview_url: m.floor_plan ?? undefined },
        { t: 25, stage: "blockout", status: "running", message: "grey-box renders from the reference camera and an overview", elapsed_s: 25 },
        { t: 58, stage: "blockout", status: "done", message: "", elapsed_s: 58, preview_url: m.comparison ?? undefined },
        { t: 58, stage: "done", status: "done", message: `plan ${req.plan_id}`, elapsed_s: 58 },
      ];
      await this.play(fake, sink, (ev) => ({ ...ev, preview_url: ev.preview_url ? this.url(ev.preview_url) : undefined }));
    } else {
      const events = m.plan_events ? await this.lines("plan_events.jsonl") : [];
      recordedId = events.map((e) => /plan (p_\w+)/.exec(e.message || "")?.[1]).find(Boolean);
      await this.play(events, sink, (ev) => {
        let p = ev.preview_url;
        if (ev.stage === "drawing_floor_plan" && p && m.floor_plan) p = m.floor_plan;
        return { ...ev, preview_url: p ? this.url(p) : undefined };
      });
    }
    const done = /plan (p_\w+)/.exec(JSON.stringify(m)) ?? null;
    return {
      plan_id: req.plan_id || (done ? done[1] : "p_4f46c795ea"),
      plan,
      floor_plan_url: this.url(m.floor_plan),
      blockout_reference_url: this.url(m.blockout_reference),
      blockout_overview_url: this.url(m.blockout_overview),
      comparison_url: this.url(m.comparison),
      timings: {},
    };
  }

  async build(req: BuildRequest, sink: Sink): Promise<BuildResponse> {
    const m = this.manifest;
    const plan = await this.loadPlan();
    const recorded = m.build_events ? await this.lines("build_events.jsonl") : synthesizeBuild(plan, req.plan_id);
    const result: Partial<BuildResponse> = m.build ? await (await fetch(this.base + "build.json")).json() : {};
    // Stills recorded with the run are served locally; map the remote still URLs onto them in order.
    const remoteStills = result.stills ?? [];
    const localStills = m.stills.map((s) => this.url(s));
    const stillMap = new Map(remoteStills.map((u, i) => [u, localStills[i] ?? u]));
    const local = (u?: string) => (u ? (stillMap.get(u) ?? this.url(u)) : undefined);
    await this.play(withPlaceholder360(recorded, m.panoramas ?? [], m.scene_glb ?? null), sink, (ev) => ({
      ...ev,
      preview_url: local(ev.preview_url),
      panorama_url: ev.panorama_url ? this.url(ev.panorama_url) : undefined,
      scene_glb_url: ev.scene_glb_url ? this.url(ev.scene_glb_url) : undefined,
    }));
    const last = recorded.findLast?.((e) => e.package_url) ?? [...recorded].reverse().find((e) => e.package_url);
    return {
      scene_id: result.scene_id ?? "s_replay",
      package_url: result.package_url ?? last?.package_url ?? "",
      scene_blend_url: result.scene_blend_url ?? "",
      stills: remoteStills.length ? remoteStills.map((u) => local(u)!) : localStills,
      props: result.props ?? [],
      standins_left: result.standins_left ?? [],
      timings: result.timings ?? {},
    };
  }
}

// ---------------------------------------------------------------- placeholder 360

/** The endpoint doesn't emit panoramas or a scene glTF yet: when a recording has none but fixtures/ has the
 *  placeholders, add them where the endpoint will (rendering: one panorama per viewpoint; packaging: the scene). */
function withPlaceholder360(events: Recorded[], panoramas: string[], sceneGlb: string | null): Recorded[] {
  const out = [...events];
  const hasPano = events.some((e) => e.panorama_url);
  const hasGlb = events.some((e) => e.scene_glb_url);
  const lastRender = [...events].reverse().find((e) => e.stage === "rendering" && e.status === "running");
  if (!hasPano && panoramas.length && lastRender) {
    panoramas.forEach((p, i) => {
      const vp = p.replace(/^panorama_|\.\w+$/g, "");
      const label = vp === "ref" ? "reference camera" : vp === "mid" ? "room centre" : vp;
      out.push({ t: lastRender.t + 0.2 + i * 0.2, stage: "rendering", status: "running", message: `360 plate: ${label} (placeholder)`, elapsed_s: lastRender.elapsed_s, panorama_url: p, viewpoint: `${label} (placeholder)` });
    });
  }
  const pack = events.find((e) => e.stage === "packaging");
  if (!hasGlb && sceneGlb && pack) {
    out.push({ t: pack.t + 0.5, stage: "packaging", status: "running", message: "scene glTF exported (placeholder)", elapsed_s: pack.elapsed_s, scene_glb_url: sceneGlb });
  }
  return out.sort((a, b) => a.t - b.t);
}

// ---------------------------------------------------------------- synthesized build

// Used only when no recorded /build run is in fixtures/: one tile per unique generated asset (as props.py groups
// them), references at 30-60 s, meshes at 3-9 min, a failure and two stand-ins, like a real draft build.
export const SAMPLE_GLB = "https://threejs.org/examples/models/gltf/DamagedHelmet/glTF-Binary/DamagedHelmet.glb";

function synthesizeBuild(plan: Plan, planId: string): Recorded[] {
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const assets = new Map<string, { id: string; label: string; n: number; small: boolean }>();
  for (const o of plan.objects) {
    if (!o.generate) continue;
    const k = assetKey(o);
    const a = assets.get(k) ?? { id: k, label: o.label, n: 0, small: (o.category === "prop" || o.category === "clutter") && Math.max(o.w, o.d, o.h) < 0.3 };
    a.n++;
    assets.set(k, a);
  }
  const list = [...assets.values()];
  const N = list.length;
  const ev: Recorded[] = [
    { t: 0, stage: "received", status: "running", message: `build ${planId} (draft)`, elapsed_s: 0 },
    { t: 1.2, stage: "prop_references", status: "running", message: `${N} unique props (${list.reduce((s, a) => s + a.n, 0)} placements)`, elapsed_s: 1.2, progress: 0 },
  ];
  const meshes: { t: number; a: (typeof list)[0]; fail: boolean; model: string }[] = [];
  list.forEach((a, i) => {
    const tr = 30 + rnd() * 30;
    ev.push({ t: tr, stage: "prop_references", status: "running", message: `${a.id} reference ready`, elapsed_s: tr, prop: { id: a.id, label: a.label, ref_url: null, status: "meshing" } });
    const model = a.small ? "meshy" : "tripo-h31";
    const tm = i === 3 || i === 9 ? 1e9 : tr + (a.small ? 300 + rnd() * 240 : 150 + rnd() * 240);
    meshes.push({ t: tm, a, fail: i === 6, model });
  });
  meshes.sort((x, y) => x.t - y.t);
  let done = 0;
  for (const mm of meshes) {
    if (mm.t > 480) break;
    done++;
    ev.push({
      t: mm.t, stage: "generating_meshes", status: "running", message: `${done} of ${N} props have meshes`, elapsed_s: mm.t, progress: done / N,
      prop: { id: mm.a.id, label: mm.a.label, ref_url: null, model: mm.fail ? null : mm.model, mesh_url: mm.fail ? null : SAMPLE_GLB, status: mm.fail ? "failed" : "done" },
    });
  }
  const left = N - done;
  ev.push({ t: 481, stage: "generating_meshes", status: "done", message: `${done} of ${N} props ready, ${left} still running`, elapsed_s: 481 });
  ev.push({ t: 481, stage: "layout", status: "running", message: "building the scene from the plan", elapsed_s: 481 });
  ev.push({ t: 540, stage: "layout", status: "done", message: `${plan.objects.length} objects placed, ${left} stand-ins`, elapsed_s: 540 });
  ev.push({ t: 540, stage: "dressing", status: "running", message: `waiting up to 240 s for ${left} late meshes`, elapsed_s: 540 });
  ev.push({ t: 780, stage: "dressing", status: "done", message: `swapped ${done} props, ${left} stand-ins kept`, elapsed_s: 780 });
  ev.push({ t: 781, stage: "rendering", status: "running", message: "stills from the reference camera and two open views", elapsed_s: 781 });
  ev.push({ t: 900, stage: "rendering", status: "done", message: "3 stills", elapsed_s: 900 });
  ev.push({ t: 901, stage: "packaging", status: "running", message: "", elapsed_s: 901 });
  ev.push({ t: 930, stage: "done", status: "done", message: "scene s_synthetic in 930 s", elapsed_s: 930 });
  return ev.sort((a, b) => a.t - b.t);
}
