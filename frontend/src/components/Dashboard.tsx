import { useActivity, useDashboardStats } from "@/hooks/useDashboardStats";
import { Link } from "react-router-dom";

export default function Dashboard() {
  const { data: stats, loading } = useDashboardStats();
  const { data: activity } = useActivity();

  const cards = [
    { label: "New today", value: stats?.new_candidates_today ?? "—", hint: "candidates" },
    { label: "Open jobs", value: stats?.open_jobs ?? "—", hint: "positions" },
    { label: "Matches / week", value: stats?.matches_this_week ?? "—", hint: "scored" },
    { label: "Calls today", value: stats?.calls_today ?? "—", hint: "outbound" },
  ];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-3xl font-semibold tracking-tight">
          Operations Overview
        </h1>
        <p className="text-text-secondary mt-1">
          Live status of the recruiting pipeline.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((c) => (
          <div key={c.label} className="card p-5">
            <div className="label-mono">{c.label}</div>
            <div className="font-mono text-4xl font-medium mt-2 text-amber-accent">
              {loading ? "··" : c.value}
            </div>
            <div className="text-text-muted text-xs mt-1">{c.hint}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 card p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display text-lg font-semibold">Activity feed</h2>
            <span className="label-mono">latest 25</span>
          </div>
          <div className="divide-y divide-bg-border">
            {(activity ?? []).slice(0, 25).map((a, i) => (
              <div key={i} className="py-3 flex items-start gap-3">
                <div className="font-mono text-xs text-text-muted w-20 pt-0.5">
                  {new Date(a.timestamp).toLocaleTimeString("de-CH", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </div>
                <div className="flex-1">
                  <div className="text-sm">{a.title}</div>
                  <div className="label-mono mt-0.5">{a.type.replace(/_/g, " ")}</div>
                </div>
              </div>
            ))}
            {(!activity || activity.length === 0) && (
              <div className="py-6 text-text-muted text-sm">No activity yet.</div>
            )}
          </div>
        </div>

        <div className="card p-6">
          <h2 className="font-display text-lg font-semibold mb-4">Quick actions</h2>
          <div className="space-y-3">
            <Link to="/people" className="btn-secondary w-full">
              Browse people
            </Link>
            <Link to="/jobs" className="btn-secondary w-full">
              Browse jobs
            </Link>
            <Link to="/messages" className="btn-secondary w-full">
              Messages
            </Link>
            <Link to="/matches" className="btn-secondary w-full">
              Open match board
            </Link>
            <Link to="/calls" className="btn-secondary w-full">
              Call history
            </Link>
            <Link to="/settings" className="btn-secondary w-full">
              System settings
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
