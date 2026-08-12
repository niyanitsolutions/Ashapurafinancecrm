// Validated categorical palette (dataviz skill default order) — passes lightness band,
// chroma floor, CVD separation (worst adjacent ΔE 9.1 protan / 19.6 normal-vision) and
// contrast (WARN on 3 slots, mitigated by always shipping a legend + direct labels) on our
// white (#FFFFFF) card surface. Fixed order, never cycled — see
// node scripts/validate_palette.js output referenced in the dashboard redesign notes.
export const CATEGORICAL = [
  "#2a78d6", // blue
  "#eb6834", // orange
  "#1baf7a", // aqua
  "#eda100", // yellow
  "#e87ba4", // magenta
  "#008300", // green
  "#4a3aa7", // violet
  "#e34948", // red
] as const;

// The brand hero color — reserved for single-series charts (Disbursed Trend) and the one
// "primary vs everything else" slot (Loan in the 2-slice Revenue Mix donut), never mixed
// into the 8-hue categorical sequence above. Validated against CATEGORICAL[0] (blue):
// CVD ΔE 27.1 protan / 37.3 normal-vision — comfortably clear of both floors.
export const BRAND_ORANGE = "#FF6B00";

// Ordinal ramp for the Pipeline funnel (stage position, not identity — see
// choosing-a-form.md) — one hue, monotone lightness via opacity over white, so every step
// is provably lighter than the last without hand-picking hex values.
export const FUNNEL_OPACITIES = [1, 0.82, 0.66, 0.52, 0.4, 0.3, 0.22] as const;

export function withOpacity(hex: string, opacity: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}

/** N real categories -> at most 8 palette slots; beyond that the tail folds into "Other"
 * per the dataviz skill's series-count ladder rather than generating a 9th hue. */
export function assignCategoricalColors<T extends { label: string; value: number }>(
  items: T[],
  maxSlots = 7,
): { label: string; value: number; color: string }[] {
  const sorted = [...items].sort((a, b) => b.value - a.value);
  if (sorted.length <= maxSlots) {
    return sorted.map((item, i) => ({ ...item, color: CATEGORICAL[i % CATEGORICAL.length] }));
  }
  const head = sorted.slice(0, maxSlots - 1).map((item, i) => ({ ...item, color: CATEGORICAL[i] }));
  const tailValue = sorted.slice(maxSlots - 1).reduce((sum, item) => sum + item.value, 0);
  return [...head, { label: "Other", value: tailValue, color: CATEGORICAL[maxSlots - 1] }];
}
