import type { AppNotification } from "./api";

/** References select existing routes; destination APIs remain the authorization boundary. */
export function notificationDestination(n: Pick<AppNotification, "entity_type" | "entity_id">, role: string | null = "employee"): string {
  if (role === "referral_partner") {
    if (n.entity_type === "partner_commission") return "/referral-portal/commissions";
    if (n.entity_type === "partner_referral") return "/referral-portal/leads";
    if (n.entity_type === "referral_partner") return "/referral-portal/kyc";
    return "/referral-portal/notifications";
  }
  const staff = role === "owner" || role === "employee";
  const fallback = staff ? "/notifications" : "/portal/alerts";
  if (!n.entity_id || !n.entity_type) return fallback;
  const id = encodeURIComponent(n.entity_id);
  if (!staff) {
    if (n.entity_type === "application") return "/portal/documents";
    if (n.entity_type === "support_ticket") return `/portal/support?ticket=${id}`;
    return fallback;
  }
  const routes: Record<string, string> = {
    referral_partner: role === "owner" ? `/referral-partners/kyc-review?partner_id=${id}` : "/notifications",
    partner_commission: role === "owner" ? "/commission-ledger" : "/notifications",
    partner_referral: role === "owner" ? "/leads/document-collection?source_id=submission%3Areferral_partner" : "/notifications",
    employee_hr: role === "owner" ? `/employees/${id}/onboarding` : "/profile/onboarding",
    employee_leave: role === "owner" ? `/employees/leave?employee=${id}` : "/profile/leave",
    daily_follow_up: "/daily-operations/follow-ups",
    operational_issue: "/daily-operations/issues",
    lead: `/leads/${id}`, insurance_case: `/insurance-cases/${id}`, loan_case: `/loan-cases/${id}`,
    application: `/applications/${id}`, customer: `/customers/${id}`,
    support_ticket: `/support-tickets?ticket=${id}`,
    task: `/tasks?task=${id}`,
    advisor: `/insurance-management/advisors/${id}`,
    recruitment_lead: `/insurance-management/recruitment/${id}`,
  };
  return routes[n.entity_type] ?? fallback;
}
