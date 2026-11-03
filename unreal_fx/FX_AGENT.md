# FX_AGENT.md: converting any Blender effect to Niagara, by script

The effects layer is generic by construction. Nothing in it is specific to the HK scene. Read `NIAGARA.md` first for
the Unreal and Niagara background. This page covers the loop the converter (and the `/scene2unreal` agent) runs for
any scene.

```
Blender scene ──fx_export.py──▶ scene.json "fx" ──build_level.py (stage fx)──▶ NiagaraActors ──MRQ──▶ compare with Cycles
                  classify + measure          place, set User params,              │
                                              read back, bounds, seed, warm-up     ▼
                                              ◀── overrides.json (tuning, no re-export)
templates.json ◀──fx_pack.py◀── fx_recipes/*.json  (new effect type = new recipe, no code)
```

## 1. The pieces

| File | What it does | Who edits it |
|---|---|---|
| `fx_recipes/NS_*.json` | One Niagara template each: emitters, module rewiring (links, one-line HLSL, enums), extra modules, renderers, and its own sprite materials (HLSL bodies). Ships: Fire, Steam, Smoke, Rain, Drips, DustMotes, Sparks/Embers, FountainJet | humans, or the agent for a new effect type |
| `fx_pack.py` | Builds `/Game/AnySceneFX` headlessly from the recipes through Epic's NiagaraToolsets, then writes `templates.json` (the param types, plus the `fx_types` each template serves) | nobody, per scene |
| `fx_export.py` | Blender side. Classifies volume shaders and particle systems by evidence: emission, drivers, albedo, velocity, gravity, lifetime, names. It measures the effect (baked density and emission slices: base, lean, reach, ring radius, optical depth; driver scroll speed; particle rate, speed, size; ground ray cast) and writes the `fx` entries | rules only |
| `build_level.py` `stage_fx` | Places a `NiagaraActor` per entry and sets the asset, then the typed params, then reads every param back (invalid = error). Also sets fixed bounds, the seed and the warm-up, and keys sampled light flicker into the camera sequences | nobody |
| `overrides.json` (`ANYSCENE_FX_OVERRIDES`) | `{fx_id or "type:<type>": {Param: value}}` applied on top of `scene.json`. This is the look-match knob, and it is reproducible | the agent |

## 2. The agent loop for a new scene

1. Run `fx_export.py`. Every entry gets `type`, `confidence`, `evidence`, the measured `physical` block and
   `params`.
2. **`technique: "agent"`** means no template serves that `type`, or the object was unclassifiable (`unknown`).
   Read its `evidence`, `physical` and `source.objects`, and look at the object in Blender (its node tree and
   modifiers). Then:
   - **An existing template fits** (a lava bubble is a slow orange `NS_Steam`; a waterfall mist is `NS_Steam` with
     a white albedo): set `technique: "niagara"`, `template`, and `params` in `overrides.json`, or patch the entry.
   - **Nothing fits** (falling leaves, snow, bubbles, fireflies, ribbons of a trail): write
     `fx_recipes/NS_<Name>.json`. Copy the closest recipe and change:
     - `fx_types`: the classifier types the template serves (add a type word to `TYPE_WORDS` in `fx_export.py` if
       it is new);
     - `common`: real-world defaults (cm, cm/s, s, nits);
     - `emitters[].core`: `gpu`, `material`, `aligned` (velocity-aligned streaks), `nonuniform` (Aspect = length /
       width), `curl`, `grow`, `sort`, `fade`;
     - `emitters[].inputs`: `[script, module, input, value]`, where `value` is a number, a bool,
       `{"link": "User.X", "type": "float"}`, `{"hlsl": "..."}` or `{"enum": "Display Name"}`. Hidden inputs need
       their parent switch set first: the tool refuses them and says so;
     - `emitters[].add_modules`: `{"asset": "/Niagara/Modules/...", "script": ..., "before": "SolveForcesAndVelocity",
       "inputs": {...}}`;
     - `emitters[].set_params`: `[script, "Particles.X", type, hlsl, before?]`;
     - `materials`: `{"M_AFX_<Name>": {"blend": "ADDITIVE|TRANSLUCENT", "lit": bool, "rgb": hlsl, "base": hlsl,
       "op": hlsl, "depth_fade": cm}}`. The HLSL bodies see `UV`, `PC` (particle colour), `PA` (alpha), `R`
       (random), `T` (time), `DP` (x = Intensity, y = Temperature) and the helpers `X.fbm(float2)` and
       `X.bb(kelvin)`.

     Keep the shared User parameter names (NIAGARA.md §3). Add scene-specific ones under `extra`.
3. Build only the new template. This takes about 1 minute, and the other templates stay as they are:
   `ANYSCENEFX_ONLY=NS_<Name> UnrealEditor-Cmd <proj> -run=pythonscript -script=fx_pack.py`.
   Check `templates_report.json`: `issues` must be empty and `compile.bHasErrors` false.
4. Run `build_level.py` with `ANYSCENE_STAGES=fx,sequences`. `build_report.json` → `fx[].params_invalid` must be
   empty.
5. Render MRQ stills and clips of the cameras that see the effect, and compare against Cycles (NIAGARA.md §6). Tune
   **only** through `overrides.json`: change one parameter per round, at most three rounds. If it still does not
   match, change the template or technique (flipbook / SVT, NIAGARA.md §5).

## 3. Rules learned on HK (apply everywhere)

- **Measure what a camera sees.** `fx_export` ray-casts each emitting sample to the scene cameras. On HK the only
  visible flame is the outer tail in the gap between the wok and its collar, about 1% of the volume. Brightness is the
  emission integrated along the view ray, and a grazing ray through a ring of flame is far brighter than one tongue.
- **Debug a dark sprite with a solid material.** Copy the recipe to `work/dbg_recipes/`, set
  `rgb: "return float3(50,0,50) * PA;"`, build with `ANYSCENEFX_RECIPES`, and place it from a scene.json copy. If the
  quads show up, the simulation is fine and the material inputs (PC, DP) are wrong.
- **Measure the visible part of the effect, not the whole volume.** Burner flames are full strength *under* the
  wok, where Cycles hides them too. Spawning there put every sprite inside the pan. `fx_export` now spawns fire on
  the upper half of the emitting band, at the outer edge of the ring.
- **A ring's slice "spread" is its radius, not the tongue width.** Size flame sprites from the flame height.
- **Steam opacity is tiny.** τ ≈ σ·width ≈ 0.05 for HK's woks, and the Cycles plume is barely visible. Don't
  "fix" a faint plume into fog.
- **Rain streaks need the shutter.** Length = drop + speed × shutter / fps. Cycles renders them motion-blurred.
- **Practical lights already exist.** `light_link` takes the brightest light within 1 m. Niagara's own light stays
  at 0, and the sampled `flicker` drives the practical light's intensity in Sequencer instead.
- **Headless gotchas:**
  - `GetStackIssues` asserts without Slate: only run it in a full editor (`ANYSCENEFX_STACK_ISSUES=1`).
  - `AddSetParametersModule` accepts HLSL defaults only for some types. `fx_pack` falls back to a typed default and
    then rewires the input.
  - `DefaultSystem` ships a stock "Fountain" emitter, which `fx_pack` removes.
  - Enum inputs come back as `NewEnumeratorN`: resolve them by display name (`UEnum_Info`).
