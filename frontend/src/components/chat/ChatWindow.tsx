import { useEffect, useRef, useState } from "react";
import { calls as callsApi, chat as chatApi, candidates } from "@/lib/api";
import type { ChatMessage } from "@/types";
import Avatar from "../shared/Avatar";

interface Props {
  candidateId: number;
  name: string;
  photoUrl: string | null;
  minimized: boolean;
  onClose: () => void;
  onToggleMinimize: () => void;
}

export default function ChatWindow({
  candidateId,
  name,
  photoUrl,
  minimized,
  onClose,
  onToggleMinimize,
}: Props) {
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [phone, setPhone] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [h, c] = await Promise.all([
          chatApi.history(candidateId),
          candidates.get(candidateId),
        ]);
        if (!cancelled) {
          setHistory(h);
          setEmail(c.email);
          setPhone(c.phone);
        }
      } catch (e: any) {
        if (!cancelled) {
          setActionMessage("Konnte Chat nicht laden.");
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [candidateId]);

  useEffect(() => {
    if (!minimized && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [history, minimized]);

  const send = async () => {
    const content = input.trim();
    if (!content || sending) return;
    setSending(true);
    setActionMessage(null);
    try {
      const updated = await chatApi.send(candidateId, content, true);
      setHistory(updated);
      setInput("");
    } catch (e: any) {
      setActionMessage(e?.response?.data?.detail || e.message || "Fehler");
    } finally {
      setSending(false);
    }
  };

  const doCall = async () => {
    setActionMessage(null);
    try {
      const r = await callsApi.initiate({ candidate_id: candidateId });
      setActionMessage(`Anruf gestartet (${r.twilio_call_sid || "?"})`);
    } catch (e: any) {
      setActionMessage(`Anruf fehlgeschlagen: ${e?.response?.data?.detail || e.message}`);
    }
  };

  const mailto = email ? `mailto:${email}` : undefined;
  const telTo = phone ? `tel:${phone}` : undefined;

  return (
    <div
      className="w-[320px] bg-bg-surface border border-bg-border rounded-t-lg shadow-2xl flex flex-col"
      style={{ height: minimized ? 44 : 460 }}
    >
      {/* Header */}
      <div
        className="h-11 px-3 flex items-center gap-2 border-b border-bg-border cursor-pointer select-none"
        onClick={onToggleMinimize}
      >
        <Avatar name={name} src={photoUrl} size={28} />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium truncate">{name}</div>
          <div className="text-[10px] text-text-muted truncate">AI Chat</div>
        </div>
        <div className="flex items-center gap-1">
          <IconButton
            title="E-Mail"
            onClick={(e) => {
              e.stopPropagation();
              if (mailto) window.open(mailto);
            }}
            disabled={!mailto}
          >
            ✉
          </IconButton>
          <IconButton
            title="Anruf"
            onClick={(e) => {
              e.stopPropagation();
              if (telTo) doCall();
            }}
            disabled={!telTo}
          >
            ☎
          </IconButton>
          <IconButton
            title={minimized ? "Öffnen" : "Minimieren"}
            onClick={(e) => {
              e.stopPropagation();
              onToggleMinimize();
            }}
          >
            {minimized ? "▴" : "▾"}
          </IconButton>
          <IconButton
            title="Schliessen"
            onClick={(e) => {
              e.stopPropagation();
              onClose();
            }}
          >
            ×
          </IconButton>
        </div>
      </div>

      {!minimized && (
        <>
          <div
            ref={scrollRef}
            className="flex-1 p-3 overflow-y-auto space-y-2"
          >
            {history.length === 0 && (
              <div className="text-xs text-text-muted">
                Sag mir, was ich mit {name} tun soll. Beispiele: "Schreib ihm
                eine kurze Mail und frag nach Gehaltswunsch", "Ruf ihn an und
                kläre Verfügbarkeit".
              </div>
            )}
            {history.map((m) => (
              <Bubble key={m.id} message={m} />
            ))}
            {sending && (
              <div className="text-xs text-text-muted animate-pulse">denkt…</div>
            )}
            {actionMessage && (
              <div className="text-xs text-amber-accent">{actionMessage}</div>
            )}
          </div>

          <div className="p-2 border-t border-bg-border flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder="Anweisung an den AI…"
              className="input text-sm flex-1 py-1.5"
            />
            <button
              onClick={send}
              disabled={sending || !input.trim()}
              className="btn-primary text-xs px-3 py-1.5"
            >
              Senden
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function Bubble({ message }: { message: ChatMessage }) {
  if (message.role === "tool") {
    return (
      <div className="text-[11px] font-mono text-text-muted border-l-2 border-amber-accent pl-2">
        → {message.tool_name}: {message.content}
      </div>
    );
  }
  const isUser = message.role === "user";
  return (
    <div
      className={`max-w-[80%] rounded-md px-3 py-2 text-sm ${
        isUser
          ? "ml-auto bg-amber-accent/10 text-text-primary"
          : "bg-bg-elevated text-text-secondary"
      }`}
    >
      {message.content}
      {message.tool_name && (
        <div className="text-[10px] font-mono text-amber-accent mt-1 uppercase">
          action · {message.tool_name}
        </div>
      )}
    </div>
  );
}

function IconButton({
  children,
  onClick,
  title,
  disabled,
}: {
  children: React.ReactNode;
  onClick: (e: React.MouseEvent) => void;
  title: string;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className="w-7 h-7 rounded flex items-center justify-center text-text-secondary hover:text-amber-accent hover:bg-bg-elevated disabled:opacity-30 disabled:cursor-not-allowed text-sm"
    >
      {children}
    </button>
  );
}
