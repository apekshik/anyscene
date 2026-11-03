import { BUILDS_PER_DAY, DEV_OPEN, OWNER_DOMAIN, buildsToday, keyError, keyRole, owner } from "@/lib/guard";

// The page's check before a build: is the access key right, who does the server take you for, and how many builds
// are left today. Same headers as the fal proxy (x-anyscene-key, x-anyscene-user, x-anyscene-name).
export async function GET(req: Request) {
  const role = keyRole(req);
  if (!role) return Response.json({ detail: keyError(req) }, { status: 401 });
  const who = owner(req, role);
  const base = { admin: role === "admin", open: DEV_OPEN, limit: BUILDS_PER_DAY, domain: OWNER_DOMAIN || null };
  if ("error" in who) return Response.json({ ...base, owner: null, error: who.error, used: 0 });
  const used = await buildsToday(who.email).catch(() => 0);
  return Response.json({ ...base, owner: who.tag, error: null, used });
}
