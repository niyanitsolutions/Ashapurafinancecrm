import { useState } from "react";
import { BRAND_ORANGE, FUNNEL_OPACITIES, withOpacity } from "@/components/charts/chartColors";

export interface FunnelStage {
  label: string;
  value: number;
}

// Ordinal color job (position in a sequence, not identity) — one hue, monotone lightness
// via opacity steps, per choosing-a-form.md's "funnel stage" example. Stages are the
// backend's group-by-status counts with no guaranteed semantic order (see dashboard
// redesign notes), so they're sorted by count descending — the conventional funnel shape,
// and a defensible ordering when the true pipeline sequence isn't exposed by the API.
export function FunnelChart({ stages }: { stages: FunnelStage[] }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const sorted = [...stages].sort((a, b) => b.value - a.value);
  const max = sorted[0]?.value || 1;

  return (
    <div className="space-y-2">
      {sorted.map((stage, i) => {
        const widthPct = Math.max((stage.value / max) * 100, 8);
        const color = withOpacity(BRAND_ORANGE, FUNNEL_OPACITIES[i % FUNNEL_OPACITIES.length]);
        const percentOfFirst = max > 0 ? Math.round((stage.value / max) * 100) : 0;
        return (
          <div
            key={stage.label}
            className="relative flex items-center gap-3"
            onMouseEnter={() => setHovered(i)}
            onMouseLeave={() => setHovered(null)}
          >
            <div className="flex-1">
              <div
                className="mx-auto flex items-center justify-center rounded-lg py-2.5 text-2xs font-semibold text-white transition-[filter] duration-150"
                style={{ width: `${widthPct}%`, backgroundColor: color, filter: hovered === i ? "brightness(1.08)" : undefined }}
              >
                {stage.value.toLocaleString("en-IN")}
              </div>
            </div>
            <div className="w-32 shrink-0 flex items-center justify-between text-2xs">
              <span className="text-textSecondary truncate">{stage.label}</span>
              <span className="font-semibold text-text">{percentOfFirst}%</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
