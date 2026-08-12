// A simple proportional horizontal bar list — used for time-ordered series (Revenue
// Trend) where a donut (share-of-total) doesn't make sense, unlike a true category
// breakdown (Lead Source, Pipeline stage, ...) which already has DonutChart.
export function MiniBarList({ data }: { data: { label: string; value: number }[] }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <ul className="space-y-1.5">
      {data.map((d) => (
        <li key={d.label} className="text-xs">
          <div className="flex items-center justify-between mb-0.5">
            <span className="text-text/60">{d.label}</span>
            <span className="text-text font-medium">{d.value.toLocaleString()}</span>
          </div>
          <div className="h-1.5 rounded-full bg-border overflow-hidden">
            <div className="h-full bg-primary" style={{ width: `${(d.value / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}
