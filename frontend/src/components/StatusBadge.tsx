interface Props {
  status: string;
  size?: "sm" | "md";
}

const COLORS: Record<string, { bg: string; text: string; dot: string }> = {
  new: { bg: "bg-cyan-link/10", text: "text-cyan-link", dot: "bg-cyan-link" },
  parsed: { bg: "bg-cyan-link/10", text: "text-cyan-link", dot: "bg-cyan-link" },
  info_requested: { bg: "bg-amber-accent/10", text: "text-amber-accent", dot: "bg-amber-accent" },
  matched: { bg: "bg-amber-accent/10", text: "text-amber-accent", dot: "bg-amber-accent" },
  contacted: { bg: "bg-amber-accent/10", text: "text-amber-accent", dot: "bg-amber-accent" },
  interview: { bg: "bg-amber-accent/15", text: "text-amber-accent", dot: "bg-amber-accent" },
  placed: { bg: "bg-success/10", text: "text-success", dot: "bg-success" },
  rejected: { bg: "bg-danger/10", text: "text-danger", dot: "bg-danger" },
  open: { bg: "bg-success/10", text: "text-success", dot: "bg-success" },
  paused: { bg: "bg-text-muted/10", text: "text-text-muted", dot: "bg-text-muted" },
  filled: { bg: "bg-success/10", text: "text-success", dot: "bg-success" },
  closed: { bg: "bg-text-muted/10", text: "text-text-muted", dot: "bg-text-muted" },
  completed: { bg: "bg-success/10", text: "text-success", dot: "bg-success" },
  initiated: { bg: "bg-cyan-link/10", text: "text-cyan-link", dot: "bg-cyan-link" },
  ringing: { bg: "bg-cyan-link/10", text: "text-cyan-link", dot: "bg-cyan-link" },
  in_progress: { bg: "bg-cyan-link/10", text: "text-cyan-link", dot: "bg-cyan-link" },
  no_answer: { bg: "bg-text-muted/10", text: "text-text-muted", dot: "bg-text-muted" },
  busy: { bg: "bg-text-muted/10", text: "text-text-muted", dot: "bg-text-muted" },
  failed: { bg: "bg-danger/10", text: "text-danger", dot: "bg-danger" },
  canceled: { bg: "bg-text-muted/10", text: "text-text-muted", dot: "bg-text-muted" },
};

export default function StatusBadge({ status }: Props) {
  const color = COLORS[status] ?? COLORS.new;
  return (
    <span className={`pill ${color.bg} ${color.text} gap-1.5`}>
      <span className={`w-1.5 h-1.5 rounded-full ${color.dot}`} />
      {status.replace("_", " ")}
    </span>
  );
}
