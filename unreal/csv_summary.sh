#!/usr/bin/env bash
# Summarise an Unreal CSV profile: mean / p50 / p95 of frame, game, render, RHI and GPU time plus the top GPU passes.
#   bash csv_summary.sh <Profile(...).csv> [skip_first_frames=60]
f="$1"; skip="${2:-60}"
awk -F, -v skip="$skip" '
NR==1 { for (i=1;i<=NF;i++) col[$i]=i; next }
$1 ~ /^\[/ || NF < 10 { next }
{ n++; if (n<=skip) next; m++
  for (k in col) if (k=="FrameTime"||k=="GameThreadTime"||k=="RenderThreadTime"||k=="RHIThreadTime"||k=="GPUTime"||k ~ /^GPU\//) { v=$(col[k])+0; s[k]+=v; a[k,m]=v } }
END {
  printf "frames=%d (after skipping %d)\n", m, skip
  split("FrameTime GameThreadTime RenderThreadTime RHIThreadTime GPUTime", ks, " ")
  for (j=1;j<=5;j++) { k=ks[j]; c=0; for (i=1;i<=m;i++) t[++c]=a[k,i]; asort(t); printf "%-17s mean %6.2f ms  p50 %6.2f  p95 %6.2f\n", k, s[k]/m, t[int(c*0.5)], t[int(c*0.95)]; delete t }
  printf "fps(mean frame)  %.1f\n", 1000/(s["FrameTime"]/m)
  for (k in s) if (k ~ /^GPU\//) printf "%8.3f %s\n", s[k]/m, k | "sort -rn | head -12"
}' "$f"
