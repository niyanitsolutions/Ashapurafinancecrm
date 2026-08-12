import { useId, useState } from "react";

export interface DonutSegment {
  label: string;
  value: number;
  color: string;
}

// SVG stroke-dasharray donut — real arcs (not conic-gradient) so each segment is its own
// hoverable/focusable element. Legend is always present (>= 2 series, per marks-and-anatomy)
// and carries the value directly, satisfying the categorical palette's contrast-relief
// requirement without needing labels crammed onto thin slices.
export function DonutChart({
  segments,
  centerLabel,
  centerValue,
  formatValue = (v) => v.toLocaleString("en-IN"),
}: {
  segments: DonutSegment[];
  centerLabel: string;
  centerValue: string;
  formatValue?: (v: number) => string;
}) {
  const uid = useId();
  const [hovered, setHovered] = useState<number | null>(null);
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  const size = 176;
  const strokeWidth = 26;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  let cumulative = 0;
  const arcs = segments.map((segment, i) => {
    const fraction = total > 0 ? segment.value / total : 0;
    const length = fraction * circumference;
    const dashArray = `${length} ${circumference - length}`;
    const dashOffset = -cumulative;
    cumulative += length;
    return { ...segment, dashArray, dashOffset, fraction, index: i };
  });

  return (
    <div className="flex flex-col items-center gap-5">
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#F4F6F9" strokeWidth={strokeWidth} />
          {arcs.map((arc) => (
            <circle
              key={`${uid}-${arc.label}`}
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={arc.color}
              strokeWidth={hovered === arc.index ? strokeWidth + 4 : strokeWidth}
              strokeDasharray={arc.dashArray}
              strokeDashoffset={arc.dashOffset}
              strokeLinecap="butt"
              className="transition-[stroke-width] duration-150 cursor-pointer"
              onMouseEnter={() => setHovered(arc.index)}
              onMouseLeave={() => setHovered(null)}
              tabIndex={0}
              role="img"
              aria-label={`${arc.label}: ${formatValue(arc.value)} (${Math.round(arc.fraction * 100)}%)`}
              onFocus={() => setHovered(arc.index)}
              onBlur={() => setHovered(null)}
            />
          ))}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-4">
          <span className="text-sm font-bold text-text leading-tight">
            {hovered !== null ? formatValue(arcs[hovered].value) : centerValue}
          </span>
          <span className="text-2xs text-textSecondary leading-tight">
            {hovered !== null ? arcs[hovered].label : centerLabel}
          </span>
        </div>
      </div>

      <ul className="w-full space-y-2">
        {arcs.map((arc) => (
          <li
            key={arc.label}
            className="flex items-center justify-between gap-2 text-2xs cursor-default"
            onMouseEnter={() => setHovered(arc.index)}
            onMouseLeave={() => setHovered(null)}
          >
            <span className="flex items-center gap-2 min-w-0">
              <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ backgroundColor: arc.color }} aria-hidden="true" />
              <span className="text-textSecondary truncate">{arc.label}</span>
            </span>
            <span className="font-semibold text-text shrink-0">{Math.round(arc.fraction * 100)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
