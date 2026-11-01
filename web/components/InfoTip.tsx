"use client";

import { useId, useState } from "react";

/** A small ⓘ next to a label: hover, focus or tap shows what the thing is. */
export default function InfoTip({ text, label }: { text: string; label: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span className="infotip" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <span
        role="button"
        tabIndex={0}
        className="infotip-i"
        aria-label={`What is ${label}?`}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onClick={(e) => {
          // focus already opened it; a click or tap only ever opens (blur, mouse-out or Escape closes)
          e.stopPropagation();
          setOpen(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            e.stopPropagation();
            setOpen((o) => !o);
          }
          if (e.key === "Escape") setOpen(false);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      >
        i
      </span>
      {open && (
        <span role="tooltip" id={id} className="infotip-box">
          {text}
        </span>
      )}
    </span>
  );
}

/** What each part of the builder page is, in one place so the wording stays consistent. */
export const HELP = {
  live: "The newest image the builder made or looked at, as it works. Click a thumbnail in the strip to hold one.",
  compare: "Your reference image next to the builder's render from the same camera angle. Drag the divider to compare.",
  previews: "Scouting shots of the finished set: every area and hero material, at different lenses and heights. Pick any of them to order as a still or a video.",
  contact: "Every image the builder produced during the build, in order: tests, layouts, critic rounds, finals. Its working notebook.",
  stills: "The finished, graded stills the critic judged, plus the downloads: package, scene.blend, glTF, and what the build cost.",
  "360": "Look around the finished set: 360° panoramas rendered with the scene's real lighting, or the scene model you can fly through.",
  schedule: "The build's milestones in order. ROLLING is the one in progress, WRAPPED ones show how long they took.",
  log: "Every step the builder takes: commands it runs, files it writes, images it looks at, and its own notes.",
  critic: "An independent reviewer that scores the stills on 8 lines out of 10: is this a good production base in your reference's world? It doesn't mark down angles or lighting for differing from the reference. The build keeps improving until it passes (none under 6, average 7+), for at most 8 rounds.",
  dials: "Settings the builder must follow, like time of day or wear. Leave one on AUTO and the builder reads it from your reference.",
  effort: "How hard Claude thinks at each step. Medium is the default; higher is slower and costs more.",
  shots: "Order finished stills or video clips of this scene: pick scouting previews or describe new shots in words.",
} as const;
