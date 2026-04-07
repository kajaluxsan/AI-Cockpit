import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "@/hooks/useApi";
import { calls as callsApi, candidates, emails, matches } from "@/lib/api";
import StatusBadge from "./StatusBadge";

export default function CandidateDetail() {
  const { id } = useParams();
  const candidateId = Number(id);
  const [callMessage, setCallMessage] = useState<string | null>(null);

  const { data: candidate, loading } = useApi(
    () => candidates.get(candidateId),
    [candidateId]
  );
  const { data: candMatches } = useApi(
    () => matches.list({ candidate_id: candidateId }),
    [candidateId]
  );
  const { data: candCalls } = useApi(
    () => callsApi.list({ candidate_id: candidateId }),
    [candidateId]
  );
  const { data: candEmails } = useApi(
    () => emails.list({ candidate_id: candidateId }),
    [candidateId]
  );

  const handleCall = async () => {
    setCallMessage(null);
    try {
      const result = await callsApi.initiate({ candidate_id: candidateId });
      setCallMessage(`Call initiated (SID: ${result.twilio_call_sid})`);
    } catch (e: any) {
      setCallMessage(`Failed: ${e?.response?.data?.detail || e.message}`);
    }
  };

  if (loading) return <div className="text-text-muted">Loading…</div>;
  if (!candidate) return <div className="text-text-muted">Not found.</div>;

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between">
        <div>
          <Link to="/candidates" className="label-mono hover:text-amber-accent">
            ← Candidates
          </Link>
          <h1 className="font-display text-3xl font-semibold tracking-tight mt-2">
            {candidate.full_name || "Unnamed candidate"}
          </h1>
          <div className="flex items-center gap-3 mt-2 text-sm text-text-secondary">
            <span>{candidate.email || "—"}</span>
            <span>·</span>
            <span>{candidate.phone || "—"}</span>
            <span>·</span>
            <span>{candidate.location || "—"}</span>
            <span>·</span>
            <StatusBadge status={candidate.status} />
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={handleCall} className="btn-primary">
            Call now
          </button>
        </div>
      </div>
      {callMessage && (
        <div className="card p-4 text-sm text-text-secondary">{callMessage}</div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <section className="card p-6">
            <h2 className="font-display text-lg font-semibold mb-3">Profile</h2>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <Field label="Headline" value={candidate.headline} />
              <Field label="Experience" value={candidate.experience_years ? `${candidate.experience_years} y` : null} />
              <Field
                label="Salary expectation"
                value={
                  candidate.salary_expectation
                    ? `${candidate.salary_expectation.toLocaleString("de-CH")} ${candidate.salary_currency || "CHF"}`
                    : null
                }
              />
              <Field label="Availability" value={candidate.availability} />
              <Field label="Language" value={candidate.language} />
              <Field
                label="Languages spoken"
                value={(candidate.languages_spoken ?? []).join(", ") || null}
              />
            </div>
            <div className="mt-4">
              <div className="label-mono mb-2">Skills</div>
              <div className="flex flex-wrap gap-1">
                {(candidate.skills ?? []).map((s) => (
                  <span key={s} className="pill bg-bg-elevated text-text-secondary">
                    {s}
                  </span>
                ))}
              </div>
            </div>
            {candidate.summary && (
              <div className="mt-4">
                <div className="label-mono mb-2">Summary</div>
                <p className="text-sm text-text-secondary leading-relaxed">
                  {candidate.summary}
                </p>
              </div>
            )}
          </section>

          <section className="card p-6">
            <h2 className="font-display text-lg font-semibold mb-3">Match history</h2>
            {(candMatches ?? []).length === 0 && (
              <div className="text-text-muted text-sm">No matches yet.</div>
            )}
            <div className="space-y-2">
              {(candMatches ?? []).map((m) => (
                <div
                  key={m.id}
                  className="flex items-center justify-between p-3 bg-bg-elevated rounded-md"
                >
                  <div>
                    <Link to={`/jobs/${m.job_id}`} className="font-medium hover:text-amber-accent">
                      Job #{m.job_id}
                    </Link>
                    <div className="text-xs text-text-muted mt-0.5">{m.rationale}</div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-xl text-amber-accent">
                      {m.score.toFixed(0)}%
                    </span>
                    <StatusBadge status={m.status} />
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="card p-6">
            <h2 className="font-display text-lg font-semibold mb-3">Communication log</h2>
            <div className="space-y-3">
              {(candCalls ?? []).map((c) => (
                <div key={`call-${c.id}`} className="p-3 bg-bg-elevated rounded-md">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-sm">CALL · {c.to_number}</span>
                    <StatusBadge status={c.status} />
                  </div>
                  {c.summary && (
                    <p className="text-sm text-text-secondary mt-2">{c.summary}</p>
                  )}
                </div>
              ))}
              {(candEmails ?? []).map((e) => (
                <div key={`mail-${e.id}`} className="p-3 bg-bg-elevated rounded-md">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-sm uppercase">{e.direction} · {e.kind}</span>
                    <span className="label-mono">
                      {new Date(e.created_at).toLocaleString("de-CH")}
                    </span>
                  </div>
                  <div className="text-sm font-medium mt-1">{e.subject || "(no subject)"}</div>
                  {e.body && (
                    <p className="text-xs text-text-secondary mt-1 line-clamp-3">{e.body}</p>
                  )}
                </div>
              ))}
              {(candCalls ?? []).length === 0 && (candEmails ?? []).length === 0 && (
                <div className="text-text-muted text-sm">No communication yet.</div>
              )}
            </div>
          </section>
        </div>

        <div className="space-y-6">
          {candidate.missing_fields && candidate.missing_fields.length > 0 && (
            <section className="card p-6 border-amber-accent/30">
              <h2 className="font-display text-lg font-semibold mb-2 text-amber-accent">
                Missing info
              </h2>
              <ul className="text-sm text-text-secondary space-y-1">
                {candidate.missing_fields.map((f) => (
                  <li key={f}>· {f}</li>
                ))}
              </ul>
            </section>
          )}
          <section className="card p-6">
            <h2 className="font-display text-lg font-semibold mb-2">Source</h2>
            <div className="text-sm text-text-secondary">{candidate.source}</div>
          </section>
        </div>
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
