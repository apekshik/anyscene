"use client";

import { useState } from "react";
import { clock, MILESTONE_LABELS, type BuilderResponse, type BuilderState } from "@/lib/builder";
import Fade from "./Fade";
import Compare from "./Compare";
import Pano360 from "./Pano360";
import SceneView from "./SceneView";
import BuilderResult from "./BuilderResult";
import InfoTip, { HELP } from "./InfoTip";
import Lightbox, { type LightboxItem } from "./Lightbox";

export type BTab = "live" | "compare" | "previews" | "contact" | "stills" | "360";

interface Props {
  tab: BTab;
  onTab: (t: BTab) => void;
  follow: boolean;
  onFollow: () => void;
  run: BuilderState;
  res: BuilderResponse | null;
  referenceUrl: string;
  now: number;
  passed?: boolean;
}

const stageName = (s: string) => MILESTONE_LABELS[s] ?? (s === "critique" ? "Critic" : s.replace(/_/g, " "));

export default function BuilderViewport(p: Props) {
  const { tab, run, res } = p;
  const [pinned, setPinned] = useState<string | null>(null);
  const [view360, setView360] = useState(0);
  const [box, setBox] = useState<{ items: LightboxItem[]; index: number } | null>(null);

  const previews = run.previews;
  const latest = previews[previews.length - 1];
  const shown = (pinned && previews.find((x) => x.url === pinned)) || latest;
  const stills = res?.stills ?? [];
  // the critic's first image is the reference-angle still; that is what to hold against the plate
  const lastCritic = [...previews].reverse().find((x) => x.stage === "critique");
  const compareRender = stills[0] ?? lastCritic?.url ?? latest?.url;
  // the scouting previews: named ones from the finished build, else every frame reported as a preview so far
  const scouting: { url: string; label: string }[] = res?.previews?.length
    ? res.previews.map((x) => ({ url: x.url, label: x.name.replace(/_/g, " ") }))
    : previews.filter((x) => x.stage === "previews").map((x) => ({ url: x.url, label: x.message || "preview" }));
  const panoramas = res?.panorama_urls ?? [];
  const sceneGlb = res?.scene_glb_url ?? null;
  const has360 = panoramas.length > 0 || !!sceneGlb;
  const v360 = view360 >= 0 && view360 < panoramas.length ? view360 : sceneGlb ? -1 : 0;

  const tabs: { id: BTab; label: string; ready: boolean; show: boolean }[] = [
    { id: "live", label: "Live", ready: !!latest, show: true },
    { id: "compare", label: "Compare", ready: !!(p.referenceUrl && compareRender), show: true },
    { id: "previews", label: `Previews${scouting.length ? ` (${scouting.length})` : ""}`, ready: scouting.length > 0, show: true },
    { id: "contact", label: "Contact sheet", ready: previews.length > 1, show: true },
    { id: "stills", label: "Stills", ready: !!res, show: !!res },
    { id: "360", label: "360", ready: has360, show: has360 },
  ];

  const title =
    tab === "live"
      ? `Camera A · ${shown ? stageName(shown.stage) : "standing by"}${pinned ? " · held frame" : " · live"}`
      : tab === "compare"
        ? "Plate vs camera A · reference angle"
        : tab === "previews"
          ? `Scouting previews · ${scouting.length}`
          : tab === "contact"
          ? `Contact sheet · ${previews.length} frames`
          : tab === "stills"
            ? "Dailies"
            : v360 >= 0
              ? `Camera B · 360 plate · ${v360 === 0 ? "reference angle" : `spot ${v360 + 1}`}`
              : "Set model · glTF · free camera";

  const last = run.critiques[run.critiques.length - 1];
  const tools = run.lines.filter((l) => l.kind === "tool").length;
  const note =
    run.status === "idle"
      ? ""
      : run.criticBusy
        ? `critic reviewing round ${run.critiques.length + 1}`
        : last
          ? `round ${last.round}: ${last.passed ? "passed" : "not yet"}`
          : `${tools} tool calls`;

  return (
    <div className="viewport">
      {box && <Lightbox items={box.items} index={box.index} onIndex={(index) => setBox({ ...box, index })} onClose={() => setBox(null)} />}
      <h3 className="sheet-h frame-title">{title}</h3>
      <div className="vp-tabs" role="tablist">
        {tabs
          .filter((t) => t.show)
          .map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              className={`vp-tab ${tab === t.id ? "on" : ""} ${t.ready ? "ready" : ""}`}
              onClick={() => p.onTab(t.id)}
            >
              {t.label}
              <InfoTip label={t.label} text={HELP[t.id]} />
            </button>
          ))}
        <span className="vp-spacer" />
        {tab === "360" && has360 && (
          <div className="seg small" role="group" aria-label="360 viewpoint">
            {panoramas.map((u, i) => (
              <button key={u} className={v360 === i ? "on" : ""} onClick={() => setView360(i)}>
                {i === 0 ? "Ref angle" : `Spot ${i + 1}`}
              </button>
            ))}
            {sceneGlb && (
              <button className={v360 === -1 ? "on" : ""} onClick={() => setView360(-1)}>
                Set model
              </button>
            )}
          </div>
        )}
        {tab === "live" && pinned && (
          <button className="text-btn" onClick={() => setPinned(null)}>
            Back to live
          </button>
        )}
        <button className={`follow ${p.follow ? "on" : ""}`} onClick={p.onFollow} title="Switch views as new results arrive">
          <span className="follow-dot" aria-hidden /> Follow
        </button>
      </div>

      <div className="vp-stage">
        {note && tab !== "stills" && tab !== "360" && <span className="frame-note">{note}</span>}
        {tab === "live" &&
          (shown ? (
            <div className="live-frame">
              <button
                className="live-open"
                aria-label="Open full screen"
                onClick={() =>
                  setBox({
                    items: previews.map((y) => ({
                      url: y.url,
                      caption: `${clock(y.t)} ${stageName(y.stage)}${y.message ? `: ${y.message}` : ""}`,
                    })),
                    index: Math.max(0, previews.findIndex((y) => y.url === shown.url)),
                  })
                }
              >
                <Fade src={shown.url} alt={shown.message || shown.stage} />
              </button>
              <span className="live-tag">
                {clock(shown.t)} {stageName(shown.stage)}
                {shown.message ? `: ${shown.message}` : ""}
              </span>
              {previews.length > 1 && (
                <div className="strip" aria-label="Recent frames">
                  {previews.slice(-14).map((x) => (
                    <button
                      key={x.url}
                      className={x.url === shown.url ? "on" : ""}
                      onClick={() => setPinned(x.url === latest.url ? null : x.url)}
                      title={`${clock(x.t)} ${stageName(x.stage)}`}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={x.url} alt="" loading="lazy" />
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <Empty running={run.status === "running"} text="Each image the builder reports, from the layout to the finals, lands here." />
          ))}
        {tab === "compare" &&
          (p.referenceUrl && compareRender ? (
            <Compare left={p.referenceUrl} right={compareRender} rightLabel={stills[0] ? "Final" : lastCritic ? `Round ${run.critiques.length}` : "Latest"} />
          ) : (
            <Empty running={run.status === "running"} text="Hold the plate against the reference-angle render once there is one." />
          ))}
        {tab === "previews" &&
          (scouting.length ? (
            <div className="contact scouting">
              {scouting.map((x, i) => (
                <figure key={x.url}>
                  <button
                    onClick={() => setBox({ items: scouting.map((y) => ({ url: y.url, caption: y.label })), index: i })}
                    aria-label={`Preview ${i + 1}: ${x.label}`}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={x.url} alt="" loading="lazy" />
                  </button>
                  <figcaption title={x.label}>
                    <b>{String(i + 1).padStart(2, "0")}</b> {x.label}
                  </figcaption>
                </figure>
              ))}
            </div>
          ) : (
            <Empty running={run.status === "running"} text="The builder scouts the finished set at the end: every zone, every hero material, wides and details. They land here." />
          ))}
        {tab === "contact" &&
          (previews.length ? (
            <div className="contact">
              {previews.map((x, i) => (
                <figure key={x.url}>
                  <button
                    onClick={() =>
                      setBox({
                        items: previews.map((y) => ({
                          url: y.url,
                          caption: `${clock(y.t)} ${stageName(y.stage)}${y.message ? `: ${y.message}` : ""}`,
                        })),
                        index: i,
                      })
                    }
                    aria-label={`Frame ${i + 1}: ${stageName(x.stage)}`}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={x.url} alt="" loading="lazy" />
                  </button>
                  <figcaption>
                    <b>{String(i + 1).padStart(2, "0")}</b> {clock(x.t)} {stageName(x.stage)}
                  </figcaption>
                </figure>
              ))}
            </div>
          ) : (
            <Empty running={run.status === "running"} text="Every reported frame, in order." />
          ))}
        {tab === "stills" && res && (
          <BuilderResult res={res} run={run} onOpen={(i) => setBox({ items: res.stills.map((u, k) => ({ url: u, caption: `Still ${k + 1}` })), index: i })} />
        )}
        {tab === "360" &&
          has360 &&
          (v360 >= 0 && panoramas[v360] ? <Pano360 url={panoramas[v360]} /> : sceneGlb ? <SceneView url={sceneGlb} envUrl={panoramas[0]} /> : null)}
      </div>

      <div className="caption" aria-live="polite">
        <span className="caption-text" key={run.working?.what || run.thought || run.status}>
          {run.status === "idle"
            ? "Drop a reference and build. One agent builds the scene and loops with a critic until it passes."
            : run.status === "failed"
              ? run.error
              : run.status === "ended"
                ? "The recording stops here: the run was still going when it was copied."
              : run.status === "done"
                ? p.passed === false
                  ? "Wrapped without a pass: the critic stopped improving. The stills and package are below."
                  : "Wrapped. The critic passed it; stills, 360 and the package are in."
                : run.working
                  ? `Running: ${run.working.what} (${clock(Math.max(0, p.now - run.working.since))})`
                  : run.thought || "The builder is starting."}
        </span>
        <span className="caption-time">{run.status === "idle" ? "" : clock(p.now)}</span>
      </div>
    </div>
  );
}

function Empty({ running, text }: { running: boolean; text: string }) {
  return (
    <div className="empty">
      {running && <span className="empty-pulse" />}
      <p>{text}</p>
    </div>
  );
}
