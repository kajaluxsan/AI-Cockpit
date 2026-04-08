interface Props {
  name?: string | null;
  src?: string | null;
  size?: number;
}

function initials(name?: string | null): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";
}

export default function Avatar({ name, src, size = 40 }: Props) {
  const style = { width: size, height: size, fontSize: size * 0.4 };
  if (src) {
    return (
      <img
        src={src}
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
