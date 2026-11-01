# AnyShot: an AI cinematographer for 3D scenes

AnyShot turns a 3D scene and plain-language shot directions into finished stills and camera moves. It is not a
render farm with a prompt box: a Claude agent works the set the way a DP would. It reads the scene, works out what
is where, turns "slow push along the counter, rack focus to the register" into a real camera move with a lens, an
ease and a focus pull, checks every frame of the move for clearance against walls and furniture, blocks each shot
with quick previews and fixes what reads wrong from the new angle, then renders and grades the finals.

- **`/scene2image`**: finished, graded stills, rendered with Cycles on the agent's own GPU.
- **`/scene2video`**: camera moves as mp4s. The agent plans and checks the moves; the frames are rendered on a render
  farm app (`farm/app.py`) across up to 100 GPUs at once, then graded and encoded.

Direct it shot by shot (`shots`), or just brief it in words (`prompt`: "a 40-second piece: open wide, walk in like a
visitor, then three close dolly reveals with rack focus") and the agent plans the shot list itself.

The scene comes in one of two ways:
- `scene_url`: a `.blend`, or a `.zip` holding a `.blend` and its textures, uploaded anywhere (fal storage, S3,
  a signed link). The agent unpacks it, finds the main `.blend`, repairs texture paths, packs a self-contained copy
  and works only on that copy. It keeps the scene's own look.
- `build_id`: an [AnyScene](../README.md) build (`/ref2scene`) on the same fal account's storage. The agent also gets
  the builder's notes and scouting cameras, so shots can be asked for by name.

Optionally, `floor_plan_url` is an image of the set's plan, with or without a camera path drawn on it. The agent
registers the plan to the scene and places cameras from it, following a drawn path as a walkthrough.

Each order is retry-safe: an identical request (same scene, shots, settings) returns the finished result, attaches to
the attempt still running, or resumes a dead one where it stopped, without re-rendering frames already on disk.

## How it works

```
request ─▶ AnyShotApp (fal, 1 GPU)                                     farm/app.py (fal, up to 100 GPUs)
           ├ fetch the scene (or open the AnyScene build)
           ├ Claude agent (builder/shots.py, builder/SHOTS.md)
           │   read the set · plan cameras (camera/camrig.py)
           │   clearance check every frame · block with Eevee previews
           │   stills: Cycles finals on this GPU, ffmpeg grade
           │   video:  farm_render ────────────────────────────────▶  frame chunks, one Blender per request
           │           grade + encode mp4 ◀─────────────────────────  frames zip on fal storage
           └ stills / videos / result.json ─▶ response
```

The code is shared with the AnyScene scene builder rather than copied. `anyshot/app.py` imports `builder/shots.py`
(the `ShotsDirector` agent and its `farm_render` tool), `builder/scene_builder.py` (the agent harness: hooks, stage
events, session resume) and `endpoint/planner.py`, and ships them with `local_python_modules`. The agent's workspace
gets `camera/` (the camrig shot rig), `pipeline/` and `SHOTS.md` (its instructions) at deploy time. The scene
builder's own `/scene2image` and `/scene2video` routes run the same code.

## Deploy your own

You need a fal account with Serverless access and an [OpenRouter](https://openrouter.ai) or Anthropic API key.

1. **Secrets.** fal secrets are shared by every app on the account, so set each once:

   ```bash
   fal secrets set OPENROUTER_API_KEY=...     # Claude through OpenRouter (or ANTHROPIC_API_KEY=... for the Anthropic API)
   fal secrets set FAL_KEY=...                # a fal key of this account: uploads, and the farm calls
   fal secrets set FAL_SERVERLESS_KEY=...     # optional: the key the farm is called with (defaults to FAL_KEY)
   fal secrets set ANYSHOT_FARM_APP=<your-fal-username>/blender-farm
   ```

   With both OPENROUTER_API_KEY and ANTHROPIC_API_KEY set, OpenRouter is used. Optional: `FARM_WORKERS` (default
   100) caps how many farm requests run at once; keep it at or under the farm's `max_concurrency` and your
   account's concurrency limit.

2. **The render farm** (for `/scene2video`):

   ```bash
   fal deploy farm/app.py::BlenderFarm --app-name blender-farm --auth private
   ```

   Without `ANYSHOT_FARM_APP` (or if the farm is down), `/scene2video` still works: the agent renders the frames on
   its own GPU in chunks, which is slower.

   How the farm is set up, and why:
   - **RTX 5090 workers** (`machine_type` in `farm/app.py`): $2.50/h against $4.00/h for an RTX PRO 6000, with about
     10% fewer cores. Switch to `GPU-RTXPRO6000` for sets that need more than 32 GB of VRAM.
   - **Chunks of at least 24 frames** (`FARM_MIN_CHUNK`, a secret/env on the AnyShot app). Every chunk pays a worker
     boot, the scene download and Blender setting up the set; at 5 frames a chunk that overhead was about 75% of the
     bill.
   - **Each worker downloads the scene to its own disk** from the bundle's CDN URL. Don't point workers at one shared
     copy on `/data`: when 42 workers read the same 1.6 GB set at once, each waited about 30 minutes before its first
     frame, against 18 seconds to download its own copy.
   - **Shared OptiX kernel cache** on `/data/anyscene-farm/optix/<gpu>/` (a small file, read once at boot). OptiX
     compiles its kernels on a worker's first Cycles render, about 2 minutes; each worker starts from the shared cache,
     warms it in `setup()` and saves it back when it grows.
   - **`keep_alive = 300`** so a burst of orders reuses booted workers.

   Measured on a 1.6 GB set (458 objects, 8.6M triangles, 118 textures) at 1920x804 and 160 samples: 42 chunks of 8
   frames on 42 RTX 5090s, all done in 3 minutes, about 102 s of Blender per chunk (17 s to the first frame, then
   about 11 s a frame). A 20-second walkthrough at 1920x804 and 256 samples cost about $9 of farm time.

3. **AnyShot:**

   ```bash
   fal deploy anyshot/app.py::AnyShotApp --app-name anyshot --auth private
   ```

   Deploy from the repository root: the app pulls in `builder/`, `endpoint/` and `camera/`. Requirements are listed
   on the app class (`fal==1.84.0`, `claude-agent-sdk==0.2.176`, `anthropic`, `pydantic`, `pillow`, `fal-client`);
   the deploying Python needs the same packages, e.g.
   `uv run --python 3.13 --with fal==1.84.0 --with pydantic --with anthropic --with pillow --with fal-client --with claude-agent-sdk==0.2.176 fal deploy ...`.
   The worker image installs Blender 5.0.1, ffmpeg and node. `request_timeout` is 7200 s (fal's cap): the agent
   stops itself at 110 minutes to deliver what it has, and a retried request resumes the order.

4. **Optional, AnyScene:** `/ref2scene` on the scene builder (`builder/app.py`) takes a `shots` order and hands the
   finished build to AnyShot. Set `ANYSHOT_APP=<your-fal-username>/anyshot` so it calls your deployment.

Storage: AnyShot keeps uploaded scenes and its retry index under `/data/anyshot/`, and reads AnyScene builds from
`/data/anyscene/builder/`, on the account's persistent `/data` volume. Each order's working files (blocking
previews, frames, the packed copy) live in `out/shots/<job_id>/` inside the scene's workspace.

## API

Both routes take the same body and return the same response.

| field | type | |
|---|---|---|
| `scene_url` | string | A `.blend`, or a `.zip` with a `.blend` and its textures. Give this **or** `build_id`. |
| `build_id` | string | An AnyScene build (`b_...`) on the same account. |
| `prompt` | string | Direction for the whole order in your own words ("a 45 s trailer: open wide, walk in like a visitor, then slow dolly reveals with rack focus; moody"). On its own, the agent plans the shot list; with `shots`, it applies to all of them. Give `prompt`, `shots`, or both. |
| `shots` | list | Optional. Each `{"name": ..., "description": ...}`; either or both. A name picks an existing camera (an AnyScene scouting camera, or a camera in the `.blend`) and names the output file. |
| `floor_plan_url` | string | Optional plan image, optionally with a camera path or camera marks drawn on it. |
| `settings` | object | Optional: `res` `[w, h]`, `samples`, `fps`, `seconds` (per video shot), `lens_mm`, `handheld` (`none` / `walk` / `subtle`), `look` (`clean` / `cinematic` / `gritty` / `vintage`). Missing ones are chosen per shot. |
| `dials` | object | Optional changes to the set for this order only (`time_of_day`, `atmosphere`, `power`, `warmth`, `wetness`, ...). The source scene is never changed. |
| `effort` | string | Claude effort: `low`, `medium` (default), `high`, `xhigh`, `max`. |
| `fresh` | bool | Shoot again even if an identical order already finished. |

Response: `job_id`, `scene_id`, `stills` (URLs), `videos` (URLs), `result` (per shot: camera, lens, move, settings
and a note), `missing` (anything not delivered), `agent_cost_usd`, `minutes`.

The agent streams its progress as `ANYSCENE_STAGE {json}` lines in the request's logs (`stage`, `message`, and a
`preview_url` for blocking frames and finals). An order takes minutes for a couple of stills and longer for video
(blocking, the farm, grading); use the queue, not a synchronous call.

### curl

```bash
# 1. upload the scene (any URL works; this uses fal storage via the client below, or your own bucket)
# 2. submit
curl -s https://queue.fal.run/<your-fal-username>/anyshot/scene2video \
  -H "Authorization: Key $FAL_KEY" -H "Content-Type: application/json" \
  -d '{
        "scene_url": "https://example.com/my_set.zip",
        "shots": [
          {"name": "counter_push", "description": "slow push along the counter at eye level, ending close on the register; rack focus from the jar in the foreground to the register"},
          {"description": "walk in through the door and turn to reveal the back room, handheld walk, 24mm"}
        ],
        "settings": {"seconds": 6, "fps": 24, "res": [1920, 1080]}
      }'
# -> {"request_id": "...", "status_url": ".../requests/<id>/status", "response_url": ".../requests/<id>"}

curl -s "https://queue.fal.run/<your-fal-username>/anyshot/requests/<id>/status?logs=1" -H "Authorization: Key $FAL_KEY"
curl -s "https://queue.fal.run/<your-fal-username>/anyshot/requests/<id>" -H "Authorization: Key $FAL_KEY"
```

### Python

```python
import fal_client  # FAL_KEY in the environment

scene = fal_client.upload_file("my_set.zip")
res = fal_client.subscribe(
    "<your-fal-username>/anyshot/scene2image",
    arguments={
        "scene_url": scene,
        "shots": [{"description": "wide establishing shot from the doorway, eye level, 24mm"},
                  {"description": "tight 85mm detail of the teapot on the counter, shallow focus"}],
        "settings": {"res": [1920, 1080]},
    },
    with_logs=True,
    on_queue_update=lambda u: [print(l["message"]) for l in getattr(u, "logs", None) or []],
)
print(res["stills"])
```

### Command line

`anyshot/client.py` uploads local files, prints the agent's live log and downloads the results:

```bash
export FAL_KEY=... ANYSHOT_APP=<your-fal-username>/anyshot
python anyshot/client.py image --scene my_set.blend --shot "wide from the doorway, 24mm" --shot "hero: tight on the teapot, f/1.8"
python anyshot/client.py video --scene my_set.zip --floor-plan plan_with_path.png \
    --shot "follow the drawn path at walking pace" --settings '{"seconds": 8}'
python anyshot/client.py video --build-id b_1234567890 --shot hero_wide --shot "orbit the bar, 35mm"
```

`--shot` takes a camera name, words, or `name: words` for both. Results land in `--out` (default `anyshot_out/`):
`response.json`, `events.jsonl`, and the stills and videos.

## Shot grammar

Describe shots the way you would to a camera crew. The agent maps the words onto the camrig moves
(`camera/README.md`) and checks each against the set:

| say | the agent does |
|---|---|
| push in, dolly in, pull out, track along X | a dolly move on 2+ keys; "slow" is about 0.2-0.4 m/s |
| truck, crab, slide past X | sideways move |
| crane up, jib, rise, pedestal down | vertical move, aim held or reframed |
| pan, tilt, whip pan to X | same position, the aim moves |
| orbit, arc, circle around X | an orbit on X's centre, with a radius and an angle range |
| reveal X | starts on a foreground element or behind an occluder and moves until X comes into view and frames it |
| rack focus / pull focus from A to B | a hold on A, then a focus pull to B, with a shallow f-stop so it reads |
| walkthrough, follow the path, Steadicam | a smooth path at walking pace and eye height; `handheld: walk` adds an operator's step and sway |
| dolly zoom, vertigo | the lens is solved per frame to hold the subject's size |
| locked off, tripod | a static camera; `subtle` handheld for life |
| wide / normal / tight, 24mm, 85mm | 18-24 mm / 35-50 mm / 85-135 mm, or the exact focal length |
| low angle, eye level, top down, over the shoulder of X | camera height and aim |
| "a 6 second push" | the shot's length (wins over `settings.seconds`) |

Objects are found by name in the scene, so naming them helps ("the teapot", "the red stool"); the agent also looks
at the set to find what you mean. A drawn path on a `floor_plan_url` becomes a walkthrough along it, and camera marks
(an X, a camera icon, a cone of view) become camera positions.

Every move is checked so the camera never passes within 0.45 m of a wall, furniture or a prop (dust, haze and glass
the move is meant to pass don't count). A path through an obstacle goes around it, and the result says so.

## Files

- `anyshot/app.py`: the fal app (`AnyShotApp`): request handling, scene fetching, retry index.
- `anyshot/client.py`: the CLI.
- `builder/shots.py`: `ShotsDirector` (the agent), `farm_render`, scene fetching and the shared `shoot()` runner.
- `builder/SHOTS.md`: the agent's instructions.
- `builder/scene_builder.py`: the agent harness shared with the scene builder.
- `camera/`: camrig (moves, focus, handheld) and `shoot.py` (previews, framing, finals).
- `farm/app.py`: the render farm.
