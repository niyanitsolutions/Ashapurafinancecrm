import { useEffect, useState } from "react";
import { listEligibleAssignees, type EligibleAssignee } from "@/features/leads/api";
import { getErrorMessage } from "@/shared/api/errors";

function moduleLabel(productCategory: string): string {
  return productCategory.charAt(0).toUpperCase() + productCategory.slice(1);
}

// Assignment picker for Leads — shows only active employees who have module access
// matching this lead's product category (e.g. a "loan" lead only shows employees with
// Loan Management module access — see backend LeadService.list_eligible_assignees).
// Deliberately not gated by a separate "assign" permission: an Owner already grants
// module access when setting up a role and should never configure a second permission
// just so employees can receive leads. Enriched with business context (designation/
// branch/current workload/product specialization) so the Owner/Employee can choose well
// without changing the RBAC model at all. A separate component from the generic
// <EmployeeSelect> (used unfiltered by other call sites) rather than an overload, so
// those stay byte-for-byte unaffected.
export function EligibleAssigneeSelect({
  productCategory,
  productId,
  value,
  onChange,
}: {
  productCategory: string;
  productId?: string;
  value: string;
  onChange: (employeeId: string) => void;
}) {
  const [candidates, setCandidates] = useState<EligibleAssignee[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    setCandidates(null);
    listEligibleAssignees(productCategory, productId)
      .then(setCandidates)
      .catch((err) => setLoadError(getErrorMessage(err)));
  }, [productCategory, productId]);

  if (loadError) {
    return <div className="rounded border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">{loadError}</div>;
  }

  if (candidates === null) {
    return <p className="text-sm text-text/40">Loading eligible employees…</p>;
  }

  if (candidates.length === 0) {
    const label = moduleLabel(productCategory);
    return (
      <div className="rounded border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning">
        No eligible employees found. This lead belongs to the {label} Module. Please create an active employee with {label} module
        access.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {candidates.map((c) => (
        <button
          key={c.id}
          type="button"
          onClick={() => onChange(c.id)}
          className={`w-full text-left rounded border px-3 py-2 transition-colors ${
            value === c.id ? "border-primary bg-primary/5" : "border-border hover:bg-background"
          }`}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-medium text-text">{c.display_name}</span>
            {c.recommended && (
              <span className="shrink-0 rounded-full bg-success/10 px-2 py-0.5 text-xs font-medium text-success">Recommended</span>
            )}
          </div>
          <div className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-text/50">
            {c.designation_name && <span>{c.designation_name}</span>}
            {c.product_match && <span className="text-primary">Product specialist</span>}
            {c.branch_name && <span>Branch: {c.branch_name}</span>}
            <span>Current Leads: {c.current_lead_count}</span>
          </div>
        </button>
      ))}
    </div>
  );
}
