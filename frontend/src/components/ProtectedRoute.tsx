import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "@/hooks/useAuth";

/**
 * Gate a subtree behind the auth context.
 *
 * States:
 * - ``loading`` — render a neutral placeholder so we don't flash the
 *   login page for users who are in fact already authenticated.
 * - ``anon``    — redirect to /login, preserving the attempted path
 *   so LoginPage can bounce back after success.
 * - ``authed``  — render the wrapped children.
 */
export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthed, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-slate-500">
        Wird geladen…
      </div>
    );
  }

  if (!isAuthed) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <>{children}</>;
}
