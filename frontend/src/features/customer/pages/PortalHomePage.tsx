import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { getOwnCustomerProfile, getOwnDashboard, type Customer, type DocumentPreviewItem, type PortalDashboard } from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";
import { buildMilestones, type MilestoneState } from "@/features/customer/timelineSummary";
import { formatISTDateTime } from "@/shared/dateFormat";
import { Icon, type IconName } from "@/theme/icons";

const MILESTONE_STYLES: Record<MilestoneState, string> = {
  completed: "bg-success text-white",
  current: "bg-primary text-white",
  upcoming: "bg-border text-text/40",
  rejected: "bg-danger text-white",
};
const MILESTONE_ICON: Record<MilestoneState, IconName> = { completed: "check-circle", current: "clock", upcoming: "clock", rejected: "x-circle" };

function SkeletonBlock({ className = "" }: { className?: string }) {
  return <div className={`animate-shimmer rounded-lg bg-gradient-to-r from-border via-background to-border bg-[length:200%_100%] ${className}`} />;
}

function Hero({ customer, dashboard }: { customer: Customer; dashboard: PortalDashboard | null }) {
  const ctaTo = dashboard?.has_application
    ? dashboard.status_label === "Draft"
      ? `/portal/applications/${dashboard.application_id}`
      : `/portal/applications/${dashboard.application_id}/timeline`
    : "/portal/applications/new?category=loan";
  const ctaLabel = dashboard?.has_application ? (dashboard.status_label === "Draft" ? "Continue Application" : "Track Status") : "Start an Application";

  return (
    <div className="mb-6 rounded-card bg-gradient-to-r from-primary to-primary-light px-6 py-6 text-white shadow-card animate-fade-in">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Welcome, {customer.full_name}</h1>
          <p className="text-sm text-white/80 mt-0.5">{customer.customer_code}</p>
        </div>
        <Link
          to={ctaTo}
          className="hover-lift rounded-xl bg-white text-primary text-sm font-semibold py-2.5 px-5 shadow-card"
        >
          {ctaLabel}
        </Link>
      </div>

      {dashboard?.has_application && (
        <div className="mt-5 grid grid-cols-2 sm:grid-cols-4 gap-4 border-t border-white/20 pt-4">
          <div>
            <p className="text-[11px] uppercase tracking-wide text-white/60">Product</p>
            <p className="text-sm font-medium">{dashboard.product_name}</p>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-wide text-white/60">Current Stage</p>
            <p className="text-sm font-medium">{dashboard.current_stage_label}</p>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-wide text-white/60">Progress</p>
            <p className="text-sm font-medium">{dashboard.progress_percent}%</p>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-wide text-white/60">Relationship Manager</p>
            <p className="text-sm font-medium">{dashboard.relationship_manager?.name ?? "Not yet assigned"}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function QuickActionCard({ to, icon, title, subtitle }: { to: string; icon: IconName; title: string; subtitle: string }) {
  return (
    <Link
      to={to}
      className="hover-lift bg-card border border-border rounded-card shadow-card hover:shadow-cardHover p-4 flex items-start gap-3 transition-shadow"
    >
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <Icon name={icon} className="h-5 w-5" />
      </span>
      <span>
        <span className="block text-sm font-semibold text-text">{title}</span>
        <span className="block text-xs text-text/50 mt-0.5">{subtitle}</span>
      </span>
    </Link>
  );
}

function QuickActions({ dashboard }: { dashboard: PortalDashboard }) {
  const isDraft = dashboard.status_label === "Draft";
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
      {isDraft && (
        <QuickActionCard to={`/portal/applications/${dashboard.application_id}`} icon="applications" title="Continue Application" subtitle="Pick up where you left off" />
      )}
      <QuickActionCard to="/portal/documents" icon="upload" title="Upload Documents" subtitle={`${dashboard.pending_documents_count} pending`} />
      <QuickActionCard to="/portal/messages" icon="chat" title="Message your RM" subtitle={dashboard.relationship_manager?.name ?? "Contact support"} />
      {!isDraft && (
        <QuickActionCard to={`/portal/applications/${dashboard.application_id}/timeline`} icon="clock" title="Track Status" subtitle={dashboard.current_stage_label ?? "View progress"} />
      )}
      <QuickActionCard to="/portal/support" icon="shield-check" title="Support" subtitle="Raise a ticket" />
    </div>
  );
}

function ApplicationSummaryCard({ dashboard }: { dashboard: PortalDashboard }) {
  return (
    <div className="bg-card border border-border rounded-card shadow-card p-5">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-text/40 mb-3">Application Summary</h3>
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-text/40">Application Number</dt>
          <dd className="font-medium text-text">{dashboard.application_code}</dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-text/40">Product</dt>
          <dd className="font-medium text-text">{dashboard.product_name}</dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-text/40">Current Stage</dt>
          <dd className="font-medium text-text">{dashboard.current_stage_label}</dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-text/40">Assigned Employee</dt>
          <dd className="font-medium text-text">{dashboard.relationship_manager?.name ?? "Unassigned"}</dd>
        </div>
      </dl>
      <div className="mt-4">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[11px] uppercase tracking-wide text-text/40">Progress</span>
          <span className="text-xs font-medium text-text/60">{dashboard.progress_percent}%</span>
        </div>
        <div className="h-2 rounded-full bg-border overflow-hidden">
          <div className="h-full bg-primary transition-all" style={{ width: `${dashboard.progress_percent}%` }} />
        </div>
      </div>
    </div>
  );
}

function RelationshipManagerCard({ dashboard }: { dashboard: PortalDashboard }) {
  const rm = dashboard.relationship_manager;
  return (
    <div className="bg-card border border-border rounded-card shadow-card p-5 flex flex-col">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-text/40 mb-1">Relationship Manager</h3>
      {rm ? (
        <>
          <p className="text-lg font-semibold text-text mb-3">{rm.name}</p>
          <div className="space-y-1.5 mb-4 text-sm">
            <a href={`tel:${rm.mobile}`} className="flex items-center gap-2 text-text/70 hover:text-primary">
              <Icon name="phone" className="h-4 w-4" /> {rm.mobile}
            </a>
            <a href={`mailto:${rm.email}`} className="flex items-center gap-2 text-text/70 hover:text-primary">
              <Icon name="mail" className="h-4 w-4" /> {rm.email}
            </a>
          </div>
        </>
      ) : (
        <p className="text-sm text-text/40 mb-4">Not yet assigned — we'll let you know once someone is handling your application.</p>
      )}
      <Link to="/portal/support" className="mt-auto text-sm font-medium text-primary hover:underline">
        Contact Support →
      </Link>
    </div>
  );
}

function PendingDocumentsCard({ dashboard }: { dashboard: PortalDashboard }) {
  const flatGroups = dashboard.document_groups;
  return (
    <div className="bg-card border border-border rounded-card shadow-card p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-text/40">Pending Documents</h3>
        <span className="text-xs text-text/50">{dashboard.pending_documents_count} remaining</span>
      </div>
      {flatGroups.length === 0 && <p className="text-sm text-text/40 mb-3">Nothing required yet.</p>}
      {flatGroups.map((group, i) => (
        <div key={group.section ?? "_default"} className={i > 0 ? "mt-3 pt-3 border-t border-border" : ""}>
          {group.section && <p className="text-[11px] font-semibold uppercase tracking-wide text-text/40 mb-1.5">{group.section}</p>}
          <ul className="space-y-1">
            {group.documents.map((doc: DocumentPreviewItem) => (
              <li key={doc.document_type_id} className="text-sm flex items-center gap-1.5">
                <Icon name={doc.uploaded ? "check-circle" : "clock"} className={`h-4 w-4 ${doc.uploaded ? "text-success" : "text-text/30"}`} />
                <span className={doc.uploaded ? "text-text" : "text-text/70"}>{doc.document_type_name}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <Link to="/portal/documents" className="mt-4 inline-block text-sm font-medium text-primary hover:underline">
        Upload →
      </Link>
    </div>
  );
}

function TimelineSummaryWidget({ dashboard }: { dashboard: PortalDashboard }) {
  const milestones = buildMilestones(dashboard);
  return (
    <div className="bg-card border border-border rounded-card shadow-card p-5">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-text/40 mb-4">Timeline</h3>
      <div className="flex items-start overflow-x-auto pb-2">
        {milestones.map((m, i) => (
          <div key={m.label} className="flex items-center">
            <div className="flex flex-col items-center w-24 shrink-0 text-center animate-slide-up" style={{ animationDelay: `${i * 60}ms` }}>
              <span className={`flex h-7 w-7 items-center justify-center rounded-full transition-colors ${MILESTONE_STYLES[m.state]}`}>
                <Icon name={MILESTONE_ICON[m.state]} className="h-4 w-4" />
              </span>
              <span className={`mt-1 text-xs ${m.state === "upcoming" ? "text-text/40" : "text-text"}`}>{m.label}</span>
            </div>
            {i < milestones.length - 1 && <span className="h-0.5 w-6 bg-border shrink-0 -mt-6" />}
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        <Link to={`/portal/applications/${dashboard.application_id}/timeline`} className="text-sm font-medium text-primary hover:underline">
          View Full Timeline →
        </Link>
        {(dashboard.current_stage_label === "Credit Evaluation" || dashboard.current_stage_label === "Offer Acceptance") && (
          <Link to={`/portal/applications/${dashboard.application_id}/loan-offers`} className="text-sm font-medium text-primary hover:underline">
            View Loan Offers →
          </Link>
        )}
      </div>
    </div>
  );
}

const ACTIVITY_ICON: Record<string, IconName> = {
  captured: "applications",
  assigned: "user",
  application_submitted: "check-circle",
  document_uploaded: "upload",
};

function RecentActivity({ dashboard }: { dashboard: PortalDashboard }) {
  return (
    <div className="bg-card border border-border rounded-card shadow-card p-5">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-text/40 mb-2">Recent Activity</h3>
      <ul className="space-y-2.5">
        {dashboard.recent_activity.map((a, i) => (
          <li key={i} className="flex items-start gap-2.5 text-sm">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
              <Icon name={ACTIVITY_ICON[a.event_type] ?? "clock"} className="h-3.5 w-3.5" />
            </span>
            <span>
              <span className="block text-text capitalize">{a.event_type.replace(/_/g, " ")}</span>
              {a.created_at && <span className="block text-xs text-text/40">{formatISTDateTime(a.created_at)}</span>}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// Phase 5 (rebuilt in Phase 5.1, restyled in the Customer Portal redesign) — the Customer
// Portal's landing page. One summary call (`getOwnDashboard`) renders the whole screen;
// every deeper view (full timeline, full document list, full message history) is a
// separate page, fetched only once opened.
export function PortalHomePage() {
  const [customer, setCustomer] = useState<Customer | null | undefined>(undefined);
  const [dashboard, setDashboard] = useState<PortalDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = () => {
    setError(null);
    getOwnDashboard()
      .then(setDashboard)
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(() => {
    getOwnCustomerProfile()
      .then(setCustomer)
      .catch((err) => setError(getErrorMessage(err)));
  }, []);

  useEffect(() => {
    if (!customer) return;
    loadDashboard();
  }, [customer]);

  if (customer === undefined) {
    return (
      <div className="max-w-app mx-auto space-y-4">
        <SkeletonBlock className="h-32" />
        <SkeletonBlock className="h-24" />
      </div>
    );
  }
  if (customer === null) return <Navigate to="/portal/profile/setup" replace />;

  return (
    <div className="max-w-app mx-auto">
      {error && (
        <div className="mb-4">
          <ErrorBanner message={error} />
          <button type="button" onClick={loadDashboard} className="mt-2 text-sm font-medium text-primary hover:underline">
            Try Again
          </button>
        </div>
      )}

      <Hero customer={customer} dashboard={dashboard} />

      {!dashboard && !error && (
        <div className="space-y-4">
          <SkeletonBlock className="h-20" />
          <SkeletonBlock className="h-40" />
        </div>
      )}

      {dashboard && !dashboard.has_application && (
        <div className="bg-card border border-border rounded-card shadow-card p-6 mb-6">
          <h2 className="text-sm font-semibold text-text/70 mb-3">Start a new application</h2>
          <div className="flex gap-3">
            <Link to="/portal/applications/new?category=loan" className="rounded bg-primary text-white text-sm font-medium py-2 px-4 hover:bg-primary-light">
              Apply for a Loan
            </Link>
            <Link
              to="/portal/applications/new?category=insurance"
              className="rounded border border-primary text-primary text-sm font-medium py-2 px-4 hover:bg-primary/10"
            >
              Apply for Insurance
            </Link>
          </div>
        </div>
      )}

      {dashboard && dashboard.has_application && (
        <div className="space-y-4">
          <QuickActions dashboard={dashboard} />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <ApplicationSummaryCard dashboard={dashboard} />
            <RelationshipManagerCard dashboard={dashboard} />
          </div>

          <PendingDocumentsCard dashboard={dashboard} />
          <TimelineSummaryWidget dashboard={dashboard} />

          {dashboard.recent_activity.length > 0 && <RecentActivity dashboard={dashboard} />}

          {/* Having an application for one product must never hide the ability to apply
              for another — this card is always reachable, not conditioned on has_application. */}
          <div className="bg-card border border-border rounded-card shadow-card p-6">
            <h2 className="text-sm font-semibold text-text/70 mb-3">Apply for another product</h2>
            <div className="flex gap-3">
              <Link to="/portal/applications/new?category=loan" className="rounded bg-primary text-white text-sm font-medium py-2 px-4 hover:bg-primary-light">
                Apply for a Loan
              </Link>
              <Link
                to="/portal/applications/new?category=insurance"
                className="rounded border border-primary text-primary text-sm font-medium py-2 px-4 hover:bg-primary/10"
              >
                Apply for Insurance
              </Link>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
