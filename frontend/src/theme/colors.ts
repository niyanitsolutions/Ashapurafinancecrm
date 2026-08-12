// Enterprise redesign pass — same key names as before (every existing `bg-primary`,
// `text-danger`, `bg-sidebar`, ... call site across the app keeps compiling and
// automatically inherits the refreshed values), plus a few new tokens for the
// glassmorphism/gradient treatments (`navy`, `info`, `textSecondary`).
export const colors = {
  sidebar: "#111111", // Power BI/Salesforce-style flat near-black — Dashboard redesign pass
  sidebarLight: "#1A1A1A", // subtle depth stop for hover/section surfaces within the sidebar
  navy: "#0F172A", // kept for AuthPageLayout's login background — unrelated to the sidebar now
  primary: {
    DEFAULT: "#FF6B00", // brand orange — Dashboard redesign pass (was #F97316)
    light: "#FF8A33",
    dark: "#E05F00",
  },
  background: "#F4F6F9",
  card: "#FFFFFF",
  border: "#E5E7EB",
  text: "#1F2937",
  textSecondary: "#6B7280",
  success: "#22C55E",
  warning: "#F59E0B",
  danger: "#EF4444",
  info: "#2563EB",
} as const;
