import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";

// Aggregate/list-level views that don't exist as a feature yet (per-employee
// Documents and Activity already exist inside EmployeeDetailsPage's own tabs —
// this is the separate, not-yet-built cross-employee view). Kept as a real,
// deep-linkable tab now so the structure is ready; swapping this for a real
// page later is a routing no-op.
export function EmployeeModulePlaceholderPage({ title, description }: { title: string; description: string }) {
  return (
    <SimplePageLayout title={title}>
      <EmptyState icon="employees" title={title} description={description} />
    </SimplePageLayout>
  );
}
