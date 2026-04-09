import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "@/hooks/useApi";
import { calls as callsApi, candidates } from "@/lib/api";
import Avatar from "./shared/Avatar";
import StatusBadge from "./StatusBadge";
import { useChatDock } from "./chat/ChatDockContext";

// Call statuses that still allow a "hangup" button to be shown.
const NON_TERMINAL_CALL_STATUSES = new Set([
  "initiated",
  "ringing",
  "in_progress",
]);

function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return "";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function CandidateDetail() {
  const { id } = useParams();
  const candidateId = Number(id);
  const [callMessage, setCallMessage] = useState<string | null>(null);
  const [showCv, setShowCv] = useState(false);
  const [hangupBusy, setHangupBusy] = useState<number | null>(null);
  const { open: openChat } = useChatDock();

  const { data: candidate, loading, reload: reloadCandidate } = useApi(
    () => candidates.get(candidateId),
    [candidateId]
  );
  const { data: protocol, reload: reloadProtocol } = useApi(
    () => candidates.protocol(candidateId),
    [candidateId]
  );
  const { data: matchingJobs } = useApi(
    () => candidates.matchingJobs(candidateId),
    [candidateId]
  );

  const handleRecordConsent = async () => {
    try {
      await candidates.recordConsent(candidateId, "manual");
      reloadCandidate();
    } catch (e: any) {
      alert(`Fehler: ${e?.response?.data?.detail || e.message}`);
    }
  };

  const handleAnonymise = async () => {
    if (
      !confirm(
        "Recht auf Vergessenwerden: alle personenbezogenen Daten dieses " +
          "Kandidaten werden unwiderruflich gelöscht (CV, Foto, Mails, Chat). " +
          "Der Datensatz bleibt für Statistiken erhalten, kann aber nicht " +
          "mehr kontaktiert werden.\n\nFortfahren?"
      )
    ) {
      return;
    }
    try {
      await candidates.anonymise(candidateId);
      reloadCandidate();
    } catch (e: any) {
      alert(`Fehler: ${e?.response?.data?.detail || e.message}`);
    }
  };

  const handleCall = async () => {
    setCallMessage(null);
    try {
      const result = await callsApi.initiate({ candidate_id: candidateId });
      setCallMessage(`Anruf initiiert (SID: ${result.twilio_call_sid})`);
      reloadProtocol();
    } catch (e: any) {
      setCallMessage(`Fehler: ${e?.response?.data?.detail || e.message}`);
    }
  };

  const handleLinkedInImport = async () => {
    const fallback = candidate?.linkedin_url || "";
    const url = prompt(
      "LinkedIn-Profil-URL:",
      fallback
    );
    if (url === null) return;
    const trimmed = url.trim();
    if (!trimmed) return;
    try {
      const result = await candidates.importLinkedIn(candidateId, trimmed);
      const count = result.updated_fields.length;
      alert(
        count === 0
          ? "LinkedIn-Import abgeschlossen: keine neuen Felder."
          : `LinkedIn-Import: ${count} Feld(er) aktualisiert (${result.updated_fields.join(", ")}).`
      );
      reloadCandidate();
    } catch (e: any) {
      alert(`Fehler: ${e?.response?.data?.detail || e.message}`);
    }
  };

  const handleHangup = async (callId: number) => {
    if (!confirm("Laufenden Anruf wirklich beenden?")) return;
    setHangupBusy(callId);
    try {
      await callsApi.hangup(callId);
      reloadProtocol();
    } catch (e: any) {
      alert(`Fehler: ${e?.response?.data?.detail || e.message}`);
    } finally {
      setHangupBusy(null);
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
          <button onClick={handleLinkedInImport} className="btn-secondary">
            LinkedIn importieren
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
        <h2 className="font-display text-lg font-semibold mb-1">
          GDPR / FADP
        </h2>
        <p className="text-xs text-text-muted mb-4">
          Einwilligung und Recht auf Vergessenwerden (Art. 17 DSGVO / Art.
          32 DSG).
        </p>
        <div className="flex flex-wrap items-center gap-4">
          <div className="text-sm">
            <div className="label-mono">Einwilligung</div>
            {candidate.consent_given_at ? (
              <div className="text-text-secondary">
                ✓ erteilt am{" "}
                {new Date(candidate.consent_given_at).toLocaleDateString("de-CH")}
                {candidate.consent_source && (
                  <span className="text-text-muted">
                    {" "}
                    ({candidate.consent_source})
                  </span>
                )}
              </div>
            ) : (
              <div className="text-amber-accent">ausstehend</div>
            )}
          </div>
          <div className="text-sm">
            <div className="label-mono">Status</div>
            {candidate.anonymised ? (
              <div className="text-rose-400">anonymisiert</div>
            ) : (
              <div className="text-text-secondary">aktiv</div>
            )}
          </div>
          <div className="flex-1" />
          {!candidate.consent_given_at && !candidate.anonymised && (
            <button
              onClick={handleRecordConsent}
              className="btn-secondary text-sm"
            >
              Einwilligung vermerken
            </button>
          )}
          {!candidate.anonymised && (
            <button
              onClick={handleAnonymise}
              className="btn-ghost text-sm text-rose-400 hover:bg-rose-500/10"
            >
              Löschen (anonymisieren)
            </button>
          )}
        </div>
      </section>

      <section className="card p-6">
        <h2 className="font-display text-lg font-semibold mb-3">Protokoll</h2>
        {(protocol?.length ?? 0) === 0 && (
          <div className="text-text-muted text-sm">Noch keine Kommunikation.</div>
        )}
        <div className="space-y-2">
          {(protocol ?? []).map((p) => {
            const isCall = p.kind === "call";
            const canHangup =
              isCall &&
              !!p.reference_id &&
              !!p.status &&
              NON_TERMINAL_CALL_STATUSES.has(p.status);
            const duration = formatDuration(p.duration_seconds);
            return (
              <div
                key={`${p.kind}-${p.reference_id}-${p.created_at}`}
                className="p-3 bg-bg-elevated rounded-md"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs uppercase text-text-muted">
                    {p.kind} {p.status ? `· ${p.status}` : ""}
                    {duration ? ` · ${duration}` : ""}
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
                {isCall && p.recording_url && (
                  <audio
                    controls
                    preload="none"
                    src={p.recording_url}
                    className="mt-2 w-full"
                  />
                )}
                {canHangup && (
                  <div className="mt-2">
                    <button
                      onClick={() => handleHangup(p.reference_id!)}
                      disabled={hangupBusy === p.reference_id}
                      className="btn-ghost text-xs text-rose-400 hover:bg-rose-500/10"
                    >
                      {hangupBusy === p.reference_id
                        ? "Beende…"
                        : "Anruf beenden"}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
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
