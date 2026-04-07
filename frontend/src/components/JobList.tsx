import { Link } from "react-router-dom";
import { useApi } from "@/hooks/useApi";
import { jobs } from "@/lib/api";
import StatusBadge from "./StatusBadge";

export default function JobList() {
  const { data, loading } = useApi(() => jobs.list(), []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold tracking-tight">Jobs</h1>
        <p className="text-text-secondary mt-1">All open positions across sources.</p>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-bg-border">
              <th className="text-left py-3 px-4 label-mono">Title</th>
              <th className="text-left py-3 px-4 label-mono">Company</th>
              <th className="text-left py-3 px-4 label-mono">Location</th>
              <th className="text-left py-3 px-4 label-mono">Source</th>
              <th className="text-left py-3 px-4 label-mono">Status</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={5} className="py-8 text-center text-text-muted">
                  Loading…
                </td>
              </tr>
            )}
            {!loading && data && data.length === 0 && (
              <tr>
                <td colSpan={5} className="py-8 text-center text-text-muted">
                  No jobs.
                </td>
              </tr>
            )}
            {(data ?? []).map((j) => (
              <tr key={j.id} className="table-row">
                <td className="py-3 px-4">
                  <Link to={`/jobs/${j.id}`} className="font-medium hover:text-amber-accent">
                    {j.title}
                  </Link>
                </td>
                <td className="py-3 px-4 text-text-secondary">{j.company || "—"}</td>
                <td className="py-3 px-4 text-text-secondary">{j.location || "—"}</td>
                <td className="py-3 px-4">
                  <span className="pill bg-bg-elevated text-text-secondary">{j.source}</span>
                </td>
                <td className="py-3 px-4">
                  <StatusBadge status={j.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
