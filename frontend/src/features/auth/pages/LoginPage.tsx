import { useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { AuthPageLayout } from "@/features/auth/components/AuthPageLayout";
import { PinAuthPanel } from "@/features/auth/components/PinAuthPanel";
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
// customer tab uses PIN endpoints; internal roles keep password login. The
// forms are always mounted, just hidden
// via CSS when inactive, so switching tabs never loses what the user already typed.
export function LoginPage() {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const returnTo = searchParams.get("return");
  const returnQuery = returnTo ? `?return=${encodeURIComponent(returnTo)}` : "";
  const infoMessage = (location.state as { message?: string } | null)?.message ?? null;
  // Customer is the default tab: the overwhelming majority of logins are customers, and a
  // secure application link (/apply/:secureCode) only ever sends a Customer here. Staff
  // switch to "Employee / Partner" once; the tab switcher keeps whatever each form already
  // has typed (hidden via CSS, never unmounted).
  const [legacyCustomer, setLegacyCustomer] = useState(false);
  const [activeTab, setActiveTab] = useState<LoginTabKey>("customer");

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
      <div hidden={activeTab !== "customer" || legacyCustomer}>
        <PinAuthPanel returnTo={returnTo} onLegacy={() => setLegacyCustomer(true)} />
      </div>
      {activeTab === "customer" && legacyCustomer && (
        <button type="button" className="mb-4 text-primary" onClick={() => setLegacyCustomer(false)}>Use customer PIN sign-in</button>
      )}
      <LoginForm
        hidden={activeTab !== "customer" || !legacyCustomer}
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
