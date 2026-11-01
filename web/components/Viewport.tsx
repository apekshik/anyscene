"use client";

import { useEffect, useState } from "react";
import { fmtTime, type RunState } from "@/lib/run";
import { STAGE_LABELS, type BuildResponse, type PlanResponse } from "@/lib/types";
import LiveMap from "./LiveMap";
import Compare from "./Compare";
import Viewer3D from "./Viewer3D";
import Result from "./Result";
import Fade from "./Fade";
import Pano360 from "./Pano360";
import SceneView from "./SceneView";
import { assetKey } from "@/lib/run";

export type TabId = "floor" | "greybox" | "live" | "compare" | "3d" | "360" | "result";

interface Props {
  tab: TabId;
  onTab: (t: TabId) => void;
  follow: boolean;
  onFollow: () => void;
  planRun: RunState;
  buildRun: RunState;
  planRes: PlanResponse | null;
  buildRes: BuildResponse | null;
  referenceUrl: string;
  selected: string | null;
  onSelect: (id: string) => void;
  now: number;
  activeKind: "plan" | "build";
}

export default function Viewport(p: Props) {
  const { tab, planRun, buildRun, planRes, buildRes } = p;
  const run = p.activeKind === "build" ? buildRun : planRun;
  const building = buildRun.kind !== null;
  const [floorMode, setFloorMode] = useState<"drawing" | "map">("drawing");
  const [greyView, setGreyView] = useState<"reference" | "overview">("reference");
  const [view360, setView360] = useState<number>(0); // index into panoramas, or -1 for the set model
  useEffect(() => {
    setFloorMode(building ? "map" : "drawing");
  }, [building]);

  const floorUrl = planRes?.floor_plan_url ?? planRun.previews.find((x) => x.stage === "drawing_floor_plan")?.url;
  const allPreviews = [...planRun.previews, ...buildRun.previews];
  const latest = allPreviews[allPreviews.length - 1];
  const stills = buildRes?.stills ?? buildRun.previews.filter((x) => x.stage === "rendering").map((x) => x.url);
  const compareRender = stills[0] ?? planRes?.blockout_reference_url;
  const sel = p.selected ? buildRun.props[p.selected] : null;
  // 360: panoramas and the scene glTF from events, or from the response
  const panoramas = buildRun.panoramas.length
    ? buildRun.panoramas
    : (buildRes?.panorama_urls ?? []).map((url, i) => ({ url, label: i === 0 ? "reference camera" : `viewpoint ${i + 1}` }));
  const sceneGlb = buildRun.sceneGlbUrl ?? buildRes?.scene_glb_url;
  const has360 = panoramas.length > 0 || !!sceneGlb;
  const refPano = panoramas[0]?.url;
  // scene lighting for the prop viewer: an explicit environment map, else the reference-camera panorama
  const envUrl = buildRun.envUrl ?? buildRes?.environment_url ?? refPano ?? null;
  const selSize = (() => {
    if (!p.selected || !planRes) return null;
    const obs = planRes.plan.objects.filter((o) => assetKey(o) === p.selected);
    if (!obs.length) return null;
    return { w: Math.max(...obs.map((o) => o.w)), d: Math.max(...obs.map((o) => o.d)), h: Math.max(...obs.map((o) => o.h)) };
  })();
  const v360 = view360 >= 0 && view360 < panoramas.length ? view360 : sceneGlb ? -1 : 0;

  const tabs: { id: TabId; label: string; ready: boolean }[] = [
    { id: "floor", label: "Floor plan", ready: !!floorUrl || !!planRes },
    { id: "greybox", label: "Grey-box", ready: !!planRes },
    { id: "live", label: "Live", ready: !!latest },
    { id: "compare", label: "Compare", ready: !!(p.referenceUrl && compareRender) },
    { id: "3d", label: "3D", ready: !!sel?.mesh_url },
    ...(has360 ? [{ id: "360" as TabId, label: "360", ready: true }] : []),
    ...(buildRun.status === "done" ? [{ id: "result" as TabId, label: "Result", ready: true }] : []),
  ];

  const lens = planRes?.plan.reference_camera ? `${Math.round(planRes.plan.reference_camera.lens_mm)}MM` : "";
  const room = planRes?.plan.room;
  const selNo = p.selected ? buildRun.propOrder.indexOf(p.selected) + 1 : 0;
  const title =
    tab === "floor"
      ? `Floor plan${room ? ` · ${room.width} x ${room.depth} M` : ""}${floorMode === "map" && planRes ? " · prop map" : ""}`
      : tab === "greybox"
        ? greyView === "reference"
          ? `Camera A · grey-box · reference angle${lens ? " · " + lens : ""}`
          : "Camera B · grey-box · overview"
        : tab === "live"
          ? `Camera A · live${lens ? " · " + lens : ""}`
          : tab === "compare"
            ? `Plate vs camera A${lens ? " · " + lens : ""}`
            : tab === "3d"
              ? `Prop ${selNo ? "P-" + String(selNo).padStart(3, "0") : ""} · turntable${selSize ? " · real scale" : ""}`
              : tab === "360"
                ? v360 >= 0
                  ? `Camera B · 360 plate · ${panoramas[v360]?.label ?? ""}`
                  : "Set model · glTF · free camera"
                : "Dailies";
  const props = Object.values(buildRun.props);
  const meshed = props.filter((x) => x.mesh_url).length;
  const standins = props.filter((x) => !x.mesh_url && x.status !== "failed").length;
  const meshPhaseOver = buildRun.stages.generating_meshes?.status === "done" || buildRun.status === "done";
  const note = building
    ? buildRun.status === "done"
      ? buildRes?.standins_left.length
        ? `${buildRes.standins_left.length} props stood in`
        : "all props in"
      : meshPhaseOver && standins
        ? `${standins} props stood in`
        : buildRun.totalProps
          ? `${meshed} of ${buildRun.totalProps} props in`
          : "calling props"
    : planRun.status === "done"
      ? "plan ready for approval"
      : planRun.status === "running"
        ? "planning"
        : "";

  return (
    <div className="viewport">
      <h3 className="sheet-h frame-title">{title}</h3>
      <div className="vp-tabs" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={`vp-tab ${tab === t.id ? "on" : ""} ${t.ready ? "ready" : ""}`}
            onClick={() => p.onTab(t.id)}
          >
            {t.label}
          </button>
        ))}
        <span className="vp-spacer" />
        {tab === "floor" && planRes && (
          <div className="seg small" role="group" aria-label="Floor plan view">
            <button className={floorMode === "drawing" ? "on" : ""} onClick={() => setFloorMode("drawing")}>
              Drawing
            </button>
            <button className={floorMode === "map" ? "on" : ""} onClick={() => setFloorMode("map")}>
              Prop map
            </button>
          </div>
        )}
        {tab === "greybox" && planRes && (
          <div className="seg small" role="group" aria-label="Grey-box view">
            <button className={greyView === "reference" ? "on" : ""} onClick={() => setGreyView("reference")}>
              Reference camera
            </button>
            <button className={greyView === "overview" ? "on" : ""} onClick={() => setGreyView("overview")}>
              Overview
            </button>
          </div>
        )}
        {tab === "360" && has360 && (
          <div className="seg small" role="group" aria-label="360 viewpoint">
            {panoramas.map((pn, i) => (
              <button key={pn.url} className={v360 === i ? "on" : ""} onClick={() => setView360(i)} title={pn.label}>
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
        <button className={`follow ${p.follow ? "on" : ""}`} onClick={p.onFollow} title="Switch views as new results arrive">
          <span className="follow-dot" aria-hidden /> Follow
        </button>
      </div>

      <div className="vp-stage">
        {note && <span className="frame-note">{note}</span>}
        {tab === "floor" &&
          (floorMode === "map" && planRes ? (
            <LiveMap plan={planRes.plan} run={buildRun} selected={p.selected} onSelect={p.onSelect} />
          ) : floorUrl ? (
            <Fade src={floorUrl} alt="Floor plan" className="paper" />
          ) : (
            <Empty run={planRun} text="The floor plan is drawn once the layout is planned." />
          ))}
        {tab === "greybox" &&
          (planRes ? (
            <Fade
              src={greyView === "reference" ? planRes.blockout_reference_url : planRes.blockout_overview_url}
              alt={greyView === "reference" ? "Grey-box from the reference camera" : "Grey-box overview"}
            />
          ) : (
            <Empty run={planRun} text="Grey-box renders from the reference camera and an overview land here." />
          ))}
        {tab === "live" &&
          (latest ? (
            <div className="live-frame">
              <Fade src={latest.url} alt={latest.message || latest.stage} />
              <span className="live-tag">
                {STAGE_LABELS[latest.stage] ?? latest.stage}
                {latest.message ? `: ${latest.message}` : ""}
              </span>
            </div>
          ) : (
            <Empty run={run} text="Each render the endpoint makes shows up here as it lands." />
          ))}
        {tab === "compare" &&
          (p.referenceUrl && compareRender ? (
            <Compare left={p.referenceUrl} right={compareRender} rightLabel={stills[0] ? "Render" : "Grey-box"} />
          ) : (
            <Empty run={run} text="Compare the reference with the matching render once there is one." />
          ))}
        {tab === "3d" &&
          (sel?.mesh_url ? (
            <Viewer3D url={sel.mesh_url} label={sel.label} model={sel.model} refUrl={sel.ref_url} size={selSize} envUrl={envUrl} no={selNo} />
          ) : (
            <Empty run={run} text={sel ? "This prop has no mesh yet." : "Pick a prop on the shelf to inspect its mesh."} />
          ))}
        {tab === "360" &&
          has360 &&
          (v360 >= 0 && panoramas[v360] ? <Pano360 url={panoramas[v360].url} /> : sceneGlb ? <SceneView url={sceneGlb} envUrl={refPano} camera={planRes?.plan.reference_camera} /> : null)}
        {tab === "result" && buildRes && <Result res={buildRes} run={buildRun} planRun={planRun} />}
      </div>

      <div className="caption" aria-live="polite">
        <span className="caption-text" key={run.caption.message}>
          {run.status === "idle"
            ? "Drop a reference, plan the space, then build it."
            : run.status === "failed"
              ? run.error
              : run.status === "done" && p.activeKind === "plan"
                ? "Plan ready. Revise it in words or approve it to build."
                : run.status === "done"
                  ? "Scene built. Download the package or look through the stills."
                  : run.caption.message || STAGE_LABELS[run.caption.stage] || "Starting"}
        </span>
        <span className="caption-time">{run.status === "idle" ? "" : fmtTime(p.now)}</span>
      </div>
    </div>
  );
}

function Empty({ run, text }: { run: RunState; text: string }) {
  return (
    <div className="empty">
      {run.status === "running" && <span className="empty-pulse" />}
      <p>{text}</p>
    </div>
  );
}
