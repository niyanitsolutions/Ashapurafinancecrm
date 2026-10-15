// Quiet content elevation. CSS variables preserve the approved sidebar shadows.
export const boxShadow = {
  card: "var(--afs-shadow-card)",
  cardHover: "0 4px 12px rgba(21, 21, 21, 0.08)",
  dropdown: "var(--afs-shadow-dropdown)",
  glass: "0 8px 32px rgba(15, 23, 42, 0.25)",
} as const;
