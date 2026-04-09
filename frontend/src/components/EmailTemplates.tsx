import { useEffect, useMemo, useState } from "react";
import { templates, type EmailTemplate } from "@/lib/api";

/**
 * Email templates editor.
 *
 * Left column lists every template; the right column is a form that
 * edits the selected one. Plain-text only — {{placeholder}} markers
 * are documented inline so the recruiter knows what they can reach.
 */

const LANGUAGES = [
  { value: "de", label: "Deutsch" },
  { value: "en", label: "English" },
  { value: "fr", label: "Français" },
  { value: "it", label: "Italiano" },
];

const PLACEHOLDERS = [
  "{{first_name}}",
  "{{last_name}}",
  "{{full_name}}",
  "{{headline}}",
  "{{skills}}",
  "{{recent_jobs}}",
  "{{agent_name}}",
  "{{company_name}}",
  "{{signature}}",
];

const BLANK_DRAFT: EmailTemplate = {
  id: 0,
  name: "",
  language: "de",
  subject: "",
  body: "",
  is_signature: false,
  created_at: "",
  updated_at: "",
};

export default function EmailTemplates() {
  const [rows, setRows] = useState<EmailTemplate[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [draft, setDraft] = useState<EmailTemplate>(BLANK_DRAFT);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ subject: string; body: string } | null>(
    null
  );

  async function reload() {
    try {
      const list = await templates.list();
      setRows(list);
      if (list.length && selectedId === null && !creating) {
        setSelectedId(list[0].id);
        setDraft(list[0]);
      }
    } catch (e: unknown) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selected = useMemo(
    () => rows.find((r) => r.id === selectedId) || null,
    [rows, selectedId]
  );

  function selectRow(row: EmailTemplate) {
    setCreating(false);
    setSelectedId(row.id);
    setDraft(row);
    setPreview(null);
    setError(null);
  }

  function startCreate() {
    setCreating(true);
    setSelectedId(null);
    setDraft(BLANK_DRAFT);
    setPreview(null);
    setError(null);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      if (creating) {
        const created = await templates.create({
          name: draft.name,
          language: draft.language,
          subject: draft.subject,
          body: draft.body,
          is_signature: draft.is_signature,
        });
        setCreating(false);
        setSelectedId(created.id);
        setDraft(created);
      } else if (selected) {
        const updated = await templates.update(selected.id, {
          name: draft.name,
          language: draft.language,
          subject: draft.subject,
          body: draft.body,
          is_signature: draft.is_signature,
        });
        setDraft(updated);
      }
      await reload();
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || (e as Error).message;
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!selected) return;
    if (!confirm(`Template "${selected.name}" wirklich löschen?`)) return;
    setBusy(true);
    try {
      await templates.delete(selected.id);
      setSelectedId(null);
      setDraft(BLANK_DRAFT);
      await reload();
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function runPreview() {
    if (!selected || creating) return;
    try {
      const p = await templates.preview(selected.id);
      setPreview(p);
    } catch (e: unknown) {
      setError((e as Error).message);
    }
  }

  const isDirty =
    !!selected &&
    (draft.name !== selected.name ||
      draft.language !== selected.language ||
      draft.subject !== selected.subject ||
      draft.body !== selected.body ||
      draft.is_signature !== selected.is_signature);

  return (
    <div className="max-w-6xl mx-auto">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">E-Mail Vorlagen</h1>
          <p className="text-sm text-text-secondary">
            Vorlagen pro Sprache. Platzhalter werden beim Versand ersetzt.
          </p>
        </div>
        <button onClick={startCreate} className="btn-primary h-9 px-4 text-sm">
          + Neue Vorlage
        </button>
      </div>

      <div className="grid grid-cols-12 gap-4">
        {/* Left — template list */}
        <aside className="col-span-4 card p-0 overflow-hidden">
          <div className="max-h-[70vh] overflow-y-auto divide-y divide-bg-border">
            {rows.length === 0 && (
              <div className="p-4 text-sm text-text-secondary">
                Noch keine Vorlagen.
              </div>
            )}
            {rows.map((row) => (
              <button
                key={row.id}
                onClick={() => selectRow(row)}
                className={`w-full text-left px-4 py-3 hover:bg-bg-elevated transition ${
                  selectedId === row.id ? "bg-bg-elevated" : ""
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-sm truncate">
                    {row.name || "(ohne Namen)"}
                  </span>
                  <span className="label-mono text-xs">{row.language}</span>
                </div>
                <div className="text-xs text-text-secondary truncate mt-0.5">
                  {row.is_signature ? "Signatur" : row.subject}
                </div>
              </button>
            ))}
          </div>
        </aside>

        {/* Right — editor */}
        <section className="col-span-8 card p-5">
          {!creating && !selected ? (
            <div className="text-sm text-text-secondary">
              Wähle links eine Vorlage oder erstelle eine neue.
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1">
                    Name
                  </label>
                  <input
                    type="text"
                    value={draft.name}
                    onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                    className="w-full rounded-md border border-bg-border bg-bg-surface px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1">
                    Sprache
                  </label>
                  <select
                    value={draft.language}
                    onChange={(e) =>
                      setDraft({ ...draft, language: e.target.value })
                    }
                    className="w-full rounded-md border border-bg-border bg-bg-surface px-3 py-2 text-sm"
                  >
                    {LANGUAGES.map((l) => (
                      <option key={l.value} value={l.value}>
                        {l.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-text-secondary mb-1">
                  Betreff
                </label>
                <input
                  type="text"
                  value={draft.subject}
                  onChange={(e) =>
                    setDraft({ ...draft, subject: e.target.value })
                  }
                  className="w-full rounded-md border border-bg-border bg-bg-surface px-3 py-2 text-sm"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-xs font-medium text-text-secondary">
                    Inhalt
                  </label>
                  <label className="flex items-center gap-2 text-xs text-text-secondary">
                    <input
                      type="checkbox"
                      checked={draft.is_signature}
                      onChange={(e) =>
                        setDraft({ ...draft, is_signature: e.target.checked })
                      }
                    />
                    Als Signatur verwenden
                  </label>
                </div>
                <textarea
                  value={draft.body}
                  onChange={(e) => setDraft({ ...draft, body: e.target.value })}
                  rows={12}
                  className="w-full rounded-md border border-bg-border bg-bg-surface px-3 py-2 text-sm font-mono"
                />
              </div>

              <div className="text-xs text-text-secondary">
                <div className="mb-1">Verfügbare Platzhalter:</div>
                <div className="flex flex-wrap gap-1.5">
                  {PLACEHOLDERS.map((p) => (
                    <code
                      key={p}
                      className="px-1.5 py-0.5 rounded bg-bg-elevated border border-bg-border"
                    >
                      {p}
                    </code>
                  ))}
                </div>
              </div>

              {error && (
                <div className="rounded-md bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 px-3 py-2 text-xs text-red-700 dark:text-red-300">
                  {error}
                </div>
              )}

              <div className="flex items-center gap-2 pt-2">
                <button
                  onClick={save}
                  disabled={
                    busy ||
                    !draft.name ||
                    !draft.subject ||
                    !draft.body ||
                    (!creating && !isDirty)
                  }
                  className="btn-primary h-9 px-4 text-sm"
                >
                  {busy ? "Speichern…" : creating ? "Erstellen" : "Speichern"}
                </button>
                {!creating && selected && (
                  <>
                    <button
                      onClick={runPreview}
                      className="btn-ghost h-9 px-4 text-sm"
                    >
                      Vorschau
                    </button>
                    <button
                      onClick={remove}
                      disabled={busy}
                      className="btn-ghost h-9 px-4 text-sm text-red-600 hover:text-red-700"
                    >
                      Löschen
                    </button>
                  </>
                )}
              </div>

              {preview && (
                <div className="mt-4 border border-bg-border rounded-md p-4 bg-bg-elevated">
                  <div className="text-xs text-text-secondary mb-1">
                    Vorschau (mit Beispieldaten)
                  </div>
                  <div className="text-sm font-medium mb-2">
                    {preview.subject}
                  </div>
                  <pre className="text-xs whitespace-pre-wrap">
                    {preview.body}
                  </pre>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
