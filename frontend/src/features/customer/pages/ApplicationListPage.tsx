import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { PortalPage as SimplePageLayout } from "@/features/customer/components/PortalPage";
import { listOwnApplications, type ApplicationListItem } from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";
import { PortalApplicationCard } from "@/features/customer/components/PortalApplicationCard";
import { Icon } from "@/theme/icons";

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
      title="My applications"
      subtitle="Continue a draft, check progress or view an application you have submitted."
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
        <div className="portal-application-grid">
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
        <div className="portal-application-grid">
          {applications.map((app) => (
            <PortalApplicationCard key={app.id} application={app} />
          ))}
        </div>
      )}
    </SimplePageLayout>
  );
}
