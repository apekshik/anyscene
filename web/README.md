# AnyScene web

The showcase UI for AnyScene. The default product is the agent builder (`builder/`, e.g. the public `apek/anyscene`): drop a reference
image and one request builds the whole scene on a fal GPU worker (up to fal's 2 h cap), with a Claude agent looping
against an independent critic. The UI shows the agent's production log, its milestones as a schedule, the newest
render live, the critic's score sheet round by round, and the result (stills, 360, package, cost). The older
plan + build pipeline (`endpoint/`) is still there at `?mode=pipeline`. Styled as a film call sheet.

Next.js (App Router, TypeScript), three.js, `@fal-ai/client` in the browser through `@fal-ai/server-proxy` on the
server. The fal key never reaches the browser.

## Run

```
npm install
cp .env.example .env.local   # then fill in FAL_KEY and the app ids
npm run env:local     # (Windows) writes FAL_KEY into .env.local from the user env var FAL_SERVERLESS_KEY (never printed)
npm run dev           # http://localhost:3210
```

The fal apps come from `NEXT_PUBLIC_*` variables in `.env.local`, as `<your-fal-username>/<app>` (see `.env.example`):
`NEXT_PUBLIC_ANYSCENE_APP` (the builder), `NEXT_PUBLIC_ANYKIT_APP` (AnyKit, for the kit gallery), and optionally
`NEXT_PUBLIC_ANYSCENE_PIPELINE_APP` (the older pipeline; defaults to the builder's id) and
`NEXT_PUBLIC_ANYSCENE_TEST_APP` (a second builder the gallery shows with `?gallery_app=<id>`). There are no defaults:
a live call to an unset app fails with a message naming the variable. `DEV_ORIGINS` (comma-separated) adds LAN hosts
allowed to open the dev server.

`npm run dev` and `npm run build` first copy `fixtures/` into `public/replay/` (`npm run fixtures`).

## Builder (default)

- Live: **Build the scene** uploads the reference to fal storage and calls `<NEXT_PUBLIC_ANYSCENE_APP>/ref2scene` with
  `{reference_image_urls, prompt, effort, scene: "scene"}`. Stage events come from the queue logs (prefix
  `ANYSCENE_STAGE `, polled every 2 s, deduped by message).
- Schedule: the milestones the agent reports (plan, props, layout, dressing, screens, materials, lighting, atmosphere,
  cameras, finals, plus any it invents), with ROLLING on the current one, WRAPPED and a duration once it moves on, and
  "take 2" when it returns to one after a critique. Then the critic's state and the package.
- Production log (bottom): every `log` event (tool label and what it did), the agent's `thinking` notes, milestones
  with a thumbnail, critic lines; filter by notes, tools or milestones. The caption under the frame is the agent's
  latest note.
- Frame: Live (newest `preview_url`, with a strip of recent frames you can hold), Compare (the plate against the
  critic's reference-angle still, then the first final), Contact sheet (every reported frame), Stills and 360 after
  the wrap.
- Critic's report (right): the eight scores per round side by side with the change from the round before, lines under
  7 marked, the verdict stamp, the summary and the ranked fixes; earlier rounds' fixes fold away.
- Result: stills, package, scene.blend and scene.glb, agent cost, minutes, critic rounds, anything `missing`.

### Builder replay

`/?replay=builder` plays `fixtures/builder/` (`events.jsonl` timed by each event's own `t`, `build.json` as the
response); speeds 1x to 64x in the toolbar, `&auto=1` starts it. That fixture is **synthetic**
(`npm run fixture:builder`): it follows the real schema, reuses the pipeline run's images, and its package link is
the earlier pipeline package. To drop in a real run:

```
npm run import:builder -- <run dir>                                               # -> fixtures/builder/
npm run import:builder -- <run dir> fal_mc_1                                            # or keep both: ?replay=fal_mc_1
```

It copies `events.jsonl`, `build.json` and any `still_*.png` (served locally in place of the remote stills), plus a
reference image. A run without `build.json` yet replays up to its last event and stops there.

## Password, who's building, and limits

The proxy checks a shared password, verified on the server: set `ANYSCENE_ACCESS_KEY` in the server environment and every proxied request must
carry it as `x-anyscene-key`. With the variable unset the proxy is open in `next dev` and **closed** in production,
so a fresh deployment can't start builds on the account. `ANYSCENE_ADMIN_KEY`, given in place of the password, also
skips the limits below.

The page asks once for the password and an email or username (**Sign in** in the toolbar; kept in that browser's
localStorage) and sends them to our own proxy only (`x-anyscene-key`, `x-anyscene-user`, `x-anyscene-name`). The proxy
tags each `/ref2scene` build with `owner` (the email or username) (stored by `builder/app.py`, listed by `/builds`, left out of
the retry fingerprint), so the gallery's **My builds** shows your own and **Everyone** shows all. A build's page is
shareable as `/?open=<build id>` (**Copy link**). It is self-declared behind the shared password: a label, not
authentication (see Google sign-in below).

Limits, all server only:

| variable | default | |
|---|---|---|
| `ANYSCENE_BUILDS_PER_DAY` | 3 | builds per email per UTC day; counted in a private Vercel Blob store when `BLOB_READ_WRITE_TOKEN` is set (else in memory) |
| `ANYSCENE_JOBS_PER_HOUR` | 6 | new jobs (builds and shots) per IP per hour, in memory per instance: a backstop |
| `ANYSCENE_OWNER_DOMAIN` | none | only emails at this domain may build, e.g. `fal.ai` (usernames are always allowed) |

The build button notes the cost (about $60-100 a build) and what's left today, and asks before starting.
`app/api/me` answers the page's "is my key right, who am I, what's left" check.

### Google sign-in (later)

To replace the self-declared name with real accounts restricted to one Google Workspace domain:

1. Google Cloud console, the owner's project: **APIs & Services > OAuth consent screen**, user type **Internal** (only
   the Workspace's accounts can sign in). Then **Credentials > Create credentials > OAuth client ID**, type **Web
   application**, authorized redirect URI `https://studio.anyscene.org/api/auth/callback/google` (and
   `http://localhost:3210/api/auth/callback/google` for dev).
2. `npm install next-auth@5` and add `auth.ts` with the Google provider, `authorization: { params: { hd: "fal.ai" } }`,
   and a `signIn` callback that returns `profile.email_verified && profile.email.endsWith("@fal.ai")` (`hd` alone is
   only a hint); export `handlers` from `app/api/auth/[...nextauth]/route.ts`.
3. Vercel env: `AUTH_SECRET` (`npx auth secret`), `AUTH_GOOGLE_ID`, `AUTH_GOOGLE_SECRET`, `AUTH_TRUST_HOST=true`.
4. In `lib/guard.ts`, take the owner from `await auth()` (session email and name) instead of the `x-anyscene-*`
   headers, and treat a session as the access key (keep `ANYSCENE_ADMIN_KEY` for the owner). In the page, replace the
   sign-in card with `signIn("google")`.

## Replay mode (pipeline)

`/?replay=demo` plays the recorded pipeline run in `fixtures/` with its original timing. Click **Plan the scene**, then
**Approve and build**.

| param | |
|---|---|
| `replay=<name>` | `demo` is `fixtures/` itself; any subfolder `fixtures/<name>/` is another recording |
| `speed=<n>` | 1 (real time) to 64; also switchable in the toolbar (1x to 16x) |
| `auto=1` | plans on load and approves the build 3.5 s after the plan lands, for hands-off screen recordings |

A recording is: `plan_events.jsonl` and `build_events.jsonl` (one `{"t": seconds, ...stage event}` per line, as written
by `endpoint/client.py --events`), `plan.json`, `build.json` (the BuildResponse), `reference.png`, `floor_plan.png`,
`blockout_reference.png`, `blockout_overview.png`, `comparison.png` and `still_*.png`. Recorded `preview_url`s that
match a local file (floor plan, comparison, stills in `build.json` order) are served locally; the rest (layout and
dressing previews, prop references, GLBs) still load from fal's CDN. Without `build_events.jsonl` the replay
synthesizes a build from `plan.json`. The last two lines of `fixtures/plan_events.jsonl` are marked `"synthetic"`:
the recorded plan run lost its final events when the client crashed, so `blockout done` and `done` were added.

## Live mode

Without `?replay`, **Plan the scene** uploads the reference to fal storage and calls `<pipeline app>/plan` through
`/api/fal/proxy`; **Approve and build** calls `<pipeline app>/build` with the plan id and tier. Stage events are read
from the queue logs (lines prefixed `ANYSCENE_STAGE `, deduped by message). The proxy only forwards to
the configured `NEXT_PUBLIC_*_APP` apps (`<app>/**`) and fal storage uploads, so a deployment's key can't be used for
other endpoints. On Vercel, set `FAL_KEY`, `ANYSCENE_ACCESS_KEY` and the `NEXT_PUBLIC_*_APP` ids in the project
environment.

## 360 and scene lighting (ahead of the endpoint)

The UI already reads these optional fields, from events or the BuildResponse:

| field | where | |
|---|---|---|
| `panorama_url` (+ `viewpoint`) | `rendering` event, one per viewpoint | equirectangular Cycles render, 2:1 |
| `panorama_urls` | BuildResponse | the same, first = reference camera |
| `scene_glb_url` | `packaging` event / BuildResponse | decimated scene glTF with KHR_lights_punctual |
| `environment_url` | any event / BuildResponse | equirect .hdr or PNG of the scene's light for the prop viewer (else the first panorama) |

Until real ones exist, `scripts/make-placeholders.mjs` builds `fixtures/panorama_ref.png`, `panorama_mid.png`
(a ray-cast grey room from `plan.json`) and `fixtures/scene.glb` (the plan as boxes with its lights), and replay
injects them where the endpoint will emit them, labelled "placeholder".

## Screens

- Left: reference plate, direction (prompt, the ten dials, planning effort, build tier), the schedule.
- Centre: the camera-report frame with Floor plan (drawing, or the prop map that fills in as meshes land), Grey-box,
  Live (newest `preview_url`), Compare (slider between the reference and the matching render), 3D (the selected
  prop's GLB at the plan's real size, with dashed bounds and a ground shadow, lit by the scene's environment map once
  there is one, studio light until then), 360 (drag-to-look panoramas per viewpoint, plus the scene glTF as a
  free-orbit set model lit by the reference-camera panorama; hidden unless the build provides them), and Dailies
  after the wrap (stills, timings, package). **Follow** moves the frame to whatever just arrived; picking a
  view turns it off.
- Bottom: the prop manifest, one card per `prop.id`: IN SHOP while meshing, TRIPO or MESHY with a turntable once the
  mesh lands, FAILED, or STAND-IN if it never arrives. Click a card for the 3D view.
- Right: the breakdown (room, setting, counts, lights, palette, dials), notes for a revision, Approve and build.

Prop GLBs are 10-60 MB, so each card's turntable is rendered once into a sprite strip on a shared offscreen renderer
and the model is freed; only the 3D view keeps a live model.

`npm run screenshots` (pipeline) and `npm run screenshots:builder` (builder), with the dev server running, capture the
main states into `screenshots/` with the installed Edge or Chrome.
