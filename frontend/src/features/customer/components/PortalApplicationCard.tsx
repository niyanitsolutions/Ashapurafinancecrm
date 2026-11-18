import { Link } from "react-router-dom";
import type { ApplicationListItem } from "../api";
import { PortalProgress } from "./PortalPage";
import { formatISTDate } from "@/shared/dateFormat";

export function PortalApplicationCard({ application: app }: { application: ApplicationListItem }) {
  return <article className="portal-card portal-application-card">
    <header><div><p className="text-xs text-slate-500">{app.application_code}</p><h2>{app.product_name}</h2></div>
      <span className={`portal-status ${app.status === "draft" ? "portal-status-draft" : ""}`}>{app.case_status_label ?? (app.status === "draft" ? "Draft" : "Submitted")}</span></header>
    <dl><div><dt>Application date</dt><dd>{formatISTDate(app.created_at)}</dd></div>
      <div><dt>Relationship manager</dt><dd>{app.assigned_to_name ?? "Not yet assigned"}</dd></div>
      {app.submitted_at && <div><dt>Submitted</dt><dd>{formatISTDate(app.submitted_at)}</dd></div>}
    </dl>
    <PortalProgress value={app.progress_percent} label={`${app.application_code} progress`} />
    <p className="text-sm text-slate-600">{app.status === "draft" ? "Next: complete your details and required documents." : "Submitted for processing. Check your documents and updates for any requests."}</p>
    <Link className="portal-button" to={`/portal/applications/${app.id}`}>{app.status === "draft" ? "Continue application" : "View details"}</Link>
  </article>;
}
