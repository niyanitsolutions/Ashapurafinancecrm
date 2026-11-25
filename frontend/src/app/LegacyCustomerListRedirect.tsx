import { Navigate, useLocation } from "react-router-dom";

export function LegacyCustomerListRedirect() {
  const location = useLocation();
  const query = new URLSearchParams(location.search);
  const status = query.get("status");
  if (status) {
    query.set(location.pathname === "/applications" ? "application_status" : "customer_status", status);
    query.delete("status");
  }
  if (query.get("unassigned_only") === "true") query.set("assigned_to", "__unassigned__");
  query.delete("unassigned_only");
  return <Navigate replace to={`/leads/document-collection${query.size ? `?${query.toString()}` : ""}`} />;
}
