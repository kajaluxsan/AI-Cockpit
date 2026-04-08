import ChatWindow from "./ChatWindow";
import { useChatDock } from "./ChatDockContext";

export default function ChatDock() {
  const { windows, maxVisible, close, toggleMinimize } = useChatDock();
  if (windows.length === 0) return null;

  const visible = windows.slice(0, maxVisible);
  const overflow = windows.slice(maxVisible);

  return (
    <div className="fixed bottom-0 right-4 z-40 flex items-end gap-3 pointer-events-none">
      {overflow.length > 0 && (
        <div className="pointer-events-auto bg-bg-surface border border-bg-border rounded-t-lg px-3 py-2 text-xs text-text-muted">
          +{overflow.length} weitere
        </div>
      )}
      {visible.map((w) => (
        <div key={w.candidateId} className="pointer-events-auto">
          <ChatWindow
            candidateId={w.candidateId}
            name={w.name}
            photoUrl={w.photoUrl}
            minimized={w.minimized}
            onClose={() => close(w.candidateId)}
            onToggleMinimize={() => toggleMinimize(w.candidateId)}
          />
        </div>
      ))}
    </div>
  );
}
