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
