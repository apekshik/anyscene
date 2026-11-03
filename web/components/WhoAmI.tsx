"use client";

import { useEffect, useState } from "react";
import { anysceneHeaders, getAccessKey, getWho, setAccessKey, setWho } from "@/lib/sources";

/** What the server says about this browser's key and name (app/api/me). */
export interface Me {
  admin: boolean;
  open: boolean;
  owner: string | null;
  error: string | null;
  limit: number;
  used: number;
  domain: string | null;
}

export async function fetchMe(): Promise<Me> {
  const r = await fetch("/api/me", { headers: anysceneHeaders(), cache: "no-store" });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `HTTP ${r.status}`);
  return body as Me;
}

/** The sign-in card: the shared password and an email or username, kept in this browser. Checked against the server before it closes. */
export default function WhoAmI({ onDone, onCancel, reason }: { onDone: (me: Me) => void; onCancel?: () => void; reason?: string }) {
  const [key, setKey] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setKey(getAccessKey());
    const w = getWho();
    if (w) setEmail(w.email);
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    const prev = { key: getAccessKey(), who: getWho() };
    setAccessKey(key.trim());
    setWho({ name: "", email: email.trim().toLowerCase() });
    try {
      const me = await fetchMe();
      if (me.error) throw new Error(me.error);
      onDone(me);
    } catch (err) {
      setAccessKey(prev.key);
      setWho(prev.who);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="sheet-backdrop" onClick={(e) => e.target === e.currentTarget && onCancel?.()}>
      <form className="sheet" role="dialog" aria-modal="true" aria-labelledby="who-title" onSubmit={submit}>
        <h2 id="who-title">Who's on the call sheet?</h2>
        <p className="fine">
          {reason || "Your builds are saved under your email or username, so you can find them again under My builds."} Kept in this browser only.
        </p>
        <label className="field">
          <span className="field-label">Email or username</span>
          <input required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={120} placeholder="you@fal.ai or a username" />
        </label>
        <label className="field">
          <span className="field-label">Password</span>
          <input type="password" autoComplete="current-password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="from the owner" />
        </label>
        {error && <p className="error-note">{error}</p>}
        <div className="sheet-actions">
          {onCancel && (
            <button type="button" className="secondary" onClick={onCancel}>
              Cancel
            </button>
          )}
          <button type="submit" className="primary" disabled={busy || !email.trim()}>
            {busy ? "Checking" : "Save"}
          </button>
        </div>
      </form>
    </div>
  );
}

/** A yes/no card before something that costs money. */
export function Confirm({ title, children, yes, onYes, onNo }: { title: string; children: React.ReactNode; yes: string; onYes: () => void; onNo: () => void }) {
  return (
    <div className="sheet-backdrop" onClick={(e) => e.target === e.currentTarget && onNo()}>
      <div className="sheet" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title">
        <h2 id="confirm-title">{title}</h2>
        {children}
        <div className="sheet-actions">
          <button type="button" className="secondary" onClick={onNo} autoFocus>
            Cancel
          </button>
          <button type="button" className="primary" onClick={onYes}>
            {yes}
          </button>
        </div>
      </div>
    </div>
  );
}
