import { useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { AuthPageLayout } from "@/features/auth/components/AuthPageLayout";
import { LoginForm } from "@/features/auth/components/LoginForm";
import { LoginTabs, type LoginTabKey } from "@/features/auth/components/LoginTabs";

const INTERNAL_ROLES = ["owner", "employee", "referral_partner"] as const;
const CUSTOMER_ROLES = ["customer"] as const;

const TAB_HEADINGS: Record<LoginTabKey, string> = {
  internal: "Employee / Partner Login",
  customer: "Customer Login",
};

// The single authentication surface for every role and every entry point (Owner, Employee,
// Referral Partner, Customer; normal navigation, an expired secure link, an idle-timeout
// auto-logout, a completed registration/password-reset) — none of those render their own
// login form; they all land here and pass `?return=<path>` when they need the user sent
// somewhere other than HomeRedirect's default role routing after authenticating.
//
// Split into two tabs (Employee/Partner vs Customer) purely as a UI/UX distinction — the
// backend still exposes one `/auth/login` for every role (see LoginForm.tsx for how the
// tab boundary is enforced client-side). Both tabs' forms are always mounted, just hidden
// via CSS when inactive, so switching tabs never loses what the user already typed.
export function LoginPage() {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const returnTo = searchParams.get("return");
  const returnQuery = returnTo ? `?return=${encodeURIComponent(returnTo)}` : "";
  const infoMessage = (location.state as { message?: string } | null)?.message ?? null;
  // A secure application link (/apply/:secureCode) only ever sends a Customer here —
  // defaulting to the Employee/Partner tab in that case means every customer opening their
  // application link has to notice and switch tabs before they can log in at all.
  const [activeTab, setActiveTab] = useState<LoginTabKey>(() => (returnTo?.startsWith("/apply/") ? "customer" : "internal"));

  return (
    <AuthPageLayout>
      <LoginTabs active={activeTab} onChange={setActiveTab} />
      <h2 key={activeTab} className="mt-6 mb-6 text-lg font-semibold text-white animate-fade-in">
        {TAB_HEADINGS[activeTab]}
      </h2>
      {infoMessage && <p className="mb-4 text-sm text-white/60 text-center">{infoMessage}</p>}
      <LoginForm
        hidden={activeTab !== "internal"}
        idPrefix="internal"
        expectedRoles={INTERNAL_ROLES}
        wrongRoleMessage="This account belongs to a Customer. Please use Customer Login."
        returnTo={returnTo}
        returnQuery={returnQuery}
      />
      <LoginForm
        hidden={activeTab !== "customer"}
        idPrefix="customer"
        expectedRoles={CUSTOMER_ROLES}
        wrongRoleMessage="This account belongs to an internal user. Please use Employee / Partner Login."
        returnTo={returnTo}
        returnQuery={returnQuery}
        showCreateAccount
      />
    </AuthPageLayout>
  );
}
