// Indian numbering system compact currency (₹2.48 Cr / ₹64.2 L / ₹8.5 K) — shared by every
// money-denominated card on the redesigned dashboard (KPI row, Disbursed Trend, Revenue Mix).
export function formatINRCompact(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e7) return `₹${(value / 1e7).toFixed(2)} Cr`;
  if (abs >= 1e5) return `₹${(value / 1e5).toFixed(2)} L`;
  if (abs >= 1e3) return `₹${(value / 1e3).toFixed(1)} K`;
  return `₹${value.toLocaleString("en-IN")}`;
}

export function formatINR(value: number): string {
  return `₹${value.toLocaleString("en-IN")}`;
}
