import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { listProductSchemas, type FormDefinition, type SchemaStatus } from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";
import { formatISTDateTime } from "@/shared/dateFormat";

// Phase 3.1 — Schema Version Display: internal version/status/audit metadata, visible
// to Owner/Admin only (this page sits behind Settings' own `RequireOwner` route guard,
// see app/router.tsx) — never surfaced anywhere in the Customer/Employee/Referral
// Partner-facing forms, which only ever render `fields`/`required_documents`.
//
// Governance round — this was a read-only dead end (no create/edit UI existed at all).
// Each row now links to the real Owner-facing editor (`SchemaEditorPage`).

const STATUS_STYLES: Record<SchemaStatus, string> = {
  active: "bg-success/10 text-success",
  draft: "bg-warning/10 text-warning",
  archived: "bg-text/10 text-text/50",
};

export function ProductSchemasPage() {
  const [schemas, setSchemas] = useState<FormDefinition[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    listProductSchemas()
      .then(setSchemas)
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <SimplePageLayout title="Product Schemas" backTo="/settings">
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}
      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Product</th>
              <th className="px-4 py-3">Category</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Version</th>
              <th className="px-4 py-3">Fields</th>
              <th className="px-4 py-3">Documents</th>
              <th className="px-4 py-3">Updated</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={8} className="px-4 py-6 text-center text-text/50">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && schemas.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-6 text-center text-text/50">
                  No product schemas yet.
                </td>
              </tr>
            )}
            {schemas.map((s) => (
              <tr key={s.id} className="border-b border-border last:border-0">
                <td className="px-4 py-3 text-text">{s.product_name || s.product_id}</td>
                <td className="px-4 py-3 capitalize text-text/70">{s.product_category}</td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STATUS_STYLES[s.status]}`}>{s.status}</span>
                  {s.is_locked && <span className="ml-1.5 rounded-full bg-text/10 px-2 py-0.5 text-xs font-medium text-text/50">Frozen</span>}
                </td>
                <td className="px-4 py-3 text-text/70">Version {s.schema_version}</td>
                <td className="px-4 py-3 text-text/70">{s.fields.length}</td>
                <td className="px-4 py-3 text-text/70">{s.required_documents.length}</td>
                <td className="px-4 py-3 text-text/50 text-xs">{formatISTDateTime(s.updated_at)}</td>
                <td className="px-4 py-3 text-right">
                  <Link to={`/settings/product-schemas/${s.id}`} className="text-sm font-medium text-primary hover:underline">
                    {s.is_locked ? "View" : "Edit"}
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SimplePageLayout>
  );
}
