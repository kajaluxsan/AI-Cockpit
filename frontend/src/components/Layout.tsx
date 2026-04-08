import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

const PRIMARY_TABS = [
  { to: "/people", label: "People" },
  { to: "/messages", label: "Messages" },
  { to: "/jobs", label: "Jobs" },
];

const SECONDARY_LINKS = [
  { to: "/overview", label: "Overview" },
  { to: "/matches", label: "Matches" },
  { to: "/calls", label: "Calls" },
  { to: "/emails", label: "Emails" },
  { to: "/settings", label: "Settings" },
];

export default function Layout() {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="min-h-screen flex flex-col bg-bg text-text-primary">
      {/* Minimal top bar */}
      <header className="h-14 border-b border-bg-border bg-bg-surface px-6 flex items-center justify-between">
        <div className="flex items-center gap-8">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 bg-amber-accent rounded-full animate-pulse" />
            <span className="font-display text-lg font-semibold tracking-tight">
              recruiter
              <span className="text-amber-accent">·ai</span>
            </span>
          </div>
          <nav className="flex items-center gap-1">
            {PRIMARY_TABS.map((tab) => {
              const active = location.pathname.startsWith(tab.to);
              return (
                <NavLink
                  key={tab.to}
                  to={tab.to}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    active
                      ? "bg-bg-elevated text-text-primary"
                      : "text-text-secondary hover:text-text-primary hover:bg-bg-elevated"
                  }`}
                >
                  {tab.label}
                </NavLink>
              );
            })}
          </nav>
        </div>

        <div className="flex items-center gap-3 relative">
          <span className="label-mono hidden md:inline">
            {new Date().toLocaleDateString("de-CH")}
          </span>
          <button
            onClick={() => setMenuOpen((v) => !v)}
            className="btn-ghost h-9 px-3 text-sm"
            aria-label="More"
          >
            More ▾
          </button>
          {menuOpen && (
            <div
              className="absolute right-0 top-12 min-w-44 card-elevated z-30 py-1"
              onMouseLeave={() => setMenuOpen(false)}
            >
              {SECONDARY_LINKS.map((l) => (
                <NavLink
                  key={l.to}
                  to={l.to}
                  onClick={() => setMenuOpen(false)}
                  className="block px-4 py-2 text-sm text-text-secondary hover:text-text-primary hover:bg-bg-elevated"
                >
                  {l.label}
                </NavLink>
              ))}
            </div>
          )}
          <div className="w-8 h-8 rounded-full bg-bg-elevated border border-bg-border flex items-center justify-center text-sm font-medium text-amber-accent">
            R
          </div>
        </div>
      </header>

      <main className="flex-1 p-6 md:p-8 overflow-auto animate-fade-in">
        <Outlet />
      </main>
    </div>
  );
}
