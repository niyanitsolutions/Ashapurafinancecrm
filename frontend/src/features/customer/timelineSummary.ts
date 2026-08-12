import type { PortalDashboard } from "@/features/customer/api";

export type MilestoneState = "completed" | "current" | "upcoming" | "rejected";

export interface Milestone {
  label: string;
  state: MilestoneState;
}

// Phase 5.1 — the Home dashboard's condensed Timeline widget. Built entirely from
// fields the dashboard summary call already returns (no second API call) by rolling the
// real, detailed per-status timeline (see ApplicationTimelinePage, which shows every
// actual workflow_definitions stage) up into milestone-level checkpoints. "Approval" and
// "Disbursement"/"Policy Issued" collapse into the same real event in this system today
// (there's no separate "approved but not yet disbursed" status) — both are marked
// together rather than inventing a status that doesn't exist.
export function buildMilestones(dashboard: PortalDashboard): Milestone[] {
  const milestones: Milestone[] = [];
  if (dashboard.has_lead) milestones.push({ label: "Lead Created", state: "completed" });

  const isDraft = dashboard.status_label === "Draft";
  milestones.push({ label: "Application Submitted", state: isDraft ? "current" : "completed" });

  const finalLabel = dashboard.product_category === "insurance" ? "Policy Issued" : "Disbursement";

  if (isDraft) {
    milestones.push({ label: "Verification", state: "upcoming" });
    milestones.push({ label: "Approval", state: "upcoming" });
    milestones.push({ label: finalLabel, state: "upcoming" });
  } else if (dashboard.status_label === "Approved") {
    milestones.push({ label: "Verification", state: "completed" });
    milestones.push({ label: "Approval", state: "completed" });
    milestones.push({ label: finalLabel, state: "completed" });
  } else if (dashboard.status_label === "Rejected") {
    milestones.push({ label: "Verification", state: "completed" });
    milestones.push({ label: "Approval", state: "rejected" });
    milestones.push({ label: finalLabel, state: "upcoming" });
  } else {
    // "Under Review" or "Submitted" (no case created yet)
    milestones.push({ label: "Verification", state: "current" });
    milestones.push({ label: "Approval", state: "upcoming" });
    milestones.push({ label: finalLabel, state: "upcoming" });
  }

  return milestones;
}
