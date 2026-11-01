"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Studio from "./Studio";
import BuilderStudio from "./BuilderStudio";
import Gallery from "./Gallery";

/** Picks the product: the agent builder (default) or the older plan + build pipeline.
 *  ?mode=pipeline forces the pipeline; a replay picks whichever kind its recording is; ?view=gallery shows everyone's
 *  builds (a card opens one in the builder view as ?open=<id>). */
export default function Shell() {
  const params = useSearchParams();
  const mode = params.get("mode");
  const replay = params.get("replay");
  const [kind, setKind] = useState<"builder" | "pipeline" | null>(mode === "pipeline" ? "pipeline" : !replay ? "builder" : null);

  useEffect(() => {
    if (mode === "pipeline") return setKind("pipeline");
    if (!replay) return setKind("builder");
    let live = true;
    fetch(`/replay/${encodeURIComponent(replay)}/manifest.json`)
      .then((r) => (r.ok ? r.json() : null))
      .then((m) => live && setKind(m?.kind === "pipeline" ? "pipeline" : "builder"))
      .catch(() => live && setKind("builder"));
    return () => {
      live = false;
    };
  }, [mode, replay]);

  if (params.get("view") === "gallery") return <Gallery />;
  if (!kind) return null;
  return kind === "pipeline" ? <Studio /> : <BuilderStudio />;
}
