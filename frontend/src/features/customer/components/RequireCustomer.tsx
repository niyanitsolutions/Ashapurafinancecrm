import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/features/auth/useAuth";

// Mirrors features/auth/components/RequireAuth.tsx's RequireOwner (Module 2) — a plain
// role gate, not touching that frozen file. Non-Customers are sent to "/" (HomeRedirect
// routes Owner/Employee to the Dashboard).
export function RequireCustomer() {
  const { role, isBootstrapping } = useAuth();

  if (isBootstrapping) {
    return null;
  }
  if (role !== "customer") {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}
