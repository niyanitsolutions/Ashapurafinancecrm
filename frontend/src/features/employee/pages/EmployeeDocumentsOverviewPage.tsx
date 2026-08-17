import { useEffect, useState } from "react";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getErrorMessage } from "@/features/customer/errors";
import { listAllEmployeeDocuments, type EmployeeDocumentOverviewItem } from "@/features/employee/api";
import { formatISTDateTime } from "@/shared/dateFormat";

const PAGE_SIZE = 20;

// Company-wide document overview — reuses the same `employee_documents` records shown
// per-employee inside EmployeeDetailsPage's own Documents tab, just aggregated across
// every employee (see `GET /employees/documents`, owner-only).
export function EmployeeDocumentsOverviewPage() {
  const [items, setItems] = useState<EmployeeDocumentOverviewItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [employeeId, setEmployeeId] = useState("");
  const [documentType, setDocumentType] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setIsLoading(true);
    listAllEmployeeDocuments({ page, page_size: PAGE_SIZE, employee_id: employeeId || undefined, document_type: documentType || undefined })
      .then((res) => {
        setItems(res.data);
        setTotal(res.pagination?.total ?? res.data.length);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, [page, employeeId, documentType]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <SimplePageLayout title="Employee Documents" subtitle="Every document uploaded across all employees, in one place.">
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      <div className="mb-4 flex items-center gap-4">
        <input
          placeholder="Filter by Employee ID" value={employeeId}
          onChange={(e) => { setPage(1); setEmployeeId(e.target.value); }}
          className="rounded border border-border px-3 py-2 text-sm"
        />
        <input
          placeholder="Filter by Document Type" value={documentType}
          onChange={(e) => { setPage(1); setDocumentType(e.target.value); }}
          className="rounded border border-border px-3 py-2 text-sm"
        />
      </div>

      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Employee</th>
              <th className="px-4 py-3">Document Type</th>
              <th className="px-4 py-3">File Name</th>
              <th className="px-4 py-3">Uploaded</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={4} className="px-4 py-6 text-center text-text/50">Loading…</td></tr>
            )}
            {!isLoading && items.length === 0 && (
              <tr>
                <td colSpan={4}>
                  <EmptyState icon="employees" title="No documents yet" description="Employee documents uploaded from their profile will show up here." />
                </td>
              </tr>
            )}
            {items.map((doc) => (
              <tr key={doc.id} className="border-b border-border last:border-0 hover:bg-background">
                <td className="px-4 py-3">{doc.employee_name || "—"}</td>
                <td className="px-4 py-3 capitalize">{doc.document_type}</td>
                <td className="px-4 py-3">{doc.file_name}</td>
                <td className="px-4 py-3">{formatISTDateTime(doc.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between mt-4 text-sm text-text/60">
        <span>Page {page} of {totalPages} ({total} documents)</span>
        <div className="flex gap-2">
          <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Previous</button>
          <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Next</button>
        </div>
      </div>
    </SimplePageLayout>
  );
}
