import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";
import { auth as authApi, http } from "@/lib/api";
import type { AuthUser } from "@/lib/api";

/**
 * Global authentication context.
 *
 * Responsibilities:
 * - On mount, probe ``GET /api/auth/me`` to find out whether the user
 *   still has a valid session cookie (survives page refresh).
 * - Expose ``login`` / ``logout`` that update the context atomically.
 * - Install a response interceptor that redirects to /login on 401 so
 *   every screen transparently handles session expiry.
 *
 * The session cookie itself is httpOnly — JS never touches it. All we
 * track locally is the decoded user object returned by the backend.
 */

type AuthState =
  | { status: "loading" }
  | { status: "authed"; user: AuthUser }
  | { status: "anon" };

type AuthContextValue = {
  state: AuthState;
  user: AuthUser | null;
  isAuthed: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<AuthUser>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  const refresh = useCallback(async () => {
    try {
      const user = await authApi.me();
      setState({ status: "authed", user });
    } catch {
      setState({ status: "anon" });
    }
  }, []);

  // Boot-time probe: ask the backend who we are right now.
  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Global 401 handler: any API call that comes back 401 means the
  // session is gone (expired, revoked, server restarted). Flip the
  // context to anon so the route guard pushes the user to /login.
  useEffect(() => {
    const id = http.interceptors.response.use(
      (r) => r,
      (err) => {
        const status = err?.response?.status;
        const url = err?.config?.url || "";
        // Don't loop on the /me probe itself — it's expected to 401
        // when the user is not logged in, and we handle it above.
        if (status === 401 && !url.includes("/api/auth/")) {
          setState({ status: "anon" });
        }
        return Promise.reject(err);
      }
    );
    return () => http.interceptors.response.eject(id);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const user = await authApi.login(username, password);
    setState({ status: "authed", user });
    return user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // best-effort — we're clearing local state either way
    }
    setState({ status: "anon" });
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      state,
      user: state.status === "authed" ? state.user : null,
      isAuthed: state.status === "authed",
      isLoading: state.status === "loading",
      login,
      logout,
      refresh,
    }),
    [state, login, logout, refresh]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return ctx;
}
