import { useApi } from "@/hooks/useApi";
import { matches } from "@/lib/api";
import type { Match, MatchStatus } from "@/types";

const COLUMNS: { id: MatchStatus; title: string }[] = [
  { id: "new", title: "New" },
  { id: "contacted", title: "Contacted" },
  { id: "interview", title: "Interview" },
  { id: "placed", title: "Placed" },
  { id: "rejected", title: "Rejected" },
];

export default function MatchBoard() {
  const { data, loading, reload } = useApi(() => matches.list(), []);

  const moveTo = async (match: Match, target: MatchStatus) => {
    await matches.update(match.id, { status: target });
    reload();
  };

  const grouped: Record<string, Match[]> = {};
  COLUMNS.forEach((c) => (grouped[c.id] = []));
  (data ?? []).forEach((m) => {
    if (grouped[m.status]) grouped[m.status].push(m);
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold tracking-tight">Match Board</h1>
        <p className="text-text-secondary mt-1">
          Pipeline of candidate ↔ job matches.
        </p>
      </div>

      {loading && <div className="text-text-muted">Loading…</div>}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        {COLUMNS.map((col) => (
          <div key={col.id} className="card p-4 min-h-[400px]">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-display font-semibold">{col.title}</h3>
              <span className="label-mono">{grouped[col.id].length}</span>
            </div>
            <div className="space-y-2">
              {grouped[col.id].map((m) => (
                <div
                  key={m.id}
                  className="bg-bg-elevated rounded-md p-3 border border-bg-border hover:border-amber-accent transition-colors"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium">Match #{m.id}</span>
                    <ScoreRing score={m.score} />
                  </div>
                  <div className="text-xs text-text-muted">
                    Cand #{m.candidate_id} → Job #{m.job_id}
                  </div>
                  {m.rationale && (
                    <p className="text-xs text-text-secondary mt-2 line-clamp-2">
                      {m.rationale}
                    </p>
                  )}
                  <div className="flex flex-wrap gap-1 mt-2">
                    {COLUMNS.filter((c) => c.id !== col.id).map((c) => (
                      <button
                        key={c.id}
                        onClick={() => moveTo(m, c.id)}
                        className="text-[10px] uppercase font-mono text-text-muted hover:text-amber-accent px-1.5 py-0.5 rounded border border-bg-border"
                      >
                        → {c.title}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ScoreRing({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(100, score));
  const color =
    pct >= 80 ? "text-success" : pct >= 60 ? "text-amber-accent" : "text-text-muted";
  return (
    <div className={`font-mono text-sm font-semibold ${color}`}>{pct.toFixed(0)}%</div>
  );
}
