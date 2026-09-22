import { useState } from "react";
import { BRAND_ORANGE, FUNNEL_OPACITIES, withOpacity } from "@/components/charts/chartColors";

export interface FunnelStage {
  status?: string;
  label: string;
  value: number;
}

// Preserve workflow order; each percentage is a share of current cases, not conversion.
export function FunnelChart({ stages, onStageClick }: { stages: FunnelStage[]; onStageClick?: (stage: FunnelStage) => void }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const max = Math.max(...stages.map((stage) => stage.value), 1);
  const total = stages.reduce((sum, stage) => sum + stage.value, 0);

  return (
    <div className="space-y-2">
      {stages.map((stage, i) => {
        const widthPct = Math.max((stage.value / max) * 100, 8);
        const color = withOpacity(BRAND_ORANGE, FUNNEL_OPACITIES[i % FUNNEL_OPACITIES.length]);
        const shareOfTotal = total > 0 ? Math.round((stage.value / total) * 100) : 0;
        return (
          <button
            key={stage.label}
            type="button"
            onClick={() => onStageClick?.(stage)}
            disabled={!onStageClick}
            aria-label={onStageClick ? `View ${stage.label} cases` : undefined}
            className={`relative flex w-full items-center gap-3 text-left ${onStageClick ? "cursor-pointer rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/40" : "cursor-default"}`}
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
              <span className="font-semibold text-text">{shareOfTotal}%</span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
