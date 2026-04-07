import { useApi } from "@/hooks/useApi";
import { emails } from "@/lib/api";

export default function EmailLog() {
  const { data, loading } = useApi(() => emails.list(), []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold tracking-tight">Email Log</h1>
        <p className="text-text-secondary mt-1">
          All inbound applications and outbound follow-ups.
        </p>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-bg-border">
              <th className="text-left py-3 px-4 label-mono">Direction</th>
              <th className="text-left py-3 px-4 label-mono">Kind</th>
              <th className="text-left py-3 px-4 label-mono">From</th>
              <th className="text-left py-3 px-4 label-mono">To</th>
              <th className="text-left py-3 px-4 label-mono">Subject</th>
              <th className="text-left py-3 px-4 label-mono">Date</th>
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
            {!loading && (!data || data.length === 0) && (
              <tr>
                <td colSpan={6} className="py-8 text-center text-text-muted">
                  No emails yet.
                </td>
              </tr>
            )}
            {(data ?? []).map((e) => (
              <tr key={e.id} className="table-row">
                <td className="py-3 px-4">
                  <span
                    className={`pill ${
                      e.direction === "inbound"
                        ? "bg-cyan-link/10 text-cyan-link"
                        : "bg-amber-accent/10 text-amber-accent"
                    }`}
                  >
                    {e.direction}
                  </span>
                </td>
                <td className="py-3 px-4 font-mono text-xs text-text-muted">{e.kind}</td>
                <td className="py-3 px-4 text-text-secondary text-sm">{e.from_address || "—"}</td>
                <td className="py-3 px-4 text-text-secondary text-sm">{e.to_address || "—"}</td>
                <td className="py-3 px-4 text-sm">{e.subject || "—"}</td>
                <td className="py-3 px-4 font-mono text-xs text-text-muted">
                  {new Date(e.created_at).toLocaleString("de-CH")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
