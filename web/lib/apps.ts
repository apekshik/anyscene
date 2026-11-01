// The fal apps the UI calls, as <owner>/<app>, from NEXT_PUBLIC_* env vars (web/.env.local; see web/.env.example).
// No defaults: an unset app fails with a message naming the variable instead of calling someone else's app.
// Each process.env.NEXT_PUBLIC_* is written out in full so Next inlines it into the client bundle.

const clean = (v: string | undefined) => (v || "").trim().replace(/^\/+|\/+$/g, "");

/** The scene builder (builder/app.py): /ref2scene, /shots, /builds, /build_events. */
export const BUILDER_APP = clean(process.env.NEXT_PUBLIC_ANYSCENE_APP);
/** The older plan + build pipeline (endpoint/app.py) behind ?mode=pipeline. Falls back to the builder app's id. */
export const PIPELINE_APP = clean(process.env.NEXT_PUBLIC_ANYSCENE_PIPELINE_APP) || BUILDER_APP;
/** AnyKit (kit/app.py): /kits, /kit_events. */
export const KIT_APP = clean(process.env.NEXT_PUBLIC_ANYKIT_APP);
/** Optional second builder deployment (e.g. a private test copy) that ?gallery_app=<id> may point the gallery at. */
export const TEST_APP = clean(process.env.NEXT_PUBLIC_ANYSCENE_TEST_APP);

/** Every app the proxy may forward to (the server-side allowlist is built from this). */
export const ALL_APPS = [...new Set([BUILDER_APP, PIPELINE_APP, KIT_APP, TEST_APP].filter(Boolean))];

const ENV_OF: [string, string, string][] = [
  [BUILDER_APP, "NEXT_PUBLIC_ANYSCENE_APP", "anyscene"],
  [PIPELINE_APP, "NEXT_PUBLIC_ANYSCENE_PIPELINE_APP", "anyscene"],
  [KIT_APP, "NEXT_PUBLIC_ANYKIT_APP", "anykit"],
];

/** The app id, or a clear error naming the env var to set. */
export function requireApp(app: string, which: "builder" | "pipeline" | "kit"): string {
  if (app) return app;
  const [, env, name] = ENV_OF[which === "builder" ? 0 : which === "pipeline" ? 1 : 2];
  throw new Error(`No fal app configured: set ${env}=<your-fal-username>/${name} in web/.env.local and restart the dev server.`);
}
