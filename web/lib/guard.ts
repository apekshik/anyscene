// Server only: who may use the proxy, who they say they are, and how many builds they have left today. Used by
// app/api/fal/proxy (every fal call) and app/api/me (the page's "who am I, what's left" check).
import { createHash, timingSafeEqual } from "node:crypto";
import { list, put } from "@vercel/blob";

// Shared password: set ANYSCENE_ACCESS_KEY on the server and every proxied request must carry it as x-anyscene-key.
// Off in local dev when the variable is unset; in production an unset key closes the proxy (fail closed), so a fresh
// deployment can't be used to start builds on the owner's account. ANYSCENE_ADMIN_KEY, given in place of the access
// key, also skips the per-IP and per-person limits.
export const ACCESS_KEY = process.env.ANYSCENE_ACCESS_KEY || "";
const ADMIN_KEY = process.env.ANYSCENE_ADMIN_KEY || "";
export const DEV_OPEN = !ACCESS_KEY && process.env.NODE_ENV !== "production";

// New jobs per client IP per hour (in memory, per serverless instance: a backstop) and builds per person per UTC day
// (in a private Vercel Blob store when BLOB_READ_WRITE_TOKEN is set, so it holds across instances; else in memory).
export const JOBS_PER_HOUR = Number(process.env.ANYSCENE_JOBS_PER_HOUR || 6);
export const BUILDS_PER_DAY = Number(process.env.ANYSCENE_BUILDS_PER_DAY || 3);
// Optional: only emails at this domain may build (e.g. fal.ai); usernames are always allowed, the password is the gate.
export const OWNER_DOMAIN = (process.env.ANYSCENE_OWNER_DOMAIN || "").trim().toLowerCase().replace(/^@/, "");

const same = (got: string, want: string) => {
  const a = Buffer.from(got);
  const b = Buffer.from(want);
  return !!want && a.length === b.length && timingSafeEqual(a, b);
};

/** "admin", "user", or null when the key is missing or wrong. */
export function keyRole(req: Request): "admin" | "user" | null {
  const got = req.headers.get("x-anyscene-key") || "";
  if (ADMIN_KEY && same(got, ADMIN_KEY)) return "admin";
  if (DEV_OPEN || same(got, ACCESS_KEY)) return "user";
  return null;
}

export function keyError(req: Request) {
  if (!ACCESS_KEY) return "The AnyScene proxy is closed: ANYSCENE_ACCESS_KEY is not set on the server.";
  return req.headers.get("x-anyscene-key") ? "That password isn't right." : "This AnyScene needs the password.";
}

const RESERVED = /^(admin|administrator|owner|root|anyscene)$/;

export interface Owner {
  email: string;
  name: string;
  /** What a build is tagged with: "Name <email>". */
  tag: string;
}

/** Who the request says it is (x-anyscene-user: an email or a username; x-anyscene-name optional), or an error to show. */
export function owner(req: Request, role: "admin" | "user" | null = null): Owner | { error: string } {
  const email = (req.headers.get("x-anyscene-user") || "").trim().toLowerCase();
  let name = "";
  try {
    name = decodeURIComponent(req.headers.get("x-anyscene-name") || "");
  } catch {
    /* a malformed name is just left out */
  }
  name = name.replace(/[<>\p{Cc}]/gu, "").trim().slice(0, 60);
  if (!email) return { error: "Tell AnyScene who you are (email or username) before starting a build." };
  if (email.includes("@")) {
    if (!/^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(email) || email.length > 120) return { error: `"${email}" is not an email address.` };
    if (OWNER_DOMAIN && !email.endsWith(`@${OWNER_DOMAIN}`)) return { error: `Builds here are for @${OWNER_DOMAIN} addresses.` };
  } else if (!/^[a-z0-9._-]{2,40}$/.test(email)) {
    return { error: "A username is 2 to 40 letters, digits, dots, dashes or underscores." };
  }
  // The label is self-declared, so names that would pass for the owner need the admin password.
  if (role !== "admin" && RESERVED.test(email.split("@")[0])) return { error: `"${email}" is reserved for the owner. Pick another name.` };
  return { email, name, tag: name ? `${name} <${email}>` : email };
}

export function clientIp(req: Request) {
  return (req.headers.get("x-forwarded-for") || "").split(",")[0].trim() || req.headers.get("x-real-ip") || "unknown";
}

// ---------------------------------------------------------------- per-IP, per hour
const jobs = new Map<string, number[]>();

/** Counts a new job for this IP; true when it is over the hourly limit (and then not counted). */
export function ipLimited(ip: string) {
  const now = Date.now();
  const recent = (jobs.get(ip) || []).filter((t) => now - t < 3600_000);
  const over = recent.length >= JOBS_PER_HOUR;
  if (!over) recent.push(now);
  jobs.set(ip, recent);
  return over;
}

// ---------------------------------------------------------------- per person, per UTC day
const BLOB = !!process.env.BLOB_READ_WRITE_TOKEN;
const memBuilds = new Map<string, number>();
const day = () => new Date().toISOString().slice(0, 10);
const prefix = (email: string) => `quota/${day()}/${createHash("sha256").update(email).digest("hex").slice(0, 24)}/`;

export async function buildsToday(email: string): Promise<number> {
  if (!BLOB) return memBuilds.get(prefix(email)) ?? 0;
  const r = await list({ prefix: prefix(email), limit: 1000 });
  return r.blobs.length;
}

export async function recordBuild(email: string, requestId: string) {
  if (!BLOB) {
    memBuilds.set(prefix(email), (memBuilds.get(prefix(email)) ?? 0) + 1);
    return;
  }
  await put(`${prefix(email)}${Date.now()}-${requestId || "job"}.json`, JSON.stringify({ email, requestId, at: new Date().toISOString() }), {
    access: "private",
    contentType: "application/json",
    addRandomSuffix: true,
  });
}

export function quotaMessage() {
  return `That's ${BUILDS_PER_DAY} builds today for you, the daily limit (it resets at 00:00 UTC). Ask the owner if you need more.`;
}
