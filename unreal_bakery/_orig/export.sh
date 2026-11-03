#!/usr/bin/env bash
# export_blend.py through the GPU queue, resumed until it finishes. Blender 5.0.1 Cycles bake crashes intermittently
# (EXCEPTION_ACCESS_VIOLATION in OpenImageIO ustring::operator= under ccl::create_mesh, ~1 per 250 bakes, a different
# asset each time); the exporter skips assets whose GLB/texture already exist, so a rerun resumes where it died.
#   bash unreal/export.sh <copy.blend> <out_dir> [export_blend.py args...]     (log: <out_dir>/export.log)
#   EXPORT_TRIES=6 EXPORT_PRE="scenes/<id>/scripts/gpu_prefs.py"
A="$(cd "$(dirname "$0")/.." && pwd)"
. "$A/pipeline/env.sh"
blend="$1"; out="$2"; shift 2
mkdir -p "$out"
: > "$out/export.log"
pre=()
[ -n "$EXPORT_PRE" ] && pre=(--python "$EXPORT_PRE")
for i in $(seq 1 "${EXPORT_TRIES:-6}"); do
  bash "$A/pipeline/gpu_run.sh" "$BLENDER" -b "$blend" "${pre[@]}" --python "$A/unreal/export_blend.py" -- --out "$out" "$@" \
    >> "$out/export.log" 2>&1
  rc=$?
  if grep -q "^EXPORT wrote" "$out/export.log"; then echo "export: done after $i run(s)"; exit 0; fi
  # rc 0 without "wrote" is a Python exception (Blender exits 0 on those): retrying will not help.
  [ "$rc" = 0 ] && { echo "export: python error, see $out/export.log"; exit 1; }
  echo "export: run $i exited rc=$rc without finishing; resuming" | tee -a "$out/export.log"
done
echo "export: gave up after ${EXPORT_TRIES:-6} runs"; exit 1
