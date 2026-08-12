const PALETTE = ["#F97316", "#0EA5E9", "#22C55E", "#A855F7", "#EAB308", "#F43F5E"];

export function DonutChart({ data }: { data: { label: string; value: number }[] }) {
  const total = data.reduce((sum, d) => sum + d.value, 0);
  let cumulative = 0;
  const stops = data
    .map((d, i) => {
      const start = total > 0 ? (cumulative / total) * 360 : 0;
      cumulative += d.value;
      const end = total > 0 ? (cumulative / total) * 360 : 0;
      return `${PALETTE[i % PALETTE.length]} ${start}deg ${end}deg`;
    })
    .join(", ");

  return (
    <div className="flex items-center gap-4">
      <div
        className="relative w-20 h-20 rounded-full shrink-0"
        style={{ background: total > 0 ? `conic-gradient(${stops})` : "#E5E7EB" }}
      >
        <div className="absolute inset-[20%] rounded-full bg-card flex items-center justify-center text-sm font-semibold text-text">
          {total}
        </div>
      </div>
      <ul className="space-y-1 text-xs min-w-0">
        {data.map((d, i) => (
          <li key={d.label} className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: PALETTE[i % PALETTE.length] }} />
            <span className="text-text/70 truncate">{d.label}</span>
            <span className="text-text/40 shrink-0 ml-1">{d.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
