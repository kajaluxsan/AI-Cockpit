import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "@/hooks/useApi";
import { jobs } from "@/lib/api";
import Avatar from "./shared/Avatar";
import StatusBadge from "./StatusBadge";
import type { MatchingCandidate } from "@/types";

export default function JobDetail() {
  const { id } = useParams();
  const jobId = Number(id);
  const { data: job, loading } = useApi(() => jobs.get(jobId), [jobId]);
  const [ranked, setRanked] = useState<MatchingCandidate[] | null>(null);
  const [ranking, setRanking] = useState(false);

  const runRanking = async () => {
    setRanking(true);
    try {
      const r = await jobs.matchingCandidates(jobId);
      setRanked(r);
    } finally {
      setRanking(false);
    }
  };

  if (loading) return <div className="text-text-muted">Loading…</div>;
  if (!job) return <div className="text-text-muted">Not found.</div>;

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      <div>
        <Link to="/jobs" className="label-mono hover:text-amber-accent">
          ← Jobs
        </Link>
        <h1 className="font-display text-3xl font-semibold tracking-tight mt-2">
          {job.title}
        </h1>
        <div className="flex items-center gap-3 mt-2 text-sm text-text-secondary">
          <span>{job.company || "—"}</span>
          <span>·</span>
          <span>{job.location || "—"}</span>
          <span>·</span>
          <StatusBadge status={job.status} />
        </div>
      </div>

      <section className="card p-6 space-y-4">
        {job.description && (
          <div>
            <div className="label-mono mb-1">Beschreibung</div>
            <p className="text-sm text-text-secondary leading-relaxed whitespace-pre-line">
              {job.description}
            </p>
          </div>
        )}

        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
          <Field
            label="Min. Erfahrung"
            value={job.min_experience_years ? `${job.min_experience_years} J` : null}
          />
          <Field label="Anstellung" value={job.employment_type} />
          <Field
            label="Gehalt"
            value={
              job.salary_min || job.salary_max
                ? `${job.salary_min ?? "?"}–${job.salary_max ?? "?"} ${job.salary_currency || "CHF"}`
                : null
            }
          />
        </div>

        {(job.required_skills ?? []).length > 0 && (
          <div>
            <div className="label-mono mb-2">Required skills</div>
            <div className="flex flex-wrap gap-1">
              {(job.required_skills ?? []).map((s) => (
                <span key={s} className="pill bg-amber-accent/10 text-amber-accent">
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="pt-2">
          <button onClick={runRanking} disabled={ranking} className="btn-primary">
            {ranking ? "Berechne…" : "Passende Kandidaten anzeigen"}
          </button>
        </div>
      </section>

      {ranked && (
        <section className="space-y-2">
          <h2 className="label-mono">Ranking · bester zuerst</h2>
          {ranked.length === 0 && (
            <div className="card p-6 text-text-muted text-sm">
              Keine Kandidaten gefunden.
            </div>
          )}
          {ranked.map((r) => {
            const c = r.candidate;
            const name =
              c.full_name ||
              [c.first_name, c.last_name].filter(Boolean).join(" ") ||
              c.email ||
              "—";
            return (
              <Link
                key={c.id}
                to={`/people/${c.id}`}
                className="card p-4 flex items-center gap-4 hover:border-amber-accent/40 transition-colors"
              >
                <Avatar name={name} src={c.photo_url} size={44} />
                <div className="flex-1 min-w-0">
                  <div className="font-medium truncate">{name}</div>
                  <div className="text-xs text-text-muted truncate">
                    {c.headline || c.email || "—"}
                  </div>
                  <div className="text-xs text-text-muted mt-1 line-clamp-1">
                    {r.match.rationale}
                  </div>
                </div>
                <div className="font-mono text-xl text-amber-accent">
                  {r.match.score.toFixed(0)}%
                </div>
              </Link>
            );
          })}
        </section>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <div className="label-mono">{label}</div>
      <div className="mt-0.5">{value || "—"}</div>
    </div>
  );
}
