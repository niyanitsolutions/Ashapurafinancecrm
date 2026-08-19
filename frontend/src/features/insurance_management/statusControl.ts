// UX-only mirror of the Insurance pipeline's real transition rules — see
// `loan_management/statusControl.ts`'s own docstring for the full rationale (same
// pattern, not shared code, since Loan and Insurance stay completely separate). The
// backend's own `WorkflowEngine.assert_transition_allowed` (transition graph, seeded
// from `scripts/seed.py`'s `_INSURANCE_ROWS`) and `InsuranceCaseService.update_status`'s
// `_SIMPLE_STATUS_TRANSITIONS` (backend/app/features/insurance_management/service.py)
// remain the sole enforcement authority regardless of what this file says.
//
// The `StatusControlInfo` shape is intentionally duplicated from
// `loan_management/statusControl.ts`, not imported — Loan and Insurance stay completely
// independent modules with no cross-feature coupling, matching every other Insurance
// status value/workflow already being its own copy, never shared with Loan's.
export type StatusControlInfo =
  | { kind: "simple"; nextStatus: string }
  | { kind: "dedicated"; actionLabel: string }
  | { kind: "customerOnly"; note: string }
  | { kind: "none" };

const INSURANCE_STATUS_CONTROL: Record<string, StatusControlInfo> = {
  application_submitted: { kind: "simple", nextStatus: "documents_pending" },
  documents_pending: { kind: "simple", nextStatus: "underwriting" },
  underwriting: { kind: "dedicated", actionLabel: "Underwriting" },
  medical_verification: { kind: "dedicated", actionLabel: "Medical Verification" },
  additional_documents: { kind: "simple", nextStatus: "premium_acceptance" },
  premium_acceptance: { kind: "customerOnly", note: "Awaiting the customer's own accept/decline decision on the premium quote." },
  policy_generation: { kind: "dedicated", actionLabel: "Policy Generation / Issue Policy" },
  on_hold: { kind: "dedicated", actionLabel: "Resume" },
  policy_issued: { kind: "none" },
  rejected: { kind: "none" },
};

export function getInsuranceStatusControlInfo(currentStatus: string): StatusControlInfo {
  return INSURANCE_STATUS_CONTROL[currentStatus] ?? { kind: "none" };
}
