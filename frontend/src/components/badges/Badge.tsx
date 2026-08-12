import type { ReactNode } from "react";

type BadgeTone = "info" | "primary" | "success" | "danger" | "warning" | "neutral";

const TONE_CLASSES: Record<BadgeTone, string> = {
  info: "bg-info/10 text-info",
  primary: "bg-primary/10 text-primary",
  success: "bg-success/10 text-success",
  danger: "bg-danger/10 text-danger",
  warning: "bg-warning/10 text-warning",
  neutral: "bg-text/10 text-textSecondary",
};

export function Badge({ tone = "neutral", children }: { tone?: BadgeTone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${TONE_CLASSES[tone]}`}>
      {children}
    </span>
  );
}

// Maps the status strings already used across Leads/Applications/Loan/Insurance/Tasks to
// one of the brief's 5 semantic tones (New=Blue, Assigned=Orange, Approved=Green,
// Rejected=Red, Pending=Yellow) — a display-only lookup, so any status value this map
// doesn't yet recognize still renders (as a neutral pill) rather than breaking a page.
const STATUS_TONE: Record<string, BadgeTone> = {
  new: "info",
  assigned: "primary",
  // Leads only ever carry status "new" today (LeadStatus.ALL = ("new",) — the real
  // configurable pipeline is a future module, per backend/app/features/leads/constants.py)
  // — these are here so the Leads list redesign's status pills are correct the moment
  // that pipeline ships, not a claim that these values exist yet.
  contacted: "primary",
  qualified: "primary",
  proposal: "warning",
  negotiation: "warning",
  won: "success",
  lost: "danger",
  approved: "success",
  disbursed: "success",
  issued: "success",
  active: "success",
  completed: "success",
  paid: "success",
  resolved: "success",
  rejected: "danger",
  cancelled: "danger",
  failed: "danger",
  overdue: "danger",
  pending: "warning",
  draft: "warning",
  in_progress: "warning",
  under_review: "warning",
  submitted: "info",
  unread: "info",
  read: "neutral",
  // Real Loan/Insurance case pipeline (backend/app/features/workflow_engine/constants.py
  // LoanStatus/InsuranceStatus) — added for the Loan/Insurance Management redesign.
  new_customer: "info",
  documents_pending: "warning",
  credit_evaluation: "warning",
  offer_acceptance: "warning",
  additional_documents: "warning",
  esign_nach_kyc: "warning",
  final_evaluation: "warning",
  send_for_disbursement: "primary",
  on_hold: "warning",
  application_submitted: "info",
  underwriting: "warning",
  medical_verification: "warning",
  premium_acceptance: "warning",
  policy_generation: "primary",
  policy_issued: "success",
};

// `label` overrides the auto-humanized text (status.replace(/_/g, " ")) while the tone
// still derives from the raw `status` value — lets callers pass a friendlier map (e.g.
// "esign_nach_kyc" -> "eSign / NACH / KYC") without losing correct color-coding.
export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const tone = STATUS_TONE[status.toLowerCase().replace(/\s+/g, "_")] ?? "neutral";
  return <Badge tone={tone}>{label ?? status.replace(/_/g, " ")}</Badge>;
}
