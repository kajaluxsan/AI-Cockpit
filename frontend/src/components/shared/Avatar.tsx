interface Props {
  name?: string | null;
  src?: string | null;
  size?: number;
}

const API_BASE =
  (import.meta as any).env?.VITE_API_URL || "http://localhost:8000";

function initials(name?: string | null): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";
}

function resolveSrc(src?: string | null): string | null {
  if (!src) return null;
  if (/^https?:\/\//i.test(src) || src.startsWith("data:")) return src;
  // Backend returns relative API paths like "/api/candidates/42/photo"
  return `${API_BASE}${src.startsWith("/") ? "" : "/"}${src}`;
}

export default function Avatar({ name, src, size = 40 }: Props) {
  const style = { width: size, height: size, fontSize: size * 0.4 };
  const resolved = resolveSrc(src);
  if (resolved) {
    return (
      <img
        src={resolved}
        alt={name || ""}
        className="rounded-full object-cover bg-bg-elevated border border-bg-border flex-shrink-0"
        style={style}
      />
    );
  }
  return (
    <div
      className="rounded-full bg-bg-elevated border border-bg-border flex items-center justify-center font-medium text-amber-accent flex-shrink-0"
      style={style}
    >
      {initials(name)}
    </div>
  );
}
