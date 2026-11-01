"use client";

import { useMemo } from "react";
import { assetKey, type RunState } from "@/lib/run";
import type { Plan } from "@/lib/types";

/** The plan drawn top-down, entrance at the bottom; generated footprints fill in as their props arrive. */
export default function LiveMap({
  plan,
  run,
  selected,
  onSelect,
}: {
  plan: Plan;
  run: RunState;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const { width: W, depth: D } = plan.room;
  const pad = Math.max(W, D) * 0.06;
  const Y = (y: number) => D - y;
  const meshesDone = run.stages.generating_meshes?.status === "done" || run.status === "done";

  const objects = useMemo(
    () => [...plan.objects].sort((a, b) => b.w * b.d - a.w * a.d), // big ones underneath
    [plan.objects],
  );

  const stateOf = (o: Plan["objects"][0]) => {
    if (!o.generate) return "fixed";
    const p = run.props[assetKey(o)];
    if (!p) return run.kind ? "waiting" : "planned";
    if (p.status === "failed") return "failed";
    if (p.mesh_url) return "meshed";
    return meshesDone ? "standin" : "ref";
  };

  const cam = plan.reference_camera;
  const camAngle = cam ? Math.atan2(cam.look_at[1] - cam.position[1], cam.look_at[0] - cam.position[0]) : 0;
  const fov = cam ? 2 * Math.atan(18 / cam.lens_mm) : 0.8;
  const reach = Math.max(W, D) * 0.22;

  return (
    <div className="livemap">
      <svg viewBox={`${-pad} ${-pad} ${W + pad * 2} ${D + pad * 2}`} preserveAspectRatio="xMidYMid meet" role="img" aria-label="Prop map">
        <defs>
          <pattern id="grid" width="1" height="1" patternUnits="userSpaceOnUse">
            <path d="M1 0H0V1" fill="none" stroke="var(--map-grid)" strokeWidth="0.012" />
          </pattern>
          <pattern id="hatch" width="0.18" height="0.18" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="0.18" stroke="#1f1d1a" strokeWidth="0.03" />
          </pattern>
        </defs>
        <rect x={0} y={0} width={W} height={D} fill="url(#grid)" />
        <rect x={0} y={0} width={W} height={D} className="map-wall" />
        {plan.openings.map((op, i) => {
          const half = op.width / 2;
          const [x1, y1, x2, y2] =
            op.wall === "front"
              ? [op.center - half, 0, op.center + half, 0]
              : op.wall === "back"
                ? [op.center - half, D, op.center + half, D]
                : op.wall === "left"
                  ? [0, op.center - half, 0, op.center + half]
                  : [W, op.center - half, W, op.center + half];
          return <line key={i} x1={x1} y1={Y(y1)} x2={x2} y2={Y(y2)} className={`map-opening ${op.kind}`} />;
        })}
        {objects.map((o) => {
          const st = stateOf(o);
          const key = assetKey(o);
          return (
            <g
              key={o.id}
              transform={`translate(${o.x} ${Y(o.y)}) rotate(${-o.rot})`}
              className={`fp ${st} ${o.source} ${selected === key ? "sel" : ""}`}
              onClick={() => o.generate && run.props[key]?.mesh_url && onSelect(key)}
            >
              <title>{`${o.label}${o.source === "invented" ? " (invented)" : ""}`}</title>
              <rect x={-o.w / 2} y={-o.d / 2} width={Math.max(o.w, 0.04)} height={Math.max(o.d, 0.04)} rx={Math.min(o.w, o.d) * 0.08} />
            </g>
          );
        })}
        {plan.lights.map((l) => (
          <circle key={l.id} cx={l.x} cy={Y(l.y)} r={Math.max(W, D) * 0.006} fill={l.color} className="map-light" />
        ))}
        {cam && (
          <g className="map-cam" transform={`translate(${cam.position[0]} ${Y(cam.position[1])})`}>
            <path
              d={`M0 0 L${Math.cos(camAngle - fov / 2) * reach} ${-Math.sin(camAngle - fov / 2) * reach} L${Math.cos(camAngle + fov / 2) * reach} ${-Math.sin(camAngle + fov / 2) * reach} Z`}
            />
            <circle r={Math.max(W, D) * 0.008} />
          </g>
        )}
      </svg>
      <div className="map-legend">
        <span className="lg meshed">Mesh in</span>
        <span className="lg ref">Reference ready</span>
        <span className="lg waiting">Waiting</span>
        <span className="lg standin">Stand-in</span>
        <span className="lg failed">Failed</span>
        <span className="lg fixed">Built from the plan</span>
      </div>
    </div>
  );
}
