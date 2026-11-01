"use client";

import { useEffect, useRef, useState } from "react";
import type { PropTile, RunState } from "@/lib/run";
import type { Plan } from "@/lib/types";
import { SPRITE_FRAMES, turntableSprite } from "@/lib/three-util";
import { modelName } from "./Viewer3D";

interface Props {
  run: RunState;
  plan: Plan | null;
  selected: string | null;
  onSelect: (id: string) => void;
}

export default function PropShelf({ run, plan, selected, onSelect }: Props) {
  const scroller = useRef<HTMLDivElement>(null);
  const tiles = run.propOrder.map((id) => run.props[id]);
  const meshed = tiles.filter((t) => t.mesh_url).length;
  const failed = tiles.filter((t) => t.status === "failed").length;
  const total = run.totalProps ?? 0;
  const ghosts = Math.max(0, total - tiles.length);
  const meshPhaseOver = run.stages.generating_meshes?.status === "done" || run.status === "done";
  const finalStandins = run.status === "done";
  const generated = plan ? plan.objects.filter((o) => o.generate).length : 0;

  // keep the newest arrival in view
  const n = tiles.length;
  useEffect(() => {
    const el = scroller.current;
    if (el && n) el.scrollTo({ left: el.scrollWidth, behavior: "smooth" });
  }, [n]);

  return (
    <div className="shelf">
      <div className="shelf-head">
        <h3 className="sheet-h shelf-title">Prop manifest</h3>
        {run.kind ? (
          <span className="shelf-count">
            <b>{meshed}</b> of {total || "…"} meshed
            {run.totalPlacements ? <span className="muted">, placed {run.totalPlacements} times</span> : null}
            {failed ? <span className="bad">, {failed} failed</span> : null}
          </span>
        ) : (
          <span className="shelf-count muted">
            {plan ? `${generated} objects will be generated. Approve the plan to start.` : "Every generated prop appears here during the build."}
          </span>
        )}
      </div>
      <div className="shelf-row" ref={scroller}>
        {tiles.map((t, i) => (
          <Tile
            key={t.id}
            no={i + 1}
            tile={t}
            selected={selected === t.id}
            onSelect={onSelect}
            standin={!t.mesh_url && t.status !== "failed" && meshPhaseOver}
            final={finalStandins}
          />
        ))}
        {Array.from({ length: ghosts }).map((_, i) => (
          <div className="tile ghost" key={`g${i}`} aria-hidden>
            <div className="tile-media" />
            <div className="tile-label" />
            <div className="tile-tag">
              <span className="no">P-{String(tiles.length + i + 1).padStart(3, "0")}</span>
              <span className="tag">CALLED</span>
            </div>
          </div>
        ))}
        {!run.kind && (
          <div className="shelf-empty">
            {Array.from({ length: 7 }).map((_, i) => (
              <div className="tile ghost" key={i} style={{ opacity: 1 - i * 0.13 }} aria-hidden>
                <div className="tile-media" />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Tile({ no, tile, selected, onSelect, standin, final }: { no: number; tile: PropTile; selected: boolean; onSelect: (id: string) => void; standin: boolean; final: boolean }) {
  const [sprite, setSprite] = useState<string | null>(null);
  const [spriteErr, setSpriteErr] = useState(false);
  useEffect(() => {
    if (!tile.mesh_url) return;
    let live = true;
    turntableSprite(tile.mesh_url)
      .then((u) => live && setSprite(u))
      .catch(() => live && setSpriteErr(true));
    return () => {
      live = false;
    };
  }, [tile.mesh_url]);

  const state = tile.status === "failed" ? "failed" : tile.mesh_url ? (sprite ? "spinning" : "loading") : standin ? "standin" : "meshing";
  const clickable = !!tile.mesh_url;
  const tag =
    state === "failed" ? "FAILED" : state === "standin" ? "STAND-IN" : tile.mesh_url ? modelName(tile.model).toUpperCase() || "IN" : "IN SHOP";
  return (
    <button
      className={`tile ${state} ${selected ? "sel" : ""}`}
      onClick={() => clickable && onSelect(tile.id)}
      disabled={!clickable}
      title={tile.label + (state === "standin" && !final ? " (stand-in until its mesh lands)" : "")}
      aria-label={`P-${String(no).padStart(3, "0")} ${tile.label}: ${tag}`}
    >
      <div className="tile-media">
        {tile.ref_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img className="tile-ref" src={tile.ref_url} alt="" loading="lazy" />
        ) : (
          <span className="tile-initial">{tile.label.slice(0, 1)}</span>
        )}
        {sprite && (
          <div
            className="tile-sprite"
            style={{ backgroundImage: `url(${sprite})`, ["--frames" as string]: SPRITE_FRAMES } as React.CSSProperties}
          />
        )}
        {state === "meshing" && <span className="tile-spin" aria-hidden />}
        {state === "loading" && !spriteErr && <span className="tile-spin small" aria-hidden />}
      </div>
      <div className="tile-label">{tile.label}</div>
      <div className="tile-tag">
        <span className="no">P-{String(no).padStart(3, "0")}</span>
        <span className={`tag ${state}`}>{tag}</span>
      </div>
    </button>
  );
}
