import { Outlet } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";

// Phase 1 deployment scope: Lead Sources and Reminder Rules tabs go Coming Soon
// alongside Leads-source-editing and Tasks respectively — see router.tsx. Geo Fencing was
// added as an explicit, later, out-of-Phase-1-scope feature request (same precedent as
// Owner Account Management) — not gated behind Coming Soon.
const TABS = [
  { label: "Loan Products", to: "/settings/loan-products", matchKey: "settings" },
  { label: "Insurance Products", to: "/settings/insurance-products", matchKey: "settings" },
  { label: "Document Types", to: "/settings/document-types", matchKey: "settings" },
  { label: "Geo Fencing", to: "/settings/geo-fencing", matchKey: "settings" },
  { label: "Communication Providers", to: "/settings/communication-providers", matchKey: "settings" },
  { label: "Master Settings", to: "/settings", matchKey: "settings", exact: true },
];

export function SettingsLayout() {
  return (
    <>
      <ModuleTabs tabs={TABS} />
      <Outlet />
    </>
  );
}
