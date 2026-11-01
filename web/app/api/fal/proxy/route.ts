import { timingSafeEqual } from "node:crypto";
import type { NextRequest } from "next/server";
import { createRouteHandler } from "@fal-ai/server-proxy/nextjs";
import { ALL_APPS } from "@/lib/apps";

// fal's server-side proxy: the browser talks to /api/fal/proxy and the server adds FAL_KEY (never sent to the client).
// POSTs are limited to the AnyScene apps and fal storage uploads (for the reference image), so the key can't be used
// for arbitrary fal endpoints. The apps are the NEXT_PUBLIC_*_APP ids the UI calls (lib/apps.ts, web/.env.example);
// with none set, only uploads get through.
const fal = createRouteHandler({
  allowedEndpoints: [...ALL_APPS.map((app) => `${app}/**`), "storage/upload/**"],
  allowUnauthorizedRequests: true, // our own guard below decides who gets through
});

// ---------------------------------------------------------------- guard
// Shared secret: set ANYSCENE_ACCESS_KEY on the server and every proxied request must carry it as x-anyscene-key.
// Off in local dev when the variable is unset; in production an unset key closes the proxy (fail closed), so a fresh
// deployment can't be used to start builds on the owner's account.
const ACCESS_KEY = process.env.ANYSCENE_ACCESS_KEY || "";
const DEV_OPEN = !ACCESS_KEY && process.env.NODE_ENV !== "production";

// Rate limit on new jobs (POSTs to an app; status polls and uploads are not counted), per client IP, in memory.
// Per serverless instance only: a backstop behind the key, not a quota. ANYSCENE_JOBS_PER_HOUR, default 6.
const JOBS_PER_HOUR = Number(process.env.ANYSCENE_JOBS_PER_HOUR || 6);
const jobs = new Map<string, number[]>();

function json(status: number, error: string) {
  return new Response(JSON.stringify({ detail: error }), { status, headers: { "content-type": "application/json" } });
}

function keyOk(req: NextRequest) {
  if (DEV_OPEN) return true;
  if (!ACCESS_KEY) return false;
  const got = Buffer.from(req.headers.get("x-anyscene-key") || "");
  const want = Buffer.from(ACCESS_KEY);
  return got.length === want.length && timingSafeEqual(got, want);
}

// Gallery reads (every build on storage, one build's events) are cheap lookups, not jobs: they don't count.
const READ_ONLY = /\/(builds|build_events|kits|kit_events)\/?(\?.*)?$/;

const APP_TARGETS = ALL_APPS.map((app) => `/${app}/`);

function startsJob(req: NextRequest) {
  const target = req.headers.get("x-fal-target-url") || "";
  const m = target.match(/^https:\/\/(?:queue\.)?fal\.run(\/[^?]*)/);
  return !!m && APP_TARGETS.some((p) => `${m[1]}/`.startsWith(p)) && !READ_ONLY.test(target);
}

function rateLimited(req: NextRequest) {
  if (DEV_OPEN || !startsJob(req)) return false;
  const ip = (req.headers.get("x-forwarded-for") || "").split(",")[0].trim() || req.headers.get("x-real-ip") || "unknown";
  const now = Date.now();
  const recent = (jobs.get(ip) || []).filter((t) => now - t < 3600_000);
  if (recent.length >= JOBS_PER_HOUR) {
    jobs.set(ip, recent);
    return true;
  }
  recent.push(now);
  jobs.set(ip, recent);
  return false;
}

function guard(req: NextRequest): Response | null {
  if (!keyOk(req)) {
    return json(401, ACCESS_KEY ? "This AnyScene needs an access key." : "The AnyScene proxy is closed: ANYSCENE_ACCESS_KEY is not set on the server.");
  }
  if (req.method === "POST" && rateLimited(req)) return json(429, `Too many builds from this address: ${JOBS_PER_HOUR} an hour.`);
  return null;
}

export async function GET(req: NextRequest) {
  return guard(req) ?? fal.GET(req);
}
export async function POST(req: NextRequest) {
  return guard(req) ?? fal.POST(req);
}
export async function PUT(req: NextRequest) {
  return guard(req) ?? fal.PUT(req);
}
