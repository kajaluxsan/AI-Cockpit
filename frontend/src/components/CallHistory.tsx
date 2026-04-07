import { useState } from "react";
import { useApi } from "@/hooks/useApi";
import { calls } from "@/lib/api";
import StatusBadge from "./StatusBadge";
import CallPlayer from "./CallPlayer";
import type { CallLog } from "@/types";

export default function CallHistory() {
  const { data, loading } = useApi(() => calls.list(), []);
  const [selected, setSelected] = useState<CallLog | null>(null);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold tracking-tight">Call History</h1>
        <p className="text-text-secondary mt-1">All voice agent calls with transcripts.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="card overflow-hidden">
          <div className="border-b border-bg-border p-3 label-mono">Calls</div>
          {loading && <div className="p-4 text-text-muted">Loading…</div>}
          <div className="divide-y divide-bg-border max-h-[600px] overflow-auto">
            {(data ?? []).map((call) => (
              <button
                key={call.id}
                onClick={() => setSelected(call)}
                className={`w-full text-left p-4 hover:bg-bg-elevated transition-colors ${
                  selected?.id === call.id ? "bg-bg-elevated" : ""
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-sm">{call.to_number || "—"}</span>
                  <StatusBadge status={call.status} />
                </div>
                <div className="text-xs text-text-muted mt-1">
                  {new Date(call.created_at).toLocaleString("de-CH")}
                </div>
                {call.detected_language && (
                  <div className="text-xs text-amber-accent mt-1">
                    {call.detected_language.toUpperCase()}
                  </div>
                )}
              </button>
            ))}
            {!loading && (!data || data.length === 0) && (
              <div className="p-4 text-text-muted text-sm">No calls yet.</div>
            )}
          </div>
        </div>

        <div className="lg:col-span-2 card p-6">
          {selected ? (
            <CallPlayer call={selected} />
          ) : (
            <div className="text-text-muted text-sm">Select a call to view details.</div>
          )}
        </div>
      </div>
    </div>
  );
}
