import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useLiveEvent } from "@/hooks/useLiveEvents";
import { messages as messagesApi } from "@/lib/api";
import type { Message } from "@/types";
import Avatar from "./shared/Avatar";

const PAGE_SIZE = 50;

export default function MessagesTab() {
  const [onlyUnanswered, setOnlyUnanswered] = useState(true);
  const [items, setItems] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [hasMore, setHasMore] = useState(false);
  const [displayLimit, setDisplayLimit] = useState(PAGE_SIZE);

  const reload = async () => {
    setLoading(true);
    try {
      // Backend /api/messages does not paginate by offset yet; we fetch a
      // generous window and render it incrementally client-side.
      const rows = await messagesApi.list({
        only_unanswered: onlyUnanswered,
        limit: 500,
      });
      setItems(rows);
      setDisplayLimit(PAGE_SIZE);
      setHasMore(rows.length > PAGE_SIZE);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onlyUnanswered]);

  // Live-refresh when a new inbound message arrives (email poller or webhook)
  useLiveEvent("message.new", () => {
    reload();
  });

  const loadMore = () => {
    const next = displayLimit + PAGE_SIZE;
    setDisplayLimit(next);
    setHasMore(next < items.length);
  };

  const toggleRead = async (id: number, answered: boolean) => {
    await messagesApi.markRead(id, answered);
    reload();
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">
            Messages
          </h1>
          <p className="text-text-secondary text-sm mt-1">
            Neue Nachrichten von Kandidaten und aus externen Systemen.
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm text-text-secondary">
          <input
            type="checkbox"
            checked={onlyUnanswered}
            onChange={(e) => setOnlyUnanswered(e.target.checked)}
          />
          Nur ungelesen
        </label>
      </div>

      {loading && <div className="text-text-muted">Lade…</div>}
      {!loading && items.length === 0 && (
        <div className="card p-10 text-center text-text-muted">
          Keine neuen Nachrichten.
        </div>
      )}

      <div className="space-y-2">
        {items.slice(0, displayLimit).map((m) => (
          <div
            key={m.id}
            className={`card p-4 flex items-start gap-4 ${
              !m.answered ? "border-amber-accent/30" : ""
            }`}
          >
            <Avatar
              name={m.candidate_name || m.from_address}
              src={m.candidate_photo_url}
              size={44}
            />
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <div className="font-medium truncate">
                  {m.candidate_id ? (
                    <Link
                      to={`/people/${m.candidate_id}`}
                      className="hover:text-amber-accent"
                    >
                      {m.candidate_name || m.from_address || "Unbekannt"}
                    </Link>
                  ) : (
                    m.from_address || "Unbekannt"
                  )}
                </div>
                <div className="label-mono whitespace-nowrap">
                  {new Date(m.created_at).toLocaleString("de-CH")}
                </div>
              </div>
              <div className="text-sm text-text-primary mt-0.5 truncate">
                {m.subject || "(kein Betreff)"}
              </div>
              {m.body && (
                <p className="text-xs text-text-muted mt-1 line-clamp-2">
                  {m.body}
                </p>
              )}
            </div>
            <button
              onClick={() => toggleRead(m.id, !m.answered)}
              className="btn-ghost text-xs"
            >
              {m.answered ? "als ungelesen" : "als gelesen"}
            </button>
          </div>
        ))}
      </div>

      {hasMore && (
        <div className="flex justify-center pt-2">
          <button onClick={loadMore} className="btn-secondary text-sm">
            Mehr laden
          </button>
        </div>
      )}
    </div>
  );
}
