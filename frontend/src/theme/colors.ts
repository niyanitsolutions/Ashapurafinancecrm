// Shared content palette. The approved sidebar retains its original CSS variable
// values in index.css; existing token names and component contracts are preserved.
export const colors = {
  sidebar: "#111111", // Power BI/Salesforce-style flat near-black — Dashboard redesign pass
  sidebarLight: "#1A1A1A", // subtle depth stop for hover/section surfaces within the sidebar
  navy: "#0F172A", // kept for AuthPageLayout's login background — unrelated to the sidebar now
  primary: {
    DEFAULT: "rgb(var(--afs-primary) / <alpha-value>)",
    light: "rgb(var(--afs-primary-light) / <alpha-value>)",
    dark: "rgb(var(--afs-primary-dark) / <alpha-value>)",
  },
  background: "#F7F8FA",
  card: "#FFFFFF",
  border: "#E5E7EB",
  text: "#151515",
  textSecondary: "#6B7280",
  success: "#16A34A",
  warning: "#F59E0B",
  danger: "#DC2626",
  info: "#2563EB",
} as const;
