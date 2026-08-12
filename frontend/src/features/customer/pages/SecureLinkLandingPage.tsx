import { useEffect, useState, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AuthPageLayout } from "@/features/auth/components/AuthPageLayout";
import { ErrorBanner } from "@/features/auth/components/ErrorBanner";
import { useAuth } from "@/features/auth/useAuth";
import {
  claimSecureLink,
  getOwnCustomerProfile,
  resolveSecureLink,
  type ApplicationDetail,
  type ResolvedSecureLink,
} from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";

function StatusScreen({
  title,
  message,
  action,
  children,
}: {
  title: string;
  message: string;
  action?: { label: string; onClick: () => void };
  children?: ReactNode;
}) {
  return (
    <AuthPageLayout title={title}>
      <p className="text-sm text-text/60 text-center">{message}</p>
      {children}
      {action && (
        <button type="button" onClick={action.onClick} className="mt-6 w-full rounded bg-primary text-white text-sm font-medium py-2.5">
          {action.label}
        </button>
      )}
    </AuthPageLayout>
  );
}

// Shown only *after* the customer has authenticated through the single shared /login
// page and the link has been claimed — never before. Deliberately shows only what
// get_secure_link_public_status/claim_secure_link already return (never internal IDs).
function ApplicationSummaryCard({ resolution, application }: { resolution: ResolvedSecureLink; application: ApplicationDetail }) {
  const relationshipManager = application.assigned_to_name ?? resolution.created_by_name;
  return (
    <div className="mb-6 rounded-lg border border-border bg-card/60 p-4 text-sm">
      <div className="flex items-center justify-between mb-3">
        <span className="font-semibold text-text">{application.product_name}</span>
        <span className="text-xs font-medium rounded-full px-2 py-1 bg-primary/10 text-primary">
          {application.status === "submitted" ? "Submitted" : "Pending"}
        </span>
      </div>
      <dl className="space-y-1.5 text-text/70">
        <div className="flex items-center justify-between">
          <dt className="text-text/50">Application No</dt>
          <dd className="text-text font-medium">{application.application_code}</dd>
        </div>
        {resolution.full_name && (
          <div className="flex items-center justify-between">
            <dt className="text-text/50">Lead</dt>
            <dd className="text-text font-medium">{resolution.full_name}</dd>
          </div>
        )}
        {relationshipManager && (
          <div className="flex items-center justify-between">
            <dt className="text-text/50">Relationship Manager</dt>
            <dd className="text-text font-medium">{relationshipManager}</dd>
          </div>
        )}
      </dl>
    </div>
  );
}

