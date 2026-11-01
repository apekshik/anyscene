// Data contract with the AnyScene pipeline fal app, NEXT_PUBLIC_ANYSCENE_PIPELINE_APP (endpoint/app.py, endpoint/stages.py, docs/ENDPOINT.md).

export const STAGE_PREFIX = "ANYSCENE_STAGE ";

export type StageStatus = "running" | "done" | "failed";

export interface PropEvent {
  id: string;
  label: string;
  ref_url?: string | null;
  model?: string | null;
  mesh_url?: string | null;
  status: "meshing" | "done" | "failed";
}

export interface StageEvent {
  stage: string;
  status: StageStatus;
  message: string;
  elapsed_s: number;
  progress?: number;
  preview_url?: string;
  prop?: PropEvent;
  package_url?: string;
  // 360 (expected from the endpoint soon; all optional)
  panorama_url?: string; // rendering: one equirectangular Cycles render per viewpoint
  viewpoint?: string; // rendering: which viewpoint the panorama is from
  scene_glb_url?: string; // packaging: decimated scene glTF with KHR_lights_punctual
  environment_url?: string; // any stage: equirect HDR/PNG of the scene's lighting for the prop viewer
}

export type RunKind = "plan" | "build";

export const PLAN_STAGES = ["received", "reading_reference", "planning", "drawing_floor_plan", "blockout", "done"] as const;
export const BUILD_STAGES = [
  "received",
  "prop_references",
  "generating_meshes",
  "layout",
  "dressing",
  "rendering",
  "packaging",
  "done",
] as const;

export const STAGE_LABELS: Record<string, string> = {
  received: "Call received",
  reading_reference: "Reading the plate",
  planning: "Layout plan",
  drawing_floor_plan: "Floor plan",
  blockout: "Grey-box",
  prop_references: "Prop refs",
  generating_meshes: "Prop build",
  layout: "Layout + stand-ins",
  dressing: "Set dressing",
  rendering: "Camera: stills",
  packaging: "Package",
  done: "Wrap",
};

// ---- Plan (schema.py) ----
export interface PlanObject {
  id: string;
  label: string;
  asset?: string;
  category: string;
  x: number;
  y: number;
  z: number;
  w: number;
  d: number;
  h: number;
  rot: number;
  source: "reference" | "invented";
  generate: boolean;
  prompt?: string;
  crop?: number[] | null;
}
export interface PlanLight {
  id: string;
  kind: string;
  x: number;
  y: number;
  z: number;
  color: string;
  power: string;
  source?: string;
}
export interface PlanOpening {
  wall: "front" | "back" | "left" | "right";
  kind: string;
  center: number;
  width: number;
  height: number;
  sill: number;
}
export interface Plan {
  name: string;
  summary: string;
  setting: string;
  time_of_day?: string;
  mood?: string[];
  palette?: string[];
  room: { width: number; depth: number; height: number };
  openings: PlanOpening[];
  objects: PlanObject[];
  lights: PlanLight[];
  reference_camera?: { position: number[]; look_at: number[]; lens_mm: number };
  notes?: string[];
  dials?: Record<string, { value: number | string; means: string }>;
}

// ---- Requests / responses (app.py) ----
export interface PlanRequest {
  reference_image_urls?: string[];
  floor_plan_url?: string | null;
  prompt?: string;
  plan_id?: string;
  edit?: string;
  effort?: string;
  dials?: Record<string, number | string>;
}
export interface PlanResponse {
  plan_id: string;
  plan: Plan;
  floor_plan_url: string;
  blockout_reference_url: string;
  blockout_overview_url: string;
  comparison_url: string;
  timings: Record<string, number>;
}
export interface BuildRequest {
  plan_id: string;
  tier: "draft" | "full";
  mesh_deadline_s?: number;
  late_mesh_wait_s?: number;
  still_samples?: number;
  include_glbs?: boolean;
}
export interface BuildResponse {
  scene_id: string;
  package_url: string;
  scene_blend_url: string;
  stills: string[];
  props: { id: string; label: string; ref_url?: string; mesh_urls?: Record<string, string>; placements?: string[] }[];
  standins_left: string[];
  timings: Record<string, number>;
  panorama_urls?: string[];
  scene_glb_url?: string;
  environment_url?: string;
}

// ---- Dials (docs/ENDPOINT.md) ----
export type DialSpec =
  | { key: string; label: string; kind: "range"; min: number; max: number; lo: string; hi: string; group: string }
  | { key: string; label: string; kind: "select"; options: string[]; group: string };

export const DIALS: DialSpec[] = [
  { key: "density", label: "Density", kind: "range", min: 0, max: 1, lo: "sparse", hi: "packed", group: "Stuff" },
  { key: "tidiness", label: "Tidiness", kind: "range", min: 0, max: 1, lo: "messy", hi: "tidy", group: "Stuff" },
  { key: "wear", label: "Wear", kind: "range", min: 0, max: 1, lo: "pristine", hi: "decayed", group: "Surfaces" },
  { key: "wetness", label: "Wetness", kind: "range", min: 0, max: 1, lo: "dry", hi: "soaked", group: "Surfaces" },
  { key: "atmosphere", label: "Atmosphere", kind: "range", min: 0, max: 1, lo: "clear", hi: "thick", group: "Environment" },
  { key: "power", label: "Power", kind: "range", min: 0, max: 1, lo: "dormant", hi: "live", group: "Energy" },
  { key: "warmth", label: "Warmth", kind: "range", min: -1, max: 1, lo: "cold", hi: "warm", group: "Look" },
  { key: "time_of_day", label: "Time of day", kind: "select", options: ["dawn", "day", "dusk", "night"], group: "Environment" },
  { key: "weather", label: "Weather", kind: "select", options: ["clear", "overcast", "rain", "fog", "snow"], group: "Environment" },
  { key: "look", label: "Look", kind: "select", options: ["clean", "cinematic", "gritty", "vintage"], group: "Look" },
];
