import { Link } from "react-router-dom";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";

// Phase 1 deployment scope trims this directory to the master data Loan/Insurance
// Management actually reads from — the rest of Settings goes Coming Soon (see router.tsx).
const LINKS: { to: string; label: string }[] = [
  { to: "/settings/loan-products", label: "Loan Products" },
  { to: "/settings/insurance-products", label: "Insurance Products" },
  { to: "/settings/document-types", label: "Document Types" },
  { to: "/settings/status-masters", label: "Status Masters" },
];

// Index page — no sidebar nav exists yet (Dashboard Framework, a later module, owns
// that); these links are the only way to reach each Settings screen today.
export function SettingsHomePage() {
  return (
    <SimplePageLayout title="Settings (Master Data)">
      <div className="bg-card border border-border rounded-card shadow-card divide-y divide-border max-w-lg">
        {LINKS.map((link) => (
          <Link key={link.to} to={link.to} className="block px-4 py-3 text-sm text-primary hover:bg-background hover:underline">
            {link.label}
          </Link>
        ))}
      </div>
    </SimplePageLayout>
  );
}
