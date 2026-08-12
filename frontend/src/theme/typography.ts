export const fontFamily = {
  sans: ["Inter", "system-ui", "sans-serif"],
} as const;

// Enterprise redesign pass — bumped meaningfully across the board (same tuple shape:
// Tailwind accepts [fontSize, {lineHeight}]) so every existing `text-xs`/`text-sm`/etc.
// call site across the app inherits the larger, more premium scale without touching each
// one individually. Sized to match how these tokens are actually used site-wide today:
//   sm  (16px) — the most common size: inputs, buttons, table cells, body copy ("Body"/"Table"/"Button" in the brief)
//   lg  (19px) — card/section titles ("Card Title")
//   xl  (30px) — page H1s via SimplePageLayout/AuthPageLayout ("Page Title")
//   2xl (34px) — dashboard KPI hero numbers, intentionally the most prominent tier
export const fontSize = {
  // "2xs"/"md"/"3xl" added for the Dashboard redesign's KPI/section scale (13/22/36px) —
  // additive only, every existing xs..2xl call site across the app is untouched.
  "2xs": ["0.8125rem", { lineHeight: "1.4" }],
  xs: ["0.875rem", { lineHeight: "1.45" }],
  sm: ["1rem", { lineHeight: "1.55" }],
  base: ["1.0625rem", { lineHeight: "1.6" }],
  md: ["1.375rem", { lineHeight: "1.3" }],
  lg: ["1.1875rem", { lineHeight: "1.45" }],
  xl: ["1.875rem", { lineHeight: "1.25" }],
  "2xl": ["2.125rem", { lineHeight: "1.2" }],
  "3xl": ["2.25rem", { lineHeight: "1.15" }],
} as const;
