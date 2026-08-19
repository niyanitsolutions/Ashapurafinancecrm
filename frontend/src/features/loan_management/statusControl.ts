// UX-only mirror of the Loan pipeline's real transition rules — for populating the Case
// Status control with something more useful than "all 11 statuses, most of which will
// 422/409." This is NOT the authority: every PATCH /loan-cases/{id}/status call still
// goes through the backend's own `WorkflowEngine.assert_transition_allowed` (the real
// transition graph, seeded from `scripts/seed.py`'s `_LOAN_ROWS`) and
// `LoanCaseService.update_status`'s `_SIMPLE_STATUS_TRANSITIONS` (backend/app/features/
// loan_management/service.py) unconditionally, regardless of what this file says. If this
// ever drifts out of sync with those two, the worst case is a suboptimal hint or an
// avoidable error message — never a bypassed validation.
//
// Kept current_status -> one outcome because that's what the real pipeline is today: no
// Loan status currently has both a "simple" direct move AND a form-gated one available at
// the same time. If the backend pipeline ever grows a branch like that, this file's shape
// (and the two backend files above) need a matching update.
export type StatusControlInfo =
  | { kind: "simple"; nextStatus: string }
  | { kind: "dedicated"; actionLabel: string }
  | { kind: "customerOnly"; note: string }
  | { kind: "none" };

const LOAN_STATUS_CONTROL: Record<string, StatusControlInfo> = {
  new_customer: { kind: "simple", nextStatus: "documents_pending" },
  documents_pending: { kind: "simple", nextStatus: "credit_evaluation" },
  credit_evaluation: { kind: "dedicated", actionLabel: "Credit Evaluation" },
  offer_acceptance: { kind: "customerOnly", note: "Awaiting the customer's own accept/decline decision on the offer." },
  additional_documents: { kind: "simple", nextStatus: "esign_nach_kyc" },
  esign_nach_kyc: { kind: "dedicated", actionLabel: "eSign / NACH / KYC Checklist" },
  final_evaluation: { kind: "dedicated", actionLabel: "Final Evaluation" },
  send_for_disbursement: { kind: "dedicated", actionLabel: "Disbursement" },
  on_hold: { kind: "dedicated", actionLabel: "Resume" },
  disbursed: { kind: "none" },
  rejected: { kind: "none" },
};

export function getLoanStatusControlInfo(currentStatus: string): StatusControlInfo {
  return LOAN_STATUS_CONTROL[currentStatus] ?? { kind: "none" };
}
