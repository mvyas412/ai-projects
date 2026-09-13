"use client";

import { useEffect, useMemo, useState } from "react";

type JsonRecord = Record<string, unknown>;
type Identity = { user: { email?: string; name?: string }; workspaces: Array<{ id: string; name: string; role: string }> };
type View = "overview" | "library" | "jobs" | "chat" | "evidence";

const labels: Record<View, string> = {
  overview: "Overview",
  library: "Library",
  jobs: "Job progress",
  chat: "Chat",
  evidence: "Evidence",
};

async function api(path: string): Promise<unknown> {
  const response = await fetch(`/api/backend/${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error("The workspace service is temporarily unavailable.");
  return response.json();
}

export function CandidateShell() {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [view, setView] = useState<View>("overview");
  const [data, setData] = useState<unknown>(null);
  const [error, setError] = useState("");
  const workspace = identity?.workspaces[0];
  const path = useMemo(() => {
    if (!workspace) return null;
    const root = `workspaces/${workspace.id}`;
    return {
      overview: `${root}/documents`,
      library: `${root}/documents`,
      jobs: `${root}/ingestion/jobs`,
      chat: `${root}/conversations`,
      evidence: `${root}/feedback`,
    }[view];
  }, [view, workspace]);

  useEffect(() => {
    api("users/me").then((value) => setIdentity(value as Identity)).catch((reason: Error) => setError(reason.message));
  }, []);
  useEffect(() => {
    if (!path) return;
    setData(null);
    api(path).then(setData).catch((reason: Error) => setError(reason.message));
  }, [path]);

  const rows = Array.isArray(data) ? (data as JsonRecord[]) : [];
  return (
    <main>
      <header>
        <div><span className="eyebrow">PHASE 8 CANDIDATE</span><h1>MM-RAG workspace</h1></div>
        <div className="identity"><span>{identity?.user.email ?? "Signed in"}</span><a href="/auth/logout">Log out</a></div>
      </header>
      <div className="notice">Evaluation-only Next.js candidate · Streamlit remains authoritative</div>
      <nav aria-label="Workspace views">
        {(Object.keys(labels) as View[]).map((item) => (
          <button key={item} aria-current={view === item ? "page" : undefined} onClick={() => setView(item)}>{labels[item]}</button>
        ))}
      </nav>
      <section className="workspace">
        <p>{workspace ? `${workspace.name} · ${workspace.role}` : "Loading personal workspace…"}</p>
        <h2>{labels[view]}</h2>
        {error ? <div role="alert" className="error">{error}</div> : null}
        {!error && !data ? <p>Loading authorized data…</p> : null}
        {data && rows.length === 0 ? <div className="empty">No items yet.</div> : null}
        <div className="cards">
          {rows.slice(0, 20).map((row, index) => (
            <article key={String(row.id ?? index)}>
              <strong>{String(row.title ?? row.name ?? row.status ?? `Item ${index + 1}`)}</strong>
              <span>{String(row.status ?? row.reason ?? row.target_type ?? "Available")}</span>
            </article>
          ))}
        </div>
        {view === "chat" ? <p className="hint">Conversation creation and paid questions stay disabled in this bounded candidate until parity acceptance.</p> : null}
        {view === "evidence" ? <p className="hint">Feedback is shown without document content or token data.</p> : null}
      </section>
    </main>
  );
}
