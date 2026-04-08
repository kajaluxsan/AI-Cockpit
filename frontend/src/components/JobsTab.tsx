import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "@/hooks/useApi";
import { jobs as jobsApi } from "@/lib/api";
import StatusBadge from "./StatusBadge";

const STATUS_OPTIONS = ["all", "open", "paused", "filled", "closed"];

export default function JobsTab() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("all");

  const { data, loading } = useApi(
    () =>
      jobsApi.list({
        q: q.trim() || undefined,
        status: status === "all" ? undefined : status,
        limit: 60,
      }),
    [q, status]
  );

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">Jobs</h1>
        <p className="text-text-secondary text-sm mt-1">
          Suche nach Titel, Firma oder Ort.
        </p>
      </div>

      <div className="card p-3 flex flex-col md:flex-row md:items-center gap-3">
        <input
          type="search"
          placeholder="Titel, Firma, Ort…"
          className="input md:flex-1"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          autoFocus
        />
        <select
          className="input md:w-48"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s === "all" ? "Alle Status" : s}
            </option>
          ))}
        </select>
      </div>

      {loading && <div className="text-text-muted text-sm">Lade…</div>}
      {!loading && (data?.length ?? 0) === 0 && (
        <div className="card p-10 text-center text-text-muted">Keine Jobs gefunden.</div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {(data ?? []).map((j) => (
          <Link
            key={j.id}
            to={`/jobs/${j.id}`}
            className="card p-4 hover:border-amber-accent/40 transition-colors block"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="font-medium truncate">{j.title}</div>
                <div className="text-xs text-text-muted truncate">
                  {j.company || "—"} · {j.location || "—"}
                </div>
              </div>
              <StatusBadge status={j.status} />
            </div>
            {j.required_skills && j.required_skills.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-3">
                {j.required_skills.slice(0, 5).map((s) => (
                  <span
                    key={s}
                    className="pill bg-bg-elevated text-text-secondary"
                  >
                    {s}
                  </span>
                ))}
              </div>
            )}
          </Link>
        ))}
      </div>
    </div>
  );
}
