import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "@/hooks/useApi";
import { candidates as candidatesApi } from "@/lib/api";
import StatusBadge from "./StatusBadge";

const STATUS_OPTIONS = [
  "all",
  "new",
  "parsed",
  "info_requested",
  "matched",
  "contacted",
  "interview",
  "placed",
  "rejected",
];

export default function CandidateList() {
  const [status, setStatus] = useState<string>("all");
  const [q, setQ] = useState<string>("");
  const { data, loading } = useApi(
    () =>
      candidatesApi.list({
        status: status === "all" ? undefined : status,
        q: q || undefined,
      }),
    [status, q]
  );

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">Candidates</h1>
          <p className="text-text-secondary mt-1">
            All candidates in the pipeline.
          </p>
        </div>
      </div>

      <div className="card p-4 flex items-center gap-3">
        <input
          type="text"
          placeholder="Search by name or email…"
          className="input max-w-md"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select
          className="input max-w-xs"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s.replace("_", " ")}
            </option>
          ))}
        </select>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-bg-border">
              <th className="text-left py-3 px-4 label-mono">Name</th>
              <th className="text-left py-3 px-4 label-mono">Email</th>
              <th className="text-left py-3 px-4 label-mono">Skills</th>
              <th className="text-left py-3 px-4 label-mono">Source</th>
              <th className="text-left py-3 px-4 label-mono">Status</th>
              <th className="text-left py-3 px-4 label-mono">Created</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={6} className="py-8 text-center text-text-muted">
                  Loading…
                </td>
              </tr>
            )}
            {!loading && data && data.length === 0 && (
              <tr>
                <td colSpan={6} className="py-8 text-center text-text-muted">
                  No candidates found.
                </td>
              </tr>
            )}
            {(data ?? []).map((c) => (
              <tr key={c.id} className="table-row">
                <td className="py-3 px-4">
                  <Link to={`/candidates/${c.id}`} className="hover:text-amber-accent">
                    {c.full_name || "—"}
                  </Link>
                </td>
                <td className="py-3 px-4 font-mono text-sm text-text-secondary">
                  {c.email || "—"}
                </td>
                <td className="py-3 px-4">
                  <div className="flex gap-1 flex-wrap max-w-xs">
                    {(c.skills ?? []).slice(0, 3).map((s) => (
                      <span key={s} className="pill bg-bg-elevated text-text-secondary">
                        {s}
                      </span>
                    ))}
                    {(c.skills?.length ?? 0) > 3 && (
                      <span className="pill bg-bg-elevated text-text-muted">
                        +{(c.skills?.length ?? 0) - 3}
                      </span>
                    )}
                  </div>
                </td>
                <td className="py-3 px-4">
                  <span className="pill bg-bg-elevated text-text-secondary">{c.source}</span>
                </td>
                <td className="py-3 px-4">
                  <StatusBadge status={c.status} />
                </td>
                <td className="py-3 px-4 font-mono text-xs text-text-muted">
                  {new Date(c.created_at).toLocaleDateString("de-CH")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
