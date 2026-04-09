import { useEffect, useState } from "react";
import {
  reports,
  type CallsReport,
  type EmailsReport,
  type PipelineReport,
  type SourcesReport,
  type SummaryReport,
  type TimeseriesReport,
} from "@/lib/api";

/**
 * Reports dashboard.
 *
 * Fetches every report endpoint in parallel on mount / when the time
 * window changes, then renders each block inline. Pure CSS bars — no
 * charting library dependency, keeps the bundle small and the layout
 * predictable across the dark/light themes.
 */
export default function ReportingDashboard() {
  const [days, setDays] = useState(30);
  const [summary, setSummary] = useState<SummaryReport | null>(null);
  const [pipe, setPipe] = useState<PipelineReport | null>(null);
  const [src, setSrc] = useState<SourcesReport | null>(null);
  const [callsR, setCallsR] = useState<CallsReport | null>(null);
  const [emailsR, setEmailsR] = useState<EmailsReport | null>(null);
  const [ts, setTs] = useState<TimeseriesReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [s, p, so, c, e, t] = await Promise.all([
          reports.summary(days),
          reports.pipeline(),
          reports.sources(),
          reports.calls(days),
          reports.emails(days),
          reports.timeseries(days),
        ]);
        if (cancelled) return;
        setSummary(s);
        setPipe(p);
        setSrc(so);
        setCallsR(c);
        setEmailsR(e);
        setTs(t);
      } catch (err: unknown) {
        if (!cancelled) setError((err as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [days]);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Reports</h1>
          <p className="text-sm text-text-secondary">
            Pipeline, Quellen, Anrufe und E-Mails auf einen Blick.
          </p>
        </div>
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="rounded-md border border-bg-border bg-bg-surface px-3 py-2 text-sm"
        >
          <option value={7}>Letzte 7 Tage</option>
          <option value={30}>Letzte 30 Tage</option>
          <option value={90}>Letzte 90 Tage</option>
          <option value={180}>Letzte 180 Tage</option>
          <option value={365}>Letztes Jahr</option>
        </select>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 px-3 py-2 text-xs text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {loading && !summary && (
        <div className="text-sm text-text-secondary">Wird geladen…</div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* KPI tiles                                                      */}
      {/* ------------------------------------------------------------- */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <Kpi label="Neue Kandidaten" value={summary.new_candidates} />
          <Kpi label="Neue Matches" value={summary.new_matches} />
          <Kpi label="Platzierungen" value={summary.placements} />
          <Kpi label="Offene Stellen" value={summary.open_jobs} />
          <Kpi
            label="Platzierungsrate"
            value={`${Math.round(summary.placement_rate * 100)}%`}
          />
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* Pipeline funnel                                                */}
      {/* ------------------------------------------------------------- */}
      {pipe && (
        <section className="card p-5">
          <h2 className="font-semibold text-sm mb-3">Pipeline</h2>
          <Bars
            data={Object.entries(pipe.stages).map(([k, v]) => ({
              label: k,
              value: v,
            }))}
          />
        </section>
      )}

      {/* ------------------------------------------------------------- */}
      {/* Sources                                                        */}
      {/* ------------------------------------------------------------- */}
      {src && (
        <section className="card p-5">
          <h2 className="font-semibold text-sm mb-3">Quellen</h2>
          <Bars
            data={Object.entries(src.sources).map(([k, v]) => ({
              label: k,
              value: v,
            }))}
          />
        </section>
      )}

      {/* ------------------------------------------------------------- */}
      {/* Calls                                                          */}
      {/* ------------------------------------------------------------- */}
      {callsR && (
        <section className="card p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold text-sm">Anrufe</h2>
            <span className="label-mono text-xs">
              Ø Antwortrate: {Math.round(callsR.answered_rate * 100)}%
            </span>
          </div>
          <Bars
            data={Object.entries(callsR.by_status).map(([k, v]) => ({
              label: k,
              value: v,
            }))}
          />
          <div className="text-xs text-text-secondary mt-3">
            Gesamt: {callsR.total} · Outbound:{" "}
            {callsR.by_direction.outbound ?? 0} · Inbound:{" "}
            {callsR.by_direction.inbound ?? 0}
          </div>
        </section>
      )}

      {/* ------------------------------------------------------------- */}
      {/* Emails                                                         */}
      {/* ------------------------------------------------------------- */}
      {emailsR && (
        <section className="card p-5">
          <h2 className="font-semibold text-sm mb-3">E-Mails</h2>
          <Bars
            data={Object.entries(emailsR.by_direction).map(([k, v]) => ({
              label: k,
              value: v,
            }))}
          />
          <div className="text-xs text-text-secondary mt-3">
            Gesamt: {emailsR.total}
          </div>
        </section>
      )}

      {/* ------------------------------------------------------------- */}
      {/* Timeseries                                                     */}
      {/* ------------------------------------------------------------- */}
      {ts && (
        <section className="card p-5">
          <h2 className="font-semibold text-sm mb-3">Neue Kandidaten pro Tag</h2>
          <Sparkline data={ts.series.map((p) => p.count)} />
          <div className="text-xs text-text-secondary mt-2">
            Gesamt im Fenster: {ts.total}
          </div>
        </section>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Presentation helpers — kept local so this file stays self-contained
// ---------------------------------------------------------------------------
function Kpi({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="card p-4">
      <div className="text-xs text-text-secondary">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
    </div>
  );
}

function Bars({ data }: { data: { label: string; value: number }[] }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div className="space-y-1.5">
      {data.map((d) => (
        <div key={d.label} className="flex items-center gap-2 text-xs">
          <div className="w-32 truncate text-text-secondary">{d.label}</div>
          <div className="flex-1 h-4 bg-bg-elevated rounded overflow-hidden">
            <div
              className="h-full bg-amber-accent"
              style={{ width: `${(d.value / max) * 100}%` }}
            />
          </div>
          <div className="w-10 text-right font-mono">{d.value}</div>
        </div>
      ))}
    </div>
  );
}

function Sparkline({ data }: { data: number[] }) {
  if (!data.length) {
    return <div className="text-xs text-text-secondary">Keine Daten.</div>;
  }
  const max = Math.max(1, ...data);
  const w = 600;
  const h = 60;
  const step = w / Math.max(1, data.length - 1);
  const points = data
    .map((v, i) => `${i * step},${h - (v / max) * h}`)
    .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-16">
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        className="text-amber-accent"
      />
    </svg>
  );
}
