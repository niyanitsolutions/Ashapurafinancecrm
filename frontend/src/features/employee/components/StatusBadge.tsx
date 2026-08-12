const COLORS: Record<string, string> = {
  active: "bg-success/10 text-success",
  inactive: "bg-text/10 text-text/60",
  suspended: "bg-danger/10 text-danger",
  on_leave: "bg-warning/10 text-warning",
  resigned: "bg-text/10 text-text/60",
};

export function StatusBadge({ status }: { status: string }) {
  const classes = COLORS[status] ?? "bg-text/10 text-text/60";
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium capitalize ${classes}`}>
      {status.replace("_", " ")}
    </span>
  );
}
