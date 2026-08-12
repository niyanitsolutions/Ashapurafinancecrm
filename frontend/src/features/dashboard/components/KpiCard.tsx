import { Icon, type IconName } from "@/theme/icons";
import { Card } from "@/components/cards/Card";

export interface KpiTrend {
  direction: "up" | "down" | "flat";
  percent: number;
  comparisonLabel: string;
}

// Stat-tile contract (dataviz skill): label, value (auto-compact), optional signed delta.
// `trend` is only ever passed when a widget provider actually returns trend_direction/
// trend_percent — never fabricated to fill the slot (see KpiRow.tsx).
export function KpiCard({
  icon,
  label,
  value,
  subtitle,
  trend,
}: {
  icon: IconName;
  label: string;
  value: string;
  subtitle?: string;
  trend?: KpiTrend;
}) {
  const trendColor = trend?.direction === "up" ? "text-success" : trend?.direction === "down" ? "text-danger" : "text-textSecondary";

  return (
    <Card className="hover-lift">
      <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-primary-dark text-white shadow-card mb-4">
        <Icon name={icon} className="h-5 w-5" />
      </span>
      <p className="text-3xl font-bold text-text leading-tight tabular-nums">{value}</p>
      <p className="text-sm text-textSecondary mt-1">{label}</p>
      {(subtitle || trend) && (
        <div className="mt-3 flex items-center gap-1.5 text-2xs">
          {trend && (
            <span className={`flex items-center gap-0.5 font-semibold ${trendColor}`}>
              <Icon name={trend.direction === "down" ? "trending-down" : "trending-up"} className="h-3.5 w-3.5" />
              {trend.percent}%
            </span>
          )}
          {subtitle && <span className="text-textSecondary">{subtitle}</span>}
        </div>
      )}
    </Card>
  );
}
