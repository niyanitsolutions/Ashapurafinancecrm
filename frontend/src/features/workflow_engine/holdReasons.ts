// Shared "On Hold" reason vocabulary — matches backend HoldReason
// (app.features.workflow_engine.constants.HoldReason). Used by both Loan and Insurance
// Case Details pages; not case-type-specific.
export const HOLD_REASONS: { value: string; label: string }[] = [
  { value: "waiting_for_customer", label: "Waiting for Customer" },
  { value: "waiting_for_bank", label: "Waiting for Bank" },
  { value: "waiting_for_insurance_company", label: "Waiting for Insurance Company" },
  { value: "internal_review", label: "Internal Review" },
  { value: "document_clarification", label: "Document Clarification" },
];
