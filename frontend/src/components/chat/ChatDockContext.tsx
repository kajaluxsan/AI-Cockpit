import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  ReactNode,
} from "react";

export interface ChatWindowState {
  candidateId: number;
  name: string;
  photoUrl: string | null;
  minimized: boolean;
}

interface ChatDockValue {
  windows: ChatWindowState[];
  maxVisible: number;
  open: (candidateId: number, name: string, photoUrl?: string | null) => void;
  close: (candidateId: number) => void;
  toggleMinimize: (candidateId: number) => void;
  setMinimized: (candidateId: number, minimized: boolean) => void;
}

const ChatDockCtx = createContext<ChatDockValue | null>(null);

// Width of a single docked chat window (incl. gap)
const WINDOW_WIDTH = 340;
const DOCK_PADDING = 48;

function computeMaxVisible(vw: number): number {
  const available = Math.max(0, vw - DOCK_PADDING);
  const count = Math.floor(available / WINDOW_WIDTH);
  return Math.max(1, Math.min(5, count));
}

export function ChatDockProvider({ children }: { children: ReactNode }) {
  const [windows, setWindows] = useState<ChatWindowState[]>([]);
  const [maxVisible, setMaxVisible] = useState(() =>
    computeMaxVisible(typeof window !== "undefined" ? window.innerWidth : 1280)
  );

  useEffect(() => {
    const onResize = () => setMaxVisible(computeMaxVisible(window.innerWidth));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const open = useCallback(
    (candidateId: number, name: string, photoUrl: string | null = null) => {
      setWindows((prev) => {
        const existing = prev.find((w) => w.candidateId === candidateId);
        if (existing) {
          // Un-minimize and move to the front
          return [
            { ...existing, minimized: false },
            ...prev.filter((w) => w.candidateId !== candidateId),
          ];
        }
        return [{ candidateId, name, photoUrl, minimized: false }, ...prev];
      });
    },
    []
  );

  const close = useCallback((candidateId: number) => {
    setWindows((prev) => prev.filter((w) => w.candidateId !== candidateId));
  }, []);

  const toggleMinimize = useCallback((candidateId: number) => {
    setWindows((prev) =>
      prev.map((w) =>
        w.candidateId === candidateId ? { ...w, minimized: !w.minimized } : w
      )
    );
  }, []);

  const setMinimized = useCallback((candidateId: number, minimized: boolean) => {
    setWindows((prev) =>
      prev.map((w) => (w.candidateId === candidateId ? { ...w, minimized } : w))
    );
  }, []);

  const value = useMemo<ChatDockValue>(
    () => ({ windows, maxVisible, open, close, toggleMinimize, setMinimized }),
    [windows, maxVisible, open, close, toggleMinimize, setMinimized]
  );

  return <ChatDockCtx.Provider value={value}>{children}</ChatDockCtx.Provider>;
}

export function useChatDock(): ChatDockValue {
  const ctx = useContext(ChatDockCtx);
  if (!ctx) throw new Error("useChatDock must be used inside ChatDockProvider");
  return ctx;
}
