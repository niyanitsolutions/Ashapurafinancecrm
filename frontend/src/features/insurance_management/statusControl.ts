// UX-only mirror of the Insurance "Policy Leads" transition rules. The backend's
// `WorkflowEngine.assert_transition_allowed` (graph seeded from `scripts/seed.py`'s
// insurance rows) and `InsuranceCaseService`'s per-action gates remain the sole
// enforcement authority regardless of what this file says. Shape intentionally
// duplicated from `loan_management/statusControl.ts` — the two modules stay independent.
export type StatusControlInfo =
  | { kind: "simple"; nextStatus: string }
  | { kind: "dedicated"; actionLabel: string }
  | { kind: "none" };

const INSURANCE_STATUS_CONTROL: Record<string, StatusControlInfo> = {
  fresh_lead: { kind: "simple", nextStatus: "policy_document" },
  policy_document: { kind: "dedicated", actionLabel: "Move to Policy Login" },
  policy_login: { kind: "dedicated", actionLabel: "Move to Policy Issued" },
  re_eligible: { kind: "dedicated", actionLabel: "Restart" },
  on_hold: { kind: "dedicated", actionLabel: "Resume" },
  policy_issued: { kind: "none" },
  rejected: { kind: "none" },
};

export function getInsuranceStatusControlInfo(currentStatus: string): StatusControlInfo {
  return INSURANCE_STATUS_CONTROL[currentStatus] ?? { kind: "none" };
}

export const INSURANCE_STATUS_LABELS: Record<string, string> = {
  fresh_lead: "Fresh Lead",
  policy_document: "Policy Document",
  policy_login: "Policy Login",
  policy_issued: "Policy Issued",
  re_eligible: "Re-Eligible",
  on_hold: "On Hold",
  rejected: "Rejected",
};

// Policy Lead "Place On Hold" reasons — matches backend `InsuranceHoldReason`. Separate
// from Loan's `HOLD_REASONS` (workflow_engine/holdReasons.ts). "Other" reveals a
// free-text "Other Hold Reason" field that is persisted with the case's hold info.
export const INSURANCE_HOLD_REASONS: { value: string; label: string }[] = [
  { value: "underwriting_issues", label: "Underwriting Issues" },
  { value: "medical_pending", label: "Medical Pending" },
  { value: "document_not_clear", label: "Document Not Clear" },
  { value: "payment_pending", label: "Payment Pending" },
  { value: "document_pending", label: "Document Pending" },
  { value: "other", label: "Other" },
];

export const INSURANCE_HOLD_REASON_LABELS: Record<string, string> = Object.fromEntries(
  INSURANCE_HOLD_REASONS.map((r) => [r.value, r.label]),
);

// Insurance offers 3 / 6 / 12 / Custom / No — no 9-month option (that is loan-only).
// "No" means "never automatically Re-Eligible".
export const INSURANCE_RE_ELIGIBILITY_OPTIONS: { value: "3_months" | "6_months" | "12_months" | "custom" | "no"; label: string }[] = [
  { value: "3_months", label: "3 Months" },
  { value: "6_months", label: "6 Months" },
  { value: "12_months", label: "12 Months" },
  { value: "custom", label: "Custom" },
  { value: "no", label: "No" },
];
