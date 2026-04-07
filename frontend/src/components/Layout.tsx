import { NavLink, Outlet, useLocation } from "react-router-dom";

const NAV = [
  { to: "/", label: "Overview", section: "01" },
  { to: "/candidates", label: "Candidates", section: "02" },
  { to: "/jobs", label: "Jobs", section: "03" },
  { to: "/matches", label: "Matches", section: "04" },
  { to: "/calls", label: "Calls", section: "05" },
  { to: "/emails", label: "Emails", section: "06" },
  { to: "/settings", label: "Settings", section: "07" },
];

export default function Layout() {
  const location = useLocation();
  return (
    <div className="min-h-screen flex bg-bg text-text-primary">
      {/* Sidebar */}
      <aside className="w-60 border-r border-bg-border bg-bg-surface flex flex-col">
        <div className="px-6 py-6 border-b border-bg-border">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 bg-amber-accent rounded-full animate-pulse" />
            <span className="font-display text-xl font-semibold tracking-tight">
              recruiter
              <span className="text-amber-accent">·ai</span>
            </span>
          </div>
          <div className="mt-1 label-mono">Swiss Talent Engine</div>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {NAV.map((item) => {
            const active =
              item.to === "/"
                ? location.pathname === "/"
                : location.pathname.startsWith(item.to);
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={`flex items-center gap-3 px-3 py-2 rounded-md font-medium transition-colors ${
                  active
                    ? "bg-bg-elevated text-text-primary border-l-2 border-amber-accent"
                    : "text-text-secondary hover:text-text-primary hover:bg-bg-elevated"
                }`}
              >
                <span className="font-mono text-xs text-text-muted">
                  {item.section}
                </span>
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="p-4 border-t border-bg-border">
          <div className="label-mono">System</div>
          <div className="flex items-center gap-2 mt-1">
            <div className="w-1.5 h-1.5 bg-success rounded-full" />
            <span className="text-sm text-text-secondary">Operational</span>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-14 border-b border-bg-border bg-bg-surface px-6 flex items-center justify-between">
          <div className="label-mono">{currentTitle(location.pathname)}</div>
          <div className="flex items-center gap-4">
            <span className="label-mono">{new Date().toLocaleDateString("de-CH")}</span>
            <div className="w-8 h-8 rounded-full bg-bg-elevated border border-bg-border flex items-center justify-center text-sm font-medium text-amber-accent">
              R
            </div>
          </div>
        </header>
        <main className="flex-1 p-8 overflow-auto animate-fade-in">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function currentTitle(path: string): string {
  if (path === "/") return "OVERVIEW";
  return path.replace("/", "").toUpperCase();
}
