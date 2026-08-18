import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { listOwnApplications, type ApplicationListItem } from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";
import { formatISTDate } from "@/shared/dateFormat";
import { Icon } from "@/theme/icons";

function ApplicationRowCard({ app }: { app: ApplicationListItem }) {
  return (
    <Link
      to={`/portal/applications/${app.id}`}
      className="hover-lift block bg-card border border-border rounded-card shadow-card hover:shadow-cardHover p-5 transition-shadow"
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <p className="text-sm font-semibold text-text">{app.product_name}</p>
          <p className="text-xs text-text/50">{app.application_code}</p>
        </div>
        <span className={`text-xs font-medium rounded-full px-2.5 py-1 ${app.status === "submitted" ? "bg-success/10 text-success" : "bg-warning/10 text-warning"}`}>
          {app.status === "submitted" ? "Submitted" : "Draft"}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 text-sm mb-3">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-text/40">Assigned RM</p>
          <p className="text-text/80">{app.assigned_to_name ?? "Unassigned"}</p>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-wide text-text/40">Created</p>
          <p className="text-text/80">{formatISTDate(app.created_at)}</p>
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-1">
          <span className="text-[11px] uppercase tracking-wide text-text/40">Progress</span>
          <span className="text-xs font-medium text-text/60">{app.progress_percent}%</span>
        </div>
        <div className="h-1.5 rounded-full bg-border overflow-hidden">
          <div className="h-full bg-primary transition-all" style={{ width: `${app.progress_percent}%` }} />
        </div>
      </div>

      <span className="mt-3 inline-block text-sm font-medium text-primary">
        {app.status === "submitted" ? "View →" : "Continue →"}
      </span>
    </Link>
  );
}

export function ApplicationListPage() {
  const [applications, setApplications] = useState<ApplicationListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    listOwnApplications()
      .then(setApplications)
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, []);

  return (
    <SimplePageLayout
      title="My Applications"
      backTo="/portal"
      actions={
        <Link to="/portal/applications/new" className="rounded-lg bg-primary text-white text-sm font-medium py-2 px-4 hover:bg-primary-light">
          Start New Application
        </Link>
      }
    >
      <ErrorBanner message={error} />
      {error && (
        <button type="button" onClick={load} className="mb-4 text-sm font-medium text-primary hover:underline">
          Try Again
        </button>
      )}

      {applications === null && !error && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[0, 1].map((i) => (
            <div key={i} className="animate-shimmer h-40 rounded-card bg-gradient-to-r from-border via-background to-border bg-[length:200%_100%]" />
          ))}
        </div>
      )}

      {applications && applications.length === 0 && (
        <div className="bg-card border border-border rounded-card shadow-card p-10 text-center">
          <span className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Icon name="applications" className="h-6 w-6" />
          </span>
          <p className="text-sm font-medium text-text mb-1">No applications yet</p>
          <p className="text-sm text-text/50 mb-4">Start a Loan or Insurance application to see it here.</p>
          <Link to="/portal" className="inline-block rounded-lg bg-primary text-white text-sm font-medium py-2 px-4 hover:bg-primary-light">
            Go to Dashboard
          </Link>
        </div>
      )}

      {applications && applications.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {applications.map((app) => (
            <ApplicationRowCard key={app.id} app={app} />
          ))}
        </div>
      )}
    </SimplePageLayout>
  );
}
