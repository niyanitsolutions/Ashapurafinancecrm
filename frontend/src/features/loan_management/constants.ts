// Single canonical status → label map (decision #129) — previously hand-duplicated
// verbatim in both LoanCaseListPage.tsx and LoanCaseDetailsPage.tsx. Must mirror
// backend/app/features/workflow_engine/constants.py's `LoanStatus` exactly.
export const LOAN_STATUS_LABELS: Record<string, string> = {
  new_customer: "New Customer",
  credit_evaluation: "Credit Evaluation",
  offer_acceptance: "Offer Acceptance",
  additional_documents: "Additional Documents",
  rv_ov_ref: "RV/OV/Ref",
  esign_nach_kyc: "eSign / NACH / KYC",
  final_evaluation: "Final Evaluation",
  send_for_disbursement: "Send For Disbursement",
  disbursed: "Disbursed",
  on_hold: "On Hold",
  re_eligible: "Re-Eligible",
  rejected: "Rejected",
};

// Tab order for LoanManagementLayout — "Loan Cases" is the display label for the
// new_customer tab specifically (spec's own naming), every other tab uses its status label.
export const LOAN_STATUS_TAB_ORDER = [
  "new_customer", "credit_evaluation", "offer_acceptance", "additional_documents", "rv_ov_ref",
  "esign_nach_kyc", "final_evaluation", "send_for_disbursement", "disbursed", "on_hold", "re_eligible", "rejected",
] as const;
