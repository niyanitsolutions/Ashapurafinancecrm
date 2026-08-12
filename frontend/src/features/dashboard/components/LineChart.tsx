// Phase 4.1 chart-consistency convention: line charts are reserved for trends over time
// (Revenue Trend, future Leads-over-time) — never used for a category/count breakdown,
// which uses the bar list (MiniBarList) instead. Simple inline SVG, no new dependency.
export function LineChart({ data }: { data: { label: string; value: number }[] }) {
  if (data.length === 0) return null;
  const width = 280;
  const height = 90;
  const padding = 8;
  const max = Math.max(1, ...data.map((d) => d.value));
  const stepX = data.length > 1 ? (width - padding * 2) / (data.length - 1) : 0;

  const points = data.map((d, i) => {
    const x = padding + i * stepX;
    const y = height - padding - (d.value / max) * (height - padding * 2);
    return { x, y, ...d };
  });
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto" preserveAspectRatio="none">
        <path d={path} fill="none" stroke="#F97316" strokeWidth={2} />
        {points.map((p) => (
          <circle key={p.label} cx={p.x} cy={p.y} r={2.5} fill="#F97316" />
        ))}
      </svg>
      <div className="flex justify-between mt-1 text-[10px] text-text/40">
        {data.map((d) => (
          <span key={d.label}>{d.label}</span>
        ))}
      </div>
    </div>
  );
}
