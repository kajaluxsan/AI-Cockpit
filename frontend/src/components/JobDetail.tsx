import { Link, useParams } from "react-router-dom";
import { useApi } from "@/hooks/useApi";
import { jobs, matches } from "@/lib/api";
import StatusBadge from "./StatusBadge";

export default function JobDetail() {
  const { id } = useParams();
  const jobId = Number(id);
  const { data: job, loading } = useApi(() => jobs.get(jobId), [jobId]);
  const { data: jobMatches } = useApi(() => matches.list({ job_id: jobId }), [jobId]);

  if (loading) return <div className="text-text-muted">Loading…</div>;
  if (!job) return <div className="text-text-muted">Not found.</div>;

  return (
    <div className="space-y-8">
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <section className="lg:col-span-2 card p-6 space-y-4">
          {job.description && (
            <div>
              <div className="label-mono mb-1">Description</div>
              <p className="text-sm text-text-secondary leading-relaxed whitespace-pre-line">
                {job.description}
              </p>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4 text-sm">
            <Field
              label="Min experience"
              value={job.min_experience_years ? `${job.min_experience_years} y` : null}
            />
            <Field label="Type" value={job.employment_type} />
            <Field
              label="Salary"
              value={
                job.salary_min || job.salary_max
                  ? `${job.salary_min ?? "?"}–${job.salary_max ?? "?"} ${job.salary_currency || "CHF"}`
                  : null
              }
            />
          </div>

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

          {(job.nice_to_have_skills ?? []).length > 0 && (
            <div>
              <div className="label-mono mb-2">Nice to have</div>
              <div className="flex flex-wrap gap-1">
                {(job.nice_to_have_skills ?? []).map((s) => (
                  <span key={s} className="pill bg-bg-elevated text-text-secondary">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>

        <section className="card p-6">
          <h2 className="font-display text-lg font-semibold mb-4">Matched candidates</h2>
          {(jobMatches ?? []).length === 0 && (
            <div className="text-text-muted text-sm">No matches yet.</div>
          )}
          <div className="space-y-2">
            {(jobMatches ?? []).map((m) => (
              <div
                key={m.id}
                className="flex items-center justify-between p-3 bg-bg-elevated rounded-md"
              >
                <Link
                  to={`/candidates/${m.candidate_id}`}
                  className="text-sm font-medium hover:text-amber-accent"
                >
                  Candidate #{m.candidate_id}
                </Link>
                <span className="font-mono text-amber-accent">
                  {m.score.toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        </section>
      </div>
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
