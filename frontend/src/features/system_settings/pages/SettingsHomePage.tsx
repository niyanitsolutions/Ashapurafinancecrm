import { Link } from "react-router-dom";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { Icon, type IconName } from "@/theme/icons";

interface SettingsNavItem {
  to: string;
  icon: IconName;
  title: string;
  description: string;
}

interface SettingsSection {
  label: string;
  items: SettingsNavItem[];
}

// Settings Center — professional card-grid navigation replacing the old plain-text link
// list. Every destination here is a real, fully-functional page (no Coming Soon left in
// Settings — see the UI/UX redesign initiative). API Settings is deliberately omitted:
// retired in favor of Connections (Integrations), which already covers the same providers.
const SECTIONS: SettingsSection[] = [
  {
    label: "Product Configuration",
    items: [
      { to: "/settings/loan-products", icon: "loan", title: "Loan Products", description: "Manage loan products, eligibility and configuration." },
      { to: "/settings/insurance-products", icon: "insurance", title: "Insurance Products", description: "Manage insurance products and configuration." },
      { to: "/settings/product-schemas", icon: "edit", title: "Product Schemas", description: "Manage dynamic field schemas for loan and insurance applications." },
    ],
  },
  {
    label: "Document & Status",
    items: [
      { to: "/settings/document-types", icon: "documents", title: "Document Types", description: "Manage required document types." },
      { to: "/settings/status-masters", icon: "check-circle", title: "Status Masters", description: "Manage configurable statuses." },
    ],
  },
  {
    label: "Security & Location",
    items: [
      { to: "/settings/geo-fencing", icon: "map-pin", title: "Geo Fencing", description: "Configure location-based activity controls." },
      {
        to: "/geo-exceptions", icon: "shield-check", title: "Geo Exceptions",
        description: "Allow specific employees to temporarily work outside an authorized location.",
      },
    ],
  },
  {
    label: "Communication",
    items: [
      { to: "/settings/communication-providers", icon: "communication", title: "Communication Providers", description: "Configure SMS, WhatsApp and Email providers." },
      { to: "/settings/notification-templates", icon: "bell", title: "Notification Templates", description: "Manage message templates for automated notifications." },
    ],
  },
  {
    label: "Operations",
    items: [
      { to: "/settings/lead-sources", icon: "funnel", title: "Lead Sources", description: "Manage where new leads come from." },
      { to: "/settings/branches", icon: "departments", title: "Branches", description: "Manage branch offices and locations." },
      { to: "/settings/reminder-rules", icon: "clock", title: "Reminder Rules", description: "Configure automated task and follow-up reminders." },
    ],
  },
  {
    label: "Organization",
    items: [
      { to: "/settings/company", icon: "grid", title: "Company Settings", description: "Manage company profile and business hours." },
    ],
  },
];

function SettingsNavCard({ to, icon, title, description }: SettingsNavItem) {
  return (
    <Link
      to={to}
      className="group flex items-start gap-3.5 rounded-card border border-border bg-card p-4 shadow-card transition-all hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-cardHover focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
    >
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <Icon name={icon} className="h-5 w-5" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold text-text">{title}</span>
          <Icon
            name="chevron-right"
            className="h-4 w-4 shrink-0 text-text/30 transition-transform group-hover:translate-x-0.5 group-hover:text-primary"
          />
        </span>
        <span className="mt-1 block text-2xs text-textSecondary">{description}</span>
      </span>
    </Link>
  );
}

export function SettingsHomePage() {
  return (
    <SimplePageLayout title="Settings" subtitle="Manage your CRM configuration and operational settings.">
      <div className="max-w-5xl space-y-8">
        {SECTIONS.map((section) => (
          <div key={section.label}>
            <h2 className="mb-3 text-2xs font-semibold uppercase tracking-wider text-textSecondary">{section.label}</h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {section.items.map((item) => (
                <SettingsNavCard key={item.to} {...item} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </SimplePageLayout>
  );
}
