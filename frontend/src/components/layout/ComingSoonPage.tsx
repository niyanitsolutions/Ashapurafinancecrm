import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";

// Phase 1 deployment scope is limited to Dashboard, Leads, Customers, Loan Management,
// Insurance Management and Connections — every other module (Tasks, Reports, Message
// Center, Administration, Referral Partners, most of Settings) routes here instead of
// its real page, so a direct URL can't bypass the nav-level Coming Soon treatment.
// Nothing about the underlying feature is touched; swapping the route element back is
// a routing no-op once a module ships in a later phase.
export function ComingSoonPage({ title, description }: { title: string; description?: string }) {
  return (
    <SimplePageLayout title={title}>
      <EmptyState
        icon="clock"
        title="Coming soon"
        description={description ?? `${title} isn't part of this release yet — it'll be enabled in a future update.`}
      />
    </SimplePageLayout>
  );
}
