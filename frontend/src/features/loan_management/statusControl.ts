// UX-only mirror of the Loan pipeline's real transition rules — for populating the Case
// Status control with something more useful than "all 12 statuses, most of which will
// 422/409." This is NOT the authority: every PATCH /loan-cases/{id}/status call still
// goes through the backend's own `WorkflowEngine.assert_transition_allowed` (the real
// transition graph, seeded from `scripts/seed.py`'s Loan rows) and
// `LoanCaseService.update_status`'s `_PLAIN_TRANSITIONS` (backend/app/features/
// loan_management/service.py) unconditionally, regardless of what this file says. If this
// ever drifts out of sync with those two, the worst case is a suboptimal hint or an
// avoidable error message — never a bypassed validation.
//
// Decision #129: `credit_evaluation` and `re_eligible` each now have MORE than one
// available action at once (a dedicated bank-offer view alongside plain reject/
// re-eligible moves) — this file's shape is an array per status for exactly that reason,
// per the note this file itself used to carry about needing a matching update if the
// pipeline ever branched like this.
export type StatusControlAction =
  | { kind: "simple"; nextStatus: string; label?: string }
  | { kind: "dedicated"; actionLabel: string }
  | { kind: "none" };

const LOAN_STATUS_CONTROL: Record<string, StatusControlAction[]> = {
  new_customer: [{ kind: "simple", nextStatus: "credit_evaluation" }],
  credit_evaluation: [
    { kind: "dedicated", actionLabel: "Bank / NBFC Offers" },
    { kind: "simple", nextStatus: "rejected", label: "Reject" },
    { kind: "simple", nextStatus: "re_eligible", label: "Mark Re-Eligible" },
  ],
  offer_acceptance: [{ kind: "dedicated", actionLabel: "Offer Acceptance" }],
  additional_documents: [{ kind: "simple", nextStatus: "rv_ov_ref" }],
  rv_ov_ref: [{ kind: "simple", nextStatus: "esign_nach_kyc" }],
  esign_nach_kyc: [{ kind: "dedicated", actionLabel: "eSign / NACH / KYC Checklist" }],
  final_evaluation: [{ kind: "dedicated", actionLabel: "Final Evaluation" }],
  send_for_disbursement: [{ kind: "dedicated", actionLabel: "Disbursement" }],
  on_hold: [{ kind: "dedicated", actionLabel: "Resume" }],
  re_eligible: [
    { kind: "simple", nextStatus: "credit_evaluation", label: "Move to Credit Evaluation" },
    { kind: "simple", nextStatus: "rejected", label: "Reject" },
  ],
  disbursed: [{ kind: "none" }],
  rejected: [{ kind: "none" }],
};

export function getLoanStatusControlInfo(currentStatus: string): StatusControlAction[] {
  return LOAN_STATUS_CONTROL[currentStatus] ?? [{ kind: "none" }];
}
