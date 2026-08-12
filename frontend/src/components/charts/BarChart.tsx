import { useState } from "react";
import { BRAND_ORANGE } from "@/components/charts/chartColors";

export interface BarDatum {
  label: string;
  value: number;
}

// Single-series vertical bar chart (nominal, not identity — one hue throughout, no legend
// needed per marks-and-anatomy). Rounded data-end, hairline gridlines, per-bar hover
// tooltip (the mark itself is the hit target, per interaction.md).
export function BarChart({
  data,
  formatValue = (v) => v.toLocaleString("en-IN"),
  height = 220,
}: {
  data: BarDatum[];
  formatValue?: (v: number) => string;
  height?: number;
}) {
  const [hovered, setHovered] = useState<number | null>(null);
  const max = Math.max(...data.map((d) => d.value), 1);
  const gridSteps = 4;
  const barWidthPct = 100 / data.length;

  return (
    <div>
      <div className="relative" style={{ height }}>
        {/* gridlines */}
        <div className="absolute inset-0 flex flex-col justify-between pb-6">
          {Array.from({ length: gridSteps + 1 }).map((_, i) => (
            <div key={i} className="border-t border-border" />
          ))}
        </div>

        <div className="relative h-full flex items-end pb-6">
          {data.map((d, i) => {
            const pct = max > 0 ? (d.value / max) * 100 : 0;
            return (
              <div
                key={d.label}
                className="relative h-full flex flex-col items-center justify-end group"
                style={{ width: `${barWidthPct}%` }}
                onMouseEnter={() => setHovered(i)}
                onMouseLeave={() => setHovered(null)}
              >
                {hovered === i && (
                  <div className="absolute -top-9 z-10 whitespace-nowrap rounded-lg bg-text px-2.5 py-1 text-2xs font-medium text-white shadow-dropdown">
                    {formatValue(d.value)}
                  </div>
                )}
                <div
                  className="w-[60%] rounded-t-[4px] transition-[filter] duration-150"
                  style={{
                    height: `${Math.max(pct, 2)}%`,
                    backgroundColor: BRAND_ORANGE,
                    filter: hovered === i ? "brightness(1.1)" : undefined,
                  }}
                />
              </div>
            );
          })}
        </div>
      </div>
      <div className="flex">
        {data.map((d) => (
          <div key={d.label} className="text-center text-2xs text-textSecondary" style={{ width: `${barWidthPct}%` }}>
            {d.label}
          </div>
        ))}
      </div>
    </div>
  );
}
