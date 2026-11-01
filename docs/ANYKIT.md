# AnyKit

`kit/app.py`, deployed on fal Serverless as `<your-fal-username>/anykit` (private). One request = one Claude agent (Opus 5.5 via OpenRouter, fast mode, effort
`medium` by default) on a GPU worker that builds a **kit**: a set of static 3D props in one style, at real-world
scale, from 1-4 style reference images. Part of the AnyAll family: AnyScene builds scenes, AnyKit builds the props
that go in them.

It is agent-driven, not a fixed pipeline. The agent plans the kit, generates a style-conditioned reference per item
(GPT Image 2.5 edit with the customer's images as input), sends every reference to Tripo H3.1 and Meshy 7.1, compares
them under the same light, picks, normalises, fixes by script what looks wrong, renders a lineup and thumbnails, and
loops with an independent critic until it passes. Code: `kit/` (`app.py`, `kit_builder.py`, `PROMPT.md`, `KIT.md`,
`gen.mjs`, `tools/`). It reuses the scene builder's session, hooks, heartbeat, cap guard and container
(`builder/scene_builder.py`, `builder/app.py`).

```
POST /kit     style references (+ prompt, items, dials)  ->  kit (per-item GLB + LOD1 + thumbnail), kit.blend, lineup
POST /smoke   {"reference_image_urls": []}               ->  container, agent and critic check
```

Both run on the fal queue (`https://queue.fal.run/<your-fal-username>/anykit/kit`). A kit takes roughly 40-110 minutes; the request
is capped at 2 hours (the agent is stopped at 110 minutes and whatever is in `out/` is packaged).

```
export ANYKIT_APP=<your-fal-username>/anykit   # or pass --app
uv run --python 3.13 --with fal-client python kit/client.py kit ref.png --prompt "1970s mission-control desk clutter" \
    --dial count=9 --dial wear=0.4 --out kit_out
```

## Request

```jsonc
{
  "reference_image_urls": ["https://..."],   // 1-4 style references (required); more than 4 are ignored
  "prompt": "1970s mission-control desk clutter, 8-10 items",   // optional
  "items": ["rotary desk phone", "ashtray"], // optional: built exactly, in this order
  "dials": { "count": 9, "wear": 0.4 },      // optional, see below
  "effort": "medium"                         // agent effort: low | medium | high | xhigh | max
}
```

### Dials

Plain settings the agent builds to. A dial that is set is an instruction, even when the reference says otherwise. A
dial left out gets ONE value read from the references and prompt. There are no variants and no switchable rigs. The
values used come back in the response's `dials`, each with its `source`.

| Dial | Range | Controls |
|---|---|---|
| `count` | integer | how many items (default: the item list's length, else the prompt, else 8) |
| `variety` | 0 - 1 | 0 = variations of one object family (matching mugs, jars); 1 = a broad mix that only shares the style |
| `detail` | `low` \| `medium` \| `high` | per-item budget: low <= 20k tris, 1K textures; medium <= 100k, 2K; high <= 200k, 2K. LOD1 is ~1/4 the tris, half-size textures |
| `wear` | 0 pristine - 1 decayed | dirt, scratches, chips, fading |
| `wetness` | 0 dry - 1 soaked | water on surfaces |
| `warmth` | -1 cold - 1 warm | palette colour temperature and the presentation light |
| `look` | `clean` \| `cinematic` \| `gritty` \| `vintage` | surface finish and the presentation renders' grade |

## Response

```jsonc
{
  "kit_id": "k_3f9a1c2b7d",
  "name": "Apollo-era flight desk",
  "style": "one paragraph: era, palette, materials, wear, fictional maker",
  "items": [
    {
      "id": "rotary_phone",
      "label": "Rotary desk phone",
      "dims_m": [0.22, 0.24, 0.13],        // width x (X), depth y (Y), height z (Z), metres
      "tris": 98000, "tris_lod1": 24500,
      "generator": "meshy",                // meshy | tripo-h31 (the pick)
      "why": "sharper dial numerals; Tripo fused the handset to the cradle",
      "glb_url": "https://...",            // LOD0: metres, bottom-centre origin, front faces -Y, textures <= 2K
      "lod1_url": "https://...",
      "thumb_url": "https://...",          // 1024 px, three-quarter front
      "turntable_url": null                // mp4, when the agent made one
    }
  ],
  "lineup_url": "https://...",             // 2400 x 1000: every item on a neutral ground, labels, scale bar
  "kit_blend_url": "https://...",          // asset library: every item marked as an asset, LOD1s in a hidden collection
  "kit_json_url": "https://...",           // out/kit.json (the items above + tags and the fixes made per item)
  "package_url": "https://...",            // zip: out/ (GLBs, renders, kit.blend, kit.json, dials.json, critique/),
                                           //      scenes/kit/ (the agent's scripts, NOTES.md), refs/kit/ (item references)
  "critiques": [
    { "round": 1, "passed": false, "summary": "...", "fixes": ["..."],
      "scores": { "cohesion": 7, "reference_fidelity": 8, "brief": 8, "mesh_quality": 6,
                  "texture_quality": 7, "assembly": 7, "scale": 8, "labels": 6 } }
  ],
  "dials": { "wear": { "value": 0.4, "source": "customer", "means": "scuffed bakelite, worn paint on edges" } },
  "missing": [],                           // deliverables not produced (empty when complete)
  "agent_cost_usd": 18.2,                  // Claude agent (OpenRouter)
  "generation_cost_usd": 31.5,             // fal generation, estimated from the spend log
  "minutes": 64.3
}
```

The kit passes when no critic score is below 6 and the average is 7 or more: a production-ready base a studio's
artists then refine, judged at normal viewing distance, with the reference setting the world rather than designs to
copy. The critic lists at most five fixes, only ones that would stop a studio using the kit. `assembly` checks that parts that belong together are connected
and seated (cords plugged in at both ends, handsets on cradles, lamp heads on arms, lids on hinges). The critic gets at
most 8 rounds (`MAX_CRITIC_ROUNDS`, shared with the scene builder); after the 8th the kit is delivered as it stands. The critic sees the style references, the lineup, up to 10
thumbnails and each item's dims. A kit stopped at the time cap or after three critic rounds without improvement is
still returned, with the last critique and `missing` saying what is short.

## Events

Same transport and format as the scene builder, so `web/lib/builder.ts` can consume them unchanged. The worker prints
one line per event, `ANYSCENE_STAGE {json}`, and the fal queue relays them as logs (`with_logs=true` on status or
subscribe). Every event:

```jsonc
{ "t": 312.4,            // seconds since the build started
  "stage": "references", // see below
  "status": "running",   // running | done | failed
  "message": "one plain sentence",
  "preview_url": "https://..."  // optional image
  /* + stage-specific fields */ }
```

| Stage | Kind | Meaning / extra fields |
|---|---|---|
| `received` | system | first event; message `build k_<id>: kit from N style reference(s)`; `reference_urls`, `prompt`, `items`, `dials`, `effort` |
| `log` | tool | one per agent tool call (`tool`: Bash, Read, Write...); `preview_url` when the agent opened an image |
| `thinking` | note | the agent's own words |
| `heartbeat` | status | every 20 s: `working`, `working_s`, `critique_rounds`, `milestones` (every milestone so far, for late attach) |
| `critique` | critic | `status: running` without `critique` = the critic is looking; with `critique` = a round's result (`round`, `scores`, `passed`, `summary`, `fixes`, `stills`) |
| `error` | system | a harness error being resumed, or the time cap; `status: failed` when the build stopped |
| `done` | system | the agent finished; `missing`, `critiques` |
| `packaged` | system | last event; `package_url`, `lineup_url` |
| anything else | milestone | reported by the agent with its best current image: normally `plan`, `references`, `models`, `picks`, `prep`, `fixes`, `lineup`, `finals`, `done`, in that order, with retakes allowed |

The milestone names are the agent's choice within that list; treat any unknown stage as a milestone (as
`builder.ts` does). The `received` message uses the word `build` so the existing `/build (b_\w+)/`-style id parse can
be widened to `/build ([bk]_\w+)/`.
