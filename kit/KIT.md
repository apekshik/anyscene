# What makes a kit good

A kit is judged as a set. One beautiful item and one off-style item is a failed kit; eight solid items that all look
like the same world is a good one. These are the things that decide it, and what the scene builds learned about the
generators (see also `CRAFT.md`).

## Cohesion comes from the references, not the 3D models

- Tripo and Meshy copy the reference image. If the references don't match each other, nothing later will fix it.
  Generate every item reference with the customer's style image as an input image (`kit/gen.mjs edit`), with one
  shared style paragraph (era, palette, materials, wear, fictional maker) pasted into every prompt.
- Check the references together, on one sheet, before any 3D: same camera, same light, same level of wear, same
  palette. Regenerate the outliers. This is the cheapest place to fix cohesion.
- The style reference is often a whole scene. Its items are a guide to the world, not a list to copy unless the
  customer asked for exactly those things.

## The generators (from ~150 props in the scene builds)

- Meshy 7.1 wins about 70% of the time: small consumer items, sharper printed labels. Its front faces -Y.
- Tripo H3.1 wins big hard-surface heroes where real geometry matters (knobs, bezels, dents). Its front faces +X,
  and with `orientation: align_image` its glTF node also carries a +-20-30 deg Z rotation that matches the reference
  photo's three-quarter view: drop it before turning the mesh (`normalize.py` and `compare.py` do). Raw it is ~2M
  tris: generate with `--face-limit` (150000 heroes, 60000 small items).
- Both bake glass opaque, fake screens into the texture, invent depth for boxy things and put real brands on labels.
  Expect all four. Meshy speckles flat panels: look at the clay render, not just the beauty.
- References come back with real brands even when told not to. Check every one.

## Scale

- Every item gets a real height (or dims for boxy things) before prep. Look up typical sizes rather than guessing:
  a desk phone is ~0.12 m tall, a coffee mug ~0.095 m, a ring binder ~0.32 m, a desk lamp ~0.45 m.
- Check scale in the lineup: items side by side must make sense relative to each other and to the scale bar.

## Prep

- Orientation: decide from the probe or compare renders which way each model faces; `normalize.py --yaw` fixes
  anything that isn't front -Y after the generator's rotation.
- glTF imports use quaternion rotation; images arrive packed, and calling `pack()` on an unmodified packed image drops
  its data (magenta render). Only repack images you changed.
- Glass: give the glass part a real transmissive material (mask by UV island or by material) and keep labels opaque.
- Brands: repaint the brand's texels (fill with the label's ground colour plus grain) and flatten the same texels in
  the normal map, or regenerate the item with a fictional brand.

## Presentation

- The lineup is the kit's cover. Items sorted for a readable silhouette rhythm, a scale bar, labels legible, nothing
  cut off, light that shows the materials. Thumbnails: three-quarter front, filling the frame.
- Look at every render you make. A script that ran proves nothing.
