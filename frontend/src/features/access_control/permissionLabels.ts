// The permission catalog seeded by scripts/seed.py already sets a business-friendly
// `label` on every entry (e.g. "Loan Cases", "Communication Queue") — this just prefers
// that label over the raw `module:resource` key, falling back to a humanized version of
// the key only for permissions created ad hoc via the Permission Matrix's "Add to
// Catalog" form (which doesn't collect a label), or for a `TemporaryAccessGrant` (which
// carries module/resource but no label of its own). Backend permission ids/values are
// untouched; this only changes what's displayed.
function humanize(value: string): string {
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function friendlyPermissionLabel(permission: { module: string; resource: string; label?: string | null }): string {
  if (permission.label) return permission.label;
  return `${humanize(permission.module)} — ${humanize(permission.resource)}`;
}
