# reference-to-scene

A fal Serverless app that turns one or more reference images into a lit, dressed Blender scene and returns it as a
package. Two calls, with an optional approval stop between them:

```
POST /plan    reference images (+ optional floor plan, prompt)  ->  plan_id, floor plan, grey-box renders, prop list
POST /plan    plan_id + edit (text or JSON)                     ->  revised plan (repeat as needed)
POST /build   plan_id (or reference images + auto_approve)       ->  package zip + scene.blend + props + renders
```

Both run on the fal queue and stream their progress as stage events (see Progress). The app lives in `endpoint/`;
final renders go to the `blender-farm` app (`farm/app.py`, synced from AnyShot). A third call, `/scene-to-scene`,
changes a built scene's dials (see Dials) and re-renders it.

To shoot a finished build (stills or camera moves described in words), use
[AnyShot](https://github.com/apekshik/anyshot): the builder's `/scene2image` and `/scene2video` forward to it.

## Dials

Ten optional controls, each changing one aspect of the scene and meaningful for any kind of place (a diner, a
forest camp, a spaceship bridge). Unset dials are read from the references and prompt. The plan records the value
each dial resolved to and what it means for this scene, so a caller can see "wear 0.62" and nudge it.

| Group | Dial | Range | Changes (and only this) | Cost to change |
|---|---|---|---|---|
| Stuff | `density` | 0 - 1 | how much is in the space: items per surface and per m² | placement pass + new props |
| | `tidiness` | 0 messy - 1 tidy | how things are arranged, not how many: scattered, tipped, piled vs aligned, stacked, put away | placement pass |
| Surfaces | `wear` | 0 pristine - 1 decayed | age and condition: dirt, scratches, stains, rust, peeling, moss | re-render |
| | `wetness` | 0 dry - 1 soaked | water on surfaces, puddles | re-render |
| Environment | `time_of_day` | dawn, day, dusk, night | sky, sun or moon, daylight through openings | re-render |
| | `weather` | clear, overcast, rain, fog, snow | sky and falling particles | re-render |
| | `atmosphere` | 0 clear - 1 thick | particles in the air: dust, haze, smoke, steam | re-render |
| Energy | `power` | 0 dormant - 1 live | whether the place is switched on: screens, fires, machines, practical lights, steam | re-render |
| Look | `warmth` | -1 cold - +1 warm | colour temperature of the lights and grade | re-render |
| | `look` | clean, cinematic, gritty, vintage | grade, grain, lens effects | re-render |

The dials are independent. Two couplings are defaults only: `weather: rain` raises `wetness` unless it is set, and
`time_of_day: night` lowers ambient light while `power` decides what is lit. "Peak service" is roughly
`density 0.8, tidiness 0.3, power 1`; the same place "after close" is `tidiness 0.9, power 0.15`.

In the plan each dial carries its value and its meaning for this scene:
```jsonc
"dials": {
  "wear":     { "value": 0.65, "means": "grease film on steel, chipped green paint on the cart, soot above the burners" },
  "power":    { "value": 0.9,  "means": "wok burners lit, bare bulbs and neon on, steam from the stock pots" },
  "tidiness": { "value": 0.4,  "means": "stools scattered off-square, newspapers left on tables, crates stacked unevenly" }
}
```

The build agent builds every scene as a rig: one control per dial (a strength input on the shared grime group, a
wetness mask, an atmosphere density, named light and emitter groups for `power`, and so on), recorded in the
package's `dials.json` with an `apply_dials.py` that sets them. `/scene-to-scene` diffs the requested dials against
the scene's: re-render-only dials skip planning and generation; `density` and `tidiness` run a placement pass first.

```jsonc
POST /scene-to-scene
{ "scene_id": "s_…", "dials": { "wetness": 0.0, "time_of_day": "dawn" },   // the dry morning version
  "preview": "wear",           // optional: one still at three values of this dial before committing
  "renders": ["stills"] }      // or the shots too
```

## Coordinates

Metres, Z up. The origin is the floor at the room's front-left corner, seen from the street/entrance:
X runs right along the front wall, Y runs into the room, Z up. Walls are named `front` (y = 0), `back` (y = depth),
`left` (x = 0) and `right` (x = width). A rotation of 0 means the object's front faces -Y (towards the entrance).

## Plan

```jsonc
{
  "plan_id": "p_7f3a2c",
  "name": "hk-dai-pai-dong",
  "summary": "Open-air street-food stall under a tarp awning, late at night after rain",
  "setting": "semi_outdoor",                     // interior | semi_outdoor | exterior
  "time_of_day": "night", "mood": ["humid", "busy", "neon"], "palette": ["#2b3a2f", "#c0392b", "#f5b041"],
  "room": { "width": 6.0, "depth": 8.0, "height": 3.2 },
  "openings": [ { "wall": "front", "kind": "shopfront", "center": 3.0,   // center = X on front/back walls, Y on left/right
                  "width": 5.0, "height": 2.6, "sill": 0.0 } ],
  "objects": [
    { "id": "kitchen_cart", "label": "green steel kitchen cart", "category": "furniture",
      "x": 1.1, "y": 5.5, "z": 0.0, "w": 2.2, "d": 0.8, "h": 1.0, "rot": 90,
      "source": "reference", "generate": true,
      "prompt": "battered green-painted steel street-food kitchen cart with two wok burners",
      "crop": [0.04, 0.18, 0.46, 0.66] }          // where it is in reference image 0, normalised x0,y0,x1,y1
  ],
  "lights": [ { "id": "bulb_1", "kind": "practical", "x": 1.0, "y": 5.0, "z": 2.4, "color": "#ffb46b", "power": "medium" } ],
  "reference_camera": { "position": [3.0, -2.5, 1.6], "look_at": [2.6, 5.0, 1.0], "lens_mm": 28 },
  "notes": ["The area behind the reference camera is invented: a second row of tables and a drinks fridge."]
}
```

Every object and light carries `source`: `reference` (visible in a reference image) or `invented` (added to complete
the space). The floor plan draws invented items dashed, so a reviewer sees at a glance what was extrapolated.

## /plan

Input
| field | type | |
|---|---|---|
| `reference_image_urls` | string[] (1-4) | the look: mood, materials, props |
| `floor_plan_url` | string, optional | a sketch, photo or drawing of the layout; overrides inferred room shape and placement |
| `prompt` | string, optional | anything the images can't show ("rain outside", "it's 1 AM", "make it twice as deep") |
| `plan_id` + `edit` | string + string | revise an existing plan from a text instruction |
| `plan_id` + `plan` | string + object | replace an existing plan with an edited JSON version |

Output
| field | |
|---|---|
| `plan_id` | id for /build or another /plan revision |
| `plan` | the Plan JSON above |
| `floor_plan` | top-down drawing (PNG): walls, openings, every footprint labelled, lights, reference camera |
| `blockout` | grey-box renders (PNG): one from the reference camera, one high three-quarter overview |
| `comparison` | reference and blockout side by side (PNG) |

## /build

Input: `plan_id`, or the /plan inputs plus `auto_approve: true`; `tier` (`draft` | `full`); `num_stills` (default 3);
`walkthrough` (bool); `resolution` (default `[1920, 804]`).

Output: `package` (zip), `scene_blend`, `props` (id, mesh, preview, reference crop, model), `stills`, `walkthrough`,
`manifest`, `timings`, `cost`.

Package layout
```
scene_package.zip
  scene.blend              packed textures, lights, cameras; opens standalone
  props/<id>.glb           cleaned, real-scale, front -Y, bottom-centre origin
  props/<id>_ref.png       the reference each prop was generated from
  renders/still_*.png      Cycles stills, including one from the reference camera
  renders/walkthrough.mp4  handheld walk-through (if requested)
  plan.json, manifest.json props + picks + reasons, lights, shots, costs, timings
  README.md, LICENSE
```

## Progress

Each request streams stage events through the fal queue logs, one JSON object per line prefixed `ANYSCENE_STAGE `:
```json
{"stage": "generating_meshes", "status": "running", "message": "41 of 80 meshes done", "progress": 0.51,
 "preview_url": "https://..."}
```
Stages, in order:
| /plan | /build |
|---|---|
| `received` | `received` |
| `reading_reference` | `prop_references` (crop + clean each prop from the reference) |
| `planning` | `generating_meshes` (all submitted at once) |
| `drawing_floor_plan` | `layout` (shell + stand-ins, runs during mesh generation) |
| `blockout` | `dressing` (meshes swapped in, collision check) |
| `done` | `materials` (textures, grime, decals) |
| | `lighting` (practicals, atmosphere, critic pass vs the reference) |
| | `rendering` (farm: stills + walkthrough) |
| | `packaging` |
| | `done` |

A failed stage emits `"status": "failed"` with a message, and the request fails with the same message.
