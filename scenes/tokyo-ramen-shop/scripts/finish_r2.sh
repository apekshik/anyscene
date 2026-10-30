#!/usr/bin/env bash
# After finals_gen.sh: confine rain away from the lens, re-render the establishing shot, publish the .blend,
# and always raise the repair agent's GPU go-signal on exit.
cd "$(dirname "$0")/../../.."
. pipeline/env.sh
trap 'touch .gpu.ramen_done; echo "SIGNAL .gpu.ramen_done"' EXIT

until grep -q ALLDONE logs/ramen_finals_gen.log; do sleep 30; done
"$B" -b scenes/tokyo-ramen-shop/ramen_r2.blend --python-expr "
import bpy
em = bpy.data.objects['rain_emitter']
ps = em.particle_systems[0].settings
bb = [em.matrix_world @ __import__('mathutils').Vector(c) for c in em.bound_box]
y0, y1 = min(p.y for p in bb), max(p.y for p in bb)
# keep the far edge at the facade (y1), pull the near edge in to y = -2.2
k = (y1 + 2.2) / (y1 - y0)
em.scale.y *= k; em.location.y = y1 - (y1 - y0) * k / 2 - 0 if False else em.location.y
bpy.context.view_layer.update()
bb = [em.matrix_world @ __import__('mathutils').Vector(c) for c in em.bound_box]
em.location.y += y1 - max(p.y for p in bb)
ps.count = int(ps.count * k)
bpy.ops.wm.save_mainfile(); bpy.context.view_layer.update()
bb = [em.matrix_world @ __import__('mathutils').Vector(c) for c in em.bound_box]
print('RAIN y', round(min(p.y for p in bb), 2), round(max(p.y for p in bb), 2), ps.count)" 2>&1 | grep -E "RAIN|Error|Traceback"
rm -rf scenes/tokyo-ramen-shop/out/shots/exterior_establish/frames
SHOTS="exterior_establish:120" bash scenes/tokyo-ramen-shop/scripts/shots_r2.sh
cp scenes/tokyo-ramen-shop/ramen_r2.blend scenes/tokyo-ramen-shop/ramen.blend && echo "PUBLISHED ramen.blend"
echo FINISHED_R2
