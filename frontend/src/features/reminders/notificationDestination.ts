import type { AppNotification } from "./api";

/** References select existing routes; destination APIs remain the authorization boundary. */
export function notificationDestination(n: Pick<AppNotification, "entity_type" | "entity_id">, role: string | null = "employee"): string {
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
    lead: `/leads/${id}`, insurance_case: `/insurance-cases/${id}`, loan_case: `/loan-cases/${id}`,
    application: `/applications/${id}`, customer: `/customers/${id}`,
    support_ticket: `/support-tickets?ticket=${id}`,
    task: `/tasks?task=${id}`,
    advisor: `/insurance-management/advisors/${id}`,
    recruitment_lead: `/insurance-management/recruitment/${id}`,
  };
  return routes[n.entity_type] ?? fallback;
}
