import { Outlet } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";

// Every Settings destination now shares one tab strip (ModuleTabs already handles
// mobile via horizontal scroll — no separate responsive treatment needed) plus the
// card-grid hub at /settings (SettingsHomePage) as the primary entry point.
const TABS = [
  { label: "Master Settings", to: "/settings", matchKey: "settings", exact: true },
  { label: "Loan Products", to: "/settings/loan-products", matchKey: "settings" },
  { label: "Insurance Products", to: "/settings/insurance-products", matchKey: "settings" },
  { label: "Product Schemas", to: "/settings/product-schemas", matchKey: "settings" },
  { label: "Document Types", to: "/settings/document-types", matchKey: "settings" },
  { label: "Status Masters", to: "/settings/status-masters", matchKey: "settings" },
  { label: "Geo Fencing", to: "/settings/geo-fencing", matchKey: "settings" },
  { label: "Communication Providers", to: "/settings/communication-providers", matchKey: "settings" },
  { label: "Notification Templates", to: "/settings/notification-templates", matchKey: "settings" },
  { label: "Lead Sources", to: "/settings/lead-sources", matchKey: "settings" },
  { label: "Branches", to: "/settings/branches", matchKey: "settings" },
  { label: "Reminder Rules", to: "/settings/reminder-rules", matchKey: ["settings", "reminder_rules"] },
  { label: "Company Settings", to: "/settings/company", matchKey: "settings" },
];

export function SettingsLayout() {
  return (
    <>
      <ModuleTabs tabs={TABS} />
      <Outlet />
    </>
  );
}
