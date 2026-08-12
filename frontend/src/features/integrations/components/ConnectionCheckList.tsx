import type { ConnectionCheckItem } from "@/features/integrations/api";

// Shared between the Create Config stepper (IntegrationListPage) and the Details page's own
// Test Connection button — one rendering of the ✓/✗ App ID/App Secret/Token/Permissions
// checklist, backed by TestConnectionResponse.checks (Meta only; null for every other
// provider, in which case this renders nothing and the caller should fall back to the plain
// success/failure message).
export function ConnectionCheckList({ checks }: { checks: ConnectionCheckItem[] }) {
  return (
    <ul className="space-y-1.5">
      {checks.map((check) => (
        <li key={check.key} className="flex items-start gap-2 text-sm">
          <span className={check.passed ? "text-success" : "text-danger"}>{check.passed ? "✓" : "✕"}</span>
          <div>
            <span className={check.passed ? "text-text" : "text-danger"}>{check.label}</span>
            {check.detail && <div className="text-xs text-text/50">{check.detail}</div>}
          </div>
        </li>
      ))}
    </ul>
  );
}
