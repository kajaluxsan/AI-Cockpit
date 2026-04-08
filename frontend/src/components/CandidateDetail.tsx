import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "@/hooks/useApi";
import { calls as callsApi, candidates } from "@/lib/api";
import Avatar from "./shared/Avatar";
import StatusBadge from "./StatusBadge";
import { useChatDock } from "./chat/ChatDockContext";

export default function CandidateDetail() {
  const { id } = useParams();
  const candidateId = Number(id);
  const [callMessage, setCallMessage] = useState<string | null>(null);
  const [showCv, setShowCv] = useState(false);
  const { open: openChat } = useChatDock();

  const { data: candidate, loading } = useApi(
    () => candidates.get(candidateId),
    [candidateId]
  );
  const { data: protocol } = useApi(
    () => candidates.protocol(candidateId),
    [candidateId]
  );
  const { data: matchingJobs } = useApi(
    () => candidates.matchingJobs(candidateId),
    [candidateId]
  );

  const handleCall = async () => {
    setCallMessage(null);
    try {
      const result = await callsApi.initiate({ candidate_id: candidateId });
      setCallMessage(`Anruf initiiert (SID: ${result.twilio_call_sid})`);
    } catch (e: any) {
      setCallMessage(`Fehler: ${e?.response?.data?.detail || e.message}`);
    }
  };

  if (loading) return <div className="text-text-muted">Loading…</div>;
  if (!candidate) return <div className="text-text-muted">Nicht gefunden.</div>;

  const displayName =
    candidate.full_name ||
    [candidate.first_name, candidate.last_name].filter(Boolean).join(" ") ||
    candidate.email ||
    "—";

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      <Link to="/people" className="label-mono hover:text-amber-accent">
        ← People
      </Link>

      <div className="flex flex-col md:flex-row items-start md:items-center gap-5 card p-6">
        <Avatar name={displayName} src={candidate.photo_url} size={88} />
        <div className="flex-1">
          <h1 className="font-display text-3xl font-semibold tracking-tight">
            {displayName}
          </h1>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 text-sm text-text-secondary">
            <span>{candidate.email || "—"}</span>
            <span>·</span>
            <span>{candidate.phone || "—"}</span>
            <span>·</span>
            <span>{candidate.address || candidate.location || "—"}</span>
            <StatusBadge status={candidate.status} />
          </div>
          {candidate.headline && (
            <div className="text-sm text-text-muted mt-2">{candidate.headline}</div>
          )}
        </div>
        <div className="flex flex-col gap-2">
          <button
            onClick={() => openChat(candidateId, displayName, candidate.photo_url)}
            className="btn-primary"
          >
            AI Chat
          </button>
          <button onClick={handleCall} className="btn-secondary">
            Anrufen
          </button>
          {candidate.has_cv && (
            <button
              onClick={() => setShowCv((v) => !v)}
              className="btn-secondary"
            >
              {showCv ? "CV ausblenden" : "CV öffnen"}
            </button>
          )}
        </div>
      </div>

      {callMessage && (
        <div className="card p-4 text-sm text-text-secondary">{callMessage}</div>
      )}

      {candidate.missing_fields && candidate.missing_fields.length > 0 && (
        <div className="card p-4 border-amber-accent/30">
          <div className="label-mono text-amber-accent">CRM-Pflichtfelder fehlen</div>
          <div className="text-sm text-text-secondary mt-1">
            {candidate.missing_fields.join(", ")}
          </div>
        </div>
      )}

      {showCv && candidate.has_cv && (
        <section className="card p-0 overflow-hidden">
          <iframe
            src={candidates.cvUrl(candidateId)}
            title={`CV ${displayName}`}
            className="w-full"
            style={{ height: "70vh", border: 0, background: "#1c1c23" }}
          />
        </section>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <section className="lg:col-span-2 card p-6 space-y-4">
          <h2 className="font-display text-lg font-semibold">Profil</h2>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <Field label="Erfahrung" value={candidate.experience_years ? `${candidate.experience_years} J` : null} />
            <Field
              label="Gehaltswunsch"
              value={
                candidate.salary_expectation
                  ? `${candidate.salary_expectation.toLocaleString("de-CH")} ${
                      candidate.salary_currency || "CHF"
                    }`
                  : null
              }
            />
            <Field label="Verfügbarkeit" value={candidate.availability} />
            <Field label="Sprache" value={candidate.language} />
            <Field
              label="Gesprochene Sprachen"
              value={(candidate.languages_spoken ?? []).join(", ") || null}
            />
            <Field label="Quelle" value={candidate.source} />
          </div>
          {candidate.skills && candidate.skills.length > 0 && (
            <div>
              <div className="label-mono mb-2">Skills</div>
              <div className="flex flex-wrap gap-1">
                {candidate.skills.map((s) => (
                  <span key={s} className="pill bg-bg-elevated text-text-secondary">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
          {candidate.summary && (
            <div>
              <div className="label-mono mb-2">Zusammenfassung</div>
              <p className="text-sm text-text-secondary leading-relaxed">
                {candidate.summary}
              </p>
            </div>
          )}
        </section>

        <section className="card p-6">
          <h2 className="font-display text-lg font-semibold mb-3">Passende Stellen</h2>
          {(matchingJobs ?? []).length === 0 && (
            <div className="text-text-muted text-sm">Keine offenen Jobs gefunden.</div>
          )}
          <div className="space-y-2">
            {(matchingJobs ?? []).map((mj) => (
              <Link
                key={mj.job.id}
                to={`/jobs/${mj.job.id}`}
                className="block p-3 bg-bg-elevated rounded-md hover:bg-bg-border transition-colors"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="font-medium truncate">{mj.job.title}</div>
                    <div className="text-xs text-text-muted truncate">
                      {mj.job.company || "—"}
                    </div>
                  </div>
                  <span className="font-mono text-amber-accent text-sm">
                    {mj.match.score.toFixed(0)}%
                  </span>
                </div>
              </Link>
            ))}
          </div>
        </section>
      </div>

      <section className="card p-6">
        <h2 className="font-display text-lg font-semibold mb-3">Protokoll</h2>
        {(protocol?.length ?? 0) === 0 && (
          <div className="text-text-muted text-sm">Noch keine Kommunikation.</div>
        )}
        <div className="space-y-2">
          {(protocol ?? []).map((p) => (
            <div
              key={`${p.kind}-${p.reference_id}-${p.created_at}`}
              className="p-3 bg-bg-elevated rounded-md"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-xs uppercase text-text-muted">
                  {p.kind} {p.status ? `· ${p.status}` : ""}
                </span>
                <span className="label-mono">
                  {new Date(p.created_at).toLocaleString("de-CH")}
                </span>
              </div>
              <div className="text-sm font-medium mt-1">{p.title}</div>
              {p.body && (
                <p className="text-xs text-text-secondary mt-1 line-clamp-3 whitespace-pre-line">
                  {p.body}
                </p>
              )}
            </div>
          ))}
        </div>
      </section>
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