// The one landing point for every Secure Application Link. Authentication itself never
// happens here — there is exactly one login experience in this app (see LoginPage.tsx),
// and this page only ever redirects to it (with `?return=/apply/:secureCode`) and waits
// to be sent back. This also means account creation for a brand-new customer goes
// through the same shared Create Account -> OTP -> Password flow every other customer
// uses (see RegisterPage.tsx) — not a secure-link-specific form.
export function SecureLinkLandingPage() {
  const { secureCode } = useParams<{ secureCode: string }>();
  const navigate = useNavigate();
  const { accessToken, role, isBootstrapping } = useAuth();
  const [resolution, setResolution] = useState<ResolvedSecureLink | null>(null);
  const [application, setApplication] = useState<ApplicationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  useEffect(() => {
    if (!secureCode) return;
    resolveSecureLink(secureCode)
      .then(setResolution)
      .catch((err) => setError(getErrorMessage(err)));
  }, [secureCode]);

  // Not authenticated — send straight to the shared login page, `?return=` brings the
  // customer straight back here afterward (a stale Owner/Employee/wrong-Customer
  // session, auto-rehydrated globally from a persisted refresh token, is handled by the
  // role check in the "valid" render branch below, not here).
  //
  // `isBootstrapping` must gate this: AuthProvider's own rehydration (refresh -> profile,
  // two round-trips — see context.tsx) is slower than this page's single
  // `resolveSecureLink` call, so on a cold load (link opened fresh, e.g. from an SMS) an
  // already-logged-in customer would otherwise be bounced to /login before their session
  // finishes loading, forcing a needless re-login.
  useEffect(() => {
    if (!secureCode || isBootstrapping || accessToken || resolution?.link_status !== "valid") return;
    navigate(`/login?return=${encodeURIComponent(`/apply/${secureCode}`)}`, { replace: true });
  }, [secureCode, isBootstrapping, accessToken, resolution, navigate]);

  // Authenticated as a Customer — claim (idempotent: returns the existing Application if
  // one was already created) so the summary below can show the real Application
  // No/status before the customer commits to "Continue Application".
  useEffect(() => {
    if (!secureCode || !accessToken || role !== "customer" || resolution?.link_status !== "valid" || application) return;
    setIsBusy(true);
    claimSecureLink(secureCode)
      .then(setApplication)
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsBusy(false));
  }, [secureCode, accessToken, role, resolution, application]);

  if (!secureCode) return null;

  const loginPath = `/login?return=${encodeURIComponent(`/apply/${secureCode}`)}`;

  const onContinue = async () => {
    if (!application) return;
    const customer = await getOwnCustomerProfile();
    navigate(customer ? `/portal/applications/${application.id}` : "/portal/profile/setup", { replace: true });
  };

  if (!resolution) {
    return (
      <AuthPageLayout title="Continue your application">
        <ErrorBanner message={error} />
        {!error && <p className="text-sm text-text/50 text-center">Loading…</p>}
      </AuthPageLayout>
    );
  }

  switch (resolution.link_status) {
    case "not_found":
    case "disabled":
      return (
        <StatusScreen
          title="Link Invalid"
          message="This application link is invalid or no longer available. Please contact your relationship manager for a new link."
        />
      );
    case "expired": {
      const hasRmContact = resolution.relationship_manager_name || resolution.relationship_manager_mobile || resolution.relationship_manager_email;
      return (
        <StatusScreen title="Application Link Expired" message="Contact your Relationship Manager for a new link.">
          {hasRmContact && (
            <div className="mt-4 rounded-lg border border-border p-3 text-center text-sm">
              {resolution.relationship_manager_name && <p className="font-medium text-text mb-1">{resolution.relationship_manager_name}</p>}
              <div className="flex items-center justify-center gap-4">
                {resolution.relationship_manager_mobile && (
                  <a href={`tel:${resolution.relationship_manager_mobile}`} className="text-primary hover:underline">
                    Call
                  </a>
                )}
                {resolution.relationship_manager_email && (
                  <a href={`mailto:${resolution.relationship_manager_email}`} className="text-primary hover:underline">
                    Email
                  </a>
                )}
                {resolution.relationship_manager_mobile && (
                  <a
                    href={`https://wa.me/91${resolution.relationship_manager_mobile}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary hover:underline"
                  >
                    WhatsApp
                  </a>
                )}
              </div>
            </div>
          )}
        </StatusScreen>
      );
    }
    case "already_used":
      return (
        <StatusScreen
          title="Link Already Used"
          message="This link has already been used to start an application. If you have an account, log in to continue."
          action={{ label: "Log in", onClick: () => navigate(loginPath) }}
        />
      );
    case "already_submitted":
      return (
        <StatusScreen
          title="Application Already Submitted"
          message={`Your application (Ref: ${resolution.application_reference ?? "—"}) was submitted on ${
            resolution.submitted_at ? new Date(resolution.submitted_at).toLocaleDateString() : "—"
          }. Current status: ${resolution.application_status ?? "—"}.`}
          action={{ label: "Log in to check status", onClick: () => navigate(loginPath) }}
        />
      );
    case "valid": {
      if (isBootstrapping) {
        return (
          <AuthPageLayout title="Continue your application">
            <p className="text-sm text-text/50 text-center">Loading…</p>
          </AuthPageLayout>
        );
      }
      if (!accessToken) {
        return (
          <AuthPageLayout title="Continue your application">
            <p className="text-sm text-text/50 text-center">Redirecting to login…</p>
          </AuthPageLayout>
        );
      }
      if (role !== "customer") {
        return (
          <StatusScreen
            title="Wrong Account"
            message="This secure application link is for a customer account. Please login with the correct customer account."
          />
        );
      }
      return (
        <AuthPageLayout title="Continue your application">
          <ErrorBanner message={error} />
          {isBusy && <p className="text-sm text-text/50 text-center">Setting up your application…</p>}
          {!isBusy && application && (
            <>
              <ApplicationSummaryCard resolution={resolution} application={application} />
              <button
                type="button"
                onClick={onContinue}
                className="w-full rounded bg-primary text-white text-sm font-medium py-2.5"
              >
                Continue Application
              </button>
            </>
          )}
        </AuthPageLayout>
      );
    }
  }
}
