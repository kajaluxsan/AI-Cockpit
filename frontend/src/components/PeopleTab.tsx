import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "@/hooks/useApi";
import { candidates as candidatesApi } from "@/lib/api";
import { useChatDock } from "./chat/ChatDockContext";
import Avatar from "./shared/Avatar";
import StatusBadge from "./StatusBadge";

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

  const { data, loading, reload } = useApi(
    () =>
      candidatesApi.list({
        q: q.trim() || undefined,
        status: status === "all" ? undefined : status,
        sort,
        limit: 60,
      }),
    [q, status, sort]
  );

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
        <div className="flex items-center justify-between">
          <h2 className="label-mono">{heading}</h2>
          <button onClick={reload} className="btn-ghost text-xs">
            ↻ Neu laden
          </button>
        </div>

        {loading && <div className="text-text-muted text-sm">Lade…</div>}
        {!loading && (data?.length ?? 0) === 0 && (
          <div className="card p-8 text-center text-text-muted">
            Keine Kandidaten gefunden.
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {(data ?? []).map((c) => {
            const name =
              c.full_name ||
              [c.first_name, c.last_name].filter(Boolean).join(" ") ||
              c.email ||
              "—";
            return (
              <div
                key={c.id}
                className="card p-4 flex items-center gap-4 hover:border-amber-accent/40 transition-colors"
              >
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
      </section>
    </div>
  );
}
