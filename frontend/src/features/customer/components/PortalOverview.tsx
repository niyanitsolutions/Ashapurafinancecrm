import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listOwnApplications, type ApplicationListItem } from "../api";
import { PortalApplicationCard } from "./PortalApplicationCard";
import { Icon, type IconName } from "@/theme/icons";

const actions: { to: string; label: string; icon: IconName }[] = [
  { to: "/portal/applications/new?category=loan", label: "Apply for loan", icon: "applications" },
  { to: "/portal/applications/new?category=insurance", label: "Apply for insurance", icon: "shield-check" },
  { to: "/portal/applications", label: "My applications", icon: "grid" },
  { to: "/portal/documents", label: "Upload documents", icon: "upload" },
  { to: "/portal/support", label: "Contact support", icon: "chat" },
];

export function PortalOverview({ pendingDocuments, counts }: { pendingDocuments: number | null; counts?: { all: number; draft: number; submitted: number } }) {
  const [applications, setApplications] = useState<ApplicationListItem[] | null>(null);
  const [error, setError] = useState(false);
  const load = () => { setError(false); listOwnApplications().then(setApplications).catch(() => setError(true)); };
  useEffect(load, []);
  const drafts = applications?.filter(app => app.status === "draft");
  const submitted = applications?.filter(app => app.status === "submitted");
  const recent = [...(applications ?? [])].sort((a, b) => new Date(b.submitted_at ?? b.created_at).getTime() - new Date(a.submitted_at ?? a.created_at).getTime()).slice(0, 4);
  return <section aria-label="Your applications overview">
    <dl className="portal-stat-grid">
      {[{ label: "Your applications", value: counts?.all ?? applications?.length }, { label: "Drafts to complete", value: counts?.draft ?? drafts?.length },
        { label: "Submitted applications", value: counts?.submitted ?? submitted?.length }, { label: "Pending documents · latest application", value: pendingDocuments }].map(stat =>
        <div className="portal-card" key={stat.label}><dt>{stat.label}</dt><dd>{stat.value ?? "—"}</dd></div>)}
    </dl>
    <div className="portal-quick-links">{actions.map(action => <Link key={action.to} to={action.to}><Icon name={action.icon} className="h-5 w-5 shrink-0" />{action.label}</Link>)}</div>
    {error && <div role="alert" className="portal-card">We couldn't load your applications. <button type="button" onClick={load} className="text-primary">Try again</button></div>}
    {applications && applications.length > 0 && <>
      <div className="portal-section-title"><h2>Your recent applications</h2><Link to="/portal/applications">View all applications</Link></div>
      <div className="portal-application-grid">{recent.map(app => <PortalApplicationCard key={app.id} application={app} />)}</div>
    </>}
  </section>;
}
