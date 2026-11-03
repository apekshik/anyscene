import { NextRequest } from "next/server";
import { createRouteHandler } from "@fal-ai/server-proxy/nextjs";
import { ALL_APPS, BUILDER_APP } from "@/lib/apps";
import { BUILDS_PER_DAY, DEV_OPEN, JOBS_PER_HOUR, buildsToday, clientIp, ipLimited, keyError, keyRole, owner, quotaMessage, recordBuild } from "@/lib/guard";

// fal's server-side proxy: the browser talks to /api/fal/proxy and the server adds FAL_KEY (never sent to the client).
// POSTs are limited to the AnyScene apps and fal storage uploads (for the reference image), so the key can't be used
// for arbitrary fal endpoints. The apps are the NEXT_PUBLIC_*_APP ids the UI calls (lib/apps.ts, web/.env.example);
// with none set, only uploads get through.
const fal = createRouteHandler({
  allowedEndpoints: [...ALL_APPS.map((app) => `${app}/**`), "storage/upload/**"],
  allowUnauthorizedRequests: true, // our own guard below decides who gets through (lib/guard.ts)
});

// Gallery reads (every build on storage, one build's events) are cheap lookups, not jobs: they don't count.
const READ_ONLY = /\/(builds|build_events|kits|kit_events)\/?(\?.*)?$/;
// A new scene build: the expensive one, counted against the per-person daily limit and tagged with its owner.
const BUILD = BUILDER_APP ? new RegExp(`^/${BUILDER_APP}/(ref2scene|build)/?$`) : null;

const APP_TARGETS = ALL_APPS.map((app) => `/${app}/`);

function json(status: number, error: string) {
  return new Response(JSON.stringify({ detail: error }), { status, headers: { "content-type": "application/json" } });
}

/** The fal path of a new job (a POST to one of our apps, not a gallery read), or null. */
function jobPath(req: NextRequest) {
  const target = req.headers.get("x-fal-target-url") || "";
  const m = target.match(/^https:\/\/(?:queue\.)?fal\.run(\/[^?]*)/);
  return m && req.method === "POST" && APP_TARGETS.some((p) => `${m[1]}/`.startsWith(p)) && !READ_ONLY.test(target) ? m[1] : null;
}

async function guarded(req: NextRequest, forward: (req: NextRequest) => Promise<Response>): Promise<Response> {
  const role = keyRole(req);
  if (!role) return json(401, keyError(req));
  const path = jobPath(req);
  if (!path) return forward(req);

  // local dev with no access key set: no limits, and a build is tagged only if the page says who you are
  const who = owner(req, role);
  if ("error" in who && !DEV_OPEN) return json(403, who.error);
  const limited = role !== "admin" && !DEV_OPEN;
  if (limited && ipLimited(clientIp(req))) return json(429, `Too many jobs from this address: ${JOBS_PER_HOUR} an hour.`);
  if (!BUILD?.test(path) || "error" in who) return forward(req);

  if (limited && (await buildsToday(who.email)) >= BUILDS_PER_DAY) return json(429, quotaMessage());
  // tag the build with who asked for it (builder/app.py stores `owner`; it is not part of the retry fingerprint)
  let body: Record<string, unknown>;
  try {
    body = JSON.parse((await req.text()) || "{}");
  } catch {
    return json(400, "The build request is not JSON.");
  }
  const headers = new Headers(req.headers);
  headers.delete("content-length");
  const tagged = new NextRequest(req.url, { method: "POST", headers, body: JSON.stringify({ ...body, owner: who.tag }) });
  const res = await forward(tagged);
  if (res.ok && limited) {
    const requestId = (await res.clone().json().catch(() => ({})))?.request_id || "";
    await recordBuild(who.email, requestId).catch((e) => console.error("quota record failed", e));
  }
  return res;
}

export async function GET(req: NextRequest) {
  return guarded(req, fal.GET);
}
export async function POST(req: NextRequest) {
  return guarded(req, fal.POST);
}
export async function PUT(req: NextRequest) {
  return guarded(req, fal.PUT);
}
