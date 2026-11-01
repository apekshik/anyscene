# How the good scenes got good

Four scenes (a Tokyo repair shop, a ramen shop, a Hong Kong dai pai dong, a 1970s mission control) were built by
agents with `SKILL.md`. What separated the good results from the first drafts was never a model or a setting. It was
this loop, run many times:

1. **Render it and look.** After every change, render the views that matter (small and fast while working) and open the
   images. Look for what's wrong the way a production designer would.
2. **Name the problem precisely.** "The CRT faces are flat grey", not "the screens look off".
3. **Write the fix as code in the scene's scripts**, specific to this scene, so a rebuild keeps it. Every scene grew its
   own `screens.py`, `fixes.py`, `dress.py`, `lights.py`, `validate.py`, written because the agent saw something wrong.
4. **Check the fix from a view that shows it.** A wide shot hides a floating chair; a camera 30 cm off the floor shows
   it at once.
5. **Get an outside opinion.** The agent that built a scene stops seeing its flaws. An independent critic, comparing
   it with the reference, catches what you've stopped seeing.

## What the reference scenes had to fix by hand (expect the same)

**Props**
- Generate every prop with both 3D models and pick by looking at same-light renders, including clay. The best model
  differs per prop (small printed items vs big hard-surface heroes).
- Generators bake glass opaque, fake screens into the texture, invent depth for boxy things, and put real brands on
  labels. Expect to fix all four on most scenes.
- Scale every prop to its real-world size; set the origin bottom-centre; face it the way it will be placed.

**Screens, signs, labels**
- Screens are a hero detail. Make them emissive with real content in one invented world (one fictional organisation,
  consistent across every screen, sign and label), at the screen's real aspect ratio. Never tile an image containing
  text; never stretch one image across a wall of differently sized panels.
- A CRT is curved: a flat patch on a domed tube leaves a hole. Fit the screen geometry to the tube.
- Signage text should be exact. Use real text objects or images made for that one sign.

**Placement**
- Drop everything onto its support with raycasts from the object's lowest vertices, starting below anything overhead.
  Re-drop after anything moves. Check for floaters, intersections and props resting on the wrong thing.
- Density sells realism more than size. Real places are small and full.

**Materials**
- Nothing should stay untextured or flat grey. Scripted architecture needs real materials (paint, laminate, tile,
  acoustic panels, wood) and wear: AO-driven dirt, edge wear, per-instance tint so copies don't read as copies.
- Glass needs real transmission; mask it so that opaque parts of the same prop (labels, contents) stay opaque.

**Light**
- Light the way the real place would be lit: the practicals first (fixtures, screens, signs, windows), fills last and
  weak. Fills that are too strong flatten the mood instantly.
- Emissive detail (indicator lamps, button glows) should glow without becoming hundreds of light sources: turn off
  emission sampling on dense emissive meshes. Too many weak lights make noise and denoiser blotches.
- Re-check exposure after each new practical.

**Atmosphere and finish**
- Haze is cheap and worth it. Overlapping volumes are what get expensive.
- Grade in post (lifted blacks, a colour split, a vignette, grain). The raw render is never the deliverable.
- Windows need something behind them at the right scale and distance.

**Process**
- Never trust that a script that ran did the right thing. Every important claim gets an image.
- Keep `NOTES.md`: one line per thing that cost you time.
- Generation is slow and parallel: start it early, in bulk, and build the room, the screens and the lights while it runs.
