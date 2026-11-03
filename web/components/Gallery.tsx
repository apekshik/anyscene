"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { SCORE_KEYS } from "@/lib/builder";
import { ago, cachedList, galleryApp, listGallery, storeList, STATUS_LABEL, type GalleryItem, type GalleryKind, type GalleryList } from "@/lib/gallery";
import { getAccessKey, getWho, ownerEmail, ownerName } from "@/lib/sources";
import Stamp from "./Stamp";
import WhoAmI from "./WhoAmI";

const WHOSE_STORAGE = "anyscene.gallery.whose";

const POLL_MS = 30_000; // the list refreshes while open, so new and running builds show up

/** Everyone's builds, newest first, read from the fal apps' storage. A card opens the build in the results view. */
export default function Gallery() {
  const params = useSearchParams();
  const kind: GalleryKind = params.get("kind") === "kit" ? "kit" : "scene";
  const override = params.get("gallery_app");
  const app = galleryApp(kind, override);
  const [list, setList] = useState<GalleryList | null>(null);
  const [stale, setStale] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<"all" | "running" | "done">("all");
  // My builds / Everyone (scenes carry an owner tag; kits don't yet)
  const [whose, setWhose] = useState<"mine" | "everyone">("everyone");
  const [me, setMe] = useState("");
  const [whoOpen, setWhoOpen] = useState(false);
  useEffect(() => {
    setMe(getWho()?.email ?? "");
    try {
      if (localStorage.getItem(WHOSE_STORAGE) === "mine") setWhose("mine");
    } catch {
      /* default: everyone */
    }
  }, []);
  const pickWhose = (w: "mine" | "everyone") => {
    if (w === "mine" && !getWho()) return setWhoOpen(true);
    setWhose(w);
    try {
      localStorage.setItem(WHOSE_STORAGE, w);
    } catch {
      /* not remembered */
    }
  };
  const mine = whose === "mine" && kind === "scene";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const l = await listGallery(kind, app);
      setList(l);
      setStale(false);
      setError("");
      storeList(kind, app, l);
    } catch (e) {
      const anyE = e as { body?: { detail?: unknown }; message?: string };
      setError(typeof anyE.body?.detail === "string" ? anyE.body.detail : anyE.message || String(e));
    } finally {
      setLoading(false);
    }
  }, [kind, app]);

  useEffect(() => {
    const c = cachedList(kind, app);
    setList(c);
    setStale(!!c);
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [kind, app, load]);

  const href = (q: Record<string, string>) => {
    const p = new URLSearchParams(q);
    if (override) p.set("gallery_app", override);
    return `/?${p.toString()}`;
  };
  const builds = (list?.builds ?? [])
    .filter((b) => !mine || (!!me && ownerEmail(b.owner) === me))
    .filter((b) => filter === "all" || (filter === "running" ? b.status === "running" : b.status !== "running"));
  const running = (list?.builds ?? []).filter((b) => b.status === "running").length;

  return (
    <div className="gallery-page">
      <header className="topbar">
        <div className="slate gallery-slate" role="group" aria-label="Slate">
          <div className="slate-cell">
            <small>Production</small>
            <b>{kind === "kit" ? "AnyKit" : "AnyScene"}</b>
          </div>
          <div className="slate-cell">
            <small>Reel</small>
            <b>Gallery</b>
          </div>
          <div className="slate-cell">
            <small>Takes</small>
            <b>{list ? String(list.total).padStart(2, "0") : "--"}</b>
          </div>
          <div className="slate-cell">
            <small>Rolling</small>
            <b>{list ? String(running).padStart(2, "0") : "--"}</b>
          </div>
          <div className="slate-cell">
            <small>Source</small>
            <b title={app}>{app.replace(/^[^/]+\//, "") || "not set"}</b>
          </div>
          <div className="slate-stripe" aria-hidden />
        </div>
        <div className="toolbar">
          <div className="seg small" role="group" aria-label="Product">
            <a className={`seg-link ${kind === "scene" ? "on" : ""}`} href={href({ view: "gallery" })} aria-current={kind === "scene" ? "page" : undefined}>
              Scenes
            </a>
            <a className={`seg-link ${kind === "kit" ? "on" : ""}`} href={href({ view: "gallery", kind: "kit" })} aria-current={kind === "kit" ? "page" : undefined}>
              Kits
            </a>
          </div>
          {kind === "scene" && (
            <div className="seg small" role="group" aria-label="Whose builds">
              {(["mine", "everyone"] as const).map((w) => (
                <button key={w} className={(w === "mine") === mine ? "on" : ""} aria-pressed={(w === "mine") === mine} onClick={() => pickWhose(w)}>
                  {w === "mine" ? "My builds" : "Everyone"}
                </button>
              ))}
            </div>
          )}
          <div className="seg small" role="group" aria-label="Show">
            {(["all", "running", "done"] as const).map((f) => (
              <button key={f} className={filter === f ? "on" : ""} aria-pressed={filter === f} onClick={() => setFilter(f)}>
                {f === "all" ? "All" : f === "running" ? "Rolling" : "Finished"}
              </button>
            ))}
          </div>
          <span className="live-pill">{loading ? (list ? "Refreshing" : "Waking the worker (a cold start can take a few minutes)") : stale ? "Cached" : `Storage: ${app}`}</span>
          <span className="vp-spacer" />
          <button className="text-btn" onClick={load} disabled={loading}>
            Refresh
          </button>
          <a className="text-btn" href={href({})}>
            New build
          </a>
        </div>
      </header>

      <main className="gallery-main">
        {error && (
          <p className="error-note">
            {error}
            {/password|access key/i.test(error) && (
              <>
                {" "}
                <button className="text-btn" onClick={() => setWhoOpen(true)}>
                  {getAccessKey() ? "Change the password" : "Enter the password"}
                </button>
              </>
            )}
          </p>
        )}
        {!list && !error && (
          <div className="empty gallery-empty">
            <span className="empty-pulse" />
            <p>Reading every build from storage. The first look can wait on a cold GPU worker for a few minutes.</p>
          </div>
        )}
        {list && builds.length === 0 && (
          <div className="empty gallery-empty">
            <p>
              {mine && filter === "all"
                ? `No builds under ${me} yet. Builds you start on the build page are saved here.`
                : filter === "all"
                  ? `No ${kind === "kit" ? "kits" : "builds"} on ${app} yet.`
                  : "Nothing here with this filter."}
            </p>
          </div>
        )}
        <ul className="gallery-grid">
          {builds.map((b) => (
            <Card key={b.id} b={b} href={href(kind === "kit" ? { open: b.id, kind: "kit" } : { open: b.id })} now={list?.now} />
          ))}
        </ul>
      </main>
      {whoOpen && (
        <WhoAmI
          onCancel={() => setWhoOpen(false)}
          onDone={() => {
            setWhoOpen(false);
            setMe(getWho()?.email ?? "");
            if (error) load();
            else pickWhose("mine");
          }}
        />
      )}
    </div>
  );
}

function Card({ b, href, now }: { b: GalleryItem; href: string; now?: number }) {
  const scores = b.last_scores ? Object.values(b.last_scores) : [];
  const avg = scores.length ? scores.reduce((s, v) => s + v, 0) / scores.length : null;
  const low = b.last_scores ? SCORE_KEYS.filter((k) => (b.last_scores?.[k] ?? 10) < 6) : [];
  const title = b.prompt?.trim() || b.name || b.milestone?.message || "(no prompt: built from the reference)";
  const ref = b.reference_urls?.[0];
  return (
    <li className={`gallery-card status-${b.status}`}>
      <a href={href} aria-label={`Open ${b.id}: ${title}`}>
        <div className="gallery-cover">
          {b.cover ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={b.cover} alt="" loading="lazy" />
          ) : (
            <span className="gallery-nocover">{b.status === "running" ? "Rolling: no frame yet" : "No frames"}</span>
          )}
          {ref && (
            // eslint-disable-next-line @next/next/no-img-element
            <img className="gallery-ref" src={ref} alt="" loading="lazy" title="Reference" />
          )}
          <span className="gallery-stamp">
            {b.status === "running" ? (
              <span className="rolling-tag">Rolling</span>
            ) : (
              <Stamp tilt={-5}>{b.status === "done" && b.passed ? "Passed" : STATUS_LABEL[b.status]}</Stamp>
            )}
          </span>
        </div>
        <div className="gallery-body">
          <p className="gallery-title" title={title}>
            {title}
          </p>
          <p className="gallery-meta">
            <b>{b.id.replace(/^[bk]_/, "").slice(0, 6).toUpperCase()}</b>
            <span title={b.started ? new Date(b.started * 1000).toLocaleString() : ""}>{b.started ? ago(b.started, now) : ""}</span>
            <span>{b.minutes != null ? `${Math.round(b.minutes)} min` : ""}</span>
            {b.owner && <span className="gallery-owner" title={b.owner}>{ownerName(b.owner)}</span>}
            <span>
              {b.critic_rounds ? `${b.critic_rounds} round${b.critic_rounds === 1 ? "" : "s"}${avg != null ? `, avg ${avg.toFixed(1)}` : ""}` : "no critic"}
            </span>
          </p>
          <p className="gallery-sub">
            {b.status === "running" && b.milestone ? `${b.milestone.stage}: ${b.milestone.message}` : ""}
            {b.status !== "running" && low.length ? `low: ${low.join(", ").replace(/_/g, " ")}` : ""}
            {b.status !== "running" && !low.length ? `${b.n_previews ? `${b.n_previews} previews · ` : ""}${b.frames} frames${b.effort ? ` · ${b.effort}` : ""}` : ""}
          </p>
        </div>
      </a>
    </li>
  );
}
