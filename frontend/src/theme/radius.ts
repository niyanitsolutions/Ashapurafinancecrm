// Enterprise redesign pass — `DEFAULT` (plain `rounded`) is what nearly every existing
// input/button in the app already uses, so bumping it to 12px hits the brief's
// Button/Input radius target with one token change. `lg` (16px) is for the new shared
// DataTable; `card` (18px) matches the brief's Card radius exactly.
export const borderRadius = {
  sm: "0.5rem",
  DEFAULT: "0.75rem",
  lg: "1rem",
  xl: "1.25rem",
  card: "1.125rem",
} as const;
