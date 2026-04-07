import StatusBadge from "./StatusBadge";
import type { CallLog } from "@/types";

interface Props {
  call: CallLog;
}

export default function CallPlayer({ call }: Props) {
  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between">
        <div>
          <div className="font-display text-xl font-semibold">
            Call #{call.id}
          </div>
          <div className="text-sm text-text-secondary mt-1">
            {call.from_number} → {call.to_number}
          </div>
        </div>
        <StatusBadge status={call.status} />
      </div>

      {call.recording_url && (
        <audio controls className="w-full" src={call.recording_url}>
          Your browser does not support audio.
        </audio>
      )}

      <div className="grid grid-cols-3 gap-4 text-sm">
        <Field label="Duration" value={call.duration_seconds ? `${call.duration_seconds}s` : null} />
        <Field label="Language" value={call.detected_language?.toUpperCase()} />
        <Field label="Interest" value={call.interest_level} />
      </div>

      {call.summary && (
        <div>
          <div className="label-mono mb-2">Summary</div>
          <p className="text-sm text-text-secondary leading-relaxed">{call.summary}</p>
        </div>
      )}

      {call.next_steps && (
        <div>
          <div className="label-mono mb-2">Next steps</div>
          <p className="text-sm text-text-secondary leading-relaxed">{call.next_steps}</p>
        </div>
      )}

      {call.transcript_segments && call.transcript_segments.length > 0 && (
        <div>
          <div className="label-mono mb-2">Transcript</div>
          <div className="space-y-2 bg-bg-elevated p-4 rounded-md max-h-96 overflow-auto">
            {call.transcript_segments.map((seg, i) => (
              <div key={i} className="text-sm">
                <span
                  className={`font-mono text-xs uppercase mr-2 ${
                    seg.role === "assistant" ? "text-amber-accent" : "text-cyan-link"
                  }`}
                >
                  {seg.role === "assistant" ? "agent" : "candidate"}:
                </span>
                <span className="text-text-secondary">{seg.text}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      {!call.transcript_segments && call.transcript && (
        <div>
          <div className="label-mono mb-2">Transcript</div>
          <pre className="text-sm bg-bg-elevated p-4 rounded-md whitespace-pre-wrap">
            {call.transcript}
          </pre>
        </div>
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
