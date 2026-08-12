import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/features/auth/useAuth";

// Mirrors features/customer/components/RequireCustomer.tsx — a plain role gate, not
// touching that frozen file. Non-Referral-Partners are sent to "/" (HomeRedirect routes
// Owner/Employee to the Dashboard, Customer to their own portal).
export function RequireReferralPartner() {
  const { role, isBootstrapping } = useAuth();

  if (isBootstrapping) {
    return null;
  }
  if (role !== "referral_partner") {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}
