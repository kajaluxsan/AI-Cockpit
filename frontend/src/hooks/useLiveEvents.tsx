/**
 * Live events pub/sub wired to the backend WebSocket at /api/events/ws.
 *
 * - `LiveEventsProvider` wraps the app, opens one long-lived WebSocket and
 *   fans out incoming events to any registered listener.
 * - `useLiveEvent(kind, handler)` subscribes a component to a specific
 *   event kind; the handler is called every time that event arrives.
 * - Reconnects automatically with exponential backoff.
 *
 * The project uses a custom `useApi` hook (not React Query), so we can't
 * just invalidate queries globally — each list/detail view registers its
 * own listener and calls `reload()` when the relevant kind arrives.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  type ReactNode,
} from "react";

const BASE_URL =
  (import.meta as any).env?.VITE_API_URL || "http://localhost:8000";

function toWsUrl(httpUrl: string): string {
  return httpUrl.replace(/^http/i, (m) =>
    m.toLowerCase() === "https" ? "wss" : "ws"
  );
}

export type LiveEvent = {
  kind: string;
  payload: Record<string, any>;
};

type Listener = (event: LiveEvent) => void;

type Bus = {
  subscribe: (kind: string, listener: Listener) => () => void;
};

const LiveEventsContext = createContext<Bus | null>(null);

export function LiveEventsProvider({ children }: { children: ReactNode }) {
  const listenersRef = useRef<Map<string, Set<Listener>>>(new Map());

  const subscribe = useCallback((kind: string, listener: Listener) => {
    const map = listenersRef.current;
    let set = map.get(kind);
    if (!set) {
      set = new Set();
      map.set(kind, set);
    }
    set.add(listener);
    return () => {
      set!.delete(listener);
      if (set!.size === 0) map.delete(kind);
    };
  }, []);

  useEffect(() => {
    let disposed = false;
    let retry = 0;
    let socket: WebSocket | null = null;

    const connect = () => {
      if (disposed) return;
      const url = `${toWsUrl(BASE_URL)}/api/events/ws`;
      socket = new WebSocket(url);

      socket.onopen = () => {
        retry = 0;
      };
      socket.onmessage = (ev) => {
        let evt: LiveEvent | null = null;
        try {
          evt = JSON.parse(ev.data);
        } catch {
          return;
        }
        if (!evt || !evt.kind) return;
        if (evt.kind === "hello" || evt.kind === "ping") return;
        const set = listenersRef.current.get(evt.kind);
        if (!set) return;
        for (const fn of set) {
          try {
            fn(evt);
          } catch {
            /* listener errors should not break the bus */
          }
        }
      };
      socket.onerror = () => {
        try {
          socket?.close();
        } catch {
          /* noop */
        }
      };
      socket.onclose = () => {
        if (disposed) return;
        const delay = Math.min(30_000, 500 * 2 ** retry++);
        setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      disposed = true;
      try {
        socket?.close();
      } catch {
        /* noop */
      }
    };
  }, []);

  const bus = useMemo<Bus>(() => ({ subscribe }), [subscribe]);
  return (
    <LiveEventsContext.Provider value={bus}>
      {children}
    </LiveEventsContext.Provider>
  );
}

/**
 * Register a listener for a specific event kind. The listener is stable
 * across renders (stored in a ref) so callers can pass an inline arrow
 * function without accidentally resubscribing every render.
 */
export function useLiveEvent(
  kind: string,
  handler: (event: LiveEvent) => void
): void {
  const bus = useContext(LiveEventsContext);
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    if (!bus) return;
    const unsubscribe = bus.subscribe(kind, (ev) => handlerRef.current(ev));
    return unsubscribe;
  }, [bus, kind]);
}
