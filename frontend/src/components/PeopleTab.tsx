import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useLiveEvent } from "@/hooks/useLiveEvents";
import {
  bulk as bulkApi,
  candidates as candidatesApi,
  templates as templatesApi,
  type BulkEmailResult,
  type EmailTemplate,
} from "@/lib/api";
import type { Candidate } from "@/types";
import { useChatDock } from "./chat/ChatDockContext";
import Avatar from "./shared/Avatar";
import StatusBadge from "./StatusBadge";

const PAGE_SIZE = 60;

const STATUS_OPTIONS = [
  "all",
  "new",
  "parsed",
  "info_requested",
  "matched",
  "contacted",
  "interview",
  "placed",
  "rejected",
];

const SORT_OPTIONS = [
  { value: "recent", label: "Zuletzt aktualisiert" },
  { value: "name", label: "Nachname A–Z" },
];

export default function PeopleTab() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState<"recent" | "name">("recent");
  const { open: openChat } = useChatDock();

  const [items, setItems] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);

  // ---- Multi-select + bulk actions ----------------------------------
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkMode, setBulkMode] = useState(false);
  const [showBulkEmail, setShowBulkEmail] = useState(false);
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [bulkTemplateId, setBulkTemplateId] = useState<number | "">("");
  const [bulkSubject, setBulkSubject] = useState("");
  const [bulkBody, setBulkBody] = useState("");
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkResult, setBulkResult] = useState<BulkEmailResult | null>(null);

  function toggleSelect(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  function selectAllOnPage() {
    setSelected(new Set(items.map((c) => c.id)));
  }
  function clearSelection() {
    setSelected(new Set());
  }

  async function openBulkEmailDialog() {
    if (selected.size === 0) return;
    try {
      const list = await templatesApi.list();
      setTemplates(list.filter((t) => !t.is_signature));
    } catch {
      setTemplates([]);
    }
    setBulkTemplateId("");
    setBulkSubject("");
    setBulkBody("");
    setBulkResult(null);
    setShowBulkEmail(true);
  }

  async function runBulkEmail() {
    if (selected.size === 0) return;
    setBulkBusy(true);
    try {
      const ids = Array.from(selected);
      const req = {
        candidate_ids: ids,
        ...(bulkTemplateId ? { template_id: Number(bulkTemplateId) } : {}),
        ...(!bulkTemplateId && bulkSubject && bulkBody
          ? { subject: bulkSubject, body: bulkBody }
          : {}),
      };
      const res = await bulkApi.email(req);
      setBulkResult(res);
    } finally {
      setBulkBusy(false);
    }
  }

  function triggerDownload(blob: Blob, filename: string) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  async function exportSelected() {
    if (selected.size === 0) return;
    const blob = await bulkApi.exportCsv(Array.from(selected));
    triggerDownload(blob, "candidates-selected.csv");
  }

  async function exportAll() {
    const blob = await bulkApi.exportAllCsv();
    triggerDownload(blob, "candidates.csv");
  }

  const fetchPage = async (offset: number) => {
    const rows = await candidatesApi.list({
      q: q.trim() || undefined,
      status: status === "all" ? undefined : status,
      sort,
      limit: PAGE_SIZE,
      offset,
    });
    return rows;
  };

  const reload = async () => {
    setLoading(true);
    try {
      const rows = await fetchPage(0);
      setItems(rows);
      setHasMore(rows.length === PAGE_SIZE);
    } finally {
      setLoading(false);
    }
  };

  const loadMore = async () => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const rows = await fetchPage(items.length);
      setItems((prev) => [...prev, ...rows]);
      setHasMore(rows.length === PAGE_SIZE);
    } finally {
      setLoadingMore(false);
    }
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, status, sort]);

  // New inbound message → list sort order may have changed; reload.
  useLiveEvent("message.new", () => {
    reload();
  });

  const heading = useMemo(() => {
    if (q) return `Treffer für "${q}"`;
    if (status !== "all") return `Kandidaten · ${status.replace("_", " ")}`;
    return "Aktuelle Kandidaten";
  }, [q, status]);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">People</h1>
        <p className="text-text-secondary text-sm mt-1">
          Suche nach Name, E-Mail, Telefon oder Adresse.
        </p>
      </div>

      {/* Single prominent search bar + dropdowns */}
      <div className="card p-3 flex flex-col md:flex-row md:items-center gap-3">
        <input
          type="search"
          placeholder="Name, E-Mail, Telefon, Adresse…"
          className="input md:flex-1"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          autoFocus
        />
        <select
          className="input md:w-48"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s === "all" ? "Alle Status" : s.replace("_", " ")}
            </option>
          ))}
        </select>
        <select
          className="input md:w-52"
          value={sort}
          onChange={(e) => setSort(e.target.value as "recent" | "name")}
        >
          {SORT_OPTIONS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </div>

      <section className="space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <h2 className="label-mono">{heading}</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                setBulkMode((v) => !v);
                clearSelection();
              }}
              className="btn-ghost text-xs"
            >
              {bulkMode ? "✕ Auswahl beenden" : "☐ Auswählen"}
            </button>
            <button onClick={exportAll} className="btn-ghost text-xs">
              CSV (alle)
            </button>
            <button onClick={reload} className="btn-ghost text-xs">
              ↻ Neu laden
            </button>
          </div>
        </div>

        {bulkMode && (
          <div className="card p-3 flex flex-wrap items-center gap-3 text-sm">
            <span className="label-mono">
              {selected.size} ausgewählt
            </span>
            <button
              onClick={selectAllOnPage}
              className="btn-ghost text-xs"
              disabled={items.length === 0}
            >
              Alle auf dieser Seite
            </button>
            <button
              onClick={clearSelection}
              className="btn-ghost text-xs"
              disabled={selected.size === 0}
            >
              Zurücksetzen
            </button>
            <div className="flex-1" />
            <button
              onClick={exportSelected}
              className="btn-secondary text-xs"
              disabled={selected.size === 0}
            >
              CSV exportieren
            </button>
            <button
              onClick={openBulkEmailDialog}
              className="btn-primary text-xs"
              disabled={selected.size === 0}
            >
              E-Mail senden
            </button>
          </div>
        )}

        {loading && <div className="text-text-muted text-sm">Lade…</div>}
        {!loading && items.length === 0 && (
          <div className="card p-8 text-center text-text-muted">
            Keine Kandidaten gefunden.
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {items.map((c) => {
            const name =
              c.full_name ||
              [c.first_name, c.last_name].filter(Boolean).join(" ") ||
              c.email ||
              "—";
            const isSelected = selected.has(c.id);
            return (
              <div
                key={c.id}
                className={`card p-4 flex items-center gap-4 transition-colors ${
                  isSelected
                    ? "border-amber-accent/60"
                    : "hover:border-amber-accent/40"
                }`}
              >
                {bulkMode && (
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggleSelect(c.id)}
                    className="h-4 w-4 accent-amber-accent"
                    aria-label={`Kandidat ${name} auswählen`}
                  />
                )}
                <Avatar name={name} src={c.photo_url} size={52} />
                <div className="flex-1 min-w-0">
                  <Link
                    to={`/people/${c.id}`}
                    className="font-medium truncate hover:text-amber-accent block"
                    title={name}
                  >
                    {name}
                  </Link>
                  <div className="text-xs text-text-muted truncate">
                    {c.email || "—"} · {c.phone || "—"}
                  </div>
                  <div className="text-xs text-text-muted truncate">
                    {c.address || c.location || ""}
                  </div>
                  <div className="mt-1">
                    <StatusBadge status={c.status} />
                  </div>
                </div>
                <button
                  onClick={() => openChat(c.id, name, c.photo_url)}
                  className="btn-secondary text-xs px-3 py-1.5"
                  title="AI Chat öffnen"
                >
                  Chat
                </button>
              </div>
            );
          })}
        </div>

        {hasMore && (
          <div className="flex justify-center pt-2">
            <button
              onClick={loadMore}
              disabled={loadingMore}
              className="btn-secondary text-sm"
            >
              {loadingMore ? "Lade…" : "Mehr laden"}
            </button>
          </div>
        )}
      </section>

      {/* ---- Bulk email modal ---------------------------------------- */}
      {showBulkEmail && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4">
          <div className="card max-w-lg w-full p-5 space-y-4">
            <div>
              <h3 className="text-lg font-semibold">
                E-Mail an {selected.size} Kandidat
                {selected.size === 1 ? "" : "en"}
              </h3>
              <p className="text-xs text-text-secondary mt-1">
                Entweder eine Vorlage wählen oder Betreff und Text direkt
                eingeben.
              </p>
            </div>

            {bulkResult ? (
              <div className="space-y-3">
                <div className="rounded-md bg-bg-elevated border border-bg-border p-3 text-sm">
                  <div>
                    Versendet: <strong>{bulkResult.sent}</strong> ·
                    Fehlgeschlagen: <strong>{bulkResult.failed}</strong>
                  </div>
                  {bulkResult.errors.length > 0 && (
                    <ul className="mt-2 text-xs text-text-secondary list-disc list-inside">
                      {bulkResult.errors.slice(0, 10).map((e) => (
                        <li key={e.candidate_id}>
                          #{e.candidate_id}: {e.reason}
                        </li>
                      ))}
                      {bulkResult.errors.length > 10 && (
                        <li>… und {bulkResult.errors.length - 10} weitere</li>
                      )}
                    </ul>
                  )}
                </div>
                <div className="flex justify-end">
                  <button
                    onClick={() => {
                      setShowBulkEmail(false);
                      clearSelection();
                      setBulkMode(false);
                    }}
                    className="btn-primary text-sm"
                  >
                    Schliessen
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1">
                    Vorlage
                  </label>
                  <select
                    value={bulkTemplateId}
                    onChange={(e) =>
                      setBulkTemplateId(
                        e.target.value ? Number(e.target.value) : ""
                      )
                    }
                    className="w-full rounded-md border border-bg-border bg-bg-surface px-3 py-2 text-sm"
                  >
                    <option value="">— Keine (manuell eingeben) —</option>
                    {templates.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name} ({t.language})
                      </option>
                    ))}
                  </select>
                </div>
                {!bulkTemplateId && (
                  <>
                    <div>
                      <label className="block text-xs font-medium text-text-secondary mb-1">
                        Betreff
                      </label>
                      <input
                        type="text"
                        value={bulkSubject}
                        onChange={(e) => setBulkSubject(e.target.value)}
                        className="w-full rounded-md border border-bg-border bg-bg-surface px-3 py-2 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-text-secondary mb-1">
                        Inhalt
                      </label>
                      <textarea
                        rows={6}
                        value={bulkBody}
                        onChange={(e) => setBulkBody(e.target.value)}
                        className="w-full rounded-md border border-bg-border bg-bg-surface px-3 py-2 text-sm"
                      />
                    </div>
                  </>
                )}
                <div className="flex justify-end gap-2 pt-2">
                  <button
                    onClick={() => setShowBulkEmail(false)}
                    className="btn-ghost text-sm"
                    disabled={bulkBusy}
                  >
                    Abbrechen
                  </button>
                  <button
                    onClick={runBulkEmail}
                    disabled={
                      bulkBusy ||
                      (!bulkTemplateId && (!bulkSubject || !bulkBody))
                    }
                    className="btn-primary text-sm"
                  >
                    {bulkBusy ? "Sende…" : "Senden"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
