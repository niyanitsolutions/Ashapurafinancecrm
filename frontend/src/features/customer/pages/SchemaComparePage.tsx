import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { compareProductSchemas, listProductSchemas, type FormDefinition, type SchemaCompareResponse } from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";

// Ask #8 — Schema Compare. Version history is exactly what `listProductSchemas`
// already returns (an old ACTIVE becomes ARCHIVED on publish, never deleted) filtered
// to this one product — no separate "list versions" endpoint needed.
export function SchemaComparePage() {
  const [searchParams] = useSearchParams();
  const productCategory = searchParams.get("product_category") ?? "";
  const productId = searchParams.get("product_id") ?? "";

  const [versions, setVersions] = useState<FormDefinition[] | null>(null);
  const [versionA, setVersionA] = useState<number | null>(null);
  const [versionB, setVersionB] = useState<number | null>(null);
  const [compare, setCompare] = useState<SchemaCompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProductSchemas()
      .then((all) => {
        const forProduct = all
          .filter((s) => s.product_category === productCategory && s.product_id === productId)
          .sort((a, b) => a.schema_version - b.schema_version);
        setVersions(forProduct);
        if (forProduct.length >= 2) {
          setVersionA(forProduct[forProduct.length - 2].schema_version);
          setVersionB(forProduct[forProduct.length - 1].schema_version);
        } else if (forProduct.length === 1) {
          setVersionA(forProduct[0].schema_version);
          setVersionB(forProduct[0].schema_version);
        }
      })
      .catch((err) => setError(getErrorMessage(err)));
  }, [productCategory, productId]);

  useEffect(() => {
    if (versionA == null || versionB == null) return;
    setError(null);
    compareProductSchemas(productCategory, productId, versionA, versionB)
      .then(setCompare)
      .catch((err) => setError(getErrorMessage(err)));
  }, [productCategory, productId, versionA, versionB]);

  return (
    <SimplePageLayout title="Compare Schema Versions" subtitle={compare?.product_name} backTo="/settings/product-schemas">
      <ErrorBanner message={error} />

      {versions !== null && versions.length < 2 && (
        <p className="text-sm text-text/50">This product only has one schema version so far — nothing to compare yet.</p>
      )}

      {versions !== null && versions.length >= 2 && (
        <>
          <div className="flex items-center gap-3 mb-6">
            <label className="text-sm text-text/70">
              Version A
              <select
                value={versionA ?? ""}
                onChange={(e) => setVersionA(Number(e.target.value))}
                className="ml-2 rounded border border-border px-2 py-1 text-sm bg-card"
              >
                {versions.map((v) => (
                  <option key={v.schema_version} value={v.schema_version}>
                    Version {v.schema_version} ({v.status}
                    {v.is_locked ? ", frozen" : ""})
                  </option>
                ))}
              </select>
            </label>
            <span className="text-text/30">vs</span>
            <label className="text-sm text-text/70">
              Version B
              <select
                value={versionB ?? ""}
                onChange={(e) => setVersionB(Number(e.target.value))}
                className="ml-2 rounded border border-border px-2 py-1 text-sm bg-card"
              >
                {versions.map((v) => (
                  <option key={v.schema_version} value={v.schema_version}>
                    Version {v.schema_version} ({v.status}
                    {v.is_locked ? ", frozen" : ""})
                  </option>
                ))}
              </select>
            </label>
          </div>

          {compare && (
            <div className="space-y-6 max-w-4xl">
              <DiffSection title="Fields">
                {compare.added_fields.map((f) => (
                  <DiffRow key={f.key} kind="added" label={`${f.label} (${f.key})`} />
                ))}
                {compare.removed_fields.map((f) => (
                  <DiffRow key={f.key} kind="removed" label={`${f.label} (${f.key})`} />
                ))}
                {compare.modified_fields.map((c) => (
                  <DiffRow key={c.key} kind="modified" label={c.key} />
                ))}
                {compare.added_fields.length + compare.removed_fields.length + compare.modified_fields.length === 0 && (
                  <p className="text-xs text-text/40">{compare.unchanged_field_count} field(s), no differences.</p>
                )}
              </DiffSection>

              <DiffSection title="Required Documents">
                {compare.added_documents.map((d) => (
                  <DiffRow key={d.document_type_id} kind="added" label={d.document_type_name || d.document_type_id} />
                ))}
                {compare.removed_documents.map((d) => (
                  <DiffRow key={d.document_type_id} kind="removed" label={d.document_type_name || d.document_type_id} />
                ))}
                {compare.modified_documents.map((c) => (
                  <DiffRow key={c.key} kind="modified" label={c.key} />
                ))}
                {compare.added_documents.length + compare.removed_documents.length + compare.modified_documents.length === 0 && (
                  <p className="text-xs text-text/40">{compare.unchanged_document_count} document(s), no differences.</p>
                )}
              </DiffSection>
            </div>
          )}
        </>
      )}
    </SimplePageLayout>
  );
}

function DiffSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-card border border-border rounded-card shadow-card p-5">
      <h3 className="text-sm font-semibold text-text/70 mb-3">{title}</h3>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

const KIND_STYLE: Record<"added" | "removed" | "modified", { label: string; className: string }> = {
  added: { label: "Added", className: "text-success bg-success/10" },
  removed: { label: "Removed", className: "text-danger bg-danger/10" },
  modified: { label: "Modified", className: "text-warning bg-warning/10" },
};

function DiffRow({ kind, label }: { kind: "added" | "removed" | "modified"; label: string }) {
  const style = KIND_STYLE[kind];
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${style.className}`}>{style.label}</span>
      <span className="text-text/80">{label}</span>
    </div>
  );
}
