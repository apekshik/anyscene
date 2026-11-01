// The shared gallery: every build anyone ran on the fal apps, read from their storage (/builds, /build_events on the
// builder app; /kits, /kit_events on the AnyKit app; see builder/gallery.py and lib/apps.ts). Unlike ?watch, this does
// not need the submitter's key: the fal queue only shows a request to the key that started it, storage shows everyone's.
import { fal } from "@fal-ai/client";
import { type BuilderEvent, type BuilderResponse, type Critique } from "./builder";
import { BUILDER_APP, KIT_APP, TEST_APP, requireApp } from "./apps";
import { configureFal } from "./sources";

export type GalleryKind = "scene" | "kit";
export { KIT_APP };

/** ?gallery_app=<id> points the scene gallery at NEXT_PUBLIC_ANYSCENE_TEST_APP (e.g. a private test copy).
 *  Empty when the app isn't configured; the calls below then fail with a message naming the env var. */
export function galleryApp(kind: GalleryKind, override?: string | null): string {
  if (kind === "kit") return KIT_APP;
  return override && (override === BUILDER_APP || override === TEST_APP) ? override : BUILDER_APP;
}

export interface GalleryItem {
  id: string;
  kind: GalleryKind;
  started: number; // unix seconds
  updated: number;
  status: "done" | "running" | "stopped" | "capped";
  passed: boolean;
  reference_urls: string[];
  prompt: string;
  dials: Record<string, number | string>;
  effort?: string | null;
  floor_plan_url?: string | null;
  items?: string[] | null;
  name?: string | null;
  critic_rounds: number;
  last_scores?: Record<string, number> | null;
  last_summary?: string | null;
  minutes: number;
  cover?: string | null;
  stills: string[];
  previews: { url: string; message: string }[];
  n_stills: number;
  n_previews: number;
  frames: number;
  milestone?: { stage: string; message: string; t: number } | null;
  attempts: number;
  has_response: boolean;
  agent_cost_usd?: number | null;
  error?: string | null;
}

export interface GalleryList {
  builds: GalleryItem[];
  total: number;
  now: number;
}

export interface GalleryEventsPage {
  id: string;
  events: BuilderEvent[];
  next: number;
  size: number;
  more: boolean;
  summary: GalleryItem;
  response?: Record<string, unknown>;
}

async function call<O>(endpoint: string, input: object): Promise<O> {
  configureFal();
  // through the queue, not a sync call: a cold GPU worker can take minutes to come up
  const r = await fal.subscribe(endpoint, { input, pollInterval: 700 });
  return r.data as O;
}

function needApp(kind: GalleryKind, app: string) {
  return requireApp(app, kind === "kit" ? "kit" : "builder");
}

export function listGallery(kind: GalleryKind, app: string, limit = 300): Promise<GalleryList> {
  app = needApp(kind, app);
  return call<GalleryList>(`${app}/${kind === "kit" ? "kits" : "builds"}`, { limit });
}

export function galleryEvents(kind: GalleryKind, app: string, id: string, after: number): Promise<GalleryEventsPage> {
  app = needApp(kind, app);
  return kind === "kit"
    ? call<GalleryEventsPage>(`${app}/kit_events`, { kit_id: id, after })
    : call<GalleryEventsPage>(`${app}/build_events`, { build_id: id, after });
}

/** The last listing, per kind, so the grid paints at once while a (possibly cold) worker answers. Per viewer only. */
const CACHE_KEY = (kind: GalleryKind, app: string) => `anyscene.gallery.${app}.${kind}`;
export function cachedList(kind: GalleryKind, app: string): GalleryList | null {
  try {
    const s = localStorage.getItem(CACHE_KEY(kind, app));
    return s ? (JSON.parse(s) as GalleryList) : null;
  } catch {
    return null;
  }
}
export function storeList(kind: GalleryKind, app: string, list: GalleryList) {
  try {
    localStorage.setItem(CACHE_KEY(kind, app), JSON.stringify(list));
  } catch {
    /* full or blocked: the grid just loads without a head start */
  }
}

interface KitItemResp {
  id: string;
  label?: string;
  thumb_url?: string | null;
  glb_url?: string | null;
}

/** A finished build's response, as the results view expects it. Kits map onto it: the lineup is the still, each item
 *  thumbnail a named preview. */
export function toBuilderResponse(kind: GalleryKind, r: Record<string, unknown> | undefined, id: string): BuilderResponse | null {
  if (!r) return null;
  if (kind === "scene") {
    const b = r as unknown as BuilderResponse;
    return {
      ...b,
      build_id: b.build_id || id,
      stills: b.stills ?? [],
      panorama_urls: b.panorama_urls ?? [],
      previews: b.previews ?? [],
      critiques: b.critiques ?? [],
      missing: b.missing ?? [],
      scene_blend_url: b.scene_blend_url ?? null,
      scene_glb_url: b.scene_glb_url ?? null,
      package_url: b.package_url ?? null,
      agent_cost_usd: b.agent_cost_usd ?? null,
      minutes: b.minutes as number,
    };
  }
  const items = ((r.items as KitItemResp[]) ?? []).filter((x) => x.thumb_url);
  const lineup = r.lineup_url as string | null;
  return {
    build_id: (r.kit_id as string) || id,
    stills: lineup ? [lineup] : [],
    previews: items.map((x) => ({ name: x.label || x.id, url: x.thumb_url! })),
    panorama_urls: [],
    scene_blend_url: (r.kit_blend_url as string | null) ?? null,
    scene_glb_url: null,
    package_url: (r.package_url as string | null) ?? null,
    critiques: (r.critiques as Critique[]) ?? [],
    missing: (r.missing as string[]) ?? [],
    dials: (r.dials as Record<string, unknown>) ?? {},
    agent_cost_usd: (r.agent_cost_usd as number | null) ?? null,
    minutes: r.minutes as number,
  };
}

export const ago = (unixS: number, now = Date.now() / 1000) => {
  const s = Math.max(0, now - unixS);
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400 * 2) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
};

export const STATUS_LABEL: Record<GalleryItem["status"], string> = {
  done: "Wrapped",
  running: "Rolling",
  stopped: "Stopped",
  capped: "Capped",
};
